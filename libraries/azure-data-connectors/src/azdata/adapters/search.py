from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from urllib.parse import quote, urlencode

from .base import Adapter, AdapterResult, json_document
from ..contracts import (
    Caveat, ConfigurationError, ConnectorConfig, ContentValue, ErrorInfo, ItemResult,
    OperationCapability, RecordKey, Request, VerificationResult, plain,
)
from ..execution import confirmation_digest, failure_item, json_bytes, matches_projection, record_body, verify_item
from ..transport import CallContext, OperationFault, check_response

SEARCH_OPTIONS = ("filter", "orderby", "queryType", "semanticConfiguration", "vectorQueries", "searchFields",
                  "searchMode", "queryLanguage", "captions", "answers", "facets", "count")


class SearchAdapter(Adapter):
    service = "search"
    caveats = (
        Caveat("eventual_indexing", "Acknowledgment does not prove immediate search visibility."),
        Caveat("non_atomic_batch", "Document batches are not transactions; item outcomes are retained."),
        Caveat("native_merge", "Merge replaces supplied field values, including arrays; it is not recursive JSON merge."),
        Caveat("local_continuation", "Continuation tokens are bound to this connector instance and do not survive recreation."),
    )

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        coordinates = config.target.coordinates
        if set(coordinates) != {"index"} or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", coordinates["index"]) or len(coordinates["index"]) > 128:
            raise ConfigurationError("Search requires one valid index coordinate")
        if config.partition_key_field is not None:
            raise ConfigurationError("Search does not take a partition field")
        self._path = f"/indexes/{coordinates['index']}"
        self.capabilities.update({
            "create": OperationCapability(reason="atomic_create_unavailable"),
            "read": OperationCapability("supported", verification=("none", "presence"), reason=""),
            "update": OperationCapability("conditional", modes=("merge",),
                                          verification=("none", "acknowledgment", "presence", "content"), reason="merge_only"),
            "upsert": OperationCapability("supported", modes=("merge", "replace"),
                                          verification=("none", "acknowledgment", "presence", "content"), reason=""),
            "delete": OperationCapability("conditional", verification=("none", "acknowledgment", "absence"), reason="missing_ok_required"),
            "query": OperationCapability("supported", dialects=("search",), options=SEARCH_OPTIONS, reason=""),
            "schema": OperationCapability("conditional", actions=("list", "read", "create", "update", "delete"),
                                          verification=("none", "schema"), reason="additive_update_and_versioned_delete"),
        })

    def _url(self, suffix: str = "", **parameters) -> str:
        return self._path + suffix + "?" + urlencode({"api-version": self.config.api_version, **parameters})

    def validate(self, operation: str, request: Request, evidence: str) -> None:
        for item in getattr(request, "records", ()) or getattr(request, "keys", ()):
            key = item.key if hasattr(item, "key") else item
            if not re.fullmatch(r"[A-Za-z0-9_=-]{1,1024}", key.parts[self.config.key_field]):
                raise OperationFault("invalid", "invalid_search_key")
            if getattr(item, "expected_version", None) is not None:
                raise OperationFault("unsupported", "document_versions_unavailable")
            if hasattr(item, "content") and any(name.startswith("@") for name in item.content.data):
                raise OperationFault("invalid", "reserved_document_field")
        if operation == "delete":
            if request.missing != "ok":
                raise OperationFault("unsupported", "delete_missing_error_unavailable")
            if any(request.expected_versions):
                raise OperationFault("unsupported", "document_versions_unavailable")
        if operation == "query":
            if request.parameters:
                raise OperationFault("unsupported", "search_parameters_unavailable")
            self._validate_query_options(request.service_options.get(self.service, {}))
        if evidence == "content":
            readable = self.config.retrievable_fields
            if readable is None:
                raise OperationFault("unsupported", "retrievable_fields_not_declared")
            for record in request.records:
                body = record_body(record, self.config.key_field)
                if not set(body) <= set(readable) or any(value is None or isinstance(value, Mapping) for value in body.values()):
                    raise OperationFault("unsupported", "content_comparison_unavailable")
        if operation == "schema":
            if request.action in {"update", "delete"}:
                if not isinstance(request.expected_version, str) or not request.expected_version or request.expected_version == "*" or any(char in request.expected_version for char in "\r\n"):
                    raise OperationFault("invalid", "schema_version_required")
            if request.action in {"create", "update"}:
                self._validate_definition(request.definition)
            elif request.definition is not None:
                raise OperationFault("invalid", "unexpected_schema_definition")
            if request.action == "delete":
                expected = confirmation_digest(self.service, self.config, request)
                if request.confirmation != expected:
                    raise OperationFault("denied", "destructive_confirmation_required")

    @staticmethod
    def _validate_query_options(options: Mapping) -> None:
        for name in ("filter", "orderby", "semanticConfiguration", "searchFields", "queryLanguage", "captions", "answers"):
            if name in options and not isinstance(options[name], str):
                raise OperationFault("invalid", "invalid_search_option")
        if "queryType" in options and options["queryType"] not in ("simple", "full", "semantic"):
            raise OperationFault("invalid", "invalid_search_option")
        if "searchMode" in options and options["searchMode"] not in ("any", "all"):
            raise OperationFault("invalid", "invalid_search_option")
        if "count" in options and type(options["count"]) is not bool:
            raise OperationFault("invalid", "invalid_search_option")
        if "facets" in options and (not isinstance(options["facets"], tuple) or not all(isinstance(value, str) for value in options["facets"])):
            raise OperationFault("invalid", "invalid_search_option")
        if "facets" in options or options.get("count") or "captions" in options or "answers" in options:
            raise OperationFault("unsupported", "query_metadata_not_exposed")
        if "vectorQueries" in options:
            vectors = options["vectorQueries"]
            if not isinstance(vectors, tuple) or not 1 <= len(vectors) <= 10:
                raise OperationFault("invalid", "invalid_vector_queries")
            for vector in vectors:
                if (not isinstance(vector, Mapping) or set(vector) - {"kind", "vector", "fields", "k", "exhaustive", "weight"}
                        or vector.get("kind") != "vector" or not isinstance(vector.get("fields"), str)
                        or not vector["fields"] or not isinstance(vector.get("vector"), tuple) or not vector["vector"]
                        or not all(type(value) in (int, float) for value in vector["vector"])
                        or type(vector.get("k", 1)) is not int or not 1 <= vector.get("k", 1) <= 1000):
                    raise OperationFault("invalid", "invalid_vector_query")
                if ("exhaustive" in vector and type(vector["exhaustive"]) is not bool
                        or "weight" in vector and (type(vector["weight"]) not in (int, float) or vector["weight"] <= 0)):
                    raise OperationFault("invalid", "invalid_vector_query")

    def _validate_definition(self, definition) -> None:
        if (not isinstance(definition, Mapping) or set(definition) - {"name", "fields", "vectorSearch", "semantic", "suggesters", "scoringProfiles", "defaultScoringProfile", "corsOptions"}
                or definition.get("name") != self.config.target.coordinates["index"]):
            raise OperationFault("invalid", "invalid_index_definition")
        fields = definition.get("fields")
        if not isinstance(fields, tuple) or not fields:
            raise OperationFault("invalid", "index_fields_required")
        names = set()
        keys = []
        for item in fields:
            if (not isinstance(item, Mapping) or not isinstance(item.get("name"), str)
                    or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", item["name"]) or item["name"] in names
                    or not isinstance(item.get("type"), str)):
                raise OperationFault("invalid", "invalid_index_field")
            names.add(item["name"])
            if item.get("key"):
                keys.append(item)
        if len(keys) != 1 or keys[0]["name"] != self.config.key_field or keys[0]["type"] != "Edm.String":
            raise OperationFault("invalid", "invalid_index_key")

    async def execute(self, operation: str, request: Request, context: CallContext,
                      evidence: str, cursor: str | None) -> AdapterResult:
        if operation == "read":
            return await self._read(request, context, evidence)
        if operation in {"update", "upsert", "delete"}:
            return await self._write(operation, request, context, evidence)
        if operation == "query":
            return await self._query(request, context, cursor)
        if operation == "schema":
            return await self._schema(request, context)
        return await super().execute(operation, request, context, evidence, cursor)

    async def _lookup(self, key: RecordKey, context: CallContext, projection: tuple[str, ...] = ()):
        parameters = {"$select": ",".join(dict.fromkeys((*projection, self.config.key_field)))} if projection else {}
        response = await context.call("GET", self._url(f"/docs/{quote(key.parts[self.config.key_field], safe='')}", **parameters))
        check_response(response)
        content = json_document(response.body)
        if content.get(self.config.key_field) != key.parts[self.config.key_field]:
            raise OperationFault("unknown", "provider_key_mismatch")
        return content

    async def _read(self, request, context, evidence) -> AdapterResult:
        items = []
        for index, key in enumerate(request.keys):
            try:
                content = await self._lookup(key, context, request.projection)
                if request.projection:
                    content = {name: content[name] for name in request.projection if name in content}
                report = VerificationResult("presence", "presence", "satisfied", 1) if evidence == "presence" else VerificationResult()
                items.append(ItemResult(index, key, "success", ContentValue(content), verification=report))
            except OperationFault as fault:
                if fault.status == "not_found" and request.missing == "ok" and evidence != "presence":
                    items.append(ItemResult(index, key, "success"))
                else:
                    items.append(failure_item(index, key, fault))
        return AdapterResult(tuple(items))

    async def _write(self, operation, request, context, evidence) -> AdapterResult:
        inputs = request.keys if operation == "delete" else request.records
        keys = list(request.keys) if operation == "delete" else [record.key for record in request.records]
        action = "delete" if operation == "delete" else "merge" if operation == "update" else "upload" if request.mode == "replace" else "mergeOrUpload"
        items = []
        for start in range(0, len(inputs), 1000):
            chunk_keys = keys[start:start + 1000]
            documents = [{self.config.key_field: key.parts[self.config.key_field]} for key in chunk_keys] if operation == "delete" else [record_body(record, self.config.key_field) for record in inputs[start:start + 1000]]
            body = {"value": [{**document, "@search.action": action} for document in documents]}
            try:
                response = await context.call("POST", self._url("/docs/index"), body=body, mutation=True)
                check_response(response, mutation=True)
                payload = json_document(response.body).get("value")
                expected = [key.parts[self.config.key_field] for key in chunk_keys]
                if not isinstance(payload, list):
                    raise OperationFault("unknown", "acknowledgment_mismatch")
                by_key = {}
                ambiguous = set()
                unexpected = False
                for entry in payload:
                    if (not isinstance(entry, dict) or not isinstance(entry.get("key"), str)
                            or entry["key"] not in expected or type(entry.get("status")) is not bool):
                        unexpected = True
                        continue
                    if entry["key"] in by_key:
                        ambiguous.add(entry["key"])
                    by_key[entry["key"]] = entry
                for offset, key in enumerate(chunk_keys):
                    identifier = key.parts[self.config.key_field]
                    entry = by_key.get(identifier)
                    if entry is None or identifier in ambiguous or unexpected:
                        uncertain = failure_item(start + offset, key, OperationFault("unknown", "acknowledgment_mismatch"), mutation=True)
                        if entry is not None and entry["status"]:
                            uncertain = replace(uncertain, effect="accepted")
                        items.append(uncertain)
                        continue
                    if entry["status"]:
                        report = VerificationResult(evidence, "acknowledgment", "satisfied" if evidence == "acknowledgment" else "not_requested")
                        item = ItemResult(start + offset, key, "success", verification=report, effect="accepted")
                        if evidence not in {"none", "acknowledgment"}:
                            expected_content = documents[offset] if evidence == "content" else None
                            item = await verify_item(item, context, request.verification, evidence,
                                                     lambda current=key, expected=expected_content: self._lookup(current, context, tuple(expected) if expected else ()),
                                                     lambda content, expected=expected_content: matches_projection(content, expected))
                        items.append(item)
                    else:
                        status_code = entry.get("statusCode")
                        status = {404: "not_found", 409: "conflict", 412: "conflict", 400: "invalid", 401: "denied", 403: "denied"}.get(status_code, "failed")
                        items.append(failure_item(start + offset, key, OperationFault(status, "document_refused")))
            except OperationFault as fault:
                items.extend(failure_item(start + offset, key, fault, mutation=True) for offset, key in enumerate(chunk_keys))
                items.extend(ItemResult(index, key, "not_attempted") for index, key in enumerate(keys[start + len(chunk_keys):], start + len(chunk_keys)))
                break
        return AdapterResult(tuple(items))

    async def _query(self, request, context, cursor) -> AdapterResult:
        skip = int(cursor) if cursor else 0
        if skip < 0 or skip > 100000:
            raise OperationFault("invalid", "invalid_search_continuation")
        top = min(context.limits.max_items, 1000)
        body = {**plain(request.service_options.get(self.service, {})), "search": request.expression, "top": top, "skip": skip}
        if request.projection:
            body["select"] = ",".join(request.projection)
        response = await context.call("POST", self._url("/docs/search"), body=body)
        check_response(response)
        documents = json_document(response.body).get("value")
        if not isinstance(documents, list) or not all(isinstance(document, dict) for document in documents):
            raise OperationFault("failed", "invalid_query_response")
        if len(documents) > top:
            raise OperationFault("failed", "query_bound_ignored")
        items = tuple(ItemResult(index, RecordKey({self.config.key_field: document[self.config.key_field]}) if self.config.key_field in document else None,
                                 "success", ContentValue(document)) for index, document in enumerate(documents))
        next_cursor = str(skip + top) if len(documents) == top and skip + top <= 100000 else None
        return AdapterResult(items, cursor=next_cursor, truncated=bool(next_cursor),
                             caveats=(Caveat("non_snapshot_paging", "Search pages do not provide snapshot consistency; an extra empty page may terminate the scan."),))

    async def _schema(self, request, context) -> AdapterResult:
        index_key = RecordKey({"index": self.config.target.coordinates["index"]})
        if request.action in {"read", "list"}:
            response = await context.call("GET", self._url())
            if response.status == 404 and request.action == "list":
                return AdapterResult()
            check_response(response)
            content = json_document(response.body)
            return AdapterResult((ItemResult(0, index_key, "success", ContentValue(content), version=content.get("@odata.etag") or response.headers.get("etag")),))
        definition = plain(request.definition)
        if request.action == "update":
            previous = await context.call("GET", self._url())
            check_response(previous)
            current = json_document(previous.body)
            current_version = current.get("@odata.etag") or previous.headers.get("etag")
            if current_version != request.expected_version:
                raise OperationFault("conflict", "version_conflict")
            fields = {item["name"]: item for item in definition["fields"]}
            for old in current.get("fields", []):
                new = fields.get(old.get("name"))
                if new is None or any(new.get(name) != value for name, value in old.items()):
                    raise OperationFault("unsupported", "destructive_schema_change")
            for name, value in current.items():
                if name not in {"fields", "@odata.etag"} and definition.get(name) != value:
                    raise OperationFault("unsupported", "schema_change_requires_migration")
        headers = {"If-None-Match": "*"} if request.action == "create" else {"If-Match": request.expected_version}
        response = await context.call("DELETE" if request.action == "delete" else "PUT", self._url(),
                                      body=None if request.action == "delete" else definition, headers=headers, mutation=True)
        check_response(response, mutation=True)
        item = ItemResult(0, index_key, "success", effect="accepted")
        try:
            observed = await context.call("GET", self._url())
            if request.action == "delete":
                matched = observed.status == 404
                if not matched:
                    check_response(observed)
                content = None
            else:
                check_response(observed)
                content = json_document(observed.body)
                matched = matches_projection(content, definition)
            report = VerificationResult("schema", "schema" if matched else "acknowledgment", "satisfied" if matched else "pending", 1)
            return AdapterResult((replace(item, status="success" if matched else "pending", content=ContentValue(content) if content else None,
                                          verification=report, version=(content or {}).get("@odata.etag")),))
        except OperationFault:
            return AdapterResult((replace(item, status="unknown", verification=VerificationResult("schema", "acknowledgment", "unknown", 1)),))