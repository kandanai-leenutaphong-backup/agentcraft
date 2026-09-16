"""Connector configuration.

Values resolve from explicit arguments first, then environment variables, so the
same code runs from a developer shell and from a managed identity in Azure with
no branching.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .errors import AdxConfigError
from .identifiers import validate_identifier

ENV_PREFIX = "ADX_"

# Public Azure suffix. The ingestion endpoint is the query endpoint with an
# `ingest-` prefix on the first label; this is a service convention, not a guess.
_INGEST_PREFIX = "ingest-"


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(ENV_PREFIX + name, default)


@dataclass(frozen=True, slots=True)
class AdxConfig:
    """Everything the connector needs to reach one database.

    Attributes:
        cluster_uri: Query endpoint, e.g. ``https://mycluster.australiaeast.kusto.windows.net``.
        database: Target database name.
        ingest_uri: Ingestion endpoint. Derived from ``cluster_uri`` when omitted.
        subscription_id: Required only for control-plane provisioning.
        resource_group: Required only for control-plane provisioning.
        cluster_name: Required only for control-plane provisioning.
        location: Azure region for provisioning.
        sku_name: Cluster SKU for provisioning.
        sku_tier: Cluster SKU tier for provisioning.
        query_timeout_seconds: Server-side query deadline.
        max_retries: Retry attempts for throttled and transient faults.
        backoff_base_seconds: First backoff interval; doubles with full jitter.
        backoff_cap_seconds: Upper bound on any single backoff interval.
        application_name: Reported to the service for traceability.
    """

    cluster_uri: str
    database: str
    ingest_uri: str | None = None
    subscription_id: str | None = None
    resource_group: str | None = None
    cluster_name: str | None = None
    location: str = "australiaeast"
    sku_name: str = "Dev(No SLA)_Standard_E2a_v4"
    sku_tier: str = "Basic"
    query_timeout_seconds: int = 240
    max_retries: int = 4
    backoff_base_seconds: float = 0.5
    backoff_cap_seconds: float = 20.0
    application_name: str = "adx-event-store"
    _derived_ingest_uri: str = field(init=False, repr=False, default="")

    def __post_init__(self) -> None:
        parsed = urlparse(self.cluster_uri)
        if parsed.scheme != "https" or not parsed.netloc:
            raise AdxConfigError(f"cluster_uri must be an https URL, got {self.cluster_uri!r}")
        validate_identifier(self.database, kind="database")
        if self.max_retries < 0:
            raise AdxConfigError("max_retries must not be negative")
        if self.query_timeout_seconds <= 0:
            raise AdxConfigError("query_timeout_seconds must be positive")

        resolved = self.ingest_uri
        if not resolved:
            host = parsed.netloc
            resolved = f"{parsed.scheme}://{_INGEST_PREFIX}{host}"
        object.__setattr__(self, "_derived_ingest_uri", resolved)

    @property
    def ingestion_endpoint(self) -> str:
        """Ingestion endpoint, derived from the query endpoint when not supplied."""
        return self._derived_ingest_uri

    @property
    def can_provision(self) -> bool:
        """True when the control-plane fields needed for provisioning are present."""
        return bool(self.subscription_id and self.resource_group and self.cluster_name)

    def require_provisioning_fields(self) -> tuple[str, str, str]:
        """Return the control-plane triple, or raise if incomplete."""
        if not self.can_provision:
            raise AdxConfigError(
                "provisioning needs subscription_id, resource_group, and cluster_name; "
                f"set {ENV_PREFIX}SUBSCRIPTION_ID, {ENV_PREFIX}RESOURCE_GROUP, {ENV_PREFIX}CLUSTER_NAME"
            )
        return self.subscription_id, self.resource_group, self.cluster_name  # type: ignore[return-value]

    @classmethod
    def from_env(cls, **overrides: object) -> "AdxConfig":
        """Build config from ``ADX_*`` environment variables, with overrides."""
        cluster_uri = overrides.pop("cluster_uri", None) or _env("CLUSTER_URI")
        database = overrides.pop("database", None) or _env("DATABASE")
        if not cluster_uri or not database:
            raise AdxConfigError(
                f"{ENV_PREFIX}CLUSTER_URI and {ENV_PREFIX}DATABASE are required "
                "when configuration is not passed explicitly"
            )
        values: dict[str, object] = {
            "cluster_uri": str(cluster_uri),
            "database": str(database),
            "ingest_uri": _env("INGEST_URI"),
            "subscription_id": _env("SUBSCRIPTION_ID"),
            "resource_group": _env("RESOURCE_GROUP"),
            "cluster_name": _env("CLUSTER_NAME"),
        }
        for key, caster in (
            ("LOCATION", str),
            ("SKU_NAME", str),
            ("SKU_TIER", str),
            ("APPLICATION_NAME", str),
            ("QUERY_TIMEOUT_SECONDS", int),
            ("MAX_RETRIES", int),
            ("BACKOFF_BASE_SECONDS", float),
            ("BACKOFF_CAP_SECONDS", float),
        ):
            raw = _env(key)
            if raw is not None:
                values[key.lower()] = caster(raw)
        values.update(overrides)
        return cls(**values)  # type: ignore[arg-type]
