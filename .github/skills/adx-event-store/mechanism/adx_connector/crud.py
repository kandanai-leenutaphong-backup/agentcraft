"""CRUD facade.

Kusto is append-optimised. It has no row-level update and no immediate hard
delete, so this module implements the two operations the engine genuinely
supports and names them for what they are:

* **Update** has two strategies. ``UpsertStrategy.SOFT_DELETE_REPLACE`` removes
  the matching rows then re-ingests the new version, giving one row per key at
  the cost of a rebuild of affected extents. ``UpsertStrategy.APPEND_VERSIONED``
  appends a new version and resolves the winner at read time with ``arg_max``,
  which is cheaper to write and preserves history.
* **Delete** defaults to the soft delete the service documents for CRUD
  workloads: rows stop being queryable immediately, storage is reclaimed by the
  retention policy. Hard removal is a separate, explicit purge.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable, Mapping, Sequence

from .client import AdxClient
from .errors import AdxQueryError
from .identifiers import validate_identifier
from .ingest import IngestMode, IngestResult, Ingestor
from .models import QueryResult, TableSchema

LOGGER = logging.getLogger("adx_connector.crud")


class UpsertStrategy(str, Enum):
    SOFT_DELETE_REPLACE = "soft_delete_replace"
    APPEND_VERSIONED = "append_versioned"


class CrudRepository:
    """Row-oriented operations over one Kusto table."""

    def __init__(self, client: AdxClient, ingestor: Ingestor, schema: TableSchema) -> None:
        self._client = client
        self._ingestor = ingestor
        self._schema = schema
        self._table = validate_identifier(schema.name, kind="table")

    @property
    def schema(self) -> TableSchema:
        return self._schema

    @property
    def table(self) -> str:
        return self._table

    def _check_column(self, name: str) -> str:
        validate_identifier(name, kind="column")
        if name not in self._schema.column_names:
            raise AdxQueryError(f"{self._table} has no column {name!r}")
        return name

    # ----------------------------------------------------------------- CREATE

    def insert(
        self,
        rows: Iterable[Mapping[str, Any]],
        *,
        mode: IngestMode = IngestMode.MANAGED_STREAMING,
        dedupe_tag: str | None = None,
    ) -> IngestResult:
        """Append rows.

        Pass ``dedupe_tag`` to make a replay of the same batch a no-op rather
        than a duplicate.
        """
        return self._ingestor.ingest_rows(
            rows, self._table, self._schema, mode=mode, dedupe_tag=dedupe_tag
        )

    # ------------------------------------------------------------------- READ

    def get(self, key_column: str, key_value: Any) -> dict[str, Any] | None:
        """One row by key, or ``None``. Errors if the key is not unique."""
        column = self._check_column(key_column)
        result = self._client.query(
            f"{self._table} | where {column} == key_value | take 2", {"key_value": key_value}
        )
        if len(result) > 1:
            raise AdxQueryError(f"{column} == {key_value!r} matched more than one row in {self._table}")
        return result.first()

    def read(
        self,
        *,
        where: str = "",
        parameters: Mapping[str, Any] | None = None,
        project: Sequence[str] = (),
        order_by: str = "",
        limit: int | None = 1_000,
    ) -> QueryResult:
        """Filtered read.

        ``where`` and ``order_by`` are KQL fragments and must reference values
        only through ``parameters``; never format a caller value into them.
        """
        parts = [self._table]
        if where:
            parts.append(f"| where {where}")
        if project:
            columns = ", ".join(self._check_column(name) for name in project)
            parts.append(f"| project {columns}")
        if order_by:
            parts.append(f"| order by {order_by}")
        if limit is not None:
            if limit <= 0:
                raise AdxQueryError("limit must be positive, or None for unbounded")
            parts.append(f"| take {int(limit)}")
        return self._client.query("\n".join(parts), parameters)

    def count(self, *, where: str = "", parameters: Mapping[str, Any] | None = None) -> int:
        """Row count, optionally filtered."""
        kql = self._table + (f"\n| where {where}" if where else "") + "\n| count"
        return int(self._client.query(kql, parameters).scalar(0))

    def exists(self, key_column: str, key_value: Any) -> bool:
        column = self._check_column(key_column)
        return bool(
            self._client.scalar(
                f"{self._table} | where {column} == key_value | take 1 | count",
                {"key_value": key_value},
            )
        )

    def latest_by(
        self,
        key_column: str,
        version_column: str,
        *,
        where: str = "",
        parameters: Mapping[str, Any] | None = None,
        limit: int | None = 1_000,
    ) -> QueryResult:
        """Newest row per key, for tables written with ``APPEND_VERSIONED``."""
        key = self._check_column(key_column)
        version = self._check_column(version_column)
        parts = [self._table]
        if where:
            parts.append(f"| where {where}")
        parts.append(f"| summarize arg_max({version}, *) by {key}")
        if limit is not None:
            parts.append(f"| take {int(limit)}")
        return self._client.query("\n".join(parts), parameters)

    # ----------------------------------------------------------------- UPDATE

    def update(
        self,
        key_column: str,
        rows: Sequence[Mapping[str, Any]],
        *,
        strategy: UpsertStrategy = UpsertStrategy.SOFT_DELETE_REPLACE,
        version_column: str | None = None,
    ) -> IngestResult:
        """Replace rows identified by ``key_column``.

        ``SOFT_DELETE_REPLACE`` deletes matching keys then ingests replacements,
        leaving exactly one row per key. Not atomic: a failure between the two
        steps leaves the keys deleted, so the caller must retry the ingest.

        ``APPEND_VERSIONED`` stamps ``version_column`` and appends. Readers must
        use :meth:`latest_by` to resolve the winner.
        """
        key = self._check_column(key_column)
        if not rows:
            return IngestResult(mode=IngestMode.MANAGED_STREAMING, table=self._table, rows=0, bytes_sent=0, source_id="", elapsed_seconds=0.0)

        missing = [row for row in rows if key not in row]
        if missing:
            raise AdxQueryError(f"{len(missing)} row(s) lack the key column {key!r}")

        if strategy is UpsertStrategy.APPEND_VERSIONED:
            version = self._check_column(version_column or "ingested_at")
            stamped = [{**row, version: datetime.now(timezone.utc).isoformat()} for row in rows]
            return self.insert(stamped, mode=IngestMode.MANAGED_STREAMING)

        keys = [row[key] for row in rows]
        self.delete_in(key, keys)
        return self.insert(rows, mode=IngestMode.MANAGED_STREAMING)

    # ----------------------------------------------------------------- DELETE

    def delete_where(self, predicate: str, parameters: Mapping[str, Any] | None = None) -> int:
        """Soft-delete rows matching ``predicate``. Returns rows removed.

        Soft delete makes rows immediately unqueryable; storage is reclaimed
        under the retention policy. Reference values only through ``parameters``.
        """
        if not predicate.strip():
            raise AdxQueryError("delete_where requires a predicate; refusing to delete every row")
        before = self.count(where=predicate, parameters=parameters)
        if before == 0:
            return 0
        declaration = AdxClient.declare_parameters(parameters)
        # `.delete` carries an embedded query, so the parameters must be declared
        # inside the command text and bound in the request properties.
        command = f".delete table {self._table} records <|\n{declaration}{self._table}\n| where {predicate}"
        self._client.command(command, parameters)
        return before

    def delete_in(self, key_column: str, keys: Sequence[Any], *, chunk: int = 500) -> int:
        """Soft-delete every row whose key is in ``keys``.

        Keys bind as individually named scalar parameters rather than one
        ``dynamic`` array: the service rejects a dynamic value on the ``in``
        operator, and per-key binding keeps every value out of the query text.
        """
        column = self._check_column(key_column)
        if not keys:
            return 0
        removed = 0
        for start in range(0, len(keys), chunk):
            batch = list(keys)[start : start + chunk]
            # Parameter names are generated here, never taken from caller input.
            names = [f"k{index}" for index in range(len(batch))]
            predicate = f"{column} in ({', '.join(names)})"
            removed += self.delete_where(predicate, dict(zip(names, batch)))
        return removed

    def purge_where(self, predicate: str, *, confirm: bool = False) -> QueryResult:
        """Hard-delete rows, reclaiming storage. Irreversible.

        Purge is asynchronous, expensive, and rate-limited by the service. Use it
        for erasure obligations, not for routine cleanup.
        """
        if not confirm:
            raise AdxQueryError("purge is irreversible; pass confirm=True to proceed")
        if not predicate.strip():
            raise AdxQueryError("purge_where requires a predicate")
        return self._client.command(
            f".purge table {self._table} records in database {self._client.config.database} "
            f"<| {self._table} | where {predicate}"
        )

    def truncate(self, *, confirm: str = "") -> QueryResult:
        """Drop every extent. Requires the table name as confirmation."""
        if confirm != self._table:
            raise AdxQueryError(f"refusing to truncate {self._table}: pass confirm={self._table!r}")
        return self._client.command(f".clear table {self._table} data")

    def drop(self, *, confirm: str = "") -> QueryResult:
        """Drop the table. Requires the table name as confirmation."""
        if confirm != self._table:
            raise AdxQueryError(f"refusing to drop {self._table}: pass confirm={self._table!r}")
        return self._client.command(f".drop table {self._table} ifexists")

    # ------------------------------------------------------------ maintenance

    def extents(self) -> QueryResult:
        """Extent inventory, for verifying ingestion and delete behaviour."""
        return self._client.command(f".show table {self._table} extents")

    def drop_by_tag(self, tag: str) -> QueryResult:
        """Drop every extent carrying ``tag``, undoing one tagged load."""
        if not tag or '"' in tag:
            raise AdxQueryError(f"invalid drop-by tag {tag!r}")
        return self._client.command(f'.drop extents <| .show table {self._table} extents where tags has "{tag}"')

    @staticmethod
    def new_batch_tag(prefix: str = "batch") -> str:
        """A unique tag for one load, usable for dedupe or rollback."""
        return f"{prefix}_{uuid.uuid4().hex}"
