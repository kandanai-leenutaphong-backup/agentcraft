"""build_agent — the composition point: a spec plus a client become an agent.

Module role:
    Resolves the model, binds the tools, calls the SDK's ``as_agent``, and
    attaches compaction. It is the seam a declarative agent roster plugs into:
    anything that can produce a name, instructions, tools and a model can be
    built here, so the roster format is not this box's concern.

Accepted spec shapes:
    A mapping, or any object with the attributes. Field lookup falls back
    through attribute, then mapping key, then a nested ``extra`` mapping — which
    is what lets a config loader's own spec object carry consumer-defined keys
    like ``parallel_tool_calls`` without this module knowing the loader exists.

What it refuses to do:
    Guess. An agent with no instructions is built and loudly logged, not
    silently given a default persona; an agent whose model cannot be resolved
    raises. A misconfigured agent that starts anyway is worse than one that
    refuses, because it answers and the answer looks fine.
"""

from __future__ import annotations

import logging
from typing import Any

from ._config import FoundryConfig
from ._maf import bind_tools, build_compaction_strategy
from ._tools import DEFAULT_TOOL_MARKERS

logger = logging.getLogger(__name__)

# Sequential tool calls by default. Parallel calls interleave tool results in a
# non-deterministic order, which is fine for throughput and wrong for any agent
# whose output narrates its own steps. Opt in per agent, never globally.
_DEFAULT_PARALLEL_TOOL_CALLS = False

_MISSING = object()


def spec_field(spec: Any, key: str, default: Any = None) -> Any:
    """Read ``key`` from a spec of any accepted shape.

    Lookup order — attribute, mapping key, then ``extra`` mapping — is fixed so
    a key present in two places resolves the same way every time. Declared
    fields therefore always beat pass-through metadata of the same name.
    """
    value = getattr(spec, key, _MISSING)
    if value is not _MISSING:
        return value
    if isinstance(spec, dict) and key in spec:
        return spec[key]
    extra = getattr(spec, "extra", None)
    if extra is None and isinstance(spec, dict):
        extra = spec.get("extra")
    if isinstance(extra, dict) and key in extra:
        return extra[key]
    return default


def build_agent(
    spec: Any,
    client: Any,
    config: FoundryConfig,
    *,
    agent_id: str = "",
    model_override: str = "",
    middleware: Any | None = None,
    context_providers: Any | None = None,
    tokenizer: Any | None = None,
    token_budget: int = 0,
    markers: tuple[str, ...] = DEFAULT_TOOL_MARKERS,
) -> Any:
    """Build one SDK agent from a spec and a client.

    Args:
        spec: Mapping or object carrying ``name``, ``description``,
            ``instructions``, ``tools``, ``model``.
        client: The client this agent gets. Normally from ``ClientPool``.
        config: Supplies the default deployment and the ``"fast"`` alias.
        agent_id: Identifier for logs. Falls back to the spec's own.
        model_override: Wins over the spec's model. This is how the retry loop
            re-builds an agent against a fallback deployment.
        middleware: SDK middleware instances, e.g. from
            ``build_tracing_middleware()``.
        context_providers: SDK context providers, passed through untouched.
        tokenizer: Required for compaction. Without one, compaction is skipped
            and logged — a token budget cannot be enforced without a counter.
        token_budget: Context window minus response budget. ``0`` skips
            compaction.
        markers: Tool marker attribute names.

    Returns:
        The object returned by ``client.as_agent(...)``.

    Raises:
        ValueError: When the model cannot be resolved to a non-empty deployment.
    """
    resolved_id = agent_id or str(spec_field(spec, "agent_id", "") or "")
    name = str(spec_field(spec, "name", "") or resolved_id or "agent")
    description = str(spec_field(spec, "description", "") or "")
    instructions = str(spec_field(spec, "instructions", "") or "")

    if not instructions:
        # Not fatal: an agent whose behaviour is entirely tool-driven is legal.
        # Loud, because far more often this means a prompt file went missing.
        logger.warning(
            "foundry.agent.no_instructions: agent=%s — the model will answer "
            "with no system prompt", name,
        )

    requested_model = str(model_override or spec_field(spec, "model", "") or "")
    model = config.resolve_model(requested_model)
    if not model:
        raise ValueError(
            f"Agent {name!r}: no model deployment resolved. Set a 'model' on "
            f"the spec, or a model_deployment on FoundryConfig."
        )
    source = (
        "override" if model_override
        else "spec" if spec_field(spec, "model", "")
        else "config_default"
    )

    raw_tools = list(spec_field(spec, "tools", ()) or ())
    tools = bind_tools(raw_tools, client, markers=markers)

    parallel = bool(
        spec_field(spec, "parallel_tool_calls", _DEFAULT_PARALLEL_TOOL_CALLS)
    )

    agent = client.as_agent(
        name=name,
        description=description,
        instructions=instructions,
        # ``None``, not ``[]``: an empty list is a declaration that the agent has
        # tools, and some SDK versions then send an empty tool schema that the
        # service rejects (GOTCHAS.md G4).
        tools=tools or None,
        default_options={
            "allow_multiple_tool_calls": parallel,
            "model_id": model,
        },
        middleware=middleware,
        context_providers=list(context_providers or []) or None,
    )

    _attach_compaction(agent, spec, name, tokenizer, token_budget)

    logger.info(
        "foundry.agent.built: id=%s name=%s model=%s (source=%s) tools=%d "
        "instructions=%d chars",
        resolved_id or name, name, model, source, len(tools), len(instructions),
    )
    return agent


def _attach_compaction(
    agent: Any,
    spec: Any,
    name: str,
    tokenizer: Any | None,
    token_budget: int,
) -> None:
    """Attach a compaction strategy post-construction, unless opted out.

    Post-construction because ``as_agent`` has no parameter for it in the
    versions this was built against; the strategy is read off the agent by the
    run loop. An agent that already carries one is left alone so a caller can
    supply a different strategy without this function fighting it.
    """
    if not bool(spec_field(spec, "compaction", True)):
        logger.info("foundry.compaction.disabled: agent=%s (by spec)", name)
        return
    if token_budget <= 0 or tokenizer is None:
        return
    if getattr(agent, "_compaction_strategy", None):
        return
    strategy = build_compaction_strategy(token_budget, tokenizer)
    if strategy is not None:
        agent._compaction_strategy = strategy
        logger.info("foundry.compaction.attached: agent=%s", name)


__all__ = ["build_agent", "spec_field"]
