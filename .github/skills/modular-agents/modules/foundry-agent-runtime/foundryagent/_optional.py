"""Lazy SDK loading, with a substitution seam so the box is testable offline.

Module role:
    Every import of the Microsoft Agent Framework and of ``azure.identity``
    passes through here. Two consequences that matter:

    1. Importing this box costs nothing. Neither SDK is imported at module load,
       so a process that wires Foundry for one agent and an in-memory stub for
       another does not pay for a package it never calls.
    2. The import can be substituted. ``set_sdk(...)`` lets the selftest drive
       the full construction path against fakes — the code under test is the
       code that ships, not a parallel branch guarded by ``if TESTING``.

Failure message design:
    A missing SDK raises with the exact pip install line. The alternative is a
    bare ``ModuleNotFoundError: agent_framework`` that tells a first-time
    consumer nothing about which extra provides it.
"""

from __future__ import annotations

import importlib
from typing import Any

# Import path -> the pip line that provides it. Keeping the mapping here means
# a new SDK dependency cannot be added without also stating how to install it.
_INSTALL_HINTS: dict[str, str] = {
    "agent_framework": (
        "the Microsoft Agent Framework is not installed. "
        "Install it with: pip install agent-framework"
    ),
    "agent_framework.azure": (
        "the Microsoft Agent Framework Azure bindings are not installed. "
        "Install them with: pip install 'agent-framework[azure]'"
    ),
    "azure.identity": (
        "azure-identity is not installed, and it is what mints the token for "
        "the Foundry endpoint. Install it with: pip install azure-identity "
        "— or pass an explicit credential= and skip it entirely."
    ),
}

# Substituted modules, by import path. Empty in production.
_OVERRIDES: dict[str, Any] = {}

# Marks a path as absent even when it is installed. Without it, the graceful-
# degradation paths are untestable on any machine that happens to have the SDK.
_ABSENT = object()


class SdkUnavailable(ImportError):
    """Raised when a required SDK is absent, carrying the install line.

    Subclasses ``ImportError`` so existing ``except ImportError`` handlers —
    including the graceful-degradation paths in this box — keep working.
    """


def set_sdk(path: str, module: Any) -> None:
    """Substitute the module returned for ``path``.

    Args:
        path: Import path, e.g. ``"agent_framework"``.
        module: Any object exposing the attributes the box reads. A
            ``types.SimpleNamespace`` is sufficient.
    """
    _OVERRIDES[path] = module


def clear_sdks() -> None:
    """Drop every substitution. Call in test teardown."""
    _OVERRIDES.clear()


def set_sdk_absent(path: str) -> None:
    """Force ``path`` to behave as if it were not installed.

    Exists so the degradation paths — compaction and tracing returning nothing —
    can be asserted on a machine where the SDK *is* installed. Without it those
    branches are exercised only by accident, on whichever runner happens to lack
    the package.
    """
    _OVERRIDES[path] = _ABSENT


def sdk_available(path: str) -> bool:
    """True when ``path`` can be loaded — substituted or genuinely installed.

    Never raises, so it is safe to call during a health check.
    """
    if path in _OVERRIDES:
        return _OVERRIDES[path] is not _ABSENT
    try:
        importlib.import_module(path)
    except ImportError:
        return False
    return True


def load_sdk(path: str) -> Any:
    """Import ``path`` and return the module, or raise :class:`SdkUnavailable`.

    Raises:
        SdkUnavailable: When the module is absent. The message is the install
            hint registered for that path, so the caller can self-serve.
    """
    override = _OVERRIDES.get(path)
    if override is _ABSENT:
        raise SdkUnavailable(_hint(path))
    if override is not None:
        return override
    try:
        return importlib.import_module(path)
    except ImportError as exc:
        raise SdkUnavailable(_hint(path)) from exc


def _hint(path: str) -> str:
    """The install line for ``path``, or a generic message when none is set."""
    return _INSTALL_HINTS.get(path, f"required module {path!r} is not installed")


__all__ = [
    "SdkUnavailable", "load_sdk", "sdk_available", "set_sdk", "set_sdk_absent",
    "clear_sdks",
]
