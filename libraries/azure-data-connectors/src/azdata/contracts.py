from __future__ import annotations

import base64
import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from types import MappingProxyType
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4

CONTRACT_VERSION = "1"
OPERATIONS = ("create", "read", "update", "upsert", "delete", "query", "ingest", "schema", "provision", "status")
EVIDENCE = frozenset({"none", "acknowledgment", "presence", "content", "absence", "schema"})


class ConfigurationError(ValueError):
    pass


def freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(item) for item in value)
    if isinstance(value, bytearray):
        return bytes(value)
    return value


def plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    return value


def positive(value: Any, *, integer: bool = False) -> bool:
    expected = int if integer else (int, float)
    if isinstance(value, bool) or not isinstance(value, expected) or value <= 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def serialized(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: serialized(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Mapping):
        return {key: serialized(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serialized(item) for item in value]
    if isinstance(value, bytes):
        return {"encoding": "base64", "value": base64.b64encode(value).decode("ascii")}
    if isinstance(value, (datetime, date, time)):
        kind = "datetime" if isinstance(value, datetime) else "date" if isinstance(value, date) else "time"
        return {"type": kind, "value": value.isoformat()}
    if isinstance(value, (Decimal, UUID)):
        return {"type": type(value).__name__.lower(), "value": str(value)}
    if isinstance(value, timedelta):
        return {"type": "timedelta", "days": value.days, "seconds": value.seconds, "microseconds": value.microseconds}
    return value


@dataclass(frozen=True)
class ResourceAddress:
    coordinates: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "coordinates", freeze(self.coordinates))


@dataclass(frozen=True)
class RecordKey:
    parts: Mapping[str, Any]
    partition: Any = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "parts", freeze(self.parts))
        object.__setattr__(self, "partition", freeze(self.partition))


@dataclass(frozen=True)
class ContentValue:
    data: Any = field(repr=False)
    kind: str = "json"
    media_type: str = "application/json"

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", freeze(self.data))


@dataclass(frozen=True)
class RecordInput:
    key: RecordKey
    content: ContentValue = field(repr=False)
    expected_version: str | None = None


@dataclass(frozen=True)
class Limits:
    timeout_seconds: float = 30.0
    max_items: int = 100
    max_input_bytes: int = 1_048_576
    max_output_bytes: int = 1_048_576
    max_attempts: int = 1

    def valid(self) -> bool:
        return positive(self.timeout_seconds) and all(
            positive(value, integer=True) for value in
            (self.max_items, self.max_input_bytes, self.max_output_bytes, self.max_attempts)
        )

    def within(self, ceiling: Limits) -> bool:
        return self.valid() and all(getattr(self, name) <= getattr(ceiling, name) for name in self.__dataclass_fields__)


@dataclass(frozen=True)
class Requirements:
    guarantees: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "guarantees", freeze(self.guarantees))


@dataclass(frozen=True)
class Verification:
    kind: str = "none"
    attempts: int = 3
    interval_seconds: float = 0.05


@dataclass(frozen=True, kw_only=True)
class Request:
    target: ResourceAddress | None = None
    request_id: str = field(default_factory=lambda: uuid4().hex)
    limits: Limits | None = None
    requirements: Requirements = field(default_factory=Requirements)
    verification: Verification = field(default_factory=Verification)
    service_options: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, freeze(getattr(self, name)))


@dataclass(frozen=True, kw_only=True)
class CreateRequest(Request):
    records: tuple[RecordInput, ...] = ()


@dataclass(frozen=True, kw_only=True)
class ReadRequest(Request):
    keys: tuple[RecordKey, ...] = ()
    projection: tuple[str, ...] = ()
    missing: str = "error"


@dataclass(frozen=True, kw_only=True)
class UpdateRequest(Request):
    mode: str
    records: tuple[RecordInput, ...] = ()


@dataclass(frozen=True, kw_only=True)
class UpsertRequest(Request):
    mode: str
    records: tuple[RecordInput, ...] = ()


@dataclass(frozen=True, kw_only=True)
class DeleteRequest(Request):
    keys: tuple[RecordKey, ...] = ()
    missing: str = "error"
    expected_versions: tuple[str | None, ...] = ()


@dataclass(frozen=True, kw_only=True)
class QueryRequest(Request):
    dialect: str
    expression: str = field(repr=False)
    parameters: Mapping[str, Any] = field(default_factory=dict, repr=False)
    projection: tuple[str, ...] = ()
    continuation: str | None = field(default=None, repr=False)


@dataclass(frozen=True, kw_only=True)
class IngestRequest(Request):
    content: ContentValue = field(default_factory=lambda: ContentValue(()), repr=False)
    format: str = "json"
    idempotency_key: str | None = None


@dataclass(frozen=True, kw_only=True)
class SchemaRequest(Request):
    action: str
    definition: Mapping[str, Any] | None = field(default=None, repr=False)
    expected_version: str | None = None
    confirmation: str | None = None


@dataclass(frozen=True, kw_only=True)
class ProvisionRequest(Request):
    action: str
    specification: Mapping[str, Any] | None = field(default=None, repr=False)
    expected_version: str | None = None
    confirmation: str | None = None


@dataclass(frozen=True, kw_only=True)
class StatusRequest(Request):
    operation_ref: str


REQUEST_TYPES = dict(zip(OPERATIONS, (CreateRequest, ReadRequest, UpdateRequest, UpsertRequest, DeleteRequest,
                                    QueryRequest, IngestRequest, SchemaRequest, ProvisionRequest, StatusRequest)))


@dataclass(frozen=True)
class ErrorInfo:
    code: str
    category: str
    retryable: bool = False


@dataclass(frozen=True)
class Caveat:
    code: str
    detail: str


@dataclass(frozen=True)
class VerificationResult:
    requested: str = "none"
    achieved: str = "none"
    state: str = "not_requested"
    attempts: int = 0


@dataclass(frozen=True)
class ItemResult:
    index: int
    key: RecordKey | None
    status: str
    content: ContentValue | None = field(default=None, repr=False)
    version: str | None = None
    error: ErrorInfo | None = None
    verification: VerificationResult = field(default_factory=VerificationResult)
    effect: str = "none"


@dataclass(frozen=True)
class OperationResult:
    request_id: str
    operation: str
    service: str
    target: ResourceAddress
    status: str
    items: tuple[ItemResult, ...] = ()
    errors: tuple[ErrorInfo, ...] = ()
    verification: VerificationResult = field(default_factory=VerificationResult)
    continuation: str | None = field(default=None, repr=False)
    truncated: bool = False
    operation_ref: str | None = None
    caveats: tuple[Caveat, ...] = ()
    metrics: Mapping[str, int | float] = field(default_factory=dict)
    contract_version: str = CONTRACT_VERSION
    metadata: Mapping[str, Any] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metrics", freeze(self.metrics))
        object.__setattr__(self, "metadata", freeze(self.metadata))

    def to_dict(self) -> dict[str, Any]:
        return serialized(self)


@dataclass(frozen=True)
class OperationCapability:
    support: str = "unsupported"
    modes: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    dialects: tuple[str, ...] = ()
    guarantees: tuple[str, ...] = ()
    verification: tuple[str, ...] = ("none",)
    options: tuple[str, ...] = ()
    reason: str = "not_implemented"


@dataclass(frozen=True)
class ConnectorDescription:
    service: str
    target: ResourceAddress
    operations: Mapping[str, OperationCapability]
    limits: Limits
    grants: tuple[str, ...]
    required_key_fields: tuple[str, ...]
    partition_required: bool
    caveats: tuple[Caveat, ...] = ()
    availability: str = "unverified"
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "operations", freeze(self.operations))

    def to_dict(self) -> dict[str, Any]:
        return serialized(self)


@dataclass(frozen=True)
class ConnectorConfig:
    endpoint: str = field(repr=False)
    target: ResourceAddress
    allowed_hosts: tuple[str, ...]
    key_field: str = "id"
    partition_key_field: str | None = None
    api_version: str = "2024-07-01"
    scope: str | None = None
    retrievable_fields: tuple[str, ...] | None = None
    key_fields: tuple[str, ...] | None = None
    database_user: str | None = None
    enable_preview: bool = False
    credential_kind: str = "entra"

    def __post_init__(self) -> None:
        try:
            parsed = urlsplit(self.endpoint)
            valid = (parsed.scheme in {"https", "postgresql", "mssql", "wss"} and parsed.hostname and not parsed.username and not parsed.password
                     and not parsed.query and not parsed.fragment and parsed.path in ("", "/")
                     and parsed.port in (None, {"https": 443, "postgresql": 5432, "mssql": 1433, "wss": 443}[parsed.scheme])
                     and not any(character.isspace() for character in self.endpoint))
        except (TypeError, ValueError, AttributeError):
            valid = False
            parsed = None
        if not valid or parsed is None:
            raise ConfigurationError("endpoint must be a supported secure service origin")
        if (not isinstance(self.allowed_hosts, (tuple, list)) or not self.allowed_hosts
                or not all(isinstance(host, str) and host == host.lower() and re.fullmatch(r"[a-z0-9.-]+", host)
                           for host in self.allowed_hosts) or parsed.hostname not in self.allowed_hosts):
            raise ConfigurationError("endpoint host must be explicitly allowed")
        if (not isinstance(self.target, ResourceAddress) or not isinstance(self.target.coordinates, Mapping)
                or not self.target.coordinates or not all(isinstance(key, str) and isinstance(value, str)
                    and value.strip() and len(value) <= 256 for key, value in self.target.coordinates.items())):
            raise ConfigurationError("target requires named resource coordinates")
        if not isinstance(self.key_field, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.key_field):
            raise ConfigurationError("invalid key field")
        if self.key_fields is not None:
            if (not isinstance(self.key_fields, (tuple, list)) or not self.key_fields
                    or not all(isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in self.key_fields)
                    or len(set(self.key_fields)) != len(self.key_fields)):
                raise ConfigurationError("key_fields must be distinct field names")
            object.__setattr__(self, "key_fields", tuple(self.key_fields))
        if self.database_user is not None and (not isinstance(self.database_user, str) or not self.database_user
                or len(self.database_user) > 256 or any(ord(character) < 32 for character in self.database_user)):
            raise ConfigurationError("invalid database user")
        if type(self.enable_preview) is not bool:
            raise ConfigurationError("enable_preview must be a boolean")
        if not isinstance(self.credential_kind, str) or self.credential_kind not in {"entra", "resource_token"}:
            raise ConfigurationError("unsupported credential kind")
        if self.partition_key_field is not None and (not isinstance(self.partition_key_field, str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.partition_key_field)):
            raise ConfigurationError("partition key field must be a top-level field name")
        if not isinstance(self.api_version, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}(?:-preview)?", self.api_version):
            raise ConfigurationError("invalid API version")
        if self.scope is not None and (not isinstance(self.scope, str) or not self.scope.startswith("https://")
                                       or not self.scope.endswith("/.default")):
            raise ConfigurationError("invalid credential scope")
        object.__setattr__(self, "endpoint", self.endpoint.rstrip("/"))
        object.__setattr__(self, "allowed_hosts", tuple(self.allowed_hosts))
        if self.retrievable_fields is not None:
            if not isinstance(self.retrievable_fields, (tuple, list)) or not all(isinstance(name, str) and name for name in self.retrievable_fields):
                raise ConfigurationError("retrievable fields must be field names")
            object.__setattr__(self, "retrievable_fields", tuple(self.retrievable_fields))