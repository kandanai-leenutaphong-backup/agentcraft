"""Container registry browsing: repositories and tags, with an AAD identity."""

from __future__ import annotations

from azdata.registry.discover import (
    CATALOG_SCOPE,
    REPOSITORY_SCOPE,
    RegistryClient,
    RegistryDiscoverer,
)

__all__ = [
    "CATALOG_SCOPE",
    "REPOSITORY_SCOPE",
    "RegistryClient",
    "RegistryDiscoverer",
]
