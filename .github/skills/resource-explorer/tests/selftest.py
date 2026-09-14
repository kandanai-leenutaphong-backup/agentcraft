#!/usr/bin/env python3
"""Walk the bundled explorer without pytest, Azure credentials or network requests."""

from __future__ import annotations

import asyncio
import sys
from collections import deque
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend/src"), str(ROOT / "vendor/azdata/src")]

from resource_explorer_api.discovery import build_access
from resource_explorer_api.nodes import InvalidNode
from resource_explorer_api.security import PrincipalGuard
from resource_explorer_api.settings import Settings
from resource_explorer_api.tree import ExplorerService, InvalidQuery


async def check() -> None:
    settings = Settings(fake_discovery=True)
    explorer = ExplorerService(settings=settings, access=build_access(settings))
    pending = deque([None])
    visited = set()
    statuses = set()
    kinds = set()
    truncated = False
    while pending:
        token = pending.popleft()
        if token in visited:
            continue
        visited.add(token)
        assert len(visited) < 2000
        response = await explorer.expand(token)
        assert response.fixtures
        assert len(response.children) <= settings.max_children
        statuses.add(response.status)
        truncated = truncated or response.truncated
        for child in response.children:
            if child.expandable:
                pending.append(child.id)
            if child.has_content:
                content = await explorer.read_content(child.id)
                assert content.fixtures
                kinds.add(content.content_kind)
                statuses.add(content.status)
    assert {"ok", "empty", "forbidden", "unreachable", "unconfigured", "unavailable"} <= statuses
    assert {"text", "json", "csv", "markdown", "image", "binary", "rows"} <= kinds
    assert truncated
    print("ok: fixture tree, content kinds, degraded statuses and truncation survive")

    hits = await explorer.search("fixture", limit=3)
    assert hits.fixtures and hits.hits and len(hits.hits) <= 3
    for hit in hits.hits:
        assert (await explorer.expand(hit.node)).fixtures
    print("ok: search results round trip into the tree")

    for operation, error in [(explorer.expand("invalid-node"), InvalidNode), (explorer.search(""), InvalidQuery)]:
        try:
            await operation
        except error:
            pass
        else:
            raise AssertionError("invalid input was accepted")
    print("ok: malformed node IDs and empty queries refused")

    async def protected_app(scope, receive, send):
        raise AssertionError("anonymous request reached the protected application")

    messages = []

    async def send(message):
        messages.append(message)

    guard = PrincipalGuard(protected_app)
    await guard({"type": "http", "path": "/api/tree", "headers": []}, None, send)
    assert messages[0]["status"] == 401
    print("ok: HTTP principal guard still refuses anonymous access")
    print("resource-explorer selftest: PASS")


if __name__ == "__main__":
    with patch("socket.socket.connect", side_effect=AssertionError("selftest attempted network access")):
        asyncio.run(check())