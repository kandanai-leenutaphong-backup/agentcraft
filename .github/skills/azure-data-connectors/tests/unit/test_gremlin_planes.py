"""test_gremlin_planes — the Gremlin write and deploy planes, with no SDKs.

Run: ``python3 tests/test_gremlin_planes.py``. Exits non-zero on failure.

The gremlinpython driver and ``azure-mgmt-cosmosdb`` are replaced by fakes
through ``azdata.core.optional``, so this exercises traversal generation,
escaping, the silent no-op delete, the read-only bypass boundary and the
bounded LRO on a laptop with no cloud account and nothing installed. The
fakes assert on the exact traversal text and the exact ARM parameters the
connectors sent, so this is a contract test of what goes on the wire.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
import time
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.core.config import AzureDataConfig  # noqa: E402
from azdata.core.crud import WritePolicy  # noqa: E402
from azdata.gremlin.read import GremlinConnector  # noqa: E402
from azdata.gremlin.write import GremlinElements, _literal  # noqa: E402
from azdata.gremlin.deploy import (  # noqa: E402
    GremlinDatabaseProvisioner,
    GremlinGraphProvisioner,
)
from azdata.core.optional import clear_overrides, override  # noqa: E402
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


class FakeToken:
    def __init__(self, token: str = "tok", expires_in: float = 3600.0) -> None:
        self.token = token
        self.expires_on = time.time() + expires_in


class FakeCredential:
    def __init__(self) -> None:
        self.calls = 0

    def get_token(self, scope: str) -> FakeToken:
        self.calls += 1
        return FakeToken(f"tok-{self.calls}")


_HAS_KEY_RE = re.compile(r"has\('id', '((?:[^'\\]|\\.)*)'\)")
_ADDV_KEY_RE = re.compile(r"addV\('[^']*'\)\.property\('id', '((?:[^'\\]|\\.)*)'\)")


def install_fake_graph(existing=(), *, drop_is_silent: bool = False):
    """A driver fake that keeps a tiny vertex store and logs every traversal.

    ``drop_is_silent`` reproduces the failure this package exists to catch:
    ``drop()`` returns without error and the vertex is still there.
    """
    log = {"queries": [], "clients": 0, "closed": 0}
    store = {key: {"id": [key]} for key in existing}

    def _key(query: str) -> str | None:
        match = _HAS_KEY_RE.search(query) or _ADDV_KEY_RE.search(query)
        return match.group(1) if match else None

    class _Result:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class _Future:
        def __init__(self, value):
            self._value = value

        def all(self):
            return _Result(self._value)

    class _Client:
        def __init__(self, **kwargs):
            log["clients"] += 1

        def submit(self, query):
            log["queries"].append(query)
            key = _key(query)
            if ".count()" in query:
                return _Future([1 if key in store else 0])
            if ".valueMap(" in query:
                return _Future([store[key]] if key in store else [])
            if ".drop()" in query:
                if not drop_is_silent:
                    store.pop(key, None)
                return _Future([])
            if "addV(" in query:
                store[key] = {"id": [key]}
                return _Future([])
            return _Future([])

        def close(self):
            log["closed"] += 1

    override("gremlin_python.driver.client", types.SimpleNamespace(Client=_Client))
    override(
        "gremlin_python.driver.serializer",
        types.SimpleNamespace(GraphSONSerializersV2d0=lambda: "serializer"),
    )
    return log, store


def install_fake_cosmos_mgmt(*, graph=None, database=None, read_back=None, poller_delay=0.0):
    """A management fake recording the exact ARM parameter dicts it received."""
    log = {"clients": 0, "created": [], "deleted": []}
    state = {"graph": graph, "database": database}

    class _NotFound(Exception):
        def __init__(self) -> None:
            super().__init__("Resource not found")
            self.status_code = 404

    class _Poller:
        def result(self):
            if poller_delay:
                time.sleep(poller_delay)
            return state["graph"]

    def _graph_doc(name, parameters):
        resource = parameters["properties"]["resource"]
        return {
            "name": name,
            "resource": {
                "id": name,
                "partition_key": resource["partitionKey"],
                "provisioning_state": "Succeeded",
            },
        }

    class _Resources:
        def get_gremlin_database(self, rg, account, name):
            if state["database"] is None:
                raise _NotFound()
            return state["database"]

        def begin_create_update_gremlin_database(self, rg, account, name, parameters):
            log["created"].append(parameters)
            state["database"] = {
                "name": name,
                "resource": {"id": name, "provisioning_state": "Succeeded"},
            }
            return _Poller()

        def begin_delete_gremlin_database(self, rg, account, name):
            log["deleted"].append(name)
            state["database"] = None
            return _Poller()

        def get_gremlin_graph(self, rg, account, database, name):
            if state["graph"] is None:
                raise _NotFound()
            return state["graph"]

        def begin_create_update_gremlin_graph(self, rg, account, database, name, parameters):
            log["created"].append(parameters)
            state["graph"] = (
                read_back if read_back is not None else _graph_doc(name, parameters)
            )
            return _Poller()

        def begin_delete_gremlin_graph(self, rg, account, database, name):
            log["deleted"].append(name)
            state["graph"] = None
            return _Poller()

    class _Client:
        def __init__(self, credential, subscription_id):
            log["clients"] += 1
            self.credential = credential
            self.subscription_id = subscription_id
            self.gremlin_resources = _Resources()

    override(
        "azure.mgmt.cosmosdb",
        types.SimpleNamespace(CosmosDBManagementClient=_Client),
    )
    return log, state


# ── Helpers ──────────────────────────────────────────────────────────────────


CFG = AzureDataConfig(
    gremlin_endpoint="wss://example/gremlin",
    gremlin_database="db",
    gremlin_graph="graph",
    max_rows=25,
    subscription_id="sub",
    resource_group="rg",
    location="australiaeast",
    gremlin_account_name="acct",
)

WRITABLE = WritePolicy.writable(allow_delete=True, verify_writes=False).with_overrides(
    verify_attempts=2, verify_delay_secs=0.01
)


def elements(policy: WritePolicy | None = None) -> GremlinElements:
    return GremlinElements(
        GremlinConnector.from_config(CFG, lambda: FakeCredential()),
        label="thing",
        partition_key_field="pk",
        policy=policy,
    )


def has_unescaped(traversal: str, character: str) -> bool:
    """True when ``character`` appears outside a Gremlin string literal."""
    in_literal = False
    index = 0
    while index < len(traversal):
        ch = traversal[index]
        if in_literal and ch == "\\":
            index += 2
            continue
        if ch == "'":
            in_literal = not in_literal
        elif ch == character and not in_literal:
            return True
        index += 1
    return False


# ── Write plane ──────────────────────────────────────────────────────────────


async def test_write_policy() -> None:
    section("gremlin write plane — policy")
    log, _ = install_fake_graph()
    conn = elements()

    refused_upload = json.loads(await conn.upload([{"id": "v1", "pk": "p1"}]))
    check("a default-policy connector refuses upload", refused_upload["error"] is True)
    check("naming the grant it lacks", "read-only" in refused_upload["detail"])

    refused_delete = json.loads(await conn.delete(["v1"]))
    check("and refuses delete separately", refused_delete["error"] is True)
    check("naming the delete grant", "delete grant" in refused_delete["detail"])

    check("nothing reached the driver", log["queries"] == [])
    check("and no client was ever built", log["clients"] == 0)


async def test_injection() -> None:
    section("gremlin write plane — injection")
    log, _ = install_fake_graph()
    conn = elements(WRITABLE)

    hostile = "hello' ; g.V().drop() ; '"
    payload = json.loads(
        await conn.upload([{"id": "v1", "pk": "p1", "note": hostile}], verify=False)
    )
    check("the upsert is accepted", payload["ok"] is True and payload["count"] == 1)

    traversal = log["queries"][0]
    expected = (
        "g.V().has('id', 'v1').fold().coalesce(unfold(), "
        "addV('thing').property('id', 'v1').property('pk', 'p1'))"
        ".property('note', 'hello\\' ; g.V().drop() ; \\'')"
    )
    check("the traversal is exactly the escaped upsert", traversal == expected)
    check("no quote escapes the literal", not has_unescaped(traversal, "'"))
    check("no second statement is introduced", not has_unescaped(traversal, ";"))
    check("only one traversal was submitted", len(log["queries"]) == 1)


def test_literal() -> None:
    section("gremlin write plane — literals")
    check("escapes a quote", _literal("o'brien") == "'o\\'brien'")
    check("escapes a backslash first", _literal("a\\") == "'a\\\\'")
    check("renders a bool as gremlin, not python", _literal(True) == "true")
    check("renders an int bare", _literal(7) == "7")
    check("renders None as null", _literal(None) == "null")
    check("escapes a newline", _literal("a\nb") == "'a\\nb'")

    for value in ({"a": 1}, ["a"], object()):
        try:
            rendered = _literal(value)
            check(f"refuses {type(value).__name__}", False)
            check("did not interpolate a repr", rendered is None)
        except (TypeError, ValueError) as exc:
            check(f"refuses {type(value).__name__}", True)
            check(
                f"naming the offending type for {type(value).__name__}",
                type(value).__name__ in str(exc),
            )

    try:
        _literal("bad\x00value")
        check("refuses a control character", False)
    except ValueError:
        check("refuses a control character", True)


async def test_silent_delete() -> None:
    section("gremlin write plane — the silent no-op delete")
    log, _ = install_fake_graph(["v1"], drop_is_silent=True)
    conn = elements(WRITABLE)

    payload = json.loads(await conn.delete(["v1"], verify=True))
    check("a drop that changed nothing is an error", payload.get("error") is True)
    check(
        "naming the verification failure",
        "never became absent" in payload["detail"],
    )
    check("after actually attempting the drop", any(".drop()" in q for q in log["queries"]))

    live_log, _ = install_fake_graph(["v2"])
    live = elements(WRITABLE)
    ok = json.loads(await live.delete(["v2"], verify=True))
    check("a real delete verifies clean", ok["ok"] is True and ok["count"] == 1)
    check("and re-read to prove it", any(".valueMap(" in q for q in live_log["queries"]))

    absent = json.loads(await live.delete(["nope"], verify=True))
    check("a key that never existed is not counted as deleted", absent["count"] == 0)
    check("and appears in failed", absent["failed"][0]["key"] == "nope")


async def test_partition_key_and_create() -> None:
    section("gremlin write plane — partition key and create")
    log, _ = install_fake_graph()
    conn = elements(WRITABLE)

    payload = json.loads(await conn.upload([{"id": "v1", "name": "x"}], verify=False))
    check("an item without the partition key is refused", payload["error"] is True)
    check("naming the field", "'pk'" in payload["detail"])
    check("before any traversal was built", log["queries"] == [])

    existing_log, _ = install_fake_graph(["v1"])
    dup = elements(WRITABLE)
    created = json.loads(
        await dup.create([{"id": "v1", "pk": "p1"}], verify=False)
    )
    check("create on an existing id is not an exception", created["ok"] is True)
    check("it lands in failed", created["count"] == 0 and len(created["failed"]) == 1)
    check(
        "with a legible reason",
        "already exists" in created["failed"][0]["detail"],
    )
    check(
        "and no addV was submitted",
        not any("addV(" in q for q in existing_log["queries"]),
    )

    fresh = json.loads(await dup.create([{"id": "v2", "pk": "p1"}], verify=False))
    check("create on a free id succeeds", fresh["count"] == 1)
    check(
        "as a plain addV carrying the partition key",
        existing_log["queries"][-1]
        == "g.addV('thing').property('id', 'v2').property('pk', 'p1')",
    )


async def test_guard_boundary() -> None:
    section("gremlin write plane — the guard boundary")
    log, _ = install_fake_graph()
    conn = elements(WRITABLE)

    refused = json.loads(await conn.query("g.V().drop()"))
    check("a caller-supplied write is refused", refused["error"] is True)
    check("by the read-only guardrail", "Write operations not allowed" in refused["detail"])
    check("and never reaches the driver", log["queries"] == [])

    await conn.query("g.V().hasLabel('thing')")
    check(
        "a caller-supplied read is limit-injected",
        log["queries"][-1] == "g.V().hasLabel('thing').limit(25)",
    )

    await conn.upload([{"id": "v9", "pk": "p1"}], verify=False)
    check(
        "a generated mutation is not limit-injected",
        ".limit(" not in log["queries"][-1],
    )
    check("and did mutate", "addV(" in log["queries"][-1])


# ── Deploy plane ─────────────────────────────────────────────────────────────


async def test_graph_provisioner() -> None:
    section("gremlin deploy plane — graph")
    log, state = install_fake_cosmos_mgmt()
    prov = GremlinGraphProvisioner.from_config(
        CFG, lambda: FakeCredential(), policy=ProvisionPolicy.deployable()
    )
    check("from_config builds a provisioner", isinstance(prov, GremlinGraphProvisioner))

    payload = json.loads(await prov.ensure({"partition_key_paths": ["/pk"]}))
    check("ensure succeeds on a matching read-back", payload["ok"] is True)
    check("and reports the create", payload["created"] is True)
    check("with no drift", payload["drift"] == {})
    check(
        "the partition path was sent rooted",
        log["created"][0]["properties"]["resource"]["partitionKey"]["paths"] == ["/pk"],
    )

    unrooted, _ = install_fake_cosmos_mgmt()
    prov2 = GremlinGraphProvisioner.from_config(
        CFG, lambda: FakeCredential(), policy=ProvisionPolicy.deployable()
    )
    rooted = json.loads(await prov2.ensure({"partition_key_paths": ["pk"]}))
    check("a caller's unrooted path is normalised, not drift", rooted["ok"] is True)

    wrong, _ = install_fake_cosmos_mgmt(
        read_back={
            "name": "graph",
            "resource": {
                "id": "graph",
                "partition_key": {"paths": ["/wrong"], "kind": "Hash"},
                "provisioning_state": "Succeeded",
            },
        }
    )
    drifted = GremlinGraphProvisioner.from_config(
        CFG, lambda: FakeCredential(), policy=ProvisionPolicy.deployable()
    )
    bad = json.loads(await drifted.ensure({"partition_key_paths": ["/pk"]}))
    check("a different partition key path is an error", bad.get("error") is True)
    check("named as drift", "partition_key_paths" in bad["detail"])

    no_delete = GremlinGraphProvisioner.from_config(
        CFG, lambda: FakeCredential(), policy=ProvisionPolicy.deployable()
    )
    refused = json.loads(await no_delete.teardown())
    check("teardown without a delete grant is refused", refused.get("error") is True)
    check("naming the grant", "delete grant" in refused["detail"])


async def test_poller_deadline() -> None:
    section("gremlin deploy plane — bounded LRO")
    install_fake_cosmos_mgmt(poller_delay=0.3)
    prov = GremlinGraphProvisioner.from_config(
        CFG,
        lambda: FakeCredential(),
        policy=ProvisionPolicy.deployable(poll_timeout_secs=0.05),
    )
    started = time.monotonic()
    payload = json.loads(await prov.ensure({"partition_key_paths": ["/pk"]}))
    elapsed = time.monotonic() - started
    check("a slow poller times out", payload.get("error") is True)
    check("as a timeout, not a hang", "did not reach a terminal state" in payload["detail"])
    check("and gives up well inside the deadline", elapsed < 2.0)


async def test_database_provisioner() -> None:
    section("gremlin deploy plane — database")
    log, _ = install_fake_cosmos_mgmt()
    prov = GremlinDatabaseProvisioner.from_config(
        CFG,
        lambda: FakeCredential(),
        policy=ProvisionPolicy.deployable(allow_delete=True),
    )
    payload = json.loads(await prov.ensure({"throughput": 400}))
    check("ensure creates the database", payload["ok"] is True and payload["created"])
    check(
        "throughput travels in options",
        log["created"][0]["properties"]["options"]["throughput"] == 400,
    )
    check("and is not compared as drift", payload["drift"] == {})

    torn = json.loads(await prov.teardown())
    check("teardown deletes and verifies", torn["ok"] is True and torn["deleted"] is True)

    unconfigured = GremlinDatabaseProvisioner.from_config(
        AzureDataConfig(gremlin_database="db"), lambda: FakeCredential()
    )
    check("an unconfigured coordinate returns an envelope", isinstance(unconfigured, str))
    check(
        "naming the missing field",
        "subscription_id" in json.loads(unconfigured)["detail"],
    )


async def test_v10_graph_readback() -> None:
    section("gremlin deploy plane — the real v10 read-back shape")
    # Introspected, not assumed: GremlinGraphGetResults is a
    # collections.abc.Mapping subclass whose dict view is the raw REST
    # payload — camelCase, 'resource' nested under 'properties', and no
    # top-level 'resource' key however much model.resource suggests one.
    def v10_graph(paths=("/pk",)) -> dict:
        return {
            "id": "/subscriptions/sub/resourceGroups/rg/providers/"
            "Microsoft.DocumentDB/databaseAccounts/acct/gremlinDatabases/db/"
            "graphs/graph",
            "name": "graph",
            "type": "Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs",
            "properties": {
                "resource": {
                    "id": "graph",
                    "partitionKey": {"paths": list(paths), "kind": "Hash"},
                    "_rid": "rid",
                    "_ts": 1,
                    "_etag": "etag",
                }
            },
        }

    install_fake_cosmos_mgmt(read_back=v10_graph())
    healthy = GremlinGraphProvisioner.from_config(
        CFG, lambda: FakeCredential(), policy=ProvisionPolicy.deployable()
    )
    clean = json.loads(await healthy.ensure({"partition_key_paths": ["/pk"]}))
    check("a camelCase nested read-back is NOT drift", clean.get("ok") is True)
    check("with an empty drift map", clean["drift"] == {})

    install_fake_cosmos_mgmt(read_back=v10_graph(paths=("/wrong",)))
    reverted = GremlinGraphProvisioner.from_config(
        CFG, lambda: FakeCredential(), policy=ProvisionPolicy.deployable()
    )
    bad = json.loads(await reverted.ensure({"partition_key_paths": ["/pk"]}))
    check("a genuinely wrong path IS drift", bad.get("error") is True)
    check("naming the partition key paths", "partition_key_paths" in bad["detail"])


async def test_v10_database_readback() -> None:
    section("gremlin deploy plane — the real v10 database read-back shape")
    v10_database = {
        "id": "/subscriptions/sub/resourceGroups/rg/providers/"
        "Microsoft.DocumentDB/databaseAccounts/acct/gremlinDatabases/db",
        "name": "db",
        "type": "Microsoft.DocumentDB/databaseAccounts/gremlinDatabases",
        "properties": {
            "resource": {"id": "db", "_rid": "rid", "_ts": 1, "_etag": "etag"}
        },
    }
    log, state = install_fake_cosmos_mgmt(database=v10_database)
    prov = GremlinDatabaseProvisioner.from_config(
        CFG, lambda: FakeCredential(), policy=ProvisionPolicy.deployable()
    )
    payload = json.loads(await prov.ensure({"throughput": 400}))
    check("a nested database read-back is NOT drift", payload.get("ok") is True)
    check("with an empty drift map", payload["drift"] == {})
    check("and it was already present, so not created", payload["created"] is False)


async def test_missing_sdk() -> None:
    section("gremlin deploy plane — missing SDK")
    clear_overrides()
    # None in sys.modules makes import_module raise ImportError, which is
    # absence as the loader sees it. Relying on azure-mgmt-cosmosdb genuinely
    # not being installed would make this pass or fail by accident.
    blocked = "azure.mgmt.cosmosdb"
    previous = sys.modules.get(blocked, "<unset>")
    sys.modules[blocked] = None  # type: ignore[assignment]
    try:
        prov = GremlinGraphProvisioner.from_config(CFG, lambda: FakeCredential())
        payload = json.loads(await prov.describe())
    finally:
        if previous == "<unset>":
            sys.modules.pop(blocked, None)
        else:
            sys.modules[blocked] = previous
    check("a missing SDK is an envelope, not an ImportError", payload["error"] is True)
    check("of type MissingDependency", "MissingDependency" in payload["detail"])
    check("naming the distribution", "azure-mgmt-cosmosdb" in payload["detail"])


# ── Runner ───────────────────────────────────────────────────────────────────


async def main() -> int:
    try:
        await test_write_policy()
        await test_injection()
        test_literal()
        await test_silent_delete()
        await test_partition_key_and_create()
        await test_guard_boundary()
        await test_graph_provisioner()
        await test_v10_graph_readback()
        await test_v10_database_readback()
        await test_poller_deadline()
        await test_database_provisioner()
        await test_missing_sdk()
    finally:
        clear_overrides()

    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} check(s)")
        for failure in _FAILURES:
            print(f"  - {failure}")
        return 1
    print("gremlin plane tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
