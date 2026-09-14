from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any

from ..contracts import Caveat, ConnectorConfig, ItemResult, OPERATIONS, OperationCapability, Request
from ..execution import json_bytes
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