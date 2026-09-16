"""Remediation battery for the authentication stores: atomic claim, bounds, and honest stamps.

Three defects are pinned here, each with the negative case that proves the check can fail:

* **F3a** ``claim_flow`` read then deleted, so two concurrent callbacks could both be handed
  the same PKCE verifier. The store now owns a single ``consume`` operation and the service
  uses it. A conditional delete that loses is a lost claim, never a returned record.
* **F3b** the replay ledger stamped ``ExpiresAt`` with a variable-width ISO string, so Table
  Storage's string comparison misordered it and a purge could delete a row whose signature
  still verified. The stamp is fixed width now, and the purge re-checks by parsing before it
  deletes anything.
* **F3c** neither store bounded what it was asked to hold.

Pure in-memory. No network, no Azure credential, no secret.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from entra_auth import InProcessRecordStore, RecordStoreUnavailable
from entra_auth._store import (
    MAX_RECORD_BYTES,
    MAX_RECORD_KEY_LENGTH,
    AzureTableRecordStore,
)
from signed_dev_access._replay import (
    MAX_PURGE_ROWS,
    AzureTableReplayLedger,
    _stamp,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _later(seconds: int = 300) -> datetime:
    return _now() + timedelta(seconds=seconds)


# --- fakes modelling exactly the two Table Storage behaviours that matter -------------------


class ResourceNotFoundError(Exception):
    status_code = 404


class ResourceModifiedError(Exception):
    """What the service raises when an If-Match precondition fails."""

    status_code = 412


class ResourceExistsError(Exception):
    status_code = 409


class _Table:
    """One shared backing table. Independent clients hold a reference to the same instance."""

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], dict] = {}
        self.version = 0
        self.deletes = 0

    def put(self, pk: str, rk: str, entity: dict) -> None:
        self.version += 1
        self.rows[(pk, rk)] = {**entity, "odata.etag": f"W/\"{self.version}\""}


class _FakeTableClient:
    """Async table client with a suspension point at every call, as a network client has.

    The suspension is the whole point: the race the audit found needs one, and an in-memory
    dict has none, which is why it did not reproduce over ``InProcessRecordStore``.
    """

    def __init__(self, table: _Table) -> None:
        self._table = table
        self.closed = False

    async def create_table(self) -> None:
        await asyncio.sleep(0)

    async def upsert_entity(self, entity: dict) -> None:
        await asyncio.sleep(0)
        self._table.put(entity["PartitionKey"], entity["RowKey"], entity)

    async def create_entity(self, entity: dict) -> None:
        await asyncio.sleep(0)
        key = (entity["PartitionKey"], entity["RowKey"])
        if key in self._table.rows:
            raise ResourceExistsError("already spent")
        self._table.put(*key, entity)

    async def get_entity(self, pk: str, rk: str) -> dict:
        await asyncio.sleep(0)
        row = self._table.rows.get((pk, rk))
        if row is None:
            raise ResourceNotFoundError("no such entity")
        return dict(row)

    async def delete_entity(self, pk: str, rk: str, *, etag: str | None = None,
                            match_condition=None) -> None:
        await asyncio.sleep(0)
        key = (pk, rk)
        row = self._table.rows.get(key)
        if row is None:
            raise ResourceNotFoundError("no such entity")
        if etag is not None and row.get("odata.etag") != etag:
            raise ResourceModifiedError("etag mismatch")
        del self._table.rows[key]
        self._table.deletes += 1

    def query_entities(self, query: str, parameters: dict | None = None):
        rows = list(self._table.rows.values())
        cutoff = (parameters or {}).get("cutoff", "")

        async def _iter():
            for row in rows:
                await asyncio.sleep(0)
                if str(row.get("ExpiresAt", "")) <= cutoff:
                    yield row

        return _iter()

    async def close(self) -> None:
        self.closed = True


def _store(table: _Table, partition: str = "flow") -> AzureTableRecordStore:
    return AzureTableRecordStore(
        endpoint="https://example.table.core.windows.net",
        table_name="t",
        partition_key=partition,
        client_factory=lambda: _FakeTableClient(table),
    )


def _ledger(table: _Table) -> AzureTableReplayLedger:
    return AzureTableReplayLedger(
        endpoint="https://example.table.core.windows.net",
        table_name="t",
        client_factory=lambda: _FakeTableClient(table),
    )


# --- F3a: exactly one consumer ------------------------------------------------------------


@pytest.mark.asyncio
async def test_in_process_consume_has_one_winner_under_concurrency() -> None:
    store = InProcessRecordStore()
    await store.put("f1", {"state": "s"}, _later())
    results = await asyncio.gather(*(store.consume("f1") for _ in range(50)))
    assert sum(1 for r in results if r is not None) == 1
    assert await store.get("f1") is None


@pytest.mark.asyncio
async def test_azure_table_consume_has_one_winner_across_independent_clients() -> None:
    """Fifty concurrent consumes across two independent store objects on one table."""
    table = _Table()
    left, right = _store(table), _store(table)
    await left.put("f1", {"state": "s"}, _later())

    results = await asyncio.gather(
        *(( left if index % 2 == 0 else right).consume("f1") for index in range(50))
    )
    winners = [r for r in results if r is not None]
    assert len(winners) == 1, f"{len(winners)} callers were handed the same flow"
    assert winners[0]["state"] == "s"
    assert table.deletes == 1
    assert ("flow", "f1") not in table.rows


@pytest.mark.asyncio
async def test_consume_never_returns_a_record_whose_delete_lost() -> None:
    """A losing conditional delete yields nothing. Reading is not claiming."""
    table = _Table()
    store = _store(table)
    await store.put("f1", {"state": "s"}, _later())
    client = await store._ready()

    original = client.delete_entity

    async def losing(*args, **kwargs):
        await original(*args)  # somebody else won; drop the precondition to model that
        raise ResourceModifiedError("etag mismatch")

    client.delete_entity = losing
    assert await store.consume("f1") is None


@pytest.mark.asyncio
async def test_consume_of_a_missing_record_is_none_not_an_error() -> None:
    assert await _store(_Table()).consume("nope") is None


@pytest.mark.asyncio
async def test_consume_fails_closed_when_the_store_is_broken() -> None:
    table = _Table()
    store = _store(table)
    await store.put("f1", {"state": "s"}, _later())
    client = await store._ready()

    async def broken(*args, **kwargs):
        raise RuntimeError("service unreachable")

    client.get_entity = broken
    with pytest.raises(RecordStoreUnavailable):
        await store.consume("f1")


@pytest.mark.asyncio
async def test_consume_honours_expiry() -> None:
    table = _Table()
    store = _store(table)
    await store.put("f1", {"state": "s"}, _now() - timedelta(seconds=1))
    assert await store.consume("f1") is None


# --- F3c: bounds --------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("store_factory", [
    lambda: InProcessRecordStore(),
    lambda: _store(_Table()),
])
async def test_put_refuses_an_oversized_record(store_factory) -> None:
    store = store_factory()
    with pytest.raises(ValueError):
        await store.put("k", {"blob": "x" * (MAX_RECORD_BYTES + 1)}, _later())


@pytest.mark.asyncio
@pytest.mark.parametrize("store_factory", [
    lambda: InProcessRecordStore(),
    lambda: _store(_Table()),
])
async def test_put_refuses_an_oversized_key(store_factory) -> None:
    store = store_factory()
    with pytest.raises(ValueError):
        await store.put("k" * (MAX_RECORD_KEY_LENGTH + 1), {"a": "b"}, _later())


# --- F3b: the stamp is fixed width, and the purge proves expiry before deleting ------------


def test_stamp_is_fixed_width_whatever_the_microsecond() -> None:
    widths = {
        len(_stamp(datetime(2026, 1, 2, 3, 4, 5, micros, tzinfo=timezone.utc)))
        for micros in (0, 1, 999, 123456, 999999)
    }
    assert widths == {len(_stamp(_now()))}


def test_stamp_orders_as_time_orders() -> None:
    """The failure mode: a whole second sorting below a fraction of the same second."""
    early = _stamp(datetime(2026, 1, 2, 3, 4, 5, 0, tzinfo=timezone.utc))
    late = _stamp(datetime(2026, 1, 2, 3, 4, 5, 123456, tzinfo=timezone.utc))
    assert early < late


def test_stamp_normalises_a_naive_or_offset_datetime_to_utc() -> None:
    aware = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone(timedelta(hours=8)))
    assert _stamp(aware) == _stamp(datetime(2026, 1, 1, 19, 4, 5, tzinfo=timezone.utc))


@pytest.mark.asyncio
async def test_purge_never_deletes_a_legacy_row_that_has_not_expired() -> None:
    """Parsing, not string order, decides what is dead.

    A stamp carrying a negative UTC offset sorts *below* the cutoff while naming an instant in
    the future — the exact shape a variable-width writer can leave behind. The query returns
    it; the purge must still refuse to delete it.
    """
    table = _Table()
    ledger = _ledger(table)
    live = _now() + timedelta(seconds=600)
    dead = _now() - timedelta(seconds=600)
    table.put("sig", "legacy-live", {
        "PartitionKey": "sig", "RowKey": "legacy-live",
        "ExpiresAt": live.astimezone(timezone(timedelta(hours=-8))).isoformat(),
    })
    table.put("sig", "legacy-dead", {
        "PartitionKey": "sig", "RowKey": "legacy-dead",
        "ExpiresAt": dead.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    })
    removed = await ledger.purge_expired()
    assert removed == 1
    assert ("sig", "legacy-live") in table.rows
    assert ("sig", "legacy-dead") not in table.rows


@pytest.mark.asyncio
async def test_purge_skips_an_unparseable_stamp_rather_than_deleting_it() -> None:
    table = _Table()
    # Sorts below every real stamp, so the query offers it; it must survive anyway.
    table.put("sig", "junk", {"PartitionKey": "sig", "RowKey": "junk", "ExpiresAt": "0000-bad"})
    table.put("sig", "blank", {"PartitionKey": "sig", "RowKey": "blank", "ExpiresAt": ""})
    assert await _ledger(table).purge_expired() == 0
    assert ("sig", "junk") in table.rows
    assert ("sig", "blank") in table.rows


@pytest.mark.asyncio
async def test_purge_is_bounded() -> None:
    table = _Table()
    dead = _stamp(_now() - timedelta(seconds=600))
    for index in range(MAX_PURGE_ROWS + 25):
        table.put("sig", f"r{index}", {
            "PartitionKey": "sig", "RowKey": f"r{index}", "ExpiresAt": dead,
        })
    removed = await _ledger(table).purge_expired()
    assert removed == MAX_PURGE_ROWS
    assert len(table.rows) == 25


@pytest.mark.asyncio
async def test_purge_limit_is_caller_boundable() -> None:
    table = _Table()
    dead = _stamp(_now() - timedelta(seconds=600))
    for index in range(10):
        table.put("sig", f"r{index}", {
            "PartitionKey": "sig", "RowKey": f"r{index}", "ExpiresAt": dead,
        })
    assert await _ledger(table).purge_expired(limit=4) == 4
    assert len(table.rows) == 6


@pytest.mark.asyncio
async def test_replay_claim_still_refuses_a_second_spend() -> None:
    """The stamp change must not weaken the primitive it is stamping."""
    table = _Table()
    ledger = _ledger(table)
    assert await ledger.claim("k", _later()) is True
    assert await ledger.claim("k", _later()) is False
