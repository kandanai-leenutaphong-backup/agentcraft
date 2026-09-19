"""Persisted local reference loop. Public calls require an explicit storage owner.

OptimizationService(root): one active process per private root.
describe(), tasks(), start(owner, task_id, executor, idempotency_key, background=True),
get_run(owner, run_id), list_runs(owner), wait(owner, run_id, timeout=10),
cancel(owner, run_id), restore(owner, run_id, candidate_id, idempotency_key),
submit_feedback(owner, run_id, text, candidate_id, idempotency_key),
respond_feedback(owner, run_id, feedback_id, disposition, reason, candidate_id,
                 idempotency_key), report(owner, run_id, format), close(timeout=10).
All run-returning operations read back persisted records. Refusal.code is stable.
"""

from concurrent.futures import ThreadPoolExecutor
import difflib
import fcntl
import inspect
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import uuid

from .contracts import LOCAL_OPERATOR, Refusal, SCHEMA_VERSION, TERMINAL, canonical, digest, experiment_document, text, timestamp
from .metrics import METRIC_VERSION, derive, footprint
from .registry import TaskRegistry, default_registry
from .store import Store

_DEFAULT_REGISTRY = default_registry()
TASKS = {task["id"]: _DEFAULT_REGISTRY.task(task["id"]) for task in _DEFAULT_REGISTRY.tasks()}
AGENT_SOURCE = TASKS["agent-tool-availability"]["source"]
CSV_SOURCE = TASKS["csv-export-transformation"]["source"]


def _config(task_id: str, content: str) -> dict:
    return _DEFAULT_REGISTRY.validate_candidate(task_id, content)


def _evaluate(task_id: str, snapshot: dict, baseline: bool, *, native: bool = False,
              registry: TaskRegistry | None = None) -> list[dict]:
    return (registry if registry is not None else _DEFAULT_REGISTRY).evaluate(task_id, snapshot, baseline, native=native)


def _executor_permission(executor, allow_model_calls, copilot_executor):
    if executor not in ("deterministic", "copilot"):
        raise Refusal("unsupported_executor")
    if executor == "copilot":
        if allow_model_calls is not True:
            raise Refusal("model_calls_not_allowed", 403)
        if copilot_executor is None:
            raise Refusal("native_executor_not_configured", 409)
        if (copilot_executor.model != "gpt-6-astra" or copilot_executor.effort != "max"
                or "max" not in copilot_executor.supported_efforts):
            raise Refusal("native_model_effort_required", 409)


def preflight_experiment(document: dict, *, registry: TaskRegistry,
                         allow_model_calls: bool = False, copilot_executor=None,
                         native_max_attempts: int = 2, native_timeout_seconds: float = 120) -> dict:
    document = experiment_document(document)
    _executor_permission(document["executor"], allow_model_calls, copilot_executor)
    task_id = document["task_id"]
    task = registry.task(task_id)
    pins = registry.pins(task_id)
    if document["task_version"] != task["task_version"]:
        raise Refusal("task_version_mismatch", 409)
    if "pins" in document and document["pins"] != pins:
        raise Refusal("frozen_evaluator_changed", 409)
    if any(name not in task["candidate_checks"] for name in document["quality_constraints"]):
        raise Refusal("unknown_quality_constraint")
    limits = document["limits"]
    if document["executor"] == "copilot":
        if limits["max_submissions"] > native_max_attempts or limits["timeout_seconds"] > native_timeout_seconds:
            raise Refusal("experiment_exceeds_service_limits", 403)
    elif limits["max_submissions"] > len(task["submissions"]):
        raise Refusal("insufficient_offline_submissions", 409)
    started = time.monotonic()
    snapshot = task["baseline_snapshot"]
    checks = registry.evaluate(task_id, snapshot, True)
    if pins != registry.pins(task_id):
        raise Refusal("frozen_evaluator_changed", 409)
    if not all(check["status"] == "passed" for check in checks):
        raise Refusal("baseline_failed", 409)
    if time.monotonic() - started >= limits["timeout_seconds"]:
        raise Refusal("experiment_timeout", 409)
    return {"schema_version": 1, "status": "ready", "experiment": document,
            "experiment_digest": digest(canonical(document)), "pins": pins,
            "baseline_digest": digest(canonical(snapshot)), "baseline_checks": checks,
            "metric_version": METRIC_VERSION, "decision": "inconclusive",
            "authoring": "config-only", "independent": False, "model_dispatched": False,
            "limitations": ["Trusted in-process adapters; no OS sandbox or production capability claim.",
                            "Deadline checked between evaluator calls; running trusted code cannot be interrupted.",
                            "Primary metric and quality references frozen; no comparative improvement rule.",
                            "Native runtime credentials and live behavior not probed by preflight."]}


class OptimizationService:
    def __init__(self, root: str | Path, *, allow_model_calls: bool = False,
                 copilot_executor=None, native_max_attempts: int = 2,
                 native_timeout_seconds: float = 120, registry: TaskRegistry | None = None):
        if type(allow_model_calls) is not bool:
            raise Refusal("invalid_model_call_grant")
        if type(native_max_attempts) is not int or not 1 <= native_max_attempts <= 2:
            raise Refusal("invalid_native_attempt_limit")
        if type(native_timeout_seconds) not in (int, float) or not 0 < native_timeout_seconds <= 120:
            raise Refusal("invalid_native_timeout")
        self.allow_model_calls = allow_model_calls
        self.copilot_executor = copilot_executor
        self.native_max_attempts = native_max_attempts
        self.native_timeout_seconds = native_timeout_seconds
        self.registry = registry if registry is not None else default_registry()
        self.store = Store(root)
        descriptor = os.open(self.store.root / "service.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        self._lease = os.fdopen(descriptor, "a+")
        try:
            fcntl.flock(self._lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            self._lease.close()
            self.store.close()
            raise Refusal("storage_root_in_use", 409) from error
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="optimization")
        self._futures = {}
        self._stops = {}
        self._started = {}
        self._closing = False
        self._closed = False
        try:
            with self.store.lock:
                rows = self.store.db.execute("SELECT owner,id FROM runs").fetchall()
            for owner, run_id in rows:
                record = self.store.get(owner, run_id)
                if record["status"] == "running":
                    def reconcile(run):
                        run.update(status="blocked", cleanup="retained", phase="terminal")
                        run["limitations"].append("Previous process interrupted; unfinished computation was not replayed.")
                        self._event(run, "reconciliation_required", "Interrupted local worker no longer owns this root")
                    self.store.update(owner, run_id, reconcile)
        except BaseException:
            self._pool.shutdown(wait=True)
            self._lease.close()
            self.store.close()
            raise

    def tasks(self) -> list[dict]:
        return self.registry.tasks()

    def describe(self) -> dict:
        native = self.allow_model_calls and self.copilot_executor is not None
        return {"schema_version": SCHEMA_VERSION, "executor": ["deterministic", "copilot"] if native else ["deterministic"],
                "operator": LOCAL_OPERATOR, "evidence_class": "synthetic-integration",
                "tasks": self.tasks(), "metric_version": METRIC_VERSION,
                "native_evaluation": native, "cloud_calls": False,
                "allow_model_calls": self.allow_model_calls,
                "native_authoring": "config-only; trusted same-user evaluation; no OS sandbox",
                "storage_root": str(self.store.root)}

    def _open(self):
        if self._closing:
            raise Refusal("service_closing", 409)

    def preflight(self, document: dict) -> dict:
        with self._lock:
            self._open()
            return preflight_experiment(document, registry=self.registry,
                                        allow_model_calls=self.allow_model_calls, copilot_executor=self.copilot_executor,
                                        native_max_attempts=self.native_max_attempts,
                                        native_timeout_seconds=self.native_timeout_seconds)

    def run_experiment(self, owner: str, document: dict, idempotency_key: str,
                       *, background: bool = True) -> dict:
        document = experiment_document(document)
        return self.start(owner, document["task_id"], document["executor"], idempotency_key,
                          background=background, experiment=document)

    def _event(self, run, kind, detail, candidate_id=None, **extra):
        started = self._started.get(run["id"])
        previous = run["events"][-1]["elapsed_seconds"] if run["events"] else 0.0
        elapsed = max(previous, time.monotonic() - started) if started is not None else previous
        at = timestamp()
        event = {"id": uuid.uuid4().hex, "at": at, "kind": kind, "detail": detail,
                 "candidate_id": candidate_id, "sequence": len(run["events"]) + 1,
                 "schema_version": SCHEMA_VERSION, "actor": "trusted-deterministic-runner",
                 "elapsed_seconds": elapsed, "outcome": "completed", **extra}
        run["events"].append(event)
        run["updated_at"] = at
        run["metrics"] = derive(run)
        return event["id"]

    def start(self, owner: str, task_id: str, executor: str = "deterministic",
              idempotency_key: str = "", *, background: bool = True, experiment: dict | None = None) -> dict:
        text(owner, "owner", 128)
        text(task_id, "task_id", 128)
        _executor_permission(executor, self.allow_model_calls, self.copilot_executor)
        self.registry.adapter(task_id)
        text(idempotency_key, "idempotency_key", 128)
        with self._lock:
            self._open()
            preflight = self.preflight(experiment) if experiment is not None else None
            if preflight is not None and (task_id != preflight["experiment"]["task_id"]
                                           or executor != preflight["experiment"]["executor"]):
                raise Refusal("experiment_argument_conflict")
            task = self.registry.task(task_id)
            run_id = uuid.uuid4().hex
            now = timestamp()
            frozen = {"task_version": task["task_version"], "task": task, "evaluator_version": task["evaluator_version"],
                      **self.registry.pins(task_id),
                      "dispatch_digest": digest(inspect.getsource(_evaluate).encode()),
                      "metric_version": METRIC_VERSION, "max_submissions": len(task["configs"]) - 1,
                      "policy": "acceptance-only demonstration; comparison inconclusive",
                      "evidence_class": "synthetic-integration", "independent": False}
            record = {"schema_version": SCHEMA_VERSION, "id": run_id, "task_id": task_id,
                      "task_name": task["name"], "domain": task["domain"], "status": "running",
                      "phase": "created", "acceptance": "not_verified", "decision": "inconclusive",
                      "evidence_class": "synthetic-integration", "executor": executor,
                      "created_at": now, "updated_at": now, "metrics": {}, "candidates": [],
                      "events": [], "feedback": [], "restorations": [], "attempts": [],
                      "selected_candidate_id": None, "baseline_candidate_id": uuid.uuid4().hex,
                      "known_good_candidate_ids": [], "active_digest": None,
                      "frozen": frozen, "cleanup": "retained", "_requests": {},
                      "limitations": ["Synthetic integration only; executor is deterministic, not a coding agent.",
                                      "No model calls or real coding-speed/improvement measurement; model_requests is unobserved/null.",
                                      "Trusted in-process evaluator is not an independent sandbox or held-out evaluation.",
                                      "Selection demonstrates passing artifacts, not comparative promotion or deployment.",
                                      "Single-host local storage; no native execution, cloud acceptance or resumable computation."]}
            if executor == "copilot":
                frozen.update(max_submissions=self.native_max_attempts, evidence_class="local-live",
                              authoring="config-only", timeout_seconds=self.native_timeout_seconds,
                              model="gpt-6-astra", effort="max")
                record.update(evidence_class="local-live", limitations=[
                    "Native config-only authoring; no arbitrary code authoring or OS sandbox.",
                    "Frozen trusted source evaluated in-process as the same user; no independent isolation or held-out evaluation.",
                    "Measured native authoring latency is not a comparative A/B coding-speed result; decision remains inconclusive.",
                    "Deny-all native tools; model receives baseline configuration and desired behavior, not a prescribed solution.",
                    "Private native runtime state retained under /tmp for operator cleanup; never publish session files.",
                    "Usage is CLI-reported; hidden requests and provider-internal effective effort remain unverified.",
                    "Single-host local storage; no cloud acceptance or resumable computation."])
            if preflight is not None:
                if preflight["pins"] != {key: frozen[key] for key in preflight["pins"]}:
                    raise Refusal("frozen_evaluator_changed", 409)
                frozen.update(experiment=preflight["experiment"], experiment_digest=preflight["experiment_digest"],
                              preflight=preflight, **preflight["experiment"]["limits"])
            self._started[run_id] = time.monotonic()
            self._event(record, "admitted", "Frozen task admitted")
            request = {"task_id": task_id, "executor": executor}
            if preflight is not None:
                request["experiment_digest"] = preflight["experiment_digest"]
            record, fresh = self.store.create(owner, record, idempotency_key, request)
            if fresh:
                self._stops[run_id] = threading.Event()
                self._futures[run_id] = self._pool.submit(self._execute, owner, run_id)
            else:
                self._started.pop(run_id, None)
                run_id = record["id"]
        return self.get_run(owner, run_id) if background else self.wait(
            owner, run_id, timeout=self.native_max_attempts * (self.native_timeout_seconds + 5) + 10)

    def _verify_pins(self, run):
        pins = self.registry.pins(run["task_id"])
        if (any(run["frozen"].get(key) != value for key, value in pins.items())
            or run["frozen"].get("dispatch_digest") != digest(inspect.getsource(_evaluate).encode())
            or run["frozen"]["task"] != self.registry.task(run["task_id"])):
            raise Refusal("frozen_evaluator_changed", 409)

    def _budget(self, run):
        if "experiment" not in run["frozen"]:
            return run["frozen"].get("timeout_seconds", self.native_timeout_seconds)
        remaining = run["frozen"]["timeout_seconds"] - (time.monotonic() - self._started[run["id"]])
        if remaining <= 0:
            raise Refusal("experiment_timeout", 409)
        return remaining

    def _submit(self, owner, run_id, index, *, config_text=None, authoring_attempt_id=None):
        run = self.store.get(owner, run_id)
        self._budget(run)
        self._verify_pins(run)
        task = run["frozen"]["task"]
        native = run["executor"] == "copilot"
        candidate_id = run["baseline_candidate_id"] if index == 0 else uuid.uuid4().hex
        snapshot = {"schema_version": 1, "task_id": run["task_id"],
                    "files": {"source.py": task["source"],
                              "config.json": config_text if config_text is not None else
                                  json.dumps(task["configs"][index], indent=2, sort_keys=True) + "\n"}}
        if index == 0:
            snapshot = task["baseline_snapshot"]
        identity = self.store.put(snapshot)
        attempt_id = uuid.uuid4().hex

        def dispatch(record):
            record["phase"] = "evaluating"
            record["attempts"].append({"id": attempt_id, "candidate_id": candidate_id,
                                       "digest": identity, "at": timestamp(), "role": "baseline" if index == 0 else "submission",
                                       "authoring_attempt_id": authoring_attempt_id})
            parent = self._event(record, "candidate_created", "Immutable source/config snapshot created", candidate_id,
                                 artifact_digest=identity)
            self._event(record, "check_dispatched", "Frozen deterministic evaluator dispatched", candidate_id,
                        parent_action_id=parent, outcome="attempted")
        self.store.update(owner, run_id, dispatch)
        started = time.monotonic()
        try:
            checks = _evaluate(run["task_id"], self.store.read_artifact(identity), index == 0,
                               native=native, registry=self.registry)
        except Refusal as error:
            if not native or error.code != "invalid_candidate_configuration":
                raise
            checks = [{"name": "configuration-schema", "status": "failed", "detail": error.code}]
        self._verify_pins(run)
        self._budget(run)
        duration = time.monotonic() - started
        for check in checks:
            check.update(candidate_digest=identity, evaluator_version=run["frozen"]["evaluator_version"],
                         evidence_class=run["evidence_class"] if index else "synthetic-integration")
        passed = all(check["status"] == "passed" for check in checks)
        baseline = self.store.read_artifact(run["candidates"][0]["digest"])["files"] if run["candidates"] else snapshot["files"]
        diff = "".join(line for filename in sorted(snapshot["files"])
                       for line in difflib.unified_diff(baseline[filename].splitlines(True),
                                                       snapshot["files"][filename].splitlines(True),
                                                       fromfile="baseline/" + filename, tofile="candidate/" + filename))
        candidate = {"id": candidate_id, "parent_id": run["candidates"][-1]["id"] if run["candidates"] else None,
                     "name": ("Known-good baseline", "Deliberately invalid candidate", "Repaired candidate")[index],
                     "digest": identity, "status": "passed" if passed else "failed",
                     "hypothesis": ("Existing behavior remains valid", "Exercise rejection without weakening checks",
                                    "Repair the failed invariant and preserve existing behavior")[index],
                     "diff": diff, "checks": checks, "role": "baseline" if index == 0 else "submission",
                     "duration_seconds": duration, "at": timestamp(), "attempt_id": attempt_id}
        candidate["config_sha256"] = digest(snapshot["files"]["config.json"].encode("utf-8"))
        if native and index:
            candidate.update(name=f"Native config attempt {index}",
                             hypothesis="Apply desired behavior while preserving frozen invariants",
                             authoring_attempt_id=authoring_attempt_id)

        def settle(record):
            record["candidates"].append(candidate)
            self._event(record, "check_completed", "All checks passed" if passed else "Failed candidate retained",
                        candidate_id, duration_seconds=duration, outcome="passed" if passed else "failed")
            if passed:
                record["known_good_candidate_ids"].append(candidate_id)
            if index == 0:
                if passed:
                    record["selected_candidate_id"] = candidate_id
                    record["active_digest"] = identity
            if index > 0 and passed and not self._stops[run_id].is_set():
                record.update(selected_candidate_id=candidate_id, active_digest=identity, acceptance="passed")
                record["_footprint"] = footprint(baseline, snapshot["files"])
                self._event(record, "accepted", "Artifact selected by frozen trusted acceptance only", candidate_id)
        self.store.update(owner, run_id, settle)
        if index == 0 and not passed:
            raise Refusal("baseline_failed", 409)
        return candidate

    def _native(self, owner, run_id):
        run = self.store.get(owner, run_id)
        baseline = self.store.read_artifact(run["candidates"][0]["digest"])["files"]["config.json"]
        task = run["frozen"]["task"]
        desired = task["desired_behavior"] + "\nSchema: " + json.dumps(task["configuration_schema"], sort_keys=True)
        prompt = ("Author a replacement JSON configuration only. Return one JSON object without markdown, "
                  "explanation or reasoning. No tools are permitted. Trusted runner applies configuration "
                  "to a separate immutable snapshot; source is not editable.\nBaseline configuration:\n"
                  + baseline + "\nDesired behavior and schema:\n" + desired)
        feedback = ""
        for attempt in range(1, run["frozen"]["max_submissions"] + 1):
            if self._stops[run_id].is_set():
                return "cancelled"
            self._verify_pins(self.store.get(owner, run_id))
            timeout = self._budget(run)
            workspace = Path(tempfile.mkdtemp(prefix="optimization-native-", dir="/tmp"))
            attempt_id = uuid.uuid4().hex
            self.store.update(owner, run_id, lambda record: self._event(
                record, "native_dispatched", "Config-only authoring dispatched", outcome="attempted",
                actor="trusted-native-supervisor", attempt_id=attempt_id, workspace=str(workspace)))
            started = time.monotonic()
            try:
                result = self.copilot_executor.run(
                    prompt + feedback, workspace=workspace, timeout_seconds=timeout,
                    cancel=self._stops[run_id], capture_final_answer=True)
            except (OSError, ValueError):
                result = {"status": "blocked", "failure_code": "native_preflight_failed",
                          "elapsed_seconds": time.monotonic() - started, "usage": None, "events": [],
                          "coverage": {}, "cleanup": "not_started"}
            result = dict(result)
            output = result.pop("candidate_output", None)
            identity = self.store.put(result)

            def retain(record):
                record["attempts"].append({"id": attempt_id, "candidate_id": None, "digest": identity,
                                           "role": "authoring", "at": timestamp(), "number": attempt,
                                           "workspace": str(workspace), "executor_result": result})
                self._event(record, "native_completed", "Native executor evidence retained",
                            actor="trusted-native-supervisor", attempt_id=attempt_id,
                            outcome=result["status"], duration_seconds=result["elapsed_seconds"])
            self.store.update(owner, run_id, retain)
            if result["status"] != "completed":
                return result["status"] if result["status"] in TERMINAL else "blocked"
            if not isinstance(output, str):
                return "blocked"
            candidate = self._submit(owner, run_id, attempt, config_text=output, authoring_attempt_id=attempt_id)
            if candidate["status"] == "passed":
                return "completed"
            feedback = ("\nPrevious final JSON:\n" + output[:8192] +
                        "\nActual frozen-check failures; repair configuration without changing checks:\n" +
                        json.dumps([check for check in candidate["checks"] if check["status"] != "passed"]))
        return "failed"

    def _execute(self, owner, run_id):
        try:
            for phase in ("preflight", "preparing", "running"):
                self.store.update(owner, run_id, lambda record, phase=phase:
                                  (record.update(phase=phase), self._event(record, "phase", phase)))
            native_status = None
            if self.store.get(owner, run_id)["executor"] == "copilot":
                if not self._stops[run_id].is_set():
                    self._submit(owner, run_id, 0)
                    native_status = self._native(owner, run_id)
            else:
                for index in range(self.store.get(owner, run_id)["frozen"]["max_submissions"] + 1):
                    if self._stops[run_id].is_set():
                        break
                    candidate = self._submit(owner, run_id, index)
                    if index > 0 and candidate["status"] == "passed":
                        break

            def finish(record):
                cancelled = self._stops[run_id].is_set()
                for phase in ("deciding", "finalizing"):
                    record["phase"] = phase
                    self._event(record, "phase", phase)
                record.update(status="cancelled" if cancelled else native_status or "completed",
                              phase="terminal", cleanup="settled")
                if record["acceptance"] != "passed" and not cancelled:
                    if record["status"] == "completed":
                        record["status"] = "failed"
                    record["acceptance"] = "failed" if record["status"] == "failed" else "not_verified"
                if any(attempt.get("executor_result", {}).get("cleanup") == "incomplete"
                       for attempt in record["attempts"]):
                    record["cleanup"] = "retained"
                self._event(record, "settled", record["status"])
            self.store.update(owner, run_id, finish)
        except Exception as error:
            def fail(record):
                record.update(status="timed_out" if isinstance(error, Refusal) and error.code == "experiment_timeout"
                              else "failed", phase="terminal", cleanup="retained")
                self._event(record, "execution_failed", error.code if isinstance(error, Refusal) else "execution_error",
                            outcome="failed")
            self.store.update(owner, run_id, fail)
        finally:
            self._started.pop(run_id, None)

    def get_run(self, owner: str, run_id: str) -> dict:
        run = self.store.get(owner, run_id)
        for attempt in run["attempts"]:
            self.store.read_artifact(attempt["digest"])
        return {key: value for key, value in run.items() if not key.startswith("_")}

    def list_runs(self, owner: str) -> list[dict]:
        return [self.get_run(owner, run["id"]) for run in self.store.list(owner)]

    def wait(self, owner: str, run_id: str, timeout: float = 10) -> dict:
        self.store.get(owner, run_id)
        future = self._futures.get(run_id)
        if future:
            future.result(timeout=timeout)
        return self.get_run(owner, run_id)

    def cancel(self, owner: str, run_id: str) -> dict:
        with self._lock:
            run = self.store.get(owner, run_id)
            if run["status"] not in TERMINAL:
                self._stops[run_id].set()
                def request(record):
                    if not any(event["kind"] == "cancel_requested" for event in record["events"]):
                        self._event(record, "cancel_requested", "Worker will stop at the next safe boundary")
                self.store.update(owner, run_id, request)
        return self.get_run(owner, run_id)

    @staticmethod
    def _candidate(run, candidate_id):
        candidate = next((item for item in run["candidates"] if item["id"] == candidate_id), None)
        if candidate is None:
            raise Refusal("candidate_not_found", 404)
        return candidate

    def _operation(self, owner, run_id, operation, key, payload, change):
        text(key, "idempotency_key", 128)
        fingerprint = digest(canonical({"operation": operation, **payload}))
        with self._lock:
            self._open()
            def update(run):
                existing = run["_requests"].get(key)
                if existing:
                    if existing != fingerprint:
                        raise Refusal("idempotency_conflict", 409)
                    return
                change(run)
                run["_requests"][key] = fingerprint
            self.store.update(owner, run_id, update)
        return self.get_run(owner, run_id)

    def submit_feedback(self, owner: str, run_id: str, feedback_text: str,
                        candidate_id: str | None, idempotency_key: str) -> dict:
        text(feedback_text, "text")
        def submit(run):
            if candidate_id is not None:
                self._candidate(run, candidate_id)
            feedback_id = uuid.uuid4().hex
            run["feedback"].append({"id": feedback_id, "at": timestamp(), "author": owner,
                                    "text": feedback_text, "candidate_id": candidate_id,
                                    "disposition": None, "reason": None})
            self._event(run, "feedback_submitted", feedback_text, candidate_id,
                        actor=owner, feedback_id=feedback_id)
        return self._operation(owner, run_id, "feedback", idempotency_key,
                               {"text": feedback_text, "candidate_id": candidate_id}, submit)

    def respond_feedback(self, owner: str, run_id: str, feedback_id: str, disposition: str,
                         reason: str, candidate_id: str | None, idempotency_key: str) -> dict:
        if disposition not in {"apply", "clarify", "defer", "decline"}:
            raise Refusal("invalid_disposition")
        text(reason, "reason")
        def respond(run):
            feedback = next((item for item in run["feedback"] if item["id"] == feedback_id), None)
            if feedback is None:
                raise Refusal("feedback_not_found", 404)
            candidate = self._candidate(run, candidate_id) if candidate_id is not None else None
            if disposition == "apply" and (candidate is None or candidate["status"] != "passed"):
                raise Refusal("applied_feedback_requires_verified_candidate", 409)
            response = self._event(run, "feedback_response", reason, candidate_id, actor=owner,
                                   feedback_id=feedback_id, disposition=disposition,
                                   check_names=[check["name"] for check in candidate["checks"]] if candidate else [])
            feedback.update(disposition=disposition, reason=reason, response_candidate_id=candidate_id,
                            response_event_id=response)
        return self._operation(owner, run_id, "respond", idempotency_key,
                               {"feedback_id": feedback_id, "disposition": disposition,
                                "reason": reason, "candidate_id": candidate_id}, respond)

    def restore(self, owner: str, run_id: str, candidate_id: str, idempotency_key: str) -> dict:
        def restore(run):
            if run["status"] not in TERMINAL:
                raise Refusal("run_not_settled", 409)
            candidate = self._candidate(run, candidate_id)
            if candidate["status"] != "passed" or candidate_id not in run["known_good_candidate_ids"]:
                raise Refusal("restore_requires_known_good", 409)
            self._verify_pins(run)
            started = time.monotonic()
            snapshot = self.store.read_artifact(candidate["digest"])
            checks = _evaluate(run["task_id"], snapshot, candidate["role"] == "baseline",
                               native=run["executor"] == "copilot", registry=self.registry)
            self._verify_pins(run)
            if not all(check["status"] == "passed" for check in checks):
                raise Refusal("restore_verification_failed", 409)
            run.update(selected_candidate_id=candidate_id, active_digest=candidate["digest"])
            self.store.read_artifact(run["active_digest"])
            run["restorations"].append({"at": timestamp(), "candidate_id": candidate_id, "verified": True,
                                        "digest": candidate["digest"], "checks": checks,
                                        "duration_seconds": time.monotonic() - started})
            self._event(run, "restored", "Exact known-good snapshot read back and behavior verified", candidate_id)
        return self._operation(owner, run_id, "restore", idempotency_key,
                               {"candidate_id": candidate_id}, restore)

    def report(self, owner: str, run_id: str, format: str = "json") -> tuple[bytes, str]:
        from .reporting import render
        return render(self.get_run(owner, run_id), format)

    def close(self, timeout: float = 10):
        if not isinstance(timeout, (int, float)) or not 0 <= timeout < float("inf"):
            raise Refusal("invalid_close_timeout")
        deadline = time.monotonic() + timeout
        with self._lock:
            if self._closed:
                return
            self._closing = True
            for stop in self._stops.values():
                stop.set()
            futures = list(self._futures.values())
        for future in futures:
            future.result(timeout=max(0, deadline - time.monotonic()))
        self._pool.shutdown(wait=True)
        with self._lock:
            if not self._closed:
                self._lease.close()
                self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()