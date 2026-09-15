from pathlib import Path
from unittest.mock import patch

import pytest

from deploy.local import configuration


def test_only_optimizer_coordinates_cross(tmp_path):
    values = {"CYBEREYE_OPENAI_ENDPOINT": "https://fixture.openai.azure.com/openai/v1/",
              "ADX_CLUSTER_URI": "https://other.kusto.windows.net", "AUTH_CLIENT_ID": "foreign",
              "CYBEREYE_OPTIMIZATION_DIR": "/other/experiments", "AZURE_CLIENT_SECRET": "fixture"}
    with patch("deploy.local.dotenv_values", return_value=values), patch.object(Path, "is_file", return_value=True), \
            patch.object(Path, "resolve", return_value=tmp_path):
        environment = configuration(tmp_path, None, {"ADX_DATABASE": "other", "PYTHONPATH": "/other/source"})
    assert "ADX_CLUSTER_URI" not in environment
    assert "ADX_DATABASE" not in environment
    assert "AUTH_CLIENT_ID" not in environment
    assert "AZURE_CLIENT_SECRET" not in environment
    assert "CYBEREYE_OPTIMIZATION_DIR" not in environment
    assert "PYTHONPATH" not in environment


def test_missing_source_refuses(tmp_path):
    with pytest.raises(ValueError, match="supply"):
        configuration(None, tmp_path / "absent", {})