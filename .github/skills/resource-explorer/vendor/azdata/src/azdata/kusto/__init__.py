"""Azure Data Explorer / Fabric Eventhouse — read, ingest, deploy, observe, verify.

Four planes and one deliberate gap.

**The write plane is ingestion, not CRUD.** Kusto has no update and no
per-row delete: a table is an append-only extent store, and the closest
thing to a delete is a soft-delete over a predicate run as a management
command against the whole table. ``KustoIngest`` is therefore an
``IngestConnector``, not a ``CrudConnector``, and the two missing verbs are
absent rather than raising.

**The deploy plane spans two planes of Azure.** The cluster and the
database are ARM resources behind ``azure-mgmt-kusto``; a table is not an
ARM resource at all and is created by control command against the data
plane. That is the same split ``search`` already makes between the service
and the index.
"""

from __future__ import annotations

from azdata.kusto.deploy import (
    CLUSTER_POLL_TIMEOUT_SECS,
    DEV_SKU,
    KustoClusterProvisioner,
    KustoDatabaseProvisioner,
    KustoDeployError,
    KustoTableProvisioner,
    cluster_policy,
    lift_kusto_model,
)
from azdata.kusto.discover import (
    ALLOWED_COMMANDS,
    KustoDiscoverer,
    cluster_name_from_uri,
)
from azdata.kusto.observe import KustoStats
from azdata.kusto.read import KqlConnector, KqlTarget, shape_kusto_response
from azdata.kusto.verify import KustoKeys, KustoVerifyError
from azdata.kusto.write import KustoIngest, KustoIngestError, kusto_literal

__all__ = [
    "ALLOWED_COMMANDS",
    "CLUSTER_POLL_TIMEOUT_SECS",
    "DEV_SKU",
    "KqlConnector",
    "KqlTarget",
    "KustoClusterProvisioner",
    "KustoDatabaseProvisioner",
    "KustoDeployError",
    "KustoDiscoverer",
    "KustoIngest",
    "KustoIngestError",
    "KustoKeys",
    "KustoStats",
    "KustoTableProvisioner",
    "KustoVerifyError",
    "cluster_name_from_uri",
    "cluster_policy",
    "kusto_literal",
    "lift_kusto_model",
    "shape_kusto_response",
]
