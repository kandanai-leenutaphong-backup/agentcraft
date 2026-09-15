from __future__ import annotations

import json
import re
import time
from urllib.parse import urlencode, urlsplit
from uuid import UUID

from .base import Adapter, AdapterResult
from ..contracts import Caveat, ConfigurationError, ContentValue, ErrorInfo, ItemResult, OperationCapability, VerificationResult
from ..transport import OperationFault


class GraphAdapter(Adapter):
    service = "graph"
    scope = "https://api.fabric.microsoft.com/.default"
    caveats = (Caveat("preview_api", "GraphModel query is a beta API requiring explicit preview opt-in."),
               Caveat("refresh_not_record_crud", "Ingestion refreshes existing model sources; it does not insert or update individual vertices."),
               Caveat("refresh_not_content_proof", "Completed refresh is job evidence, not a claim that a particular input batch is queryable."))

    def __init__(self, config):
        super().__init__(config)
        try:
            if set(config.target.coordinates) != {"workspace", "graph_model"}:
                raise ValueError()
            for value in config.target.coordinates.values():
                if str(UUID(value)) != value:
                    raise ValueError()
        except ValueError:
            raise ConfigurationError("GraphModel requires canonical workspace and graph_model UUIDs") from None
        if config.partition_key_field is not None:
            raise ConfigurationError("GraphModel has no record partition field")
        self.root = f"/v1/workspaces/{config.target.coordinates['workspace']}/graphModels/{config.target.coordinates['graph_model']}"
        self.job_root = f"/v1/workspaces/{config.target.coordinates['workspace']}/items/{config.target.coordinates['graph_model']}/jobs/instances/"
        self.capabilities["query"] = OperationCapability("supported", dialects=("gql",), reason="")
        self.capabilities["ingest"] = OperationCapability("supported", verification=("none", "acknowledgment"), reason="")
        self.capabilities["schema"] = OperationCapability("supported", actions=("read",), verification=("none",), reason="")
        self.capabilities["status"] = OperationCapability("supported", reason="")
        for operation in ("create", "read", "update", "upsert", "delete"):
            self.capabilities[operation] = OperationCapability(reason="graph_record_crud_not_native")

    def create_client(self, session, kind):
        import aiohttp

        return session.pipeline_client()

    def validate(self, operation, request, evidence):
        if operation == "query":
            if not self.config.enable_preview:
                raise OperationFault("unsupported", "graph_preview_opt_in_required")
            if request.parameters or request.projection:
                raise OperationFault("unsupported", "graph_native_binding_unavailable")
            expression = request.expression.strip().rstrip(";").strip()
            if (not re.match(r"^(MATCH|OPTIONAL\s+MATCH|RETURN)\b", expression, re.I)
                    or ";" in expression or re.search(r"\b(INSERT|DELETE|REMOVE|SET|CREATE|DROP|CALL|COPY|LOAD)\b", expression, re.I)):
                raise OperationFault("denied", "read_gql_required")
        if operation == "ingest":
            if request.format != "refresh" or request.content.data not in ((), None) or request.idempotency_key is not None:
                raise OperationFault("unsupported", "graph_refresh_only")
        if operation == "schema" and (request.definition is not None or request.expected_version is not None):
            raise OperationFault("invalid", "schema_read_has_no_definition")

    def _reference(self, response, kind):
        location = response.headers.get("Location")
        parsed = urlsplit(location or "")
        endpoint = urlsplit(self.config.endpoint)
        prefix = self.job_root if kind == "refresh" else "/v1/operations/"
        suffix = parsed.path.removeprefix(prefix)
        if ((parsed.scheme, parsed.netloc) != (endpoint.scheme, endpoint.netloc) or parsed.query or parsed.fragment
                or not parsed.path.startswith(prefix) or not re.fullmatch(r"[0-9a-f-]{36}", suffix)):
            raise OperationFault("unknown" if kind == "refresh" else "failed", "operation_location_outside_scope")
        delay = self._retry_delay(response)
        return json.dumps({"kind": kind, "path": parsed.path, "not_before": time.time() + delay}), delay

    @staticmethod
    def _retry_delay(response):
        try:
            delay = int(response.headers.get("Retry-After", "0"))
            if not 0 <= delay <= 86400:
                raise ValueError()
        except ValueError:
            raise OperationFault("unknown", "invalid_retry_after") from None
        return delay

    @staticmethod
    def _payload(response):
        try:
            payload = json.loads(response.body())
            if not isinstance(payload, dict):
                raise ValueError()
            return payload
        except (ValueError, TypeError):
            raise OperationFault("failed", "invalid_graph_response") from None

    async def execute(self, operation, request, context, evidence, cursor):
        if operation == "query":
            parameters = {"beta": "true"}
            if cursor:
                parameters["continuationToken"] = cursor
            response = await context.invoke(lambda: context.session.request("POST", self.root + "/executeQuery?" + urlencode(parameters), {"query": request.expression}))
            payload = self._payload(response)
            if payload.get("status", {}).get("code") != "00000":
                raise OperationFault("failed", "gql_execution_failed")
            result = payload.get("result", {})
            if result.get("kind") != "TABLE" or not isinstance(result.get("data"), list) or not all(isinstance(row, dict) for row in result["data"]):
                raise OperationFault("failed", "gql_table_required")
            rows = result["data"]
            token = payload.get("continuationToken")
            if token is not None and not isinstance(token, str):
                raise OperationFault("failed", "invalid_provider_continuation")
            truncated = len(rows) > context.limits.max_items
            items = tuple(ItemResult(index, None, "success", ContentValue(row)) for index, row in enumerate(rows[:context.limits.max_items]))
            return AdapterResult(items, cursor=None if truncated else token, truncated=truncated or bool(token), metadata={"columns": result.get("columns", [])})
        if operation == "ingest":
            response = await context.invoke(lambda: context.session.request("POST", self.root + "/jobs/refreshGraph/instances"), mutation=True)
            if response.status_code != 202:
                raise OperationFault("unknown", "refresh_acknowledgment_invalid")
            reference, delay = self._reference(response, "refresh")
            report = VerificationResult(evidence, "acknowledgment", "satisfied" if evidence == "acknowledgment" else "not_requested")
            return AdapterResult((ItemResult(0, None, "pending", effect="accepted", verification=report),),
                                 operation_ref=reference, metadata={"retry_after_seconds": delay})
        if operation == "schema":
            response = await context.invoke(lambda: context.session.request("POST", self.root + "/getDefinition"))
            if response.status_code == 202:
                reference, delay = self._reference(response, "definition")
                return AdapterResult((ItemResult(0, None, "pending"),), operation_ref=reference, metadata={"retry_after_seconds": delay})
            payload = self._payload(response)
            if not isinstance(payload.get("definition"), dict):
                raise OperationFault("failed", "graph_definition_missing")
            return AdapterResult((ItemResult(0, None, "success", ContentValue(payload["definition"])),))
        if operation == "status":
            try:
                reference = json.loads(cursor)
                kind, path, not_before = reference["kind"], reference["path"], reference["not_before"]
            except (ValueError, TypeError, KeyError):
                raise OperationFault("invalid", "invalid_operation_reference") from None
            if time.time() < not_before:
                return AdapterResult((ItemResult(0, None, "pending"),), operation_ref=cursor,
                                     metadata={"retry_after_seconds": max(0, not_before - time.time())})
            response = await context.invoke(lambda: context.session.request("GET", path))
            payload = self._payload(response)
            state = payload.get("status")
            if state in {"NotStarted", "InProgress", "Running"}:
                delay = self._retry_delay(response)
                reference["not_before"] = time.time() + delay
                return AdapterResult((ItemResult(0, None, "pending"),), operation_ref=json.dumps(reference), metadata={"retry_after_seconds": delay})
            if state in {"Failed", "Cancelled"}:
                return AdapterResult((ItemResult(0, None, "failed", error=ErrorInfo("graph_job_failed", "failed")),))
            if state not in {"Completed", "Succeeded"}:
                raise OperationFault("unknown", "unknown_graph_job_state")
            if kind == "definition":
                response = await context.invoke(lambda: context.session.request("GET", path + "/result"))
                payload = self._payload(response)
                if not isinstance(payload.get("definition"), dict):
                    raise OperationFault("failed", "graph_definition_missing")
                return AdapterResult((ItemResult(0, None, "success", ContentValue(payload["definition"])),))
            return AdapterResult((ItemResult(0, None, "success", ContentValue({"status": state})),))
        return await super().execute(operation, request, context, evidence, cursor)