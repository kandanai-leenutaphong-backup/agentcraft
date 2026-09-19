import json
import os
from pathlib import Path
import sys
import tempfile
import threading

import pytest

from optimization_framework.executors import CopilotExecutor


SUCCESS = '''
import json, pathlib, sys
args = sys.argv
usage = pathlib.Path(args[args.index("--usage-output-file") + 1])
usage.write_text(json.dumps({"totalUserRequests": 1, "modelMetrics": {"fixture-model": {"requests": {"count": 1, "cost": 1}, "usage": {"inputTokens": 3, "outputTokens": 2, "reasoningTokens": 1}}}, "private": "SECRET"}))
print(json.dumps({"type": "model.call_start", "data": {"model": "fixture-model", "turnId": "turn-1"}}))
print(json.dumps({"type": "assistant.message", "data": {"content": "OK", "model": "fixture-model", "toolRequests": [], "reasoning": "SECRET"}}))
print(json.dumps({"type": "result", "exitCode": 0, "sessionId": args[args.index("--session-id") + 1]}))
'''


@pytest.fixture
def setup_executor():
    with tempfile.TemporaryDirectory(prefix="executor-test-") as directory:
        root = Path(directory)
        repository = root / "original"
        repository.mkdir()
        workspace = root / "workspace"
        workspace.mkdir()
        script = root / "fake_cli.py"

        def make(source=SUCCESS, **kwargs):
            script.write_text(source)
            return CopilotExecutor(
                command=(sys.executable, str(script)), original_repository=repository,
                environment={"PATH": os.defpath}, model="fixture-model",
                supported_efforts=("max",), **kwargs,
            )

        yield make, workspace, repository


def test_success_fresh_sessions_and_private_payloads(setup_executor):
    make, workspace, _repository = setup_executor
    executor = make()
    first = executor.run("test", workspace=workspace, expected_output="OK")
    second = executor.run("test", workspace=workspace, expected_output="OK")
    assert first["status"] == second["status"] == "completed"
    assert first["session_id"] != second["session_id"]
    assert first["resolved_model"] == "fixture-model"
    assert first["resolved_effort"] == "max"
    assert first["coverage"]["usage"] == "read_back"
    assert "SECRET" not in json.dumps(first)
    assert first["elapsed_seconds"] > 0


@pytest.mark.parametrize("tail,code", [
    ('import sys; print(\'Error: Reasoning effort max is not supported\', file=sys.stderr)', "native_refusal_or_error"),
    ('print("not JSON")', "unsupported_or_incomplete_events"),
    ('print(json.dumps({"type": "future.event", "data": {}}))', "unsupported_or_incomplete_events"),
    ('print(json.dumps({"type": "session.error", "data": {"message": "SECRET"}}))', "native_refusal_or_error"),
    ('print(json.dumps({"type": "tool.execution_start", "data": {"toolName": "bash", "toolCallId": "call-1", "arguments": "SECRET"}}))', "deny_all_tool_violation"),
    ('usage.unlink()', "unverified_usage_or_model"),
    ('usage.write_text("invalid")', "unverified_usage_or_model"),
    ('sys.exit(2)', "nonzero_exit"),
])
def test_failure_even_after_success_event(setup_executor, tail, code):
    make, workspace, _repository = setup_executor
    result = make(SUCCESS + tail).run("test", workspace=workspace)
    assert result["status"] != "completed"
    assert result["failure_code"] == code
    assert "SECRET" not in json.dumps(result)


def test_deadline_and_cancel(setup_executor):
    make, workspace, _repository = setup_executor
    source = "import signal, time\nsignal.signal(signal.SIGTERM, signal.SIG_IGN)\ntime.sleep(30)"
    executor = make(source)
    result = executor.run("test", workspace=workspace, timeout_seconds=0.1)
    assert result["status"] == "timed_out"
    assert result["elapsed_seconds"] < 2
    assert result["exit_code"] is not None
    cancel = threading.Event()
    timer = threading.Timer(0.1, cancel.set)
    timer.start()
    try:
        result = executor.run("test", workspace=workspace, cancel=cancel)
    finally:
        timer.join()
    assert result["status"] == "cancelled"
    assert result["exit_code"] is not None


def test_output_bound(setup_executor):
    make, workspace, _repository = setup_executor
    result = make('print("x" * 100000)', max_output_bytes=1024).run("test", workspace=workspace)
    assert result["failure_code"] == "output_limit"


def test_paths_and_tools_refuse(setup_executor):
    make, workspace, repository = setup_executor
    executor = make()
    for bad in (repository, repository.parent, Path("relative")):
        with pytest.raises((ValueError, FileNotFoundError)):
            executor.run("test", workspace=bad)
    (workspace / "escape").symlink_to(repository, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        executor.run("test", workspace=workspace)
    with pytest.raises(ValueError, match="allowlists"):
        make(allowed_tools=("shell(*)",))


def test_unvalidated_effort_blocks_without_launch(setup_executor):
    make, workspace, _repository = setup_executor
    executor = make()
    executor.supported_efforts = ("high",)
    result = executor.run("test", workspace=workspace)
    assert result["status"] == "blocked"
    assert result["failure_code"] == "unvalidated_model_effort"
    assert list(workspace.iterdir()) == []


def test_expected_answer_is_checked(setup_executor):
    make, workspace, _repository = setup_executor
    result = make().run("test", workspace=workspace, expected_output="different")
    assert result["failure_code"] == "unexpected_output"


def test_final_answer_capture_requires_approval_and_success(setup_executor):
    make, workspace, _repository = setup_executor
    executor = make()
    assert "candidate_output" not in executor.run("test", workspace=workspace)
    result = executor.run("test", workspace=workspace, capture_final_answer=True)
    assert result["candidate_output"] == "OK"
    assert "SECRET" not in json.dumps(result)
    failed = executor.run("test", workspace=workspace, capture_final_answer=True, expected_output="other")
    assert "candidate_output" not in failed
    with pytest.raises(ValueError, match="boolean"):
        executor.run("test", workspace=workspace, capture_final_answer="yes")


def test_observed_native_envelope_and_reasoning_omission(setup_executor):
    make, workspace, _repository = setup_executor
    prefix = '''
import json
for kind in ["session.mcp_servers_loaded", "session.tools_updated", "assistant.message_start", "assistant.reasoning", "assistant.idle", "session.usage_checkpoint"]:
    print(json.dumps({"type": kind, "data": {"content": "PRIVATE_REASONING"}}))
print(json.dumps({"type": "model.call_finished", "data": {"outcome": "success", "turnId": "turn-1"}}))
'''
    result = make(prefix + SUCCESS).run("test", workspace=workspace)
    assert result["status"] == "completed"
    assert result["coverage"]["model_requests"]["observed_starts"] == 1
    assert "PRIVATE_REASONING" not in json.dumps(result)


def test_requests_are_not_dispatches(setup_executor):
    make, workspace, _repository = setup_executor
    prefix = '''
import json
print(json.dumps({"type": "assistant.message", "data": {"toolRequests": [{"toolCallId": "request-1", "name": "view", "arguments": {"path": "PRIVATE"}}]}}))
'''
    result = make(prefix + SUCCESS).run("test", workspace=workspace)
    assert result["failure_code"] == "deny_all_tool_violation"
    assert result["coverage"]["tool_requests"]["observed_requests"] == 1
    assert result["coverage"]["tool_requests"]["observed_dispatches"] == 0
    assert "PRIVATE" not in json.dumps(result)


@pytest.mark.parametrize("replacement", [
    '"I cannot comply"', '"I am unable to do that"',
])
def test_textual_refusal_exit_zero(setup_executor, replacement):
    make, workspace, _repository = setup_executor
    result = make(SUCCESS.replace('"OK"', replacement)).run("test", workspace=workspace)
    assert result["failure_code"] == "native_refusal_or_error"


def test_hardlink_and_inherited_configuration_refuse(setup_executor):
    make, workspace, repository = setup_executor
    protected = repository / "protected.txt"
    protected.write_text("original")
    os.link(protected, workspace / "linked.txt")
    with pytest.raises(ValueError, match="hardlinked"):
        make().run("test", workspace=workspace)
    (workspace / "linked.txt").unlink()
    (workspace / ".github").mkdir()
    with pytest.raises(ValueError, match="configuration"):
        make().run("test", workspace=workspace)


def test_usage_symlink_refuses(setup_executor):
    make, workspace, _repository = setup_executor
    source = SUCCESS + '\nusage.unlink()\nusage.symlink_to("/etc/passwd")\n'
    result = make(source).run("test", workspace=workspace)
    assert result["failure_code"] == "unverified_usage_or_model"


def test_child_group_is_cancelled_and_reaped(setup_executor):
    make, workspace, _repository = setup_executor
    source = '''
import pathlib, signal, subprocess, sys, time
child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
pathlib.Path("child.pid").write_text(str(child.pid))
def stop(signum, frame):
    child.wait(timeout=0.2)
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
time.sleep(30)
'''
    result = make(source).run("test", workspace=workspace, timeout_seconds=0.3)
    assert result["status"] == "timed_out"
    child_pid = int((workspace / "child.pid").read_text())
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid, 0)


def test_native_argv_environment_and_usage_metrics(setup_executor):
    make, workspace, _repository = setup_executor
    prefix = '''
import os, pathlib, sys
args = sys.argv
assert "--available-tools=" in args
assert "--allow-all" not in args and "--resume" not in args and "--continue" not in args
assert args[args.index("--reasoning-effort") + 1] == "max"
assert pathlib.Path(os.environ["HOME"]).is_relative_to(pathlib.Path.cwd())
assert pathlib.Path(os.environ["COPILOT_HOME"]).is_relative_to(pathlib.Path.cwd())
assert os.environ["COPILOT_GITHUB_TOKEN"] == "SECRET_TOKEN"
assert "COPILOT_ALLOW_ALL" not in os.environ and "BASH_ENV" not in os.environ
assert "OTEL_EXPORTER_OTLP_ENDPOINT" not in os.environ
'''
    executor = make(prefix + SUCCESS)
    executor.environment.update({"COPILOT_GITHUB_TOKEN": "SECRET_TOKEN", "COPILOT_ALLOW_ALL": "true",
                                 "BASH_ENV": "/private", "OTEL_EXPORTER_OTLP_ENDPOINT": "https://invalid"})
    result = executor.run("test", workspace=workspace)
    assert result["status"] == "completed"
    assert result["usage"]["modelMetrics"]["fixture-model"]["requests"]["count"] == 1
    assert result["usage"]["modelMetrics"]["fixture-model"]["usage"]["reasoningTokens"] == 1


@pytest.mark.parametrize("source,code", [
    (SUCCESS.replace('"exitCode": 0', '"exitCode": 1'), "native_refusal_or_error"),
    (SUCCESS.replace('args[args.index("--session-id") + 1]', '"foreign-session"'), "unsupported_or_incomplete_events"),
    (SUCCESS.replace('"fixture-model"', '"other-model"'), "unverified_usage_or_model"),
    (SUCCESS.replace('"count": 1', '"count": 0'), "unverified_model_request"),
    (SUCCESS.replace('"totalUserRequests": 1', '"totalUserRequests": 1, "codeChanges": {"linesAdded": 1}'), "deny_all_write_violation"),
])
def test_native_integrity_negatives(setup_executor, source, code):
    make, workspace, _repository = setup_executor
    result = make(source).run("test", workspace=workspace)
    assert result["failure_code"] == code


def test_explicit_credentials_never_returned(setup_executor):
    make, workspace, _repository = setup_executor
    prefix = 'import json\nprint(json.dumps({"id": "SECRET_TOKEN", "type": "assistant.reasoning", "data": {"content": "SECRET_TOKEN"}}))\n'
    executor = make(prefix + SUCCESS)
    executor.environment["COPILOT_GITHUB_TOKEN"] = "SECRET_TOKEN"
    result = executor.run("test", workspace=workspace)
    assert result["status"] == "completed"
    assert "SECRET_TOKEN" not in json.dumps(result)


@pytest.mark.parametrize("source,code", [
    (SUCCESS.replace('"requests": {"count": 1, "cost": 1}', '"requests": 1'), "unverified_model_request"),
    ('print(\'{"type":"model.call_finished","data":{"outcome":[]}}\')\n' + SUCCESS, "unsupported_or_incomplete_events"),
    ('print("[" * 2000 + "0" + "]" * 2000)\n' + SUCCESS, "unsupported_or_incomplete_events"),
])
def test_malformed_payloads_return_failure(setup_executor, source, code):
    make, workspace, _repository = setup_executor
    result = make(source).run("test", workspace=workspace)
    assert result["failure_code"] == code