from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import replace
from azure.core import MatchConditions

from .base import Adapter, AdapterResult, json_document
from ..contracts import (
    Caveat, ConfigurationError, ConnectorConfig, ContentValue, ErrorInfo, ItemResult,
    OperationCapability, RecordKey, Request, VerificationResult, plain,
)
from ..execution import confirmation_digest, failure_item, json_bytes, matches_projection, record_body, verify_item
from ..transport import OperationFault
from ..sdk import CallContext

SEARCH_OPTIONS = ("filter", "orderby", "queryType", "semanticConfiguration", "vectorQueries", "searchFields",
                  "searchMode", "queryLanguage", "captions", "answers", "facets", "count")


class SearchAdapter(Adapter):
    service = "search"
    scope = "https://search.azure.com/.default"
    caveats = (
        Caveat("eventual_indexing", "Acknowledgment does not prove immediate search visibility."),
        Caveat("non_atomic_batch", "Document batches are not transactions; item outcomes are retained."),
        Caveat("native_merge", "Merge replaces supplied field values, including arrays; it is not recursive JSON merge."),
        Caveat("local_continuation", "Continuation tokens are bound to this connector instance and do not survive recreation."),
    )

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        if self.key_fields != (config.key_field,):
            raise ConfigurationError("Search supports one configured key field")
        coordinates = config.target.coordinates
        if set(coordinates) != {"index"} or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", coordinates["index"]) or len(coordinates["index"]) > 128:
            raise ConfigurationError("Search requires one valid index coordinate")
        if config.partition_key_field is not None:
            raise ConfigurationError("Search does not take a partition field")
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

    def create_client(self, session, kind):
        from azure.search.documents.aio import SearchClient
        from azure.search.documents.indexes.aio import SearchIndexClient

        options = session.client_options()
        options.update(api_version=self.config.api_version, audience=(self.config.scope or self.scope).removesuffix("/.default"))
        if kind == "documents":
            return SearchClient(self.config.endpoint, self.config.target.coordinates["index"], session.credential, **options)
        return SearchIndexClient(self.config.endpoint, session.credential, **options)

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
        selected = list(dict.fromkeys((*projection, self.config.key_field))) if projection else None
        content = await context.invoke(lambda: context.session.client("documents").get_document(key.parts[self.config.key_field], selected_fields=selected))
        content = json_document(content)
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
        method = "delete_documents" if operation == "delete" else "merge_documents" if operation == "update" else "upload_documents" if request.mode == "replace" else "merge_or_upload_documents"
        items = []
        for start in range(0, len(inputs), 1000):
            chunk_keys = keys[start:start + 1000]
            documents = [{self.config.key_field: key.parts[self.config.key_field]} for key in chunk_keys] if operation == "delete" else [record_body(record, self.config.key_field) for record in inputs[start:start + 1000]]
            try:
                native = await context.invoke(lambda: getattr(context.session.client("documents"), method)(documents), mutation=True)
                payload = [{"key": entry.key, "status": entry.succeeded, "statusCode": entry.status_code} for entry in native]
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
        names = {"orderby": "order_by", "queryType": "query_type", "semanticConfiguration": "semantic_configuration_name",
                 "vectorQueries": "vector_queries", "searchFields": "search_fields", "searchMode": "search_mode",
                 "queryLanguage": "query_language", "captions": "query_caption", "answers": "query_answer", "count": "include_total_count"}
        options = {names.get(name, name): plain(value) for name, value in request.service_options.get(self.service, {}).items()}
        for name in ("order_by", "search_fields"):
            if name in options:
                options[name] = options[name].split(",")
        async def fetch_page():
            client = context.session.client("documents")
            from azure.search.documents.models import VectorQuery

            if "vector_queries" in options:
                options["vector_queries"] = [VectorQuery.deserialize(value) for value in options["vector_queries"]]
            results = await client.search(request.expression, select=list(request.projection) or None,
                                          top=min(context.limits.max_items, 1000), **options)
            pages = results.by_page(continuation_token=cursor)
            documents = [document async for document in await anext(pages)]
            continuation = pages.continuation_token
            if isinstance(continuation, bytes):
                continuation = continuation.decode("ascii")
            documents = [{name: value for name, value in document.items() if not name.startswith("@search.") or value is not None} for document in documents]
            for document in documents:
                if "@search.captions" in document:
                    document["@search.captions"] = [caption.serialize(keep_readonly=True) for caption in document["@search.captions"]]
            metadata = {}
            for option, name, getter in (("include_total_count", "count", pages.get_count), ("facets", "facets", pages.get_facets),
                                         ("query_answer", "answers", pages.get_answers)):
                if options.get(option):
                    value = await getter()
                    metadata[name] = [item.serialize(keep_readonly=True) for item in value] if name == "answers" and value else value
            return documents, continuation, metadata
        documents, next_cursor, metadata = await context.invoke(fetch_page)
        if len(documents) > context.limits.max_items:
            raise OperationFault("failed", "query_bound_ignored")
        items = tuple(ItemResult(index, RecordKey({self.config.key_field: document[self.config.key_field]}) if self.config.key_field in document else None,
                                 "success", ContentValue(json_document(document))) for index, document in enumerate(documents))
        return AdapterResult(items, cursor=next_cursor, truncated=next_cursor is not None, metadata=metadata,
                             caveats=(Caveat("non_snapshot_paging", "Native Search continuation does not guarantee snapshot consistency."),))

    async def _schema(self, request, context) -> AdapterResult:
        context.session.client("indexes")
        from azure.search.documents.indexes.models import SearchIndex

        index_key = RecordKey({"index": self.config.target.coordinates["index"]})
        name = self.config.target.coordinates["index"]
        async def read_index():
            model = await context.invoke(lambda: context.session.client("indexes").get_index(name))
            return model.serialize(keep_readonly=True)
        if request.action in {"read", "list"}:
            try:
                content = await read_index()
            except OperationFault as fault:
                if fault.status == "not_found" and request.action == "list":
                    return AdapterResult()
                raise
            return AdapterResult((ItemResult(0, index_key, "success", ContentValue(content), version=content.get("@odata.etag")),))
        definition = plain(request.definition)
        if request.action == "update":
            current = await read_index()
            current_version = current.get("@odata.etag")
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
        model = SearchIndex.deserialize(definition) if definition else SearchIndex(name=name, fields=[])
        model.e_tag = request.expected_version
        if request.action == "delete":
            await context.invoke(lambda: context.session.client("indexes").delete_index(model, match_condition=MatchConditions.IfNotModified), mutation=True)
        else:
            condition = MatchConditions.IfMissing if request.action == "create" else MatchConditions.IfNotModified
            await context.invoke(lambda: context.session.client("indexes").create_or_update_index(model, match_condition=condition), mutation=True, allow_empty=True)
        item = ItemResult(0, index_key, "success", effect="accepted")
        try:
            content = await read_index()
            matched = request.action != "delete" and matches_projection(content, definition)
            report = VerificationResult("schema", "schema" if matched else "acknowledgment", "satisfied" if matched else "pending", 1)
            return AdapterResult((replace(item, status="success" if matched else "pending", content=ContentValue(content) if content else None,
                                          verification=report, version=(content or {}).get("@odata.etag")),))
        except OperationFault as fault:
            if request.action == "delete" and fault.status == "not_found":
                return AdapterResult((replace(item, verification=VerificationResult("schema", "schema", "satisfied", 1)),))
            return AdapterResult((replace(item, status="unknown", verification=VerificationResult("schema", "acknowledgment", "unknown", 1)),))