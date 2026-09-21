"""agentconfig — declarative agent definition: YAML roster, prompts, tools.

WHY THIS EXISTS
---------------
Agents defined in Python drift. Each one grows its own construction code, its
prompt gets embedded in a string literal, its tool list becomes an import
block, and adding the fifth agent means editing five files. Nobody can answer
"what agents exist and what can they do" without reading the code.

This package makes an agent a **configuration entry**: a YAML block naming a
model, prompt files, and tool specs. Adding an agent is one file plus one
config entry. Nothing in the runtime changes.

THE SHAPE
---------
    control/
      agent_config.yaml      cross-cutting: default, foundation prompts,
                             include list, tool display names
      agents/*.yaml          one fragment per use case, each owning its roster
      prompts/*.md           instruction text, composable and version-controlled

    YAML -> load + merge -> compose prompts -> resolve tools -> AgentSpec
                                                                    |
                                              your factory ---------+
                                                                    |
                                                          your SDK's agent

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
This package imports no agent SDK and no cloud SDK. The consumer supplies one
factory function that turns an ``AgentSpec`` into a concrete agent. That
function is the entire integration surface.

Unknown YAML keys are preserved on ``AgentSpec.extra`` rather than rejected, so
a consumer can carry roles, feature flags, or UI configuration in the same file
without this package knowing what any of it means.

FAIL-LOUD BY DEFAULT
--------------------
Three failure modes are converted into boot-time exceptions, because each one
otherwise ships an agent that looks fine and is not:

    - a tool spec that does not resolve            (silently missing capability)
    - an instructions list that resolves to no text (agent with no system prompt)
    - a module prefix outside the import allowlist  (arbitrary import from config)

The allowlist is empty by default. Nothing is importable until the consumer
declares a prefix.

PUBLIC SURFACE
--------------
    set_control_dir(path)             point the loader at your control/ tree
    set_allowed_tool_prefixes(prefs)  fail-closed import allowlist
    set_default_agent(agent_id)       fallback when config omits ``default``
    build_agents(factory, ...)        the seam: every spec -> your SDK
    build_spec(agent_id, ...)         resolve one agent
    build_all_specs(...)              resolve every agent, fail on any error
    AgentSpec                         the resolved, immutable definition
    tool / is_tool / tool_metadata    SDK-free tool authoring
    register_server_tool(name, fac)   platform-hosted tool factories
    load_agent_config / load_agents_block / get_tool_display_names
    invalidate_config_cache()         drop caches after editing YAML at runtime
    AgentVersionStore                 owner-scoped immutable authoring and assignment
    AgentDraft / SaveAgent / AgentVersion / InstructionFile
    AgentAssignment / AssignAgent / AgentStoreError

DEPENDENCIES
------------
Standard library plus PyYAML and Pydantic. No agent SDK, cloud SDK or web framework.
Authoring writes require POSIX flock and same-filesystem hard links.

READ NEXT
---------
``README.md`` for rationale and the design decisions worth keeping.
``CONTRACT.md`` for the exact YAML schema.
``GOTCHAS.md`` for the failures that cost real time.
``examples/`` for a complete working control tree and a factory.
"""

from __future__ import annotations

from pathlib import Path

from ._config import (
    AgentNotFound,
    default_agent_id,
    find_agent,
    get_control_dir,
    get_prompts_dir,
    get_tool_display_names,
    invalidate_config_cache,
    iter_agents,
    load_agent_config,
    load_agents_block,
    resolve_agent_cfg,
    set_default_agent_fallback as set_default_agent,
    set_default_control_dir as set_control_dir,
)
from ._decorator import TOOL_MARKER, is_tool, tool, tool_metadata
from ._prompts import PromptLoadError, load_foundation_prompts, load_instructions
from ._spec import AgentSpec, build_agents, build_all_specs, build_spec
from ._tools import (
    register_server_tool,
    resolve_tool,
    resolve_tools,
    set_default_allowed_prefixes as set_allowed_tool_prefixes,
)
from ._versions import (
    AGENT_ID,
    MAX_INSTRUCTION_BYTES,
    AgentAssignment,
    AgentDraft,
    AgentStoreError,
    AgentVersion,
    AgentVersionStore,
    AssignAgent,
    InstructionFile,
    SaveAgent,
)
from ._state import OwnerDocumentStore


def configure(
    control_dir: Path | str,
    *,
    allowed_tool_prefixes: tuple[str, ...] = (),
    default_agent: str = "",
) -> None:
    """One-call composition-root setup.

    Equivalent to calling the three setters individually. Idempotent, so it is
    safe to run from a module imported by several entrypoints.
    """
    set_control_dir(control_dir)
    if allowed_tool_prefixes:
        set_allowed_tool_prefixes(tuple(allowed_tool_prefixes))
    if default_agent:
        set_default_agent(default_agent)


__all__ = [
    "OwnerDocumentStore",
    "AGENT_ID",
    "MAX_INSTRUCTION_BYTES",
    "AgentAssignment",
    "AgentDraft",
    "AgentStoreError",
    "AgentVersion",
    "AgentVersionStore",
    "AssignAgent",
    "InstructionFile",
    "SaveAgent",
    # composition
    "configure",
    "set_control_dir",
    "set_allowed_tool_prefixes",
    "set_default_agent",
    # building
    "AgentSpec",
    "build_agents",
    "build_all_specs",
    "build_spec",
    # tool authoring
    "tool",
    "is_tool",
    "tool_metadata",
    "TOOL_MARKER",
    "register_server_tool",
    "resolve_tool",
    "resolve_tools",
    # config access
    "load_agent_config",
    "load_agents_block",
    "get_tool_display_names",
    "get_control_dir",
    "get_prompts_dir",
    "default_agent_id",
    "find_agent",
    "iter_agents",
    "resolve_agent_cfg",
    "invalidate_config_cache",
    # prompts
    "load_instructions",
    "load_foundation_prompts",
    # errors
    "AgentNotFound",
    "PromptLoadError",
]

__version__ = "1.0.0"
