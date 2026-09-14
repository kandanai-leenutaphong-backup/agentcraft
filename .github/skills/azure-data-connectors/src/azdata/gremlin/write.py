"""Gremlin write plane — mutation traversals this module builds, never ones
a caller hands it.

WHY THIS EXISTS
---------------
Gremlin has no write API. You write by submitting a traversal that mutates,
which puts a write plane in direct conflict with the read plane's own
safety machinery and with four specific production failures.

**The read-only guardrail is in the way, by design.** ``_GREMLIN_WRITE_RE``
in :mod:`._guardrails` refuses ``.addV(``, ``.addE(``, ``.drop(`` and
``.property(``, and it is right to: the read connector executes traversals
that arrived from outside. A write plane must get past it. The whole safety
model of this module is *which* traversals get past it: mutations are built
here from structured items, so the only text that bypasses the guard is
text this module generated character by character. A caller-supplied
traversal never bypasses it — :meth:`GremlinElements.query` goes to the
read-only connector, keeps the guard and keeps the limit injection.

**String interpolation into a traversal is injection.** A property value
containing an apostrophe closes the literal and everything after it is
executable Gremlin; ``o'brien`` is a name, and ``x' ; g.V().drop() ; '`` is
a graph wipe with the same shape. Every literal in every generated
traversal goes through :func:`_literal`, which escapes or refuses. No
f-string and no ``str.format`` ever sees a raw caller value.

**``drop()`` on a traversal matching nothing succeeds silently.** No error,
no count, no signal. A delete against a key that was never there and a
delete that failed to match look identical. So a delete's per-item result
is decided by a count taken *before* the drop, and ``verify=True`` re-reads
afterwards through the base class's polling machinery (GOTCHAS.md, and
:class:`._crud.CrudConnector`).

**``addV`` is not idempotent.** Re-running a load creates a second vertex
with the same id, or errors, depending on the partition (GOTCHAS.md G13).
:meth:`~GremlinElements.upload` therefore emits the
``fold().coalesce(unfold(), addV(...))`` upsert form, and
:meth:`~GremlinElements.create` checks existence first rather than
discovering the duplicate later.

**Cosmos needs the partition key on every vertex.** A vertex written
without its partition key property is stored and is not retrievable by
point lookup; the failure surfaces much later as an empty read. Items
lacking it are refused before a single traversal is built.

WHAT THIS IS NOT
----------------
Not a bulk loader. Every element is one round trip at roughly four writes
per second (G13); anything time-sensitive belongs in a bulk-import path
against a different API. Not a query builder — it emits exactly the five
traversal shapes above and nothing composable.

DEPENDENCIES
------------
Standard library, plus :class:`._gremlin.GremlinConnector` for transport.
No SDK is imported here: the driver loads inside that connector, on first
use.
"""

from __future__ import annotations

import json
import logging
import math
import re
from typing import Any, Callable, Sequence

from azdata.core.config import AzureDataConfig
from azdata.core.crud import CrudConnector, WritePolicy
from azdata.core.envelope import is_error
from azdata.gremlin.read import GremlinConnector

logger = logging.getLogger(__name__)

# Groovy string escapes. Backslash is in the map so a value ending in one
# cannot escape the closing quote.
_STRING_ESCAPES = {
    "\\": "\\\\",
    "'": "\\'",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}

# Control characters with no escape form. Refused rather than stripped: a
# value the caller cannot see in the traversal is a value they cannot debug.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class GremlinWriteError(RuntimeError):
    """A generated traversal was submitted and the service refused it."""


def _literal(value: Any) -> str:
    """Render ``value`` as a Gremlin literal that cannot break out.

    The single chokepoint for caller data entering a traversal. Types are
    allow-listed: an unsupported type raises rather than falling through to
    ``str()``, because interpolating a dict's ``repr`` produces syntax that
    happens to parse and means something else.
    """
    if value is None:
        return "null"
    # bool before int: bool is an int subclass and would render as 1/0.
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError("Gremlin literal cannot be NaN or infinity")
        return repr(value)
    if isinstance(value, str):
        if _CONTROL_RE.search(value):
            raise ValueError(
                "Gremlin literal contains a control character with no escape "
                "form; strip it before writing"
            )
        return "'" + "".join(_STRING_ESCAPES.get(ch, ch) for ch in value) + "'"
    raise TypeError(
        f"Gremlin literal must be str, bool, int, float or None, not "
        f"{type(value).__name__}. Serialise it before writing."
    )


class GremlinElements(CrudConnector):
    """Vertex CRUD over one Cosmos DB graph, by generated traversal.

    Args:
        connector: The read-only :class:`~._gremlin.GremlinConnector` this
            instance borrows its coordinates and credential from. Injected
            so the driver handling, client cache, token rebuild (G1) and
            worker-thread event loop (G2) live in exactly one place.
        label: Vertex label written by ``create`` and ``upload``.
        partition_key_field: Item field carrying the Cosmos partition key.
            Required on every item; a vertex without it is unreadable by
            point lookup.
        key_field: Item field carrying the vertex id.
    """

    service = "gremlin"

    def __init__(
        self,
        connector: GremlinConnector,
        *,
        label: str,
        partition_key_field: str,
        key_field: str = "id",
        policy: WritePolicy | None = None,
        breaker: Any = None,
        gate_provider: Callable[[], Any] | None = None,
    ) -> None:
        super().__init__(
            policy=policy,
            breaker=breaker,
            gate_provider=gate_provider,
            key_field=key_field,
        )
        self._reader = connector
        self._label = label
        self._partition_key_field = partition_key_field
        # A second connector rather than a flag on the shared one: a flag is
        # process-wide mutable state that an unrelated concurrent read would
        # observe, so one racing write would silently un-guard every caller.
        self._mutations = GremlinConnector(
            resolve_target=connector._resolve_target,
            credential_provider=connector._credential_provider,
            token_scope=connector._token_scope,
            validate_fn=None,          # generated traversals must mutate
            transform_query=None,      # a limit on an upsert writes fewer elements
            token_refresh_margin_secs=connector._refresh_margin,
            not_configured_detail="Gremlin endpoint not configured.",
            error_detail_prefix="Gremlin mutation failed",
        )

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        label: str,
        partition_key_field: str,
        policy: WritePolicy | None = None,
        **kwargs: Any,
    ) -> "GremlinElements":
        """Build both connectors from a frozen config."""
        return cls(
            GremlinConnector.from_config(config, credential_provider),
            label=label,
            partition_key_field=partition_key_field,
            policy=policy,
            **kwargs,
        )

    @property
    def label(self) -> str:
        return self._label

    @property
    def partition_key_field(self) -> str:
        return self._partition_key_field

    # ------------------------------------------------------------------
    # Write seams. Every traversal below is assembled here; no caller text
    # reaches the unguarded connector.
    # ------------------------------------------------------------------

    async def _do_create(self, items: Sequence[dict]) -> list[dict]:
        self._require_partition_keys(items)
        results: list[dict] = []
        for item in items:
            key = self._key_of(item)
            try:
                # addV on an existing id duplicates or errors depending on
                # the partition, so existence is checked, not assumed.
                if await self._count(key):
                    results.append(
                        {
                            "key": key,
                            "ok": False,
                            "detail": f"a vertex with this {self._key_field} already exists",
                        }
                    )
                    continue
                await self._submit(
                    f"g.addV({_literal(self._label)})"
                    f"{self._identity_steps(item)}{self._property_steps(item)}"
                )
                results.append({"key": key, "ok": True, "detail": "created"})
            except Exception as exc:  # noqa: BLE001 - per item: one bad item is not a batch failure
                results.append({"key": key, "ok": False, "detail": str(exc)[:300]})
        return results

    async def _do_upload(self, items: Sequence[dict]) -> list[dict]:
        self._require_partition_keys(items)
        results: list[dict] = []
        for item in items:
            key = self._key_of(item)
            try:
                # The properties trail the coalesce so they land on both the
                # newly created and the already-present vertex (G13).
                await self._submit(
                    f"g.V().has({_literal(self._key_field)}, {_literal(key)})"
                    f".fold().coalesce(unfold(), addV({_literal(self._label)})"
                    f"{self._identity_steps(item)})"
                    f"{self._property_steps(item)}"
                )
                results.append({"key": key, "ok": True, "detail": "upserted"})
            except Exception as exc:  # noqa: BLE001 - per item
                results.append({"key": key, "ok": False, "detail": str(exc)[:300]})
        return results

    async def _do_read(self, key: Any, **kwargs: Any) -> dict | None:
        rows = await self._submit(
            f"g.V().has({_literal(self._key_field)}, {_literal(key)}).valueMap(true)"
        )
        return rows[0] if rows else None

    async def _do_delete(self, keys: Sequence[Any], **kwargs: Any) -> list[dict]:
        results: list[dict] = []
        for key in keys:
            try:
                # drop() on a traversal matching nothing returns without an
                # error and without a count, so the count before it is the
                # only thing that can tell a delete from a no-op.
                present = await self._count(key)
                if not present:
                    results.append(
                        {"key": key, "ok": False, "detail": "no vertex matched"}
                    )
                    continue
                await self._submit(
                    f"g.V().has({_literal(self._key_field)}, {_literal(key)}).drop()"
                )
                results.append({"key": key, "ok": True, "detail": "dropped"})
            except Exception as exc:  # noqa: BLE001 - per item
                results.append({"key": key, "ok": False, "detail": str(exc)[:300]})
        return results

    async def query(self, query: str, **kwargs: Any) -> str:
        """Run a caller-supplied traversal on the READ-ONLY connector.

        Deliberately not the mutation connector: text from outside keeps
        the write guard and the limit injection. The bypass in this module
        applies only to traversals it built itself.
        """
        return await self._reader.execute(query, **kwargs)

    # ------------------------------------------------------------------
    # Internals.
    # ------------------------------------------------------------------

    def _require_partition_keys(self, items: Sequence[dict]) -> None:
        """Refuse the batch before a traversal exists when the key is absent.

        Raised for the chunk rather than recorded per item: a caller that
        omitted the partition key has a mapping bug, and writing the
        remainder produces a half-loaded graph to clean up.
        """
        missing = [
            i for i, item in enumerate(items)
            if item.get(self._partition_key_field) is None
        ]
        if missing:
            raise ValueError(
                f"{len(missing)} item(s) have no '{self._partition_key_field}' "
                f"value (first at index {missing[0]}); a vertex written without "
                "its Cosmos partition key is not retrievable by point lookup"
            )

    def _identity_steps(self, item: dict) -> str:
        """The id and partition key properties every new vertex must carry."""
        return (
            f".property({_literal(self._key_field)}, {_literal(self._key_of(item))})"
            f".property({_literal(self._partition_key_field)}, "
            f"{_literal(item[self._partition_key_field])})"
        )

    def _property_steps(self, item: dict) -> str:
        """Remaining item fields, in insertion order, each escaped."""
        reserved = (self._key_field, self._partition_key_field)
        return "".join(
            f".property({_literal(name)}, {_literal(value)})"
            for name, value in item.items()
            if name not in reserved
        )

    async def _count(self, key: Any) -> int:
        rows = await self._submit(
            f"g.V().has({_literal(self._key_field)}, {_literal(key)}).count()"
        )
        return int(rows[0]) if rows else 0

    async def _submit(self, traversal: str) -> list:
        """Execute a generated traversal, turning an error envelope into a raise.

        The connector returns failure as a value; the ``_do_*`` seams above
        are specified to raise, and the base class turns that back into an
        envelope at the boundary.
        """
        payload = await self._mutations.execute(traversal)
        if is_error(payload):
            raise GremlinWriteError(json.loads(payload).get("detail", "traversal failed"))
        parsed = json.loads(payload)
        return parsed if isinstance(parsed, list) else [parsed]


__all__ = ["GremlinElements", "GremlinWriteError"]
