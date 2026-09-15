"""A host-authorized, read-only ADX query and independent result comparison."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from azdata import ConnectorConfig, Limits, Policy, QueryRequest, ResourceAddress, connect


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def validate_observation(value, semantic):
    if (not isinstance(value, dict) or set(value) != {"columns", "rows", "truncated"}
            or not isinstance(value["columns"], list) or not isinstance(value["rows"], list)
            or type(value["truncated"]) is not bool
            or any(not isinstance(row, list) or len(row) != len(value["columns"]) for row in value["rows"])):
        raise ValueError("independent_expected_required")
    if semantic == "count":
        if (value["columns"] != ["Count"] or len(value["rows"]) != 1
                or type(value["rows"][0][0]) is not int or value["rows"][0][0] < 0 or value["truncated"]):
            raise ValueError("invalid_count")
    if semantic == "ordinal-schema":
        if value["columns"] != ["fields", "field_count"] or len(value["rows"]) != 1 or value["truncated"]:
            raise ValueError("invalid_ordinal_schema")
        fields, count = value["rows"][0]
        if (not isinstance(fields, list) or type(count) is not int or count != len(fields)
                or any(not isinstance(item, dict) or set(item) != {"name", "type"}
                       or any(not isinstance(child, str) or not child for child in item.values()) for item in fields)
                or len({item["name"] for item in fields}) != count):
            raise ValueError("invalid_ordinal_schema")


def validate_case(case, limits, *, require_oracle=True):
    if case.get("comparison", "ordered") not in {"ordered", "typed-multiset"}:
        raise ValueError("invalid_comparison")
    if case.get("semantic", "query") not in {"query", "count", "ordinal-schema", "preview"}:
        raise ValueError("invalid_semantic")
    if (type(limits.get("max_rows")) is not int or not 1 <= limits["max_rows"] <= 100
            or not 0 < limits.get("timeout_seconds", 0) <= 30
            or not 0 < limits.get("max_output_bytes", 0) <= 1_048_576):
        raise ValueError("invalid_read_limits")
    if require_oracle and case.get("expected_status") == "success":
        validate_observation(case.get("expected"), case.get("semantic", "query"))


def comparison_digest(value, comparison):
    compared = dict(value)
    if comparison == "typed-multiset":
        compared["rows"] = sorted(value["rows"], key=canonical)
    return hashlib.sha256(canonical(compared)).hexdigest()


def _native_scalar(value):
    if isinstance(value, datetime):
        return {"type": "datetime", "value": value.isoformat()}
    raise TypeError("unsupported native scalar type")


async def observe(case, *, target, limits, credential, before_call) -> dict:
    from azure.kusto.data import ClientRequestProperties, KustoConnectionStringBuilder
    from azure.kusto.data.aio import KustoClient

    validate_case(case, limits, require_oracle=False)
    remaining = min(before_call(), limits["timeout_seconds"], 30)
    started = time.monotonic()
    request_id = str(uuid.uuid4())

    async def token_provider():
        token = await asyncio.to_thread(credential.get_token, "https://kusto.kusto.windows.net/.default")
        return token.token

    builder = KustoConnectionStringBuilder.with_async_token_provider(target["endpoint"], token_provider)
    properties = ClientRequestProperties()
    properties.client_request_id = request_id
    properties.set_option("request_readonly", True)
    properties.set_option("request_remote_entities_disabled", True)
    properties.set_option("servertimeout", timedelta(seconds=min(remaining, limits["timeout_seconds"])))
    properties.set_option("truncationmaxrecords", limits["max_rows"])
    properties.set_option("truncationmaxsize", limits["max_output_bytes"])
    for name, value in case["parameters"].items():
        properties.set_parameter(name, value)
    async with asyncio.timeout(remaining):
        async with KustoClient(builder) as client:
            result = await client.execute_query(target["database"], case["expression"], properties)
    if result.get_exceptions() or len(result.primary_results) != 1:
        raise ValueError("native_result_incomplete")
    table = result.primary_results[0]
    observed = {"columns": [column.column_name for column in table.columns],
                "rows": [list(row) for row in table], "truncated": False}
    encoded = json.dumps(observed, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                         allow_nan=False, default=_native_scalar).encode()
    validate_observation(json.loads(encoded), case.get("semantic", "query"))
    if len(observed["rows"]) > limits["max_rows"] or len(encoded) > limits["max_output_bytes"]:
        raise ValueError("native_result_exceeds_bounds")
    return {"expected": json.loads(encoded), "attempts": 1, "request_id": request_id,
            "row_count": len(observed["rows"]), "observed_sha256": hashlib.sha256(encoded).hexdigest(),
            "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}


async def run(case, *, target, limits, credential, before_call, transport=None, observed_out=None) -> dict:
    validate_case(case, limits)
    remaining = min(before_call(), 30)
    bounds = Limits(timeout_seconds=min(remaining, limits["timeout_seconds"]),
                    max_items=limits["max_rows"], max_output_bytes=limits["max_output_bytes"],
                    max_attempts=1)
    config = ConnectorConfig(target["endpoint"], ResourceAddress({"database": target["database"]}),
                             (urlsplit(target["endpoint"]).hostname,))
    request = QueryRequest(dialect="kql", expression=case["expression"], parameters=case["parameters"])
    async with asyncio.timeout(remaining):
        async with connect("adx", config, credential=credential, transport=transport,
                           policy=Policy(target["principal_id"], grants={"query"}, limits=bounds,
                                         max_concurrency=1)) as client:
            result = await client.query(request)
    attempts = result.metrics.get("attempts")
    evidence = "live" if transport is None and type(attempts) is int and attempts > 0 else "offline"
    report = {"attempts": attempts, "request_id": request.request_id,
              "elapsed_ms": result.metrics.get("elapsed_ms", 0), "evidence_class": evidence}
    if result.status != case["expected_status"]:
        return {**report, "outcome": "FAIL", "error_code": "service_failed"}
    if result.status != "success":
        return {**report, "outcome": "PASS_REFUSAL"}
    if result.truncated or any(caveat.code == "output_bound" for caveat in result.caveats):
        return {**report, "outcome": "FAIL", "error_code": "incomplete_result"}
    payload = result.to_dict()
    tables = payload["metadata"].get("columns", [])
    if len(tables) != 1:
        return {**report, "outcome": "FAIL", "error_code": "oracle_mismatch"}
    columns = [column["name"] for column in tables[0]]
    rows = [[item["content"]["data"][column] for column in columns] for item in payload["items"]]
    observed = {"columns": columns, "rows": rows, "truncated": result.truncated}
    if observed_out is not None:
        observed_out.update(observed)
    try:
        validate_observation(observed, case.get("semantic", "query"))
    except ValueError:
        return {**report, "outcome": "FAIL", "error_code": "oracle_mismatch"}
    observed_digest = hashlib.sha256(canonical(observed)).hexdigest()
    report.update(row_count=len(rows), observed_sha256=observed_digest)
    comparison = case.get("comparison", "ordered")
    if comparison_digest(observed, comparison) != comparison_digest(case["expected"], comparison):
        return {**report, "outcome": "FAIL", "error_code": "oracle_mismatch"}
    return {**report, "outcome": "PASS_LIVE" if evidence == "live" else "PASS_OFFLINE"}