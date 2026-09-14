"""test_search_planes — the Search write plane and deploy plane, with no SDKs.

Run: ``python3 tests/test_search_planes.py``. Exits non-zero on any failure.

Every Azure SDK is replaced through ``azdata.core.optional.override``, so this
exercises eventual-consistency verification, partial batch failure,
batching, index drift detection and LRO bounding on a laptop with no cloud
account, no network and nothing installed. The fakes assert on what the
connector sent, so this is a contract test, not a smoke test.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import types
from collections.abc import MutableMapping
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.core.config import AzureDataConfig  # noqa: E402
from azdata.core.crud import WritePolicy  # noqa: E402
from azdata.core.optional import clear_overrides, override  # noqa: E402
from azdata.core.provision import ProvisionPolicy  # noqa: E402
from azdata.search.write import SearchDocuments  # noqa: E402
from azdata.search.deploy import (  # noqa: E402
    SearchIndexProvisioner,
    SearchServiceProvisioner,
)

_FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        _FAILURES.append(label)


def section(title: str) -> None:
    print(title)


# ── Fakes ────────────────────────────────────────────────────────────────────


class ResourceNotFoundError(Exception):
    """Named exactly as the SDK's, because that is what the code detects."""

    status_code = 404


class FakeCredential:
    def get_token(self, scope: str):  # noqa: D102 - never called by these paths
        return types.SimpleNamespace(token="tok", expires_on=time.time() + 3600)


class SdkModel(MutableMapping):
    """What ``azure-search-documents`` 12.0 actually returns.

    Its models are ``MutableMapping`` subclasses that are **not** ``dict``, and
    the mapping is keyed by the *wire* names while the documented attributes
    use the Python names. The two disagree, and both defects this file now pins
    lived in that gap: ``json.dumps(doc, default=str)`` stringifies a mapping it
    does not recognise, and ``result["succeeded"]`` is absent while
    ``result.succeeded`` is ``True``.

    Reproduced rather than imported, because this suite runs with no SDK
    installed. ``tests/unit/test_live_environment.py`` is where the real
    package is asserted against, when it is present.
    """

    _ATTRS: dict[str, str] = {}

    def __init__(self, wire: dict) -> None:
        self._wire = dict(wire)

    def __getitem__(self, key):
        return self._wire[key]

    def __setitem__(self, key, value):
        self._wire[key] = value

    def __delitem__(self, key):
        del self._wire[key]

    def __iter__(self):
        return iter(self._wire)

    def __len__(self):
        return len(self._wire)

    def __getattr__(self, name):
        wire_name = type(self)._ATTRS.get(name)
        if wire_name is None:
            raise AttributeError(name)
        return self._wire.get(wire_name)


class FakeIndexingResult(SdkModel):
    """``IndexingResult``: ``succeeded`` is under the wire key ``status``."""

    _ATTRS = {
        "key": "key",
        "succeeded": "status",
        "error_message": "errorMessage",
        "status_code": "statusCode",
    }

    def __init__(self, key, succeeded=True, error_message="", status_code=200):
        super().__init__(
            {
                "key": key,
                "status": succeeded,
                "errorMessage": error_message,
                "statusCode": status_code,
            }
        )


class FakeLookupDocument(SdkModel):
    """``LookupDocument``: a document, and not a ``dict``."""


class FakeIndex:
    """One index's documents, with the service's eventual consistency modelled.

    ``readable_after`` is how many ``get_document`` calls must pass before a
    just-written document becomes retrievable: 1 is immediate, 3 is the
    indexing lag that breaks naive write-then-read code.
    """

    def __init__(
        self,
        *,
        existing=(),
        readable_after=1,
        forget_on_delete=True,
        fail_keys=(),
    ) -> None:
        self.docs = {doc["id"]: dict(doc) for doc in existing}
        self.readable_after = readable_after
        self.forget_on_delete = forget_on_delete
        self.fail_keys = set(fail_keys)
        self.uploads: list[list[dict]] = []
        self.merges: list[list[dict]] = []
        self.deletes: list[list[dict]] = []
        self.searches: list[dict] = []
        self.clients = 0
        self.closed = 0
        self.read_counts: dict[str, int] = {}
        self._visible_at: dict[str, int] = {}

    def get_document(self, key, **kwargs):
        count = self.read_counts.get(key, 0) + 1
        self.read_counts[key] = count
        if key not in self.docs or count < self._visible_at.get(key, 0):
            raise ResourceNotFoundError(f"({key}) was not found")
        return FakeLookupDocument(self.docs[key])

    def upload_documents(self, documents=None):
        self.uploads.append(list(documents or []))
        return self._write(documents)

    def merge_or_upload_documents(self, documents=None):
        self.merges.append(list(documents or []))
        return self._write(documents)

    def delete_documents(self, documents=None):
        stubs = list(documents or [])
        self.deletes.append(stubs)
        results = []
        for stub in stubs:
            key = stub["id"]
            ok = key not in self.fail_keys
            if ok and self.forget_on_delete:
                self.docs.pop(key, None)
            results.append(FakeIndexingResult(key, ok))
        return results

    def search(self, **params):
        self.searches.append(params)
        return list(self.docs.values())

    def _write(self, documents):
        results = []
        for doc in documents or []:
            key = doc["id"]
            ok = key not in self.fail_keys
            if ok:
                self.docs[key] = dict(doc)
                self._visible_at[key] = (
                    self.read_counts.get(key, 0) + self.readable_after
                )
            results.append(
                FakeIndexingResult(
                    key,
                    ok,
                    "" if ok else "the request is invalid",
                    200 if ok else 400,
                )
            )
        return results


def fake_documents_module(index: FakeIndex):
    class _SearchClient:
        def __init__(self, **kwargs):
            index.clients += 1
            self.kwargs = kwargs

        def get_document(self, key, **kwargs):
            return index.get_document(key, **kwargs)

        def upload_documents(self, documents=None):
            return index.upload_documents(documents=documents)

        def merge_or_upload_documents(self, documents=None):
            return index.merge_or_upload_documents(documents=documents)

        def delete_documents(self, documents=None):
            return index.delete_documents(documents=documents)

        def search(self, **params):
            return index.search(**params)

        def close(self):
            index.closed += 1

    return types.SimpleNamespace(SearchClient=_SearchClient)


class FakeSearchField:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeSearchIndex:
    def __init__(self, name, fields, **kwargs):
        self.name = name
        self.fields = list(fields)
        self.__dict__.update(kwargs)


class FakeIndexService:
    """The index-management plane. ``drift_fields`` stores something else."""

    def __init__(self, *, drift_fields=None) -> None:
        self.index = None
        self.gets = 0
        self.puts: list = []
        self.deleted: list[str] = []
        self.drift_fields = drift_fields

    def get_index(self, name):
        self.gets += 1
        if self.index is None:
            raise ResourceNotFoundError(f"index '{name}' was not found")
        return self.index

    def create_or_update_index(self, index):
        self.puts.append(index)
        if self.drift_fields is not None:
            self.index = FakeSearchIndex(name=index.name, fields=self.drift_fields)
        else:
            self.index = index
        return self.index

    def delete_index(self, name):
        self.deleted.append(name)
        self.index = None


def fake_index_modules(service: FakeIndexService):
    class _SearchIndexClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def get_index(self, name):
            return service.get_index(name)

        def create_or_update_index(self, index):
            return service.create_or_update_index(index)

        def delete_index(self, name):
            return service.delete_index(name)

    indexes = types.SimpleNamespace(SearchIndexClient=_SearchIndexClient)
    models = types.SimpleNamespace(
        SearchField=FakeSearchField, SearchIndex=FakeSearchIndex
    )
    return indexes, models


def fake_mgmt_module(*, poller_delay: float):
    log = {"created": [], "deleted": []}

    class _Poller:
        def result(self):
            time.sleep(poller_delay)
            return {"name": "svc", "provisioning_state": "Succeeded"}

    class _Services:
        def get(self, resource_group, name):
            raise ResourceNotFoundError(f"service '{name}' was not found")

        def begin_create_or_update(self, resource_group, name, spec):
            log["created"].append((resource_group, name, spec))
            return _Poller()

        def delete(self, resource_group, name):
            log["deleted"].append((resource_group, name))

    class _SearchManagementClient:
        def __init__(self, credential, subscription_id):
            self.credential = credential
            self.subscription_id = subscription_id
            self.services = _Services()

    return types.SimpleNamespace(SearchManagementClient=_SearchManagementClient), log


def install_documents(index: FakeIndex) -> None:
    override("azure.search.documents", fake_documents_module(index))
    override(
        "azure.core.exceptions",
        types.SimpleNamespace(ResourceNotFoundError=ResourceNotFoundError),
    )


def connector(index: FakeIndex, policy: WritePolicy, **kwargs) -> SearchDocuments:
    install_documents(index)
    return SearchDocuments(
        endpoint="https://search.example.net",
        index_name="idx",
        credential=FakeCredential(),
        policy=policy,
        **kwargs,
    )


def parse(payload: str) -> dict:
    return json.loads(payload)


# ── Write plane: policy ──────────────────────────────────────────────────────


async def test_write_policy() -> None:
    section("search write plane: policy denies by default")

    index = FakeIndex()
    read_only = connector(index, WritePolicy.read_only())
    refused = parse(await read_only.upload([{"id": "a"}]))
    check("a default-policy connector refuses upload", refused["error"] is True)
    check("and says how to grant it", "WritePolicy.writable" in refused["detail"])
    check(
        "nothing reached the SDK",
        index.merges == [] and index.uploads == [] and index.clients == 0,
    )

    write_only = connector(index, WritePolicy(allow_write=True))
    denied = parse(await write_only.delete(["a"]))
    check("write does not imply delete", denied["error"] is True)
    check("nothing was deleted", index.deletes == [])


# ── Write plane: verification ────────────────────────────────────────────────


async def test_verification() -> None:
    section("search write plane: an accepted write is not an indexed document")

    # The case that matters: the service accepts the upload and the document
    # becomes retrievable two reads later.
    index = FakeIndex(readable_after=3)
    conn = connector(
        index,
        WritePolicy(allow_write=True, verify_writes=True, verify_delay_secs=0.01),
    )
    lagging = parse(await conn.upload([{"id": "a", "body": "x"}]))
    check("upload survives indexing lag", lagging["ok"] is True)
    check("and reports itself verified", lagging["verified"] is True)
    check("by polling until it read back", index.read_counts["a"] == 3)

    never = FakeIndex(readable_after=99)
    stuck = connector(
        never,
        WritePolicy(
            allow_write=True,
            verify_writes=True,
            verify_attempts=3,
            verify_delay_secs=0.01,
        ),
    )
    lost = parse(await stuck.upload([{"id": "a"}]))
    check("a document that never indexes fails the upload", lost["error"] is True)
    check("and the detail names verification", "VerificationFailed" in lost["detail"])
    check("after exactly the budgeted attempts", never.read_counts["a"] == 3)

    zombie = FakeIndex(existing=[{"id": "a"}], forget_on_delete=False)
    deleter = connector(
        zombie,
        WritePolicy(
            allow_write=True,
            allow_delete=True,
            verify_writes=True,
            verify_attempts=2,
            verify_delay_secs=0.01,
        ),
    )
    undead = parse(await deleter.delete(["a"]))
    check("a delete that deleted nothing fails", undead["error"] is True)
    check("and the detail names verification", "VerificationFailed" in undead["detail"])


# ── Write plane: batch behaviour ─────────────────────────────────────────────


async def test_batches() -> None:
    section("search write plane: batches, partial failure and create")

    index = FakeIndex(fail_keys={"b"})
    conn = connector(index, WritePolicy(allow_write=True))
    partial = parse(
        await conn.upload([{"id": "a"}, {"id": "b"}], verify=False)
    )
    check("a partial batch failure is still ok", partial["ok"] is True)
    check("the failure is reported, not dropped", len(partial["failed"]) == 1)
    check("naming the document", partial["failed"][0]["key"] == "b")
    check("and the count excludes it", partial["count"] == 1)

    big = FakeIndex()
    batched = connector(big, WritePolicy(allow_write=True, max_batch=100))
    bulk = parse(
        await batched.upload(
            [{"id": f"d{i}"} for i in range(250)], verify=False
        )
    )
    check("250 documents at max_batch=100 make 3 calls", len(big.merges) == 3)
    check("chunk sizes are 100/100/50", [len(c) for c in big.merges] == [100, 100, 50])
    check("and every document is accounted for", bulk["count"] == 250)

    occupied = FakeIndex(existing=[{"id": "a"}])
    creator = connector(occupied, WritePolicy(allow_write=True))
    clash = parse(await creator.create([{"id": "a"}, {"id": "c"}], verify=False))
    check("create refuses a batch with an existing key", clash["error"] is True)
    check("naming the conflict", "'a'" in clash["detail"])
    check("and uploads nothing", occupied.uploads == [])


# ── Write plane: the SDK's return shapes ─────────────────────────────────────


async def test_sdk_return_shapes() -> None:
    """Both 12.0 shapes, pinned. Neither was caught by an attribute-only fake."""
    section("search write plane: the shapes azure-search-documents 12.0 returns")

    # 1. A read-back is a document, not a document's repr.
    index = FakeIndex(existing=[{"id": "a", "title": "seed row", "n": 3}])
    conn = connector(index, WritePolicy.read_only())
    read = parse(await conn.read("a"))
    row = read["results"][0]
    check("a read-back row is an object", isinstance(row, dict))
    check("not the str() of a mapping", not isinstance(row, str))
    check("and it carries the document's fields", row["title"] == "seed row")
    check("with values, not reprs", row["n"] == 3)

    # 2. A successful delete says so.
    live = FakeIndex(existing=[{"id": "a"}])
    deleter = connector(live, WritePolicy(allow_write=True, allow_delete=True))
    gone = parse(await deleter.delete(["a"], verify=False))
    check("a delete the service accepted is ok", gone["ok"] is True)
    check("with nothing in failed", gone["failed"] == [])
    check("and the key counted", gone["count"] == 1)

    # 3. A real failure is still a failure, and still names the status.
    broken = FakeIndex(existing=[{"id": "a"}], fail_keys={"a"})
    failing = connector(broken, WritePolicy(allow_write=True, allow_delete=True))
    refused = parse(await failing.delete(["a"], verify=False))
    check("a delete the service refused is reported", len(refused["failed"]) == 1)
    check("naming the document", refused["failed"][0]["key"] == "a")
    check("and 'status None' is not the detail", "status None" not in json.dumps(refused))

    # 4. A plain dict still works, so a fake need not model an SDK.
    from azdata.search.write import _indexing_results

    plain = _indexing_results(
        [
            {"key": "d1", "succeeded": True, "status_code": 200},
            {"key": "d2", "succeeded": False, "error_message": "bad", "status_code": 400},
        ]
    )
    check("a dict-shaped result maps by its own names", plain[0]["ok"] is True)
    check("and its failure detail survives", plain[1]["detail"] == "bad")

    # 5. The wire keys alone are enough, which is what a raw JSON body is.
    wire = _indexing_results(
        [{"key": "d3", "status": True, "statusCode": 200, "errorMessage": None}]
    )
    check("wire-keyed results map too", wire[0]["ok"] is True and wire[0]["key"] == "d3")


# ── Deploy plane: the index ──────────────────────────────────────────────────


async def test_index_provisioner() -> None:
    section("search deploy plane: index")

    spec = {
        "name": "idx",
        "fields": [
            {"name": "id", "type": "Edm.String", "key": True},
            {"name": "body", "type": "Edm.String"},
        ],
    }

    service = FakeIndexService()
    indexes, models = fake_index_modules(service)
    override("azure.search.documents.indexes", indexes)
    override("azure.search.documents.indexes.models", models)

    prov = SearchIndexProvisioner(
        endpoint="https://search.example.net",
        name="idx",
        credential=FakeCredential(),
        policy=ProvisionPolicy.deployable(),
    )
    first = parse(await prov.ensure(spec))
    check("ensure creates a missing index", first["ok"] is True)
    check("and reports it created", first["created"] is True)
    check("with no drift", first["drift"] == {})
    check("translating field dicts to SDK models", isinstance(service.puts[0].fields[0], FakeSearchField))

    second = parse(await prov.ensure(spec))
    check("a second ensure is idempotent", second["ok"] is True)
    check("and reports it was already there", second["created"] is False)

    drifting = FakeIndexService(
        drift_fields=[FakeSearchField(name="id"), FakeSearchField(name="other")]
    )
    drift_indexes, drift_models = fake_index_modules(drifting)
    override("azure.search.documents.indexes", drift_indexes)
    override("azure.search.documents.indexes.models", drift_models)
    drift_prov = SearchIndexProvisioner(
        endpoint="https://search.example.net",
        name="idx",
        credential=FakeCredential(),
        policy=ProvisionPolicy.deployable(),
    )
    drifted = parse(await drift_prov.ensure(spec))
    check("a field list that did not survive the write is an error", drifted["error"] is True)
    check("naming the field list", "field_names" in drifted["detail"])


# ── Deploy plane: the service ────────────────────────────────────────────────


async def test_service_provisioner() -> None:
    section("search deploy plane: service")

    module, log = fake_mgmt_module(poller_delay=1.0)
    override("azure.mgmt.search", module)

    prov = SearchServiceProvisioner(
        subscription_id="sub",
        resource_group="rg",
        name="svc",
        location="Australia East",
        credential=FakeCredential(),
        policy=ProvisionPolicy.deployable(poll_timeout_secs=0.05),
    )
    started = time.monotonic()
    timed_out = parse(
        await prov.ensure(
            {"location": "Australia East", "sku": {"name": "standard"}}
        )
    )
    elapsed = time.monotonic() - started
    check("a wedged LRO fails instead of hanging", timed_out["error"] is True)
    check("naming the deadline", "terminal state" in timed_out["detail"])
    check("and it gave up promptly", elapsed < 2.0)
    check("the spec did reach ARM", log["created"][0][1] == "svc")

    unconfigured = SearchServiceProvisioner.from_config(
        AzureDataConfig(),
        lambda: FakeCredential(),
        policy=ProvisionPolicy.deployable(),
    )
    missing = parse(await unconfigured.describe())
    check("missing coordinates are an envelope, not a client", missing["error"] is True)
    check("naming the config field", "subscription_id" in missing["detail"])


# ── Deploy plane: the service read-back shape ────────────────────────────────


class FakeSearchService:
    """A msrest-style model: NOT a Mapping, ``as_dict()`` flattened snake_case.

    Introspected on azure-mgmt-search 9.2.0, and the exact opposite of the
    JSON-backed azure-mgmt-cosmosdb 10 models used elsewhere in this
    package: ``SearchService`` is not a ``collections.abc.Mapping``, and
    ``as_dict()`` returns ``{'location', 'sku', 'replica_count',
    'partition_count', 'hosting_mode', 'public_network_access'}`` with no
    ``properties`` nesting at all.
    """

    def __init__(self, **fields) -> None:
        self._fields = dict(fields)

    def as_dict(self) -> dict:
        return dict(self._fields)


def fake_mgmt_with_readback(readback: FakeSearchService):
    log = {"created": [], "deleted": []}

    class _Poller:
        def result(self):
            return readback

    class _Services:
        def __init__(self) -> None:
            self.present = False

        def get(self, resource_group, name):
            if not self.present:
                raise ResourceNotFoundError(f"service '{name}' was not found")
            return readback

        def begin_create_or_update(self, resource_group, name, service):
            log["created"].append(service)
            self.present = True
            return _Poller()

        def delete(self, resource_group, name):
            # The real signature returns None, not a poller.
            log["deleted"].append(name)
            self.present = False
            return None

    class _SearchManagementClient:
        def __init__(self, credential, subscription_id):
            self.services = _Services()

    return types.SimpleNamespace(SearchManagementClient=_SearchManagementClient), log


async def test_service_readback_shape() -> None:
    section("search deploy plane: the real msrest service read-back shape")

    spec = {
        "location": "Australia East",
        "sku": {"name": "basic"},
        "replica_count": 1,
        "partition_count": 1,
        "public_network_access": "enabled",
    }

    def provisioner() -> SearchServiceProvisioner:
        return SearchServiceProvisioner(
            subscription_id="sub",
            resource_group="rg",
            name="svc",
            location="Australia East",
            credential=FakeCredential(),
            policy=ProvisionPolicy.deployable(allow_delete=True, poll_timeout_secs=5.0),
        )

    healthy = FakeSearchService(
        location="australiaeast",
        sku={"name": "basic"},
        replica_count=1,
        partition_count=1,
        hosting_mode="default",
        public_network_access="enabled",
    )
    module, log = fake_mgmt_with_readback(healthy)
    override("azure.mgmt.search", module)
    clean = parse(await provisioner().ensure(spec))
    check("a flattened snake_case read-back is NOT drift", clean.get("ok") is True)
    check("with an empty drift map", clean["drift"] == {})
    check("the plain dict spec reached ARM unchanged", log["created"][0] == spec)

    reverted = FakeSearchService(
        location="australiaeast",
        sku={"name": "basic"},
        replica_count=1,
        partition_count=1,
        hosting_mode="default",
        public_network_access="disabled",
    )
    module, _ = fake_mgmt_with_readback(reverted)
    override("azure.mgmt.search", module)
    drifted = parse(await provisioner().ensure(spec))
    check("a reverted public_network_access IS drift", drifted.get("error") is True)
    check("naming the field", "public_network_access" in drifted["detail"])
    check("blaming the right cause", "Policy" in drifted["detail"])
    check("and never the normalised location", "location" not in drifted["detail"])

    module, delete_log = fake_mgmt_with_readback(healthy)
    override("azure.mgmt.search", module)
    torn = provisioner()
    await torn.ensure(spec)
    gone = parse(await torn.teardown())
    check("delete returns None, not a poller, and teardown copes", gone["ok"] is True)
    check("and it did delete", delete_log["deleted"] == ["svc"])

    camel = parse(
        await provisioner().ensure(
            {"location": "Australia East", "publicNetworkAccess": "enabled"}
        )
    )
    check(
        "a camelCase spec key is normalised, not phantom drift",
        camel.get("ok") is True,
    )
    check("with an empty drift map", camel["drift"] == {})


# ── Dependencies ─────────────────────────────────────────────────────────────


async def test_missing_dependency() -> None:
    section("search planes: missing SDK")
    clear_overrides()

    # None in sys.modules makes import_module raise ImportError, which is
    # absence as the loader sees it. Asserting on the SDK genuinely not being
    # installed would make this test pass or fail by accident.
    blocked = "azure.search.documents"
    previous = sys.modules.get(blocked, "<unset>")
    sys.modules[blocked] = None  # type: ignore[assignment]
    try:
        conn = SearchDocuments(
            endpoint="https://search.example.net",
            index_name="idx",
            credential=FakeCredential(),
            policy=WritePolicy(allow_write=True),
        )
        absent = parse(await conn.upload([{"id": "a"}], verify=False))
    finally:
        if previous == "<unset>":
            sys.modules.pop(blocked, None)
        else:
            sys.modules[blocked] = previous

    check("a missing SDK is an error envelope", absent["error"] is True)
    check("raised as MissingDependency", "MissingDependency" in absent["detail"])
    check(
        "naming the distribution to install",
        "azure-search-documents" in absent["detail"],
    )


# ── Runner ───────────────────────────────────────────────────────────────────


async def main() -> int:
    try:
        await test_write_policy()
        await test_verification()
        await test_batches()
        await test_sdk_return_shapes()
        await test_index_provisioner()
        await test_service_provisioner()
        await test_service_readback_shape()
        await test_missing_dependency()
    finally:
        clear_overrides()

    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} check(s)")
        for failure in _FAILURES:
            print(f"  - {failure}")
        return 1
    print("search plane tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
