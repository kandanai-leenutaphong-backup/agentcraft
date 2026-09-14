"""test_kusto_planes — the Kusto deploy plane and ingest plane, with no SDKs.

Run: ``.venv/bin/python -m pytest tests/unit/test_kusto_planes.py -q``, or
``python3 tests/unit/test_kusto_planes.py`` for the same checks as a script.

Every Azure SDK is substituted through ``azdata.core.optional.override``,
so this exercises the resumable cluster poll, drift detection across the
third management SDK's model shape, the data-plane table split and
row-count-delta ingest verification with no cloud account, no network and
nothing installed. ``check`` asserts as well as printing: a suite that
prints FAIL and exits zero is not a suite.
"""

from __future__ import annotations

import asyncio
import collections.abc
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.core.config import AzureDataConfig  # noqa: E402
from azdata.core.breaker import reset_gates  # noqa: E402
from azdata.core.crud import WritePolicy  # noqa: E402
from azdata.core.optional import (  # noqa: E402
    MissingDependency,
    clear_overrides,
    override,
)
from azdata.core.provision import ProvisionPolicy  # noqa: E402
from azdata.kusto.deploy import (  # noqa: E402
    DEV_SKU,
    KustoClusterProvisioner,
    KustoDatabaseProvisioner,
    KustoTableProvisioner,
    lift_kusto_model,
)
from azdata.kusto.read import KqlConnector  # noqa: E402
from azdata.kusto.write import KustoIngest, KustoIngestError  # noqa: E402

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


def parse(payload: str) -> dict:
    return json.loads(payload)


class FakeCredential:
    def get_token(self, scope: str):  # noqa: D102 - never reached by these paths
        return types.SimpleNamespace(token="tok", expires_on=0)


class NotFound(Exception):
    """Named exactly as the SDK's, because that is what the code detects."""

    status_code = 404


# ── The model shape pin ──────────────────────────────────────────────────────


class JsonBackedModel(collections.abc.Mapping):
    """azure-mgmt-kusto 4.x: a Mapping over the raw camelCase REST payload.

    Introspected on 4.0.0. ``isinstance(Cluster(...), Mapping)`` is True,
    the MRO runs through ``_MyMutableMapping``, and
    ``Cluster(location="eastus", enable_streaming_ingest=True).as_dict()``
    is ``{'location': 'eastus', 'properties': {'enableStreamingIngest':
    True}}``. Same family as azure-mgmt-cosmosdb 10, the exact opposite of
    azure-mgmt-search 9 (GOTCHAS G18).
    """

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


class MsrestModel:
    """azure-mgmt-search 9.x style: not a Mapping, flattened snake_case."""

    def __init__(self, **fields):
        self._fields = dict(fields)

    def as_dict(self):
        return dict(self._fields)


async def test_model_shape_is_the_json_backed_camelcase_style() -> None:
    section("kusto deploy plane: the SDK model shape this normalisation assumes")

    live = JsonBackedModel(
        id="/subscriptions/s/resourceGroups/rg/providers/Microsoft.Kusto/clusters/adx",
        name="adx",
        location="eastus",
        sku={"name": DEV_SKU["name"], "tier": "Basic", "capacity": 1},
        properties={
            "provisioningState": "Succeeded",
            "state": "Running",
            "enableStreamingIngest": True,
        },
    )
    check(
        "azure-mgmt-kusto models are Mappings, like cosmosdb and unlike search",
        isinstance(live, collections.abc.Mapping),
    )
    lifted = lift_kusto_model(live)
    check("the lift flattens properties one level", "provisioning_state" in lifted)
    check("snake-casing the camelCase wire keys", lifted["enable_streaming_ingest"] is True)
    check("and keeps the top-level keys", lifted["name"] == "adx")
    check("with nested models as plain data", lifted["sku"]["capacity"] == 1)
    check(
        "there is no surviving 'properties' block to hide a value in",
        "properties" not in lifted,
    )

    # A 3.x msrest pin hands over the other shape. The lift must pass it
    # through unchanged rather than looking for a properties block that is
    # not there, or a downgrade silently reports drift on everything.
    flat = lift_kusto_model(
        MsrestModel(location="eastus", provisioning_state="Succeeded", state="Running")
    )
    check("an already-flat snake_case payload survives the lift", flat["state"] == "Running")


# ── ARM fakes ────────────────────────────────────────────────────────────────


class FakeClusters:
    """One cluster's ARM lifecycle, with a scripted provisioning state."""

    def __init__(self, *, present=False, states=None, drift=None):
        self.present = present
        # Successive provisioningState values returned by get(). The last
        # one repeats, so a poll that never finishes is expressible.
        self.states = list(states or ["Succeeded"])
        self.drift = drift or {}
        self.creates: list[dict] = []
        self.deletes: list[str] = []
        self.gets = 0
        self.stopped = 0
        self.started = 0
        self.spec: dict = {}

    def _state(self) -> str:
        index = min(self.gets, len(self.states)) - 1
        return self.states[max(index, 0)]

    def get(self, resource_group, name):
        self.gets += 1
        if not self.present:
            raise NotFound(f"cluster '{name}' was not found")
        payload = dict(self.spec)
        sku = dict(payload.get("sku") or {})
        sku.update(self.drift.get("sku", {}))
        return JsonBackedModel(
            name=name,
            location="eastus",
            sku=sku,
            tags=self.drift.get("tags", payload.get("tags", {})),
            properties={
                "provisioningState": self._state(),
                "state": "Running" if self._state() == "Succeeded" else "Creating",
            },
        )

    def begin_create_or_update(self, resource_group, name, parameters):
        self.creates.append(dict(parameters))
        self.present = True
        self.spec = dict(parameters)
        return types.SimpleNamespace(result=lambda: None)

    def begin_delete(self, resource_group, name):
        self.deletes.append(name)
        self.present = False
        return types.SimpleNamespace(result=lambda: None)

    def begin_stop(self, resource_group, name):
        self.stopped += 1
        return types.SimpleNamespace(result=lambda: None)

    def begin_start(self, resource_group, name):
        self.started += 1
        return types.SimpleNamespace(result=lambda: None)


class FakeDatabases:
    def __init__(self, *, present=False):
        self.present = present
        self.creates: list[dict] = []
        self.deletes: list[str] = []

    def get(self, resource_group, cluster, name):
        if not self.present:
            raise NotFound(f"database '{name}' was not found")
        return JsonBackedModel(
            name=name,
            location="eastus",
            kind="ReadWrite",
            properties={"provisioningState": "Succeeded", "softDeletePeriod": "P30D"},
        )

    def begin_create_or_update(self, resource_group, cluster, name, parameters):
        self.creates.append(dict(parameters))
        self.present = True
        return types.SimpleNamespace(result=lambda: None)

    def begin_delete(self, resource_group, cluster, name):
        self.deletes.append(name)
        self.present = False
        return types.SimpleNamespace(result=lambda: None)


def cluster_provisioner(clusters, policy=None, **kwargs):
    return KustoClusterProvisioner(
        client=types.SimpleNamespace(clusters=clusters),
        resource_group="rg",
        name="adx-azdatalive",
        location="eastus",
        policy=policy or ProvisionPolicy.deployable(poll_timeout_secs=5.0),
        **kwargs,
    )


# ── Deploy plane: the cluster ────────────────────────────────────────────────


async def test_cluster_ensure_and_teardown() -> None:
    section("kusto deploy plane: cluster")

    clusters = FakeClusters()
    prov = cluster_provisioner(clusters)
    spec = prov.default_spec(tags={"azdatalive-owned": "true"})
    first = parse(await prov.ensure(spec))
    check("ensure creates a missing cluster", first["ok"] is True)
    check("reporting it created", first["created"] is True)
    check("with no drift", first["drift"] == {})
    check("at the Dev/No-SLA sku", clusters.creates[0]["sku"]["name"] == DEV_SKU["name"])
    check("with capacity 1", clusters.creates[0]["sku"]["capacity"] == 1)
    check("read back after the write, not trusted from it", clusters.gets >= 2)

    second = parse(await prov.ensure(spec))
    check("a second ensure is idempotent", second["ok"] is True)
    check("and reports it was already there", second["created"] is False)

    refused = parse(await prov.teardown())
    check("teardown without a delete grant is refused", refused["error"] is True)
    check("naming the grant", "allow_delete=True" in refused["detail"])
    check("and nothing was deleted", clusters.deletes == [])

    deletable = cluster_provisioner(
        clusters,
        policy=ProvisionPolicy.deployable(allow_delete=True, poll_timeout_secs=5.0),
    )
    gone = parse(await deletable.teardown())
    check("with the grant, teardown deletes", gone["ok"] is True)
    check("and proves absence by re-reading", gone["verified"] is True)


async def test_cluster_policy_denies_by_default() -> None:
    section("kusto deploy plane: cluster policy denies by default")

    clusters = FakeClusters()
    prov = cluster_provisioner(clusters, policy=ProvisionPolicy.read_only())
    refused = parse(await prov.ensure(prov.default_spec()))
    check("a read-only provisioner refuses ensure", refused["error"] is True)
    check("saying how to grant it", "ProvisionPolicy.deployable" in refused["detail"])
    check("and nothing reached ARM", clusters.creates == [])

    powerless = parse(await prov.stop())
    check("a read-only provisioner refuses to stop the cluster", powerless["error"] is True)
    check("and never called begin_stop", clusters.stopped == 0)


async def test_cluster_drift_is_an_error_not_an_ok() -> None:
    section("kusto deploy plane: drift is an error")

    clusters = FakeClusters(drift={"sku": {"capacity": 2}})
    prov = cluster_provisioner(clusters)
    drifted = parse(await prov.ensure(prov.default_spec()))
    check("a sku that did not survive the write is an error", drifted.get("error") is True)
    check("never an ok envelope with a drift map", "ok" not in drifted)
    check("naming the field", "sku" in drifted["detail"])
    check("blaming the right cause", "Policy" in drifted["detail"])

    # location is normalised by ARM and must never be reported: a
    # provisioner that cries wolf on every deployment is switched off.
    normalising = FakeClusters()
    quiet = cluster_provisioner(normalising)
    clean = parse(await quiet.ensure(quiet.default_spec(location="East US")))
    check("the normalised location is not reported as drift", clean["ok"] is True)


async def test_cluster_ensure_resumes_an_in_flight_create() -> None:
    section("kusto deploy plane: a 10-15 minute create resumes, it does not restart")

    # The cluster exists and is still Creating: exactly the state a re-run
    # after a timeout finds.
    clusters = FakeClusters(
        present=True, states=["Creating", "Creating", "Succeeded", "Succeeded"]
    )
    clusters.spec = {"location": "eastus", "sku": dict(DEV_SKU)}
    prov = cluster_provisioner(clusters, poll_interval_secs=0.0)
    resumed = parse(await prov.ensure(prov.default_spec()))
    check("the resumed ensure succeeds", resumed["ok"] is True)
    check(
        "without submitting a second create for the same cluster",
        clusters.creates == [],
    )
    check("reporting it was already there", resumed["created"] is False)
    check("after polling until the state went terminal", clusters.gets >= 3)

    stuck = FakeClusters(present=True, states=["Creating"])
    stuck.spec = {"location": "eastus", "sku": dict(DEV_SKU)}
    impatient = cluster_provisioner(
        stuck,
        policy=ProvisionPolicy.deployable(poll_timeout_secs=0.05),
        poll_interval_secs=0.01,
    )
    timed_out = parse(await impatient.ensure(impatient.default_spec()))
    check("a create that never finishes fails instead of hanging", timed_out["error"] is True)
    check("naming the deadline", "terminal state" in timed_out["detail"])


async def test_cluster_power_state() -> None:
    section("kusto deploy plane: pause and resume are the cost lever")

    clusters = FakeClusters(present=True)
    clusters.spec = {"location": "eastus", "sku": dict(DEV_SKU)}
    prov = cluster_provisioner(clusters)
    stopped = parse(await prov.stop())
    check("stop is an ok envelope", stopped["ok"] is True)
    check("and it reached the SDK", clusters.stopped == 1)
    started = parse(await prov.start())
    check("start is an ok envelope", started["ok"] is True)
    check("and it reached the SDK", clusters.started == 1)


# ── Deploy plane: the database ───────────────────────────────────────────────


async def test_database_provisioner() -> None:
    section("kusto deploy plane: database")

    databases = FakeDatabases()
    prov = KustoDatabaseProvisioner(
        client=types.SimpleNamespace(databases=databases),
        resource_group="rg",
        cluster_name="adx-azdatalive",
        name="azdatalive",
        location="eastus",
        policy=ProvisionPolicy.deployable(allow_delete=True, poll_timeout_secs=5.0),
    )
    created = parse(await prov.ensure(prov.default_spec()))
    check("ensure creates a missing database", created["ok"] is True)
    check("as a ReadWrite database", databases.creates[0]["kind"] == "ReadWrite")
    check("with no drift", created["drift"] == {})

    again = parse(await prov.ensure(prov.default_spec()))
    check("a second ensure is idempotent", again["ok"] is True)
    check("reporting it was already there", again["created"] is False)

    gone = parse(await prov.teardown())
    check("teardown deletes and proves absence", gone["ok"] is True)
    check("and it reached the SDK", databases.deletes == ["azdatalive"])


# ── The data plane: tables, and ingest ───────────────────────────────────────


class FakeKustoDataPlane:
    """A cluster's data plane: tables, rows, and the control commands.

    Stateful on purpose. A stub that echoed canned rows could not tell the
    difference between an ingest that landed and one that was refused,
    which is the whole point of the row-count-delta test below.
    """

    def __init__(self, *, tables=None, drop_column=""):
        self.tables = dict(tables or {})
        self.rows: dict[str, int] = {name: 0 for name in self.tables}
        # Models a table whose live schema is missing a declared column.
        self.drop_column = drop_column
        self.commands: list[str] = []

    def execute(self, database, command):
        self.commands.append(command)
        text = command.strip()
        # The read plane injects a row cap into a tabular query, so the
        # count arrives as "Assets | count | take 500". Stripping it here
        # keeps the guardrail exercised rather than switched off.
        if "| take " in text:
            text = text[: text.rindex("| take ")].strip()
        if text == ".show tables":
            return [{"TableName": name} for name in self.tables]
        if text.startswith(".show table ") and text.endswith(" cslschema"):
            name = text.split()[2]
            schema = self.tables.get(name)
            if schema is None:
                raise RuntimeError(f"Table '{name}' could not be resolved")
            return [{"TableName": name, "Schema": schema}]
        if text.startswith(".create-merge table "):
            name = text.split()[2]
            body = text[text.index("(") + 1 : text.rindex(")")]
            columns = [part.strip() for part in body.split(",")]
            if self.drop_column:
                columns = [
                    c for c in columns if not c.startswith(f"{self.drop_column}:")
                ]
            self.tables[name] = ",".join(columns)
            self.rows.setdefault(name, 0)
            return []
        if text.startswith(".drop table "):
            name = text.split()[2]
            self.tables.pop(name, None)
            self.rows.pop(name, None)
            return []
        if text.startswith(".set-or-append "):
            name = text.split()[1]
            if name not in self.tables:
                raise RuntimeError(f"Table '{name}' could not be resolved")
            body = text[text.rindex("[") + 1 : text.rindex("]")]
            values = [v for v in body.split(",") if v.strip()]
            width = len(self.tables[name].split(","))
            self.rows[name] += len(values) // width
            return []
        if text.endswith("| count"):
            name = text.split("|")[0].strip()
            return [{"Count": self.rows.get(name, 0)}]
        raise RuntimeError(f"unexpected command: {command}")


def install_data_plane(plane: FakeKustoDataPlane):
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

    class _Client:
        def __init__(self, kcsb):
            pass

        def execute(self, database, query):
            return _Response(plane.execute(database, query))

    class _Kcsb:
        @staticmethod
        def with_azure_token_credential(uri, credential):
            return {"uri": uri}

    override(
        "azure.kusto.data",
        types.SimpleNamespace(KustoClient=_Client, KustoConnectionStringBuilder=_Kcsb),
    )


def data_connector() -> KqlConnector:
    config = AzureDataConfig(
        kql_query_uri="https://adx.eastus.kusto.windows.net",
        kql_database="azdatalive",
    )
    # The gate and its breaker are process-wide by name; a test that
    # tripped one would otherwise fail the next test for the wrong reason.
    reset_gates()
    return KqlConnector.from_config(
        config, lambda: FakeCredential(), gate_name="kusto-planes-test"
    )


ASSET_COLUMNS = {
    "AssetId": "string",
    "Site": "string",
    "Reading": "real",
}


async def test_table_provisioner_is_a_data_plane_operation() -> None:
    section("kusto deploy plane: the table is a control command, not ARM")

    plane = FakeKustoDataPlane()
    install_data_plane(plane)
    prov = KustoTableProvisioner(
        connector=data_connector(),
        name="Assets",
        policy=ProvisionPolicy.deployable(allow_delete=True, poll_timeout_secs=5.0),
    )
    created = parse(await prov.ensure({"columns": ASSET_COLUMNS}))
    check("ensure creates a missing table", created["ok"] is True)
    check("reporting it created", created["created"] is True)
    check("with no drift", created["drift"] == {})
    check(
        "through .create-merge, the idempotent form",
        any(c.startswith(".create-merge table Assets (") for c in plane.commands),
    )
    check("and no ARM call was made at all", "azure.mgmt.kusto" not in sys.modules)

    again = parse(await prov.ensure({"columns": ASSET_COLUMNS}))
    check("a second ensure is idempotent", again["ok"] is True)
    check("reporting it was already there", again["created"] is False)

    gone = parse(await prov.teardown())
    check("teardown drops the table", gone["ok"] is True)
    check("and proves absence by re-reading", "Assets" not in plane.tables)


async def test_table_drift_is_an_error() -> None:
    section("kusto deploy plane: a column that did not survive is drift")

    # The service accepted the create and kept a schema without 'Reading'.
    # Every value written to that column would be dropped silently.
    plane = FakeKustoDataPlane(drop_column="Reading")
    install_data_plane(plane)
    prov = KustoTableProvisioner(
        connector=data_connector(),
        name="Assets",
        policy=ProvisionPolicy.deployable(poll_timeout_secs=5.0),
    )
    drifted = parse(await prov.ensure({"columns": ASSET_COLUMNS}))
    check("a missing declared column is an error", drifted.get("error") is True)
    check("never an ok envelope", "ok" not in drifted)
    check("naming the column set", "columns" in drifted["detail"])


async def test_table_refuses_to_interpolate_a_non_identifier() -> None:
    section("kusto deploy plane: a table name is validated, never escaped")

    plane = FakeKustoDataPlane()
    install_data_plane(plane)
    prov = KustoTableProvisioner(
        connector=data_connector(),
        name="Assets; .drop table Assets",
        policy=ProvisionPolicy.deployable(poll_timeout_secs=5.0),
    )
    refused = parse(await prov.ensure({"columns": ASSET_COLUMNS}))
    check("a non-identifier table name is refused", refused["error"] is True)
    check("naming the rule", "not a plain Kusto identifier" in refused["detail"])
    check("and no command reached the service", not any("drop" in c for c in plane.commands))


# ── The ingest plane ─────────────────────────────────────────────────────────


def ingest_connector(plane, policy) -> KustoIngest:
    install_data_plane(plane)
    return KustoIngest(
        connector=data_connector(),
        table="Assets",
        columns=ASSET_COLUMNS,
        policy=policy,
    )


def seeded_plane() -> FakeKustoDataPlane:
    return FakeKustoDataPlane(tables={"Assets": "AssetId:string,Site:string,Reading:real"})


ROWS = [
    {"AssetId": "asset-000", "Site": "north", "Reading": 1.5},
    {"AssetId": "asset-001", "Site": "south", "Reading": 2.5},
]


async def test_ingest_is_denied_by_default() -> None:
    section("kusto ingest plane: denied by default, and the count proves it")

    plane = seeded_plane()
    connector = ingest_connector(plane, WritePolicy.read_only())
    before = await connector.count()
    refused = parse(await connector.ingest(ROWS))
    after = await connector.count()
    check("a default-policy connector refuses ingest", refused["error"] is True)
    check("saying how to grant it", "WritePolicy.writable" in refused["detail"])
    # The negative that matters: a refusal that still wrote would pass a
    # test that only asserted on the envelope.
    check("the refused ingest left the row count unchanged", before == after == 0)
    check("and no ingest command was sent", not any(".set-or-append" in c for c in plane.commands))


async def test_ingest_verifies_by_row_count_delta() -> None:
    section("kusto ingest plane: verification is a row-count delta, not a digest")

    plane = seeded_plane()
    connector = ingest_connector(
        plane, WritePolicy.writable(verify_writes=True).with_overrides(verify_delay_secs=0.01)
    )
    landed = parse(await connector.ingest(ROWS))
    check("the ingest is ok", landed["ok"] is True)
    check("and reports itself verified", landed["verified"] is True)
    check("by the count before", landed["rows_before"] == 0)
    check("and the count after", landed["rows_after"] == 2)
    check("stating the delta rather than implying it", landed["delta"] == 2)
    check("the table really holds the rows", plane.rows["Assets"] == 2)


async def test_ingest_that_lands_nothing_fails_verification() -> None:
    section("kusto ingest plane: an accepted command that changed nothing fails")

    class Swallowing(FakeKustoDataPlane):
        def execute(self, database, command):
            if command.strip().startswith(".set-or-append"):
                self.commands.append(command)
                return []  # accepted, and silently ingested nothing
            return super().execute(database, command)

    plane = Swallowing(tables={"Assets": "AssetId:string,Site:string,Reading:real"})
    connector = ingest_connector(
        plane,
        WritePolicy.writable(verify_writes=True).with_overrides(
            verify_attempts=2, verify_delay_secs=0.01
        ),
    )
    lost = parse(await connector.ingest(ROWS))
    check("an ingest that moved no rows is an error", lost["error"] is True)
    check("naming verification", "VerificationFailed" in lost["detail"])
    check("and reporting the counts it actually saw", "0 to 0" in lost["detail"])


async def test_ingest_encodes_values_as_typed_literals() -> None:
    section("kusto ingest plane: a row value cannot become command syntax")

    plane = seeded_plane()
    connector = ingest_connector(plane, WritePolicy.writable(verify_writes=False))
    command = connector.build_command(
        [{"AssetId": 'a"; .drop table Assets //', "Site": None, "Reading": 3.0}]
    )
    check("the command is a set-or-append", command.startswith(".set-or-append Assets <|"))
    check("carrying a datatable schema", "datatable(AssetId:string, Site:string, Reading:real)" in command)
    check("with the quote escaped, not interpolated", '\\"' in command)
    check("a missing value is a typed null", "string(null)" in command)

    oversized = [{"AssetId": f"a{i}"} for i in range(1001)]
    try:
        connector.build_command(oversized)
        check("an oversized inline batch is refused", False)
    except KustoIngestError as exc:
        check("an oversized inline batch is refused", True)
        check("pointing at queued ingestion", "azure-kusto-ingest" in str(exc))


async def test_ingest_has_no_update_and_no_delete() -> None:
    section("kusto ingest plane: the two verbs Kusto does not have are absent")

    plane = seeded_plane()
    connector = ingest_connector(plane, WritePolicy.writable(allow_delete=True))
    check("there is no delete to call", not hasattr(connector, "delete"))
    check("and no update either", not hasattr(connector, "update"))
    check("it is not a CrudConnector", not hasattr(connector, "_do_delete"))


# ── Dependencies ─────────────────────────────────────────────────────────────


async def test_missing_management_sdk() -> None:
    section("kusto deploy plane: missing SDK")
    clear_overrides()

    # None in sys.modules makes import_module raise ImportError, which is
    # absence as the loader sees it. Asserting on the SDK genuinely not
    # being installed would make this pass or fail by accident.
    blocked = "azure.mgmt.kusto"
    previous = sys.modules.get(blocked, "<unset>")
    sys.modules[blocked] = None  # type: ignore[assignment]
    try:
        result = KustoClusterProvisioner.from_config(
            AzureDataConfig(
                subscription_id="sub", resource_group="rg", location="eastus"
            ),
            lambda: FakeCredential(),
            name="adx-azdatalive",
        )
        check("raises MissingDependency", False)
    except MissingDependency as exc:
        check("raises MissingDependency", True)
        check("naming the distribution", "azure-mgmt-kusto" in str(exc))
        check("with the pin the deploy plane was written against", ">=3.3" in str(exc))
    finally:
        if previous == "<unset>":
            sys.modules.pop(blocked, None)
        else:
            sys.modules[blocked] = previous


async def test_unconfigured_coordinates_are_an_envelope() -> None:
    section("kusto deploy plane: missing coordinates name themselves")

    unconfigured = KustoClusterProvisioner.from_config(
        AzureDataConfig(), lambda: FakeCredential(), name="adx-azdatalive"
    )
    check("an unconfigured deploy plane answers with an envelope", isinstance(unconfigured, str))
    parsed = parse(unconfigured)
    check("which is an error", parsed["error"] is True)
    check("naming the config field", "subscription_id" in parsed["detail"])


# ── Runner ───────────────────────────────────────────────────────────────────


async def main() -> int:
    tests = [
        test_model_shape_is_the_json_backed_camelcase_style,
        test_cluster_ensure_and_teardown,
        test_cluster_policy_denies_by_default,
        test_cluster_drift_is_an_error_not_an_ok,
        test_cluster_ensure_resumes_an_in_flight_create,
        test_cluster_power_state,
        test_database_provisioner,
        test_table_provisioner_is_a_data_plane_operation,
        test_table_drift_is_an_error,
        test_table_refuses_to_interpolate_a_non_identifier,
        test_ingest_is_denied_by_default,
        test_ingest_verifies_by_row_count_delta,
        test_ingest_that_lands_nothing_fails_verification,
        test_ingest_encodes_values_as_typed_literals,
        test_ingest_has_no_update_and_no_delete,
        test_missing_management_sdk,
        test_unconfigured_coordinates_are_an_envelope,
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
    print("kusto plane tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
