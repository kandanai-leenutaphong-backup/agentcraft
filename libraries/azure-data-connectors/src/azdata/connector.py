from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Any

from .adapters.base import Adapter
from .contracts import (
    Caveat, ConfigurationError, ConnectorConfig, ConnectorDescription, CreateRequest,
    DeleteRequest, ErrorInfo, IngestRequest, Limits, OperationResult, ProvisionRequest,
    QueryRequest, ReadRequest, REQUEST_TYPES, Request, ResourceAddress, SchemaRequest,
    StatusRequest, UpdateRequest, UpsertRequest, VerificationResult,
)
from .execution import Continuations, aggregate, bounded_items, evidence_satisfies, json_bytes, validate_request
from .policy import Policy
from .transport import AsyncTransport, CallContext, OperationFault, Session


def connect(service: str, config: ConnectorConfig, *, credential: Any, policy: Policy,
            transport: AsyncTransport | None = None) -> DataConnector:
    if not isinstance(config, ConnectorConfig) or not isinstance(policy, Policy):
        raise ConfigurationError("ConnectorConfig and Policy are required")
    if credential is None or not callable(getattr(credential, "get_token", None)):
        raise ConfigurationError("an injected token credential is required")
    if transport is not None and not callable(getattr(transport, "request", None)):
        raise ConfigurationError("transport must implement async request")
    if service == "search":
        from .adapters.search import SearchAdapter

        adapter = SearchAdapter(config)
    elif service == "cosmos":
        from .adapters.cosmos import CosmosAdapter

        adapter = CosmosAdapter(config)
    else:
        raise ConfigurationError("unregistered data service")
    return DataConnector(adapter, credential=credential, policy=policy, transport=transport)


class DataConnector:
    def __init__(self, adapter: Adapter, *, credential: Any, policy: Policy,
                 transport: AsyncTransport | None = None) -> None:
        self._adapter = adapter
        self._config = adapter.config
        self._policy = policy
        self._session = Session(adapter.service, adapter.config, credential, transport, policy.max_concurrency)
        self._continuations = Continuations()
        self._closed = False
        self._close_lock = asyncio.Lock()

    def describe(self) -> ConnectorDescription:
        return ConnectorDescription(self._adapter.service, self._config.target, self._adapter.capabilities,
                                    self._policy.limits, tuple(sorted(self._policy.grants)),
                                    (self._config.key_field,), self._adapter.partition_required, self._adapter.caveats)

    async def create(self, request: CreateRequest) -> OperationResult:
        return await self._execute("create", request)

    async def read(self, request: ReadRequest) -> OperationResult:
        return await self._execute("read", request)

    async def update(self, request: UpdateRequest) -> OperationResult:
        return await self._execute("update", request)

    async def upsert(self, request: UpsertRequest) -> OperationResult:
        return await self._execute("upsert", request)

    async def delete(self, request: DeleteRequest) -> OperationResult:
        return await self._execute("delete", request)

    async def query(self, request: QueryRequest) -> OperationResult:
        return await self._execute("query", request)

    async def ingest(self, request: IngestRequest) -> OperationResult:
        return await self._execute("ingest", request)

    async def schema(self, request: SchemaRequest) -> OperationResult:
        return await self._execute("schema", request)

    async def provision(self, request: ProvisionRequest) -> OperationResult:
        return await self._execute("provision", request)

    async def status(self, request: StatusRequest) -> OperationResult:
        return await self._execute("status", request)

    async def aclose(self) -> None:
        async with self._close_lock:
            if not self._closed:
                self._closed = True
                await self._session.aclose()

    async def __aenter__(self) -> DataConnector:
        if self._closed:
            raise ConfigurationError("connector is closed")
        return self

    async def __aexit__(self, exception_type, exception, traceback) -> None:
        await self.aclose()

    def _binding(self, request: QueryRequest) -> bytes:
        return json_bytes([self._adapter.service, self._config.endpoint, self._config.target.coordinates,
                           self._policy.principal, sorted(self._policy.grants), request.dialect,
                           request.expression, request.parameters, request.projection, request.service_options])

    async def _execute(self, operation: str, request: Request) -> OperationResult:
        context = None
        evidence = "none"
        try:
            if self._closed:
                raise OperationFault("failed", "connector_closed")
            if type(request) is not REQUEST_TYPES[operation]:
                raise OperationFault("invalid", "wrong_request_type")
            if request.target is not None and (not isinstance(request.target, ResourceAddress)
                                               or request.target != self._config.target):
                raise OperationFault("denied", "target_outside_scope")
            limits = request.limits if request.limits is not None else self._policy.limits
            if not isinstance(limits, Limits) or not limits.within(self._policy.limits):
                raise OperationFault("invalid", "limits_exceed_policy")
            validate_request(operation, request, limits, self._config.key_field, self._config.partition_key_field)
            capability = self._adapter.capabilities[operation]
            if capability.support == "unsupported":
                raise OperationFault("unsupported", capability.reason)
            if hasattr(request, "mode") and request.mode not in capability.modes:
                raise OperationFault("unsupported", "mode_unsupported")
            if hasattr(request, "action") and request.action not in capability.actions:
                raise OperationFault("unsupported", "action_unsupported")
            if hasattr(request, "dialect") and request.dialect not in capability.dialects:
                raise OperationFault("unsupported", "dialect_unsupported")
            if not set(request.requirements.guarantees) <= set(capability.guarantees):
                raise OperationFault("unsupported", "guarantee_unsupported")
            if set(request.service_options) - {self._adapter.service}:
                raise OperationFault("invalid", "unknown_option_namespace")
            options = request.service_options.get(self._adapter.service, {})
            if not isinstance(options, Mapping):
                raise OperationFault("invalid", "invalid_service_options")
            if set(options) - set(capability.options):
                raise OperationFault("invalid", "unknown_service_option")
            grant = f"{operation}.{request.action}" if operation in {"schema", "provision"} else operation
            if grant not in self._policy.grants:
                raise OperationFault("denied", "operation_not_granted")
            minimum = self._policy.minimum_verification.get(grant, "none")
            if operation == "schema" and request.action in {"create", "update", "delete"}:
                minimum = "schema"
            evidence = request.verification.kind if request.verification.kind != "none" else minimum
            if not evidence_satisfies(evidence, minimum):
                raise OperationFault("denied", "verification_below_policy")
            if evidence not in capability.verification:
                raise OperationFault("unsupported", "verification_unsupported")
            if evidence in {"presence", "content", "absence"} and "read" not in self._policy.grants:
                raise OperationFault("denied", "verification_read_not_granted")
            if evidence == "schema" and "schema.read" not in self._policy.grants:
                raise OperationFault("denied", "verification_read_not_granted")
            if operation == "schema" and request.action == "delete" and not self._policy.destructive:
                raise OperationFault("denied", "destructive_not_granted")
            self._adapter.validate(operation, request, evidence)
            cursor = self._continuations.decode(request.continuation, self._binding(request)) if isinstance(request, QueryRequest) and request.continuation else None
            context = CallContext(self._session, limits)
            result = await self._adapter.execute(operation, request, context, evidence, cursor)
            items, bounded = bounded_items(result.items, limits.max_output_bytes, query=operation == "query")
            continuation = self._continuations.encode(result.cursor, self._binding(request)) if result.cursor is not None and not bounded else None
            caveats = self._adapter.caveats + result.caveats
            if bounded:
                caveats += (Caveat("output_bound", "Returned content is bounded; dropped query content cannot be resumed."),)
            status = aggregate(items)
            reports = [item.verification for item in items]
            if evidence == "none" or not items:
                verification = VerificationResult(evidence)
            elif all(report.state == "satisfied" for report in reports):
                verification = VerificationResult(evidence, evidence, "satisfied", sum(report.attempts for report in reports))
            else:
                verification = VerificationResult(evidence, "none", "unknown" if any(report.state == "unknown" for report in reports)
                                                  else "pending" if any(report.state == "pending" for report in reports) else "failed",
                                                  sum(report.attempts for report in reports))
            return OperationResult(request.request_id, operation, self._adapter.service, self._config.target,
                                   status, items, tuple(item.error for item in items if item.error), verification,
                                   continuation, result.truncated or bounded, caveats=caveats,
                                   metrics={"elapsed_ms": round((time.monotonic() - context.started) * 1000, 3), "attempts": context.attempts})
        except OperationFault as fault:
            identifier = getattr(request, "request_id", "")
            if not isinstance(identifier, str) or len(identifier) > 128 or any(ord(character) < 32 for character in identifier):
                identifier = ""
            return OperationResult(identifier, operation, self._adapter.service,
                                   self._config.target, fault.status, errors=(ErrorInfo(fault.code, fault.status),),
                                   verification=VerificationResult(evidence), caveats=self._adapter.caveats,
                                   metrics={"attempts": context.attempts if context else 0})