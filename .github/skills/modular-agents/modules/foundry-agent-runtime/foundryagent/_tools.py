"""tool — mark a plain function agent-callable without importing an SDK.

Module role:
    Stamps metadata on a function and returns it **unwrapped**. The concrete SDK
    binding happens later, in :func:`foundryagent.bind_tools`, at agent-build
    time when the client is known.

Why a stamp instead of the SDK's own decorator:
    Decorating with the SDK at module load means every tool module imports the
    SDK, tools become untestable without it, and the schema for every tool in
    the process is built at import time — so one malformed annotation takes down
    every agent, not just the one that uses that tool. That failure is real and
    is GOTCHAS.md G5.

Interoperating with another marker:
    The marker is just an attribute name. A tool library that stamps a different
    attribute is bound by passing ``markers=("__their_marker__",)`` to
    ``bind_tools``. Nothing here needs to be the only stamp in the process.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

# Namespaced so it cannot collide with an SDK's own marker attribute.
TOOL_MARKER = "__agent_tool__"

# What ``bind_tools`` looks for when the caller does not say. A tuple rather
# than a single name so several tool libraries can coexist in one roster.
DEFAULT_TOOL_MARKERS: tuple[str, ...] = (TOOL_MARKER,)


def tool(
    _fn: _F | None = None,
    *,
    description: str | None = None,
    approval_mode: str = "never_require",
    **metadata: Any,
) -> Any:
    """Mark a function as agent-callable. Usable bare or with arguments.

    Args:
        description: Model-visible description. Leave unset and write a good
            docstring: the reader and the model then see the same text, so it
            cannot drift.
        approval_mode: Forwarded to the SDK at bind time. ``"never_require"``
            runs the tool without a human gate; SDKs that support approval
            accept their own values here.
        **metadata: Extra fields carried through to whatever reads the marker.

    Returns:
        The original function with a metadata dict attached — not a wrapper, so
        a unit test calls it directly and sees no indirection.
    """

    def _stamp(fn: _F) -> _F:
        setattr(fn, TOOL_MARKER, {
            "description": description or (fn.__doc__ or "").strip(),
            "approval_mode": approval_mode,
            **metadata,
        })
        return fn

    return _stamp(_fn) if _fn is not None else _stamp


def tool_metadata(fn: Any, markers: tuple[str, ...] = DEFAULT_TOOL_MARKERS) -> dict[str, Any] | None:
    """Return the stamped metadata for ``fn``, or ``None`` when unmarked.

    ``None`` and ``{}`` mean different things: unmarked, versus marked with no
    metadata. ``bind_tools`` binds the second and passes the first through.
    """
    for name in markers:
        marker = getattr(fn, name, None)
        if marker is not None:
            return dict(marker)
    return None


__all__ = ["tool", "tool_metadata", "TOOL_MARKER", "DEFAULT_TOOL_MARKERS"]
