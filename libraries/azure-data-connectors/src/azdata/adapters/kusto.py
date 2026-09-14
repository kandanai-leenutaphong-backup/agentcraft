from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import timedelta
from urllib.parse import urlencode

from .base import Adapter, AdapterResult
from ..contracts import Caveat, ConfigurationError, ContentValue, ErrorInfo, ItemResult, OperationCapability, VerificationResult, plain
from ..execution import json_bytes
from ..transport import OperationFault


class KustoAdapter(Adapter):
    service = "adx"
    scope = "https://kusto.kusto.windows.net/.default"
    content_kinds = ("json", "bytes")
    caveats = (Caveat("append_store", "Kusto is append-oriented; keyed CRUD is not emulated."),
               Caveat("streaming_acknowledgment", "Streaming ingestion requires an enabled table policy; acceptance is not batch-content verification."),
               Caveat("public_cloud_audience", "The default token audience is public-cloud Kusto; other audiences require explicit scope configuration."))

    def __init__(self, config):
        super().__init__(config)
        if (set(config.target.coordinates) not in ({"database"}, {"database", "table"})
                or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value) for value in config.target.coordinates.values())
                or config.partition_key_field is not None):
            raise ConfigurationError("Kusto requires a database and optional table with simple identifiers")
        self.capabilities["query"] = OperationCapability("supported", dialects=("kql",), reason="")
        if "table" in config.target.coordinates:
            self.capabilities["ingest"] = OperationCapability("supported", verification=("none", "acknowledgment"), options=("mapping",), reason="")
            self.capabilities["schema"] = OperationCapability("supported", actions=("read",), verification=("none", "schema"), reason="")
        for operation in ("create", "read", "update", "upsert", "delete"):
            self.capabilities[operation] = OperationCapability(reason="keyed_operation_not_native")

    def create_client(self, session, kind):
        from azure.kusto.data import ClientRequestProperties
        from azure.kusto.ingest import IngestionProperties

        return session.pipeline_client()

    def validate(self, operation, request, evidence):
        if operation == "query":
            if request.expression.lstrip().startswith(".") or "\x00" in request.expression:
                raise OperationFault("denied", "management_command_not_query")
            if request.projection:
                raise OperationFault("unsupported", "native_projection_required")
            if request.continuation:
                raise OperationFault("unsupported", "continuation_unsupported")
            if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in request.parameters):
                raise OperationFault("invalid", "invalid_parameter_name")
            if any(value is None or type(value) not in (str, int, float, bool) for value in request.parameters.values()):
                raise OperationFault("unsupported", "parameter_type_unsupported")
        if operation == "ingest":
            if request.format not in {"json", "multijson", "csv", "tsv"}:
                raise OperationFault("unsupported", "ingestion_format_unsupported")
            if request.idempotency_key is not None:
                raise OperationFault("unsupported", "streaming_deduplication_unavailable")
            mapping = request.service_options.get(self.service, {}).get("mapping")
            if mapping is not None and (not isinstance(mapping, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", mapping)):
                raise OperationFault("invalid", "invalid_mapping_name")
            if request.content.kind == "json" and (request.format not in {"json", "multijson"}
                    or not isinstance(request.content.data, (Mapping, tuple))
                    or isinstance(request.content.data, tuple) and not all(isinstance(row, Mapping) for row in request.content.data)):
                raise OperationFault("invalid", "ingestion_rows_required")
        if operation == "schema" and (request.definition is not None or request.expected_version is not None):
            raise OperationFault("invalid", "schema_read_has_no_definition")

    def _properties(self, request, context):
        from azure.kusto.data import ClientRequestProperties

        properties = ClientRequestProperties()
        properties.client_request_id = "azdata;" + request.request_id
        properties.set_option("servertimeout", str(timedelta(seconds=context.limits.timeout_seconds)))
        properties.set_option("truncationmaxrecords", context.limits.max_items)
        properties.set_option("truncationmaxsize", context.limits.max_output_bytes)
        properties.set_option("request_readonly", True)
        properties.set_option("request_remote_entities_disabled", True)
        for name, value in getattr(request, "parameters", {}).items():
            properties.set_parameter(name, value)
        return properties

    async def execute(self, operation, request, context, evidence, cursor):
        context.session.client("rest")
        if operation == "ingest":
            return await self._ingest(request, context, evidence)
        if operation not in {"query", "schema"}:
            return await super().execute(operation, request, context, evidence, cursor)
        from azure.kusto.data.response import KustoResponseDataSetV1, KustoResponseDataSetV2

        coordinates = self.config.target.coordinates
        expression = request.expression if operation == "query" else f".show table {coordinates['table']} schema as json"
        properties = self._properties(request, context)
        body = {"db": coordinates["database"], "csl": expression, "properties": properties.to_json()}
        path = "/v2/rest/query" if operation == "query" else "/v1/rest/mgmt"
        response = await context.invoke(lambda: context.session.request("POST", path, body))
        try:
            payload = json.loads(response.body())
            dataset = KustoResponseDataSetV2(payload) if operation == "query" else KustoResponseDataSetV1(payload)
            errors = dataset.get_exceptions()
            completion_error = operation == "query" and any(frame.get("HasErrors") for frame in payload if frame.get("FrameType") == "DataSetCompletion")
            tables = dataset.primary_results
            items = []
            columns = []
            for table in tables:
                columns.append([{"name": column.column_name, "type": column.column_type} for column in table.columns])
                for row in table:
                    report = VerificationResult(evidence, "schema", "satisfied", 1) if evidence == "schema" else VerificationResult()
                    items.append(ItemResult(len(items), None, "success", ContentValue(row.to_dict(), kind="row"), verification=report))
            if errors or completion_error:
                items.append(ItemResult(len(items), None, "failed", error=ErrorInfo("kusto_partial_error", "failed")))
            truncated = len(items) > context.limits.max_items
            if truncated:
                items = items[:context.limits.max_items]
                items[-1] = ItemResult(items[-1].index, None, "failed", items[-1].content, error=ErrorInfo("kusto_row_limit", "failed"))
            return AdapterResult(tuple(items), truncated=truncated, metadata={"columns": columns})
        except (ValueError, TypeError, KeyError, IndexError, AttributeError):
            raise OperationFault("failed", "invalid_kusto_response") from None

    async def _ingest(self, request, context, evidence):
        from azure.kusto.data import DataFormat
        from azure.kusto.ingest import IngestionProperties

        coordinates = self.config.target.coordinates
        mapping = request.service_options.get(self.service, {}).get("mapping")
        format_name = "multijson" if request.format == "json" else request.format
        data_format = DataFormat[format_name.upper()]
        IngestionProperties(coordinates["database"], coordinates["table"], data_format=data_format, ingestion_mapping_reference=mapping)
        if request.content.kind == "bytes":
            payload = request.content.data
        else:
            rows = (request.content.data,) if isinstance(request.content.data, Mapping) else request.content.data
            if len(rows) > context.limits.max_items:
                raise OperationFault("invalid", "item_limit")
            payload = b"\n".join(json_bytes(row) for row in rows)
        if not payload or len(payload) > min(context.limits.max_input_bytes, 4 * 1024 * 1024):
            raise OperationFault("invalid", "streaming_input_limit")
        query = {"streamFormat": data_format.kusto_value}
        if mapping:
            query["mappingName"] = mapping
        path = f"/v1/rest/ingest/{coordinates['database']}/{coordinates['table']}?{urlencode(query)}"
        await context.invoke(lambda: context.session.request("POST", path, payload,
            {"Content-Type": "application/octet-stream", "x-ms-client-request-id": "azdata;" + request.request_id}), mutation=True)
        report = VerificationResult(evidence, "acknowledgment", "satisfied" if evidence == "acknowledgment" else "not_requested", 0)
        return AdapterResult((ItemResult(0, None, "success", effect="accepted", verification=report),))


class EventhouseAdapter(KustoAdapter):
    service = "eventhouse"