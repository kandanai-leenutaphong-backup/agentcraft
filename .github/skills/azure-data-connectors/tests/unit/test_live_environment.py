"""test_live_environment — the live conformance topology, with no Azure.

Run: ``.venv/bin/python -m pytest tests/unit/test_live_environment.py -q``,
or ``python3 tests/unit/test_live_environment.py`` for the same checks as a
script.

Every management and data SDK is substituted through
``azdata.core.optional.override``. Nothing here opens a socket, and the
whole file passes with no Azure SDK installed at all — which is the point:
the lifecycle is exercised on a laptop before it is ever pointed at a
subscription that bills.

The load-bearing test is ``test_down_refuses_an_untagged_group``. A
teardown that can reach a resource group it did not create is a teardown
that will eventually reach the wrong one.
"""

from __future__ import annotations

import asyncio
import collections.abc
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.core.breaker import reset_gates  # noqa: E402
from azdata.core.optional import clear_overrides, override  # noqa: E402
from azdata import live as live_package  # noqa: E402
from azdata.live import seed  # noqa: E402
from azdata.live import environment as environment_module  # noqa: E402
from azdata.live.__main__ import build_parser  # noqa: E402
from azdata.live.environment import (  # noqa: E402
    COSMOS_ACCOUNT,
    GREMLIN_ACCOUNT,
    KUSTO_CLUSTER,
    LOG_WORKSPACE,
    OWNER_TAG_KEY,
    OWNER_TAG_VALUE,
    RESOURCE_GROUP,
    ROLES,
    SEARCH_SERVICE,
    TOPOLOGY,
    Environment,
    LiveEnvironmentError,
    NameUnavailable,
    TeardownRefused,
    assert_no_secrets,
    principal_from_token,
    validate_account_name,
)

_FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        _FAILURES.append(label)
    assert condition, label


def section(title: str) -> None:
    print(title)


# ── Fakes ────────────────────────────────────────────────────────────────────


class NotFound(Exception):
    status_code = 404


class Model(collections.abc.Mapping):
    """The JSON-backed management model shape both cosmosdb and kusto use."""

    def __init__(self, **payload):
        self._payload = dict(payload)

    def __getitem__(self, key):
        return self._payload[key]

    def __iter__(self):
        return iter(self._payload)

    def __len__(self):
        return len(self._payload)

    def as_dict(self):
        return dict(self._payload)


def poller(value=None):
    return types.SimpleNamespace(result=lambda: value)


class FakeCredential:
    #: An unsigned JWT whose payload carries the claims a role assignment
    #: needs. Nothing verifies it; nothing is supposed to.
    def get_token(self, scope):
        import base64

        claims = base64.urlsafe_b64encode(
            json.dumps({"oid": "principal-1", "tid": "tenant-1", "upn": "a@b.c"}).encode()
        ).decode().rstrip("=")
        return types.SimpleNamespace(token=f"header.{claims}.signature", expires_on=0)


class Azure:
    """One in-memory subscription: every ARM and data-plane call lands here.

    Stateful, because idempotency and resume are the properties under
    test and a stub that answered from a script could not express either.
    """

    def __init__(self, *, group_tags=None, group_present=False, fail=None):
        self.groups: dict[str, dict] = {}
        if group_present:
            self.groups[RESOURCE_GROUP] = {
                "id": f"/subscriptions/sub/resourceGroups/{RESOURCE_GROUP}",
                "name": RESOURCE_GROUP,
                "location": "eastus",
                "tags": dict(
                    group_tags
                    if group_tags is not None
                    else {OWNER_TAG_KEY: OWNER_TAG_VALUE}
                ),
            }
        self.generic: dict[str, dict] = {}
        self.search: dict[str, dict] = {}
        self.indexes: dict[str, object] = {}
        self.accounts: dict[str, dict] = {}
        self.sql_databases: set = set()
        self.sql_containers: dict = {}
        self.gremlin_databases: set = set()
        self.gremlin_graphs: dict = {}
        self.clusters: dict[str, dict] = {}
        self.kusto_databases: set = set()
        self.tables: dict[str, str] = {}
        self.rows: dict[str, int] = {}
        self.role_assignments: list[dict] = []
        self.cosmos_role_assignments: list[dict] = []
        self.kusto_role_assignments: list[dict] = []
        self.deleted_groups: list[str] = []
        self.search_creates = 0
        self.cluster_creates = 0
        #: Step name that should raise once, to model a partial failure.
        self.fail = fail
        self.failed_once = False

    def _maybe_fail(self, step):
        if self.fail == step and not self.failed_once:
            self.failed_once = True
            raise RuntimeError(f"{step} exploded")


# -- azure.mgmt.resource -----------------------------------------------------


def fake_resource_module(azure: Azure):
    class _Groups:
        def get(self, name):
            group = azure.groups.get(name)
            if group is None:
                raise NotFound(f"resource group '{name}' was not found")
            return Model(**group)

        def create_or_update(self, name, parameters):
            azure._maybe_fail("resource-group")
            azure.groups[name] = {
                "id": f"/subscriptions/sub/resourceGroups/{name}",
                "name": name,
                "location": parameters.get("location", ""),
                "tags": dict(parameters.get("tags") or {}),
            }
            return Model(**azure.groups[name])

        def begin_delete(self, name):
            azure.deleted_groups.append(name)
            azure.groups.pop(name, None)
            return poller()

    class _Resources:
        # Signature mirrors azure-mgmt-resource 26: api_version is keyword-only
        # and follows parameters. A fake with the older positional arity let an
        # arity bug reach Azure.
        def get(self, rg, namespace, parent, rtype, name, *, api_version):
            key = f"{namespace}/{rtype}/{name}"
            resource = azure.generic.get(key)
            if resource is None:
                raise NotFound(f"'{name}' was not found")
            return Model(**resource)

        def begin_create_or_update(
            self, rg, namespace, parent, rtype, name, parameters, *, api_version
        ):
            azure._maybe_fail("log-workspace")
            key = f"{namespace}/{rtype}/{name}"
            azure.generic[key] = {
                "name": name,
                "location": parameters.get("location", ""),
                "tags": dict(parameters.get("tags") or {}),
                "properties": {"provisioningState": "Succeeded"},
            }
            return poller()

    class _Client:
        def __init__(self, credential, subscription_id):
            self.resource_groups = _Groups()
            self.resources = _Resources()

    return types.SimpleNamespace(ResourceManagementClient=_Client)


# -- azure.mgmt.authorization ------------------------------------------------


def fake_authorization_module(azure: Azure):
    class _RoleAssignments:
        def create(self, scope, name, parameters):
            azure._maybe_fail("role-assignments")
            azure.role_assignments.append({"scope": scope, **dict(parameters)})
            return Model(name=name)

    class _Client:
        def __init__(self, credential, subscription_id):
            self.role_assignments = _RoleAssignments()

    return types.SimpleNamespace(AuthorizationManagementClient=_Client)


# -- azure.mgmt.search -------------------------------------------------------


class FakeSearchService:
    """msrest-style: not a Mapping, flattened snake_case as_dict()."""

    def __init__(self, **fields):
        self._fields = dict(fields)

    def as_dict(self):
        return dict(self._fields)


def fake_search_mgmt_module(azure: Azure):
    class _Services:
        def get(self, rg, name):
            service = azure.search.get(name)
            if service is None:
                raise NotFound(f"service '{name}' was not found")
            return FakeSearchService(**service)

        def begin_create_or_update(self, rg, name, spec):
            azure._maybe_fail("search-service")
            azure.search_creates += 1
            azure.search[name] = {
                "location": "eastus",
                "sku": dict(spec.get("sku") or {}),
                "tags": dict(spec.get("tags") or {}),
                "replica_count": spec.get("replica_count"),
                "partition_count": spec.get("partition_count"),
                "provisioning_state": "Succeeded",
            }
            return poller()

        def delete(self, rg, name):
            azure.search.pop(name, None)

    class _Client:
        def __init__(self, credential, subscription_id):
            self.services = _Services()

    return types.SimpleNamespace(SearchManagementClient=_Client)


# -- azure.search.documents.indexes ------------------------------------------


class FakeField:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeIndex:
    def __init__(self, name, fields, **kwargs):
        self.name = name
        self.fields = list(fields)
        self.__dict__.update(kwargs)


class FakeVectorProfile:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeHnswAlgorithm:
    kind = "hnsw"

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeExhaustiveKnnAlgorithm:
    kind = "exhaustiveKnn"

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeVectorSearch:
    def __init__(self, profiles=(), algorithms=()):
        self.profiles = list(profiles)
        self.algorithms = list(algorithms)


def fake_index_modules(azure: Azure):
    class _IndexClient:
        def __init__(self, **kwargs):
            pass

        def get_index(self, name):
            index = azure.indexes.get(name)
            if index is None:
                raise NotFound(f"index '{name}' was not found")
            return index

        def create_or_update_index(self, index):
            azure._maybe_fail("search-index")
            azure.indexes[index.name] = index
            return index

        def delete_index(self, name):
            azure.indexes.pop(name, None)

    override(
        "azure.search.documents.indexes",
        types.SimpleNamespace(SearchIndexClient=_IndexClient),
    )
    # The vector models are part of the real module. A fake without them lets a
    # dict reach the wire in snake_case and the suite never notices.
    override(
        "azure.search.documents.indexes.models",
        types.SimpleNamespace(
            SearchField=FakeField,
            SearchIndex=FakeIndex,
            VectorSearch=FakeVectorSearch,
            VectorSearchProfile=FakeVectorProfile,
            HnswAlgorithmConfiguration=FakeHnswAlgorithm,
            ExhaustiveKnnAlgorithmConfiguration=FakeExhaustiveKnnAlgorithm,
        ),
    )


# -- azure.mgmt.cosmosdb -----------------------------------------------------


def fake_cosmos_mgmt_module(azure: Azure):
    class _Accounts:
        def get(self, rg, name):
            account = azure.accounts.get(name)
            if account is None:
                raise NotFound(f"account '{name}' was not found")
            return Model(**account)

        def check_name_exists(self, name):
            return name in azure.accounts

        def begin_create_or_update(self, rg, name, spec):
            azure._maybe_fail("cosmos-account")
            properties = dict(spec.get("properties") or {})
            properties["provisioningState"] = "Succeeded"
            azure.accounts[name] = {
                "name": name,
                "location": spec.get("location", ""),
                "kind": spec.get("kind", ""),
                "tags": dict(spec.get("tags") or {}),
                "properties": properties,
            }
            return poller()

        def begin_delete(self, rg, name):
            azure.accounts.pop(name, None)
            return poller()

    class _Sql:
        def get_sql_database(self, rg, account, name):
            if (account, name) not in azure.sql_databases:
                raise NotFound(f"database '{name}' was not found")
            return Model(
                id=name,
                name=name,
                properties={"resource": {"id": name}, "provisioningState": "Succeeded"},
            )

        def begin_create_update_sql_database(self, rg, account, name, parameters):
            azure.sql_databases.add((account, name))
            return poller()

        def get_sql_container(self, rg, account, database, name):
            container = azure.sql_containers.get((account, database, name))
            if container is None:
                raise NotFound(f"container '{name}' was not found")
            return Model(
                name=name,
                properties={"resource": container, "provisioningState": "Succeeded"},
            )

        def begin_create_update_sql_container(self, rg, account, database, name, parameters):
            resource = dict(parameters["properties"]["resource"])
            azure.sql_containers[(account, database, name)] = resource
            return poller()

        def begin_create_update_sql_role_assignment(
            self,
            role_assignment_id,
            resource_group_name,
            account_name,
            create_update_sql_role_assignment_parameters,
        ):
            azure._maybe_fail("role-assignments")
            azure.cosmos_role_assignments.append(
                {
                    "account": account_name,
                    **dict(create_update_sql_role_assignment_parameters),
                }
            )
            return poller()

    class _Gremlin:
        def get_gremlin_database(self, rg, account, name):
            if (account, name) not in azure.gremlin_databases:
                raise NotFound(f"database '{name}' was not found")
            return Model(
                name=name,
                properties={"resource": {"id": name}, "provisioningState": "Succeeded"},
            )

        def begin_create_update_gremlin_database(self, rg, account, name, parameters):
            azure.gremlin_databases.add((account, name))
            return poller()

        def get_gremlin_graph(self, rg, account, database, name):
            graph = azure.gremlin_graphs.get((account, database, name))
            if graph is None:
                raise NotFound(f"graph '{name}' was not found")
            return Model(
                name=name,
                properties={"resource": graph, "provisioningState": "Succeeded"},
            )

        def begin_create_update_gremlin_graph(self, rg, account, database, name, parameters):
            azure.gremlin_graphs[(account, database, name)] = dict(
                parameters["properties"]["resource"]
            )
            return poller()

    class _Client:
        def __init__(self, credential, subscription_id):
            self.database_accounts = _Accounts()
            self.sql_resources = _Sql()
            self.gremlin_resources = _Gremlin()

    return types.SimpleNamespace(CosmosDBManagementClient=_Client)


# -- azure.mgmt.kusto --------------------------------------------------------


def fake_kusto_mgmt_module(azure: Azure):
    class _Clusters:
        def get(self, rg, name):
            cluster = azure.clusters.get(name)
            if cluster is None:
                raise NotFound(f"cluster '{name}' was not found")
            return Model(**cluster)

        def begin_create_or_update(self, rg, name, parameters):
            azure._maybe_fail("kusto-cluster")
            azure.cluster_creates += 1
            azure.clusters[name] = {
                "name": name,
                "location": parameters.get("location", ""),
                "sku": dict(parameters.get("sku") or {}),
                "tags": dict(parameters.get("tags") or {}),
                "properties": {"provisioningState": "Succeeded", "state": "Running"},
            }
            return poller()

        def begin_delete(self, rg, name):
            azure.clusters.pop(name, None)
            return poller()

        def begin_stop(self, rg, name):
            azure.clusters[name]["properties"]["state"] = "Stopped"
            return poller()

        def begin_start(self, rg, name):
            azure.clusters[name]["properties"]["state"] = "Running"
            return poller()

    class _Databases:
        def get(self, rg, cluster, name):
            if (cluster, name) not in azure.kusto_databases:
                raise NotFound(f"database '{name}' was not found")
            return Model(
                name=name,
                location="eastus",
                kind="ReadWrite",
                properties={"provisioningState": "Succeeded"},
            )

        def begin_create_or_update(self, rg, cluster, name, parameters):
            azure.kusto_databases.add((cluster, name))
            return poller()

        def begin_delete(self, rg, cluster, name):
            azure.kusto_databases.discard((cluster, name))
            return poller()

    class _PrincipalAssignments:
        def begin_create_or_update(self, rg, cluster, database, name, parameters):
            azure._maybe_fail("role-assignments")
            azure.kusto_role_assignments.append(dict(parameters))
            return poller()

    class _Client:
        def __init__(self, credential, subscription_id):
            self.clusters = _Clusters()
            self.databases = _Databases()
            self.database_principal_assignments = _PrincipalAssignments()

    return types.SimpleNamespace(KustoManagementClient=_Client)


# -- azure.kusto.data --------------------------------------------------------


def fake_kusto_data_module(azure: Azure):
    class _Col:
        def __init__(self, name):
            self.column_name = name
            self.column_type = "string"

    class _Primary:
        def __init__(self, rows):
            self.rows = rows
            self.columns = [_Col(name) for name in (rows[0] if rows else {})]

        def __iter__(self):
            return iter(self.rows)

    class _Response:
        def __init__(self, rows):
            self.primary_results = [_Primary(rows)]

    def run(command: str):
        text = command.strip()
        if "| take " in text:
            text = text[: text.rindex("| take ")].strip()
        if text.startswith("print "):
            return [{"probe": 1}]
        if text == ".show tables":
            return [{"TableName": name} for name in azure.tables]
        if text.startswith(".show table ") and text.endswith(" cslschema"):
            name = text.split()[2]
            if name not in azure.tables:
                raise RuntimeError(f"Table '{name}' could not be resolved")
            return [{"TableName": name, "Schema": azure.tables[name]}]
        if text.startswith(".create-merge table "):
            azure._maybe_fail("kusto-table")
            name = text.split()[2]
            body = text[text.index("(") + 1 : text.rindex(")")]
            azure.tables[name] = ",".join(p.strip() for p in body.split(","))
            azure.rows.setdefault(name, 0)
            return []
        if text.startswith(".set-or-append "):
            name = text.split()[1]
            body = text[text.rindex("[") + 1 : text.rindex("]")]
            width = len(azure.tables[name].split(","))
            azure.rows[name] += len([v for v in body.split(",") if v.strip()]) // width
            return []
        if text.endswith("| count"):
            return [{"Count": azure.rows.get(text.split("|")[0].strip(), 0)}]
        raise RuntimeError(f"unexpected command: {command}")

    class _Client:
        def __init__(self, kcsb):
            pass

        def execute(self, database, query):
            return _Response(run(query))

    class _Kcsb:
        @staticmethod
        def with_azure_token_credential(uri, credential):
            return {"uri": uri}

    return types.SimpleNamespace(KustoClient=_Client, KustoConnectionStringBuilder=_Kcsb)


# -- azure.cosmos.aio (the data-plane probe) ---------------------------------


def fake_cosmos_aio_module(azure: Azure):
    class _Database:
        async def read(self):
            return {"id": "azdatalive"}

    class _Client:
        def __init__(self, url=None, credential=None):
            pass

        def get_database_client(self, name):
            return _Database()

        async def close(self):
            return None

    return types.SimpleNamespace(CosmosClient=_Client)


def install(azure: Azure) -> None:
    reset_gates()
    override("azure.mgmt.resource.resources", fake_resource_module(azure))
    override("azure.mgmt.authorization", fake_authorization_module(azure))
    override("azure.mgmt.search", fake_search_mgmt_module(azure))
    override("azure.mgmt.cosmosdb", fake_cosmos_mgmt_module(azure))
    override("azure.mgmt.kusto", fake_kusto_mgmt_module(azure))
    override("azure.kusto.data", fake_kusto_data_module(azure))
    override("azure.cosmos.aio", fake_cosmos_aio_module(azure))
    fake_index_modules(azure)


def environment(azure: Azure, tmp: Path, **kwargs) -> Environment:
    install(azure)
    return Environment(
        credential_provider=lambda: FakeCredential(),
        subscription_id="sub",
        state_path=tmp,
        report=lambda result: None,
        role_budget_secs=1.0,
        role_probe_interval_secs=0.0,
        **kwargs,
    )


def state_file(name: str) -> Path:
    import tempfile

    return Path(tempfile.mkdtemp(prefix="azdata-live-")) / name


# ── Topology ─────────────────────────────────────────────────────────────────


async def test_topology_is_well_formed() -> None:
    section("live: the topology of SPEC 7.1")

    names = [plan.name for plan in TOPOLOGY]
    check("five resources, as specified", len(TOPOLOGY) == 5)
    check("every name is unique", len(set(names)) == 5)
    check("named exactly as the spec names them", set(names) == {
        SEARCH_SERVICE, COSMOS_ACCOUNT, GREMLIN_ACCOUNT, KUSTO_CLUSTER, LOG_WORKSPACE
    })
    by_key = {plan.key: plan for plan in TOPOLOGY}
    check("search is basic, not free", by_key["search"].sku == "basic")
    check("both Cosmos accounts are serverless", by_key["cosmos"].sku == "serverless")
    check("gremlin is a separate account", by_key["gremlin"].name != by_key["cosmos"].name)
    check("kusto is the Dev/No-SLA sku", "Dev(No SLA)" in by_key["kusto"].sku)
    check(
        "every endpoint is derived from the name and carries no secret",
        all("key" not in plan.endpoint("eastus").lower() for plan in TOPOLOGY),
    )

    check("six role assignments, per SPEC 7.4", len(ROLES) == 6)
    check(
        "and the Cosmos data-plane role is separate from Contributor",
        {plan.plane for plan in ROLES} == {"management", "data"},
    )


async def test_account_names_are_validated_before_arm_sees_them() -> None:
    section("live: a globally unique name fails by name, not by stack trace")

    check("the topology's own names are legal", validate_account_name(COSMOS_ACCOUNT))
    for bad in ("Cosmos-Upper", "x", "-leading", "trailing-"):
        try:
            validate_account_name(bad)
            check(f"'{bad}' is refused", False)
        except NameUnavailable as exc:
            check(f"'{bad}' is refused", True)
            check(f"naming the rule for '{bad}'", "lowercase" in str(exc))

    azure = Azure()
    # Somebody else's account of the same name: present globally, absent
    # from this resource group.
    azure.accounts[COSMOS_ACCOUNT] = {}

    class Foreign(Azure):
        pass

    env = environment(azure, state_file("environment.json"))

    class _Accounts:
        def check_name_exists(self, name):
            return True

        def get(self, rg, name):
            raise NotFound(name)

    env._clients["cosmos"] = types.SimpleNamespace(database_accounts=_Accounts())
    try:
        await env._check_account_name(COSMOS_ACCOUNT)
        check("a name taken by another subscription is a named error", False)
    except NameUnavailable as exc:
        check("a name taken by another subscription is a named error", True)
        check("saying what to do about it", "choose a different name" in str(exc))


# ── Seed ─────────────────────────────────────────────────────────────────────


async def test_seed_projections_all_derive_from_one_dataset() -> None:
    section("live: one dataset, four projections, forty keys")

    check("forty assets", len(seed.ASSETS) == 40)
    keys = seed.projection_keys()
    check("four projections", set(keys) == {"search", "cosmos", "gremlin", "kusto"})
    for name, projected in keys.items():
        check(f"{name} carries forty keys", len(projected) == 40)
        check(f"{name} agrees with the dataset", projected == seed.asset_ids())

    check(
        "the search projection carries the vector field",
        all(len(doc["vector"]) == seed.VECTOR_DIMS for doc in seed.search_documents()),
    )
    check(
        "the cosmos projection spreads over four partitions",
        len({item["site"] for item in seed.cosmos_items()}) == 4,
    )

    edges = seed.gremlin_edges()
    check("sixty edges", len(edges) == 60)
    check("over three labels", len({edge["label"] for edge in edges}) == 3)
    check("no edge is a self loop", all(e["from"] != e["to"] for e in edges))
    vertices = {v["id"] for v in seed.gremlin_vertices()}
    check(
        "and every endpoint is a seeded vertex",
        all(e["from"] in vertices and e["to"] in vertices for e in edges),
    )

    rows = seed.kusto_rows()
    check(
        "the kusto projection matches the declared columns",
        set(rows[0]) == set(seed.KUSTO_COLUMNS),
    )
    check(
        "the dataset is deterministic across calls",
        seed.kusto_rows()[7] == rows[7],
    )


# ── down ─────────────────────────────────────────────────────────────────────


async def test_down_refuses_an_untagged_group() -> None:
    section("live: down refuses a resource group it does not own")

    azure = Azure(group_present=True, group_tags={"owner": "somebody-else"})
    env = environment(azure, state_file("environment.json"))
    try:
        await env.down(confirm=True)
        check("an untagged group is refused", False)
    except TeardownRefused as exc:
        check("an untagged group is refused", True)
        check("naming the tag it wanted", OWNER_TAG_KEY in str(exc))
    # The check that makes the refusal worth anything.
    check("and nothing was deleted", azure.deleted_groups == [])
    check("the group is still there", RESOURCE_GROUP in azure.groups)


async def test_down_refuses_without_an_explicit_yes() -> None:
    section("live: down refuses without --yes, even on its own group")

    azure = Azure(group_present=True)
    env = environment(azure, state_file("environment.json"))
    try:
        await env.down()
        check("an unconfirmed teardown is refused", False)
    except TeardownRefused as exc:
        check("an unconfirmed teardown is refused", True)
        check("naming the flag", "--yes" in str(exc))
    check("and nothing was deleted", azure.deleted_groups == [])


async def test_down_deletes_a_tagged_group_and_proves_absence() -> None:
    section("live: down deletes its own group and re-reads to prove it")

    azure = Azure(group_present=True)
    path = state_file("environment.json")
    env = environment(azure, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    answer = await env.down(confirm=True)
    check("the tagged group is deleted", answer["deleted"] is True)
    check("absence is proved by re-reading", answer["present"] is False)
    check("and it reached the SDK", azure.deleted_groups == [RESOURCE_GROUP])
    check("the state file is cleared with it", not path.exists())


# ── up ───────────────────────────────────────────────────────────────────────


async def test_up_creates_everything_and_records_it() -> None:
    section("live: up creates the topology, reads it back, and records it")

    azure = Azure()
    path = state_file("environment.json")
    env = environment(azure, path)
    record = await env.up(seed=False)

    check("the resource group is tagged at creation", azure.groups[RESOURCE_GROUP]["tags"][OWNER_TAG_KEY] == OWNER_TAG_VALUE)
    check("the search service exists", SEARCH_SERVICE in azure.search)
    check("at the basic sku", azure.search[SEARCH_SERVICE]["sku"]["name"] == "basic")
    check("both Cosmos accounts exist", {COSMOS_ACCOUNT, GREMLIN_ACCOUNT} <= set(azure.accounts))
    check(
        "and only the gremlin one carries EnableGremlin",
        any(
            c["name"] == "EnableGremlin"
            for c in azure.accounts[GREMLIN_ACCOUNT]["properties"]["capabilities"]
        )
        and not any(
            c["name"] == "EnableGremlin"
            for c in azure.accounts[COSMOS_ACCOUNT]["properties"]["capabilities"]
        ),
    )
    check("the ADX cluster exists", KUSTO_CLUSTER in azure.clusters)
    check("the log analytics workspace exists", any(LOG_WORKSPACE in k for k in azure.generic))
    check("the search index was created on the data plane", "azdata-assets" in azure.indexes)
    check("the kusto table was created by control command", "Assets" in azure.tables)
    check("the cosmos container carries the /site partition key", azure.sql_containers[(COSMOS_ACCOUNT, "azdatalive", "assets")]["partitionKey"]["paths"] == ["/site"])

    check("six role assignments were made", len(azure.role_assignments) + len(azure.cosmos_role_assignments) + len(azure.kusto_role_assignments) == 6)
    check("including the separate Cosmos data-plane role", len(azure.cosmos_role_assignments) == 2)
    check("and the ADX database admin", len(azure.kusto_role_assignments) == 1)
    check(
        "every assignment reports the propagation wait actually observed",
        all("propagation_secs" in entry for entry in record["roles"]),
    )

    on_disk = json.loads(path.read_text(encoding="utf-8"))
    check("the state file records every resource", {"search", "cosmos", "gremlin", "kusto", "logs"} <= set(on_disk["resources"]))
    check("with ids", on_disk["resources"]["kusto"]["id"].endswith(KUSTO_CLUSTER))
    check("endpoints", on_disk["resources"]["search"]["endpoint"].startswith("https://"))
    check("and creation timestamps", "created_utc" in on_disk["resources"]["search"])
    blob = json.dumps(on_disk).lower()
    check("and no key, secret or connection string", not any(
        marker in blob for marker in ("accountkey", "sharedaccesssignature", "password", "connectionstring")
    ))


async def test_up_is_idempotent_when_everything_exists() -> None:
    section("live: a second up changes nothing")

    azure = Azure()
    path = state_file("environment.json")
    env = environment(azure, path)
    await env.up(seed=False)
    creates_after_first = (azure.search_creates, azure.cluster_creates)

    second = await env.up(seed=False)
    check("the second up succeeds", "resources" in second)
    check(
        "and reports nothing as newly created",
        second["steps"]["search-service"]["created"] is False
        and second["steps"]["kusto-cluster"]["created"] is False,
    )
    check(
        "the ARM writes are idempotent, not skipped-and-lying",
        (azure.search_creates, azure.cluster_creates) > creates_after_first,
    )
    check("no resource was duplicated", len(azure.accounts) == 2 and len(azure.clusters) == 1)


async def test_up_resumes_after_a_partial_failure() -> None:
    section("live: a partial failure resumes rather than restarting")

    azure = Azure(fail="kusto-cluster")
    path = state_file("environment.json")
    env = environment(azure, path)
    try:
        await env.up(seed=False)
        check("the failing step fails the run", False)
    except LiveEnvironmentError as exc:
        check("the failing step fails the run", True)
        check("naming the step", "kusto-cluster" in str(exc))

    partial = json.loads(path.read_text(encoding="utf-8"))
    check("the state file records what did get created", "search" in partial["resources"])
    check("and not what did not", "kusto" not in partial["resources"])
    check("the ADX cluster really is absent", KUSTO_CLUSTER not in azure.clusters)

    # The resume. Nothing before the failure is created a second time from
    # scratch, and the run reaches the end.
    resumed = await environment(azure, path).up(seed=False)
    check("the resumed run completes", "roles" in resumed)
    check("the cluster now exists", KUSTO_CLUSTER in azure.clusters)
    check(
        "and the search service was not reported as newly created",
        resumed["steps"]["search-service"]["created"] is False,
    )
    check(
        "the original creation timestamp survived the resume",
        json.loads(path.read_text(encoding="utf-8"))["created_utc"] == partial["created_utc"],
    )


async def test_up_seeds_all_four_services() -> None:
    section("live: the seed reaches every service through the write planes")

    azure = Azure()
    env = environment(azure, state_file("environment.json"))
    await env.up(seed=False)
    # Only the Kusto half is exercised end to end here: the Search, Cosmos
    # and Gremlin write planes have their own suites, and re-faking three
    # more data-plane SDKs would test the fakes, not this module.
    counts = await env._seed_kusto()
    check("forty rows reached the table", counts == 40)
    check("and the table really holds them", azure.rows["Assets"] == 40)


# ── pause / resume, status, and the state file ───────────────────────────────


async def test_pause_and_resume_move_the_cluster() -> None:
    section("live: pause and resume are the cost lever")

    azure = Azure()
    env = environment(azure, state_file("environment.json"))
    await env.up(seed=False)
    await env.pause()
    check("pause stops the cluster", azure.clusters[KUSTO_CLUSTER]["properties"]["state"] == "Stopped")
    await env.resume()
    check("resume starts it again", azure.clusters[KUSTO_CLUSTER]["properties"]["state"] == "Running")


async def test_status_answers_for_everything_at_once() -> None:
    section("live: status is one document, and one unreadable resource is not fatal")

    azure = Azure()
    env = environment(azure, state_file("environment.json"))
    await env.up(seed=False)
    document = await env.status()
    check("the group is reported present", document["resource_group_present"] is True)
    check("with its ownership tag", document["resource_group_tags"][OWNER_TAG_KEY] == OWNER_TAG_VALUE)
    check("every topology entry is described", len(document["topology"]) == 5)
    check("the cluster describes as present", document["resources"]["kusto"]["present"] is True)
    check("stats are collected too", "kusto" in document["stats"])
    check("and the standing cost is stated", "74" in document["standing_cost_note"])
    check("the document is JSON-serialisable as a whole", isinstance(json.dumps(document), str))


async def test_state_file_refuses_a_credential() -> None:
    section("live: the state file will not carry a secret")

    try:
        assert_no_secrets({"resources": {"cosmos": {"connection": "AccountKey=abc123"}}})
        check("a key-shaped value is refused", False)
    except LiveEnvironmentError as exc:
        check("a key-shaped value is refused", True)
        check("naming what it saw", "accountkey" in str(exc))

    assert_no_secrets({"resources": {"cosmos": {"endpoint": "https://x.documents.azure.com"}}})
    check("an endpoint is not a secret", True)


async def test_the_subscription_is_never_defaulted() -> None:
    section("live: the billing target is named by the caller or not at all")

    check(
        "the module publishes no subscription of its own",
        not hasattr(environment_module, "SUBSCRIPTION_ID")
        and not hasattr(live_package, "SUBSCRIPTION_ID"),
    )

    for missing in (None, "", "   "):
        calls: list[int] = []
        try:
            Environment(
                credential_provider=lambda: calls.append(1),
                subscription_id=missing,  # type: ignore[arg-type]
            )
            check(f"{missing!r} is refused", False)
        except ValueError as exc:
            check(f"{missing!r} is refused", True)
            check(f"naming the argument for {missing!r}", "subscription_id" in str(exc))
        # The check that makes the refusal worth anything: an unusable target
        # must not cost a sign-in to discover.
        check(f"and no credential was requested for {missing!r}", calls == [])

    azure = Azure()
    path = state_file("environment.json")
    env = environment(azure, path)
    record = await env.up(seed=False)
    check("an explicit subscription is accepted", record["subscription_id"] == "sub")
    check(
        "and it is the one the state file records",
        json.loads(path.read_text(encoding="utf-8"))["subscription_id"] == "sub",
    )

    parser = build_parser()
    for argv in (["up"], ["up", "--subscription", ""], ["up", "--subscription", "  "]):
        try:
            parser.parse_args(argv)
            check(f"the CLI refuses {argv}", False)
        except SystemExit as exc:
            check(f"the CLI refuses {argv}", exc.code == 2)
    check(
        "and accepts an explicit one",
        parser.parse_args(["down", "--subscription", "sub", "--yes"]).subscription == "sub",
    )


async def test_identity_comes_from_the_token_not_from_the_cli() -> None:
    section("live: the running identity is read out of its own token")

    token = FakeCredential().get_token("scope").token
    identity = principal_from_token(token)
    check("the object id is read from the claims", identity["principal_id"] == "principal-1")
    check("a user is not mistaken for a service principal", identity["principal_type"] == "User")
    check("and the tenant comes along", identity["tenant_id"] == "tenant-1")

    try:
        principal_from_token("not-a-jwt")
        check("a non-JWT is a named error", False)
    except LiveEnvironmentError as exc:
        check("a non-JWT is a named error", True)
        check("saying what it needed", "object id" in str(exc))


# ── Runner ───────────────────────────────────────────────────────────────────


async def main() -> int:
    tests = [
        test_topology_is_well_formed,
        test_account_names_are_validated_before_arm_sees_them,
        test_seed_projections_all_derive_from_one_dataset,
        test_down_refuses_an_untagged_group,
        test_down_refuses_without_an_explicit_yes,
        test_down_deletes_a_tagged_group_and_proves_absence,
        test_up_creates_everything_and_records_it,
        test_up_is_idempotent_when_everything_exists,
        test_up_resumes_after_a_partial_failure,
        test_up_seeds_all_four_services,
        test_pause_and_resume_move_the_cluster,
        test_status_answers_for_everything_at_once,
        test_state_file_refuses_a_credential,
        test_the_subscription_is_never_defaulted,
        test_identity_comes_from_the_token_not_from_the_cli,
    ]
    try:
        for test in tests:
            try:
                await test()
            except AssertionError:
                pass
    finally:
        clear_overrides()

    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} check(s)")
        for failure in _FAILURES:
            print(f"  - {failure}")
        return 1
    print("live environment tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
