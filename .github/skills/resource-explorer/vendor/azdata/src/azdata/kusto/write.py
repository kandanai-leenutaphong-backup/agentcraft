"""Kusto write plane — inline ingestion, and the two verbs that do not exist.

WHY THIS EXISTS
---------------
Everything else in this package that writes is a :class:`CrudConnector`.
Kusto is not, and this module is where that difference is stated rather
than papered over. A Kusto table is an append-only extent store: there is
no per-row update, and there is no per-row delete. The closest thing is a
soft-delete over a predicate, run as a management command against the
whole table, with its own retention semantics and its own permissions.

So :class:`KustoIngest` subclasses :class:`IngestConnector` and offers
``ingest`` and ``count`` and nothing else. It does not raise
``NotImplementedError`` from ``update`` and ``delete``, because it does not
have them. A connector that advertises a verb the service cannot honour is
worse than one that never offered it.

**Verification is by row-count delta, and this is the documented
exception.** The package principle is that a write is proved by reading
back the keys it was handed. That principle assumes a key addresses a row.
Here it does not: rows carry whatever identifier the caller's schema uses,
re-ingesting the same payload legitimately produces a second row, and
there is no upsert to make the operation idempotent. So the proof is
weaker on purpose — count before, count after, assert the difference — and
the envelope says so by carrying ``rows_before``, ``rows_after`` and
``delta`` instead of a bare ``verified: true``. See
``IngestConnector`` in ``core/crud.py`` for the same statement in the
contract.

**Ingestion is asynchronous even when the command is synchronous.**
``.set-or-append`` returns when the extent is committed, but the queued
ingestion path returns as soon as the payload is accepted, and rows become
queryable afterwards. The delta check polls; it never sleeps a guessed
interval.

**Inline means small.** ``.set-or-append T <| datatable(...)`` embeds the
rows in the command text. That is right for a seed batch and wrong for a
load: the command is subject to the request payload limit, and a caller
with real volume wants queued ingestion through ``azure-kusto-ingest``,
which this module deliberately does not wrap. :data:`MAX_INLINE_ROWS`
refuses the batch that is too big rather than sending a command that will
be rejected by the service with a less useful message.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
Column names and Kusto types are the caller's, declared once at
construction. Every one of them is validated as a plain identifier before
interpolation, and every *value* is encoded as a typed literal — never
interpolated as text — so a row value cannot become command syntax.

DEPENDENCIES
------------
Standard library, plus ``azure-kusto-data`` behind the connector.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping, Sequence

from azdata.core.breaker import CircuitBreaker
from azdata.core.crud import IngestConnector, WritePolicy
from azdata.core.envelope import is_error
from azdata.kusto.read import KqlConnector

logger = logging.getLogger(__name__)

# Inline ingestion embeds every row in the command text. Beyond this the
# caller wants queued ingestion, and should be told so rather than
# discovering it from a truncated request.
MAX_INLINE_ROWS = 1000

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class KustoIngestError(RuntimeError):
    """A batch was refused before any command was sent."""


def control_connector(connector: KqlConnector) -> KqlConnector:
    """A second connector with the read guards off, for generated commands.

    A flag on the shared connector would be process-wide mutable state that
    an unrelated concurrent read would observe, so one ingest would
    silently un-guard every caller. The same reasoning, and the same
    shape, as ``KustoStats``. Caller query text never reaches the returned
    connector: only commands assembled in this package do.
    """
    return KqlConnector(
        resolve_target=connector._resolve_target,
        credential_provider=connector._credential_provider,
        gate_provider=connector._gate_provider,
        validate_fn=None,       # a control command is not a read-only query
        transform_query=None,   # '| take' on a control command changes it
        error_detail_prefix="Kusto control command failed",
    )


def _identifier(name: Any, what: str) -> str:
    if not name or not _IDENTIFIER.match(str(name)):
        raise KustoIngestError(
            f"'{name}' is not a plain Kusto identifier and will not be "
            f"interpolated as a {what}"
        )
    return str(name)


def kusto_literal(value: Any, kusto_type: str) -> str:
    """Encode one value as a typed KQL literal.

    Never string interpolation of caller data into command syntax: a
    string becomes a JSON-escaped quoted literal, a null becomes the typed
    ``string(null)`` form, and a ``dynamic`` column becomes
    ``dynamic(<json>)``. A value this cannot encode raises rather than
    being coerced, because a coerced value is a silently wrong row.
    """
    ctype = str(kusto_type).lower()
    if value is None:
        return f"{ctype}(null)"
    if ctype == "dynamic":
        return f"dynamic({json.dumps(value, default=str)})"
    if ctype == "bool":
        return "true" if value else "false"
    if ctype in ("int", "long"):
        return str(int(value))
    if ctype in ("real", "double", "decimal"):
        return repr(float(value))
    if ctype == "datetime":
        text = value.isoformat() if hasattr(value, "isoformat") else str(value)
        return f"datetime({json.dumps(text)})"
    if ctype in ("string", "guid", "timespan"):
        text = value if isinstance(value, str) else str(value)
        # json.dumps produces the same escaping KQL string literals use for
        # quotes, backslashes and newlines.
        return json.dumps(text)
    raise KustoIngestError(
        f"'{kusto_type}' is not a Kusto column type this connector can encode "
        "inline; use queued ingestion for it"
    )


class KustoIngest(IngestConnector):
    """Append a small batch of rows to one Kusto table, and prove the delta.

    Args:
        connector: A read-plane :class:`KqlConnector`. Its coordinates,
            credential and throttle gate are reused; the counting query
            keeps its guardrails and a second, unguarded connector is
            built from it for the generated ingestion command.
        table: Table to append to. A plain identifier.
        columns: ``{column name: Kusto type}``, declared once. Rows are
            projected onto exactly these columns in this order, so a row
            carrying an extra field appends nothing extra and a row
            missing one appends a typed null.
        policy: Denies by default, as everywhere else in this package.
    """

    service = "kusto"

    def __init__(
        self,
        *,
        connector: KqlConnector,
        table: str,
        columns: Mapping[str, str],
        policy: WritePolicy | None = None,
        breaker: CircuitBreaker | None = None,
    ) -> None:
        super().__init__(policy=policy, breaker=breaker)
        self._reader = connector
        self._table = _identifier(table, "table")
        self._columns = {
            _identifier(name, "column name"): _identifier(ctype, "column type")
            for name, ctype in dict(columns).items()
        }
        if not self._columns:
            raise KustoIngestError(
                "a Kusto ingest connector needs at least one declared column"
            )
        self._commands = control_connector(connector)

    @property
    def table(self) -> str:
        return self._table

    @property
    def columns(self) -> dict[str, str]:
        return dict(self._columns)

    # ------------------------------------------------------------------
    # Subclass seams.
    # ------------------------------------------------------------------

    async def _do_ingest(self, rows: Sequence[Mapping[str, Any]]) -> None:
        command = self.build_command(rows)
        payload = await self._commands.execute(command)
        if is_error(payload):
            raise KustoIngestError(
                json.loads(payload).get("detail", "the ingest command failed")
            )

    async def count(self, target: str | None = None) -> int:
        table = _identifier(target or self._table, "table")
        rows = await self._query(f"{table} | count")
        if not rows:
            return -1
        value = rows[0].get("Count", rows[0].get("count"))
        return int(value) if value is not None else -1

    async def query(self, query: str, **kwargs: Any) -> str:
        """Delegate to the read plane, guardrails intact."""
        return await self._reader.execute(query, **kwargs)

    # ------------------------------------------------------------------
    # Command construction.
    # ------------------------------------------------------------------

    def build_command(self, rows: Sequence[Mapping[str, Any]]) -> str:
        """``.set-or-append T <| datatable(...) [...]`` for ``rows``.

        Exposed rather than private so a test can pin the exact text sent
        to the service, which is the only way to prove that a row value
        cannot become command syntax.
        """
        if len(rows) > MAX_INLINE_ROWS:
            raise KustoIngestError(
                f"{len(rows)} rows exceeds the inline ingestion limit of "
                f"{MAX_INLINE_ROWS}; use queued ingestion (azure-kusto-ingest) "
                "for a batch this size"
            )
        schema = ", ".join(f"{n}:{t}" for n, t in self._columns.items())
        literals = ", ".join(
            kusto_literal(row.get(name), ctype)
            for row in rows
            for name, ctype in self._columns.items()
        )
        return (
            f".set-or-append {self._table} <| "
            f"datatable({schema}) [{literals}]"
        )

    async def _query(self, query: str) -> list[dict]:
        payload = await self._reader.execute(query)
        if is_error(payload):
            raise KustoIngestError(
                json.loads(payload).get("detail", "the count query failed")
            )
        shaped = json.loads(payload)
        return list(shaped.get("rows") or []) if isinstance(shaped, dict) else []


__all__ = [
    "MAX_INLINE_ROWS",
    "KustoIngest",
    "KustoIngestError",
    "control_connector",
    "kusto_literal",
]
