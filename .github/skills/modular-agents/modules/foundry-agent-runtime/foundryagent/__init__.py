"""foundryagent — run an agent roster on Azure AI Foundry, on the Microsoft
Agent Framework, with managed identity and no key material.

The whole integration surface is four calls:

    config = FoundryConfig.from_env()
    pool   = ClientPool(foundry_agent_client(config))
    agent  = build_agent(spec, pool.client_for(spec_id), config)
    result = await run_with_fallback(lambda model: agent.run(text), config)

Everything else in this package exists to make those four correct: one
credential for the process, one client per agent, one file holding every SDK
import, and a retry policy that distinguishes a throttle from a refusal.

Nothing here imports an SDK at module load. ``import foundryagent`` is free.
"""

from __future__ import annotations

from ._build import build_agent, spec_field
from ._client import ClientPool, foundry_agent_client
from ._config import DEFAULT_ENV_PREFIX, FoundryConfig
from ._credentials import (
    get_credential,
    has_credential,
    reset_credential,
    set_credential,
)
from ._maf import (
    bind_tools,
    build_compaction_strategy,
    build_tracing_middleware,
    is_maf_client,
    maf_available,
)
from ._optional import (
    SdkUnavailable,
    clear_sdks,
    sdk_available,
    set_sdk,
    set_sdk_absent,
)
from ._retry import (
    classify,
    is_fatal,
    is_rate_limit,
    is_transient,
    parse_retry_seconds,
    run_with_fallback,
    should_retry,
)
from ._tools import DEFAULT_TOOL_MARKERS, TOOL_MARKER, tool, tool_metadata

__version__ = "1.0.0"

__all__ = [
    # configuration
    "FoundryConfig",
    "DEFAULT_ENV_PREFIX",
    # identity
    "get_credential",
    "set_credential",
    "reset_credential",
    "has_credential",
    # clients
    "foundry_agent_client",
    "ClientPool",
    # agents
    "build_agent",
    "spec_field",
    # tools
    "tool",
    "tool_metadata",
    "TOOL_MARKER",
    "DEFAULT_TOOL_MARKERS",
    "bind_tools",
    # SDK bindings
    "maf_available",
    "is_maf_client",
    "build_compaction_strategy",
    "build_tracing_middleware",
    # resilience
    "classify",
    "is_rate_limit",
    "is_fatal",
    "is_transient",
    "parse_retry_seconds",
    "should_retry",
    "run_with_fallback",
    # SDK substitution seam
    "SdkUnavailable",
    "sdk_available",
    "set_sdk",
    "set_sdk_absent",
    "clear_sdks",
    "__version__",
]
