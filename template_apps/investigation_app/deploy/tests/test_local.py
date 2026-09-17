import json
import socket
from pathlib import Path
from unittest.mock import patch

import pytest

from deploy.local import configuration, free_port


def settings(**overrides):
    return {"ADX_CLUSTER_URI": "https://fixture.australiaeast.kusto.windows.net",
            "CYBEREYE_OPENAI_ENDPOINT": "https://fixture.openai.azure.com/openai/v1/", **overrides}


def configured(tmp_path, values, inherited=None):
    source = tmp_path / "source"
    source.mkdir()
    with patch("deploy.local.dotenv_values", return_value=values), patch.object(Path, "is_file", return_value=True):
        return configuration(source_root=source, env_file=None, inherited=inherited or {}, root=tmp_path / "copy")


def test_only_coordinates_cross_and_state_remains_owned(tmp_path):
    environment = configured(tmp_path, settings(
        AZURE_SUBSCRIPTION_ID="subscription", AZURE_RESOURCE_GROUP="resource-group",
        AZURE_CLIENT_SECRET="fixture-not-a-real-secret", AUTH_TENANT_ID="foreign",
        CYBEREYE_AGENT_STORE_DIR="/source/agents", CYBEREYE_COPILOT_WORKSPACES="/source/workspaces",
    ), inherited={"PYTHONPATH": "/source/code", "AUTH_CLIENT_ID": "foreign"})
    assert "AZURE_CLIENT_SECRET" not in environment
    assert "PYTHONPATH" not in environment
    assert environment["AUTH_TENANT_ID"] == environment["AUTH_CLIENT_ID"] == ""
    assert environment["GREMLIN_SUBSCRIPTION_ID"] == "subscription"
    assert environment["CYBEREYE_AGENT_STORE_DIR"] == str(tmp_path / "copy/app/cybereye/.local/agents")
    assert "CYBEREYE_COPILOT_WORKSPACES" not in environment
    assert "CYBEREYE_GUIDE_DATA_DIR" not in environment
    assert "CYBEREYE_OPTIMIZATION_DIR" not in environment


@pytest.mark.parametrize("endpoint", ["http://fixture.example", "https://user:password@fixture.example",
                                       "https://fixture.example?sig=fixture", "https://fixture.example/path"])
def test_invalid_or_credentialed_coordinates_refuse(tmp_path, endpoint):
    with pytest.raises(ValueError, match="coordinate"):
        configured(tmp_path, settings(ADX_CLUSTER_URI=endpoint))


def test_missing_configuration_refuses(tmp_path):
    with pytest.raises(ValueError, match="no configuration file"):
        configuration(source_root=None, env_file=tmp_path / "absent", inherited={})


@pytest.mark.parametrize("allow_model_calls", [False, True])
def test_model_calls_require_an_explicit_launch_flag(tmp_path, capsys, allow_model_calls):
    from deploy.local import main

    environment = configured(tmp_path, settings(), inherited={
        "CYBEREYE_LOCAL_CALL_LIMITS": "untrusted", "CYBEREYE_ALLOW_MODEL_CALLS": "true",
    })
    assert "CYBEREYE_LOCAL_CALL_LIMITS" not in environment
    arguments = ["local", "--check", *(["--allow-model-calls"] if allow_model_calls else [])]
    with patch("sys.argv", arguments), \
            patch("deploy.local.configuration", return_value=environment):
        assert main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["model_calls_enabled"] is allow_model_calls
    assert result["cloud_contacted"] is False
    assert environment["CYBEREYE_ALLOW_MODEL_CALLS"] == str(allow_model_calls).lower()
    assert "call_limits" not in result


@pytest.mark.parametrize("arguments", [["--max-model-calls", "20"], ["--max-data-calls", "100"]])
def test_removed_call_limit_options_refuse_before_launch(arguments):
    from deploy.local import main

    with patch("sys.argv", ["local", *arguments]), patch("deploy.local.configuration", return_value={}), \
            patch("deploy.local.serve") as launch, pytest.raises(SystemExit) as refusal:
        main()
    assert refusal.value.code == 2
    launch.assert_not_called()


def test_occupied_port_selects_another():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        assert free_port(port) != port