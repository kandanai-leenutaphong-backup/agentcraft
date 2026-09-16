"""tool — SDK-free decorator that marks a function agent-callable.

Module role:
    Stamps metadata on a function and returns it **unwrapped**. It binds to no
    agent SDK, imports nothing, and does not change how the function is called.
    The concrete SDK binding happens later, at agent-build time, in the
    consumer's factory.

Why not just use the SDK's decorator:
    Because then every tool module imports the SDK at module load. That makes
    tools untestable without it, makes the import graph fragile, and welds your
    tool library to one framework. A stamp keeps a tool a plain function: unit
    tests call it directly, and swapping SDKs is a change in one factory rather
    than in every tool file.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

_F = TypeVar("_F", bound=Callable[..., Any])

# Attribute name is namespaced so it cannot collide with an SDK's own marker.
TOOL_MARKER = "__agentconfig_tool__"


def tool(
    _fn: _F | None = None,
    *,
    description: str | None = None,
    approval_mode: str = "never_require",
    **metadata: Any,
) -> Any:
    """Mark a function as agent-callable. Usable bare or with arguments.

    Args:
        description: Overrides the docstring as the model-visible description.
            Leave unset and write a good docstring instead: it stays correct
            because the reader and the model see the same text.
        approval_mode: Passed through to SDKs that gate tool execution.
        **metadata: Arbitrary extra fields the consumer's factory may read.

    Returns:
        The original function, with a metadata dict attached. Not a wrapper —
        calling it directly in a test is unaffected.
    """

    def _stamp(fn: _F) -> _F:
        setattr(fn, TOOL_MARKER, {
            "description": description or (fn.__doc__ or "").strip(),
            "approval_mode": approval_mode,
            **metadata,
        })
        return fn

    return _stamp(_fn) if _fn is not None else _stamp


def is_tool(fn: Any) -> bool:
    """True when ``fn`` carries the marker."""
    return callable(fn) and hasattr(fn, TOOL_MARKER)


def tool_metadata(fn: Any) -> dict[str, Any]:
    """Return the stamped metadata, or an empty dict for an unstamped callable."""
    return dict(getattr(fn, TOOL_MARKER, {}) or {})
