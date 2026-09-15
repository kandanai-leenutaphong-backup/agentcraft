"""The investigation agent: versioned configuration, resolved tools, and the model loop."""

from __future__ import annotations

from .config import (
    CONFIG_PATH,
    AgentSpec,
    ConfigError,
    ResolvedTool,
    describe_agent,
    load_agent_spec,
)
from .service import AgentService, sse

__all__ = [
    "AgentService",
    "AgentSpec",
    "CONFIG_PATH",
    "ConfigError",
    "ResolvedTool",
    "describe_agent",
    "load_agent_spec",
    "sse",
]
