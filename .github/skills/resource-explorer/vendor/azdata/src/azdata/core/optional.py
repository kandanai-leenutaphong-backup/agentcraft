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
   exercised in ``tests/unit/selftest.py`` with no cloud account, no network,
   and no SDK installed. That is the only reason the selftest can honour
   R4 (runs with nothing but the standard library).

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
# grep, and a missing-dependency message can name the pin the deploy plane
# was written against instead of just the distribution.
KNOWN_DISTRIBUTIONS: dict[str, str] = {
    "azure.core.exceptions": "azure-core",
    "azure.cosmos.aio": "azure-cosmos>=4.5,<5",
    "azure.kusto.data": "azure-kusto-data>=4.3",
    "azure.mgmt.authorization": "azure-mgmt-authorization>=4",
    "azure.mgmt.cosmosdb": "azure-mgmt-cosmosdb>=10",
    "azure.mgmt.kusto": "azure-mgmt-kusto>=3.3",
    "azure.mgmt.monitor": "azure-mgmt-monitor>=6",
    "azure.mgmt.resource": "azure-mgmt-resource>=23",
    "azure.mgmt.resource.resources": "azure-mgmt-resource>=23",
    "azure.mgmt.search": "azure-mgmt-search>=9.1",
    "azure.search.documents": "azure-search-documents>=11.5",
    "azure.search.documents.indexes": "azure-search-documents>=11.5",
    "azure.search.documents.indexes.models": "azure-search-documents>=11.5",
    "certifi": "certifi>=2024.2.2",
    "gremlin_python.driver.client": "gremlinpython>=3.6",
    "gremlin_python.driver.serializer": "gremlinpython>=3.6",
    "httpx": "httpx>=0.27",
    # The TDS driver is pure Python, but its TLS is not: python-tds negotiates
    # encryption through pyOpenSSL and connects in the clear without it, which
    # Azure SQL refuses. The two are separate entries because they fail apart.
    "pytds": "python-tds>=1.16",
    "pytds.tls": "pyOpenSSL>=24",
    "sqlglot": "sqlglot>=25",
    "sqlglot.expressions": "sqlglot>=25",
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
        # azure-mgmt-kusto" installs a version whose model shape the
        # deploy plane may not handle, and the message should say so.
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
