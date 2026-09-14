from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from azure.core import MatchConditions

from .base import AdapterResult, RecordAdapter
from ..contracts import Caveat, ConfigurationError, ContentValue, ItemResult, OperationCapability, RecordKey, plain
from ..transport import OperationFault


class TableAdapter(RecordAdapter):
    service = "tables"
    scope = "https://storage.azure.com/.default"
    content_kinds = ("json", "entity")
    caveats = (Caveat("partitioned_identity", "Entity identity is PartitionKey plus RowKey; cross-partition atomic batches are not supplied."),)

    def __init__(self, config):
        super().__init__(config)
        if (set(config.target.coordinates) != {"table"} or not re.fullmatch(r"[A-Za-z][A-Za-z0-9]{2,62}", config.target.coordinates["table"])
                or config.partition_key_field is not None):
            raise ConfigurationError("Table Storage requires one table coordinate; keys carry PartitionKey and RowKey")
        self.key_fields = ("PartitionKey", "RowKey")
        if config.key_fields is not None and config.key_fields != self.key_fields:
            raise ConfigurationError("Table keys must be PartitionKey and RowKey")
        for operation in ("create", "read", "update", "upsert", "delete"):
            evidence = ("none", "presence") if operation == "read" else ("none", "acknowledgment", "absence") if operation == "delete" else ("none", "acknowledgment", "presence", "content")
            self.capabilities[operation] = OperationCapability("supported", modes=("merge", "replace") if operation in {"update", "upsert"} else (),
                guarantees=("create_if_absent",) if operation == "create" else ("conditional_version",) if operation in {"update", "delete"} else (), verification=evidence, reason="")
        self.capabilities["query"] = OperationCapability("supported", dialects=("odata",), reason="")

    def create_client(self, session, kind):
        from azure.data.tables.aio import TableClient

        return TableClient(self.config.endpoint, self.config.target.coordinates["table"], credential=session.credential,
                           audience=(self.config.scope or self.scope).removesuffix("/.default"), **session.client_options())

    def validate(self, operation, request, evidence):
        for entry in getattr(request, "records", ()) or getattr(request, "keys", ()):
            key = entry.key if hasattr(entry, "key") else entry
            if any(re.search(r"[/\\#?\x00-\x1f\x7f-\x9f]", value) for value in key.parts.values()):
                raise OperationFault("invalid", "invalid_entity_key")
            if operation in {"create", "upsert"} and entry.expected_version is not None:
                raise OperationFault("unsupported", "precondition_unsupported")
            if hasattr(entry, "content"):
                values = entry.content.data
                if any(name in {"Timestamp", "odata.etag"} or name.startswith("@") for name in values):
                    raise OperationFault("invalid", "reserved_entity_property")
                if any(value is None or not isinstance(value, (str, bool, int, float, bytes, datetime, UUID)) for value in values.values()):
                    raise OperationFault("unsupported", "entity_property_type_unsupported")
        if "conditional_version" in request.requirements.guarantees:
            versions = request.expected_versions if operation == "delete" else tuple(record.expected_version for record in request.records)
            if not versions or not all(versions):
                raise OperationFault("invalid", "expected_version_required")

    @staticmethod
    def _content(entity):
        return ContentValue(dict(entity), kind="entity"), entity.metadata.get("etag")

    async def read_record(self, key, context):
        entity = await context.invoke(lambda: context.session.client("table").get_entity(key.parts["PartitionKey"], key.parts["RowKey"]))
        if any(entity.get(name) != value for name, value in key.parts.items()):
            raise OperationFault("unknown", "provider_key_mismatch")
        return self._content(entity)

    async def write_record(self, operation, key, record, version, request, context):
        async def write():
            from azure.data.tables import UpdateMode

            client = context.session.client("table")
            condition = {"etag": version, "match_condition": MatchConditions.IfNotModified} if version else {}
            if operation == "delete":
                await client.delete_entity(key.parts["PartitionKey"], key.parts["RowKey"], **condition)
                return None
            entity = {**plain(record.content.data), **plain(key.parts)}
            if operation == "create":
                response = await client.create_entity(entity)
            else:
                method = client.update_entity if operation == "update" else client.upsert_entity
                response = await method(entity, mode=UpdateMode.MERGE if request.mode == "merge" else UpdateMode.REPLACE, **condition)
            return response.get("etag")
        return await context.invoke(write, mutation=True)

    async def execute(self, operation, request, context, evidence, cursor):
        if operation != "query":
            return await super().execute(operation, request, context, evidence, cursor)
        async def page():
            pages = context.session.client("table").query_entities(request.expression, parameters=plain(request.parameters),
                select=list(request.projection) or None, results_per_page=context.limits.max_items).by_page(
                    continuation_token=json.loads(cursor) if cursor else None)
            try:
                current = await anext(pages)
            except StopAsyncIteration:
                return [], None
            return [entity async for entity in current], pages.continuation_token
        entities, token = await context.invoke(page)
        if len(entities) > context.limits.max_items:
            raise OperationFault("failed", "query_bound_ignored")
        items = []
        for index, entity in enumerate(entities):
            content, version = self._content(entity)
            key = RecordKey({name: entity[name] for name in self.key_fields}) if all(name in entity for name in self.key_fields) else None
            items.append(ItemResult(index, key, "success", content, version=version))
        return AdapterResult(tuple(items), cursor=json.dumps(token) if token else None, truncated=bool(token))