"""The use-case data inventory, composed for this deployment.

`manifest.py` reads `control/data_inventory.yaml` and resolves its coordinates
against the environment. `probes.py` binds each declared connector to the code
that actually reads it. This module puts the two together and hands the result
to the domain-blind component in `app/components/resource_explorer`.

Composition happens here and nowhere deeper: the component learns what exists
by being given a registry, never by reading a file or an environment variable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.components.resource_explorer import InventoryRegistry, InventoryService

from .manifest import MANIFEST_PATH, ManifestError, load_registry
from .probes import default_probes


def build_service(registry: InventoryRegistry | None = None, *, probes: Mapping[str, Any] | None = None) -> InventoryService:
    """The inventory service this deployment serves. Reads no network at build."""
    return InventoryService(registry or load_registry(), default_probes() if probes is None else probes)


__all__ = [
    "MANIFEST_PATH",
    "ManifestError",
    "build_service",
    "default_probes",
    "load_registry",
]
