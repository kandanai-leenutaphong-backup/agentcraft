from __future__ import annotations

import re
from urllib.parse import quote

from .base import Adapter, AdapterResult, json_document
from ..contracts import (
    Caveat, ConfigurationError, ConnectorConfig, ContentValue, ErrorInfo, ItemResult,
    OperationCapability, RecordKey, Request, VerificationResult,
)
from ..execution import failure_item, json_bytes, record_body, verify_item
from ..transport import CallContext, OperationFault, check_response

SYSTEM_FIELDS = frozenset({"_rid", "_self", "_etag", "_attachments", "_ts"})


class CosmosAdapter(Adapter):
    service = "cosmos"
    partition_required = True
    caveats = (
        Caveat("addressed_partition", "Read and delete evidence applies only to the supplied ID and partition, not to the ID in other partitions."),
        Caveat("non_atomic_batch", "Items execute independently; no transactional batch is implemented."),
        Caveat("replace_only", "Merge updates and merge upserts are unsupported in this pass."),
        Caveat("local_continuation", "Continuation tokens are bound to this connector instance and do not survive recreation."),
    )

    def __init__(self, config: ConnectorConfig) -> None:
        super().__init__(config)
        coordinates = config.target.coordinates
        if (set(coordinates) != {"database", "container"}
                or any(value in {".", ".."} or not re.fullmatch(r"[^/\\?#\x00-\x20]{1,255}", value) for value in coordinates.values())):
            raise ConfigurationError("Cosmos requires valid database and container coordinates")
        if config.key_field != "id" or config.partition_key_field is None:
            raise ConfigurationError("Cosmos requires the id key and an explicit top-level partition field")
        self._path = f"/dbs/{quote(coordinates['database'], safe='')}/colls/{quote(coordinates['container'], safe='')}/docs"
        self.capabilities.update({
            "create": OperationCapability("supported", guarantees=("create_if_absent", "per_item_atomic"),
                                          verification=("none", "acknowledgment", "presence", "content"), reason=""),
            "read": OperationCapability("supported", verification=("none", "presence"), reason=""),
            "update": OperationCapability("conditional", modes=("replace",), guarantees=("conditional_version", "per_item_atomic"),
                                          verification=("none", "acknowledgment", "presence", "content"), reason="replace_only"),
            "upsert": OperationCapability("conditional", modes=("replace",), guarantees=("per_item_atomic",),
                                          verification=("none", "acknowledgment", "presence", "content"), reason="replace_only"),
            "delete": OperationCapability("supported", guarantees=("conditional_version", "per_item_atomic"),
                                          verification=("none", "acknowledgment", "absence"), reason=""),
            "query": OperationCapability("supported", dialects=("cosmos-sql",), options=("partition",), reason=""),
        })

    def validate(self, operation: str, request: Request, evidence: str) -> None:
        for item in getattr(request, "records", ()) or getattr(request, "keys", ()):
            key = item.key if hasattr(item, "key") else item
            if key.parts["id"] in {".", ".."} or not re.fullmatch(r"[^/\\?#\x00-\x1f]{1,1023}", key.parts["id"]):
                raise OperationFault("invalid", "invalid_cosmos_id")
            if operation in {"create", "upsert"} and item.expected_version is not None:
                raise OperationFault("unsupported", "precondition_unsupported")
            if hasattr(item, "content") and SYSTEM_FIELDS & set(item.content.data):
                raise OperationFault("invalid", "reserved_document_field")
        if "conditional_version" in request.requirements.guarantees:
            versions = request.expected_versions if operation == "delete" else tuple(item.expected_version for item in request.records)
            if not versions or not all(version is not None for version in versions):
                raise OperationFault("invalid", "expected_version_required")
        if operation == "query":
            if not re.match(r"\s*SELECT\s", request.expression, re.IGNORECASE):
                raise OperationFault("invalid", "cosmos_select_required")
            if not all(re.fullmatch(r"@[A-Za-z_][A-Za-z0-9_]*", name) for name in request.parameters):
                raise OperationFault("invalid", "invalid_parameter_name")
            partition = request.service_options.get(self.service, {}).get("partition")
            if partition is not None and type(partition) not in {str, int, float, bool}:
                raise OperationFault("invalid", "invalid_query_partition")

    def _key_path(self, key: RecordKey) -> str:
        return self._path + "/" + quote(key.parts["id"], safe="")

    @staticmethod
    def _headers(key: RecordKey, version: str | None = None) -> dict[str, str]:
        headers = {"x-ms-documentdb-partitionkey": json_bytes([key.partition]).decode()}
        if version is not None:
            headers["If-Match"] = version
        return headers

    async def _lookup(self, key: RecordKey, context: CallContext) -> dict:
        response = await context.call("GET", self._key_path(key), headers=self._headers(key))
        check_response(response)
        content = json_document(response.body)
        if content.get("id") != key.parts["id"] or json_bytes(content.get(self.config.partition_key_field)) != json_bytes(key.partition):
            raise OperationFault("unknown", "provider_key_mismatch")
        return content

    async def execute(self, operation: str, request: Request, context: CallContext,
                      evidence: str, cursor: str | None) -> AdapterResult:
        if operation == "query":
            return await self._query(request, context, cursor)
        if operation not in {"create", "read", "update", "upsert", "delete"}:
            return await super().execute(operation, request, context, evidence, cursor)
        inputs = request.keys if operation in {"read", "delete"} else request.records
        keys = list(request.keys) if operation in {"read", "delete"} else [record.key for record in request.records]
        items = []
        for index, key in enumerate(keys):
            try:
                if operation == "read":
                    content = await self._lookup(key, context)
                    version = content.get("_etag")
                    if request.projection:
                        content = {name: content[name] for name in request.projection if name in content}
                    report = VerificationResult(evidence, evidence, "satisfied", 1) if evidence == "presence" else VerificationResult()
                    items.append(ItemResult(index, key, "success", ContentValue(content), version=version, verification=report))
                    continue
                record = None if operation == "delete" else inputs[index]
                expected = None if record is None else record_body(record, "id", self.config.partition_key_field)
                version = (request.expected_versions[index] if request.expected_versions else None) if operation == "delete" else record.expected_version
                headers = self._headers(key, version)
                if operation == "upsert":
                    headers["x-ms-documentdb-is-upsert"] = "true"
                method = "DELETE" if operation == "delete" else "PUT" if operation == "update" else "POST"
                path = self._key_path(key) if operation in {"update", "delete"} else self._path
                response = await context.call(method, path, body=expected, headers=headers, mutation=True)
                check_response(response, mutation=True)
                if operation != "delete":
                    stored = json_document(response.body)
                    if stored.get("id") != key.parts["id"] or json_bytes(stored.get(self.config.partition_key_field)) != json_bytes(key.partition):
                        raise OperationFault("unknown", "provider_key_mismatch")
                    version = stored.get("_etag")
                report = VerificationResult(evidence, "acknowledgment", "satisfied" if evidence == "acknowledgment" else "not_requested")
                item = ItemResult(index, key, "success", version=version, verification=report, effect="accepted")
                if evidence not in {"none", "acknowledgment"}:
                    item = await verify_item(item, context, request.verification, evidence,
                                             lambda current=key: self._lookup(current, context),
                                             lambda content, desired=expected: json_bytes({name: value for name, value in content.items() if name not in SYSTEM_FIELDS}) == json_bytes(desired))
                items.append(item)
            except OperationFault as fault:
                if fault.status == "not_found" and operation in {"read", "delete"} and request.missing == "ok" and evidence != "presence":
                    report = VerificationResult(evidence, "absence", "satisfied", 1) if evidence == "absence" else VerificationResult()
                    items.append(ItemResult(index, key, "success", verification=report))
                else:
                    items.append(failure_item(index, key, fault, mutation=operation != "read"))
                if fault.status in {"unknown", "failed", "denied"}:
                    items.extend(ItemResult(remaining, key, "not_attempted") for remaining, key in enumerate(keys[index + 1:], index + 1))
                    break
        return AdapterResult(tuple(items))

    async def _query(self, request, context, cursor) -> AdapterResult:
        headers = {"x-ms-documentdb-isquery": "true", "Content-Type": "application/query+json",
                   "x-ms-max-item-count": str(context.limits.max_items)}
        partition = request.service_options.get(self.service, {}).get("partition")
        if partition is None:
            headers["x-ms-documentdb-query-enablecrosspartition"] = "true"
        else:
            headers["x-ms-documentdb-partitionkey"] = json_bytes([partition]).decode()
        if cursor is not None:
            headers["x-ms-continuation"] = cursor
        body = {"query": request.expression, "parameters": [{"name": name, "value": value} for name, value in request.parameters.items()]}
        response = await context.call("POST", self._path, body=body, headers=headers)
        check_response(response)
        documents = json_document(response.body).get("Documents")
        if (not isinstance(documents, list) or len(documents) > context.limits.max_items
                or not all(isinstance(document, dict) for document in documents)):
            raise OperationFault("failed", "invalid_query_response")
        items = []
        for index, document in enumerate(documents):
            key = RecordKey({"id": document["id"]}, document[self.config.partition_key_field]) if "id" in document and self.config.partition_key_field in document else None
            version = document.get("_etag")
            if request.projection:
                document = {name: document[name] for name in request.projection if name in document}
            items.append(ItemResult(index, key, "success", ContentValue(document), version=version))
        cursor = response.headers.get("x-ms-continuation") or None
        if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 12000):
            raise OperationFault("failed", "invalid_provider_continuation")
        return AdapterResult(tuple(items), cursor=cursor, truncated=cursor is not None)