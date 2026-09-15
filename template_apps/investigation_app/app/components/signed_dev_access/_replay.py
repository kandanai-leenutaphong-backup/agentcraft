"""Replay ledgers — the record that says a signature has already been spent.

The canonical string carries no nonce, so a captured signature is replayable for the whole
skew window unless something remembers it. That memory has to be **shared** and **atomic**:

- shared, because a per-process dictionary is defeated by a second replica, by a cold start,
  and by the overlap window of a revision swap;
- atomic, because two concurrent replays of the same signature must produce exactly one
  winner, which read-then-write cannot guarantee.

Retention is not a TTL chosen for convenience. A key is held until the instant its signature
stops verifying, which the verifier reports as ``VerifyResult.expires_at``. Anything shorter
leaves a gap in which an evicted signature verifies again.

Fail-closed everywhere: a ledger that cannot answer raises :class:`ReplayLedgerUnavailable`,
and the middleware turns that into the same bare 401 as a forged signature. There is no
degraded mode in which requests are admitted without a replay check.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


class ReplayLedgerUnavailable(RuntimeError):
    """The ledger could not decide. Callers must deny the request."""


@runtime_checkable
class ReplayLedger(Protocol):
    """Atomic claim-once store.

    Implementations must make ``claim`` a single atomic operation: exactly one concurrent
    caller may receive ``True`` for a given key.
    """

    async def claim(self, key: str, expires_at: datetime) -> bool:
        """Record ``key`` and return True, or return False when it was already recorded.

        Raises:
            ReplayLedgerUnavailable: When the answer is unknown. Never return True on doubt.
        """


def _utc(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc) if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


#: Ceiling on how many rows one purge removes. Housekeeping that deletes an unbounded number
#: of rows in one call is a long-running loop against a paged query, and purging late is
#: harmless by construction: a row is only ever removed once its signature has stopped
#: verifying, so no cadence can open a replay gap.
MAX_PURGE_ROWS = 5000


def _stamp(moment: datetime) -> str:
    """ISO-8601 UTC with a ``Z`` suffix and fixed width, so string ordering is time ordering.

    Table Storage compares strings. ``isoformat()`` drops the fractional part on a whole
    second, so ``...:05Z`` and ``...:05.123456Z`` differ in width, and ``'Z' > '1'`` makes the
    whole second sort *after* the fraction of the same second. A purge filtered on that
    comparison then selects rows whose signatures still verify.
    """
    return _utc(moment).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _parse_stamp(value: str) -> datetime | None:
    """Read a stamp in either the fixed-width form or the legacy variable-width one.

    Rows written before the width was fixed are still in the table. Returning ``None`` for
    anything unreadable is what keeps the purge honest: a row it cannot date is a row it must
    not delete.
    """
    text = (value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return _utc(parsed)


class InProcessReplayLedger:
    """Bounded in-memory ledger. Correct for exactly one process, and it says so.

    Legitimate for a workstation, a test, and a single-replica deployment that has accepted
    the limitation in writing. It is **not** a fallback: nothing selects it automatically,
    because a silent downgrade from a shared ledger to this one is indistinguishable from
    having no replay protection at all.

    When the bound is reached and nothing has expired it denies rather than evicting a live
    key. Evicting a key whose signature still verifies would reopen the hole under exactly the
    memory pressure an attacker can create.
    """

    #: Names this ledger so a composition root can report which one it built.
    kind = "in-process"
    durable = False

    def __init__(self, *, max_entries: int = 8192) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        self._max_entries = max_entries
        self._seen: dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def claim(self, key: str, expires_at: datetime) -> bool:
        deadline = _utc(expires_at)
        async with self._lock:
            now = datetime.now(timezone.utc)
            for stale in [k for k, exp in self._seen.items() if exp <= now]:
                del self._seen[stale]
            if key in self._seen:
                return False
            if len(self._seen) >= self._max_entries:
                raise ReplayLedgerUnavailable("replay ledger is full")
            self._seen[key] = deadline
            return True

    def __len__(self) -> int:
        return len(self._seen)

    def __bool__(self) -> bool:
        # An empty ledger is still a ledger. Without this, ``ledger or fallback`` silently
        # replaces a perfectly good empty one, which is a security downgrade wearing the
        # costume of a default argument.
        return True


class AzureTableReplayLedger:
    """Durable, shared, atomic ledger over one Azure Table, reached with a managed identity.

    Chosen because Table Storage gives the needed primitive directly: inserting an entity
    whose ``(PartitionKey, RowKey)`` already exists fails with ``ResourceExistsError`` and no
    read-then-write race exists. It costs cents per month at this volume and holds no secret —
    the credential is an Entra identity, never an account key.

    The table is **dedicated to authentication**. It never shares a store with replay
    datasets: a ledger write path that reaches a telemetry account is a write path into
    telemetry.

    Entities are ``{PartitionKey: partition, RowKey: key, ExpiresAt: <iso8601>}``. Nothing
    about the caller, the request, or the key material is stored: the row key is already a
    digest, and an operator reading the table learns only that some signature was spent.

    Table Storage has no server-side TTL, so :meth:`purge_expired` is housekeeping the
    operator runs on a schedule. Purging late is harmless — a row is only removed once its
    signature can no longer verify, so no purge cadence can open a replay gap.
    """

    kind = "azure-table"
    durable = True

    #: One partition holds every key. Table Storage guarantees insert atomicity per entity,
    #: not per partition, so a single partition costs nothing in correctness and keeps
    #: purging a single query.
    DEFAULT_PARTITION = "sig"

    def __init__(
        self,
        *,
        endpoint: str,
        table_name: str,
        partition_key: str = DEFAULT_PARTITION,
        client_factory: Callable[[], Any] | None = None,
    ) -> None:
        """
        Args:
            endpoint: Table service endpoint, e.g.
                ``https://<account>.table.core.windows.net``.
            table_name: Table holding the ledger. Created on first use if absent.
            partition_key: Partition every entity lands in.
            client_factory: Builds the async ``TableClient``. Injected by tests; the default
                builds one with ``DefaultAzureCredential`` and imports the SDK lazily, so
                importing this module costs nothing and needs no Azure identity.
        """
        if not endpoint or not table_name:
            raise ValueError("endpoint and table_name are required")
        self._endpoint = endpoint
        self._table_name = table_name
        self._partition = partition_key
        self._client_factory = client_factory or self._default_client_factory
        self._client: Any | None = None
        self._credential: Any | None = None
        self._ensured = False
        self._lock = asyncio.Lock()

    def _default_client_factory(self) -> Any:
        # Imported here, not at module scope: the SDK is only a dependency of deployments that
        # actually configure this ledger.
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
        """Whether the service refused because the entity already exists.

        Matched by name and by status code rather than by importing the SDK exception, so this
        module stays importable without the SDK installed.
        """
        return (
            type(exc).__name__ == "ResourceExistsError"
            or getattr(exc, "status_code", None) == 409
        )

    async def _ready(self) -> Any:
        async with self._lock:
            if self._client is None:
                self._client = self._client_factory()
            if not self._ensured:
                try:
                    await self._client.create_table()
                except Exception as exc:
                    if not self._is_conflict(exc):
                        raise ReplayLedgerUnavailable("ledger table unavailable") from exc
                self._ensured = True
            return self._client

    async def claim(self, key: str, expires_at: datetime) -> bool:
        client = await self._ready()
        entity = {
            "PartitionKey": self._partition,
            "RowKey": key,
            "ExpiresAt": _stamp(expires_at),
        }
        try:
            await client.create_entity(entity)
        except Exception as exc:
            if self._is_conflict(exc):
                return False
            raise ReplayLedgerUnavailable("ledger write failed") from exc
        return True

    async def purge_expired(
        self, *, now: datetime | None = None, limit: int = MAX_PURGE_ROWS,
    ) -> int:
        """Delete rows whose signatures can no longer verify. Returns how many were removed.

        The query narrows; the parse decides. A legacy row's stamp can sort on the wrong side
        of the cutoff, so every candidate is re-dated before it is deleted and anything
        unreadable or still live is left exactly where it is.
        """
        if limit < 1:
            raise ValueError("limit must be positive")
        client = await self._ready()
        moment = _utc(now or datetime.now(timezone.utc))
        cutoff = _stamp(moment)
        removed = 0
        try:
            entities = client.query_entities(
                "PartitionKey eq @partition and ExpiresAt le @cutoff",
                parameters={"partition": self._partition, "cutoff": cutoff},
            )
            async for entity in entities:
                expires_at = _parse_stamp(str(entity.get("ExpiresAt", "")))
                if expires_at is None or expires_at > moment:
                    continue
                await client.delete_entity(entity["PartitionKey"], entity["RowKey"])
                removed += 1
                if removed >= limit:
                    break
        except Exception as exc:
            raise ReplayLedgerUnavailable("ledger purge failed") from exc
        return removed

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._ensured = False
        if self._credential is not None:
            await self._credential.close()
            self._credential = None


async def claim_or_deny(ledger: ReplayLedger, key: str, expires_at: datetime) -> bool:
    """Claim a key, treating every unavailability as a denial. Never raises."""
    try:
        outcome: bool | Awaitable[bool] = ledger.claim(key, expires_at)
        return bool(await outcome) if hasattr(outcome, "__await__") else bool(outcome)
    except Exception:
        return False
