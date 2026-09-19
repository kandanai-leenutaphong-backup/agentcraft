import json
from http.client import HTTPConnection
from pathlib import Path
import sys
import threading
from unittest.mock import patch

import pytest

from optimization_framework.contracts import Refusal, TaskAdapter, digest
from optimization_framework.api import make_server
from optimization_framework.cli import main
from optimization_framework.registry import TaskRegistry, default_registry
from optimization_framework.service import OptimizationService, preflight_experiment
from test_native_service import executor


class AlertAdapter:
    id = "alert-threshold"

    def describe(self):
        return {"id": self.id, "name": "Alert threshold", "description": "Offline alert configuration",
                "domain": "alerting", "task_version": 1, "evaluator_version": "alert-1",
                "configuration_schema": {"type": "object", "additionalProperties": False,
                    "properties": {"threshold": {"type": "integer", "minimum": 1, "maximum": 100}},
                    "required": ["threshold"]},
                "submissions": [{"threshold": 40}, {"threshold": 70}],
                "desired_behavior": "Alert for readings at least 70; lower readings remain quiet.",
                "baseline_checks": ["threshold-behavior"], "candidate_checks": ["threshold-behavior"]}

    def baseline(self):
        return {"schema_version": 1, "task_id": self.id,
                "files": {"source.py": "def alert(reading, threshold):\n    return reading >= threshold\n",
                          "config.json": '{"threshold":80}'}}

    def validate_candidate(self, config):
        return None

    def evaluate(self, snapshot, baseline):
        threshold = json.loads(snapshot["files"]["config.json"])["threshold"]
        readings = [0, 69, 70, 79, 80, 100]
        expected = [reading >= (80 if baseline else 70) for reading in readings]
        namespace = {}
        exec(compile(snapshot["files"]["source.py"], "<trusted-alert-fixture>", "exec"), namespace)
        observed = [namespace["alert"](reading, threshold) for reading in readings]
        return [{"name": "threshold-behavior", "status": "passed" if observed == expected else "failed",
                 "detail": f"Observed {observed}; expected {expected}"}]


def test_registration_and_strict_configuration():
    registry = TaskRegistry()
    adapter = AlertAdapter()
    assert isinstance(adapter, TaskAdapter)
    registry.register(adapter)
    assert registry.tasks()[0]["id"] == adapter.id
    assert registry.evaluate(adapter.id, adapter.baseline(), True)[0]["status"] == "passed"
    with pytest.raises(Refusal, match="duplicate_task"):
        registry.register(AlertAdapter())
    with pytest.raises(Refusal, match="unknown_task"):
        registry.task("not-registered")
    for content in ('{"threshold":true}', '{"threshold":70,"command":"echo no"}',
                    '{"threshold":70,"threshold":80}', '{"threshold":NaN}'):
        with pytest.raises(Refusal, match="invalid_candidate_configuration"):
            registry.validate_candidate(adapter.id, content)
    snapshot = adapter.baseline()
    snapshot["files"]["source.py"] = "raise RuntimeError('must never execute')"
    with pytest.raises(Refusal, match="untrusted_candidate_source"):
        registry.evaluate(adapter.id, snapshot, False)


def test_third_domain_offline_lifecycle(tmp_path):
    registry = TaskRegistry()
    registry.register(AlertAdapter())
    with OptimizationService(tmp_path, registry=registry) as service:
        run = service.start("alice", "alert-threshold", idempotency_key="third", background=False)
        assert run["status"] == "completed"
        assert run["acceptance"] == "passed" and run["decision"] == "inconclusive"
        assert [candidate["status"] for candidate in run["candidates"]] == ["passed", "failed", "passed"]
        assert run["frozen"]["task_digest"] == registry.pins("alert-threshold")["task_digest"]
        candidate = run["candidates"][-1]
        assert json.loads(service.store.read_artifact(candidate["digest"])["files"]["config.json"]) == {"threshold": 70}
        assert "source.py" not in candidate["diff"]
        assert service.restore("alice", run["id"], candidate["id"], "restore")["restorations"][-1]["verified"]


def experiment(executor="deterministic", **changes):
    return {"schema_version": 1, "task_id": "alert-threshold", "task_version": 1,
            "executor": executor, "limits": {"max_submissions": 2, "timeout_seconds": 120},
            "primary_metric": "time_to_verified_acceptance_seconds", "quality_constraints": ["threshold-behavior"],
            **changes}


def test_experiment_cli_preflight_run_and_unknowns(tmp_path, capsys):
    registry = TaskRegistry()
    registry.register(AlertAdapter())
    path = tmp_path / "experiment.json"
    root = tmp_path / "store"
    path.write_text(json.dumps(experiment()))
    assert main(["preflight", "--experiment", str(path), "--root", str(root)], registry=registry) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["status"] == "ready" and receipt["baseline_checks"][0]["status"] == "passed"
    assert not root.exists()
    path.write_text(json.dumps(experiment(pins=receipt["pins"])))
    assert main(["run", "--experiment", str(path), "--root", str(root), "--idempotency-key", "doc"], registry=registry) == 0
    run = json.loads(capsys.readouterr().out)
    assert run["acceptance"] == "passed" and run["frozen"]["experiment"]["pins"] == receipt["pins"]
    path.write_text(json.dumps(experiment(allow_model_calls=True)))
    assert main(["preflight", "--experiment", str(path)], registry=registry) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "invalid_experiment_fields"


@pytest.fixture
def registry():
    result = default_registry()
    result.register(AlertAdapter())
    return result


@pytest.mark.parametrize("changes,code", [
    ({"task_id": "unregistered.module:Adapter"}, "unknown_task"),
    ({"task_version": 2}, "task_version_mismatch"),
    ({"schema_version": True}, "invalid_experiment_schema_version"),
    ({"task_version": True}, "invalid_experiment_task_version"),
    ({"executor": "shell"}, "unsupported_executor"),
    ({"executor": []}, "unsupported_executor"),
    ({"command": "touch /tmp/not-allowed"}, "invalid_experiment_fields"),
    ({"import": "unregistered.module:Adapter"}, "invalid_experiment_fields"),
    ({"allow_model_calls": True}, "invalid_experiment_fields"),
    ({"primary_metric": "made_up_improvement"}, "unknown_primary_metric"),
    ({"primary_metric": {}}, "unknown_primary_metric"),
    ({"quality_constraints": ["threshold-behavior", "not-registered"]}, "unknown_quality_constraint"),
    ({"quality_constraints": []}, "invalid_experiment_quality_constraints"),
    ({"quality_constraints": ["threshold-behavior", "threshold-behavior"]}, "invalid_experiment_quality_constraints"),
    ({"quality_constraints": [{}]}, "invalid_experiment_quality_constraints"),
    ({"limits": {"max_submissions": 1, "timeout_seconds": 30, "command": "anything"}}, "invalid_experiment_limits"),
    ({"limits": {"max_submissions": True, "timeout_seconds": 30}}, "invalid_experiment_limits_max_submissions"),
    ({"limits": {"max_submissions": 3, "timeout_seconds": 30}}, "invalid_experiment_limits_max_submissions"),
    ({"limits": {"max_submissions": 1, "timeout_seconds": 0}}, "invalid_experiment_limits_timeout_seconds"),
    ({"limits": {"max_submissions": 1, "timeout_seconds": 121}}, "invalid_experiment_limits_timeout_seconds"),
    ({"pins": {"task_digest": "0" * 64, "evaluator_digest": "0" * 64}}, "frozen_evaluator_changed"),
    ({"pins": {"task_digest": "0" * 64, "evaluator_digest": "0" * 64, "import": "bad"}}, "invalid_experiment_pins"),
])
def test_document_refusals_do_not_schedule(tmp_path, registry, changes, code):
    native = executor()
    with OptimizationService(tmp_path, registry=registry, copilot_executor=native) as service:
        with pytest.raises(Refusal, match=f"^{code}$"):
            service.run_experiment("alice", experiment(**changes), "refuse", background=False)
        assert service.list_runs("alice") == []
        native.run.assert_not_called()


@pytest.mark.parametrize("description", [
    {"command": "anything"}, {"configuration_schema": {"type": "object", "$ref": "https://invalid/schema"}},
    {"configuration_schema": {"type": "object", "additionalProperties": True, "properties": {}, "required": []}},
    {"configuration_schema": {"type": "object", "additionalProperties": False,
        "properties": {"threshold": {"type": "integer", "unexpected": 1}}, "required": ["threshold"]}},
    {"configuration_schema": {"type": "object", "additionalProperties": False,
        "properties": {"threshold": {"type": "integer"}}, "required": []}},
    {"configuration_schema": {"type": "object", "additionalProperties": False,
        "properties": {"threshold": {"type": "string", "pattern": "["}}, "required": ["threshold"]}},
    {"submissions": []}, {"submissions": [{"threshold": True}]},
    {"baseline_checks": []}, {"candidate_checks": ["check", "check"]},
    {"task_version": True}, {"id": "different"},
])
def test_invalid_adapter_schema_refuses(description):
    adapter = AlertAdapter()
    result = {**adapter.describe(), **description}
    with patch.object(adapter, "describe", return_value=result):
        with pytest.raises(Refusal, match="invalid_task_adapter"):
            TaskRegistry().register(adapter)


@pytest.mark.parametrize("adapter", [AlertAdapter, "unregistered.module:Adapter", object()])
def test_registration_requires_explicit_instance(adapter):
    with pytest.raises(Refusal, match="invalid_task_adapter"):
        TaskRegistry().register(adapter)


class InvalidChecksAdapter(AlertAdapter):
    def __init__(self, result):
        self.result = result

    def evaluate(self, snapshot, baseline):
        return self.result


@pytest.mark.parametrize("result", [
    [], {}, None, [{"name": "threshold-behavior", "status": "passed"}],
    [{"name": "threshold-behavior", "status": "passed", "detail": "claim", "improvement": 100}],
    [{"name": "unregistered", "status": "passed", "detail": "claim"}],
    [{"name": "threshold-behavior", "status": "unknown", "detail": "claim"}],
    [{"name": "threshold-behavior", "status": "passed", "detail": 123}],
])
def test_invalid_evaluator_cannot_forge_success(tmp_path, result):
    registry = TaskRegistry()
    registry.register(InvalidChecksAdapter(result))
    with OptimizationService(tmp_path, registry=registry) as service:
        with pytest.raises(Refusal, match="invalid_evaluator_result"):
            service.preflight(experiment())
        run = service.start("alice", "alert-threshold", idempotency_key="bad-checks", background=False)
        assert run["status"] == "failed" and run["acceptance"] != "passed"
        assert run["selected_candidate_id"] is None and run["decision"] == "inconclusive"


class FailedBaselineAdapter(AlertAdapter):
    def evaluate(self, snapshot, baseline):
        result = super().evaluate(snapshot, baseline)
        if baseline:
            result[0]["status"] = "failed"
        return result


def test_failed_baseline_retained_and_native_never_dispatched(tmp_path):
    registry = TaskRegistry()
    registry.register(FailedBaselineAdapter())
    native = executor('{"threshold":70}')
    with OptimizationService(tmp_path, registry=registry, allow_model_calls=True, copilot_executor=native) as service:
        with pytest.raises(Refusal, match="baseline_failed"):
            service.run_experiment("alice", experiment("copilot"), "preflight", background=False)
        assert service.list_runs("alice") == []
        run = service.start("alice", "alert-threshold", "copilot", "baseline", background=False)
        assert run["status"] == "failed" and run["acceptance"] != "passed"
        assert [candidate["status"] for candidate in run["candidates"]] == ["failed"]
        assert run["selected_candidate_id"] is None
        native.run.assert_not_called()


@pytest.mark.parametrize("outputs,expected", [
    (('{"threshold":40}', '{"threshold":70}'), "completed"),
    (('{"threshold":70}',), "completed"),
    (('{"threshold":80}', '{"threshold":80}'), "failed"),
    (('{"threshold":70,"import":"bad"}', '{"threshold":true}'), "failed"),
])
def test_third_domain_native_mock_config_only(tmp_path, registry, outputs, expected):
    native = executor(*outputs)
    with patch("optimization_framework.service.tempfile.mkdtemp", return_value=str(tmp_path)):
        with OptimizationService(tmp_path / "store", registry=registry, allow_model_calls=True,
                                 copilot_executor=native) as service:
            document = experiment("copilot")
            receipt = service.preflight(document)
            native.run.assert_not_called()
            document["pins"] = receipt["pins"]
            run = service.run_experiment("alice", document, "native-third", background=False)
            assert run["status"] == expected and run["decision"] == "inconclusive"
            assert run["candidates"][0]["status"] == "passed"
            assert native.run.call_count == len(outputs)
            for call in native.run.call_args_list:
                assert "threshold" in call.args[0] and "Desired behavior" in call.args[0]
                assert '"threshold": 70' not in call.args[0]
                assert 0 < call.kwargs["timeout_seconds"] <= 120
            for candidate in run["candidates"]:
                assert "source.py" not in candidate["diff"]
                assert candidate["checks"][0]["evaluator_version"] == "alert-1"
            if expected == "completed":
                assert run["acceptance"] == "passed"
                selected = service.store.read_artifact(run["active_digest"])
                assert json.loads(selected["files"]["config.json"]) == {"threshold": 70}
                assert service.restore("alice", run["id"], run["selected_candidate_id"], "restore")["restorations"][-1]["verified"]
            else:
                assert run["acceptance"] == "failed"
                assert run["selected_candidate_id"] == run["baseline_candidate_id"]
            assert service.run_experiment("alice", document, "native-third")["id"] == run["id"]
            assert native.run.call_count == len(outputs)


def test_permission_and_limits_are_caller_owned(tmp_path, registry):
    native = executor()
    with OptimizationService(tmp_path, registry=registry, copilot_executor=native) as service:
        with pytest.raises(Refusal, match="model_calls_not_allowed"):
            service.preflight(experiment("copilot"))
    with OptimizationService(tmp_path, registry=registry, allow_model_calls=True, copilot_executor=native,
                             native_max_attempts=1, native_timeout_seconds=30) as service:
        with pytest.raises(Refusal, match="experiment_exceeds_service_limits"):
            service.preflight(experiment("copilot"))
        ready = service.preflight(experiment("copilot", limits={"max_submissions": 1, "timeout_seconds": 30}))
        assert ready["status"] == "ready"
    native.run.assert_not_called()


def test_cli_model_flag_separate_and_preflight_never_launches(tmp_path, registry, capsys):
    native = executor('{"threshold":70}')
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(experiment("copilot")))
    args = ["preflight", "--experiment", str(path), "--root", str(tmp_path / "unused")]
    assert main(args, registry=registry, copilot_executor=native) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "model_calls_not_allowed"
    assert main([*args, "--allow-model-calls"], registry=registry, copilot_executor=native) == 0
    assert json.loads(capsys.readouterr().out)["model_dispatched"] is False
    native.run.assert_not_called()
    assert not (tmp_path / "unused").exists()
    with patch("optimization_framework.service.tempfile.mkdtemp", return_value=str(tmp_path)):
        assert main(["run", "--experiment", str(path), "--allow-model-calls", "--root", str(tmp_path / "store")],
                    registry=registry, copilot_executor=native) == 0
    assert json.loads(capsys.readouterr().out)["acceptance"] == "passed"
    assert native.run.call_count == 1


@pytest.mark.parametrize("content", ['{"schema_version":1,"schema_version":1}', '[]', '{"value":NaN}',
                                     '{"value":Infinity}', '[' * 2000, 'x' * 32769])
def test_cli_invalid_json_never_creates_storage(tmp_path, registry, capsys, content):
    path = tmp_path / "invalid.json"
    path.write_text(content)
    root = tmp_path / "store"
    assert main(["run", "--experiment", str(path), "--root", str(root)], registry=registry) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "invalid_experiment"
    assert not root.exists()


@pytest.mark.parametrize("options", [["--executor", "deterministic"], ["--native-max-attempts", "1"],
                                     ["--native-timeout-seconds", "1"]])
def test_cli_document_flag_conflicts_refuse(tmp_path, registry, capsys, options):
    path = tmp_path / "experiment.json"
    path.write_text(json.dumps(experiment()))
    assert main(["run", "--experiment", str(path), *options], registry=registry) == 2
    assert json.loads(capsys.readouterr().err)["error"] == "experiment_argument_conflict"


def test_attempt_limit_and_idempotency_policy(tmp_path, registry):
    with OptimizationService(tmp_path, registry=registry) as service:
        document = experiment(limits={"max_submissions": 1, "timeout_seconds": 120})
        run = service.run_experiment("alice", document, "one", background=False)
        assert run["status"] == "failed" and len(run["candidates"]) == 2
        assert run["selected_candidate_id"] == run["baseline_candidate_id"]
        with pytest.raises(Refusal, match="idempotency_conflict"):
            service.run_experiment("alice", experiment(), "one")
        with pytest.raises(Refusal):
            service.get_run("bob", run["id"])


def test_deadline_exhaustion_retains_baseline(tmp_path, registry):
    native = executor('{"threshold":70}')
    with OptimizationService(tmp_path, registry=registry, allow_model_calls=True, copilot_executor=native) as service:
        completed = native.run.side_effect

        def expire(*args, **kwargs):
            run_id = next(iter(service._started))
            service._started[run_id] -= 121
            return next(completed)

        native.run.side_effect = expire
        with patch("optimization_framework.service.tempfile.mkdtemp", return_value=str(tmp_path)):
            run = service.run_experiment("alice", experiment("copilot"), "timeout", background=False)
        assert run["status"] == "timed_out" and run["acceptance"] != "passed"
        assert run["selected_candidate_id"] == run["baseline_candidate_id"]
        assert run["decision"] == "inconclusive" and native.run.call_count == 1
        assert run["attempts"][-1]["role"] == "authoring"


def test_task_and_evaluator_drift_refuse_restore(tmp_path, registry, monkeypatch):
    with OptimizationService(tmp_path, registry=registry) as service:
        run = service.run_experiment("alice", experiment(), "pin", background=False)
        adapter = registry.adapter("alert-threshold")
        description = adapter.describe()
        with patch.object(adapter, "describe", return_value={**description, "task_version": 2}):
            with pytest.raises(Refusal):
                service.restore("alice", run["id"], run["selected_candidate_id"], "changed-task")

        def replacement(self, snapshot, baseline):
            return [{"name": "threshold-behavior", "status": "passed", "detail": "unverified"}]

        monkeypatch.setattr(AlertAdapter, "evaluate", replacement)
        with pytest.raises(Refusal, match="frozen_evaluator_changed"):
            service.restore("alice", run["id"], run["selected_candidate_id"], "changed-evaluator")
        assert service.get_run("alice", run["id"])["restorations"] == []


def test_registration_leaves_core_unchanged_and_does_not_import_domain(tmp_path):
    import optimization_framework.service as service_module

    source = Path(service_module.__file__).parent
    before = {str(path): digest(path.read_bytes()) for path in source.rglob("*.py")}
    modules = {name for name in sys.modules if name.startswith("optimization_framework")}
    registry = default_registry()
    with patch("importlib.import_module", side_effect=AssertionError("no plugin import discovery")):
        registry.register(AlertAdapter())
        with OptimizationService(tmp_path, registry=registry) as service:
            run = service.run_experiment("alice", experiment(), "unchanged-core", background=False)
            assert run["acceptance"] == "passed"
    assert before == {str(path): digest(path.read_bytes()) for path in source.rglob("*.py")}
    assert modules == {name for name in sys.modules if name.startswith("optimization_framework")}
    assert all(b"alert-threshold" not in path.read_bytes() for path in source.rglob("*.py"))


def test_existing_http_tasks_route_is_dynamic(tmp_path, registry):
    with OptimizationService(tmp_path, registry=registry) as service:
        server = make_server(service, port=0)
        thread = threading.Thread(target=server.serve_forever)
        thread.start()
        connection = HTTPConnection("127.0.0.1", server.server_port, timeout=5)
        try:
            connection.request("GET", "/api/tasks")
            response = connection.getresponse()
            assert response.status == 200
            tasks = json.loads(response.read())["tasks"]
            assert len(tasks) == 3 and tasks[-1]["id"] == "alert-threshold"
        finally:
            connection.close()
            server.shutdown()
            server.server_close()
            thread.join(5)


def test_runtime_constant_tamper_refuses_and_pins_are_stable(tmp_path, registry, monkeypatch):
    pins = registry.pins("alert-threshold")
    with OptimizationService(tmp_path, registry=registry) as service:
        for unused in range(12):
            service.preflight(experiment())
            assert registry.pins("alert-threshold") == pins
        run = service.run_experiment("alice", experiment(), "constants", background=False)
        code = AlertAdapter.evaluate.__code__
        changed = tuple(71 if value == 70 else value for value in code.co_consts)
        assert changed != code.co_consts
        monkeypatch.setattr(AlertAdapter.evaluate, "__code__", code.replace(co_consts=changed))
        with pytest.raises(Refusal, match="frozen_evaluator_changed"):
            service.restore("alice", run["id"], run["selected_candidate_id"], "constant-tamper")