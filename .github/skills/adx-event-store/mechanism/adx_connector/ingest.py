"""Ingestion strategies.

Three modes, because the right one depends on payload size and latency need:

* ``QUEUED`` — the service batches and optimises. Highest throughput; the
  service-recommended default for bulk. Data appears after the batching policy
  fires, seconds to minutes.
* ``MANAGED_STREAMING`` — streams small payloads for near-immediate visibility
  and falls back to queued automatically when a payload is too large or
  streaming is unavailable. The right default for single-row writes.
* ``INLINE`` — the payload travels inside a control command. Prototyping and
  tests only; the service documents it as unsuitable for production volume.
"""

from __future__ import annotations

import csv
import io
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from azure.kusto.data import KustoConnectionStringBuilder
from azure.kusto.data.data_format import DataFormat
from azure.kusto.ingest import (
    IngestionProperties,
    ManagedStreamingIngestClient,
    QueuedIngestClient,
    ReportLevel,
    StreamDescriptor,
)

from .config import AdxConfig
from .errors import AdxIngestionError
from .identifiers import validate_identifier
from .models import TableSchema

LOGGER = logging.getLogger("adx_connector.ingest")

# The service rejects any single ingestion payload above this size.
MAX_UNCOMPRESSED_BYTES = 1_073_741_824


class IngestMode(str, Enum):
    QUEUED = "queued"
    MANAGED_STREAMING = "managed_streaming"
    INLINE = "inline"


@dataclass(frozen=True, slots=True)
class IngestResult:
    """Outcome of one ingestion call."""

    mode: IngestMode
    table: str
    rows: int
    bytes_sent: int
    source_id: str
    elapsed_seconds: float
    status: str = "queued"
    tags: tuple[str, ...] = field(default_factory=tuple)

    @property
    def is_terminal(self) -> bool:
        """True when the result already reflects data being queryable."""
        return self.status == "succeeded"


class Ingestor:
    """Owns the ingestion clients for one database."""

    def __init__(self, config: AdxConfig, credential: Any | None = None) -> None:
        self._config = config
        self._credential = credential
        self._queued: QueuedIngestClient | None = None
        self._managed: ManagedStreamingIngestClient | None = None

    def _credential_or_default(self) -> Any:
        if self._credential is not None:
            return self._credential
        from azure.identity import DefaultAzureCredential

        return DefaultAzureCredential(exclude_interactive_browser_credential=False)

    def _kcsb(self, uri: str) -> KustoConnectionStringBuilder:
        builder = KustoConnectionStringBuilder.with_azure_token_credential(uri, self._credential_or_default())
        builder.application_for_tracing = self._config.application_name
        return builder

    @property
    def queued(self) -> QueuedIngestClient:
        if self._queued is None:
            self._queued = QueuedIngestClient(self._kcsb(self._config.ingestion_endpoint))
        return self._queued

    @property
    def managed(self) -> ManagedStreamingIngestClient:
        if self._managed is None:
            # Managed streaming needs both endpoints: the engine for the streaming
            # attempt, the data-management endpoint for the queued fallback.
            self._managed = ManagedStreamingIngestClient(
                engine_kcsb=self._kcsb(self._config.cluster_uri),
                dm_kcsb=self._kcsb(self._config.ingestion_endpoint),
            )
        return self._managed

    def close(self) -> None:
        for client in (self._queued, self._managed):
            if client is not None:
                client.close()
        self._queued = None
        self._managed = None

    # ------------------------------------------------------------ properties

    def _properties(
        self,
        table: str,
        data_format: DataFormat,
        *,
        mapping_reference: str | None,
        dedupe_tag: str | None,
        drop_by_tag: str | None,
        flush_immediately: bool,
        ignore_first_record: bool,
    ) -> IngestionProperties:
        validate_identifier(table, kind="table")
        properties = IngestionProperties(
            database=self._config.database,
            table=table,
            data_format=data_format,
            ignore_first_record=ignore_first_record,
            flush_immediately=flush_immediately,
            report_level=ReportLevel.FailuresAndSuccesses,
        )
        if mapping_reference:
            properties.ingestion_mapping_reference = validate_identifier(mapping_reference, kind="mapping")
        if dedupe_tag:
            # `ingest_by:` plus `ingest_if_not_exists` makes a replayed batch a
            # no-op instead of a duplicate — the service-supported idempotency key.
            properties.ingest_by_tags = [dedupe_tag]
            properties.ingest_if_not_exists = [dedupe_tag]
        if drop_by_tag:
            # Tagging by batch lets a bad load be dropped later without touching
            # neighbouring data.
            properties.drop_by_tags = [drop_by_tag]
        return properties

    # --------------------------------------------------------------- ingest

    def ingest_file(
        self,
        path: Path,
        table: str,
        *,
        mode: IngestMode = IngestMode.QUEUED,
        data_format: DataFormat = DataFormat.CSV,
        mapping_reference: str | None = None,
        dedupe_tag: str | None = None,
        drop_by_tag: str | None = None,
        ignore_first_record: bool = True,
    ) -> IngestResult:
        """Ingest a file. ``ignore_first_record`` skips a CSV header row."""
        if not path.exists():
            raise AdxIngestionError(f"ingestion source not found: {path}")
        size = path.stat().st_size
        if size > MAX_UNCOMPRESSED_BYTES:
            raise AdxIngestionError(
                f"{path.name} is {size:,} bytes, above the {MAX_UNCOMPRESSED_BYTES:,} byte limit; "
                "split the file or ingest from blob storage"
            )
        properties = self._properties(
            table,
            data_format,
            mapping_reference=mapping_reference,
            dedupe_tag=dedupe_tag,
            drop_by_tag=drop_by_tag,
            flush_immediately=mode is IngestMode.MANAGED_STREAMING,
            ignore_first_record=ignore_first_record,
        )
        source_id = str(uuid.uuid4())
        client = self.managed if mode is IngestMode.MANAGED_STREAMING else self.queued
        started = time.monotonic()
        try:
            client.ingest_from_file(str(path), ingestion_properties=properties)
        except Exception as exc:  # noqa: BLE001
            raise AdxIngestionError(f"ingesting {path.name} into {table} failed: {exc}") from exc
        elapsed = time.monotonic() - started
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            if ignore_first_record:
                next(reader, None)
            rows = sum(1 for row in reader if row)
        LOGGER.info("ingested %s (%s bytes) into %s in %.2fs", path.name, f"{size:,}", table, elapsed)
        return IngestResult(
            mode=mode,
            table=table,
            rows=rows,
            bytes_sent=size,
            source_id=source_id,
            elapsed_seconds=elapsed,
            tags=tuple(t for t in (dedupe_tag, drop_by_tag) if t),
        )

    def ingest_rows(
        self,
        rows: Iterable[Mapping[str, Any]],
        table: str,
        schema: TableSchema,
        *,
        mode: IngestMode = IngestMode.MANAGED_STREAMING,
        dedupe_tag: str | None = None,
        drop_by_tag: str | None = None,
    ) -> IngestResult:
        """Ingest in-memory rows as CSV, ordered to the table schema."""
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        count = 0
        for row in rows:
            unknown = set(row) - set(schema.column_names)
            if unknown:
                raise AdxIngestionError(f"row has columns absent from {schema.name}: {sorted(unknown)}")
            writer.writerow(["" if row.get(name) is None else row.get(name) for name in schema.column_names])
            count += 1
        if count == 0:
            return IngestResult(mode=mode, table=table, rows=0, bytes_sent=0, source_id="", elapsed_seconds=0.0)

        payload = buffer.getvalue().encode("utf-8")
        properties = self._properties(
            table,
            DataFormat.CSV,
            mapping_reference=None,
            dedupe_tag=dedupe_tag,
            drop_by_tag=drop_by_tag,
            # In-memory row writes are interactive, so bypass the batching
            # aggregator. Without this a handful of rows waits out the table's
            # batching policy - five minutes by default - before becoming
            # queryable, which reads as data loss.
            flush_immediately=True,
            ignore_first_record=False,
        )
        source_id = str(uuid.uuid4())
        descriptor = StreamDescriptor(io.BytesIO(payload), source_id=source_id, is_compressed=False)
        client = self.managed if mode is IngestMode.MANAGED_STREAMING else self.queued
        started = time.monotonic()
        try:
            client.ingest_from_stream(descriptor, ingestion_properties=properties)
        except Exception as exc:  # noqa: BLE001
            raise AdxIngestionError(f"ingesting {count} row(s) into {table} failed: {exc}") from exc
        elapsed = time.monotonic() - started
        return IngestResult(
            mode=mode,
            table=table,
            rows=count,
            bytes_sent=len(payload),
            source_id=source_id,
            elapsed_seconds=elapsed,
            status="succeeded" if mode is IngestMode.MANAGED_STREAMING else "queued",
            tags=tuple(t for t in (dedupe_tag, drop_by_tag) if t),
        )

    @staticmethod
    def inline_command(table: str, schema: TableSchema, rows: Sequence[Mapping[str, Any]]) -> str:
        """Build a ``.ingest inline`` command. Prototyping and tests only."""
        validate_identifier(table, kind="table")
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        for row in rows:
            writer.writerow(["" if row.get(name) is None else row.get(name) for name in schema.column_names])
        return f".ingest inline into table {table} <|\n{buffer.getvalue().rstrip()}"
