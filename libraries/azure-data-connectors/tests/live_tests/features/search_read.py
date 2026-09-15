"""Host-authorized Search reads compared with independently frozen native results."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid
from types import SimpleNamespace
from urllib.parse import urlsplit

from azdata import ConnectorConfig, Limits, Policy, QueryRequest, ReadRequest, RecordKey, ResourceAddress, SchemaRequest, connect


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def schema_projection(document):
    def field_projection(field):
        projected = {name: field[name] for name in ("name", "type", "key", "searchable", "filterable",
                     "sortable", "facetable", "retrievable") if name in field}
        if field.get("fields"):
            projected["fields"] = [field_projection(child) for child in field["fields"]]
        return projected

    return {"name": document["name"], "fields": [field_projection(field) for field in document["fields"]],
            "@odata.etag": document.get("@odata.etag")}


def validate_case(case, limits, *, require_oracle=True):
    if case.get("operation") not in {"query", "read", "schema"}:
        raise ValueError("only_search_reads_implemented")
    if (type(limits.get("max_rows")) is not int or not 1 <= limits["max_rows"] <= 100
            or not 0 < limits.get("max_output_bytes", 0) <= 1_048_576):
        raise ValueError("invalid_read_limits")
    if require_oracle and case.get("expected_status") == "success":
        expected = case.get("expected")
        if (not isinstance(expected, dict) or set(expected) != {"documents", "metadata", "truncated"}
                or not isinstance(expected["documents"], list) or not isinstance(expected["metadata"], dict)
                or type(expected["truncated"]) is not bool):
            raise ValueError("independent_expected_required")
        if case.get("expected_sha256", digest(expected)) != digest(expected):
            raise ValueError("baseline_digest_mismatch")


def native_schema_projection(document):
    def fields(items):
        result = []
        for item in items:
            projected = {key: value for key, value in item.items() if key in
                         {"name", "type", "key", "searchable", "filterable", "sortable", "facetable", "retrievable"}}
            if item.get("fields"):
                projected["fields"] = fields(item["fields"])
            result.append(projected)
        return result

    return {"name": document["name"], "fields": fields(document["fields"]),
            "@odata.etag": document.get("@odata.etag")}


async def observe(case, *, target, limits, credential, before_call, transport=None):
    from azure.search.documents.aio import SearchClient
    from azure.search.documents.indexes.aio import SearchIndexClient
    from azure.core.exceptions import ResourceNotFoundError

    validate_case(case, limits, require_oracle=False)
    remaining = min(before_call(), limits.get("timeout_seconds", 30), 30)
    started = time.monotonic()
    request_id = str(uuid.uuid4())

    async def get_token(*scopes, **kwargs):
        return await asyncio.to_thread(credential.get_token, *scopes, **kwargs)

    borrowed = SimpleNamespace(get_token=get_token)
    client_options = {"api_version": "2024-07-01", "retry_total": 0, "retry_connect": 0,
                      "retry_read": 0, "retry_status": 0, "connection_timeout": remaining,
                      "read_timeout": remaining}
    if transport is not None:
        client_options["transport"] = transport
    headers = {"x-ms-client-request-id": request_id}
    metadata = {}
    continuation = None
    async with asyncio.timeout(remaining):
        if case["operation"] == "schema":
            async with SearchIndexClient(target["endpoint"], borrowed, **client_options) as client:
                model = await client.get_index(target["index"], headers=headers)
                documents = [native_schema_projection(model.serialize(keep_readonly=True))]
        else:
            async with SearchClient(target["endpoint"], target["index"], borrowed, **client_options) as client:
                if case["operation"] == "read":
                    try:
                        document = await client.get_document(case["expression"],
                            selected_fields=case["projection"] or None, headers=headers)
                        documents = [document]
                    except ResourceNotFoundError:
                        documents = []
                else:
                    options = case["options"]
                    native = {}
                    if "count" in options:
                        native["include_total_count"] = options["count"]
                    if "filter" in options:
                        native["filter"] = options["filter"]
                    if "orderby" in options:
                        native["order_by"] = options["orderby"].split(",")
                    def check_count(response):
                        if response.http_response.status_code == 200:
                            count = json.loads(response.http_response.body()).get("@odata.count")
                            if count is not None and (type(count) is not int or count < 0):
                                raise ValueError("native_count_missing_or_inconsistent")

                    results = await client.search(case["expression"], select=case["projection"] or None,
                        raw_response_hook=check_count,
                        top=limits["max_rows"], headers=headers, **native)
                    pages = results.by_page()
                    documents = [document async for document in await anext(pages)]
                    continuation = pages.continuation_token
                    documents = [{name: value for name, value in document.items()
                                  if not name.startswith("@search.") or value is not None} for document in documents]
                    for document in documents:
                        if "@search.captions" in document:
                            document["@search.captions"] = [caption.serialize(keep_readonly=True)
                                                           for caption in document["@search.captions"]]
                    if options.get("count"):
                        metadata["count"] = await pages.get_count()
                        if type(metadata["count"]) is not int or metadata["count"] < len(documents):
                            raise ValueError("native_count_missing_or_inconsistent")
    observed = {"documents": documents, "metadata": metadata, "truncated": continuation is not None}
    if len(documents) > limits["max_rows"] or len(json.dumps(observed).encode()) > limits["max_output_bytes"]:
        raise ValueError("native_result_exceeds_bounds")
    return {"expected": observed, "attempts": 1, "request_id": request_id, "row_count": len(documents),
            "observed_sha256": digest(observed), "elapsed_ms": round((time.monotonic() - started) * 1000, 3)}


def candidate_observation(result, operation):
    payload = result.to_dict()
    documents = [item["content"]["data"] for item in payload["items"] if item["content"] is not None]
    if operation == "schema":
        documents = [schema_projection(document) for document in documents]
    return {"documents": documents, "metadata": payload["metadata"], "truncated": result.truncated}


async def run(case, *, target, limits, credential, before_call, transport=None, observed_out=None):
    validate_case(case, limits)
    remaining = min(before_call(), 30)
    bounds = Limits(timeout_seconds=min(remaining, limits["timeout_seconds"]), max_items=limits["max_rows"],
                    max_output_bytes=limits["max_output_bytes"], max_attempts=1)
    config = ConnectorConfig(target["endpoint"], ResourceAddress({"index": target["index"]}),
                             (urlsplit(target["endpoint"]).hostname,), key_field=target["key_field"])
    operation = case["operation"]
    if operation == "query":
        request = QueryRequest(dialect="search", expression=case["expression"], projection=tuple(case["projection"]),
                               service_options={"search": case["options"]})
    elif operation == "read":
        request = ReadRequest(keys=(RecordKey({target["key_field"]: case["expression"]}),),
                              projection=tuple(case["projection"]), missing="ok")
    elif operation == "schema":
        request = SchemaRequest(action="read")
    else:
        raise ValueError("only_search_reads_implemented")
    async with asyncio.timeout(remaining):
        async with connect("search", config, credential=credential, transport=transport,
            policy=Policy(target["principal_id"], grants={"query", "read", "schema.read"},
                          limits=bounds, max_concurrency=1)) as client:
            result = await getattr(client, operation)(request)
    attempts = result.metrics.get("attempts")
    evidence = "live" if transport is None and type(attempts) is int and attempts > 0 else "offline"
    report = {"attempts": attempts, "request_id": request.request_id, "result_status": result.status,
              "elapsed_ms": result.metrics.get("elapsed_ms", 0), "evidence_class": evidence}
    if result.errors:
        report["result_error_code"] = result.errors[0].code
    if result.status != case["expected_status"]:
        return {**report, "outcome": "FAIL", "error_code": "service_failed"}
    if result.status != "success":
        return {**report, "outcome": "PASS_REFUSAL"}
    if (any(caveat.code == "output_bound" for caveat in result.caveats)
            or any(item.status != "success" or item.error for item in result.items)):
        return {**report, "outcome": "FAIL", "error_code": "incomplete_result"}
    observed = candidate_observation(result, operation)
    if observed_out is not None:
        observed_out.update(observed)
    report.update(row_count=len(observed["documents"]), observed_sha256=digest(observed))
    if digest(observed) != digest(case["expected"]):
        return {**report, "outcome": "FAIL", "error_code": "oracle_mismatch"}
    return {**report, "outcome": "PASS_LIVE" if evidence == "live" else "PASS_OFFLINE"}