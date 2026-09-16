"""Read back the local template; --scan additionally queries the existing ADX replay."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import zipfile
from datetime import datetime, timezone
from email.parser import Parser
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


def candidate_identity(wheel: Path, expected_sha256: str) -> dict:
    if wheel.stat().st_size > 20971520 or hashlib.sha256(wheel.read_bytes()).hexdigest() != expected_sha256:
        raise ValueError("candidate wheel digest mismatch")
    with zipfile.ZipFile(wheel) as archive:
        metadata = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
        if len(metadata) != 1:
            raise ValueError("candidate wheel metadata is invalid")
        headers = Parser().parsestr(archive.read(metadata[0]).decode("utf-8"))
        if headers.get("Name") != "azdata" or not headers.get("Version"):
            raise ValueError("candidate must be the azdata distribution")
        sources = {name.removeprefix("azdata/"): hashlib.sha256(archive.read(name)).hexdigest()
                   for name in archive.namelist() if name.startswith("azdata/") and name.endswith(".py")}
        if "__init__.py" not in sources:
            raise ValueError("candidate runtime is absent")
    return {"distribution": "azdata", "version": headers["Version"], "source_sha256": _digest(sources)}


def load_baseline(path: Path) -> dict:
    if path.stat().st_size > 2097152:
        raise ValueError("baseline exceeds byte bound")
    value = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(value, dict)
            or set(value) != {"schema_version", "configuration_digest", "window", "scan", "evidence"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or not isinstance(value["configuration_digest"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", value["configuration_digest"])
            or not isinstance(value["window"], dict) or set(value["window"]) != {"start", "end"}
            or not isinstance(value["scan"], dict) or value["scan"].get("historical_replay") is not True
            or not isinstance(value["scan"].get("situations"), list) or not isinstance(value["evidence"], dict)):
        raise ValueError("baseline fields are invalid")
    start, end = (datetime.fromisoformat(value["window"][field].replace("Z", "+00:00")) for field in ("start", "end"))
    if start.utcoffset() is None or end.utcoffset() is None or not 0 < (end - start).total_seconds() <= 48 * 3600:
        raise ValueError("baseline window is invalid")
    identifiers = [situation["situation_id"] for situation in value["scan"]["situations"]]
    if (len(identifiers) > 20 or len(set(identifiers)) != len(identifiers)
            or any(not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", identifier) for identifier in identifiers)
            or set(value["evidence"]) != set(identifiers)
            or any(not isinstance(item, dict) for item in value["evidence"].values())):
        raise ValueError("baseline requires complete bounded situation evidence")
    _digest(value)
    return value


def compare_replay(baseline: dict, scan: dict, evidence: dict) -> dict:
    def project(scan_value, evidence_value):
        projected_scan = copy.deepcopy(scan_value)
        projected_scan.get("summary", {}).pop("elapsed_ms", None)
        for execution in projected_scan.get("rule_executions", []):
            execution.pop("elapsed_ms", None)
            execution.get("observation", {}).pop("elapsed_ms", None)
        projected_evidence = copy.deepcopy(evidence_value)
        for result in projected_evidence.values():
            result.pop("elapsed_ms", None)
            result.pop("client_request_id", None)
        return {"scan": projected_scan, "evidence": projected_evidence}

    expected = _digest(project(baseline["scan"], baseline["evidence"]))
    observed = _digest(project(scan, evidence))
    return {"passed": expected == observed, "expected_sha256": expected, "observed_sha256": observed}


def validate_read_context(context: dict) -> None:
    baseline = context.get("baseline")
    if (not isinstance(baseline, dict) or not isinstance(baseline.get("expected"), dict)
            or baseline.get("target") != context.get("target")
            or baseline.get("candidate_sha256") != context.get("candidate_sha256")
            or not re.fullmatch(r"[a-f0-9]{64}", context.get("candidate_sha256", ""))
            or baseline.get("arguments") != context.get("arguments")
            or baseline.get("operation") != context.get("operation")
            or baseline.get("expected_sha256") != _digest(baseline["expected"])):
        raise ValueError("consumer_baseline_mismatch")
    context["preflight"]()


def read_attempt_delta(before: dict, after: dict) -> dict:
    def totals(identity):
        try:
            surfaces = identity["read_surfaces"]
            metrics = [surfaces["knowledge"]["metrics"], surfaces["catalogue"]["adx"]["metrics"],
                       surfaces["catalogue"]["search"]["metrics"]]
            result = {"known_attempts": 0, "unknown_attempt_operations": 0}
            for counter in metrics:
                for name in result:
                    value = counter[name]
                    if type(value) is not int or value < 0:
                        raise ValueError("invalid_read_metrics")
                    result[name] += value
            return result
        except (KeyError, TypeError):
            raise ValueError("read_metrics_required") from None

    initial, final = totals(before), totals(after)
    result = {name: final[name] - initial[name] for name in initial}
    if any(value < 0 for value in result.values()):
        raise ValueError("read_metrics_reset")
    return result


def _read_report(context, observed, metrics):
    passed = (_digest(observed) == context["baseline"]["expected_sha256"]
              and metrics.get("unknown_attempt_operations") == 0)
    offline = context.get("transport") is not None
    if not offline and not (type(metrics.get("known_attempts")) is int and metrics["known_attempts"] > 0):
        passed = False
    return {"outcome": ("PASS_OFFLINE" if offline else "PASS_LIVE") if passed else "FAIL",
            "observed_sha256": _digest(observed), "expected_sha256": context["baseline"]["expected_sha256"],
            "candidate_sha256": context["candidate_sha256"], "consumer": "investigation", "metrics": metrics}


def run_knowledge_read(context: dict) -> dict:
    from azdata import ConnectorConfig, Limits, Policy, ResourceAddress
    from app.cybereye.backend.knowledge import search

    operation, arguments = context["operation"], context["arguments"]
    if operation not in {"retrieve", "status", "keyed"}:
        raise ValueError("unsupported_knowledge_read")
    maximum = 3 if operation == "status" else 1
    if operation == "retrieve":
        top = arguments.get("top")
        if type(top) is not int or not 1 <= top <= 100:
            raise ValueError("invalid_read_limit")
        maximum += sum(any(str(value).strip() for value in values) for values in arguments.get("terms", {}).values())
        if maximum > 4:
            raise ValueError("knowledge_reservation_exceeded")
    validate_read_context(context)
    target = context["target"]
    config = ConnectorConfig(target["endpoint"], ResourceAddress({"index": target["index"]}),
                             (urlsplit(target["endpoint"]).hostname or "",))
    reservation = context["reserve"](maximum)
    handle = None
    try:
        handle = search.configure(config, credential=context["credential"], transport=context.get("transport"),
            policy=Policy("investigation-read-verifier", grants={"query", "read"}, max_concurrency=1,
                          limits=Limits(timeout_seconds=30, max_items=100, max_output_bytes=1_048_576, max_attempts=1)))
        if operation == "retrieve":
            hits, relaxed, expression = search.retrieve(**arguments)
            observed = {"hits": hits, "relaxed": relaxed, "expression": expression}
        elif operation == "keyed":
            observed = {"document": search.get_by_doc_id(**arguments)}
        else:
            observed = search.status()
        return _read_report(context, observed, handle.describe()["metrics"])
    finally:
        try:
            context["reconcile"](reservation, handle.describe()["metrics"] if handle is not None else None)
        finally:
            if handle is not None:
                handle.close()


async def run_catalogue_read(context: dict) -> dict:
    from resource_explorer import parse_selection, source_node
    from app.cybereye.backend.inventory import build_service
    from resource_explorer.probes import AdxProbe, SearchProbe

    registry, target, arguments = context["registry"], context["target"], context["arguments"]
    source = registry.source(target["use_case_id"], target["source_id"])
    if (source is None or source.binding.connector not in {"adx", "search"}
            or dict(source.binding.coordinates) != target["coordinates"]):
        raise ValueError("catalogue_target_mismatch")
    selection = parse_selection(arguments.get("selection"), allowed=registry.source_ids())
    if not selection.enabled(source.source_id):
        raise ValueError("source_disabled")
    operation = context["operation"]
    limit = arguments.get("limit", 25)
    if operation not in {"resource", "content"} or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("invalid_catalogue_read")
    validate_read_context(context)
    maximum = 2 if operation == "resource" else 3
    reservation = context["reserve"](maximum)
    probe_type = AdxProbe if source.binding.connector == "adx" else SearchProbe
    probe = probe_type(credential_provider=lambda: context["credential"], transport=context.get("transport"))
    try:
        service = build_service(registry, probes={source.binding.connector: probe})
        node = source_node(source.use_case_id, source.source_id)
        result = (await service.resource(node, selection) if operation == "resource"
                  else await service.content(node, selection, limit=limit))
        observed = result.model_dump(by_alias=True)
        observed.pop("observedAt", None)
        return _read_report(context, observed, probe.describe()["metrics"])
    finally:
        try:
            context["reconcile"](reservation, probe.describe()["metrics"])
        finally:
            await probe.aclose()


def verify_data_reads(client, check) -> None:
    def read(path, **params):
        response = client.get(path, params=params)
        response.raise_for_status()
        return response.json()

    try:
        status = read("/api/cyber/graph/status")
        available = status.get("available") is True
        check("graph_available", available, vertices=status.get("vertices"), edges=status.get("edges"))
        if not available:
            return
        check("graph_loaded_counts", (status.get("vertices"), status.get("edges")) == (1308, 2429))
        overview = read("/api/cyber/graph/overview")
        seeds = overview.get("seeds", [])
        check("graph_overview", len(seeds) >= 2)
        if len(seeds) < 2:
            return
        core = read("/api/cyber/graph/core", start="2026-08-13T02:30:00Z", end="2026-08-13T03:40:00Z")
        check("graph_core", bool(core.get("nodes")) and bool(core.get("edges")),
              nodes=len(core.get("nodes", [])), edges=len(core.get("edges", [])))
        seed = seeds[0]
        neighbours = read("/api/cyber/graph/node", id=seed["id"], depth=2)
        check("graph_two_hop", neighbours.get("focus") == seed["id"] and bool(neighbours.get("nodes")))
        selection = read("/api/cyber/graph/selection", id=[item["id"] for item in seeds[:2]], depth=2, scope="shared")
        check("graph_selection", len(selection.get("selected", [])) == 2)
        check("graph_search", bool(read("/api/cyber/graph/search", q=seed["name"], limit=5)))
        missing = client.get("/api/cyber/graph/node", params={"id": "migration-verifier-absent-node"})
        check("graph_missing_refused", missing.status_code == 404)
        root = read("/api/cyber/inventory/tree")
        use_case = next(item for item in root["children"] if item["useCaseId"] == "open_source_cybersecurity")
        sources = read("/api/cyber/inventory/tree", node=use_case["id"])
        source = next(item for item in sources["children"] if item["sourceId"] == "cyberkb.search.mitre_attack")
        preview = read("/api/cyber/inventory/content", node=source["id"], limit=25)
        rows = preview.get("rows") or []
        check("mitre_preview", preview.get("status") == "ok" and bool(rows), rows=len(rows))
        if rows:
            record = rows[0]
            document = read("/api/cyber/knowledge/type/" + quote(record["doc_id"], safe=""))
            check("mitre_keyed_readback", all(document.get(name) == record.get(name)
                                             for name in ("doc_id", "title", "path", "commit", "license")))
        missing = client.get("/api/cyber/knowledge/type/migration-verifier-absent-document")
        check("mitre_missing_refused", missing.status_code == 404)
        disabled = client.get("/api/cyber/inventory/content", params={"node": source["id"], "limit": 25},
                              headers={"X-Inventory-Selection": "none"})
        check("mitre_selection_refused", disabled.status_code == 409 and disabled.json().get("error") == "source_disabled")
    except (httpx.HTTPError, ValueError, KeyError, TypeError, StopIteration) as error:
        check("data_read_failure", False, error_type=type(error).__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://127.0.0.1:9011")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--data", action="store_true", help="Verify existing Perth graph and MITRE reads; no inference or data writes.")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate-wheel", type=Path)
    parser.add_argument("--candidate-sha256")
    parser.add_argument("--observed-out", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/verification/api.json"))
    arguments = parser.parse_args()
    if arguments.data and arguments.baseline is not None:
        parser.error("data workflow checks use their own scope, not frozen ADX artifact acceptance")
    origin = urlsplit(arguments.api)
    if (origin.scheme != "http" or origin.hostname not in {"127.0.0.1", "localhost"}
            or origin.username or origin.password or origin.path not in {"", "/"}
            or origin.query or origin.fragment):
        parser.error("verification requires a plain loopback HTTP origin")
    baseline = None
    candidate = None
    if arguments.baseline is not None:
        if not arguments.scan or arguments.candidate_wheel is None or not arguments.candidate_sha256:
            parser.error("baseline verification requires --scan, --candidate-wheel and --candidate-sha256")
        if arguments.output.exists():
            parser.error("baseline verification requires a new output path; prior evidence is never overwritten")
        try:
            baseline = load_baseline(arguments.baseline)
            candidate = candidate_identity(arguments.candidate_wheel, arguments.candidate_sha256)
        except (OSError, ValueError, TypeError, KeyError, AttributeError, zipfile.BadZipFile):
            parser.error("baseline or candidate artifact is invalid")
    elif arguments.candidate_wheel is not None or arguments.candidate_sha256:
        parser.error("candidate options require --baseline")
    if arguments.observed_out is not None:
        private = arguments.observed_out
        if (baseline is None or not private.is_absolute() or private.exists()
                or any((parent / ".git").exists() for parent in private.resolve().parents)):
            parser.error("observed output requires a baseline and a new private path outside a checkout")
    checks = []

    def check(name, passed, **detail):
        checks.append({"name": name, "passed": bool(passed), **detail})

    with httpx.Client(base_url=arguments.api.rstrip("/"), timeout=90, trust_env=False) as client:
        response = client.get("/healthz")
        check("liveness", response.status_code == 200 and response.json() == {"status": "ok"})
        response = client.get("/api/whoami")
        check("local_identity", response.status_code == 200 and response.json().get("issuer") == "local-preview")
        for name, headers in (("foreign_origin", {"Origin": "https://untrusted.example"}),
                              ("foreign_host", {"Host": "untrusted.example"})):
            response = client.get("/api/whoami", headers=headers)
            check(name, response.status_code == 401 and not response.content)
        configuration_response = client.get("/api/cyber/detector/configuration")
        configuration = configuration_response.json()
        configured = configuration_response.status_code == 200
        configured = configured and configuration.get("historical_replay") is True
        configured = configured and len(configuration.get("configuration_digest", "")) == 64
        check("detector_readback", configured)
        if baseline is not None:
            check("frozen_configuration", configuration.get("configuration_digest") == baseline["configuration_digest"])
            identity_response = client.get("/api/cyber/library-identity")
            identity = identity_response.json()
            matches = identity_response.status_code == 200 and identity.get("editable") is False
            matches = matches and identity.get("wheel_install") is True
            matches = matches and identity.get("transport") == "native"
            matches = matches and all(identity.get(key) == expected for key, expected in candidate.items())
            check("candidate_runtime", matches, candidate_sha256=arguments.candidate_sha256)
        response = client.get("/api/cyber/optimization")
        check("optimizer_removed", response.status_code == 404)
        response = client.get("/api/cyber/inventory/tree")
        check("guide_not_composed", response.status_code == 200 and not any(
            node.get("useCaseId") == "guide" for node in response.json().get("children", [])))
        window = baseline["window"] if baseline is not None else {"start": "2026-08-13T02:30:00Z", "end": "2026-08-13T03:40:59Z"}
        response = client.post("/api/cyber/scan", json={**window, "end": window["start"]})
        check("invalid_window_refused", response.status_code == 400)
        ready = baseline is None or all(item["passed"] for item in checks)
        if arguments.scan and ready:
            response = client.post("/api/cyber/scan", json=window)
            body = response.json()
            check("live_adx_scan", response.status_code == 200, status_code=response.status_code,
                  summary=body.get("summary"))
            situations = body.get("situations", [])
            if baseline is not None and response.status_code == 200:
                observed_evidence = {}
                for identifier in baseline["evidence"]:
                    response = client.get(f"/api/cyber/evidence/{identifier}", params=window)
                    check("frozen_evidence_readback", response.status_code == 200)
                    if response.status_code == 200:
                        observed_evidence[identifier] = response.json()
                if arguments.observed_out is not None:
                    encoded = json.dumps({"scan": body, "evidence": observed_evidence}, allow_nan=False).encode()
                    check("private_observation_bound", len(encoded) <= 2097152)
                    if len(encoded) <= 2097152:
                        arguments.observed_out.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                        descriptor = os.open(arguments.observed_out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                        with os.fdopen(descriptor, "wb") as destination:
                            destination.write(encoded)
                comparison = compare_replay(baseline, body, observed_evidence)
                check("frozen_replay_parity", comparison["passed"], expected_sha256=comparison["expected_sha256"],
                      observed_sha256=comparison["observed_sha256"])
            elif response.status_code == 200:
                check("replay_situations_present", bool(situations), count=len(situations))
            if situations and baseline is None:
                response = client.get(f"/api/cyber/evidence/{situations[0]['situation_id']}", params=window)
                evidence = response.json()
                check("evidence_readback", response.status_code == 200 and evidence.get("row_count", 0) > 0,
                      status_code=response.status_code, row_count=evidence.get("row_count"))
        if arguments.data and all(item["passed"] for item in checks):
            verify_data_reads(client, check)
        report = {"observed_at": datetime.now(timezone.utc).isoformat(), "api": arguments.api,
              "live_adx_requested": arguments.scan, "model_calls": False,
              "live_data_requested": arguments.data,
              "baseline_sha256": _digest(baseline) if baseline is not None else None,
              "checks": checks, "passed": all(item["passed"] for item in checks)}
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    with arguments.output.open("x" if baseline is not None else "w", encoding="utf-8") as destination:
        destination.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())