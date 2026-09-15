"""Optional-SDK loader — the one place a vendor SDK enters this package.

WHY THIS EXISTS
---------------
Each connector needs a different Azure SDK, and almost no consumer needs
all of them. If the SDKs were imported at module scope, installing the box
would mean installing five client libraries to use one, and importing the
box would fail outright when any of them were absent.

Routing every vendor import through ``load()`` buys three things:

1. **Install what you use.** ``requirements.txt`` declares the full
   surface; the base import path touches none of it.
2. **A legible failure.** A missing SDK raises :class:`MissingDependency`
   naming the distribution and the pip command, instead of an
   ``ImportError`` from three frames down inside a retry loop.
3. **A test seam.** ``override()`` substitutes a fake module for a dotted
   path, so every retry, backoff and breaker path in this package is
   exercised with no cloud account, no network, and no SDK installed.

PUBLIC SURFACE
--------------
``load``              — import a dotted module path or raise MissingDependency.
``override``          — install a fake module for a path (tests only).
``clear_overrides``   — drop all fakes; call in test teardown.
``MissingDependency`` — raised when the real SDK is absent.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import importlib
from typing import Any

# Dotted module path -> substitute module object. Empty in production.
_overrides: dict[str, Any] = {}

# Substituting a module proves the present case; only this sentinel proves the
# absent one, which is otherwise decided by whatever happens to be installed.
_MISSING = object()

# Dotted module path -> the distribution and version pin that provides it.
# Every ``load()`` call site in this package appears here, so the set of
# vendor SDKs the package can possibly reach is one list rather than a
# grep, and a missing-dependency message can name the pin this package was
# written against instead of just the distribution.
KNOWN_DISTRIBUTIONS: dict[str, str] = {
    "azure.core.exceptions": "azure-core",
    "azure.kusto.data": "azure-kusto-data>=4.3",
    "azure.search.documents": "azure-search-documents>=11.5",
}


class MissingDependency(RuntimeError):
    """A connector was used without its SDK installed.

    Carries the distribution name so the message can tell the operator
    exactly what to install rather than what failed to import.
    """

    def __init__(self, module_path: str, dist: str) -> None:
        self.module_path = module_path
        self.dist = dist
        super().__init__(
            f"{module_path} is not installed. This connector needs the "
            f"'{dist}' distribution: pip install {dist}"
        )


def load(module_path: str, *, dist: str) -> Any:
    """Import ``module_path``, honouring test overrides.

    Args:
        module_path: Dotted path, e.g. ``"azure.kusto.data"``.
        dist: PyPI distribution that provides it, used in the error message.

    Raises:
        MissingDependency: The module is absent and no override is installed.
    """
    if module_path in _overrides:
        substitute = _overrides[module_path]
        if substitute is _MISSING:
            raise MissingDependency(
                module_path, KNOWN_DISTRIBUTIONS.get(module_path, dist)
            )
        return substitute
    try:
        return importlib.import_module(module_path)
    except ImportError as exc:
        # The pin, when this package knows one: "pip install
        # azure-kusto-data" installs a version whose response shape the
        # content plane may not handle, and the message should say so.
        raise MissingDependency(
            module_path, KNOWN_DISTRIBUTIONS.get(module_path, dist)
        ) from exc


def override(module_path: str, module: Any) -> None:
    """Substitute ``module`` for ``module_path``. Tests only."""
    _overrides[module_path] = module


def override_missing(module_path: str) -> None:
    """Force ``module_path`` to look uninstalled. Tests only.

    A test that asserts the missing-SDK path must not depend on the SDK
    genuinely being absent from the environment: installing it silently
    converts that test into a live network call.
    """
    _overrides[module_path] = _MISSING


def clear_overrides() -> None:
    """Remove every substitution installed by :func:`override`."""
    _overrides.clear()


__all__ = [
    "KNOWN_DISTRIBUTIONS",
    "MissingDependency",
    "clear_overrides",
    "load",
    "override_missing",
    "override",
]
