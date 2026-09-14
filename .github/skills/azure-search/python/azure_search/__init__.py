"""Azure AI Search CRUD: indexes and documents, over Entra ID.

Every call is REST over the standard library against a pinned API version. There
is no search SDK dependency and no admin key, query key, or connection string
anywhere in the path.

Patterned on ``reference_skills/harness/data/azure-ai-search-management``; see
its ``CONTRACT.md`` for the request shapes and ``GOTCHAS.md`` for the failure
modes the retry, 207 handling, and name validation here exist to survive.
"""

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
    "Transport",
    "VectorSpec",
    "render_index",
    "safe_key",
    "valid_index_name",
]
