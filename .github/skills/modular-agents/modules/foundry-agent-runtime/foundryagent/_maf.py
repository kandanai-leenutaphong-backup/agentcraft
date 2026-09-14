"""The Microsoft Agent Framework binding — every direct SDK touch, in one file.

Module role:
    Holds the four things the runtime needs from the SDK: recognising an SDK
    client, binding marked tools to it, building the context-compaction
    strategy, and building the tool-tracing middleware. Nothing else in this box
    imports the SDK.

Why isolated:
    Swapping the framework becomes a sibling module rather than a rewrite. The
    builder in ``_build.py`` calls ``as_agent`` and knows nothing else about the
    SDK; everything version-specific is here, where a version quirk can be
    documented next to the workaround it forced.

Graceful absence, deliberately asymmetric:
    Compaction and tracing return ``None`` / ``[]`` when the SDK is missing —
    the agent runs without them. Tool binding does not degrade: a tool that
    should have been bound and was not is an agent that silently cannot act, so
    the caller is told. The asymmetry is the point, and GOTCHAS.md G6 is what
    happens when it is not applied.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from ._optional import load_sdk, sdk_available
from ._tools import DEFAULT_TOOL_MARKERS, tool_metadata

logger = logging.getLogger(__name__)

# Truncation strategy limits: keep the last N messages, compacting to M when the
# budget is exceeded. Values carried from the deployment this was extracted
# from, where they held a multi-hour investigation session inside the window.
_TRUNCATION_MAX_N = 200
_TRUNCATION_COMPACT_TO = 100

# Only this many characters of an exception reach the trace log. A tool failure
# can carry an entire response body; logging it whole turns an error line into a
# log-ingestion cost and can leak payload content into an observability sink.
_TRACE_ERROR_CHARS = 200


def maf_available() -> bool:
    """True when the Agent Framework can be imported."""
    return sdk_available("agent_framework")


def is_maf_client(client: Any) -> bool:
    """True when ``client`` is an Agent Framework client.

    Decided by the top-level package of the client's defining module rather than
    by ``isinstance``. Importing the class to compare against would defeat the
    lazy-import property of the whole box, and the check must also be correct
    for a stub client that deliberately mimics the interface.
    """
    return type(client).__module__.split(".", 1)[0] == "agent_framework"


def bind_tools(
    tools: Any,
    client: Any,
    *,
    markers: tuple[str, ...] = DEFAULT_TOOL_MARKERS,
) -> list:
    """Bind marked callables to the concrete SDK, preserving order.

    Args:
        tools: Iterable of resolved callables and/or already-SDK tool objects.
        client: The client the agent is being built on.
        markers: Attribute names that identify a marked tool.

    Returns:
        A new list. For an SDK client, marked callables are wrapped with the
        SDK's own tool decorator and everything else passes through untouched —
        an already-decorated tool or a hosted platform-tool object must not be
        wrapped twice. For a non-SDK client the markers are inert and the raw
        callables are returned, which is what makes an in-memory stub client
        work with the same roster.

    Order is preserved because some SDKs present tools to the model in list
    order, which makes the roster's order a behavioural input rather than a
    formatting detail (GOTCHAS.md G7).
    """
    resolved = list(tools)
    if not is_maf_client(client):
        return resolved

    # Lazy: reached only when the SDK is genuinely the active client.
    framework = load_sdk("agent_framework")
    sdk_tool = framework.tool

    bound: list = []
    for fn in resolved:
        marker = tool_metadata(fn, markers)
        if marker is None:
            bound.append(fn)
            continue
        approval_mode = marker.get("approval_mode", "never_require")
        bound.append(sdk_tool(approval_mode=approval_mode)(fn))
    return bound


def build_compaction_strategy(token_budget: int, tokenizer: Any) -> Any | None:
    """Build the composed context-compaction strategy.

    Composed of two strategies in a deliberate order: tool results are compacted
    first because they are the largest and least re-read content in an agent
    transcript, and only then is the message history truncated. Reversing the
    order truncates away messages while a single oversized tool result still
    dominates the window.

    Args:
        token_budget: Context window minus the response budget. Not the window.
        tokenizer: Any object exposing ``count_tokens``.

    Returns:
        The strategy, or ``None`` when the SDK is absent — the caller then
        attaches nothing and the agent runs uncompacted.
    """
    if not maf_available():
        logger.warning(
            "foundry.compaction.unavailable: SDK not installed — agent will run "
            "without compaction and will fail once the window fills"
        )
        return None

    framework = load_sdk("agent_framework")
    try:
        composed = framework.TokenBudgetComposedStrategy
        tool_result = framework.ToolResultCompactionStrategy
        truncation = framework.TruncationStrategy
    except AttributeError as exc:
        # A version that moved or renamed the strategies. Degrading is correct;
        # crashing the boot over an optional optimisation is not.
        logger.warning("foundry.compaction.unavailable: %s", exc)
        return None

    strategy = composed(
        strategies=[
            tool_result(),
            truncation(
                max_n=_TRUNCATION_MAX_N,
                compact_to=_TRUNCATION_COMPACT_TO,
                tokenizer=tokenizer,
            ),
        ],
        token_budget=token_budget,
        tokenizer=tokenizer,
    )
    logger.info("foundry.compaction.created: budget=%d tokens", token_budget)
    return strategy


def build_tracing_middleware(on_event: Any | None = None) -> list:
    """Build the tool-tracing middleware pipeline.

    Args:
        on_event: Optional ``callable(event: dict) -> None`` receiving one dict
            per tool invocation (``tool``, ``duration_ms``, ``ok``, and ``error``
            when it failed). The seam for pushing traces at a metrics sink
            without this module importing one.

    Returns:
        A one-element list, or ``[]`` when the SDK is absent.

    The middleware is purely observational: it times the call, records the
    outcome, and **re-raises**. A middleware that swallows is a tool failure the
    agent never learns about, which it then reports as a successful answer
    (GOTCHAS.md G9).
    """
    if not maf_available():
        logger.warning("foundry.middleware.unavailable: SDK not installed")
        return []

    framework = load_sdk("agent_framework")
    try:
        base = framework.FunctionMiddleware
    except AttributeError as exc:
        logger.warning("foundry.middleware.unavailable: %s", exc)
        return []

    class ToolTracingMiddleware(base):  # type: ignore[misc,valid-type]
        """Times every tool invocation and records name, duration and outcome."""

        async def process(self, context: Any, call_next: Any) -> None:
            tool_name = getattr(getattr(context, "function", None), "name", "unknown")
            started = time.monotonic()
            try:
                await call_next()
            except Exception as exc:
                duration_ms = round((time.monotonic() - started) * 1000, 1)
                logger.warning(
                    "foundry.tool.error: tool=%s duration_ms=%s error=%s",
                    tool_name, duration_ms, str(exc)[:_TRACE_ERROR_CHARS],
                )
                _emit(on_event, {
                    "tool": tool_name,
                    "duration_ms": duration_ms,
                    "ok": False,
                    "error": str(exc)[:_TRACE_ERROR_CHARS],
                })
                raise
            duration_ms = round((time.monotonic() - started) * 1000, 1)
            logger.info(
                "foundry.tool.complete: tool=%s duration_ms=%s",
                tool_name, duration_ms,
            )
            _emit(on_event, {
                "tool": tool_name, "duration_ms": duration_ms, "ok": True,
            })

    logger.info("foundry.middleware.created: tool tracing enabled")
    return [ToolTracingMiddleware()]


def _emit(on_event: Any | None, event: dict) -> None:
    """Deliver a trace event, never letting the sink break the tool call."""
    if on_event is None:
        return
    try:
        on_event(event)
    except Exception:
        # An observability sink must not be able to fail a tool invocation.
        logger.exception("foundry.trace.sink_failed")


__all__ = [
    "maf_available",
    "is_maf_client",
    "bind_tools",
    "build_compaction_strategy",
    "build_tracing_middleware",
]
