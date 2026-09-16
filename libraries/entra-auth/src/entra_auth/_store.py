"""Durable, shared storage for the two short-lived records browser sign-in needs.

Module role:
    An expiring key-value store with exactly four operations. Two consumers use it: the
    in-progress sign-in flow, whose record holds a PKCE verifier for the length of a redirect,
    and the browser session, whose record holds a verified identity until the token that
    proved it expires.

Why it is shared rather than in-process:
    The same reason the replay ledger is. A process-local dictionary is defeated by a second
    replica, by a cold start, and by the overlap window of a revision swap — a person signs in
    against one replica and is anonymous to the next, and a revoked session survives in a
    replica that has not restarted. Sign-out that only reaches one replica is not sign-out.

What is deliberately **not** stored:
    Access tokens, refresh tokens, id tokens, and raw session identifiers. A session record
    holds the SHA-256 of its identifier and the identity fields already proved, so read access
    to the table — a support query, a backup, an over-broad role assignment — yields nothing
    that can be presented as a credential.

Fail closed:
    A store that cannot answer raises :class:`RecordStoreUnavailable`. The consumer turns that
    into a refusal. There is no degraded mode in which a session is believed because the store
    was unreachable.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol, runtime_checkable


#: Ceilings on what a store may be asked to hold. Both records it keeps are small and fixed in
#: shape — a sign-in flow and a session identity — so anything larger is a caller defect or an
#: attempt to buy storage with an unauthenticated request.
MAX_RECORD_KEY_LENGTH = 256
MAX_RECORD_BYTES = 4096
MAX_RECORD_FIELDS = 16


class RecordStoreUnavailable(RuntimeError):
    """The store could not answer. Callers must refuse the request."""


@runtime_checkable
class RecordStore(Protocol):
    """An expiring key-value store of small string maps."""

    async def put(self, key: str, record: Mapping[str, str], expires_at: datetime) -> None:
        """Write or replace ``key``. Raises :class:`RecordStoreUnavailable` on failure."""

    async def get(self, key: str) -> dict[str, str] | None:
        """Return the live record, or ``None`` when absent or expired."""

    async def consume(self, key: str) -> dict[str, str] | None:
        """Atomically remove ``key`` and return what it held, or ``None``.

        Exactly one concurrent caller may receive the record. This is not ``get`` followed by
        ``delete``: between those two calls a durable store suspends on network I/O, and a
        second caller reads the same record and is handed the same one-time secret.

        ``None`` covers absent, expired, and lost-the-race, and the three are deliberately
        indistinguishable. Raises :class:`RecordStoreUnavailable` when the answer is unknown,
        because a consumer that cannot tell must refuse rather than admit.
        """

    async def delete(self, key: str) -> None:
        """Remove ``key``. Absent is success: revocation must be idempotent."""

    async def purge_expired(self, *, now: datetime | None = None) -> int:
        """Remove every expired record. Returns how many were removed."""


def _checked(key: str, record: Mapping[str, str]) -> dict[str, str]:
    """Validate one write against the bounds, returning the normalised record."""
    if not key or len(key) > MAX_RECORD_KEY_LENGTH:
        raise ValueError(f"record key must be 1..{MAX_RECORD_KEY_LENGTH} characters")
    fields = {str(name): str(value) for name, value in record.items()}
    if len(fields) > MAX_RECORD_FIELDS:
        raise ValueError(f"a record may hold at most {MAX_RECORD_FIELDS} fields")
    size = sum(len(name.encode("utf-8")) + len(value.encode("utf-8")) for name, value in fields.items())
    if size > MAX_RECORD_BYTES:
        raise ValueError(f"a record may be at most {MAX_RECORD_BYTES} bytes; got {size}")
    return fields


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def _stamp(moment: datetime) -> str:
    """ISO-8601 UTC with a ``Z`` suffix: fixed width, so string ordering is time ordering.

    Table Storage compares strings. A stamp whose width varies — an offset form, a dropped
    fractional part — sorts wrongly, and a purge filtered on it then deletes live rows or
    keeps dead ones.
    """
    return _utc(moment).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class InProcessRecordStore:
    """Bounded in-memory store. Correct for exactly one process, and it says so.

    Legitimate for a workstation and for tests. It is **not** a fallback: nothing selects it
    automatically, because a silent downgrade from a shared store to this one turns sign-out
    into a suggestion.
    """

    kind = "in-process"
    durable = False

    def __init__(self, *, max_entries: int = 8192) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._items: dict[str, tuple[datetime, dict[str, str]]] = {}
        self._lock = asyncio.Lock()

    async def put(self, key: str, record: Mapping[str, str], expires_at: datetime) -> None:
        fields = _checked(key, record)
        async with self._lock:
            self._drop_expired(datetime.now(timezone.utc))
            if key not in self._items and len(self._items) >= self._max_entries:
                raise RecordStoreUnavailable("record store is full")
            self._items[key] = (_utc(expires_at), fields)

    async def get(self, key: str) -> dict[str, str] | None:
        async with self._lock:
            found = self._items.get(key)
            if found is None:
                return None
            expires_at, record = found
            if expires_at <= datetime.now(timezone.utc):
                del self._items[key]
                return None
            return dict(record)

    async def consume(self, key: str) -> dict[str, str] | None:
        """Pop under the same lock that guards every other operation."""
        async with self._lock:
            found = self._items.pop(key, None)
            if found is None:
                return None
            expires_at, record = found
            return None if expires_at <= datetime.now(timezone.utc) else dict(record)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._items.pop(key, None)

    async def purge_expired(self, *, now: datetime | None = None) -> int:
        async with self._lock:
            return self._drop_expired(_utc(now or datetime.now(timezone.utc)))

    def _drop_expired(self, now: datetime) -> int:
        stale = [k for k, (exp, _) in self._items.items() if exp <= now]
        for key in stale:
            del self._items[key]
        return len(stale)

    def __len__(self) -> int:
        return len(self._items)

    def __bool__(self) -> bool:
        # An empty store is still a store. Without this, ``store or fallback`` silently
        # replaces a working one, which is a downgrade wearing the costume of a default.
        return True


class AzureTableRecordStore:
    """Durable, shared store over one Azure Table, reached with a managed identity.

    Entities are ``{PartitionKey, RowKey, ExpiresAt, Payload}`` where ``Payload`` is the JSON
    of the record. No account key is involved anywhere: the credential is an Entra identity
    holding a data-plane role on one dedicated account.

    The account is **dedicated to authentication**. It never shares a store with replay
    datasets — a write path from the auth edge that reaches a telemetry account is a write
    path into telemetry.
    """

    kind = "azure-table"
    durable = True

    def __init__(
        self,
        *,
        endpoint: str,
        table_name: str,
        partition_key: str,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        if not endpoint or not table_name or not partition_key:
            raise ValueError("endpoint, table_name and partition_key are required")
        self._endpoint = endpoint
        self._table_name = table_name
        self._partition = partition_key
        self._client_factory = client_factory or self._default_client_factory
        self._client: Any | None = None
        self._credential: Any | None = None
        self._ensured = False
        self._lock = asyncio.Lock()

    def _default_client_factory(self) -> Any:
        # Imported here, not at module scope, so importing this component costs nothing and
        # needs no Azure identity in a deployment that configures a different store.
        from azure.data.tables.aio import TableClient
        from azure.identity.aio import DefaultAzureCredential

        # Held so it can be closed. The credential owns its own HTTP session, and closing only
        # the table client leaves it open for the life of the process.
        self._credential = DefaultAzureCredential()
        return TableClient(
            endpoint=self._endpoint,
            table_name=self._table_name,
            credential=self._credential,
        )

    @staticmethod
    def _is_conflict(exc: BaseException) -> bool:
        return (
            type(exc).__name__ == "ResourceExistsError"
            or getattr(exc, "status_code", None) == 409
        )

    @staticmethod
    def _is_missing(exc: BaseException) -> bool:
        return (
            type(exc).__name__ == "ResourceNotFoundError"
            or getattr(exc, "status_code", None) == 404
        )

    @staticmethod
    def _lost_claim(exc: BaseException) -> bool:
        """Whether a conditional delete failed because somebody else got there first.

        412 is the precondition failing — another consumer changed or removed the entity
        between the read and the delete. 404 is the same outcome one step further on. Both
        mean this caller did not win, and neither is an error to report.
        """
        return (
            type(exc).__name__ in ("ResourceModifiedError", "ResourceNotFoundError")
            or getattr(exc, "status_code", None) in (404, 412)
        )

    @staticmethod
    def _etag_of(entity: Any) -> str | None:
        metadata = getattr(entity, "metadata", None)
        if isinstance(metadata, Mapping) and metadata.get("etag"):
            return str(metadata["etag"])
        if isinstance(entity, Mapping) and entity.get("odata.etag"):
            return str(entity["odata.etag"])
        return None

    async def _ready(self) -> Any:
        async with self._lock:
            if self._client is None:
                self._client = self._client_factory()
            if not self._ensured:
                try:
                    await self._client.create_table()
                except Exception as exc:
                    if not self._is_conflict(exc):
                        raise RecordStoreUnavailable("record table unavailable") from exc
                self._ensured = True
            return self._client

    async def put(self, key: str, record: Mapping[str, str], expires_at: datetime) -> None:
        fields = _checked(key, record)
        client = await self._ready()
        entity = {
            "PartitionKey": self._partition,
            "RowKey": key,
            "ExpiresAt": _stamp(expires_at),
            "Payload": json.dumps(fields, separators=(",", ":")),
        }
        try:
            await client.upsert_entity(entity)
        except Exception as exc:
            raise RecordStoreUnavailable("record write failed") from exc

    async def get(self, key: str) -> dict[str, str] | None:
        client = await self._ready()
        try:
            entity = await client.get_entity(self._partition, key)
        except Exception as exc:
            if self._is_missing(exc):
                return None
            raise RecordStoreUnavailable("record read failed") from exc
        # Expiry is enforced here, not only by the purge: a record read between its expiry and
        # the next housekeeping run must be dead already.
        if str(entity.get("ExpiresAt", "")) <= _stamp(datetime.now(timezone.utc)):
            return None
        return self._payload_of(entity)

    async def consume(self, key: str) -> dict[str, str] | None:
        """Read, then delete on the exact version that was read. Only a winning delete returns.

        Table Storage gives the primitive directly: ``If-Match`` on the entity's ETag. A second
        consumer arriving between the read and the delete either changed the ETag or removed
        the row, and its precondition fails — so the loser is told nothing and, critically, is
        never handed the record it read.
        """
        client = await self._ready()
        try:
            entity = await client.get_entity(self._partition, key)
        except Exception as exc:
            if self._is_missing(exc):
                return None
            raise RecordStoreUnavailable("record read failed") from exc
        if str(entity.get("ExpiresAt", "")) <= _stamp(datetime.now(timezone.utc)):
            return None
        etag = self._etag_of(entity)
        if etag is None:
            # Without an ETag there is no conditional delete, and an unconditional one would
            # reintroduce the race this method exists to close.
            raise RecordStoreUnavailable("record carries no version to claim it by")
        try:
            await client.delete_entity(
                self._partition, key, etag=etag, match_condition=_if_not_modified(),
            )
        except Exception as exc:
            if self._lost_claim(exc):
                return None
            raise RecordStoreUnavailable("record claim failed") from exc
        return self._payload_of(entity)

    def _payload_of(self, entity: Any) -> dict[str, str] | None:
        try:
            payload = json.loads(str(entity.get("Payload", "{}")))
        except ValueError as exc:
            raise RecordStoreUnavailable("record payload is unreadable") from exc
        return {str(k): str(v) for k, v in payload.items()} if isinstance(payload, dict) else None

    async def delete(self, key: str) -> None:
        client = await self._ready()
        try:
            await client.delete_entity(self._partition, key)
        except Exception as exc:
            if self._is_missing(exc):
                return
            raise RecordStoreUnavailable("record delete failed") from exc

    async def purge_expired(self, *, now: datetime | None = None) -> int:
        client = await self._ready()
        cutoff = _stamp(now or datetime.now(timezone.utc))
        removed = 0
        try:
            entities = client.query_entities(
                "PartitionKey eq @partition and ExpiresAt le @cutoff",
                parameters={"partition": self._partition, "cutoff": cutoff},
            )
            async for entity in entities:
                await client.delete_entity(entity["PartitionKey"], entity["RowKey"])
                removed += 1
        except Exception as exc:
            raise RecordStoreUnavailable("record purge failed") from exc
        return removed

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._ensured = False
        if self._credential is not None:
            await self._credential.close()
            self._credential = None


def _if_not_modified() -> Any:
    """The SDK's If-Match condition. Imported here so the module still imports without it.

    A deployment that reached this line is already using the Azure client, so an ImportError
    means a broken image rather than a different store — and the honest answer is that the
    claim cannot be made safely, not that it can be made unsafely.
    """
    try:
        from azure.core import MatchConditions
    except ImportError as exc:  # pragma: no cover - only on a broken image
        raise RecordStoreUnavailable("the table SDK is unavailable") from exc
    return MatchConditions.IfNotModified


__all__ = [
    "MAX_RECORD_BYTES",
    "MAX_RECORD_FIELDS",
    "MAX_RECORD_KEY_LENGTH",
    "RecordStore",
    "RecordStoreUnavailable",
    "InProcessRecordStore",
    "AzureTableRecordStore",
]
