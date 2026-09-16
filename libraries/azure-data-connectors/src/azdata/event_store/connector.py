"""The connector facade.

One object that owns configuration, credentials, the query client, the
ingestion clients, and the provisioner, so callers hold a single lifetime.

    with AdxConnector.from_env() as adx:
        adx.ensure_infrastructure()
        repo = adx.repository(schema)
        repo.insert(rows)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Mapping, Sequence

from .client import AdxClient
from .config import AdxConfig
from .crud import CrudRepository, UpsertStrategy
from .errors import AdxError
from .identifiers import validate_identifier
from .ingest import IngestMode, IngestResult, Ingestor
from .models import QueryResult, TableSchema
from .policy import EventStorePolicy
from .provision import AdxProvisioner, ClusterInfo
from .schema import create_table_command, csv_mapping_command, infer_schema

LOGGER = logging.getLogger("azdata.event_store")

__all__ = ["AdxConnector", "UpsertStrategy"]


class AdxConnector:
    """Single entry point for provisioning, schema, ingestion, and CRUD."""

    def __init__(self, config: AdxConfig, credential: Any | None = None, *, policy: EventStorePolicy | None = None) -> None:
        self._config = config
        self._credential = credential
        self._policy = policy if policy is not None else EventStorePolicy()
        self._client = AdxClient(config, credential, policy=self._policy)
        self._ingestor = Ingestor(config, credential, policy=self._policy)
        self._provisioner = AdxProvisioner(config, credential, policy=self._policy)

    @classmethod
    def from_env(cls, credential: Any | None = None, *, policy: EventStorePolicy | None = None, **overrides: object) -> "AdxConnector":
        return cls(AdxConfig.from_env(**overrides), credential, policy=policy)

    # ------------------------------------------------------------- lifecycle

    @property
    def config(self) -> AdxConfig:
        return self._config

    @property
    def client(self) -> AdxClient:
        return self._client

    @property
    def ingestor(self) -> Ingestor:
        return self._ingestor

    @property
    def provisioner(self) -> AdxProvisioner:
        return self._provisioner

    def close(self) -> None:
        self._client.close()
        self._ingestor.close()
        self._provisioner.close()

    def __enter__(self) -> "AdxConnector":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    # ----------------------------------------------------------- provisioning

    def ensure_infrastructure(self, *, wait: bool = True) -> ClusterInfo:
        """Create cluster and database if absent, then wait until queryable."""
        info = self._provisioner.ensure_cluster(wait=wait)
        if wait:
            self._provisioner.wait_for_running()
        self._provisioner.ensure_database()
        return info

    def health(self) -> dict[str, Any]:
        """Connectivity and capacity snapshot, safe to call on every start-up."""
        report: dict[str, Any] = {"cluster_uri": self._config.cluster_uri, "database": self._config.database}
        try:
            report["reachable"] = self._client.ping()
            report["principal"] = self._client.scalar("print p = current_principal()")
            report["database_exists"] = bool(
                self._client.command(".show database schema | take 1").rows
            )
        except AdxError as exc:
            report["reachable"] = False
            report["error"] = str(exc)
        return report

    # ----------------------------------------------------------------- schema

    def create_table(self, schema: TableSchema, *, mapping_name: str | None = None) -> TableSchema:
        """Create or merge the table, and optionally a CSV ingestion mapping."""
        self._policy.require("schema")
        self._client._command(create_table_command(schema), grant="schema")
        if mapping_name:
            self._client._command(csv_mapping_command(schema, mapping_name), grant="schema")
        LOGGER.info("ensured table %s with %d columns", schema.name, len(schema.columns))
        return schema

    def infer_schema_from_csv(self, csv_path: Path, table_name: str, **kwargs: Any) -> TableSchema:
        return infer_schema(csv_path, table_name, **kwargs)

    def table_schema(self, table_name: str) -> TableSchema:
        """Read the live schema of an existing table."""
        from .models import ColumnSpec

        validate_identifier(table_name, kind="table")
        result = self._client.command(f".show table {table_name} cslschema")
        row = result.first()
        if not row:
            raise AdxError(f"table {table_name} not found")
        columns = tuple(
            ColumnSpec(name=part.split(":", 1)[0], kusto_type=part.split(":", 1)[1])
            for part in str(row["Schema"]).split(",")
            if ":" in part
        )
        return TableSchema(name=table_name, columns=columns)

    def list_tables(self) -> list[str]:
        return [str(row["TableName"]) for row in self._client.command(".show tables").to_dicts()]

    def set_batching_latency(self, table: str, seconds: int) -> QueryResult:
        """Lower the ingestion batching delay for a table.

        The default batching policy waits up to five minutes. For a demo or a
        test battery that is an eternity; 10-30 seconds trades throughput for
        visibility.
        """
        self._policy.require("schema")
        validate_identifier(table, kind="table")
        if type(seconds) is not int or not 1 <= seconds <= 59:
            raise AdxError("batching seconds must be an integer from 1 to 59")
        policy = f'{{"MaximumBatchingTimeSpan":"00:00:{seconds:02d}","MaximumNumberOfItems":500,"MaximumRawDataSizeMB":1024}}'
        return self._client._command(f".alter table {table} policy ingestionbatching @'{policy}'", grant="schema")

    def enable_streaming(self, table: str) -> QueryResult:
        """Turn on the streaming ingestion policy for a table."""
        self._policy.require("schema")
        validate_identifier(table, kind="table")
        return self._client._command(
            f'.alter table {table} policy streamingingestion @\'{{"IsEnabled": true}}\'', grant="schema"
        )

    # ------------------------------------------------------------------- data

    def repository(self, schema: TableSchema) -> CrudRepository:
        """A CRUD repository bound to ``schema``."""
        return CrudRepository(self._client, self._ingestor, schema)

    def load_csv(
        self,
        csv_path: Path,
        table_name: str,
        *,
        mapping_name: str | None = None,
        mode: IngestMode = IngestMode.QUEUED,
        create: bool = True,
        dedupe_tag: str | None = None,
        sample_rows: int = 5_000,
        force_types: Mapping[str, str] | None = None,
    ) -> tuple[TableSchema, IngestResult]:
        """Infer, create, and load in one call. The bulk-load path."""
        self._policy.require("ingest")
        if create:
            self._policy.require("schema")
        schema = infer_schema(
            csv_path, table_name, sample_rows=sample_rows, force_types=dict(force_types or {})
        )
        if create:
            self.create_table(schema, mapping_name=mapping_name)
        result = self._ingestor.ingest_file(
            csv_path,
            table_name,
            mode=mode,
            mapping_reference=mapping_name,
            dedupe_tag=dedupe_tag,
            ignore_first_record=True,
        )
        return schema, result

    def wait_for_rows(self, table: str, expected: int, *, timeout_seconds: int = 600, poll_seconds: int = 5) -> int:
        """Block until ``table`` holds at least ``expected`` rows.

        Queued ingestion is asynchronous; without this a test asserts on an
        empty table and fails for the wrong reason.
        """
        import time

        validate_identifier(table, kind="table")
        deadline = time.monotonic() + timeout_seconds
        observed = 0
        while time.monotonic() < deadline:
            observed = int(self._client.scalar(f"{table} | count", default=0) or 0)
            if observed >= expected:
                return observed
            time.sleep(poll_seconds)
        raise AdxError(f"{table} reached {observed:,} rows, expected {expected:,} within {timeout_seconds}s")

    def query(self, kql: str, parameters: Mapping[str, Any] | None = None, **kwargs: Any) -> QueryResult:
        return self._client.query(kql, parameters, **kwargs)

    def command(self, kql: str, parameters: Mapping[str, Any] | None = None, **kwargs: Any) -> QueryResult:
        return self._client.command(kql, parameters, **kwargs)

    def iter_pages(self, kql: str, parameters: Mapping[str, Any] | None = None, **kwargs: Any):
        return self._client.iter_pages(kql, parameters, **kwargs)

    def ingestion_failures(self, *, hours: int = 1) -> QueryResult:
        """Recent ingestion failures, the first place to look when rows are missing."""
        return self._client.command(f".show ingestion failures | where FailedOn > ago({int(hours)}h)")
