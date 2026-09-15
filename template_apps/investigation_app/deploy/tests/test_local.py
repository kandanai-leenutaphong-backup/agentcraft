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


def test_occupied_port_selects_another():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        assert free_port(port) != port