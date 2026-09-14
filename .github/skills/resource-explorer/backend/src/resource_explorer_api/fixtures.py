"""A whole fixture subscription — every node kind, every status, no network.

WHY THIS IS PRODUCTION CODE AND NOT A TEST HELPER
-------------------------------------------------
The frontend dev server, Playwright, the backend suite and a local `uvicorn`
run all need the same estate, and an estate that only exists inside `pytest`
cannot be walked by a human. It ships in the package, behind
``RESOURCE_EXPLORER_FAKE_DISCOVERY=1``, and every response it produces is
stamped ``fixtures: true``.

WHAT IT COVERS, DELIBERATELY
----------------------------
Every node kind the wire contract declares, and one branch per outcome —
because a fixture estate where everything works proves only the happy path:

* ``ok``           — the resource groups, and most branches below them
* ``empty``        — a resource group with nothing in it, and an empty index
* ``truncated``    — an index with 501 fields against a 500 clamp
* ``forbidden``    — one Cosmos account
* ``unreachable``  — one storage account, the network-blocked case
* ``unconfigured`` — one Kusto cluster
* ``unavailable``  — one Search service whose SDK is "missing"

Contents cover every rendering the client must implement: markdown, JSON,
CSV, plain text, a real viewable PNG, an undecodable binary, ARM property
JSON, and four kinds of row sample.

``nested/deep/file.txt`` exists because blob storage is flat: it is one blob
whose name contains slashes, and the tree has to synthesise two folders from
it. A fixture set without a nested blob would not exercise the one piece of
blob logic that is not a listing.

Fixtures satisfy both planes' invariants by construction: they go through the
same :func:`bounded_discovery` and :func:`bounded_content` wrappers the real
implementations use, so ordering, truncation and the ``ok``/``empty``
distinction are the shared implementation and not a second one that can
drift.
"""

from __future__ import annotations

import json
import struct
import zlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from azdata import (
    ContentBounds,
    ContentPayload,
    ContentResult,
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryResult,
    DiscoveryScope,
    DiscovererRegistry,
    bounded_content,
    bounded_discovery,
    content_failure,
    discovery_failure,
    normalize_rows,
)

SUBSCRIPTION = "fixture-subscription"

#: The name that breaks every delimiter-joined id scheme.
AWKWARD_INDEX = "assets/v1: beta"

#: More items than the clamp, so truncation is observable end to end.
LARGE_INDEX = "hc-large"
LARGE_INDEX_FIELDS = 501
EMPTY_INDEX = "hc-empty"
PRIMARY_INDEX = "azdata-assets"

DEMO_CONTAINER = "explorer-demo"

#: Repository names with a slash in them, which is what makes a registry
#: listing a real test of the node codec.
REPOSITORIES: tuple[str, ...] = ("explorer/api", "explorer/deps")


def resource_id(group: str, resource_type: str, name: str) -> str:
    return (
        f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{group}"
        f"/providers/{resource_type}/{name}"
    )


def _png(width: int, height: int, colour: tuple[int, int, int]) -> bytes:
    """A real, viewable PNG. Built rather than embedded so it cannot rot."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        raw = tag + data
        return (
            struct.pack(">I", len(data))
            + raw
            + struct.pack(">I", zlib.crc32(raw) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    rows = b"".join(b"\x00" + bytes(colour) * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


DEPTH_MARKER = (
    "Depth marker: this blob is named nested/deep/file.txt, which is one "
    "flat name, not two folders.\n"
)

#: ``blob name -> (bytes, content type)``. A flat map, exactly as the service
#: holds it; the folder hierarchy is synthesised from the names.
DEMO_BLOBS: dict[str, tuple[bytes, str]] = {
    "README.md": (
        b"# Explorer fixture container\n\n"
        b"Seven blobs, one of them nested two levels deep.\n",
        "text/markdown",
    ),
    "config.json": (
        json.dumps({"retries": 3, "region": "eastus", "enabled": True}, indent=2).encode(
            "utf-8"
        ),
        "application/json",
    ),
    "metrics.csv": (
        b"day,requests,errors\n2026-08-29,1204,3\n2026-08-30,1187,0\n",
        "text/csv",
    ),
    "diagram.png": (_png(16, 16, (32, 96, 160)), "image/png"),
    "notes.txt": (b"Plain text, no header, nothing clever.\n", "text/plain"),
    "payload.bin": (bytes(range(256)) * 4, "application/octet-stream"),
    "nested/deep/file.txt": (DEPTH_MARKER.encode("utf-8"), "text/plain"),
    "nested/deep/manifest.json": (
        json.dumps({"depth": 2, "parent": "nested/deep"}, indent=2).encode("utf-8"),
        "application/json",
    ),
}

ROWS_BY_KIND: dict[str, list[dict[str, Any]]] = {
    "documents": [
        {"id": "1", "name": "first", "tags": "alpha,beta"},
        {"id": "2", "name": "second", "tags": "gamma"},
    ],
    "search": [
        {"id": "a1", "title": "Fixture asset", "@search.score": 1.0},
        {"id": "a2", "title": "Second asset", "@search.score": 0.8},
    ],
    "rows": [
        {"Timestamp": "2026-08-30T09:00:00Z", "Level": "Info", "Message": "started"},
        {"Timestamp": "2026-08-30T09:00:05Z", "Level": "Warning", "Message": "slow"},
    ],
}


# ----------------------------------------------------------------------
# The estate.
# ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class FixtureResource:
    name: str
    type: str
    group: str
    location: str = "eastus"
    kind: str | None = None
    sku: str | None = None

    @property
    def id(self) -> str:
        return resource_id(self.group, self.type, self.name)


GROUPS: tuple[tuple[str, str, int], ...] = (
    ("rg-fixture", "eastus", 9),
    ("rg-locked", "westus", 1),
    ("rg-empty", "eastus", 0),
)

RESOURCES: tuple[FixtureResource, ...] = (
    FixtureResource("hcfixturestore", "Microsoft.Storage/storageAccounts", "rg-fixture", kind="StorageV2", sku="Standard_LRS"),
    FixtureResource("cosmos-fixture", "Microsoft.DocumentDB/databaseAccounts", "rg-fixture", kind="GlobalDocumentDB"),
    FixtureResource("cosmos-forbidden", "Microsoft.DocumentDB/databaseAccounts", "rg-fixture"),
    FixtureResource("srch-fixture", "Microsoft.Search/searchServices", "rg-fixture", sku="standard"),
    FixtureResource("srch-broken", "Microsoft.Search/searchServices", "rg-fixture"),
    FixtureResource("adx-fixture", "Microsoft.Kusto/clusters", "rg-fixture"),
    FixtureResource("adx-unconfigured", "Microsoft.Kusto/clusters", "rg-fixture"),
    FixtureResource("log-fixture", "Microsoft.OperationalInsights/workspaces", "rg-fixture"),
    FixtureResource("acrfixture", "Microsoft.ContainerRegistry/registries", "rg-fixture", sku="Basic"),
    FixtureResource("app-fixture", "Microsoft.App/containerApps", "rg-fixture"),
    FixtureResource("kv-fixture", "Microsoft.KeyVault/vaults", "rg-fixture"),
    FixtureResource("id-fixture", "Microsoft.ManagedIdentity/userAssignedIdentities", "rg-fixture"),
    FixtureResource("stlockedfixture", "Microsoft.Storage/storageAccounts", "rg-locked", kind="StorageV2"),
)

#: ARM child collections the fixture answers, keyed by ``(resource, collection)``.
ARM_CHILDREN: dict[tuple[str, str], tuple[dict[str, Any], ...]] = {
    ("app-fixture", "revisions"): (
        {"name": "app-fixture--rev1", "properties": {"active": True, "trafficWeight": 100, "runningState": "Running"}},
        {"name": "app-fixture--rev2", "properties": {"active": False, "trafficWeight": 0, "runningState": "Stopped"}},
    ),
    ("app-fixture--rev1", "replicas"): (
        {"name": "app-fixture--rev1-abc", "properties": {"runningState": "Running"}},
    ),
    ("kv-fixture", "secrets"): (
        {"name": "storage-connection", "properties": {"enabled": True}},
        {"name": "signing-key-name", "properties": {"enabled": True}},
    ),
    ("kv-fixture", "keys"): (),
    ("hcfixturestore", "tableServices/default/tables"): (
        {"name": "auditlog", "properties": {}},
    ),
    ("hcfixturestore", "queueServices/default/queues"): (),
    ("hcfixturestore", "fileServices/default/shares"): (),
}

#: A branch that answers with a status instead of children, keyed by the
#: resource name it hangs off.
DARK_BRANCHES: dict[str, tuple[str, str]] = {
    "stlockedfixture": (
        "unreachable",
        "ServiceRequestError: public network access is disabled for this account",
    ),
    "cosmos-forbidden": (
        "forbidden",
        "the app identity lacks Cosmos DB Account Reader on the account",
    ),
    "adx-unconfigured": ("unconfigured", "the cluster declares no query URI"),
    "srch-broken": (
        "unavailable",
        "azure-search-documents is not installed",
    ),
}


def _resource_by_name(name: str) -> FixtureResource | None:
    return next((item for item in RESOURCES if item.name == name), None)


def _name_from_id(value: str) -> str:
    parts = [part for part in str(value).split("/") if part]
    return parts[-1] if parts else ""


def _dark(resource_name: str) -> tuple[str, str] | None:
    return DARK_BRANCHES.get(resource_name)


# ----------------------------------------------------------------------
# Discoverers.
# ----------------------------------------------------------------------


Answer = tuple[str, str] | Iterable[DiscoveryNode]

#: A table is handed the whole scope, not just the path, because the real
#: planes are addressed differently — blob and search by endpoint, Cosmos and
#: Kusto by account name — and a fixture that stored the account in a module
#: global would race between two concurrent expansions.
Table = Callable[[str, tuple[str, ...], DiscoveryScope], Answer]


@dataclass
class FixtureDiscoverer:
    """A discoverer whose estate is a table. Implements the same protocol."""

    service: str
    levels: tuple[str, ...]
    child_levels: Mapping[str, str | None]
    table: Table
    calls: list[tuple[str, tuple[str, ...]]] = field(default_factory=list)

    def child_level(self, level: str) -> str | None:
        return self.child_levels.get(level)

    async def discover(
        self,
        level: str,
        scope: DiscoveryScope,
        *,
        bounds: DiscoveryBounds = DiscoveryBounds(),
    ) -> DiscoveryResult:
        self.calls.append((level, tuple(scope.path)))
        if level not in self.levels:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unavailable",
                detail=f"unknown level {level}",
            )
        answer = self.table(level, tuple(scope.path), scope)
        if isinstance(answer, tuple) and len(answer) == 2 and isinstance(answer[0], str):
            status, detail = answer
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status=status,  # type: ignore[arg-type]
                detail=detail,
            )
        nodes = list(answer)  # type: ignore[arg-type]
        return await bounded_discovery(
            service=self.service,
            level=level,
            scope=scope,
            bounds=bounds,
            collect=lambda: nodes,
        )


def _host_label(endpoint: str) -> str:
    host = str(endpoint or "").split("://", 1)[-1].split("/", 1)[0]
    return host.split(".", 1)[0] if host else ""


def _estate_table(level: str, path: tuple[str, ...], scope: DiscoveryScope) -> Answer:
    if level == "subscription":
        return [
            DiscoveryNode(
                kind="resource_group",
                name=name,
                path=(name,),
                has_children=True,
                attributes={
                    "id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{name}",
                    "location": location,
                    "resources": count,
                },
            )
            for name, location, count in GROUPS
        ]
    if level == "resource_group":
        group = path[0] if path else ""
        return [
            DiscoveryNode(
                kind="resource",
                name=item.name,
                path=(item.id,),
                has_children=True,
                attributes={
                    "id": item.id,
                    "type": item.type,
                    "location": item.location,
                    "kind": item.kind,
                    "sku": item.sku,
                },
            )
            for item in RESOURCES
            if item.group == group
        ]
    parent = _name_from_id(path[0] if path else "")
    collection = path[1] if len(path) > 1 else ""
    items = ARM_CHILDREN.get((parent, collection))
    if items is None:
        return ("unavailable", f"provider declares no collection '{collection}'")
    return [
        DiscoveryNode(
            kind="arm_child",
            name=str(item["name"]),
            path=(path[0], collection, str(item["name"])),
            has_children=False,
            attributes={
                "id": f"{path[0]}/{collection}/{item['name']}",
                "collection": collection,
                **{
                    key: value
                    for key, value in (item.get("properties") or {}).items()
                    if isinstance(value, (str, int, float, bool))
                },
            },
        )
        for item in items
    ]


def _blob_entries(container: str, prefix: str) -> list[DiscoveryNode]:
    """One prefix level, exactly as ``walk_blobs`` with a ``/`` delimiter."""
    folders: set[str] = set()
    nodes: list[DiscoveryNode] = []
    for name, (data, content_type) in DEMO_BLOBS.items():
        if not name.startswith(prefix):
            continue
        leaf = name[len(prefix) :]
        head, slash, _ = leaf.partition("/")
        if slash:
            folders.add(head)
            continue
        nodes.append(
            DiscoveryNode(
                kind="blob",
                name=leaf,
                path=(container, name),
                has_children=False,
                attributes={
                    "blob": name,
                    "size": len(data),
                    "contentType": content_type,
                    "blobType": "BlockBlob",
                },
            )
        )
    nodes.extend(
        DiscoveryNode(
            kind="blob_folder",
            name=folder,
            path=(container, f"{prefix}{folder}/"),
            has_children=True,
            attributes={"prefix": f"{prefix}{folder}/"},
        )
        for folder in sorted(folders)
    )
    return nodes


def _blob_table(level: str, path: tuple[str, ...], scope: DiscoveryScope) -> Answer:
    dark = _dark(scope.account_name or _host_label(scope.endpoint))
    if dark:
        return dark
    if level == "account":
        return [
            DiscoveryNode(
                kind="blob_container",
                name=name,
                path=(name, ""),
                has_children=True,
                attributes={"publicAccess": None, "deleted": False},
            )
            for name in (DEMO_CONTAINER, AWKWARD_INDEX)
        ]
    container = path[0] if path else ""
    prefix = path[1] if len(path) > 1 else ""
    if container != DEMO_CONTAINER:
        return []
    return _blob_entries(container, prefix)


def _cosmos_table(level: str, path: tuple[str, ...], scope: DiscoveryScope) -> Answer:
    dark = _dark(scope.account_name or _host_label(scope.endpoint))
    if dark:
        return dark
    if level == "account":
        return [
            DiscoveryNode(kind="cosmos_database", name="hcdb", path=("hcdb",), has_children=True, attributes={"id": "hcdb"}),
        ]
    return [
        DiscoveryNode(
            kind="cosmos_container",
            name=name,
            path=(*path, name),
            has_children=False,
            attributes={"partition_key_paths": "/id", "default_ttl": None},
        )
        for name in ("items", "empty-container")
    ]


def _gremlin_table(level: str, path: tuple[str, ...], scope: DiscoveryScope) -> Answer:
    dark = _dark(scope.account_name or _host_label(scope.endpoint))
    if dark:
        return dark
    if level == "account":
        return [
            DiscoveryNode(kind="gremlin_database", name="graphdb", path=("graphdb",), has_children=True, attributes={"id": "graphdb"})
        ]
    return [
        DiscoveryNode(
            kind="gremlin_graph",
            name="people",
            path=(*path, "people"),
            has_children=False,
            attributes={"partition_key_paths": "/pk"},
        )
    ]


def _search_table(level: str, path: tuple[str, ...], scope: DiscoveryScope) -> Answer:
    dark = _dark(_host_label(scope.endpoint) or scope.account_name)
    if dark:
        return dark
    if level == "service":
        return [
            DiscoveryNode(kind="search_index", name=name, path=(name,), has_children=True, attributes={"name": name})
            for name in (PRIMARY_INDEX, AWKWARD_INDEX, EMPTY_INDEX, LARGE_INDEX)
        ]
    index = path[0] if path else ""
    if index == EMPTY_INDEX:
        return []
    if index == LARGE_INDEX:
        return [
            DiscoveryNode(
                kind="search_field",
                name=f"f{position:04d}",
                path=(index, f"f{position:04d}"),
                has_children=False,
                attributes={"type": "Edm.String"},
            )
            for position in range(LARGE_INDEX_FIELDS)
        ]
    return [
        DiscoveryNode(
            kind="search_field",
            name=name,
            path=(index, name),
            has_children=False,
            attributes={"type": field_type, "key": name == "id", "searchable": True},
        )
        for name, field_type in (
            ("id", "Edm.String"),
            ("title", "Edm.String"),
            ("body/summary", "Edm.String"),
            ("updated", "Edm.DateTimeOffset"),
        )
    ]


def _kusto_table(level: str, path: tuple[str, ...], scope: DiscoveryScope) -> Answer:
    dark = _dark(scope.account_name or _host_label(scope.endpoint))
    if dark:
        return dark
    if level == "cluster":
        return [
            DiscoveryNode(kind="kusto_database", name="telemetry", path=("telemetry",), has_children=True, attributes={"hot_cache_period": "P7D"})
        ]
    return [
        DiscoveryNode(
            kind="kusto_table",
            name=name,
            path=(*path, name),
            has_children=False,
            attributes={"folder": "fixture"},
        )
        for name in ("Events", "Heartbeat")
    ]


def _logs_table(level: str, path: tuple[str, ...], scope: DiscoveryScope) -> Answer:
    return [
        DiscoveryNode(
            kind="log_table",
            name=name,
            path=(path[0] if path else "", name),
            has_children=False,
            attributes={"plan": "Analytics", "retentionInDays": 30},
        )
        for name in ("AppTraces", "ContainerAppConsoleLogs")
    ]


def _acr_table(level: str, path: tuple[str, ...], scope: DiscoveryScope) -> Answer:
    login_server = path[0] if path else ""
    if level == "registry":
        return [
            DiscoveryNode(
                kind="registry_repository",
                name=name,
                path=(login_server, name),
                has_children=True,
                attributes={"repository": name},
            )
            for name in REPOSITORIES
        ]
    repository = path[1] if len(path) > 1 else ""
    return [
        DiscoveryNode(
            kind="registry_tag",
            name=name,
            path=(login_server, repository, name),
            has_children=False,
            attributes={"digest": f"sha256:{name}", "signed": False},
        )
        for name in ("latest", "v1")
    ]


# ----------------------------------------------------------------------
# Readers.
# ----------------------------------------------------------------------


class FixtureProperties:
    """The ARM document of any fixture resource, plus estate search."""

    async def properties(
        self, resource_id_value: str, *, bounds: ContentBounds = ContentBounds()
    ) -> ContentResult:
        if not resource_id_value:
            return content_failure(
                service="estate",
                kind="properties",
                status="unconfigured",
                detail="properties read not configured: resource id",
            )
        name = _name_from_id(resource_id_value)
        item = _resource_by_name(name)
        document = {
            "id": resource_id_value,
            "name": name,
            "type": item.type if item else "",
            "location": item.location if item else "eastus",
            "properties": {
                "provisioningState": "Succeeded",
                "primaryKey": "(redacted)",
                "note": "Fixture ARM document. Every real field is a live read.",
            },
            "tags": {"owner": "fixtures"},
        }
        raw = json.dumps(document, indent=2, sort_keys=True).encode("utf-8")

        def fetch() -> tuple[ContentPayload, bool]:
            return (
                ContentPayload(
                    form="bytes",
                    media_type="application/json",
                    data=raw[: bounds.max_bytes],
                    size_bytes=len(raw),
                ),
                len(raw) > bounds.max_bytes,
            )

        return await bounded_content(
            service="estate", kind="properties", bounds=bounds, fetch=fetch
        )

    async def search(
        self,
        text: str,
        *,
        subscriptions: tuple[str, ...] = (),
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        term = str(text or "").strip().lower()
        if not term:
            return content_failure(
                service="estate",
                kind="search",
                status="unconfigured",
                detail="search not configured: query text",
            )
        matches: list[dict[str, Any]] = []
        for group, location, _ in GROUPS:
            if term in group.lower():
                matches.append(
                    {
                        "id": f"/subscriptions/{SUBSCRIPTION}/resourceGroups/{group}",
                        "name": group,
                        "type": "microsoft.resources/subscriptions/resourcegroups",
                        "resourceGroup": group,
                        "location": location,
                        "matchedIn": "name",
                    }
                )
        for item in RESOURCES:
            haystack = f"{item.name} {item.type} {item.group} {item.location}".lower()
            if term in haystack:
                matches.append(
                    {
                        "id": item.id,
                        "name": item.name,
                        "type": item.type,
                        "resourceGroup": item.group,
                        "location": item.location,
                        "kind": item.kind,
                        "skuName": item.sku,
                        "matchedIn": "name" if term in item.name.lower() else "type",
                    }
                )

        def fetch() -> tuple[ContentPayload, bool]:
            rows, columns, truncated = normalize_rows(matches, max_rows=bounds.max_rows)
            return (
                ContentPayload(
                    form="rows",
                    media_type="application/json",
                    rows=rows,
                    columns=columns,
                    size_bytes=len(rows),
                ),
                truncated,
            )

        return await bounded_content(
            service="estate", kind="search", bounds=bounds, fetch=fetch
        )


class FixtureBlobReader:
    async def read(
        self,
        *,
        account_name: str = "",
        endpoint: str = "",
        container: str,
        blob: str,
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        account = account_name or _host_label(endpoint)
        dark = _dark(account)
        if dark:
            return content_failure(
                service="blob", kind="blob", status=dark[0], detail=dark[1]  # type: ignore[arg-type]
            )
        entry = DEMO_BLOBS.get(blob) if container == DEMO_CONTAINER else None
        if entry is None:
            return content_failure(
                service="blob",
                kind="blob",
                status="unavailable",
                detail=f"no such blob in fixture container {container}",
            )
        data, content_type = entry

        def fetch() -> tuple[ContentPayload, bool]:
            return (
                ContentPayload(
                    form="bytes",
                    media_type=content_type,
                    data=data[: bounds.max_bytes],
                    size_bytes=len(data),
                ),
                len(data) > bounds.max_bytes,
            )

        return await bounded_content(
            service="blob", kind="blob", bounds=bounds, fetch=fetch
        )


class FixtureRows:
    """One row sample, shaped like whichever reader asked for it."""

    def __init__(self, service: str, kind: str, rows: list[dict[str, Any]]) -> None:
        self._service = service
        self._kind = kind
        self._rows = rows

    async def _sample(
        self, bounds: ContentBounds, *, empty: bool = False
    ) -> ContentResult:
        rows = [] if empty else self._rows

        def fetch() -> tuple[ContentPayload, bool]:
            capped, columns, truncated = normalize_rows(rows, max_rows=bounds.max_rows)
            return (
                ContentPayload(
                    form="rows",
                    media_type="application/json",
                    rows=capped,
                    columns=columns,
                    size_bytes=len(capped),
                ),
                truncated,
            )

        return await bounded_content(
            service=self._service, kind=self._kind, bounds=bounds, fetch=fetch
        )

    async def documents(
        self,
        *,
        account_name: str = "",
        endpoint: str = "",
        database: str = "",
        container: str = "",
        index: str = "",
        text: str = "*",
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        account = account_name or _host_label(endpoint)
        dark = _dark(account)
        if dark:
            return content_failure(
                service=self._service, kind=self._kind, status=dark[0], detail=dark[1]  # type: ignore[arg-type]
            )
        return await self._sample(bounds, empty=container == "empty-container")

    async def rows(
        self,
        *,
        query_uri: str = "",
        workspace_id: str = "",
        database: str = "",
        table: str = "",
        bounds: ContentBounds = ContentBounds(),
    ) -> ContentResult:
        return await self._sample(bounds)


class FixtureArm:
    """The one management read the tree makes outside the discover plane."""

    def read(self, resource_id_value: str, *, api_version: str = "") -> dict[str, Any]:
        name = _name_from_id(resource_id_value)
        uri = "" if name == "adx-unconfigured" else f"https://{name}.eastus.kusto.windows.net"
        return {"id": resource_id_value, "name": name, "properties": {"uri": uri}}


@dataclass(frozen=True)
class FixtureAccess:
    """The same attribute surface :func:`azdata.build_estate_access` returns."""

    discoverers: DiscovererRegistry
    arm: FixtureArm
    properties: FixtureProperties
    blob: FixtureBlobReader
    cosmos: FixtureRows
    kusto: FixtureRows
    search: FixtureRows
    logs: FixtureRows


_SPECIFICATIONS: tuple[
    tuple[str, tuple[str, ...], Mapping[str, str | None], Table], ...
] = (
    (
        "estate",
        ("subscription", "resource_group", "collection"),
        {"subscription": "resource_group", "resource_group": "collection", "collection": None},
        _estate_table,
    ),
    ("blob", ("account", "container"), {"account": "container", "container": "container"}, _blob_table),
    ("cosmos", ("account", "database"), {"account": "database", "database": None}, _cosmos_table),
    ("gremlin", ("account", "database"), {"account": "database", "database": None}, _gremlin_table),
    ("search", ("service", "index"), {"service": "index", "index": None}, _search_table),
    ("kusto", ("cluster", "database"), {"cluster": "database", "database": None}, _kusto_table),
    ("logs", ("workspace",), {"workspace": None}, _logs_table),
    ("acr", ("registry", "repository"), {"registry": "repository", "repository": None}, _acr_table),
)


def build_fixture_access() -> FixtureAccess:
    """The whole fixture subscription, connected to nothing."""
    registry = DiscovererRegistry()
    for service, levels, child_levels, table in _SPECIFICATIONS:
        registry.register(
            FixtureDiscoverer(
                service=service, levels=levels, child_levels=child_levels, table=table
            )
        )
    return FixtureAccess(
        discoverers=registry,
        arm=FixtureArm(),
        properties=FixtureProperties(),
        blob=FixtureBlobReader(),
        cosmos=FixtureRows("cosmos", "documents", ROWS_BY_KIND["documents"]),
        kusto=FixtureRows("kusto", "rows", ROWS_BY_KIND["rows"]),
        search=FixtureRows("search", "documents", ROWS_BY_KIND["search"]),
        logs=FixtureRows("logs", "rows", ROWS_BY_KIND["rows"]),
    )


__all__ = [
    "ARM_CHILDREN",
    "AWKWARD_INDEX",
    "DARK_BRANCHES",
    "DEMO_BLOBS",
    "DEMO_CONTAINER",
    "DEPTH_MARKER",
    "EMPTY_INDEX",
    "GROUPS",
    "LARGE_INDEX",
    "LARGE_INDEX_FIELDS",
    "PRIMARY_INDEX",
    "REPOSITORIES",
    "RESOURCES",
    "ROWS_BY_KIND",
    "SUBSCRIPTION",
    "FixtureAccess",
    "FixtureDiscoverer",
    "FixtureResource",
    "Table",
    "build_fixture_access",
    "resource_id",
]
