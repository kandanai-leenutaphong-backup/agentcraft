"""Cosmos NoSQL write plane — item CRUD where the partition key is the whole
problem.

WHY THIS EXISTS
---------------
``CosmosContainer`` hands out a container client and lets the caller write
its own operations. That is right for reads and wrong for writes, because
every Cosmos write is partition-scoped and the SDK will not tell you when
you scoped it wrongly in the way that matters.

Three specific production failures this module exists to prevent:

* **A delete that deletes nothing and reports success.**
  ``delete_item(id, partition_key=<wrong>)`` raises 404, identically to a
  delete of an item that was already gone. A caller that treats "already
  gone" as success leaves the item in the container and tells its operator
  the delete worked. Here a 404 from a delete is a *failed* per-item result
  carried in ``failed``, never an ``ok`` one, and never swallowed.
* **A verification read that proves the wrong thing.**
  ``read_item(id, partition_key=<wrong>)`` also raises 404, so re-reading
  with the same wrong key "confirms" the delete. Verification is only
  meaningful against a partition key the caller actually supplied, so
  reads *require* one: there is no default, and no fallback.
* **A cross-partition scan where a point read was meant.** A
  cross-partition query costs orders of magnitude more RU than a point
  read, and on a large container it is the difference between a query and
  a throttling incident. On ``azure-cosmos`` 4.x there is no
  ``enable_cross_partition_query`` flag any more — it was a 3.x argument,
  and 4.x ``query_items`` takes ``**kwargs``, so passing it raises nothing
  and does nothing while reading as though scoping were enforced. In 4.x a
  query is cross-partition exactly when no ``partition_key`` is supplied,
  so :meth:`CosmosItems.query` passes the key when the caller gave one and
  omits it otherwise, and never invents one to recover from a key it could
  not determine.

The design consequence runs through the whole module: the connector is
constructed with an explicit ``partition_key_field`` — the path segment
name, e.g. ``"site"`` — and derives the partition key value from each
item. ``_key_of`` therefore returns the ``(id, partition_key)`` pair, so
that the base class's post-write verification re-reads with a key it can
actually scope. ``read`` and ``delete`` accept either that pair or a bare
id plus an explicit ``partition_key`` argument. When neither yields a
partition key, the operation fails with a ``ValueError`` naming the field:
an unqualified read is a bug in the caller, not a lookup that happens to
be broad.

Cosmos has no batch write API. ``WritePolicy.max_batch`` still chunks, so
the breaker and throttle gate see one acquisition per chunk rather than
one per item, but every item is a separate request and every item's
outcome is reported.

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
``partition_key_field`` and ``key_field`` are parameters. No field name
from any consuming application appears in this file.

WHAT THIS IS NOT
----------------
Not a transaction manager: Cosmos transactional batch is a different API
with a same-partition constraint, and is not wrapped here. Not an ORM.
Not a replacement for ``CosmosContainer``, which still owns connection
health and the bounded probe.

DEPENDENCIES
------------
Standard library, plus ``azure-cosmos`` loaded on first use.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, Sequence

from azdata.core.breaker import CircuitBreaker
from azdata.core.config import AzureDataConfig
from azdata.core.crud import CrudConnector, WritePolicy
from azdata.core.envelope import error_envelope
from azdata.core.guardrails import ensure_limit, validate_read_only
from azdata.core.optional import load

logger = logging.getLogger(__name__)

# Cosmos raises one exception type for everything and distinguishes on the
# HTTP status. Read via getattr so azure.cosmos.exceptions is never imported
# at module scope, which would defeat the optional-SDK contract.
_NOT_FOUND = 404
_CONFLICT = 409


def _status_of(exc: Exception) -> int | None:
    return getattr(exc, "status_code", None)


class CosmosItems(CrudConnector):
    """Create, retrieve, upload and delete items in one Cosmos container.

    The container client is injected rather than constructed, for the same
    reason as :class:`~azdata.cosmos.read.CosmosContainer`: the class is then
    unit-testable with a double and carries no import-time dependency on
    the Azure SDK. Use :meth:`connect` for the normal path.

    Args:
        container: An **async** ``ContainerProxy``. The aio client is used
            deliberately and is not wrapped in a thread: it is genuinely
            async, and ``asyncio.to_thread`` around it would add a hop and
            a thread per item.
        partition_key_field: Name of the field holding the partition key
            value, matching the container's partition key path.
        key_field: Name of the item id field. ``"id"`` in every Cosmos
            container, but a parameter so no schema knowledge is baked in.
    """

    service = "cosmos"

    def __init__(
        self,
        *,
        container: Any,
        partition_key_field: str,
        key_field: str = "id",
        policy: WritePolicy | None = None,
        breaker: CircuitBreaker | None = None,
        gate_provider: Callable[[], Any] | None = None,
        client: Any = None,
    ) -> None:
        super().__init__(
            policy=policy,
            breaker=breaker,
            gate_provider=gate_provider,
            key_field=key_field,
        )
        self._container = container
        self._partition_key_field = partition_key_field
        # Only set when connect() built the client; close() must not close a
        # client the caller owns and may still be using.
        self._owned_client = client

    @classmethod
    def connect(
        cls,
        *,
        endpoint: str,
        database: str,
        container: str,
        credential: Any,
        partition_key_field: str,
        **kwargs: Any,
    ) -> "CosmosItems":
        """Build the async Cosmos client and return a wired write plane."""
        aio = load("azure.cosmos.aio", dist="azure-cosmos")
        client = aio.CosmosClient(url=endpoint, credential=credential)
        container_client = client.get_database_client(database).get_container_client(
            container
        )
        return cls(
            container=container_client,
            partition_key_field=partition_key_field,
            client=client,
            **kwargs,
        )

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        *,
        database: str,
        container: str,
        partition_key_field: str,
        policy: WritePolicy | None = None,
        **kwargs: Any,
    ) -> "CosmosItems":
        return cls.connect(
            endpoint=config.cosmos_endpoint,
            database=database,
            container=container,
            credential=credential_provider(),
            partition_key_field=partition_key_field,
            policy=policy,
            **kwargs,
        )

    @property
    def container(self) -> Any:
        return self._container

    @property
    def partition_key_field(self) -> str:
        return self._partition_key_field

    # ------------------------------------------------------------------
    # Key handling. The reason this class exists.
    # ------------------------------------------------------------------

    def _key_of(self, item: dict) -> Any:
        """Return ``(id, partition_key)``, or None when the id is missing.

        The pair, not the bare id, because the base class verifies a write
        by re-reading the keys it was handed and a bare id cannot be read.
        None when the id is absent so the base's missing-key guard still
        fires instead of accepting ``(None, ...)``.
        """
        item_id = item.get(self._key_field)
        if item_id is None:
            return None
        return (item_id, item.get(self._partition_key_field))

    def _resolve(self, key: Any, partition_key: Any = None) -> tuple[Any, Any]:
        """Split ``key`` into ``(id, partition_key)`` or refuse.

        Accepts a bare id with an explicit ``partition_key``, or the
        ``(id, partition_key)`` pair produced by :meth:`_key_of`. Refusing
        is the point: without a partition key the only alternatives are a
        cross-partition scan or a 404 that means nothing.
        """
        if isinstance(key, tuple) and len(key) == 2:
            item_id, derived = key
        else:
            item_id, derived = key, None
        resolved = derived if derived is not None else partition_key
        if resolved is None:
            raise ValueError(
                f"no partition key for item '{item_id}': supply "
                f"partition_key=, or an item carrying "
                f"'{self._partition_key_field}'. An unqualified read or "
                "delete would 404 without proving anything."
            )
        return item_id, resolved

    # ------------------------------------------------------------------
    # Subclass seams.
    # ------------------------------------------------------------------

    async def _do_create(self, items: Sequence[dict]) -> list[dict]:
        results: list[dict] = []
        for item in items:
            key = self._key_of(item)
            try:
                await self._container.create_item(body=item)
            except Exception as exc:  # noqa: BLE001 - 409 is an outcome, not a fault
                if _status_of(exc) != _CONFLICT:
                    raise
                results.append({"key": key, "ok": False, "detail": "already exists"})
                continue
            results.append({"key": key, "ok": True, "detail": "created"})
        return results

    async def _do_upload(self, items: Sequence[dict]) -> list[dict]:
        results: list[dict] = []
        for item in items:
            await self._container.upsert_item(body=item)
            results.append({"key": self._key_of(item), "ok": True, "detail": "upserted"})
        return results

    async def _do_read(self, key: Any, *, partition_key: Any = None) -> dict | None:
        item_id, pk = self._resolve(key, partition_key)
        try:
            return await self._container.read_item(item=item_id, partition_key=pk)
        except Exception as exc:  # noqa: BLE001 - absence is an answer
            if _status_of(exc) == _NOT_FOUND:
                return None
            raise

    async def _do_delete(
        self, keys: Sequence[Any], *, partition_key: Any = None
    ) -> list[dict]:
        results: list[dict] = []
        for key in keys:
            item_id, pk = self._resolve(key, partition_key)
            try:
                await self._container.delete_item(item=item_id, partition_key=pk)
            except Exception as exc:  # noqa: BLE001 - 404 is a failed delete here
                if _status_of(exc) != _NOT_FOUND:
                    raise
                # Not "already gone": the same 404 is returned for a wrong
                # partition key, and reporting ok would hide a live item.
                results.append(
                    {
                        "key": key,
                        "ok": False,
                        "detail": (
                            "not found under the supplied partition key; the "
                            "item may still exist under another"
                        ),
                    }
                )
                continue
            results.append({"key": key, "ok": True, "detail": "deleted"})
        return results

    async def query(
        self,
        query: str,
        *,
        parameters: list[dict] | None = None,
        partition_key: Any = None,
        max_rows: int | None = None,
    ) -> str:
        """Run a Cosmos SQL query and return ``{"results": [...], "count": n}``.

        Read-only and row-bounded through the shared guardrails, and
        partition-scoped whenever the caller can say where to look.

        Scoping is the presence of ``partition_key`` and nothing else.
        ``enable_cross_partition_query`` does not exist on 4.x
        ``query_items``; because that method takes ``**kwargs`` the removed
        flag is absorbed silently, so sending it would look like an
        enforced scope while changing nothing at all.
        """
        violation = validate_read_only(query, "sql")
        if violation:
            return error_envelope(violation)
        bounded = ensure_limit(query, "sql", max_rows)

        params: dict[str, Any] = {
            "query": bounded,
            "parameters": parameters or [],
        }
        if partition_key is not None:
            params["partition_key"] = partition_key

        async def _run() -> list[dict]:
            rows: list[dict] = []
            async for row in self._container.query_items(**params):
                rows.append(row)
            return rows

        try:
            rows = await self._guarded(_run)
        except Exception as exc:  # noqa: BLE001 - boundary: failure is a value
            return self._failure("query", exc)
        return json.dumps({"results": rows, "count": len(rows)}, default=str)

    async def close(self) -> None:
        """Close the client this connector built. Never the credential (G8)."""
        if self._owned_client is not None:
            await self._owned_client.close()


__all__ = ["CosmosItems"]
