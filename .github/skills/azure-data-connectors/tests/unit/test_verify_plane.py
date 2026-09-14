"""test_verify_plane — what changed, and did anything change that nobody asked.

Run: ``python3 -m pytest tests/unit/test_verify_plane.py``.

Fakes are installed through ``azdata.core.optional.override`` or injected
directly, the same idiom as ``tests/unit/selftest.py``. No SDK, no network,
no cloud account.

Every positive here has its negative, because a verifier that cannot fail
cannot pass. The negatives assert on the **digest** where the point is that
a count would not have caught it.
"""

from __future__ import annotations

import json
import random
import re
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.core.config import AzureDataConfig  # noqa: E402
from azdata.core.crud import WritePolicy  # noqa: E402
from azdata.core.journal import OperationJournal  # noqa: E402
from azdata.core.optional import clear_overrides  # noqa: E402
from azdata.core.verify import (  # noqa: E402
    Effect,
    StateDelta,
    StateSnapshot,
    capture,
    key_digest,
    snapshot,
    verify_effect,
)
from azdata.cosmos.observe import CosmosStats  # noqa: E402
from azdata.cosmos.verify import CosmosKeys  # noqa: E402
from azdata.cosmos.write import CosmosItems  # noqa: E402
from azdata.gremlin.verify import GremlinKeys  # noqa: E402
from azdata.kusto.verify import KustoKeys, KustoVerifyError  # noqa: E402
from azdata.search.verify import SearchKeys, content_digest  # noqa: E402


@pytest.fixture(autouse=True)
def _clean():
    yield
    clear_overrides()


# ── A Cosmos container that actually mutates ─────────────────────────────────


class FakeContainer:
    """Enough Cosmos to write to, read back, and enumerate.

    ``_etag`` changes on every write, exactly as the service does, which is
    what makes ``changed`` distinguishable from ``added`` plus ``removed``.
    """

    def __init__(self, items=()):
        self.items: dict[str, dict] = {}
        self.headers = {"x-ms-request-charge": "1.0"}
        self._writes = 0
        for item in items:
            self._store(dict(item))
        self.client_connection = types.SimpleNamespace(
            last_response_headers=self.headers
        )

    def _store(self, item: dict) -> dict:
        self._writes += 1
        item["_etag"] = f"etag-{self._writes}"
        self.items[item["id"]] = item
        return item

    async def create_item(self, body=None):
        if body["id"] in self.items:
            raise _Status(409)
        return self._store(dict(body))

    async def upsert_item(self, body=None):
        return self._store(dict(body))

    async def read_item(self, item=None, partition_key=None):
        found = self.items.get(item)
        if found is None or found.get("site") != partition_key:
            raise _Status(404)
        return found

    async def delete_item(self, item=None, partition_key=None):
        found = self.items.get(item)
        if found is None or found.get("site") != partition_key:
            raise _Status(404)
        del self.items[item]

    def query_items(self, query=None, parameters=None, partition_key=None):
        rows = self._rows_for(query)

        async def _iterate():
            for row in rows:
                yield row

        return _iterate()

    def _rows_for(self, query: str):
        if "COUNT(1)" in query:
            return [len(self.items)]
        ordered = [
            {"id": item["id"], "_etag": item["_etag"]}
            for item in sorted(self.items.values(), key=lambda i: i["id"])
        ]
        top = re.search(r"TOP (\d+)", query)
        return ordered[: int(top.group(1))] if top else ordered

    async def read(self):
        return {"partitionKey": {"paths": ["/site"]}}


class _Status(Exception):
    def __init__(self, status_code):
        super().__init__(str(status_code))
        self.status_code = status_code


def wiring(items=(), *, allow_write=False, allow_delete=False, with_stats=False):
    """A container, its write plane and its verify plane over one state."""
    container = FakeContainer(items)
    policy = (
        WritePolicy.writable(allow_delete=allow_delete, verify_writes=False)
        if allow_write
        else WritePolicy.read_only()
    )
    writer = CosmosItems(
        container=container, partition_key_field="site", policy=policy
    )
    stats = (
        CosmosStats(container=container, database="azdatalive", container_name="assets")
        if with_stats
        else None
    )
    keys = CosmosKeys(
        container=container,
        database="azdatalive",
        container_name="assets",
        stats_provider=stats,
    )
    return container, writer, keys


SEED = [
    {"id": "a", "site": "north", "value": 1},
    {"id": "b", "site": "north", "value": 2},
]


# ── Digest ───────────────────────────────────────────────────────────────────


def test_the_digest_is_blind_to_key_order():
    keys = [f"k{index}" for index in range(50)]
    shuffled = list(keys)
    random.Random(7).shuffle(shuffled)
    assert shuffled != keys
    assert key_digest(shuffled) == key_digest(keys)


def test_the_digest_changes_when_the_key_set_changes():
    assert key_digest(["a", "b"]) != key_digest(["a", "c"])


def test_the_digest_is_blind_to_a_duplicate_key():
    assert key_digest(["a", "b", "a"]) == key_digest(["a", "b"])


# ── Bounds ───────────────────────────────────────────────────────────────────


class CountedKeys:
    """A synthetic key space of a known size, for the cap boundary."""

    service = "test"
    target = "synthetic"

    def __init__(self, size: int, max_keys: int = 10):
        self.size = size
        self.max_keys = max_keys

    async def enumerate_keys(self, target=None):
        return {f"k{index:04d}": "digest" for index in range(self.size)}

    async def count(self, target=None):
        return self.size


async def test_below_the_cap_nothing_is_sampled():
    taken = await snapshot(CountedKeys(9))
    assert taken.sampled is False
    assert len(taken.keys) == 9
    assert taken.count == 9


async def test_exactly_at_the_cap_nothing_is_sampled():
    taken = await snapshot(CountedKeys(10))
    assert taken.sampled is False
    assert len(taken.keys) == 10


async def test_one_past_the_cap_samples_and_says_so():
    taken = await snapshot(CountedKeys(11))
    assert taken.sampled is True
    assert len(taken.keys) == 10
    # The count is the truth; the keys are a sample. Both are reported.
    assert taken.count == 11
    assert taken.as_dict()["sampled"] is True


async def test_the_sample_is_deterministic_and_the_digest_covers_only_it():
    first = await snapshot(CountedKeys(5000))
    second = await snapshot(CountedKeys(5000))
    assert first.keys == second.keys
    assert first.digest == second.digest
    assert first.digest == key_digest([f"k{index:04d}" for index in range(10)])


async def test_the_cap_defaults_from_the_config_variable():
    config = AzureDataConfig.from_env({"AZDATA_VERIFY_MAX_KEYS": "25"})
    assert config.verify_max_keys == 25
    assert AzureDataConfig.from_env({}).verify_max_keys == 5000
    assert AzureDataConfig.from_env({"AZDATA_VERIFY_MAX_KEYS": "nonsense"}).verify_max_keys == 5000


# ── Snapshot content ─────────────────────────────────────────────────────────


async def test_the_snapshot_carries_the_observe_plane_stats():
    _, _, keys = wiring(SEED, with_stats=True)
    taken = await snapshot(keys)
    assert taken.service == "cosmos"
    assert taken.target == "azdatalive/assets"
    assert taken.stats["item_count"] == 2
    assert taken.stats["last_request_charge_ru"] == 1.0


async def test_stats_that_cannot_be_collected_do_not_fail_a_snapshot():
    class Broken:
        service = "cosmos"

        async def enumerate_keys(self, target=None):
            return {"a": "d"}

        async def stats(self, target=None):
            raise RuntimeError("the observe plane is down")

    taken = await snapshot(Broken())
    assert taken.stats == {}
    assert taken.keys == ("a",)


# ── Positive: an expected effect matches ─────────────────────────────────────


async def test_an_expected_add_matches():
    _, writer, keys = wiring(SEED, allow_write=True)
    payload = json.loads(
        await verify_effect(
            keys,
            expect=Effect.added(["c"]),
            operation=lambda: writer.upload([{"id": "c", "site": "north"}]),
        )
    )
    assert payload["ok"] is True
    assert payload["matched"] is True
    assert payload["observed"]["added"] == ["c"]
    assert payload["observed"]["count_before"] == 2
    assert payload["observed"]["count_after"] == 3
    assert list(payload)[:5] == ["ok", "operation", "service", "target", "matched"]


async def test_an_expected_removal_matches():
    _, writer, keys = wiring(SEED, allow_write=True, allow_delete=True)
    payload = json.loads(
        await verify_effect(
            keys,
            expect=Effect.removed(["b"]),
            operation=lambda: writer.delete([("b", "north")]),
        )
    )
    assert payload["ok"] is True
    assert payload["observed"]["removed"] == ["b"]
    assert payload["observed"]["unchanged"] == 1


async def test_a_content_change_is_reported_as_changed_not_as_a_replacement():
    _, writer, keys = wiring(SEED, allow_write=True)
    payload = json.loads(
        await verify_effect(
            keys,
            expect=Effect.changed(["a"]),
            operation=lambda: writer.upload([{"id": "a", "site": "north", "value": 99}]),
        )
    )
    assert payload["ok"] is True
    assert payload["observed"]["changed"] == ["a"]
    assert payload["observed"]["added"] == []
    assert payload["observed"]["removed"] == []
    assert payload["before"]["digest"] == payload["after"]["digest"]


async def test_effect_any_matches_without_asserting_anything():
    _, writer, keys = wiring(SEED, allow_write=True)
    payload = json.loads(
        await verify_effect(
            keys,
            expect=Effect.any(),
            operation=lambda: writer.upload([{"id": "z", "site": "north"}]),
        )
    )
    assert payload["ok"] is True
    assert payload["expected"] == {"any": True}


# ── Negative: a refusal leaves a byte-identical digest ───────────────────────


async def test_a_refused_write_leaves_the_digest_byte_identical():
    container, writer, keys = wiring(SEED)  # WritePolicy.read_only()
    before = await snapshot(keys)

    refusal = json.loads(await writer.upload([{"id": "c", "site": "north"}]))
    assert refusal["error"] is True
    assert "WriteRefused" in refusal["detail"]

    after = await snapshot(keys)
    # The digest, not the count. Byte-identical is the assertion.
    assert after.digest == before.digest
    assert after.digest.encode() == before.digest.encode()
    assert container.items.keys() == {"a", "b"}


async def test_a_refused_write_satisfies_effect_unchanged():
    _, writer, keys = wiring(SEED)
    payload = json.loads(
        await verify_effect(
            keys,
            expect=Effect.unchanged(),
            operation=lambda: writer.upload([{"id": "c", "site": "north"}]),
        )
    )
    assert payload["ok"] is True
    assert payload["matched"] is True
    assert payload["before"]["digest"] == payload["after"]["digest"]
    assert payload["observed"]["added"] == []


async def test_a_delete_without_a_delete_grant_changes_nothing():
    container, writer, keys = wiring(SEED, allow_write=True)  # write, not delete
    before = await snapshot(keys)

    refusal = json.loads(await writer.delete([("a", "north")]))
    assert refusal["error"] is True
    # WriteRefused is raised inside the connector and converted at the
    # boundary; the type name in the detail is the evidence it was raised.
    assert "WriteRefused" in refusal["detail"]
    assert "allow_delete=True" in refusal["detail"]

    after = await snapshot(keys)
    assert after.digest == before.digest
    assert container.items.keys() == {"a", "b"}


async def test_a_refused_delete_satisfies_effect_unchanged():
    _, writer, keys = wiring(SEED, allow_write=True)
    payload = json.loads(
        await verify_effect(
            keys,
            expect=Effect.unchanged(),
            operation=lambda: writer.delete([("a", "north")]),
        )
    )
    assert payload["ok"] is True
    assert payload["before"]["digest"] == payload["after"]["digest"]


# ── Negative: an unrequested change fails ────────────────────────────────────


async def test_an_unrequested_extra_add_fails_the_verification():
    _, writer, keys = wiring(SEED, allow_write=True)
    payload = json.loads(
        await verify_effect(
            keys,
            expect=Effect.added(["a2"]),
            operation=lambda: writer.upload(
                [{"id": "a2", "site": "north"}, {"id": "b2", "site": "north"}]
            ),
        )
    )
    assert payload["error"] is True
    assert "ok" not in payload
    assert payload["matched"] is False
    assert payload["expected"] == {"added": ["a2"]}
    assert payload["observed"]["added"] == ["a2", "b2"]


async def test_a_concurrent_removal_fails_an_otherwise_correct_add():
    container, writer, keys = wiring(SEED, allow_write=True)

    async def _add_while_something_else_deletes():
        result = await writer.upload([{"id": "c", "site": "north"}])
        del container.items["b"]  # the concurrent process in the docstring
        return result

    payload = json.loads(
        await verify_effect(
            keys, expect=Effect.added(["c"]), operation=_add_while_something_else_deletes
        )
    )
    assert payload["error"] is True
    assert payload["observed"]["added"] == ["c"]
    assert payload["observed"]["removed"] == ["b"]
    assert payload["observed"]["count_before"] == payload["observed"]["count_after"]


async def test_a_mismatch_carries_the_whole_observation():
    _, writer, keys = wiring(SEED, allow_write=True)
    payload = json.loads(
        await verify_effect(
            keys,
            expect=Effect.unchanged(),
            operation=lambda: writer.upload([{"id": "c", "site": "north"}]),
        )
    )
    assert payload["error"] is True
    assert payload["detail"]
    assert payload["before"]["digest"] != payload["after"]["digest"]
    assert set(payload) >= {
        "error",
        "detail",
        "operation",
        "service",
        "target",
        "matched",
        "expected",
        "observed",
        "before",
        "after",
        "elapsed_ms",
    }


# ── Negative: the count is not the evidence, the keys are ────────────────────


async def test_count_delta_fails_a_net_zero_add_and_remove():
    """A swap nets to zero. Nothing about the store is the same."""
    container, writer, keys = wiring(SEED, allow_write=True)

    async def _swap():
        result = await writer.upload([{"id": "c", "site": "north"}])
        del container.items["b"]
        return result

    before = await snapshot(keys)
    payload = json.loads(
        await verify_effect(keys, expect=Effect.count_delta(0), operation=_swap)
    )
    after_digest = payload["after"]["digest"]

    assert payload["error"] is True
    assert payload["observed"]["count_before"] == payload["observed"]["count_after"]
    # The count matched exactly and the digest did not. That difference is
    # the whole reason a digest is taken.
    assert after_digest != before.digest


async def test_count_delta_plus_one_fails_a_net_zero_add_and_remove():
    container, writer, keys = wiring(SEED, allow_write=True)

    async def _swap():
        result = await writer.upload([{"id": "c", "site": "north"}])
        del container.items["b"]
        return result

    payload = json.loads(
        await verify_effect(keys, expect=Effect.count_delta(1), operation=_swap)
    )
    assert payload["error"] is True
    assert payload["expected"] == {"count_delta": 1}


async def test_count_delta_matches_a_genuine_single_add():
    _, writer, keys = wiring(SEED, allow_write=True)
    payload = json.loads(
        await verify_effect(
            keys,
            expect=Effect.count_delta(1),
            operation=lambda: writer.upload([{"id": "c", "site": "north"}]),
        )
    )
    assert payload["ok"] is True


def test_count_delta_rejects_a_matching_count_with_moved_keys_directly():
    before = StateSnapshot("cosmos", "t", "now", 2, ("a", "b"), key_digest(["a", "b"]))
    after = StateSnapshot("cosmos", "t", "now", 2, ("a", "c"), key_digest(["a", "c"]))
    delta = StateDelta.between(before, after)
    assert delta.count_after - delta.count_before == 0
    assert Effect.count_delta(0).matches(delta, before=before, after=after) is False
    assert Effect.unchanged().matches(delta, before=before, after=after) is False


def test_unchanged_rejects_two_stores_with_the_same_count():
    before = StateSnapshot("cosmos", "t", "now", 40, ("a",), key_digest(["a"]))
    after = StateSnapshot("cosmos", "t", "now", 40, ("z",), key_digest(["z"]))
    delta = StateDelta.between(before, after)
    assert before.count == after.count
    assert before.digest != after.digest
    assert Effect.unchanged().matches(delta, before=before, after=after) is False


# ── The journal sees the verification ────────────────────────────────────────


async def test_a_verification_is_journalled_with_its_outcome():
    _, writer, keys = wiring(SEED, allow_write=True)
    journal = OperationJournal()
    journal.enable()

    await verify_effect(
        keys,
        expect=Effect.added(["c"]),
        operation=lambda: writer.upload([{"id": "c", "site": "north"}]),
        journal_=journal,
    )
    await verify_effect(
        keys,
        expect=Effect.unchanged(),
        operation=lambda: writer.upload([{"id": "d", "site": "north"}]),
        journal_=journal,
    )

    outcomes = [(r.operation, r.outcome, r.verified) for r in journal.records()]
    assert outcomes == [("verify", "ok", True), ("verify", "error", False)]
    assert journal.records()[0].service == "cosmos"


async def test_a_disabled_journal_records_no_verification():
    _, writer, keys = wiring(SEED, allow_write=True)
    journal = OperationJournal()
    await verify_effect(
        keys,
        expect=Effect.any(),
        operation=lambda: writer.upload([{"id": "c", "site": "north"}]),
        journal_=journal,
    )
    assert journal.records() == ()


# ── The service key spaces ───────────────────────────────────────────────────


class FakeSearchClient:
    def __init__(self, documents=(), total=None):
        self.documents = [dict(doc) for doc in documents]
        self.total = total
        self.searches: list[dict] = []

    def search(self, **params):
        self.searches.append(params)
        return list(self.documents)

    def get_document_count(self):
        if self.total is None:
            raise RuntimeError("count unavailable")
        return self.total


async def test_search_keys_enumerate_and_digest_document_content():
    client = FakeSearchClient(
        documents=[
            {"id": "d1", "title": "one", "@search.score": 1.0},
            {"id": "d2", "title": "two", "@search.score": 0.5},
        ],
        total=2,
    )
    keys = SearchKeys(client=client, index_name="azdata-assets", max_keys=10)
    enumerated = await keys.enumerate_keys()

    assert sorted(enumerated) == ["d1", "d2"]
    assert await keys.count() == 2
    # One past the cap, so "exactly the cap" is distinguishable from truncated.
    assert client.searches[0]["top"] == 11
    # The volatile search score must not read as a content change.
    assert enumerated["d1"] == content_digest({"id": "d1", "title": "one"}, "id")


async def test_search_count_is_minus_one_when_the_service_will_not_say():
    keys = SearchKeys(client=FakeSearchClient(documents=[{"id": "d1"}]), max_keys=10)
    assert await keys.count() == -1


async def test_cosmos_keys_use_the_etag_as_the_content_digest():
    container, writer, keys = wiring(SEED, allow_write=True)
    before = await keys.enumerate_keys()
    await writer.upload([{"id": "a", "site": "north", "value": 99}])
    after = await keys.enumerate_keys()

    assert set(before) == set(after) == {"a", "b"}
    assert before["a"] != after["a"]
    assert before["b"] == after["b"]


async def test_cosmos_enumeration_is_ordered_and_asks_for_one_past_the_cap():
    container = FakeContainer(SEED)
    keys = CosmosKeys(container=container, max_keys=10)
    captured, _ = await capture(keys)
    assert captured.keys == ("a", "b")
    assert captured.count == 2


class FakeGremlinReader:
    def __init__(self, responses):
        self.responses = responses
        self.queries: list[str] = []

    async def execute(self, query, **kwargs):
        self.queries.append(query)
        if query not in self.responses:
            return json.dumps({"error": True, "detail": f"unexpected: {query}"})
        return json.dumps(self.responses[query])


async def test_gremlin_keys_enumerate_vertices_not_edges():
    reader = FakeGremlinReader(
        {
            "g.V().valueMap(true).limit(11)": [
                {"id": "v1", "label": "asset", "site": ["north"]},
                {"id": "v2", "label": "asset", "site": ["south"]},
            ],
            "g.V().count()": [2],
        }
    )
    keys = GremlinKeys(connector=reader, database="db", graph="assets", max_keys=10)
    enumerated = await keys.enumerate_keys()

    assert sorted(enumerated) == ["v1", "v2"]
    assert enumerated["v1"] != enumerated["v2"]
    assert await keys.count() == 2


async def test_a_refused_traversal_fails_the_snapshot_rather_than_faking_one():
    keys = GremlinKeys(connector=FakeGremlinReader({}), max_keys=10)
    with pytest.raises(Exception):
        await keys.enumerate_keys()


class FakeKqlReader:
    def __init__(self, responses):
        self.responses = responses
        self.queries: list[str] = []

    async def execute(self, query, **kwargs):
        self.queries.append(query)
        if query not in self.responses:
            return json.dumps({"error": True, "detail": f"unexpected: {query}"})
        return json.dumps({"columns": [], "rows": self.responses[query]})


async def test_kusto_keys_enumerate_the_named_key_column():
    reader = FakeKqlReader(
        {
            "Assets | project AssetId, Status | order by AssetId asc | take 11": [
                {"AssetId": "a1", "Status": "ok"},
                {"AssetId": "a2", "Status": "ok"},
            ],
            "Assets | count": [{"Count": 2}],
        }
    )
    keys = KustoKeys(
        connector=reader,
        table="Assets",
        key_column="AssetId",
        content_columns=("Status",),
        max_keys=10,
    )
    enumerated = await keys.enumerate_keys()
    assert sorted(enumerated) == ["a1", "a2"]
    assert enumerated["a1"] == enumerated["a2"]  # same content, same digest
    assert await keys.count() == 2


async def test_kusto_refuses_to_interpolate_anything_that_is_not_an_identifier():
    keys = KustoKeys(
        connector=FakeKqlReader({}), table="Assets", key_column="AssetId; .drop table"
    )
    with pytest.raises(KustoVerifyError):
        await keys.enumerate_keys()


def test_fabric_graph_has_no_verify_plane_and_says_why():
    import azdata.fabric_graph as fabric_graph

    assert not (Path(fabric_graph.__file__).parent / "verify.py").exists()
    assert "No verify plane" in fabric_graph.__doc__


def test_the_verify_plane_is_on_the_public_surface():
    import azdata

    for name in ("Effect", "StateSnapshot", "StateDelta", "verify_effect", "snapshot"):
        assert name in azdata.__all__
        assert hasattr(azdata, name)
