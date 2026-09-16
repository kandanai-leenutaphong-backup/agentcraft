"""Optional imports with explicit missing-dependency diagnostics and no global overrides."""

from __future__ import annotations

import importlib
from typing import Any

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
    """Import ``module_path`` or report its required distribution.

    Args:
        module_path: Dotted path, e.g. ``"azure.kusto.data"``.
        dist: PyPI distribution that provides it, used in the error message.

    Raises:
        MissingDependency: The module is absent.
    """
    try:
        return importlib.import_module(module_path)
    except ImportError as exc:
        # The pin, when this package knows one: "pip install
        # azure-kusto-data" installs a version whose response shape the
        # content plane may not handle, and the message should say so.
        raise MissingDependency(
            module_path, KNOWN_DISTRIBUTIONS.get(module_path, dist)
        ) from exc


__all__ = [
    "KNOWN_DISTRIBUTIONS",
    "MissingDependency",
    "load",
]
