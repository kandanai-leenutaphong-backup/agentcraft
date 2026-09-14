"""Shared fixtures. Every test runs against fake discovery: no cloud, ever."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from azdata import AzureDataConfig

from resource_explorer_api.app import create_app
from resource_explorer_api.discovery import build_access
from resource_explorer_api.settings import Settings
from resource_explorer_api.tree import ExplorerService

COMPONENT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = COMPONENT_ROOT / "contracts" / "tree.schema.json"
SOURCE_ROOT = COMPONENT_ROOT / "backend" / "src"

PRINCIPAL = {"X-MS-CLIENT-PRINCIPAL-ID": "operator"}

#: The fixture estate's own names, so a test names a branch rather than an
#: index into a listing whose order is the implementation's to change.
GROUP = "rg-fixture"
LOCKED_GROUP = "rg-locked"
EMPTY_GROUP = "rg-empty"
STORAGE = "hcfixturestore"
STORAGE_TYPE = "Microsoft.Storage/storageAccounts"
COSMOS_TYPE = "Microsoft.DocumentDB/databaseAccounts"
SEARCH_TYPE = "Microsoft.Search/searchServices"
KUSTO_TYPE = "Microsoft.Kusto/clusters"
LOGS_TYPE = "Microsoft.OperationalInsights/workspaces"
ACR_TYPE = "Microsoft.ContainerRegistry/registries"
APP_TYPE = "Microsoft.App/containerApps"
VAULT_TYPE = "Microsoft.KeyVault/vaults"
IDENTITY_TYPE = "Microsoft.ManagedIdentity/userAssignedIdentities"


def make_settings(**overrides: Any) -> Settings:
    """Fixture-backed settings with a static dir that does not exist."""
    base: dict[str, Any] = {
        "azure": AzureDataConfig(subscription_id="fixture-subscription"),
        "fake_discovery": True,
        "static_dir": Path("/nonexistent-static"),
    }
    base.update(overrides)
    return Settings(**base)


def make_service(**overrides: Any) -> ExplorerService:
    settings = make_settings(**overrides)
    return ExplorerService(settings=settings, access=build_access(settings))


def client(app: Any) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://explorer.test"
    )


async def children(service: ExplorerService, node: str | None) -> dict[str, Any]:
    """Label -> child, so a test never depends on listing order."""
    response = await service.expand(node)
    return {child.label: child for child in response.children}


async def walk(service: ExplorerService, *labels: str) -> Any:
    """Follow labels from the root and return the last child reached."""
    node: str | None = None
    found: Any = None
    for label in labels:
        listing = await children(service, node)
        assert label in listing, f"{label!r} not in {sorted(listing)}"
        found = listing[label]
        node = found.id
    return found


async def resource_node(service: ExplorerService, group: str, resource_type: str, name: str) -> Any:
    """A resource, reached the way a user reaches it: group, type, name."""
    listing = await children(service, None)
    types = await children(service, listing[group].id)
    label = next(key for key in types if key.startswith(f"{resource_type} ("))
    resources = await children(service, types[label].id)
    return resources[name]


@pytest.fixture
def app() -> Any:
    return create_app(make_settings())


@pytest.fixture
def service() -> ExplorerService:
    return make_service()
