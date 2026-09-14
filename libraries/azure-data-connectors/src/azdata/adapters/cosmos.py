from __future__ import annotations

import re
from azure.core import MatchConditions

from .base import Adapter, AdapterResult, json_document
from ..contracts import (
    Caveat, ConfigurationError, ConnectorConfig, ContentValue, ErrorInfo, ItemResult,
    OperationCapability, RecordKey, Request, VerificationResult,
)
from ..execution import failure_item, json_bytes, record_body, verify_item
from ..transport import OperationFault
from ..sdk import CallContext

SYSTEM_FIELDS = frozenset({"_rid", "_self", "_etag", "_attachments", "_ts"})


class CosmosAdapter(Adapter):
    service = "cosmos"
    scope = "https://cosmos.azure.com/.default"
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

    def create_client(self, session, kind):
        from azure.cosmos.aio import CosmosClient
        from azure.cosmos.documents import ConnectionPolicy

        options = session.client_options()
        policy = ConnectionPolicy()
        policy.ConnectionRetryConfiguration = options.pop("retry_policy")
        return CosmosClient(self.config.endpoint, session.credential, connection_policy=policy,
                            retry_total=0, retry_write=0, enable_endpoint_discovery=False, **options)

    async def prepare(self, session):
        await session.client("cosmos").__aenter__()

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

    def _container(self, context):
        client = context.session.client("cosmos")
        return client.get_database_client(self.config.target.coordinates["database"]).get_container_client(self.config.target.coordinates["container"])

    async def _lookup(self, key: RecordKey, context: CallContext) -> dict:
        content = await context.invoke(lambda: self._container(context).read_item(key.parts["id"], partition_key=key.partition))
        content = json_document(content)
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
                condition = {"etag": version, "match_condition": MatchConditions.IfNotModified} if version else {}
                async def mutate():
                    container = self._container(context)
                    if operation == "delete":
                        return await container.delete_item(key.parts["id"], partition_key=key.partition, retry_write=0, **condition)
                    if operation == "update":
                        return await container.replace_item(key.parts["id"], expected, retry_write=0, **condition)
                    method = container.create_item if operation == "create" else container.upsert_item
                    return await method(expected, retry_write=0)
                stored = await context.invoke(mutate, mutation=True)
                if operation != "delete":
                    stored = json_document(stored)
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
        partition = request.service_options.get(self.service, {}).get("partition")
        async def fetch_page():
            options = {"partition_key": partition} if partition is not None else {}
            results = self._container(context).query_items(request.expression,
                parameters=[{"name": name, "value": value} for name, value in request.parameters.items()],
                max_item_count=context.limits.max_items, **options)
            pages = results.by_page(continuation_token=cursor)
            try:
                page = await anext(pages)
            except StopAsyncIteration:
                return [], None
            return [document async for document in page], pages.continuation_token
        documents, cursor = await context.invoke(fetch_page)
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
        if cursor is not None and (not isinstance(cursor, str) or len(cursor) > 12000):
            raise OperationFault("failed", "invalid_provider_continuation")
        return AdapterResult(tuple(items), cursor=cursor, truncated=cursor is not None)