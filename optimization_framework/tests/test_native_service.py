import json
from http.client import HTTPConnection
import threading
from unittest.mock import Mock, patch

import pytest

from optimization_framework.contracts import Refusal, digest
from optimization_framework.api import make_server
from optimization_framework.cli import main
from optimization_framework.contracts import LOCAL_OPERATOR
from optimization_framework.service import OptimizationService, TASKS, _evaluate


def executor(*outputs):
    native = Mock(model="gpt-6-astra", effort="max", supported_efforts=("max",))
    native.run.side_effect = [{
        "status": "completed", "candidate_output": output, "elapsed_seconds": 0.25,
        "usage": {"modelMetrics": {"gpt-6-astra": {"requests": {"count": 1}}}},
        "events": [{"kind": "model.call_start"}, {"kind": "assistant.reasoning"}, {"kind": "result"}],
        "coverage": {"model_requests": {"observed_starts": 1}},
        "cleanup": "process_reaped_group_signalled",
    } for output in outputs]
    return native


@pytest.mark.parametrize("task,output", [
    ("agent-tool-availability", '{"tools":["export","search","read"]}'),
    ("csv-export-transformation", '{"quoted":true,"uppercase":true}'),
])
def test_native_success_exact_config_and_baseline_first(tmp_path, task, output):
    native = executor(output)
    with OptimizationService(tmp_path, allow_model_calls=True, copilot_executor=native) as service:
        run = service.start("alice", task, "copilot", "native", background=False)
        assert run["status"] == "completed"
        assert run["acceptance"] == "passed" and run["decision"] == "inconclusive"
        assert [candidate["status"] for candidate in run["candidates"]] == ["passed", "passed"]
        baseline, candidate = run["candidates"]
        assert baseline["duration_seconds"] > 0
        assert candidate["config_sha256"] == digest(output.encode())
        snapshot = service.store.read_artifact(candidate["digest"])
        assert snapshot["files"] == {"source.py": TASKS[task]["source"], "config.json": output}
        assert "source.py" not in candidate["diff"] and "config.json" in candidate["diff"]
        kinds = [event["kind"] for event in run["events"]]
        assert kinds.index("check_completed") < kinds.index("native_dispatched")
        prompt = native.run.call_args.args[0]
        assert "Baseline configuration" in prompt and "Desired behavior" in prompt
        assert output not in prompt
        assert native.run.call_args.kwargs["capture_final_answer"] is True
        assert str(native.run.call_args.kwargs["workspace"]).startswith("/tmp/optimization-native-")
        assert service.start("alice", task, "copilot", "native")["id"] == run["id"]
        assert native.run.call_count == 1
        assert run["metrics"]["model_requests"] == 1
        assert run["metrics"]["coding_latency_seconds"] == 0.25
        assert run["metrics"]["native_event_kinds"] == {"model.call_start": 1, "assistant.reasoning": 1, "result": 1}
        assert run["metrics"]["files_changed"] == 1
        assert run["metrics"]["first_pass_success"] is True
        assert run["metrics"]["repair_cycles"] == 0
        restored = service.restore("alice", run["id"], candidate["id"], "restore")
        assert restored["restorations"][0]["verified"]
        with pytest.raises(Refusal):
            service.get_run("bob", run["id"])


def test_grant_and_config_fail_closed(tmp_path):
    native = executor()
    with OptimizationService(tmp_path, copilot_executor=native) as service:
        with pytest.raises(Refusal, match="model_calls_not_allowed"):
            service.start("alice", "agent-tool-availability", "copilot", "deny")
        assert service.list_runs("alice") == []
        native.run.assert_not_called()
    with OptimizationService(tmp_path, allow_model_calls=True) as service:
        with pytest.raises(Refusal, match="native_executor_not_configured"):
            service.start("alice", "agent-tool-availability", "copilot", "deny")


def test_honest_bounded_repair(tmp_path):
    native = executor('{"tools":["read","export","shell"]}', '{"tools":["read","export","search"]}')
    with OptimizationService(tmp_path, allow_model_calls=True, copilot_executor=native) as service:
        run = service.start("alice", "agent-tool-availability", "copilot", "repair", background=False)
        assert [candidate["status"] for candidate in run["candidates"]] == ["passed", "failed", "passed"]
        assert native.run.call_count == 2
        prompt = native.run.call_args.args[0]
        assert "preserve-search" in prompt and "shell-refused" in prompt
        assert "Observed None; expected True" in prompt
        attempts = [attempt for attempt in run["attempts"] if attempt["role"] == "authoring"]
        assert [attempt["number"] for attempt in attempts] == [1, 2]
        assert attempts[0]["workspace"] != attempts[1]["workspace"]
        assert attempts[0]["executor_result"]["usage"] == attempts[1]["executor_result"]["usage"]
        assert "candidate_output" not in attempts[0]["executor_result"]
        assert run["metrics"]["model_requests"] == 2
        assert run["metrics"]["coding_latency_seconds"] == 0.5
        assert run["metrics"]["repair_cycles"] == 1
        assert run["metrics"]["first_pass_success"] is False


@pytest.mark.parametrize("output", [
    '{}', '[]', '{"tools":["read"],"code":"anything"}', '{"tools":["read","read"]}',
    '{"tools":true}', '{"tools":[1]}', '{"tools":[],"tools":["read"]}',
    '{"tools":NaN}', '```json\n{}\n```', '[' * 2000,
])
def test_strict_schema_retains_failed_attempt(tmp_path, output):
    native = executor(output)
    with OptimizationService(tmp_path, allow_model_calls=True, copilot_executor=native,
                             native_max_attempts=1) as service:
        run = service.start("alice", "agent-tool-availability", "copilot", "invalid", background=False)
        assert run["status"] == "failed" and run["acceptance"] == "failed"
        assert run["candidates"][-1]["checks"][0]["detail"] == "invalid_candidate_configuration"
        assert run["selected_candidate_id"] == run["baseline_candidate_id"]
        assert native.run.call_count == 1


@pytest.mark.parametrize("task,output", [
    ("agent-tool-availability", '{"tools":["read","search"]}'),
    ("csv-export-transformation", '{"uppercase":false,"quoted":true}'),
    ("csv-export-transformation", '{"uppercase":1,"quoted":true}'),
    ("csv-export-transformation", '{"uppercase":true,"quoted":false}'),
])
def test_unchanged_or_invalid_behavior_never_accepted(tmp_path, task, output):
    native = executor(output, output)
    with OptimizationService(tmp_path, allow_model_calls=True, copilot_executor=native) as service:
        run = service.start("alice", task, "copilot", "invalid", background=False)
        assert run["status"] == "failed" and run["acceptance"] == "failed"
        assert native.run.call_count == 2
        assert run["selected_candidate_id"] == run["baseline_candidate_id"]


def test_source_tamper_refused():
    snapshot = {"files": {"source.py": "raise RuntimeError('untrusted')", "config.json": '{"tools":[]}'}}
    with pytest.raises(Refusal, match="untrusted_candidate_source"):
        _evaluate("agent-tool-availability", snapshot, False, native=True)


@pytest.mark.parametrize("status", ["timed_out", "blocked", "failed", "cancelled"])
def test_executor_failure_keeps_telemetry_and_baseline(tmp_path, status):
    native = executor()
    native.run.side_effect = None
    native.run.return_value = {
        "status": status, "failure_code": "fixture_failure", "elapsed_seconds": 0.5,
        "usage": None, "events": [], "coverage": {}, "cleanup": "process_reaped_group_signalled",
    }
    with OptimizationService(tmp_path, allow_model_calls=True, copilot_executor=native) as service:
        run = service.start("alice", "agent-tool-availability", "copilot", "failure", background=False)
        assert run["status"] == status
        assert run["acceptance"] != "passed" and run["decision"] == "inconclusive"
        assert len(run["candidates"]) == 1
        assert native.run.call_count == 1
        assert run["attempts"][-1]["executor_result"]["failure_code"] == "fixture_failure"
        assert run["metrics"]["model_requests"] is None
        assert run["metrics"]["coding_latency_seconds"] == 0.5


def test_cancel_propagates_and_never_selects_candidate(tmp_path):
    entered = threading.Event()
    native = executor()

    def wait_for_cancel(prompt, *, cancel, **kwargs):
        entered.set()
        assert cancel.wait(5)
        return {"status": "cancelled", "elapsed_seconds": 0.1, "usage": None, "events": [],
                "coverage": {}, "cleanup": "process_reaped_group_signalled"}

    native.run.side_effect = wait_for_cancel
    with OptimizationService(tmp_path, allow_model_calls=True, copilot_executor=native) as service:
        run = service.start("alice", "csv-export-transformation", "copilot", "cancel")
        assert entered.wait(5)
        service.cancel("alice", run["id"])
        settled = service.wait("alice", run["id"])
        assert settled["status"] == "cancelled" and settled["acceptance"] == "not_verified"
        assert settled["selected_candidate_id"] == settled["baseline_candidate_id"]
        assert native.run.call_count == 1


def test_failed_baseline_and_frozen_pin_prevent_dispatch(tmp_path):
    native = executor()
    with OptimizationService(tmp_path, allow_model_calls=True, copilot_executor=native) as service:
        with patch("optimization_framework.service._evaluate", side_effect=Refusal("baseline_failed")):
            with patch.object(service, "_verify_pins"):
                with patch("optimization_framework.service.inspect.getsource", return_value="fixture"):
                    run = service.start("alice", "csv-export-transformation", "copilot", "baseline", background=False)
        assert run["status"] == "failed"
        native.run.assert_not_called()
        with pytest.raises(Refusal, match="frozen_evaluator_changed"):
            service._verify_pins(run)


@pytest.mark.parametrize("grant", [False, True])
def test_http_native_admission_requires_service_grant(tmp_path, grant):
    native = executor('{"uppercase":true,"quoted":true}')
    with OptimizationService(tmp_path, allow_model_calls=grant, copilot_executor=native) as service:
        server = make_server(service, port=0)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        host = f"127.0.0.1:{server.server_port}"
        try:
            connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            connection.request("POST", "/api/runs", json.dumps({"task_id": "csv-export-transformation",
                               "executor": "copilot", "idempotency_key": "http"}),
                               {"Host": host, "Origin": "http://" + host, "Content-Type": "application/json"})
            response = connection.getresponse()
            body = json.loads(response.read())
            connection.close()
            if grant:
                assert response.status == 200
                assert service.wait(LOCAL_OPERATOR, body["id"])["acceptance"] == "passed"
                assert native.run.call_count == 1
            else:
                assert response.status == 403 and body["error"] == "model_calls_not_allowed"
                assert service.list_runs(LOCAL_OPERATOR) == []
                native.run.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(5)


@pytest.mark.parametrize("global_flag", [False, True])
def test_cli_explicit_grant_passed_to_service(tmp_path, capsys, global_flag):
    native = executor('{"uppercase":true,"quoted":true}')
    args = ["--root", str(tmp_path)]
    if global_flag:
        args.append("--allow-model-calls")
    args += ["run", "--task", "csv-export-transformation", "--executor", "copilot", "--native-max-attempts", "1"]
    if not global_flag:
        args.append("--allow-model-calls")
    with patch("optimization_framework.cli.CopilotExecutor", return_value=native) as factory:
        assert main(args) == 0
        assert factory.call_args.kwargs["command"][0].endswith("/.local/bin/copilot")
        assert factory.call_args.kwargs["effort"] == "max"
    run = json.loads(capsys.readouterr().out)
    assert run["acceptance"] == "passed" and native.run.call_count == 1


@pytest.mark.parametrize("options", [
    {"allow_model_calls": "true"}, {"native_max_attempts": 0}, {"native_max_attempts": 3},
    {"native_max_attempts": True}, {"native_timeout_seconds": 121}, {"native_timeout_seconds": float("nan")},
])
def test_invalid_native_options_refuse(tmp_path, options):
    with pytest.raises(Refusal):
        OptimizationService(tmp_path, **options)


def test_model_effort_never_falls_back(tmp_path):
    native = executor()
    native.effort = "high"
    with OptimizationService(tmp_path, allow_model_calls=True, copilot_executor=native) as service:
        with pytest.raises(Refusal, match="native_model_effort_required"):
            service.start("alice", "agent-tool-availability", "copilot", "wrong-effort")
        native.run.assert_not_called()