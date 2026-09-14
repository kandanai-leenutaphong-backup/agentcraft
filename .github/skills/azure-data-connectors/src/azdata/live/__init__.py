"""`azdata.live` — the live conformance topology, as code.

The environment this package's live conformance suite runs against:
five resources, one seed dataset, one lifecycle. Everything is driven
through the package's own deploy plane, so standing the environment up is
itself the first real test of the provisioners.

``python -m azdata.live up --subscription <id>`` builds it; ``status``
describes it; ``pause`` and ``resume`` stop and start the ADX cluster,
which is the only real cost lever; ``down`` deletes the resource group,
refuses unless it carries the ownership tag, and re-reads to prove
absence. Every command requires an explicit subscription.
"""

from __future__ import annotations

from azdata.live.environment import (
    COSMOS_ACCOUNT,
    COSMOS_CONTAINER,
    COSMOS_DATABASE,
    GREMLIN_ACCOUNT,
    GREMLIN_DATABASE,
    GREMLIN_GRAPH,
    KUSTO_CLUSTER,
    KUSTO_DATABASE,
    KUSTO_TABLE,
    LOCATION,
    LOG_WORKSPACE,
    OWNER_TAG_KEY,
    OWNER_TAG_VALUE,
    RESOURCE_GROUP,
    ROLES,
    SEARCH_INDEX,
    SEARCH_SERVICE,
    TOPOLOGY,
    Environment,
    LiveEnvironmentError,
    NameUnavailable,
    ResourcePlan,
    RolePlan,
    StepResult,
    TeardownRefused,
)
from azdata.live.seed import (
    ASSET_COUNT,
    ASSETS,
    EDGE_COUNT,
    KUSTO_COLUMNS,
    asset_ids,
    cosmos_items,
    gremlin_edges,
    gremlin_vertices,
    kusto_rows,
    projection_keys,
    search_documents,
)

__all__ = [
    "ASSETS",
    "ASSET_COUNT",
    "COSMOS_ACCOUNT",
    "COSMOS_CONTAINER",
    "COSMOS_DATABASE",
    "EDGE_COUNT",
    "Environment",
    "GREMLIN_ACCOUNT",
    "GREMLIN_DATABASE",
    "GREMLIN_GRAPH",
    "KUSTO_CLUSTER",
    "KUSTO_COLUMNS",
    "KUSTO_DATABASE",
    "KUSTO_TABLE",
    "LOCATION",
    "LOG_WORKSPACE",
    "LiveEnvironmentError",
    "NameUnavailable",
    "OWNER_TAG_KEY",
    "OWNER_TAG_VALUE",
    "RESOURCE_GROUP",
    "ROLES",
    "ResourcePlan",
    "RolePlan",
    "SEARCH_INDEX",
    "SEARCH_SERVICE",
    "StepResult",
    "TOPOLOGY",
    "TeardownRefused",
    "asset_ids",
    "cosmos_items",
    "gremlin_edges",
    "gremlin_vertices",
    "kusto_rows",
    "projection_keys",
    "search_documents",
]
