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

    def __init__(self, config: ConnectorConfig) -> None:
        self.config = config
        self.capabilities = {operation: OperationCapability() for operation in OPERATIONS}

    def validate(self, operation: str, request: Request, evidence: str) -> None:
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