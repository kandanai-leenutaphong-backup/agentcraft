#!/usr/bin/env python3
"""A complete fixture-backed application-service call without an HTTP server."""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "vendor/azdata/src")]

from resource_explorer_api.discovery import build_access
from resource_explorer_api.settings import Settings
from resource_explorer_api.tree import ExplorerService


async def main() -> None:
    settings = Settings(fake_discovery=True)
    service = ExplorerService(settings=settings, access=build_access(settings))
    result = await service.expand(None)
    print(json.dumps(result.model_dump(mode="json", by_alias=True), indent=2))


if __name__ == "__main__":
    asyncio.run(main())