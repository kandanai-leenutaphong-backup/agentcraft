"""The deployment's data inventory: manifest, probes, and the HTTP surface.

Three things these tests hold that nothing else can:

* the shipped `control/data_inventory.yaml` really declares the two use cases
  the analyst is promised, with their real coordinates and no invented ones;
* a request is refused before an SDK is reached, not after — the probes here
  record every call, and most assertions are that the list stayed empty;
* the Search slots report "not configured" without probing, and the *same*
  code path reads a live index once an endpoint exists.

Offline. No Azure account, no network, no credential.
"""

from __future__ import annotations

import asyncio
import json
import unittest
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

from azdata import HttpResponse, Limits, Policy
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from resource_explorer.content import (
    ContentPayload,
    ContentResult,
    collected_now,
)
from resource_explorer import (
    SELECTION_HEADER,
    InventoryRegistry,
    InventoryService,
    ProbeReport,
    build_inventory_router,
    source_node,
    use_case_node,
)
from app.cybereye.backend.inventory.manifest import (
    MANIFEST_PATH,
    ManifestError,
    load_registry,
)
from resource_explorer.probes import AdxProbe, GremlinProbe, SearchProbe

LIVE_ENV = {
    "ADX_CLUSTER_URI": "https://adxperthcyber01.australiaeast.kusto.windows.net",
    "ADX_DATABASE": "PerthCyber",
    "CYBEREYE_TABLE": "EventsUnified",
    "GREMLIN_ACCOUNT": "cosmos-gremlin-perth-3d020490",
    "GREMLIN_DATABASE": "airportgraph",
    "GREMLIN_GRAPH": "ontology",
}


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class ManifestTests(unittest.TestCase):
    def test_the_shipped_manifest_declares_every_use_case_with_exact_labels(self) -> None:
        registry = load_registry(env=LIVE_ENV)
        self.assertEqual(
            [use_case.name for use_case in registry.use_cases],
            ["Perth Cybersec POC_0", "AIT", "Open-Source CyberSecurity"],
        )

    def test_each_replay_use_case_declares_one_table_and_one_graph(self) -> None:
        """Retrieval is knowledge, not telemetry: neither replay files a search index."""
        registry = load_registry(env=LIVE_ENV)
        expected = {
            "perth_cybersec_poc_0": ["adx_table", "gremlin_graph"],
            "ait": ["adx_table", "gremlin_graph"],
            "open_source_cybersecurity": ["search_index"],
        }
        for use_case in registry.use_cases:
            with self.subTest(use_case.use_case_id):
                kinds = sorted(item.source_type for item in use_case.sources)
                self.assertEqual(kinds, expected[use_case.use_case_id])

    def test_ait_coordinates_are_its_own_and_not_perths(self) -> None:
        """Name matching is what files a source under the wrong use case."""
        registry = load_registry(env=LIVE_ENV)
        ait = registry.source("ait", "ait.adx.events")
        perth = registry.source("perth_cybersec_poc_0", "perth.adx.events_unified")
        assert ait is not None and perth is not None
        self.assertEqual(ait.binding.coordinates["database"], "AitLogs")
        self.assertEqual(ait.binding.coordinates["table"], "AitEvents")
        self.assertEqual(perth.binding.coordinates["database"], "PerthCyber")
        self.assertEqual(perth.binding.coordinates["table"], "EventsUnified")
        self.assertIsNone(registry.source("ait", "perth.adx.events_unified"))

    def test_graph_slots_target_different_graphs(self) -> None:
        registry = load_registry(env=LIVE_ENV)
        perth = registry.source("perth_cybersec_poc_0", "perth.gremlin.ontology")
        ait = registry.source("ait", "ait.gremlin.aitgraph")
        assert perth is not None and ait is not None
        self.assertEqual(perth.binding.coordinates["graph"], "ontology")
        self.assertEqual(ait.binding.coordinates["graph"], "aitgraph")

    def test_the_one_search_slot_is_the_shared_knowledge_index(self) -> None:
        registry = load_registry(env=LIVE_ENV)
        indexes = [item.source_id for item in registry.sources()
                   if item.source_type == "search_index"]
        self.assertEqual(indexes, ["cyberkb.search.mitre_attack"])
        for source_id, key in (("cyberkb.search.mitre_attack", "CYBEREYE_MITRE_SEARCH_INDEX"),):
            with self.subTest(source_id):
                found = next(
                    item for item in registry.sources() if item.source_id == source_id
                )
                self.assertFalse(found.is_configured)
                self.assertIn("CYBEREYE_SEARCH_ENDPOINT", found.binding.settings)
                self.assertIn(key, found.binding.settings)
                self.assertIn(key, found.unconfigured_detail)

    def test_no_declared_environment_key_is_missing_from_the_template(self) -> None:
        """The template is how an operator learns a slot exists."""
        template = (MANIFEST_PATH.parents[1] / ".env.example").read_text(encoding="utf-8")
        for source in load_registry(env=LIVE_ENV).sources():
            for key in source.binding.settings:
                with self.subTest(key):
                    self.assertIn(key, template)

    def test_the_manifest_carries_nothing_secret_shaped(self) -> None:
        text = MANIFEST_PATH.read_text(encoding="utf-8").lower()
        for banned in ("accountkey", "sharedaccesskey", "password", "client_secret", "api-key"):
            self.assertNotIn(banned, text)

    def test_an_absent_environment_key_leaves_a_source_unconfigured(self) -> None:
        registry = load_registry(env={})
        for source in registry.sources():
            with self.subTest(source.source_id):
                self.assertFalse(source.is_configured)

    def test_a_manifest_that_declares_a_coordinate_twice_is_refused(self) -> None:
        bad = self._temp_manifest(
            """
version: 1
use_cases:
  - id: alpha
    name: Alpha
    sources:
      - id: alpha.one
        name: One
        type: adx_table
        connector: adx
        coordinates: {endpoint: literal}
        coordinates_from_env: {endpoint: SOME_KEY}
        required: [endpoint]
"""
        )
        with self.assertRaises(ManifestError):
            load_registry(path=bad, env={})

    def test_a_required_coordinate_nobody_declares_is_refused(self) -> None:
        bad = self._temp_manifest(
            """
version: 1
use_cases:
  - id: alpha
    name: Alpha
    sources:
      - id: alpha.one
        name: One
        type: adx_table
        connector: adx
        coordinates: {database: d}
        required: [endpoint]
"""
        )
        with self.assertRaises(ManifestError):
            load_registry(path=bad, env={})

    def test_an_unknown_source_type_is_refused(self) -> None:
        bad = self._temp_manifest(
            """
version: 1
use_cases:
  - id: alpha
    name: Alpha
    sources:
      - id: alpha.one
        name: One
        type: mainframe
        connector: adx
"""
        )
        with self.assertRaises(ManifestError):
            load_registry(path=bad, env={})

    def test_a_wrong_version_is_refused(self) -> None:
        bad = self._temp_manifest("version: 2\nuse_cases: []\n")
        with self.assertRaises(ManifestError):
            load_registry(path=bad, env={})

    def test_an_absent_manifest_is_refused(self) -> None:
        with self.assertRaises(ManifestError):
            load_registry(path=Path("/nonexistent/data_inventory.yaml"), env={})

    def test_a_coordinate_outside_the_type_s_set_is_refused(self) -> None:
        """Each source type has a finite coordinate set, and it reaches a browser."""
        bad = self._temp_manifest(
            """
version: 1
use_cases:
  - id: alpha
    name: Alpha
    sources:
      - id: alpha.one
        name: One
        type: adx_table
        connector: adx
        coordinates: {endpoint: 'https://c.kusto.windows.net', container: blobs}
"""
        )
        with self.assertRaises(ManifestError) as caught:
            load_registry(path=bad, env={})
        self.assertIn("container", str(caught.exception))

    def test_a_credential_shaped_coordinate_is_refused_without_echoing_it(self) -> None:
        for name, value in (
            ("account_key", "AbCdEf0123456789=="),
            ("sas_token", "sv=2022-11-02&sig=deadbeef"),
            ("api-key", "abcdef123456"),
        ):
            with self.subTest(name):
                bad = self._temp_manifest(
                    f"""
version: 1
use_cases:
  - id: alpha
    name: Alpha
    sources:
      - id: alpha.one
        name: One
        type: adx_table
        connector: adx
        coordinates: {{endpoint: 'https://c.kusto.windows.net', {name}: '{value}'}}
"""
                )
                with self.assertRaises(ManifestError) as caught:
                    load_registry(path=bad, env={})
                self.assertIn(name, str(caught.exception))
                self.assertNotIn(value, str(caught.exception))

    def test_an_endpoint_carrying_a_signature_is_refused(self) -> None:
        """A SAS URL is how a credential travels inside something that looks like one."""
        sas = "https://acct.blob.core.windows.net/c?sv=2022-11-02&sig=deadbeefdeadbeef"
        bad = self._temp_manifest(
            f"""
version: 1
use_cases:
  - id: alpha
    name: Alpha
    sources:
      - id: alpha.one
        name: One
        type: adx_table
        connector: adx
        coordinates: {{endpoint: '{sas}'}}
"""
        )
        with self.assertRaises(ManifestError) as caught:
            load_registry(path=bad, env={})
        self.assertNotIn("sig=deadbeefdeadbeef", str(caught.exception))

    def test_an_endpoint_with_embedded_credentials_is_refused(self) -> None:
        secret = "https://admin:hunter2@c.kusto.windows.net"
        bad = self._temp_manifest(
            f"""
version: 1
use_cases:
  - id: alpha
    name: Alpha
    sources:
      - id: alpha.one
        name: One
        type: adx_table
        connector: adx
        coordinates: {{endpoint: '{secret}'}}
"""
        )
        with self.assertRaises(ManifestError) as caught:
            load_registry(path=bad, env={})
        self.assertNotIn("hunter2", str(caught.exception))

    def test_a_non_https_endpoint_is_refused(self) -> None:
        for endpoint in ("http://c.kusto.windows.net", "file:///etc/passwd", "notaurl"):
            with self.subTest(endpoint):
                bad = self._temp_manifest(
                    f"""
version: 1
use_cases:
  - id: alpha
    name: Alpha
    sources:
      - id: alpha.one
        name: One
        type: adx_table
        connector: adx
        coordinates: {{endpoint: '{endpoint}'}}
"""
                )
                with self.assertRaises(ManifestError):
                    load_registry(path=bad, env={})

    def test_a_name_that_is_not_a_resource_name_is_refused(self) -> None:
        for table in ("Events; drop", "../../etc/passwd", "a b"):
            with self.subTest(table):
                bad = self._temp_manifest(
                    f"""
version: 1
use_cases:
  - id: alpha
    name: Alpha
    sources:
      - id: alpha.one
        name: One
        type: adx_table
        connector: adx
        coordinates: {{table: '{table}'}}
"""
                )
                with self.assertRaises(ManifestError):
                    load_registry(path=bad, env={})

    def test_the_shipped_coordinates_pass_the_same_validation(self) -> None:
        """The guard is not one nothing real can satisfy."""
        registry = load_registry(env=LIVE_ENV)
        adx = registry.source("perth_cybersec_poc_0", "perth.adx.events_unified")
        graph = registry.source("ait", "ait.gremlin.aitgraph")
        assert adx is not None and graph is not None
        self.assertTrue(adx.is_configured)
        self.assertTrue(graph.is_configured)
        self.assertEqual(
            sorted(adx.binding.coordinates), ["database", "endpoint", "table"]
        )
        self.assertEqual(
            sorted(graph.binding.coordinates), ["account", "database", "graph"]
        )

    def _temp_manifest(self, body: str) -> Path:
        import tempfile

        handle = tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", delete=False, encoding="utf-8"
        )
        handle.write(body)
        handle.close()
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)


class SearchProbeTests(unittest.TestCase):
    """The unconfigured slot and the configured one, through the same code."""

    def _slot(self, endpoint: str = "", index: str = "") -> Any:
        registry = load_registry(
            env={
                **LIVE_ENV,
                "CYBEREYE_SEARCH_ENDPOINT": endpoint,
                "CYBEREYE_MITRE_SEARCH_INDEX": index,
            }
        )
        source = registry.source("open_source_cybersecurity", "cyberkb.search.mitre_attack")
        assert source is not None
        return source

    def test_unconfigured_reports_without_building_a_client(self) -> None:
        credential_provider = Mock(side_effect=AssertionError("unconfigured source requested identity"))
        transport = SimpleNamespace(request=AsyncMock(side_effect=AssertionError("unconfigured source requested data")))
        probe = SearchProbe(credential_provider=credential_provider, transport=transport)
        report = run(probe.metadata(self._slot()))
        self.assertEqual(report.status, "unconfigured")
        self.assertIsNone(report.total_rows)
        preview = run(probe.preview(self._slot(), limit=5))
        self.assertEqual(preview.status, "unconfigured")
        credential_provider.assert_not_called()
        transport.request.assert_not_called()

    def test_a_configured_index_is_read_through_the_same_probe(self) -> None:
        """A simulated service, and it is labelled as one: this is not live proof."""
        transport = SimpleNamespace(request=AsyncMock(side_effect=[
            HttpResponse(200, {"value": [{"id": "a"}], "@odata.count": 1234}),
            HttpResponse(200, {"name": "mitre-attack-test", "fields": [{"name": "id", "type": "Edm.String", "key": True}]}),
            HttpResponse(200, {"value": [{"id": "a", "title": "one"}, {"id": "b", "title": "two"}]}),
        ]))
        credential = SimpleNamespace(get_token=lambda *args: SimpleNamespace(token="offline", expires_on=2**31))
        probe = SearchProbe(credential_provider=lambda: credential, transport=transport)
        slot = self._slot(endpoint="https://search.example.net", index="mitre-attack-test")

        async def read():
            try:
                return await probe.metadata(slot), await probe.preview(slot, limit=5)
            finally:
                await probe.aclose()

        report, preview = run(read())
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.metrics["document_count"], 1234)
        self.assertEqual(report.total_rows, 1234)
        self.assertEqual(preview.status, "ok")
        self.assertEqual(len(preview.payload.rows), 2)
        requests = [call.args[0] for call in transport.request.call_args_list]
        self.assertIn("mitre-attack-test", requests[0].url)
        self.assertEqual(requests[-1].body["search"], "*")
        self.assertEqual(requests[-1].body["top"], 5)

    def test_a_refused_index_is_forbidden_not_an_exception(self) -> None:
        transport = SimpleNamespace(request=AsyncMock(return_value=HttpResponse(403)))
        credential = SimpleNamespace(get_token=lambda *args: SimpleNamespace(token="offline", expires_on=2**31))
        probe = SearchProbe(credential_provider=lambda: credential, transport=transport)

        async def read():
            try:
                return await probe.metadata(self._slot(endpoint="https://s", index="i"))
            finally:
                await probe.aclose()

        report = run(read())
        self.assertEqual(report.status, "forbidden")


class GremlinProbeTests(unittest.TestCase):
    def _slot(self, source_id: str = "perth.gremlin.ontology", use_case: str = "perth_cybersec_poc_0") -> Any:
        source = load_registry(env=LIVE_ENV).source(use_case, source_id)
        assert source is not None
        return source

    @staticmethod
    def _probe(factory: Any, account: str = LIVE_ENV["GREMLIN_ACCOUNT"]) -> GremlinProbe:
        return GremlinProbe(service_factory=factory, deployment_account=account)

    def test_counts_come_from_the_graph_the_source_names(self) -> None:
        built: list[tuple[str, str, str]] = []

        class FakeGraph:
            def __init__(self, target: Any) -> None:
                self.target = target

            def element_count(self, element: str) -> int:
                return 1308 if element == "vertices" else 2429

            def sample(self, element: str, limit: int) -> list[dict[str, Any]]:
                return [
                    {"id": f"{self.target.graph}-{i}", "label": "Host"}
                    for i in range(limit)
                ]

        def factory(target: Any) -> Any:
            built.append((target.account, target.database, target.graph))
            return FakeGraph(target)

        probe = self._probe(factory)
        report = run(probe.metadata(self._slot()))
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.metrics, {"vertices": 1308, "edges": 2429})
        self.assertEqual(
            built, [(LIVE_ENV["GREMLIN_ACCOUNT"], "airportgraph", "ontology")]
        )

        ait = run(probe.metadata(self._slot("ait.gremlin.aitgraph", "ait")))
        self.assertEqual(ait.status, "ok")
        self.assertEqual(
            built[-1], (LIVE_ENV["GREMLIN_ACCOUNT"], "airportgraph", "aitgraph")
        )

    def test_two_accounts_with_the_same_graph_name_cannot_alias(self) -> None:
        """The reproduced defect: the account was checked non-empty and dropped.

        Two sources declaring the same database and graph in *different*
        accounts both answered `ok` from one client built for the first
        account, so the second showed the first's data under its own name.
        """
        built: list[tuple[str, str, str]] = []

        class FakeGraph:
            def element_count(self, element: str) -> int:
                return 1

            def sample(self, element: str, limit: int) -> list[dict[str, Any]]:
                return [{"id": "v1"}]

        def factory(target: Any) -> Any:
            built.append((target.account, target.database, target.graph))
            return FakeGraph()

        probe = self._probe(factory, account="account-one")
        mine = run(probe.metadata(graph_slot("account-one")))
        theirs = run(probe.metadata(graph_slot("account-two")))

        self.assertEqual(mine.status, "ok")
        self.assertEqual(theirs.status, "unconfigured")
        self.assertIn("account-two", theirs.detail)
        self.assertIn("account-one", theirs.detail)
        # One client, for the one account this deployment can key.
        self.assertEqual(built, [("account-one", "db", "g")])

    def test_a_foreign_account_is_refused_before_a_preview_reader_runs(self) -> None:
        def factory(_target: Any) -> Any:
            raise AssertionError("a client was built for an account with no key")

        probe = self._probe(factory, account="account-one")
        result = run(probe.preview(graph_slot("account-two"), limit=5))
        self.assertEqual(result.status, "unconfigured")
        self.assertIn("account-two", result.detail)

    def test_a_deployment_with_no_account_reads_nothing(self) -> None:
        def factory(_target: Any) -> Any:
            raise AssertionError("a client was built with no account configured")

        probe = self._probe(factory, account="")
        report = run(probe.metadata(graph_slot("account-one")))
        self.assertEqual(report.status, "unconfigured")
        self.assertIn("GREMLIN_ACCOUNT", report.detail)

    def test_one_client_per_distinct_target(self) -> None:
        built: list[tuple[str, str, str]] = []

        class FakeGraph:
            def element_count(self, element: str) -> int:
                return 1

        def factory(target: Any) -> Any:
            built.append((target.account, target.database, target.graph))
            return FakeGraph()

        probe = self._probe(factory)
        for _ in range(2):
            run(probe.metadata(self._slot()))
            run(probe.metadata(self._slot("ait.gremlin.aitgraph", "ait")))
        self.assertEqual(len(built), 2)
        self.assertEqual({item[2] for item in built}, {"ontology", "aitgraph"})

    def test_an_unset_key_is_unconfigured_and_names_it(self) -> None:
        from app.cybereye.backend.data.graph import GraphUnavailable

        class Unset:
            def element_count(self, element: str) -> int:
                raise GraphUnavailable("unset: GREMLIN_RESOURCE_GROUP")

        probe = self._probe(lambda _target: Unset())
        report = run(probe.metadata(self._slot()))
        self.assertEqual(report.status, "unconfigured")
        self.assertIn("GREMLIN_RESOURCE_GROUP", report.detail)

    def test_a_refused_key_read_is_forbidden(self) -> None:
        from app.cybereye.backend.data.graph import GraphUnavailable

        class Denied:
            def element_count(self, element: str) -> int:
                cause = RuntimeError("no role")
                cause.status_code = 403  # type: ignore[attr-defined]
                raise GraphUnavailable("gremlin query failed") from cause

        probe = self._probe(lambda _target: Denied())
        report = run(probe.metadata(self._slot()))
        self.assertEqual(report.status, "forbidden")

    def test_a_preview_asks_for_one_more_than_the_bound(self) -> None:
        calls: list[tuple[str, int]] = []

        class Sampler:
            def sample(self, element: str, limit: int) -> list[dict[str, Any]]:
                calls.append((element, limit))
                return [{"id": str(i)} for i in range(limit)]

        probe = self._probe(lambda _target: Sampler())
        result = run(probe.preview(self._slot(), limit=10))
        self.assertEqual(result.status, "ok")
        self.assertEqual(calls, [("vertices", 11)])
        self.assertTrue(result.truncated)


class GraphServiceTargetTests(unittest.TestCase):
    """The key read must target the graph being read, not the configured one."""

    def test_the_default_target_is_the_configured_one(self) -> None:
        from app.cybereye.backend.config import settings
        from app.cybereye.backend.data.graph import GraphService

        service = GraphService()
        self.assertEqual(
            service.target,
            (settings.graph_account, settings.graph_database, settings.graph_name),
        )
        self.assertEqual(service.resource_group, settings.graph_resource_group)
        self.assertEqual(service.subscription, settings.graph_subscription_id)

    def test_an_overridden_target_resolves_its_own_key(self) -> None:
        from app.cybereye.backend.data.graph import GraphService
        from app.cybereye.backend.data.graph_binding import bind_graph
        from types import SimpleNamespace

        connector = bind_graph(account="cosmos-other", database="otherdb", graph="othergraph",
            resource_group="rg-other", subscription="00000000-0000-0000-0000-000000000001",
            credential=SimpleNamespace(get_token=lambda *args: None))
        service = GraphService(connector=connector, account="cosmos-other", database="otherdb", graph="othergraph",
            resource_group="rg-other", subscription="00000000-0000-0000-0000-000000000001")
        self.assertEqual(service.target, ("cosmos-other", "otherdb", "othergraph"))
        self.assertEqual(connector.describe().target.coordinates, {"database": "otherdb", "container": "othergraph"})
        self.assertEqual(connector.describe().grants, ("query",))
        run(service.aclose())

    def test_an_unset_arm_coordinate_names_the_key_and_reads_nothing(self) -> None:
        from app.cybereye.backend.data.graph import GraphService, GraphUnavailable
        from app.cybereye.backend.data.graph_binding import bind_graph
        from unittest.mock import patch

        connector = bind_graph(account="cosmos-other", database="db", graph="graph", resource_group="rg-other",
                               subscription="", credential=object())
        service = GraphService(connector=connector)
        with self.assertRaises(GraphUnavailable) as caught:
            with patch("azure.mgmt.cosmosdb.aio.CosmosDBManagementClient") as factory:
                run(service.element_count("vertices"))
        self.assertIn("unconfigured", str(caught.exception))
        factory.assert_not_called()


def graph_slot(account: str, *, database: str = "db", graph: str = "g") -> Any:
    """One gremlin source in a named account. Not from the shipped manifest."""
    from resource_explorer import InventorySource, SourceBinding

    return InventorySource(
        source_id="test.graph",
        use_case_id="test",
        name="Test graph",
        source_type="gremlin_graph",
        holds="",
        capabilities=("metadata", "preview"),
        binding=SourceBinding(
            connector="gremlin",
            coordinates={"account": account, "database": database, "graph": graph},
            required=("account", "database", "graph"),
        ),
    )


class RecordingProbe:
    def __init__(self) -> None:
        self.metadata_calls: list[str] = []
        self.preview_calls: list[str] = []

    async def metadata(self, source: Any) -> ProbeReport:
        self.metadata_calls.append(source.source_id)
        return ProbeReport(
            status="ok",
            metrics={"row_count": 15520},
            total_rows=15520,
            collected_at=collected_now(),
        )

    async def preview(self, source: Any, *, limit: int) -> ContentResult:
        self.preview_calls.append(source.source_id)
        return ContentResult(
            service="adx",
            kind="rows",
            status="ok",
            payload=ContentPayload(
                form="rows",
                media_type="application/json",
                rows=tuple({"TimeGenerated": f"t{i}"} for i in range(min(limit, 2))),
                columns=("TimeGenerated",),
                size_bytes=2,
            ),
            collected_at=collected_now(),
        )


def api(registry: InventoryRegistry, probe: RecordingProbe) -> TestClient:
    service = InventoryService(registry, {"adx": probe, "gremlin": probe, "search": probe})
    app = FastAPI()
    app.state.inventory = service
    app.include_router(build_inventory_router(lambda request: _from(request)))
    return TestClient(app)


def _from(request: Request) -> InventoryService:
    return request.app.state.inventory


ORDINAL_SCHEMA = tuple({"name": f"field_{180 - ordinal:03d}", "type": "string"}
                       for ordinal in range(181))
CATALOGUE_LIMITS = {"rows": (1, 100), "columns": 512, "cell_chars": 4000,
                    "serialized_bytes": 1_048_576}


def adx_response(rows, columns, *, partial=False):
    return HttpResponse(200, [
        {"FrameType": "DataTable", "TableId": 0, "TableKind": "PrimaryResult", "TableName": "PrimaryResult",
         "Columns": [{"ColumnName": name, "ColumnType": kind} for name, kind in columns], "Rows": rows},
        {"FrameType": "DataSetCompletion", "HasErrors": partial},
    ])


class CanonicalAdxProbeTests(unittest.IsolatedAsyncioTestCase):
    def probe(self, *responses):
        self.transport = SimpleNamespace(request=AsyncMock(side_effect=list(responses)))
        self.credential = SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline", expires_on=2**31)), close=Mock())
        probe = AdxProbe(credential_provider=lambda: self.credential, transport=self.transport,
                         policy=Policy("offline-catalogue", grants={"query"}, max_concurrency=1,
                                       limits=Limits(timeout_seconds=20, max_items=100, max_attempts=1)))
        self.addAsyncCleanup(probe.aclose)
        return probe

    def source(self):
        return load_registry(env=LIVE_ENV).source("perth_cybersec_poc_0", "perth.adx.events_unified")

    async def test_adx_count_and_packed_ordinal_schema_share_one_deadline(self):
        probe = self.probe(adx_response([[0]], [("Count", "long")]),
                           adx_response([[list(ORDINAL_SCHEMA), 181]], [("fields", "dynamic"), ("field_count", "long")]))
        report = await probe.metadata(self.source())
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.metrics, {"row_count": 0, "column_count": 181})
        self.assertEqual(report.total_rows, 0)
        self.assertEqual(report.schema_fields, ORDINAL_SCHEMA)
        requests = [call.args[0] for call in self.transport.request.call_args_list]
        self.assertEqual(requests[0].body["csl"], '["EventsUnified"] | count')
        self.assertEqual(requests[1].body["csl"], '["EventsUnified"] | getschema | order by ColumnOrdinal asc\n'
                         '| summarize fields=make_list(bag_pack("name", ColumnName, "type", coalesce(ColumnType, DataType))), field_count=count()')
        for request in requests:
            options = json.loads(request.body["properties"])["Options"]
            self.assertEqual(options["truncationmaxrecords"], 1)
            self.assertTrue(options["request_readonly"])
            self.assertIn("/v2/rest/query", request.url)
        self.assertLess(requests[1].timeout_seconds, requests[0].timeout_seconds)
        self.assertLessEqual(requests[0].timeout_seconds, 20)

    async def test_adx_known_count_survives_schema_failure(self):
        probe = self.probe(adx_response([[7]], [("Count", "long")]), HttpResponse(403))
        report = await probe.metadata(self.source())
        self.assertEqual(report.status, "forbidden")
        self.assertEqual(report.total_rows, 7)
        self.assertEqual(report.metrics, {"row_count": 7})
        self.assertEqual(report.schema_fields, ())

    async def test_adx_malformed_wide_schemas_do_not_pass(self):
        for fields, count in ((list(ORDINAL_SCHEMA), 180), ([ORDINAL_SCHEMA[0], ORDINAL_SCHEMA[0]], 2),
                              ("not-json", 1), ([{"name": "one"}], 1)):
            with self.subTest(count=count):
                probe = self.probe(adx_response([[7]], [("Count", "long")]),
                    adx_response([[fields, count]], [("fields", "dynamic"), ("field_count", "long")]))
                report = await probe.metadata(self.source())
                self.assertEqual(report.status, "unavailable")
                self.assertEqual(report.total_rows, 7)

    async def test_adx_count_unknown_invalid_and_partial_are_not_zero(self):
        for count in (None, True, -1):
            with self.subTest(count=count):
                probe = self.probe(adx_response([[count]], [("Count", "dynamic")]))
                report = await probe.metadata(self.source())
                self.assertEqual(report.status, "unavailable")
                self.assertIsNone(report.total_rows)
                self.assertNotIn("row_count", report.metrics)
        probe = self.probe(adx_response([[1]], [("Count", "long")], partial=True))
        self.assertEqual((await probe.metadata(self.source())).status, "unavailable")

    async def test_adx_preview_preserves_empty_columns_and_exact_service_limit(self):
        for limit in (1, 100):
            probe = self.probe(adx_response([], [("Last", "string"), ("First", "long")]))
            result = await probe.preview(self.source(), limit=limit)
            self.assertEqual(result.status, "empty")
            self.assertEqual(result.payload.columns, ("Last", "First"))
            self.assertEqual(result.payload.rows, ())
            request = self.transport.request.call_args.args[0]
            self.assertEqual(request.body["csl"], f'["EventsUnified"] | take {limit}')
            self.assertEqual(json.loads(request.body["properties"])["Options"]["truncationmaxrecords"], limit)

    async def test_adx_multiple_primary_tables_and_partial_preview_are_unavailable(self):
        primary = adx_response([], [("value", "long")]).body[0]
        multiple = HttpResponse(200, [primary, {**primary, "TableId": 1}])
        for response in (multiple, adx_response([[1]], [("value", "long")], partial=True)):
            probe = self.probe(response)
            self.assertEqual((await probe.preview(self.source(), limit=1)).status, "unavailable")

    async def test_adx_invalid_table_and_limit_refuse_before_credential_or_transport(self):
        probe = self.probe()
        source = self.source()
        invalid = replace(source, binding=replace(source.binding, coordinates={
            **source.binding.coordinates, "table": 'EventsUnified"] | drop'}))
        self.assertIn((await probe.metadata(invalid)).status, {"unconfigured", "unavailable"})
        for limit in (0, 101, True):
            self.assertEqual((await probe.preview(source, limit=limit)).status, "unavailable")
        self.transport.request.assert_not_called()
        self.credential.get_token.assert_not_called()


class CanonicalSearchProbeTests(unittest.IsolatedAsyncioTestCase):
    def probe(self, *responses, maximum_bytes=1_048_576):
        self.transport = SimpleNamespace(request=AsyncMock(side_effect=list(responses)))
        self.credential = SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline", expires_on=2**31)), close=Mock())
        probe = SearchProbe(credential_provider=lambda: self.credential, transport=self.transport,
            policy=Policy("offline-search", grants={"query", "schema.read"}, max_concurrency=1,
                          limits=Limits(timeout_seconds=20, max_attempts=1, max_output_bytes=maximum_bytes)))
        self.addAsyncCleanup(probe.aclose)
        return probe

    def source(self):
        return load_registry(env={**LIVE_ENV, "CYBEREYE_SEARCH_ENDPOINT": "https://unit.search.windows.net",
                                  "CYBEREYE_MITRE_SEARCH_INDEX": "fixture"}).source(
                                  "open_source_cybersecurity", "cyberkb.search.mitre_attack")

    async def test_search_zero_count_has_ordered_schema_and_key_only_count_request(self):
        fields = [{"name": "id", "type": "Edm.String", "key": True},
                  {"name": "Last", "type": "Edm.String"}, {"name": "First", "type": "Edm.Int32"}]
        probe = self.probe(HttpResponse(200, {"value": [], "@odata.count": 0}),
                           HttpResponse(200, {"name": "fixture", "fields": fields}))
        report = await probe.metadata(self.source())
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.metrics, {"document_count": 0, "column_count": 3})
        self.assertEqual(report.total_rows, 0)
        self.assertEqual(report.schema_fields, tuple({"name": item["name"], "type": item["type"]} for item in fields))
        requests = [call.args[0] for call in self.transport.request.call_args_list]
        self.assertEqual(requests[0].body, {"search": "*", "select": "id", "top": 1, "count": True})
        self.assertEqual(requests[1].method, "GET")
        self.assertLess(requests[1].timeout_seconds, requests[0].timeout_seconds)

    async def test_search_unknown_counts_never_become_zero(self):
        for extra in ({}, {"@odata.count": None}, {"@odata.count": True}, {"@odata.count": -1}):
            with self.subTest(extra=extra):
                probe = self.probe(HttpResponse(200, {"value": [], **extra}))
                report = await probe.metadata(self.source())
                self.assertEqual(report.status, "unavailable")
                self.assertIsNone(report.total_rows)
                self.assertNotIn("document_count", report.metrics)
                self.assertEqual(self.transport.request.call_count, 1)

    async def test_search_preview_keeps_sdk_annotation_order_defaults_and_native_values(self):
        from azure.core.pipeline.transport import AsyncHttpResponse
        from azure.search.documents.aio import SearchClient

        payload = {"value": [{"id": "one", "title": None, "tags": ["a", "b"],
                              "nested": {"none": None}, "@search.rerankerScore": 2.5}]}

        class NativeResponse(AsyncHttpResponse):
            def __init__(self):
                super().__init__(None, None)
                self.status_code = 200
                self.headers = {"content-type": "application/json"}
                self.content_type = "application/json"

            def body(self):
                return json.dumps(payload).encode()

            async def load_body(self):
                return None

        credential = SimpleNamespace(get_token=AsyncMock(return_value=SimpleNamespace(token="offline", expires_on=2**31)))
        with patch("azure.core.pipeline.transport.AioHttpTransport.send", new=AsyncMock(return_value=NativeResponse())):
            async with SearchClient("https://unit.search.windows.net", "fixture", credential, retry_total=0) as native:
                native_rows = [row async for row in await native.search("*", top=1)]
        expected_columns = tuple(native_rows[0])
        self.assertEqual(expected_columns[-4:], ("@search.score", "@search.reranker_score", "@search.highlights", "@search.captions"))
        self.assertEqual(set(expected_columns[:-4]), {"id", "title", "tags", "nested"})
        probe = self.probe(HttpResponse(200, payload))
        result = await probe.preview(self.source(), limit=1)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.payload.columns, expected_columns)
        row = result.payload.rows[0]
        self.assertIsNone(row["title"])
        self.assertEqual(row["tags"], '["a", "b"]')
        self.assertEqual(row["nested"], '{"none": null}')
        self.assertEqual(row["@search.reranker_score"], 2.5)
        self.assertIsNone(row["@search.score"])
        self.assertNotIn("@search.rerankerScore", row)
        self.assertEqual(self.transport.request.call_args.args[0].body["top"], 1)

    async def test_search_first_row_that_cannot_fit_is_truncated_ok_not_empty(self):
        row = {"id": "one", "data": ['"\\'] * 150}
        self.assertLess(len(json.dumps(row).encode()), 1500)
        probe = self.probe(HttpResponse(200, {"value": [row]}), maximum_bytes=1500)
        result = await probe.preview(self.source(), limit=1)
        self.assertEqual(result.status, "ok")
        self.assertTrue(result.truncated)
        self.assertEqual(result.payload.rows, ())
        self.assertIn("byte limit", " ".join(result.payload.notes))
        sample = {"rows": result.payload.rows, "columns": result.payload.columns, "notes": result.payload.notes}
        self.assertLessEqual(len(json.dumps(sample, ensure_ascii=False).encode()), 1500)

    async def test_search_column_and_cell_omissions_are_explicit(self):
        row = {"id": "one", "text": "x" * 4500, **{f"field_{position}": position for position in range(514)}}
        probe = self.probe(HttpResponse(200, {"value": [row]}))
        result = await probe.preview(self.source(), limit=100)
        self.assertEqual(len(result.payload.columns), 512)
        self.assertTrue(result.truncated)
        self.assertIn("500 more characters not shown", result.payload.rows[0]["text"])
        self.assertIn("512", " ".join(result.payload.notes))
        self.assertIn("4000", " ".join(result.payload.notes))


class CanonicalProbeLifetimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_accounting_counts_cold_metadata_preview_and_failures_per_source(self):
        transport = SimpleNamespace(request=AsyncMock(side_effect=[
            adx_response([], [("value", "long")]), adx_response([[7]], [("Count", "long")]), HttpResponse(403)]))
        credential = SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline", expires_on=2**31)))
        probe = AdxProbe(credential_provider=lambda: credential, transport=transport)
        source = load_registry(env=LIVE_ENV).source("perth_cybersec_poc_0", "perth.adx.events_unified")
        self.assertEqual(probe.describe()["metrics"]["known_attempts"], 0)
        credential.get_token.assert_not_called()
        await probe.preview(source, limit=1)
        self.assertEqual((await probe.metadata(source)).status, "forbidden")
        metrics = probe.describe()["metrics"]
        self.assertEqual(metrics["known_attempts"], 3)
        self.assertEqual(metrics["operations"], {"query": 3, "schema": 0})
        self.assertEqual(metrics["sources"][source.source_id]["known_attempts"], 3)
        self.assertEqual(metrics["unknown_attempt_operations"], 0)
        await probe.aclose()

    async def test_explicit_probes_are_used_without_constructing_defaults(self):
        from app.cybereye.backend import inventory
        probes = {"adx": RecordingProbe()}
        with patch.object(inventory, "default_probes", side_effect=AssertionError("implicit probes")):
            service = inventory.build_service(load_registry(env=LIVE_ENV), probes=probes)
        self.assertIs(service._probes["adx"], probes["adx"])

    async def test_default_probes_borrow_explicit_credential_without_acquiring_tokens(self):
        from app.cybereye.backend.inventory import default_probes
        provider = Mock(return_value=None)
        probes = default_probes(credential_provider=provider)
        self.assertEqual(set(probes), {"adx", "search", "gremlin"})
        provider.assert_not_called()
        for name in ("adx", "search"):
            await probes[name].aclose()
        provider.assert_not_called()

    async def test_fixed_coordinates_and_credential_bindings_never_share_clients(self):
        from resource_explorer import probes as module
        from azdata import connect as canonical_connect
        credentials = [SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline", expires_on=2**31)), close=Mock())
                       for _ in range(2)]
        active = [credentials[0]]
        transport = SimpleNamespace(request=AsyncMock(return_value=adx_response([], [("value", "long")])) , aclose=AsyncMock())
        probe = AdxProbe(credential_provider=lambda: active[0], transport=transport)
        source = load_registry(env=LIVE_ENV).source("perth_cybersec_poc_0", "perth.adx.events_unified")
        with patch.object(module, "connect", wraps=canonical_connect) as connect:
            self.assertEqual((await probe.preview(source, limit=1)).status, "empty")
            self.assertEqual((await probe.preview(source, limit=1)).status, "empty")
            active[0] = credentials[1]
            self.assertEqual((await probe.preview(source, limit=1)).status, "empty")
            other = replace(source, binding=replace(source.binding, coordinates={**source.binding.coordinates, "table": "Other"}))
            self.assertEqual((await probe.preview(other, limit=1)).status, "empty")
            self.assertEqual(connect.call_count, 3)
        clients = list(probe._clients.values())
        loop = asyncio.get_running_loop()
        closures = []
        for client in clients:
            close = client.aclose

            async def owned_close(close=close):
                closures.append(asyncio.get_running_loop())
                await close()

            client.aclose = owned_close
        await probe.aclose()
        await probe.aclose()
        self.assertEqual(closures, [loop] * 3)
        self.assertEqual((await probe.preview(source, limit=1)).status, "unavailable")
        self.assertEqual(transport.request.call_count, 4)
        transport.aclose.assert_not_called()
        for credential in credentials:
            credential.close.assert_not_called()

    async def test_unconfigured_or_credentialless_probe_refuses_before_connect(self):
        from resource_explorer import probes as module
        source = load_registry(env=LIVE_ENV).source("perth_cybersec_poc_0", "perth.adx.events_unified")
        with patch.object(module, "connect", side_effect=AssertionError("connector created")):
            for provider in (None, lambda: None):
                probe = AdxProbe(credential_provider=provider)
                self.assertEqual((await probe.preview(source, limit=1)).status, "unconfigured")
                await probe.aclose()


class CatalogueMergeTests(unittest.TestCase):
    def test_empty_preview_uses_available_metadata_columns(self):
        class EmptyProbe(RecordingProbe):
            async def metadata(self, source):
                return ProbeReport(status="ok", total_rows=0, schema_fields=(
                    {"name": "Last", "type": "string"}, {"name": "First", "type": "long"}))

            async def preview(self, source, *, limit):
                return ContentResult(service="adx", kind="rows", status="empty")

        client = api(load_registry(env=LIVE_ENV), EmptyProbe())
        body = client.get("/api/inventory/content", params={"node": source_node("ait", "ait.adx.events")}).json()
        self.assertEqual(body["columns"], ["Last", "First"])
        self.assertEqual(body["status"], "empty")
        self.assertEqual(body["sampleOf"], 0)

    def test_full_limit_with_unknown_population_is_explicitly_truncated(self):
        class UnknownProbe(RecordingProbe):
            async def metadata(self, source):
                return ProbeReport(status="unavailable", total_rows=None)

        client = api(load_registry(env=LIVE_ENV), UnknownProbe())
        body = client.get("/api/inventory/content", params={"node": source_node("ait", "ait.adx.events"), "limit": 2}).json()
        self.assertIsNone(body["sampleOf"])
        self.assertTrue(body["truncated"])
        self.assertIn("row limit reached; total population is unknown", body["sampleNotes"])


class FrozenCatalogueTests(unittest.TestCase):
    def test_zero_unknown_and_wide_schema_are_independent_literals(self) -> None:
        self.assertEqual(len(ORDINAL_SCHEMA), 181)
        self.assertEqual(ORDINAL_SCHEMA[0], {"name": "field_180", "type": "string"})
        self.assertEqual(ORDINAL_SCHEMA[-1], {"name": "field_000", "type": "string"})
        for total in (0, None):
            with self.subTest(total=total):
                class LiteralProbe(RecordingProbe):
                    async def metadata(self, source: Any) -> ProbeReport:
                        return ProbeReport(status="ok" if total == 0 else "unavailable",
                                           metrics={"row_count": 0} if total == 0 else {},
                                           total_rows=total, schema_fields=ORDINAL_SCHEMA,
                                           detail="" if total == 0 else "count_unknown")

                client = api(load_registry(env=LIVE_ENV), LiteralProbe())
                node = source_node("ait", "ait.adx.events")
                resource = client.get("/api/inventory/resource", params={"node": node}).json()
                content = client.get("/api/inventory/content", params={"node": node}).json()
                self.assertEqual(resource["status"], "ok" if total == 0 else "unavailable")
                self.assertEqual(resource["metrics"], {"row_count": 0} if total == 0 else {})
                self.assertEqual(resource["schemaFields"], list(ORDINAL_SCHEMA))
                self.assertEqual(content["sampleOf"], total)

    def test_existing_preview_envelope_retains_limits_status_and_omissions(self) -> None:
        for limit in CATALOGUE_LIMITS["rows"]:
            for status in ("ok", "empty", "forbidden", "unreachable", "unconfigured", "unavailable"):
                with self.subTest(limit=limit, status=status):
                    class LiteralProbe(RecordingProbe):
                        async def metadata(self, source: Any) -> ProbeReport:
                            return ProbeReport(status="ok", total_rows=None)

                        async def preview(self, source: Any, *, limit: int) -> ContentResult:
                            self.preview_calls.append(str(limit))
                            return ContentResult(
                                service="adx", kind="rows", status=status, truncated=status == "ok",
                                payload=ContentPayload(form="rows", media_type="application/json",
                                                       columns=("Last", "First"), rows=(),
                                                       notes=("column limit", "cell limit", "byte limit")),
                                detail="partial_error" if status == "unavailable" else "",
                            )

                    probe = LiteralProbe()
                    client = api(load_registry(env=LIVE_ENV), probe)
                    response = client.get("/api/inventory/content", params={
                        "node": source_node("ait", "ait.adx.events"), "limit": limit})
                    self.assertEqual(response.status_code, 200)
                    body = response.json()
                    self.assertEqual(body["status"], status)
                    self.assertEqual(body["columns"], ["Last", "First"])
                    self.assertEqual(body["rowLimit"], limit)
                    self.assertEqual(body["sizeBytes"], 0)
                    self.assertEqual(body["sampleNotes"], ["column limit", "cell limit", "byte limit"])
                    self.assertEqual(body["truncated"], status == "ok")
                    self.assertEqual(probe.preview_calls, [str(limit)])


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_registry(env=LIVE_ENV)
        self.probe = RecordingProbe()
        self.client = api(self.registry, self.probe)

    def test_the_root_lists_exactly_the_declared_use_cases(self) -> None:
        response = self.client.get("/api/inventory/tree")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            [child["label"] for child in body["children"]],
            ["Perth Cybersec POC_0", "AIT", "Open-Source CyberSecurity"],
        )
        self.assertFalse(body["fixtures"])

    def test_every_response_refuses_caching(self) -> None:
        for path in (
            "/api/inventory/tree",
            "/api/inventory/selection",
            f"/api/inventory/resource?node={source_node('ait', 'ait.adx.events')}",
            f"/api/inventory/content?node={source_node('ait', 'ait.adx.events')}",
        ):
            with self.subTest(path):
                headers = self.client.get(path).headers
                self.assertEqual(headers["cache-control"], "no-store, private")
                self.assertEqual(headers["vary"], SELECTION_HEADER)

    def test_a_malformed_node_is_400_and_echoes_nothing(self) -> None:
        response = self.client.get("/api/inventory/tree?node=not-a-token!!")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_node")
        self.assertNotIn("not-a-token", response.text)
        self.assertEqual(self.probe.metadata_calls, [])

    def test_a_forged_cross_use_case_token_is_400_before_any_read(self) -> None:
        forged = source_node("ait", "perth.adx.events_unified")
        response = self.client.get(f"/api/inventory/resource?node={forged}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_node")
        self.assertEqual(self.probe.metadata_calls, [])

    def test_an_unknown_use_case_is_400(self) -> None:
        response = self.client.get(f"/api/inventory/tree?node={use_case_node('nope')}")
        self.assertEqual(response.status_code, 400)

    def test_an_oversized_node_is_rejected_before_the_codec(self) -> None:
        response = self.client.get("/api/inventory/tree?node=" + "a" * 9000)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_node")
        self.assertEqual(response.headers["cache-control"], "no-store, private")
        self.assertEqual(self.probe.metadata_calls, [])

    def test_a_rejection_never_echoes_the_submitted_token(self) -> None:
        """The client already has its token; reflecting it buys nothing."""
        token = "z" * 200
        for path in (
            f"/api/inventory/tree?node={token}",
            f"/api/inventory/resource?node={token}",
            f"/api/inventory/content?node={token}",
        ):
            with self.subTest(path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 400)
                self.assertNotIn(token, response.text)

    def test_an_excessive_row_bound_is_422_before_any_read(self) -> None:
        node = source_node("ait", "ait.adx.events")
        for limit in ("0", "101", "100000", "-5", "abc", ""):
            with self.subTest(limit):
                response = self.client.get(
                    f"/api/inventory/content?node={node}&limit={limit}"
                )
                self.assertEqual(response.status_code, 422)
                body = response.json()
                self.assertEqual(body["error"], "invalid_limit")
                self.assertEqual((body["minimum"], body["maximum"]), (1, 100))
                self.assertEqual(
                    response.headers["cache-control"], "no-store, private"
                )
                self.assertNotIn(str(limit) if limit else "@@", body.get("detail", ""))
        self.assertEqual(self.probe.preview_calls, [])

    def test_a_live_resource_read_carries_coordinates_and_a_timestamp(self) -> None:
        node = source_node("perth_cybersec_poc_0", "perth.adx.events_unified")
        body = self.client.get(f"/api/inventory/resource?node={node}").json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["metrics"]["row_count"], 15520)
        self.assertEqual(body["coordinates"]["database"], "PerthCyber")
        self.assertEqual(body["coordinates"]["table"], "EventsUnified")
        self.assertTrue(body["coordinates"]["endpoint"].startswith("https://"))
        self.assertTrue(body["observedAt"].endswith("Z"))
        self.assertIn("replay", body["provenance"].lower())

    def test_an_unconfigured_search_slot_is_reported_without_a_probe(self) -> None:
        node = source_node("open_source_cybersecurity", "cyberkb.search.mitre_attack")
        body = self.client.get(f"/api/inventory/content?node={node}").json()
        self.assertEqual(body["status"], "unconfigured")
        self.assertEqual(body["contentKind"], "none")
        self.assertIn("CYBEREYE_SEARCH_ENDPOINT", body["error"])
        self.assertEqual(self.probe.preview_calls, [])

    def test_a_disabled_source_is_409_and_never_reaches_a_reader(self) -> None:
        node = source_node("ait", "ait.adx.events")
        response = self.client.get(
            f"/api/inventory/content?node={node}",
            headers={SELECTION_HEADER: "perth.adx.events_unified"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "source_disabled")
        self.assertEqual(self.probe.preview_calls, [])

    def test_the_same_source_still_answers_for_another_session(self) -> None:
        """Two requests, two selections, no shared state between them."""
        node = source_node("ait", "ait.adx.events")
        off = self.client.get(
            f"/api/inventory/content?node={node}",
            headers={SELECTION_HEADER: "none"},
        )
        on = self.client.get(
            f"/api/inventory/content?node={node}",
            headers={SELECTION_HEADER: "all"},
        )
        self.assertEqual(off.status_code, 409)
        self.assertEqual(on.status_code, 200)
        self.assertEqual(on.json()["status"], "ok")

    def test_an_empty_selection_means_none(self) -> None:
        body = self.client.get(
            "/api/inventory/selection", headers={SELECTION_HEADER: ""}
        ).json()
        self.assertEqual(body["mode"], "none")
        self.assertEqual(body["enabled"], [])

    def test_an_absent_selection_header_means_all(self) -> None:
        body = self.client.get("/api/inventory/selection").json()
        self.assertEqual(body["mode"], "all")
        self.assertEqual(len(body["enabled"]), len(self.registry.source_ids()))

    def test_an_unknown_id_in_the_selection_is_400(self) -> None:
        response = self.client.get(
            "/api/inventory/tree",
            headers={SELECTION_HEADER: "ait.adx.events,not.a.source"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_selection")

    def test_a_forged_endpoint_in_the_selection_is_400(self) -> None:
        response = self.client.get(
            "/api/inventory/tree",
            headers={SELECTION_HEADER: "https://attacker.example.net/index"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_selection")
        self.assertEqual(self.probe.metadata_calls, [])

    def test_a_preview_reports_the_bound_and_the_population(self) -> None:
        node = source_node("ait", "ait.adx.events")
        body = self.client.get(f"/api/inventory/content?node={node}&limit=2").json()
        self.assertEqual(body["rowLimit"], 2)
        self.assertEqual(body["sizeBytes"], 2)
        self.assertEqual(body["sampleOf"], 15520)
        self.assertTrue(body["truncated"])

    def test_no_response_carries_a_credential_shaped_string(self) -> None:
        node = source_node("perth_cybersec_poc_0", "perth.gremlin.ontology")
        for path in (
            "/api/inventory/tree",
            f"/api/inventory/tree?node={use_case_node('perth_cybersec_poc_0')}",
            f"/api/inventory/resource?node={node}",
            f"/api/inventory/content?node={node}",
            "/api/inventory/selection",
        ):
            with self.subTest(path):
                text = self.client.get(path).text.lower()
                for banned in ("accountkey", "primarykey", "sharedaccesskey", "password", "bearer "):
                    self.assertNotIn(banned, text)

    def test_the_scope_statement_does_not_overclaim(self) -> None:
        body = self.client.get("/api/inventory/selection").json()
        scope = body["scope"].lower()
        self.assertIn("data sources", scope)
        self.assertIn("does not change", scope)
        self.assertIn("scanner", scope)


class CompositionTests(unittest.TestCase):
    def test_the_router_is_mounted_by_the_application(self) -> None:
        from app.cybereye.backend.main import app

        paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
        for path in (
            "/api/inventory/tree",
            "/api/inventory/resource",
            "/api/inventory/content",
            "/api/inventory/selection",
        ):
            self.assertIn(path, paths)

    def test_the_inventory_exposes_no_write_verb(self) -> None:
        from app.cybereye.backend.main import app

        for route in app.routes:  # type: ignore[attr-defined]
            path = getattr(route, "path", "")
            if path.startswith("/api/inventory"):
                self.assertEqual(
                    set(getattr(route, "methods", set())) - {"HEAD", "OPTIONS"}, {"GET"}
                )

    def test_the_selection_header_is_allowed_through_cors(self) -> None:
        from app.cybereye.backend.main import app

        allowed = [
            middleware
            for middleware in app.user_middleware
            if "CORSMiddleware" in str(middleware.cls)
        ]
        self.assertTrue(allowed)
        self.assertIn(SELECTION_HEADER, allowed[0].kwargs["allow_headers"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
