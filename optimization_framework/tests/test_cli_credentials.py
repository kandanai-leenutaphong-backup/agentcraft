import json
from unittest.mock import Mock, patch

import pytest

from optimization_framework.cli import main, native_environment
from optimization_framework.contracts import Refusal
from optimization_framework.service import OptimizationService
from optimization_framework.contracts import LOCAL_OPERATOR


def test_credential_bridge_requires_explicit_choice():
    with patch("optimization_framework.cli.subprocess.run") as execute:
        native_environment(False)
        execute.assert_not_called()
        assert main(["run", "--task", "agent-tool-availability", "--github-cli-auth"]) == 2
        execute.assert_not_called()


def test_credential_bridge_is_memory_only_and_refuses_failures():
    with patch("optimization_framework.cli.shutil.which", return_value="/usr/bin/gh"), \
            patch("optimization_framework.cli.subprocess.run") as execute:
        execute.return_value = Mock(returncode=0, stdout=b"synthetic-test-credential\n")
        assert native_environment(True)["COPILOT_GITHUB_TOKEN"] == "synthetic-test-credential"
        assert execute.call_args.kwargs["capture_output"] is True
        execute.return_value = Mock(returncode=1, stdout=b"")
        with pytest.raises(Refusal, match="github_cli_auth_unavailable"):
            native_environment(True)


def test_reading_blocked_run_is_successful_command(tmp_path, capsys):
    with OptimizationService(tmp_path) as service:
        run = service.start(LOCAL_OPERATOR, "agent-tool-availability", "deterministic", "read", background=False)
        service.store.update(LOCAL_OPERATOR, run["id"], lambda record: record.update(status="blocked"))
    assert main(["status", "--root", str(tmp_path), "--run", run["id"]]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "blocked"