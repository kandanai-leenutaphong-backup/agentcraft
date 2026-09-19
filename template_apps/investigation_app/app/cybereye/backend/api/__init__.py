"""The HTTP surface, one router per area of the application.

Every route lives in exactly one module here; `main` composes them in this order and adds
nothing of its own. Routers depend on the application's own service packages and on
`security` for the caller, never on each other.
"""

from __future__ import annotations

from fastapi import APIRouter

from . import agent_editor, agents, chat, data_sources, graph, health, profiles, scanning, situations

#: Include order. Paths do not overlap, so this is a reading order, not a routing rule.
ROUTERS: tuple[APIRouter, ...] = (
    health.router,
    agents.router,
    agent_editor.router,
    profiles.router,
    data_sources.router,
    scanning.router,
    situations.router,
    graph.router,
    chat.router,
)

__all__ = ["ROUTERS"]
