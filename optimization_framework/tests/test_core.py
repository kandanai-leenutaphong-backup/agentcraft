import csv
from http.client import HTTPConnection
import io
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from optimization_framework.contracts import Refusal
from optimization_framework.store import Store
from optimization_framework.service import OptimizationService
from optimization_framework.api import make_server
from optimization_framework.contracts import LOCAL_OPERATOR
from optimization_framework.metrics import derive, footprint


class StoreTests(unittest.TestCase):
    def test_atomic_publication_retains_pending_on_unknown_save(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            with patch("optimization_framework.store.os.link", side_effect=OSError("injected")):
                with self.assertRaises(OSError):
                    store.put({"complete": True})
            pending = list(store.artifacts.glob(".pending-*"))
            self.assertEqual(len(pending), 1)
            self.assertEqual(json.loads(pending[0].read_bytes()), {"complete": True})
            identity = store.put({"complete": True})
            self.assertEqual(store.read_artifact(identity), {"complete": True})
            self.assertTrue(pending[0].exists())
            with self.assertRaises(Refusal):
                store.read_artifact("../index.sqlite3")
            store.close()

    def test_persistence_owner_immutability_and_idempotency(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(root)
            record = {"id": "run", "task_id": "task", "events": [],
                      "candidates": [{"id": "baseline"}]}
            created, fresh = store.create("alice", record, "key", {"task": "task"})
            self.assertTrue(fresh)
            self.assertEqual(created, record)
            self.assertFalse(store.create("alice", record, "key", {"task": "task"})[1])
            with self.assertRaises(Refusal):
                store.create("alice", record, "key", {"task": "other"})
            with self.assertRaises(Refusal):
                store.get("bob", "run")
            with self.assertRaises(Refusal):
                store.update("bob", "run", lambda value: value.update(status="failed"))
            with self.assertRaises(Refusal):
                store.update("alice", "run", lambda value: value["candidates"].clear())
            store.update("alice", "run", lambda value: value["events"].append({"kind": "done"}))
            self.assertEqual(store.db.execute("SELECT COUNT(*) FROM revisions").fetchone()[0], 2)
            with self.assertRaises(sqlite3.IntegrityError):
                store.db.execute("DELETE FROM revisions")
            store.close()
            restarted = Store(root)
            self.assertEqual(restarted.get("alice", "run")["events"], [{"kind": "done"}])
            self.assertEqual(restarted.list("bob"), [])
            identity = restarted.db.execute("SELECT digest FROM runs").fetchone()[0]
            (Path(root) / "artifacts" / identity).write_bytes(b"tampered")
            with self.assertRaises(Refusal):
                restarted.get("alice", "run")
            restarted.close()


class ServiceTests(unittest.TestCase):
    def test_cooperative_cancel_close_and_no_new_work(self):
        entered = threading.Event()
        release = threading.Event()

        class PausedService(OptimizationService):
            def _submit(self, owner, run_id, index):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError("test_gate")
                return super()._submit(owner, run_id, index)

        with tempfile.TemporaryDirectory() as root:
            service = PausedService(root)
            try:
                run = service.start("alice", "agent-tool-availability", idempotency_key="cancel")
                self.assertTrue(entered.wait(5))
                with self.assertRaises(Refusal):
                    service.cancel("bob", run["id"])
                requested = service.cancel("alice", run["id"])
                self.assertEqual(requested["status"], "running")
                self.assertEqual(service.cancel("alice", run["id"]), requested)
                with self.assertRaises(TimeoutError):
                    service.close(timeout=0)
                with self.assertRaises(Refusal):
                    service.start("alice", "agent-tool-availability", idempotency_key="new")
                release.set()
                settled = service.wait("alice", run["id"])
                self.assertEqual(settled["status"], "cancelled")
                self.assertEqual(settled["cleanup"], "settled")
                self.assertTrue(settled["metrics"]["censored"])
                self.assertEqual(len(settled["candidates"]), 1)
                service.close()
                self.assertTrue(all(future.done() for future in service._futures.values()))
                service.close()
            finally:
                release.set()
                service.close()

    def test_concurrent_admission_exclusive_root_and_interrupted_restart(self):
        with tempfile.TemporaryDirectory() as root:
            with OptimizationService(root) as service:
                with self.assertRaises(Refusal):
                    OptimizationService(root)
                with self.assertRaises(Refusal):
                    service.start("alice", "agent-tool-availability", "copilot", "unsupported")
                self.assertEqual(service.list_runs("alice"), [])
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures = [pool.submit(service.start, "alice", "agent-tool-availability",
                                           "deterministic", "one") for _ in range(4)]
                    runs = [future.result(timeout=5) for future in futures]
                self.assertEqual(len({run["id"] for run in runs}), 1)
                run = service.wait("alice", runs[0]["id"])
                with self.assertRaises(Refusal):
                    service.start("alice", "csv-export-transformation", idempotency_key="one")
            service.store.update("alice", run["id"], lambda record: record.update(status="running"))
            with OptimizationService(root) as restarted:
                recovered = restarted.get_run("alice", run["id"])
                self.assertEqual(recovered["status"], "blocked")
                self.assertEqual(recovered["cleanup"], "retained")
                self.assertEqual(recovered["candidates"], run["candidates"])
                self.assertEqual(recovered["events"][-1]["kind"], "reconciliation_required")

    def test_both_tasks_repair_restore_restart_and_feedback(self):
        with tempfile.TemporaryDirectory() as root:
            with OptimizationService(root) as service:
                for task in service.tasks():
                    run = service.start("alice", task["id"], idempotency_key=task["id"], background=False)
                    self.assertEqual(run["status"], "completed")
                    self.assertEqual(run["acceptance"], "passed")
                    self.assertEqual(run["decision"], "inconclusive")
                    self.assertEqual([item["status"] for item in run["candidates"]], ["passed", "failed", "passed"])
                    self.assertEqual(run["metrics"]["repair_cycles"], 1)
                    self.assertEqual(run["metrics"]["calls"], 3)
                    self.assertEqual(run["metrics"]["actions"], 3)
                    self.assertIsNone(run["metrics"]["model_requests"])
                    self.assertFalse(run["metrics"]["first_pass_success"])
                    self.assertEqual(service.start("alice", task["id"], idempotency_key=task["id"])["id"], run["id"])
                    for operation in (lambda: service.get_run("bob", run["id"]),
                                      lambda: service.cancel("bob", run["id"]),
                                      lambda: service.restore("bob", run["id"], run["baseline_candidate_id"], "restore"),
                                      lambda: service.submit_feedback("bob", run["id"], "note", None, "feedback")):
                        with self.assertRaises(Refusal):
                            operation()
                    with self.assertRaises(Refusal):
                        service.restore("alice", run["id"], run["candidates"][1]["id"], "invalid")
                    feedback = service.submit_feedback("alice", run["id"], "review", None, "feedback")
                    duplicate = service.submit_feedback("alice", run["id"], "review", None, "feedback")
                    self.assertEqual(feedback, duplicate)
                    with self.assertRaises(Refusal):
                        service.submit_feedback("alice", run["id"], "different", None, "feedback")
                    feedback_id = feedback["feedback"][0]["id"]
                    response = service.respond_feedback("alice", run["id"], feedback_id, "apply", "verified",
                                                        run["selected_candidate_id"], "response")
                    self.assertEqual(response, service.respond_feedback("alice", run["id"], feedback_id, "apply",
                                     "verified", run["selected_candidate_id"], "response"))
                    restored = service.restore("alice", run["id"], run["baseline_candidate_id"], "restore")
                    self.assertEqual(restored["selected_candidate_id"], run["baseline_candidate_id"])
                    self.assertTrue(restored["restorations"][0]["verified"])
                    self.assertEqual(restored, service.restore("alice", run["id"], run["baseline_candidate_id"], "restore"))
            with OptimizationService(root) as restarted:
                self.assertEqual(len(restarted.list_runs("alice")), 2)
                self.assertEqual(restarted.get_run("alice", run["id"]), restored)
                self.assertEqual(restarted.list_runs("bob"), [])


class AdapterTests(unittest.TestCase):
    def test_cli_subprocess_and_restart_readback(self):
        with tempfile.TemporaryDirectory() as root:
            package = Path(__file__).resolve().parents[1]
            environment = {**os.environ, "PYTHONPATH": str(package / "src")}

            def cli(*args):
                return subprocess.run([sys.executable, "-m", "optimization_framework", "--root", root, *args],
                                      cwd=package, env=environment, capture_output=True, text=True, timeout=10)
            description = cli("describe", "--json")
            self.assertEqual(description.returncode, 0, description.stderr)
            self.assertEqual(len(json.loads(description.stdout)["tasks"]), 2)
            completed = cli("run", "--task", "csv-export-transformation", "--executor", "deterministic",
                            "--idempotency-key", "cli")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            run = json.loads(completed.stdout)
            status = cli("status", "--run", run["id"])
            self.assertEqual(json.loads(status.stdout), run)
            report = cli("report", "--run", run["id"], "--format", "json")
            self.assertEqual(json.loads(report.stdout), run)
            unsupported = cli("run", "--task", "csv-export-transformation", "--executor", "copilot")
            self.assertEqual(unsupported.returncode, 2)

    def test_exports_escape_and_preserve_failures(self):
        with tempfile.TemporaryDirectory() as root, OptimizationService(root) as service:
            run = service.start("alice", "agent-tool-availability", idempotency_key="run", background=False)
            run = service.submit_feedback("alice", run["id"], '=HYPERLINK("evil")<script>alert(1)</script>', None, "feedback")
            payload, _ = service.report("alice", run["id"], "json")
            self.assertEqual(json.loads(payload), run)
            payload, _ = service.report("alice", run["id"], "html")
            self.assertNotIn(b"<script>", payload)
            self.assertIn(b"&lt;script&gt;", payload)
            self.assertIn(b"Deliberately invalid candidate", payload)
            payload, _ = service.report("alice", run["id"], "csv")
            rows = list(csv.DictReader(io.StringIO(payload.decode())))
            feedback = next(row for row in rows if row["record_type"] == "feedback")
            self.assertTrue(feedback["detail"].startswith("'="))
            self.assertTrue(any(row["status"] == "failed" for row in rows))
            with self.assertRaises(Refusal):
                service.report("bob", run["id"], "json")

    def test_http_host_origin_fixed_owner_and_static(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as dist:
            (Path(dist) / "index.html").write_text("<!doctype html><title>fixture</title>")
            (Path(dist) / "secret.txt").write_text("private")
            (Path(dist) / "escape.js").symlink_to(Path(dist) / "secret.txt")
            with OptimizationService(root) as service:
                with self.assertRaises(Refusal):
                    make_server(service, "0.0.0.0", 0)
                server = make_server(service, port=0, dist=dist)
                thread = threading.Thread(target=server.serve_forever)
                thread.start()
                host = f"127.0.0.1:{server.server_port}"

                def request(method, path, body=None, headers=None):
                    connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
                    values = {"Host": host, **(headers or {})}
                    if body is not None:
                        values["Content-Type"] = "application/json"
                    connection.request(method, path, json.dumps(body) if body is not None else None, values)
                    response = connection.getresponse()
                    result = (response.status, response.read(), dict(response.getheaders()))
                    connection.close()
                    return result
                try:
                    self.assertEqual(request("GET", "/api/health")[0], 200)
                    self.assertEqual(request("GET", "/api/health", headers={"Host": "evil.example"})[0], 403)
                    self.assertEqual(request("GET", "/api/health", headers={"Origin": "http://evil.example"})[0], 403)
                    self.assertEqual(request("GET", "/api/health", headers={"X-Owner": "alice"})[0], 403)
                    body = {"task_id": "agent-tool-availability", "executor": "deterministic", "idempotency_key": "api"}
                    self.assertEqual(request("POST", "/api/runs", body)[0], 403)
                    origin = {"Origin": "http://" + host}
                    status, payload, _ = request("POST", "/api/runs", body, origin)
                    self.assertEqual(status, 200, payload)
                    run_id = json.loads(payload)["id"]
                    run = service.wait(LOCAL_OPERATOR, run_id)
                    self.assertEqual(run["status"], "completed")
                    self.assertEqual(len(service.list_runs("alice")), 0)
                    self.assertEqual(request("GET", "/api/runs/" + run_id)[0], 200)
                    self.assertEqual(request("GET", "/api/runs/" + run_id + "/report?format=html")[0], 200)
                    self.assertEqual(request("GET", "/api/tasks")[0], 200)
                    self.assertEqual(json.loads(request("POST", "/api/runs", body, origin)[1])["id"], run_id)
                    self.assertEqual(request("POST", "/api/runs", {**body, "owner": "alice"}, origin)[0], 400)
                    feedback_body = {"text": "SME note", "candidate_id": None, "idempotency_key": "note"}
                    feedback_path = "/api/runs/" + run_id + "/feedback"
                    status, payload, _ = request("POST", feedback_path, feedback_body, origin)
                    self.assertEqual(status, 200, payload)
                    feedback_run = json.loads(payload)
                    self.assertEqual(feedback_run["feedback"][0]["author"], LOCAL_OPERATOR)
                    self.assertEqual(json.loads(request("POST", feedback_path, feedback_body, origin)[1]), feedback_run)
                    response_body = {"disposition": "defer", "reason": "Synthetic only", "candidate_id": None,
                                     "idempotency_key": "response"}
                    response_path = feedback_path + "/" + feedback_run["feedback"][0]["id"] + "/respond"
                    self.assertEqual(request("POST", response_path, response_body, origin)[0], 200)
                    restore_path = "/api/runs/" + run_id + "/restore"
                    self.assertEqual(request("POST", restore_path,
                                            {"candidate_id": run["candidates"][1]["id"], "idempotency_key": "bad"}, origin)[0], 409)
                    status, payload, _ = request("POST", restore_path,
                                                {"candidate_id": run["baseline_candidate_id"], "idempotency_key": "restore"}, origin)
                    self.assertEqual(status, 200, payload)
                    self.assertEqual(json.loads(payload)["selected_candidate_id"], run["baseline_candidate_id"])
                    self.assertEqual(request("POST", "/api/runs/" + run_id + "/cancel", {}, origin)[0], 200)
                    self.assertEqual(request("GET", "/api/runs/" + run_id + "/report?format=html&format=json")[0], 400)
                    self.assertEqual(request("GET", "/")[0], 200)
                    for path in ("/secret.txt", "/escape.js", "/%2e%2e/secret.txt", "/assets/%252e%252e/secret.txt"):
                        self.assertIn(request("GET", path)[0], {400, 403, 404})
                    status, _, headers = request("GET", "/api/runs")
                    self.assertEqual(status, 200)
                    self.assertEqual(headers["Cache-Control"], "no-store, private")
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(5)


class MetricTests(unittest.TestCase):
    def test_golden_event_counts_and_footprint(self):
        record = {"candidates": [{"role": "baseline", "status": "passed", "digest": "a"},
                                  {"role": "submission", "status": "failed", "digest": "b"},
                                  {"role": "submission", "status": "failed", "digest": "b"},
                                  {"role": "submission", "status": "passed", "digest": "c"}],
                  "events": [{"kind": "candidate_created", "elapsed_seconds": 1},
                             {"kind": "check_dispatched", "elapsed_seconds": 2},
                             {"kind": "check_completed", "elapsed_seconds": 4},
                             {"kind": "accepted", "elapsed_seconds": 5},
                             {"kind": "settled", "elapsed_seconds": 6}]}
        metrics = derive(record)
        self.assertEqual(metrics["elapsed_seconds"], 6)
        self.assertEqual(metrics["time_to_verified_acceptance_seconds"], 5)
        self.assertEqual(metrics["repair_cycles"], 1)
        self.assertEqual(metrics["calls"], 1)
        self.assertEqual(metrics["actions"], 1)
        self.assertFalse(metrics["first_pass_success"])
        self.assertIsNone(metrics["model_requests"])
        self.assertEqual(footprint({"source.py": "old\n"}, {"source.py": "new\n"}),
                         {"files_changed": 1, "lines_added": 1, "lines_deleted": 1})


if __name__ == "__main__":
    unittest.main()