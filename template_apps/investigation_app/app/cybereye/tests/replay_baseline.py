"""Prepare native read plans and assemble their observations with fixed app synthesis."""

from __future__ import annotations

import argparse
import asyncio
import copy
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path

from template_foundations.situation_detector import configuration_digest

from app.cybereye.backend.agents.tools.base import evidence_query
from app.cybereye.backend.data.adx import ReadOnlyAdx
from app.cybereye.backend.data.azdata_client import QueryRows, bind_parameters
from app.cybereye.backend.investigation.detector.engine import DetectorEngine, validate_window
from app.cybereye.backend.models import ScanRequest


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def query_identity(query, parameters):
    prologue, values = bind_parameters(parameters)
    return {"expression": prologue + query, "parameters": values}


def query_case(identifier, query, parameters, max_rows):
    return {"case_id": identifier, **query_identity(f"{query.strip()}\n| take {max_rows + 1}", parameters),
            "expected_status": "success", "expected": None}


def rule_plan(template, configuration, window, max_rows):
    request = ScanRequest.model_validate(window)
    validate_window(request)
    if not 1 <= max_rows <= 99 or template["target"]["service"] != "adx":
        raise ValueError("bounded ADX plan required")
    engine = DetectorEngine(None, configuration)
    plan = copy.deepcopy(template)
    plan["run_id"] = template["run_id"][:55] + "-rules"
    plan["cases"] = [query_case("LI-ADX-RULE-" + rule.rule_id, rule.query,
        {"start": request.start, "end": request.end, "rule_threshold": rule.threshold}, max_rows)
        for rule in engine.rules]
    plan["limits"] = {"max_calls": len(plan["cases"]), "timeout_seconds": 30,
                      "max_rows": max_rows + 1, "max_output_bytes": 1048576}
    return plan


def native_value(value):
    if isinstance(value, dict) and set(value) == {"type", "value"} and value["type"] == "datetime":
        return datetime.fromisoformat(value["value"])
    if isinstance(value, list):
        return [native_value(item) for item in value]
    if isinstance(value, dict):
        return {key: native_value(item) for key, item in value.items()}
    return value


class ObservedQueries:
    def __init__(self, plan):
        self.observations = {}
        for case in plan["cases"]:
            key = digest({name: case[name] for name in ("expression", "parameters")})
            if key in self.observations or not isinstance(case["expected"], dict):
                raise ValueError("complete unique native observations required")
            self.observations[key] = case["expected"]

    def query(self, query, parameters=None, *, timeout_seconds=None):
        observed = self.observations.get(digest(query_identity(query, parameters or {})))
        if observed is None:
            raise ValueError("query absent from frozen native observations")
        return QueryRows(tuple(observed["columns"]), tuple(tuple(native_value(value) for value in row)
                         for row in observed["rows"]), "native-baseline", 0, observed["truncated"])


class ObservedAdx(ReadOnlyAdx):
    def __init__(self, plan, max_rows):
        self.connector = ObservedQueries(plan)
        self.maximum = max_rows

    def parameterized(self, query, params, max_rows=100):
        return super().parameterized(query, params, min(max_rows, self.maximum))


def replay_scan(observations, configuration, window, max_rows):
    expected = rule_plan(observations, configuration, window, max_rows)
    wanted = [{name: case[name] for name in ("case_id", "expression", "parameters")} for case in expected["cases"]]
    actual = [{name: case[name] for name in ("case_id", "expression", "parameters")} for case in observations["cases"]]
    if wanted != actual:
        raise ValueError("native rules do not match frozen configuration and window")
    engine = DetectorEngine(ObservedAdx(observations, max_rows), configuration)
    return asyncio.run(engine.scan(ScanRequest.model_validate(window)))


def evidence_plan(observations, configuration, window, max_rows):
    scan = replay_scan(observations, configuration, window, max_rows)
    if not 0 < len(scan.situations) <= 20:
        raise ValueError("M1 requires bounded nonempty situations")
    plan = copy.deepcopy(observations)
    plan["run_id"] = observations["run_id"][:50] + "-evidence"
    plan["cases"] = []
    for situation in scan.situations:
        identifiers = [identifier for pattern in situation.patterns for identifier in pattern.evidence_ids]
        if identifiers:
            query, parameters = evidence_query(identifiers)
            plan["cases"].append(query_case("LI-ADX-EVIDENCE-" + situation.situation_id,
                                           query, parameters, max_rows))
    plan["limits"]["max_calls"] = len(plan["cases"])
    return plan


def assemble(observations, evidence, configuration, window, max_rows):
    if evidence["target"] != observations["target"]:
        raise ValueError("native evidence target mismatch")
    scan = replay_scan(observations, configuration, window, max_rows)
    reader = ObservedAdx(evidence, max_rows)
    results = {}
    for situation in scan.situations:
        identifiers = [identifier for pattern in situation.patterns for identifier in pattern.evidence_ids]
        if identifiers:
            query, parameters = evidence_query(identifiers)
            result = reader.parameterized(query, parameters).model_dump(mode="json")
        else:
            result = {"columns": [], "rows": [], "row_count": 0}
        results[situation.situation_id] = {"situation_id": situation.situation_id, **result}
    return {"schema_version": 1, "configuration_digest": configuration_digest(configuration),
            "window": window, "scan": scan.model_dump(mode="json"), "evidence": results}


def write_private(path, value):
    path = path.resolve()
    if any((parent / ".git").exists() for parent in path.parents):
        raise ValueError("baseline payload must remain outside a checkout")
    encoded = json.dumps(value, indent=2, allow_nan=False).encode()
    if len(encoded) > 2097152:
        raise ValueError("private baseline exceeds byte bound")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(encoded)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("rules", "evidence", "assemble"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--configuration", type=Path, required=True)
    parser.add_argument("--evidence", type=Path)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--max-rows", type=int, default=99)
    parser.add_argument("--output", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        plan = json.loads(arguments.plan.read_text())
        source = json.loads(arguments.configuration.read_text())
        configuration = source["configuration"]
        if configuration_digest(configuration) != source["configuration_digest"]:
            raise ValueError("configuration digest mismatch")
        window = {"start": arguments.start, "end": arguments.end}
        if arguments.action == "rules":
            value = rule_plan(plan, configuration, window, arguments.max_rows)
        elif arguments.action == "evidence":
            value = evidence_plan(plan, configuration, window, arguments.max_rows)
        else:
            if arguments.evidence is None:
                raise ValueError("native evidence observations required")
            value = assemble(plan, json.loads(arguments.evidence.read_text()), configuration, window, arguments.max_rows)
        write_private(arguments.output, value)
        print(json.dumps({"action": arguments.action, "sha256": digest(value),
                          "output": str(arguments.output), "live_calls": 0}))
        return 0
    except (OSError, KeyError, TypeError, ValueError):
        print(json.dumps({"status": "BLOCKED", "error_code": "invalid_or_incomplete_native_baseline", "live_calls": 0}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())