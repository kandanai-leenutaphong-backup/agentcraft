"""Canonical native Search reads and retained fixture-only schema/write helpers."""

from __future__ import annotations

from .client import SearchIndexClient
from .config import (
    DEFAULT_ENV_PREFIX,
    DEFAULT_SEARCH_API_VERSION,
    SEARCH_SCOPE,
    SearchConfig,
    SearchConfigError,
    valid_index_name,
)
from .schema import FieldSpec, IndexSpec, VectorSpec, render_index, safe_key
from .transport import SearchError, Transport
from .read import SearchReadClient

__all__ = [
    "DEFAULT_ENV_PREFIX",
    "DEFAULT_SEARCH_API_VERSION",
    "FieldSpec",
    "IndexSpec",
    "SEARCH_SCOPE",
    "SearchConfig",
    "SearchConfigError",
    "SearchError",
    "SearchIndexClient",
    "SearchReadClient",
    "Transport",
    "VectorSpec",
    "render_index",
    "safe_key",
    "valid_index_name",
]
