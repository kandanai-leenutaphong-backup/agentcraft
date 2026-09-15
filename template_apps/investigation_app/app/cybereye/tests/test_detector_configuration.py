import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.cybereye.backend.investigation import Scanner, default_configuration, load_configuration
from app.cybereye.tests.test_detector_engine import FakeAdx, T0
from app.cybereye.backend.models import ScanRequest
from datetime import timedelta


def test_main_file_reproduces_default_and_overrides_query_threshold(tmp_path):
    source = Path(__file__).resolve().parents[1] / "control/situation_detector.json"
    assert load_configuration(source) == default_configuration()
    config = json.loads(source.read_text())
    config["rule_sets"][0]["rules"] = [{"builtin": "explicit_credential_burst", "parameters": {"threshold": 3}}]
    path = tmp_path / "detector.json"
    path.write_text(json.dumps(config))
    loaded = load_configuration(path)
    adx = FakeAdx()
    original = adx.parameterized
    adx.parameterized = Mock(side_effect=original)
    scanner = Scanner(adx, loaded)
    asyncio.run(scanner.scan_async(ScanRequest(start=T0, end=T0 + timedelta(hours=1))))
    assert adx.executed == ["explicit_credential_burst"]
    assert adx.parameterized.call_args.args[1]["rule_threshold"] == 3
    assert "event_count >= rule_threshold" in adx.parameterized.call_args.args[0]


def test_main_config_refuses_unknown_rules_invalid_processing_and_missing_files(tmp_path):
    path = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        load_configuration(path)
    config = {"version": "bad", "max_window_seconds": 172800, "rule_sets": [
        {"id": "rules", "rules": [{"builtin": "not_registered"}]}]}
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="Unknown builtin"):
        load_configuration(path)
    config["rule_sets"][0]["rules"] = [{"builtin": "explicit_credential_burst", "processing": {"kind": "arbitrary"}}]
    path.write_text(json.dumps(config))
    with pytest.raises(ValueError, match="entity_groups"):
        load_configuration(path)


def test_main_rule_readback_uses_configured_battery():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.cybereye.backend.api.scanning import router
    from app.cybereye.backend.security import Principal, current_principal

    configuration = default_configuration()
    configuration["rule_sets"][0]["rules"] = configuration["rule_sets"][0]["rules"][:1]
    application = FastAPI()
    application.include_router(router)
    application.state.scanner = Scanner(FakeAdx(), configuration)
    application.dependency_overrides[current_principal] = lambda: Principal("local:fixture", issuer="local-preview")
    with TestClient(application) as client:
        rules = client.get("/api/cyber/rules").json()
        assert len(rules) == 1 and rules[0]["rule_id"] == "explicit_credential_burst"
        response = client.get("/api/cyber/detector/configuration")
        assert response.status_code == 200
        assert response.json()["configuration"] == configuration
        assert response.json()["component"] == "situation_detector"
        application.dependency_overrides.clear()
        assert client.get("/api/cyber/detector/configuration").status_code == 401