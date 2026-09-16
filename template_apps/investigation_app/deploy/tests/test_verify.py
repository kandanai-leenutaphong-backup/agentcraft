import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch
from types import SimpleNamespace
import asyncio

import httpx
import pytest

from deploy.verify import candidate_identity, compare_replay, load_baseline, main


@pytest.mark.parametrize("action", ["local", "verify", "replay-baseline"])
@pytest.mark.parametrize("missing", [False, True])
def test_entrypoint_uses_isolated_python_without_uv_fallback(action, missing, tmp_path):
    executable = str(tmp_path / "missing-python") if missing else shutil.which("false")
    assert executable
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["bash", str(root / "deploy/deploy.sh"), action, "--help"],
        env={**os.environ, "LIVE_PYTHON": executable, "UV_OFFLINE": "1", "UV_NO_SYNC": "1"},
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == (127 if missing else 1)


def test_native_browser_entrypoint_refuses_non_loopback_before_node(tmp_path):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["bash", str(root / "deploy/deploy.sh"), "browser-verify", "native-offline"],
        env={**os.environ, "CYBEREYE_URL": "https://fixture.invalid",
             "ARTIFACT_DIR": str(tmp_path / "artifacts")},
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 2
    assert "loopback HTTP origin" in result.stderr
    assert not (tmp_path / "artifacts").exists()


def test_native_browser_help_does_not_require_an_interpreter_or_create_artifacts(tmp_path):
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(
        ["bash", str(root / "deploy/deploy.sh"), "browser-verify", "native-offline", "--help"],
        env={**os.environ, "LIVE_PYTHON": str(tmp_path / "missing-python"),
             "CYBEREYE_URL": "http://127.0.0.1:9011", "ARTIFACT_DIR": str(tmp_path / "artifacts")},
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == 0, result.stderr
    for required in ("LIVE_PYTHON", "VIRTUAL_ENV", "pytest", "Playwright Chromium", "outside the checkout", "No automatic install or sync"):
        assert required in result.stdout
    assert not (tmp_path / "artifacts").exists()


@pytest.mark.parametrize("case", ["missing-python", "other-template", "checkout-artifacts", "unknown-argument"])
def test_native_browser_preflight_refuses_before_build_or_server(case, tmp_path):
    root = Path(__file__).resolve().parents[2]
    artifacts = tmp_path / "artifacts"
    environment = {**os.environ, "LIVE_PYTHON": sys.executable, "CYBEREYE_URL": "http://127.0.0.1:9011",
                   "ARTIFACT_DIR": str(artifacts), "UV_OFFLINE": "1", "UV_NO_SYNC": "1"}
    arguments = []
    if case == "missing-python":
        environment["LIVE_PYTHON"] = str(tmp_path / "missing-python")
        expected = "Native browser Python missing"
    elif case == "other-template":
        environment["LIVE_PYTHON"] = str(root.parent / "not-authorized" / "bin/python")
        expected = "another template's interpreter"
    elif case == "checkout-artifacts":
        environment["ARTIFACT_DIR"] = str(root / "app")
        expected = "artifacts must stay outside checkout"
    else:
        arguments = ["--not-an-offline-option"]
        expected = "unknown native browser arguments"
    result = subprocess.run(
        ["bash", str(root / "deploy/deploy.sh"), "browser-verify", "native-offline", *arguments],
        env=environment, capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode != 0
    assert expected in result.stderr
    assert not artifacts.exists()


def baseline_value():
    return {
        "schema_version": 1, "configuration_digest": "a" * 64,
        "window": {"start": "2026-08-13T02:30:00Z", "end": "2026-08-13T03:40:59Z"},
        "scan": {"historical_replay": True, "situations": [{"situation_id": "cyb_fixture", "first_seen": "2026-08-13T03:00:00Z"}],
                 "summary": {"situations": 1, "elapsed_ms": 10},
                 "rule_executions": [{"rule_id": "fixture", "hit_count": 1, "elapsed_ms": 5,
                                      "observation": {"groups_qualified": 1, "elapsed_ms": 5}}]},
        "evidence": {"cyb_fixture": {"columns": ["resource_id", "value"], "rows": [["row-1", 1]],
                                     "truncated": False, "row_count": 1, "elapsed_ms": 5, "client_request_id": "old"}},
    }


def test_comparison_ignores_only_named_execution_timing_and_request_identity():
    expected = baseline_value()
    scan, evidence = copy.deepcopy(expected["scan"]), copy.deepcopy(expected["evidence"])
    scan["summary"]["elapsed_ms"] = 900
    scan["rule_executions"][0]["elapsed_ms"] = 100
    scan["rule_executions"][0]["observation"]["elapsed_ms"] = 100
    evidence["cyb_fixture"].update(elapsed_ms=44, client_request_id="new")
    report = compare_replay(expected, scan, evidence)
    assert report["passed"]
    assert "rows" not in report
    assert expected["evidence"]["cyb_fixture"]["client_request_id"] == "old"
    for change in ("row", "schema", "time", "truncated", "observation", "missing"):
        changed_scan, changed_evidence = copy.deepcopy(scan), copy.deepcopy(evidence)
        if change == "row":
            changed_evidence["cyb_fixture"]["rows"][0][1] = True
        elif change == "schema":
            changed_evidence["cyb_fixture"]["columns"].reverse()
        elif change == "time":
            changed_scan["situations"][0]["first_seen"] = "2026-08-13T04:00:00Z"
        elif change == "truncated":
            changed_evidence["cyb_fixture"]["truncated"] = True
        elif change == "observation":
            changed_scan["rule_executions"][0]["observation"]["groups_qualified"] = 2
        else:
            changed_evidence.clear()
        assert not compare_replay(expected, changed_scan, changed_evidence)["passed"]


def test_baseline_requires_complete_bounded_evidence(tmp_path):
    path = tmp_path / "baseline.json"
    expected = baseline_value()
    path.write_text(json.dumps(expected))
    assert load_baseline(path) == expected
    expected["evidence"].clear()
    path.write_text(json.dumps(expected))
    import pytest
    with pytest.raises(ValueError):
        load_baseline(path)


def test_candidate_identity_comes_from_pinned_wheel_bytes(tmp_path):
    wheel = tmp_path / "candidate.whl"
    source = b"CONTRACT_VERSION = 1\n"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("azdata/__init__.py", source)
        archive.writestr("azdata-4.0.0a3.dist-info/METADATA", "Name: azdata\nVersion: 4.0.0a3\n")
    expected = candidate_identity(wheel, hashlib.sha256(wheel.read_bytes()).hexdigest())
    assert expected["distribution"] == "azdata"
    assert expected["version"] == "4.0.0a3"
    assert expected["source_sha256"] == hashlib.sha256(json.dumps(
        {"__init__.py": hashlib.sha256(source).hexdigest()}, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    import pytest
    with pytest.raises(ValueError):
        candidate_identity(wheel, "0" * 64)


@pytest.mark.parametrize("matching,wheel_install", [(True, True), (False, True), (True, False)])
def test_baseline_cli_requires_matching_native_backend_before_scan(tmp_path, matching, wheel_install):
    baseline = baseline_value()
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline))
    wheel = tmp_path / "candidate.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("azdata/__init__.py", b"CONTRACT_VERSION = 1\n")
        archive.writestr("azdata-4.0.0a3.dist-info/METADATA", "Name: azdata\nVersion: 4.0.0a3\n")
    wheel_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
    identity = {**candidate_identity(wheel, wheel_hash), "editable": False, "transport": "native", "wheel_install": wheel_install}
    if not matching:
        identity["source_sha256"] = "0" * 64
    scans = []

    def handle(request):
        path = request.url.path
        if path == "/healthz":
            return httpx.Response(200, json={"status": "ok"})
        if path == "/api/whoami":
            if request.headers.get("Origin") or request.headers["Host"] == "untrusted.example":
                return httpx.Response(401)
            return httpx.Response(200, json={"issuer": "local-preview"})
        if path == "/api/cyber/detector/configuration":
            return httpx.Response(200, json={"historical_replay": True, "configuration_digest": baseline["configuration_digest"]})
        if path == "/api/cyber/optimization":
            return httpx.Response(404)
        if path == "/api/inventory/tree":
            return httpx.Response(200, json={"children": []})
        if path == "/api/cyber/library-identity":
            return httpx.Response(200, json=identity)
        if path == "/api/cyber/scan":
            window = json.loads(request.content)
            if window["start"] == window["end"]:
                return httpx.Response(400)
            scans.append(window)
            return httpx.Response(200, json=baseline["scan"])
        if path == "/api/cyber/evidence/cyb_fixture":
            return httpx.Response(200, json=baseline["evidence"]["cyb_fixture"])
        raise AssertionError(path)

    output = tmp_path / "report.json"
    observed = tmp_path / "observed.json"
    client = httpx.Client(base_url="http://127.0.0.1:9011", transport=httpx.MockTransport(handle))
    with patch("deploy.verify.httpx.Client", return_value=client), patch("sys.argv", [
        "verify", "--scan", "--baseline", str(baseline_path), "--candidate-wheel", str(wheel),
        "--candidate-sha256", wheel_hash, "--output", str(output), "--observed-out", str(observed),
    ]):
        assert main() == (0 if matching and wheel_install else 1)
    assert len(scans) == (1 if matching and wheel_install else 0)
    report = json.loads(output.read_text())
    assert report["passed"] is (matching and wheel_install)
    assert "row-1" not in output.read_text()
    assert observed.exists() is (matching and wheel_install)
    if observed.exists():
        assert observed.stat().st_mode & 0o777 == 0o600
        assert json.loads(observed.read_text())["evidence"] == baseline["evidence"]


def test_observed_output_without_baseline_refuses_before_http(tmp_path):
    with patch("deploy.verify.httpx.Client") as client, patch("sys.argv", [
        "verify", "--observed-out", str(tmp_path / "observed.json"),
    ]), pytest.raises(SystemExit) as refusal:
        main()
    assert refusal.value.code == 2
    client.assert_not_called()


def test_read_context_binding_refuses_before_credentials_or_reservation():
    from deploy.verify import validate_read_context
    from unittest.mock import Mock

    expected, target = {"rows": []}, {"endpoint": "https://fixture.search.windows.net", "index": "fixture"}
    digest = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    context = {"candidate_sha256": "a" * 64, "target": target, "arguments": {},
               "baseline": {"candidate_sha256": "a" * 64, "target": target, "arguments": {},
                            "expected": expected, "expected_sha256": digest}, "preflight": Mock()}
    for changed in ({"target": {**target, "index": "other"}}, {"candidate_sha256": "b" * 64}, {"arguments": {"limit": 101}}):
        with pytest.raises(ValueError):
            validate_read_context({**context, **changed})
    context["preflight"].assert_not_called()
    validate_read_context(context)
    context["preflight"].assert_called_once()


def test_counter_delta_preserves_unknowns_and_refuses_missing_or_decreasing_metrics():
    from deploy.verify import read_attempt_delta

    def identity(known, unknown=0):
        return {"read_surfaces": {"knowledge": {"metrics": {"known_attempts": known, "unknown_attempt_operations": unknown}},
                                  "catalogue": {"search": {"metrics": {"known_attempts": 0, "unknown_attempt_operations": 0}},
                                                "adx": {"metrics": {"known_attempts": 0, "unknown_attempt_operations": 0}}}}}

    assert read_attempt_delta(identity(1), identity(4)) == {"known_attempts": 3, "unknown_attempt_operations": 0}
    assert read_attempt_delta(identity(1), identity(1, 1))["unknown_attempt_operations"] == 1
    with pytest.raises(ValueError):
        read_attempt_delta({}, identity(1))
    with pytest.raises(ValueError):
        read_attempt_delta(identity(4), identity(1))


def read_context(expected, operation, arguments, target, responses):
    from azdata import HttpResponse
    expected_sha256 = hashlib.sha256(json.dumps(expected, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"candidate_sha256": "a" * 64, "operation": operation, "target": target, "arguments": arguments,
        "baseline": {"candidate_sha256": "a" * 64, "operation": operation, "target": target, "arguments": arguments,
                     "expected": expected, "expected_sha256": expected_sha256},
        "credential": SimpleNamespace(get_token=lambda *args: SimpleNamespace(token="offline", expires_on=2**31)),
        "transport": SimpleNamespace(request=AsyncMock(side_effect=responses)),
        "preflight": Mock(), "reserve": Mock(return_value="reserved"), "reconcile": Mock()}


@pytest.mark.parametrize("operation", ["retrieve", "keyed", "status"])
@pytest.mark.asyncio
async def test_callable_knowledge_verifier_runs_actual_public_owner(operation):
    from deploy.verify import run_knowledge_read
    from azdata import HttpResponse

    target = {"endpoint": "https://unit.search.windows.net", "index": "fixture"}
    arguments = {"doc_kind": "analytic", "query": "", "terms": {}, "top": 1}
    expected = {"hits": [], "relaxed": [], "expression": "doc_kind eq 'analytic'"}
    responses = [HttpResponse(200, {"value": []})]
    maximum = 1
    if operation == "keyed":
        arguments, expected, responses = {"doc_kind": "analytic", "doc_id": "missing"}, {"document": None}, [HttpResponse(404)]
    if operation == "status":
        arguments = {}
        expected = {"available": False, **target, "retrieval": "azure-ai-search", "local_fallback": False,
                    "advisory_only": True, "documents": 0, "situation_types": 0, "analytics": 0}
        responses = [HttpResponse(200, {"value": [], "@odata.count": 0})] * 3
        maximum = 3
    context = read_context(expected, operation, arguments, target, responses)
    report = (await run_knowledge_read(context))
    assert report["outcome"] == "PASS_OFFLINE"
    assert report["metrics"]["known_attempts"] == maximum
    context["reserve"].assert_called_once_with(maximum)
    context["reconcile"].assert_called_once()
    assert context["transport"].request.call_count == maximum


@pytest.mark.asyncio
async def test_callable_catalogue_verifier_compares_to_independent_probe_envelope():
    from deploy.verify import run_catalogue_read
    from resource_explorer import InventoryService, ProbeReport, parse_selection, source_node
    from app.cybereye.backend.inventory import load_registry
    from test_data_inventory import LIVE_ENV, adx_response

    registry = load_registry(env=LIVE_ENV)
    source = registry.source("ait", "ait.adx.events")
    expected_probe = SimpleNamespace(metadata=AsyncMock(return_value=ProbeReport(
        status="ok", metrics={"row_count": 0, "column_count": 0}, total_rows=0)))
    expected_service = InventoryService(registry, {"adx": expected_probe})
    node = source_node("ait", "ait.adx.events")
    envelope = (await expected_service.resource(node, parse_selection("all", allowed=registry.source_ids())))
    expected = envelope.model_dump(by_alias=True)
    expected.pop("observedAt")
    target = {"source_id": source.source_id, "use_case_id": source.use_case_id, "coordinates": dict(source.binding.coordinates)}
    context = read_context(expected, "resource", {"selection": "all"}, target, [
        adx_response([[0]], [("Count", "long")]),
        adx_response([[[], 0]], [("fields", "dynamic"), ("field_count", "long")])])
    context["registry"] = registry
    report = (await run_catalogue_read(context))
    assert report["outcome"] == "PASS_OFFLINE"
    assert report["metrics"]["known_attempts"] == 2
    context["reserve"].assert_called_once_with(2)
    context["reconcile"].assert_called_once()