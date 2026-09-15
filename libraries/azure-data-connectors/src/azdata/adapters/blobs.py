from __future__ import annotations

import re

from azure.core import MatchConditions

from .base import AdapterResult, RecordAdapter
from ..contracts import Caveat, ConfigurationError, ContentValue, ItemResult, OperationCapability, RecordKey
from ..transport import OperationFault


class BlobAdapter(RecordAdapter):
    service = "blobs"
    scope = "https://storage.azure.com/.default"
    content_kinds = ("bytes",)
    empty_query = True
    caveats = (Caveat("block_blobs_only", "Only bounded block blobs are supported; snapshots, leases and historical versions are not deleted implicitly."),)

    def __init__(self, config):
        super().__init__(config)
        if self.key_fields != (config.key_field,):
            raise ConfigurationError("Blob Storage supports one configured name key")
        if (set(config.target.coordinates) != {"container"} or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", config.target.coordinates["container"])
                or not 3 <= len(config.target.coordinates["container"]) <= 63 or config.partition_key_field is not None):
            raise ConfigurationError("Blob Storage requires one valid container and no partition field")
        for operation in ("create", "update", "upsert", "delete", "read"):
            evidence = ("none", "presence") if operation == "read" else ("none", "acknowledgment", "absence") if operation == "delete" else ("none", "acknowledgment", "presence", "content")
            self.capabilities[operation] = OperationCapability("supported", modes=("replace",) if operation in {"update", "upsert"} else (),
                guarantees=("create_if_absent",) if operation == "create" else ("conditional_version",) if operation in {"update", "delete"} else (), verification=evidence, reason="")
        self.capabilities["query"] = OperationCapability("supported", dialects=("blob-prefix",), reason="")

    def create_client(self, session, kind):
        from azure.storage.blob.aio import ContainerClient

        return ContainerClient(self.config.endpoint, self.config.target.coordinates["container"], credential=session.credential,
                               **session.client_options())

    def _blob(self, key, context):
        return context.session.client("container").get_blob_client(key.parts[self.config.key_field])

    def validate(self, operation, request, evidence):
        if request.service_options:
            raise OperationFault("invalid", "blob_options_unsupported")
        if getattr(request, "projection", ()):
            raise OperationFault("unsupported", "blob_projection_unsupported")
        for entry in getattr(request, "records", ()) or getattr(request, "keys", ()):
            key = entry.key if hasattr(entry, "key") else entry
            if any(part in {".", ".."} for part in key.parts[self.config.key_field].split("/")):
                raise OperationFault("invalid", "invalid_blob_name")
            if hasattr(entry, "content") and len(entry.content.data) > 4 * 1024 * 1024:
                raise OperationFault("unsupported", "single_put_limit")
            if operation in {"create", "upsert"} and entry.expected_version is not None:
                raise OperationFault("unsupported", "precondition_unsupported")
        if "conditional_version" in request.requirements.guarantees:
            versions = request.expected_versions if operation == "delete" else tuple(record.expected_version for record in request.records)
            if not versions or not all(versions):
                raise OperationFault("invalid", "expected_version_required")
        if operation == "query" and request.parameters:
            raise OperationFault("unsupported", "blob_query_parameters_unsupported")

    async def read_record(self, key, context):
        async def read():
            blob = self._blob(key, context)
            properties = await blob.get_blob_properties()
            if type(properties.size) is not int or properties.size < 0:
                raise OperationFault("unknown", "invalid_blob_length")
            if properties.size > context.limits.max_output_bytes:
                raise OperationFault("failed", "response_too_large")
            data = b""
            if properties.size:
                stream = await blob.download_blob(etag=properties.etag, match_condition=MatchConditions.IfNotModified)
                data = await stream.readall()
            if len(data) != properties.size:
                raise OperationFault("failed", "incomplete_blob_content")
            return ContentValue(data, kind="bytes", media_type=properties.content_settings.content_type or "application/octet-stream"), properties.etag
        return await context.invoke(read)

    async def write_record(self, operation, key, record, version, request, context):
        async def write():
            from azure.storage.blob import ContentSettings

            blob = self._blob(key, context)
            condition = {"etag": version, "match_condition": MatchConditions.IfNotModified} if version else {}
            if operation == "delete":
                await blob.delete_blob(**condition)
                return None
            if operation == "update" and not version:
                condition = {"etag": "*", "match_condition": MatchConditions.IfPresent}
            response = await blob.upload_blob(record.content.data, overwrite=operation != "create", max_concurrency=1,
                content_settings=ContentSettings(content_type=record.content.media_type), **condition)
            return response.get("etag")
        return await context.invoke(write, mutation=True)

    async def execute(self, operation, request, context, evidence, cursor):
        if operation != "query":
            return await super().execute(operation, request, context, evidence, cursor)
        async def page():
            pages = context.session.client("container").list_blobs(name_starts_with=request.expression,
                results_per_page=context.limits.max_items).by_page(continuation_token=cursor)
            try:
                current = await anext(pages)
            except StopAsyncIteration:
                return [], None
            values = [value async for value in current]
            return values, pages.continuation_token
        values, token = await context.invoke(page)
        if len(values) > context.limits.max_items:
            raise OperationFault("failed", "query_bound_ignored")
        items = tuple(ItemResult(index, RecordKey({self.config.key_field: value.name}), "success",
                    ContentValue({"name": value.name, "size": value.size}), version=value.etag) for index, value in enumerate(values))
        return AdapterResult(items, cursor=token, truncated=token is not None)