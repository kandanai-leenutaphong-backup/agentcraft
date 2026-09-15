"""Control-plane provisioning.

Creates the cluster, database, and permissions the data plane needs, and waits
for each to reach a usable state. Every operation is idempotent: an existing
resource is reused rather than recreated.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

from .config import AdxConfig
from .errors import AdxProvisioningError
from .identifiers import validate_identifier

LOGGER = logging.getLogger("adx_connector.provision")

# A Dev/No-SLA cluster is single-node and unsuitable for production traffic, but
# it is the cheapest and fastest path to a working endpoint for a proof of concept.
DEV_SKU = "Dev(No SLA)_Standard_E2a_v4"


def _state_of(resource: Any) -> str:
    """Normalise the SDK's ``State`` enum to its wire value.

    ``str()`` on the enum yields ``State.RUNNING``, not ``Running``, so comparing
    the stringified enum against a documented state name never matches.
    """
    state = getattr(resource, "state", None)
    return str(getattr(state, "value", state))


@dataclass(frozen=True, slots=True)
class ClusterInfo:
    name: str
    uri: str
    ingest_uri: str
    state: str
    location: str
    sku: str
    created: bool


class AdxProvisioner:
    """Creates and inspects clusters and databases."""

    def __init__(self, config: AdxConfig, credential: Any | None = None) -> None:
        self._config = config
        self._credential = credential
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            from azure.mgmt.kusto import KustoManagementClient

            subscription, _, _ = self._config.require_provisioning_fields()
            credential = self._credential
            if credential is None:
                from azure.identity import DefaultAzureCredential

                credential = DefaultAzureCredential(exclude_interactive_browser_credential=False)
            self._client = KustoManagementClient(credential, subscription)
        return self._client

    # ---------------------------------------------------------------- cluster

    def cluster_exists(self) -> bool:
        _, resource_group, cluster_name = self._config.require_provisioning_fields()
        try:
            self.client.clusters.get(resource_group, cluster_name)
        except Exception:  # noqa: BLE001 - the SDK raises ResourceNotFoundError among others
            return False
        return True

    def ensure_cluster(self, *, streaming_ingestion: bool = True, wait: bool = True) -> ClusterInfo:
        """Create the cluster if absent, then return its addresses."""
        _, resource_group, cluster_name = self._config.require_provisioning_fields()
        validate_identifier(cluster_name.replace("-", "_"), kind="cluster name")

        if self.cluster_exists():
            cluster = self.client.clusters.get(resource_group, cluster_name)
            LOGGER.info("cluster %s already exists in %s", cluster_name, cluster.location)
            return ClusterInfo(
                name=cluster_name,
                uri=cluster.uri,
                ingest_uri=cluster.data_ingestion_uri,
                state=_state_of(cluster),
                location=cluster.location,
                sku=cluster.sku.name,
                created=False,
            )

        from azure.mgmt.kusto.models import AzureSku, Cluster

        LOGGER.info("creating cluster %s in %s", cluster_name, self._config.location)
        parameters = Cluster(
            location=self._config.location,
            sku=AzureSku(name=self._config.sku_name, tier=self._config.sku_tier),
            enable_streaming_ingest=streaming_ingestion,
            # A single-node dev cluster has no purge workflow enabled by default;
            # turning it on here keeps the hard-delete path available.
            enable_purge=True,
        )
        try:
            poller = self.client.clusters.begin_create_or_update(resource_group, cluster_name, parameters)
            cluster = poller.result() if wait else parameters
        except Exception as exc:  # noqa: BLE001
            raise AdxProvisioningError(f"creating cluster {cluster_name} failed: {exc}") from exc

        return ClusterInfo(
            name=cluster_name,
            uri=getattr(cluster, "uri", ""),
            ingest_uri=getattr(cluster, "data_ingestion_uri", ""),
            state=_state_of(cluster) if hasattr(cluster, "state") else "Unknown",
            location=self._config.location,
            sku=self._config.sku_name,
            created=True,
        )

    def wait_for_running(self, *, timeout_seconds: int = 1800, poll_seconds: int = 20) -> str:
        """Block until the cluster reports ``Running``."""
        _, resource_group, cluster_name = self._config.require_provisioning_fields()
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            cluster = self.client.clusters.get(resource_group, cluster_name)
            state = _state_of(cluster)
            if state == "Running":
                return state
            if state in {"Stopped", "Unavailable"}:
                raise AdxProvisioningError(f"cluster {cluster_name} reached terminal state {state}")
            LOGGER.info("cluster %s is %s; waiting", cluster_name, state)
            time.sleep(poll_seconds)
        raise AdxProvisioningError(f"cluster {cluster_name} did not reach Running within {timeout_seconds}s")

    # --------------------------------------------------------------- database

    def ensure_database(self, *, hot_cache_days: int = 31, retention_days: int = 365) -> bool:
        """Create the database if absent. Returns True when it was created."""
        _, resource_group, cluster_name = self._config.require_provisioning_fields()
        database = self._config.database
        from datetime import timedelta

        from azure.mgmt.kusto.models import ReadWriteDatabase

        try:
            self.client.databases.get(resource_group, cluster_name, database)
            LOGGER.info("database %s already exists", database)
            return False
        except Exception:  # noqa: BLE001
            pass

        parameters = ReadWriteDatabase(
            location=self._config.location,
            # From the 2021-01-01 API version the polymorphic discriminator must
            # be set explicitly; this SDK does not default it.
            kind="ReadWrite",
            soft_delete_period=timedelta(days=retention_days),
            hot_cache_period=timedelta(days=hot_cache_days),
        )
        try:
            self.client.databases.begin_create_or_update(
                resource_group, cluster_name, database, parameters
            ).result()
        except Exception as exc:  # noqa: BLE001
            raise AdxProvisioningError(f"creating database {database} failed: {exc}") from exc
        LOGGER.info("created database %s", database)
        return True

    def teardown_cluster(self, *, confirm: str = "") -> None:
        """Delete the cluster. Requires the cluster name as explicit confirmation."""
        _, resource_group, cluster_name = self._config.require_provisioning_fields()
        if confirm != cluster_name:
            raise AdxProvisioningError(
                f"refusing to delete {cluster_name}: pass confirm={cluster_name!r} to proceed"
            )
        self.client.clusters.begin_delete(resource_group, cluster_name).result()
        LOGGER.warning("deleted cluster %s", cluster_name)
