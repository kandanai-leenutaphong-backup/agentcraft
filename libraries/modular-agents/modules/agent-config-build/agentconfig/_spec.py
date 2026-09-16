"""Agent spec resolution — config + prompts + tools into one immutable object.

Module role:
    The composition step. Turns a YAML agent definition into a fully resolved
    :class:`AgentSpec`: display metadata, model id, the concatenated system
    prompt, and the imported tool callables. This is the boundary where
    declarative configuration stops and a concrete agent SDK begins.

Why a spec object and not a built agent:
    Building an agent binds you to one SDK. Returning a spec keeps the
    declarative layer usable by any of them: the consumer's factory receives a
    spec and constructs whatever its framework wants. That single function is
    the entire integration surface of this box.

Fail-loud by construction:
    A missing prompt file, an unresolvable tool spec, or a disallowed import
    prefix raises here, at build time. An agent that silently boots without its
    tools or its instructions is the failure this module exists to prevent
    (GOTCHAS.md G1, G2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ._config import (
    AgentNotFound,
    get_prompts_dir,
    iter_agents,
    load_agents_block,
    resolve_agent_cfg,
)
from ._prompts import load_foundation_prompts, load_instructions
from ._tools import resolve_tools


@dataclass(frozen=True, slots=True)
class AgentSpec:
    """One agent, fully resolved and ready to hand to an SDK.

    Attributes:
        agent_id: Config key. Stable identifier used by sessions and clients.
        name: Human-facing display name.
        description: One line on what the agent does; shown in pickers.
        model: Model identifier, passed through verbatim to the SDK.
        instructions: Foundation prompts + per-agent prompts, already
            concatenated in configured order.
        tools: Imported callables and platform-tool objects, in configured
            order. Order is preserved because some SDKs surface tools to the
            model in list order.
        surface: Where the agent is exposed. Consumer-defined vocabulary; the
            empty string means "no surface declared". Conventionally ``hidden``
            keeps an agent out of user-facing pickers while leaving it callable.
        extra: Every other key from the YAML definition, untouched. This is
            what lets a consumer carry its own metadata (roles, feature flags,
            UI hints) in the same file without this package knowing about it.
    """

    agent_id: str
    name: str
    description: str
    model: str
    instructions: str
    tools: tuple[Any, ...] = ()
    surface: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def is_hidden(self) -> bool:
        """True when the agent should not appear in a user-facing picker."""
        return self.surface == "hidden"


# Keys this package consumes; everything else passes through to ``extra`` so a
# consumer can extend the schema without forking the loader.
_KNOWN_KEYS = frozenset(
    {"name", "description", "model", "instructions", "tools", "surface"}
)


def build_spec(
    agent_id: str | None = None,
    *,
    control_dir: Path | None = None,
    allowed_prefixes: tuple[str, ...] | None = None,
    default_model: str = "",
) -> AgentSpec:
    """Resolve one agent id (or the configured default) to an ``AgentSpec``.

    Args:
        agent_id: Agent to resolve. ``None`` resolves the config's ``default``.
        control_dir: Directory holding ``agent_config.yaml`` and ``prompts/``.
            ``None`` uses the process-wide default registered via
            :func:`agentconfig.set_control_dir`.
        allowed_prefixes: Import allowlist for local tool specs. ``None`` uses
            the process-wide default, which is empty (fail-closed).
        default_model: Model used when a definition omits ``model``. Empty
            means the SDK's own default applies.

    Raises:
        AgentNotFound: the id is absent from the merged config.
        PromptLoadError: ``instructions`` was non-empty but resolved to no text.
        ValueError / ImportError / AttributeError / TypeError: a tool spec did
            not resolve.
    """
    target_id, cfg = resolve_agent_cfg(agent_id)

    prompts_dir = get_prompts_dir() if control_dir is None else control_dir / "prompts"

    # Foundation text is prepended to every agent, so cross-cutting rules live
    # in one file rather than being duplicated into each prompt.
    foundation = load_foundation_prompts()
    per_agent = load_instructions(cfg.get("instructions") or [], prompts_dir)
    instructions = "\n\n".join(part for part in (foundation, per_agent) if part)

    tools = resolve_tools(
        [str(spec) for spec in (cfg.get("tools") or [])],
        allowed_prefixes=allowed_prefixes,
    )

    return AgentSpec(
        agent_id=target_id,
        name=str(cfg.get("name") or target_id),
        description=str(cfg.get("description") or ""),
        model=str(cfg.get("model") or default_model),
        instructions=instructions,
        tools=tuple(tools),
        surface=str(cfg.get("surface") or ""),
        extra={k: v for k, v in cfg.items() if k not in _KNOWN_KEYS},
    )


def build_all_specs(
    *,
    control_dir: Path | None = None,
    allowed_prefixes: tuple[str, ...] | None = None,
    default_model: str = "",
) -> dict[str, AgentSpec]:
    """Resolve every agent in the merged config.

    Use at boot to fail the whole process on any broken definition, rather than
    discovering a typo when a user first selects that agent.
    """
    block = load_agents_block()
    return {
        agent_id: build_spec(
            agent_id,
            control_dir=control_dir,
            allowed_prefixes=allowed_prefixes,
            default_model=default_model,
        )
        for agent_id, _ in iter_agents(block)
    }


def build_agents(
    factory: Callable[[AgentSpec], Any],
    *,
    control_dir: Path | None = None,
    allowed_prefixes: tuple[str, ...] | None = None,
    default_model: str = "",
) -> dict[str, Any]:
    """Resolve every agent and hand each spec to the consumer's factory.

    This is the injection seam. ``factory`` is the only code a consumer writes
    to bind this declarative layer to a concrete agent SDK.

    Example::

        agents = build_agents(
            lambda spec: ChatAgent(
                name=spec.name,
                instructions=spec.instructions,
                tools=list(spec.tools),
            ),
            allowed_prefixes=("mytools.",),
        )
    """
    specs = build_all_specs(
        control_dir=control_dir,
        allowed_prefixes=allowed_prefixes,
        default_model=default_model,
    )
    return {agent_id: factory(spec) for agent_id, spec in specs.items()}


__all__ = [
    "AgentSpec",
    "AgentNotFound",
    "build_spec",
    "build_all_specs",
    "build_agents",
]
