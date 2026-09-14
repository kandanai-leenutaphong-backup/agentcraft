"""test_cosmos_planes — the Cosmos write and deploy planes, with no SDK.

Run: ``python3 tests/test_cosmos_planes.py``. Exits non-zero on any failure.

Every fake here models a hazard rather than a happy path. The Cosmos SDK
returns 404 for "no such item" and for "wrong partition key" identically,
and ARM returns ``Succeeded`` for a write an Azure Policy ``Modify``
effect has already reverted. Both are reproduced below, because both are
failures that a connector can report as success.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.core.config import AzureDataConfig  # noqa: E402
from azdata.cosmos.write import CosmosItems  # noqa: E402
from azdata.cosmos.deploy import (  # noqa: E402
    CosmosAccountProvisioner,
    CosmosContainerProvisioner,
    CosmosDatabaseProvisioner,
)
from azdata.core.crud import WritePolicy  # noqa: E402
from azdata.core.optional import MissingDependency, clear_overrides, override  # noqa: E402
from azdata.core.provision import ProvisionPolicy  # noqa: E402

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


class FakeCosmosError(Exception):
    """Stands in for CosmosHttpResponseError: one type, a status code."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"cosmos error {status_code}")
        self.status_code = status_code


class FakeContainer:
    """An async container proxy that enforces partition scoping like Cosmos.

    ``delete_is_noop`` reproduces the accepted-but-not-applied delete: the
    call returns, the item stays readable. ``query_items`` deliberately
    takes ``**params`` and records them, exactly as the real 4.x method
    absorbs unknown keywords into ``**kwargs`` — an unsupported argument
    has to be caught by asserting on what was sent, because neither the
    fake nor the SDK will raise on one.
    """

    def __init__(self, items=None, *, delete_is_noop: bool = False, rows=None) -> None:
        # Keyed by (id, partition key value), which is what Cosmos addresses.
        self.items: dict[tuple, dict] = dict(items or {})
        self.delete_is_noop = delete_is_noop
        self.rows = list(rows or [])
        self.calls: list[tuple] = []
        self.query_params: list[dict] = []

    async def create_item(self, body: dict) -> dict:
        key = (body["id"], body.get("site"))
        self.calls.append(("create", key))
        if key in self.items:
            raise FakeCosmosError(409)
        self.items[key] = dict(body)
        return dict(body)

    async def upsert_item(self, body: dict) -> dict:
        key = (body["id"], body.get("site"))
        self.calls.append(("upsert", key))
        self.items[key] = dict(body)
        return dict(body)

    async def read_item(self, item, partition_key):
        self.calls.append(("read", (item, partition_key)))
        found = self.items.get((item, partition_key))
        if found is None:
            raise FakeCosmosError(404)
        return found

    async def delete_item(self, item, partition_key):
        self.calls.append(("delete", (item, partition_key)))
        if (item, partition_key) not in self.items:
            # The hazard: identical to "already gone".
            raise FakeCosmosError(404)
        if not self.delete_is_noop:
            del self.items[(item, partition_key)]

    async def query_items(self, **params):
        self.query_params.append(params)
        for row in self.rows:
            yield row


class FakeGate:
    """Counts acquisitions so chunking is observable."""

    def __init__(self) -> None:
        self.acquired = 0
        self.released = 0

    async def acquire(self) -> bool:
        self.acquired += 1
        return False

    async def record_success(self) -> None:
        pass

    def release(self, *, was_probe: bool = False) -> None:
        self.released += 1


class FakePoller:
    """An LROPoller whose ``result`` blocks, like a real one."""

    def __init__(self, delay: float = 0.0) -> None:
        self.delay = delay

    def result(self):
        if self.delay:
            time.sleep(self.delay)
        return {"provisioning_state": "Succeeded"}


class FakeAccounts:
    def __init__(self, readback=None, *, poller_delay: float = 0.0) -> None:
        self.readback = readback
        self.state = None
        self.poller_delay = poller_delay
        self.calls: list[str] = []

    def get(self, resource_group, name):
        self.calls.append("get")
        if self.state is None:
            raise FakeCosmosError(404)
        return dict(self.state)

    def begin_create_or_update(self, resource_group, name, spec):
        self.calls.append("create")
        self.state = self.readback
        return FakePoller(self.poller_delay)

    def begin_delete(self, resource_group, name):
        self.calls.append("delete")
        self.state = None
        return FakePoller()


def install_mgmt(accounts) -> FakeAccounts:
    client = types.SimpleNamespace(database_accounts=accounts, sql_resources=None)
    override(
        "azure.mgmt.cosmosdb",
        types.SimpleNamespace(
            CosmosDBManagementClient=lambda credential, subscription_id: client
        ),
    )
    return accounts


def writable(**overrides) -> WritePolicy:
    base = {
        "allow_write": True,
        "allow_delete": True,
        "verify_writes": False,
        "verify_attempts": 2,
        "verify_delay_secs": 0.01,
    }
    base.update(overrides)
    return WritePolicy(**base)


def items_connector(container, **kwargs) -> CosmosItems:
    return CosmosItems(container=container, partition_key_field="site", **kwargs)


# ── Write plane ──────────────────────────────────────────────────────────────


async def test_write_refusals() -> None:
    section("cosmos write plane: refusals")
    container = FakeContainer()
    conn = items_connector(container)

    upload = json.loads(await conn.upload([{"id": "a", "site": "north"}]))
    check("a default-policy connector refuses upload", upload["error"] is True)
    check("naming the missing grant", "read-only" in upload["detail"])

    deleted = json.loads(await conn.delete(["a"], partition_key="north"))
    check("and refuses delete", deleted["error"] is True)
    check("as a separate grant", "delete grant" in deleted["detail"])
    check("nothing reached the SDK", container.calls == [])

    write_only = items_connector(
        FakeContainer(), policy=WritePolicy(allow_write=True, verify_writes=False)
    )
    no_delete = json.loads(await write_only.delete(["a"], partition_key="north"))
    check("a write grant is not a delete grant", no_delete["error"] is True)


async def test_delete_verification() -> None:
    section("cosmos write plane: the delete that deleted nothing")
    container = FakeContainer(
        {("a", "north"): {"id": "a", "site": "north"}}, delete_is_noop=True
    )
    conn = items_connector(container, policy=writable())

    result = json.loads(await conn.delete(["a"], partition_key="north", verify=True))
    check("an accepted-but-not-applied delete FAILS", result.get("error") is True)
    check("naming the verification failure", "never became absent" in result["detail"])
    check("after re-reading the item", ("read", ("a", "north")) in container.calls)

    honest = FakeContainer({("a", "north"): {"id": "a", "site": "north"}})
    ok = json.loads(
        await items_connector(honest, policy=writable()).delete(
            ["a"], partition_key="north", verify=True
        )
    )
    check("a real delete verifies clean", ok["ok"] is True and ok["count"] == 1)


async def test_wrong_partition_key() -> None:
    section("cosmos write plane: the wrong partition key")
    live = {"id": "a", "site": "north"}
    container = FakeContainer({("a", "north"): live})
    conn = items_connector(container, policy=writable())

    # The item lives in partition 'north'; the caller deletes against 'south'.
    result = json.loads(await conn.delete(["a"], partition_key="south", verify=True))
    check("a 404 from delete is not a success", result.get("count") == 0)
    check("the key is reported as failed", result["failed"][0]["key"] == "a")
    check(
        "the detail says the item may live elsewhere",
        "another" in result["failed"][0]["detail"],
    )
    check("and the item is still there", container.items.get(("a", "north")) == live)

    still = json.loads(await conn.read("a", partition_key="north"))
    check("a correctly scoped read still finds it", still["count"] == 1)


async def test_unqualified_read() -> None:
    section("cosmos write plane: an unqualified read is a bug")
    container = FakeContainer({("a", "north"): {"id": "a", "site": "north"}})
    conn = items_connector(container, policy=writable())

    result = json.loads(await conn.read("a"))
    check("a read with no partition key fails", result["error"] is True)
    check("naming the partition key field", "site" in result["detail"])
    check("without a cross-partition scan", container.calls == [])

    from_pair = json.loads(await conn.read(("a", "north")))
    check("a derived (id, partition key) pair reads fine", from_pair["count"] == 1)


async def test_create_conflict() -> None:
    section("cosmos write plane: create over an existing key")
    container = FakeContainer({("a", "north"): {"id": "a", "site": "north"}})
    conn = items_connector(container, policy=writable())

    result = json.loads(
        await conn.create(
            [{"id": "a", "site": "north"}, {"id": "b", "site": "north"}]
        )
    )
    check("a 409 is an outcome, not an exception", result["ok"] is True)
    check("the conflicting key is in failed", result["failed"][0]["key"] == ["a", "north"])
    check("with a legible detail", result["failed"][0]["detail"] == "already exists")
    check("and the other item was created", result["count"] == 1)


async def test_query_guardrails() -> None:
    section("cosmos write plane: query guardrails")
    container = FakeContainer(rows=[{"id": "a"}])
    conn = items_connector(container)

    blocked = json.loads(await conn.query("DELETE FROM c"))
    check("refuses a write query", blocked["error"] is True)
    check("without reaching the SDK", container.query_params == [])

    payload = json.loads(await conn.query("SELECT * FROM c"))
    check("returns the read-plane shape", payload == {"results": [{"id": "a"}], "count": 1})
    check(
        "injects TOP when the caller supplied no limit",
        container.query_params[-1]["query"] == "SELECT TOP 500 * FROM c",
    )

    await conn.query("SELECT TOP 5 * FROM c")
    check(
        "and does not double-inject",
        container.query_params[-1]["query"] == "SELECT TOP 5 * FROM c",
    )

    await conn.query("SELECT * FROM c", max_rows=10)
    check(
        "honours an explicit row cap",
        container.query_params[-1]["query"] == "SELECT TOP 10 * FROM c",
    )


async def test_query_partition_scope() -> None:
    section("cosmos write plane: cross-partition is the absence of a key")
    container = FakeContainer(rows=[{"id": "a"}])
    conn = items_connector(container)

    await conn.query("SELECT * FROM c", partition_key="north")
    scoped = container.query_params[-1]
    check("a scoped query passes the partition key through", scoped["partition_key"] == "north")

    await conn.query("SELECT * FROM c")
    unscoped = container.query_params[-1]
    # On azure-cosmos 4.x there is no enable_cross_partition_query: the
    # query is cross-partition exactly when no partition_key is sent, and
    # query_items takes **kwargs, so a stale flag would be absorbed in
    # silence and read like an enforced scope.
    check(
        "an unscoped query is cross-partition by omission",
        "partition_key" not in unscoped,
    )
    check(
        "and the 3.x flag is never sent",
        all("enable_cross_partition_query" not in p for p in container.query_params),
    )


async def test_batching() -> None:
    section("cosmos write plane: chunking without dropping")
    container = FakeContainer()
    gate = FakeGate()
    conn = items_connector(
        container,
        policy=writable(max_batch=100),
        gate_provider=lambda: gate,
    )

    payload = [{"id": f"i{n}", "site": "north"} for n in range(250)]
    result = json.loads(await conn.upload(payload))
    upserts = [c for c in container.calls if c[0] == "upsert"]
    check("every item is written", result["count"] == 250)
    check("Cosmos has no batch API, so 250 requests", len(upserts) == 250)
    check("chunked into 3 gate acquisitions", gate.acquired == 3)
    check("and every permit released", gate.released == 3)


async def test_close() -> None:
    section("cosmos write plane: lifecycle")
    closed = {"n": 0}

    class _Client:
        async def close(self):
            closed["n"] += 1

    owned = items_connector(FakeContainer(), client=_Client())
    await owned.close()
    check("closes a client it constructed", closed["n"] == 1)

    await items_connector(FakeContainer()).close()
    check("and never one it was handed", closed["n"] == 1)


# ── Deploy plane ─────────────────────────────────────────────────────────────


def deploy_config() -> AzureDataConfig:
    return AzureDataConfig(
        subscription_id="sub",
        resource_group="rg",
        location="Australia East",
        cosmos_account_name="acct",
    )


ACCOUNT_SPEC = {
    "location": "Australia East",
    "kind": "GlobalDocumentDB",
    "public_network_access": "Enabled",
    "disable_local_auth": True,
}


async def test_policy_drift() -> None:
    section("cosmos deploy plane: Azure Policy drift")
    reverted = install_mgmt(
        FakeAccounts(
            {
                # ARM normalises the region; Policy reverted the access flag.
                "location": "australiaeast",
                "kind": "GlobalDocumentDB",
                "public_network_access": "Disabled",
                "disable_local_auth": True,
                "provisioning_state": "Succeeded",
            }
        )
    )
    prov = CosmosAccountProvisioner.from_config(
        deploy_config(),
        lambda: object(),
        policy=ProvisionPolicy.deployable(poll_timeout_secs=5.0),
    )
    result = json.loads(await prov.ensure(ACCOUNT_SPEC))
    check("a reverted setting is an ERROR, not a warning", result["error"] is True)
    check("naming the field Policy rewrote", "public_network_access" in result["detail"])
    check("blaming the right cause", "Policy" in result["detail"])
    check("and ignoring the normalised region", "location" not in result["detail"])
    check("after re-reading the resource", reverted.calls.count("get") == 2)

    install_mgmt(
        FakeAccounts(
            {
                "location": "australiaeast",
                "kind": "GlobalDocumentDB",
                "public_network_access": "Enabled",
                "disable_local_auth": True,
                "provisioning_state": "Succeeded",
            }
        )
    )
    clean = CosmosAccountProvisioner.from_config(
        deploy_config(),
        lambda: object(),
        policy=ProvisionPolicy.deployable(poll_timeout_secs=5.0),
    )
    ok = json.loads(await clean.ensure(ACCOUNT_SPEC))
    check("an honest deployment succeeds", ok["ok"] is True)
    check("and reports it created the account", ok["created"] is True)
    check("with no drift", ok["drift"] == {})


async def test_lro_bound() -> None:
    section("cosmos deploy plane: the poller is bounded")
    install_mgmt(FakeAccounts({"provisioning_state": "Succeeded"}, poller_delay=0.75))
    prov = CosmosAccountProvisioner.from_config(
        deploy_config(),
        lambda: object(),
        policy=ProvisionPolicy.deployable(poll_timeout_secs=0.05),
    )
    started = time.monotonic()
    result = json.loads(await prov.ensure(ACCOUNT_SPEC))
    elapsed = time.monotonic() - started
    check("a wedged LRO times out", result["error"] is True)
    check("naming the deadline", "did not reach a terminal state" in result["detail"])
    check("and gives up promptly", elapsed < 2.0)


async def test_teardown_refused() -> None:
    section("cosmos deploy plane: teardown needs its own grant")
    accounts = install_mgmt(FakeAccounts({"provisioning_state": "Succeeded"}))
    prov = CosmosAccountProvisioner.from_config(
        deploy_config(), lambda: object(), policy=ProvisionPolicy.deployable()
    )
    result = json.loads(await prov.teardown())
    check("teardown without a delete grant is refused", result["error"] is True)
    check("naming the missing grant", "delete grant" in result["detail"])
    check("without touching the service", accounts.calls == [])


def test_container_partition_key_drift() -> None:
    section("cosmos deploy plane: container partition key")
    spec = {"resource": {"id": "items", "partition_key": {"paths": ["/site"]}}}
    prov = CosmosContainerProvisioner(
        client=object(),
        resource_group="rg",
        account_name="acct",
        database="db",
        name="items",
    )
    verifiable = prov._verifiable(spec)  # noqa: SLF001 - the seam under test
    check("verifies the partition key paths", verifiable == {"partition_key_paths": ["/site"]})
    check(
        "and nothing the service normalises",
        list(verifiable) == ["partition_key_paths"],
    )


# ── The read-back shape azure-mgmt-cosmosdb 10 actually returns ──────────────
#
# Introspected, not assumed: SqlContainerGetResults and
# DatabaseAccountGetResults are collections.abc.Mapping subclasses, and
# dict(model) is the raw REST payload — camelCase keys, everything
# interesting under 'properties', and NO top-level 'resource' key even
# though model.resource returns one. A connector that reads the top level
# of that dict finds nothing and calls a healthy deployment drifted.


def v10_account(*, public_network_access: str = "Enabled") -> dict:
    return {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.DocumentDB/databaseAccounts/acct",
        "name": "acct",
        "type": "Microsoft.DocumentDB/databaseAccounts",
        "location": "australiaeast",
        "kind": "GlobalDocumentDB",
        "properties": {
            "provisioningState": "Succeeded",
            "publicNetworkAccess": public_network_access,
            "disableLocalAuth": True,
            "databaseAccountOfferType": "Standard",
            "locations": [
                {"locationName": "Australia East", "failoverPriority": 0}
            ],
        },
    }


def v10_container(*, paths=("/site",)) -> dict:
    return {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.DocumentDB/databaseAccounts/acct/sqlDatabases/db/"
        "containers/items",
        "name": "items",
        "type": "Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers",
        "properties": {
            "resource": {
                "id": "items",
                "partitionKey": {"paths": list(paths), "kind": "Hash"},
                "_rid": "rid",
                "_ts": 1,
                "_etag": "etag",
            },
            "options": {"throughput": 400},
        },
    }


class FakeSqlResources:
    """Serves the v10 container payload; ``begin_*`` records what was sent."""

    def __init__(self, readback: dict | None) -> None:
        self.readback = readback
        self.state: dict | None = None
        self.sent: list[dict] = []

    def get_sql_container(self, rg, account, database, name):
        if self.state is None:
            raise FakeCosmosError(404)
        return dict(self.state)

    def begin_create_update_sql_container(self, rg, account, database, name, spec):
        self.sent.append(spec)
        self.state = self.readback
        return FakePoller()

    def begin_delete_sql_container(self, rg, account, database, name):
        self.state = None
        return FakePoller()


async def test_v10_account_readback() -> None:
    section("cosmos deploy plane: the real v10 account read-back shape")
    install_mgmt(FakeAccounts(v10_account()))
    prov = CosmosAccountProvisioner.from_config(
        deploy_config(),
        lambda: object(),
        policy=ProvisionPolicy.deployable(poll_timeout_secs=5.0),
    )
    healthy = json.loads(await prov.ensure(ACCOUNT_SPEC))
    check("a camelCase nested read-back is NOT drift", healthy.get("ok") is True)
    check("with an empty drift map", healthy["drift"] == {})
    check("and the state read out of properties", healthy["state"] == "Succeeded")

    install_mgmt(FakeAccounts(v10_account(public_network_access="Disabled")))
    reverted = CosmosAccountProvisioner.from_config(
        deploy_config(),
        lambda: object(),
        policy=ProvisionPolicy.deployable(poll_timeout_secs=5.0),
    )
    drifted = json.loads(await reverted.ensure(ACCOUNT_SPEC))
    check("a genuinely reverted field IS drift", drifted.get("error") is True)
    check("naming the field", "public_network_access" in drifted["detail"])
    check("and still ignoring the normalised region", "location" not in drifted["detail"])


async def test_v10_container_readback() -> None:
    section("cosmos deploy plane: the real v10 container read-back shape")
    spec = {
        "location": "Australia East",
        "properties": {
            "resource": {
                "id": "items",
                "partitionKey": {"paths": ["/site"], "kind": "Hash"},
            },
            "options": {"throughput": 400},
        },
    }

    def provisioner(resources) -> CosmosContainerProvisioner:
        client = types.SimpleNamespace(database_accounts=None, sql_resources=resources)
        return CosmosContainerProvisioner(
            client=client,
            resource_group="rg",
            account_name="acct",
            database="db",
            name="items",
            policy=ProvisionPolicy.deployable(poll_timeout_secs=5.0),
        )

    resources = FakeSqlResources(v10_container())
    healthy = json.loads(await provisioner(resources).ensure(spec))
    check("a healthy container reports NO drift", healthy.get("ok") is True)
    check("with an empty drift map", healthy["drift"] == {})
    check("the REST-shaped spec reached ARM verbatim", resources.sent[0] == spec)

    wrong = json.loads(
        await provisioner(FakeSqlResources(v10_container(paths=("/wrong",)))).ensure(spec)
    )
    check("a container built on the wrong path IS drift", wrong.get("error") is True)
    check("naming the partition key paths", "partition_key_paths" in wrong["detail"])


def test_configuration() -> None:
    section("cosmos deploy plane: unconfigured coordinates")
    install_mgmt(FakeAccounts(None))
    envelope = json.loads(
        CosmosAccountProvisioner.from_config(
            AzureDataConfig(resource_group="rg", location="l", cosmos_account_name="a"),
            lambda: object(),
        )
    )
    check("a missing coordinate is an error envelope", envelope["error"] is True)
    check("naming the field", "subscription_id" in envelope["detail"])

    database = CosmosDatabaseProvisioner.from_config(
        deploy_config(), lambda: object(), database="db"
    )
    check("a complete config builds a provisioner", isinstance(database, CosmosDatabaseProvisioner))
    check("labelled by resource kind", database.resource_kind == "cosmos-database")


def test_missing_sdk() -> None:
    section("cosmos deploy plane: missing SDK")
    clear_overrides()
    # None in sys.modules makes import_module raise ImportError, which is
    # absence as the loader sees it. Relying on azure-mgmt-cosmosdb genuinely
    # not being installed would make this pass or fail by accident.
    blocked = "azure.mgmt.cosmosdb"
    previous = sys.modules.get(blocked, "<unset>")
    sys.modules[blocked] = None  # type: ignore[assignment]
    try:
        CosmosAccountProvisioner.from_config(deploy_config(), lambda: object())
        check("raises MissingDependency", False)
    except MissingDependency as exc:
        check("raises MissingDependency", True)
        check("naming the distribution to install", "azure-mgmt-cosmosdb" in str(exc))
    finally:
        if previous == "<unset>":
            sys.modules.pop(blocked, None)
        else:
            sys.modules[blocked] = previous


# ── Runner ───────────────────────────────────────────────────────────────────


async def main() -> int:
    try:
        await test_write_refusals()
        await test_delete_verification()
        await test_wrong_partition_key()
        await test_unqualified_read()
        await test_create_conflict()
        await test_query_guardrails()
        await test_query_partition_scope()
        await test_batching()
        await test_close()
        await test_policy_drift()
        await test_v10_account_readback()
        await test_v10_container_readback()
        await test_lro_bound()
        await test_teardown_refused()
        test_container_partition_key_drift()
        test_configuration()
        test_missing_sdk()
    finally:
        clear_overrides()

    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} check(s)")
        for failure in _FAILURES:
            print(f"  - {failure}")
        return 1
    print("cosmos plane tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
