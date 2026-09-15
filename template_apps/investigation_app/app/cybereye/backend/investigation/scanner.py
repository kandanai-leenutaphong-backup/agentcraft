"""Deterministic scanner over the configured telemetry table.

These patterns are derived from fields present in the Perth replay. They are not
the source CyberEye Sysmon detectors, whose table and field contracts do not
exist here.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Any

from ..data import ReadOnlyAdx
from ..models import ScanRequest, ScanResponse
from .detector import DetectorEngine


def records(result: Any) -> list[dict[str, Any]]:
    return [dict(zip(result.columns, row)) for row in result.rows]


def sid(host: str, principal: str) -> str:
    digest = hashlib.sha256(f"{host}|{principal}".encode()).hexdigest()[:12]
    return f"cyb_{digest}"


class Scanner:
    """Public compatibility facade over the concurrent detector engine."""

    def __init__(self, adx: ReadOnlyAdx, configuration: dict[str, Any] | None = None) -> None:
        self.engine = DetectorEngine(adx, configuration)

    async def scan_async(self, request: ScanRequest) -> ScanResponse:
        return await self.engine.scan(request)

    async def stream_scan(self, request: ScanRequest):
        async for event in self.engine.stream_scan(request):
            yield event

    def scan(self, request: ScanRequest) -> ScanResponse:
        return asyncio.run(self.scan_async(request))
