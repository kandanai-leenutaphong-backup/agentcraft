from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

from ..contracts import Caveat, ConnectorConfig, ContentValue, ItemResult, OPERATIONS, OperationCapability, Request, VerificationResult, plain, serialized
from ..execution import content_bytes, failure_item, json_bytes, matches_projection, verify_item
from ..transport import OperationFault
from ..sdk import CallContext


@dataclass(frozen=True)
class AdapterResult:
    items: tuple[ItemResult, ...] = ()
    cursor: str | None = None
    truncated: bool = False
    caveats: tuple[Caveat, ...] = ()
    metadata: Mapping[str, Any] | None = None


class Adapter:
    service: str
    caveats: tuple[Caveat, ...] = ()
    partition_required = False
    content_kinds = ("json",)
    scalar_keys = False
    schemes = ("https",)
    scope = ""

    def __init__(self, config: ConnectorConfig) -> None:
        from urllib.parse import urlsplit
        from ..contracts import ConfigurationError

        if urlsplit(config.endpoint).scheme not in self.schemes:
            raise ConfigurationError("endpoint protocol does not match the service adapter")
        self.config = config
        self.key_fields = config.key_fields or (config.key_field,)
        self.capabilities = {operation: OperationCapability() for operation in OPERATIONS}

    def validate(self, operation: str, request: Request, evidence: str) -> None:
        return None

    def create_client(self, session, kind):
        raise OperationFault("unsupported", "client_not_implemented")

    async def prepare(self, session):
        return None

    async def execute(self, operation: str, request: Request, context: CallContext,
                      evidence: str, cursor: str | None) -> AdapterResult:
        raise OperationFault("unsupported", "not_implemented")


def json_document(value: Any) -> dict:
    if not isinstance(value, dict):
        raise OperationFault("unknown", "invalid_provider_document")
    try:
        json_bytes(value)
    except OperationFault:
        raise OperationFault("unknown", "invalid_provider_document") from None
    return value


class RecordAdapter(Adapter):
    async def read_record(self, key, context):
        raise OperationFault("unsupported", "read_unsupported")

    async def write_record(self, operation, key, record, version, request, context):
        raise OperationFault("unsupported", "write_unsupported")

    def expected_content(self, record):
        if record.content.kind == "bytes":
            return record.content
        return ContentValue({**plain(record.content.data), **plain(record.key.parts)}, kind=record.content.kind)

    async def execute(self, operation, request, context, evidence, cursor):
        if operation not in {"create", "read", "update", "upsert", "delete"}:
            return await super().execute(operation, request, context, evidence, cursor)
        inputs = request.keys if operation in {"read", "delete"} else request.records
        items = []
        for index, entry in enumerate(inputs):
            record = None if operation in {"read", "delete"} else entry
            key = entry if record is None else record.key
            try:
                if operation == "read":
                    content, version = await self.read_record(key, context)
                    if request.projection:
                        content = ContentValue({name: content.data[name] for name in request.projection if name in content.data}, kind=content.kind)
                    report = VerificationResult(evidence, evidence, "satisfied", 1) if evidence == "presence" else VerificationResult()
                    items.append(ItemResult(index, key, "success", content, version=version, verification=report))
                    continue
                version = (request.expected_versions[index] if request.expected_versions else None) if operation == "delete" else record.expected_version
                version = await self.write_record(operation, key, record, version, request, context)
                item = ItemResult(index, key, "success", version=version, effect="accepted",
                                  verification=VerificationResult(evidence, "acknowledgment", "satisfied" if evidence == "acknowledgment" else "not_requested"))
                if evidence not in {"none", "acknowledgment"}:
                    async def lookup(current=key):
                        return (await self.read_record(current, context))[0]
                    expected = self.expected_content(record) if record else None
                    merge = getattr(request, "mode", None) == "merge"
                    compare = lambda content, desired=expected: (matches_projection(serialized(content.data), serialized(desired.data))
                        if merge else content_bytes(content) == content_bytes(desired))
                    item = await verify_item(item, context, request.verification, evidence, lookup, compare)
                items.append(item)
            except OperationFault as fault:
                if fault.status == "not_found" and operation in {"read", "delete"} and request.missing == "ok" and evidence != "presence":
                    report = VerificationResult(evidence, "absence", "satisfied", 1) if evidence == "absence" else VerificationResult()
                    items.append(ItemResult(index, key, "success", verification=report))
                else:
                    items.append(failure_item(index, key, fault, mutation=operation != "read"))
                if operation != "read" and fault.status in {"unknown", "failed", "denied"}:
                    items.extend(ItemResult(offset, tail if operation == "delete" else tail.key, "not_attempted")
                                 for offset, tail in enumerate(inputs[index + 1:], index + 1))
                    break
        return AdapterResult(tuple(items))