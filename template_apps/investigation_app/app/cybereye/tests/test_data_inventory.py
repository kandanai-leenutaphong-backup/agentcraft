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
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.components.data_connector_library import (
    ContentPayload,
    ContentResult,
    clear_overrides,
    collected_now,
    override,
    override_missing,
)
from app.components.resource_explorer import (
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
from app.cybereye.backend.inventory.probes import GremlinProbe, SearchProbe

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

    def tearDown(self) -> None:
        clear_overrides()

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
        override_missing("azure.search.documents")
        probe = SearchProbe(credential_provider=lambda: object())
        report = run(probe.metadata(self._slot()))
        self.assertEqual(report.status, "unconfigured")
        self.assertIsNone(report.total_rows)
        preview = run(probe.preview(self._slot(), limit=5))
        self.assertEqual(preview.status, "unconfigured")

    def test_a_configured_index_is_read_through_the_same_probe(self) -> None:
        """A simulated service, and it is labelled as one: this is not live proof."""
        captured: dict[str, Any] = {}

        class FakeSearchClient:
            def __init__(self, **kwargs: Any) -> None:
                captured["client"] = kwargs

            def get_document_count(self) -> int:
                captured["counted"] = True
                return 1234

            def search(self, **kwargs: Any) -> list[dict[str, Any]]:
                captured["search"] = kwargs
                return [{"id": "a", "title": "one"}, {"id": "b", "title": "two"}]

        override(
            "azure.search.documents", SimpleNamespace(SearchClient=FakeSearchClient)
        )
        probe = SearchProbe(credential_provider=lambda: object())
        slot = self._slot(endpoint="https://search.example.net", index="mitre-attack-test")

        report = run(probe.metadata(slot))
        self.assertEqual(report.status, "ok")
        self.assertEqual(report.metrics["document_count"], 1234)
        self.assertEqual(report.total_rows, 1234)
        self.assertTrue(captured["counted"])

        preview = run(probe.preview(slot, limit=5))
        self.assertEqual(preview.status, "ok")
        self.assertEqual(len(preview.payload.rows), 2)
        self.assertEqual(captured["client"]["index_name"], "mitre-attack-test")
        self.assertEqual(captured["search"]["search_text"], "*")
        self.assertEqual(captured["search"]["top"], 6)

    def test_a_refused_index_is_forbidden_not_an_exception(self) -> None:
        class Denied:
            def __init__(self, **_: Any) -> None:
                pass

            def get_document_count(self) -> int:
                error = RuntimeError("denied")
                error.status_code = 403  # type: ignore[attr-defined]
                raise error

        override("azure.search.documents", SimpleNamespace(SearchClient=Denied))
        probe = SearchProbe(credential_provider=lambda: object())
        report = run(
            probe.metadata(self._slot(endpoint="https://s", index="i"))
        )
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

        class FakeArm:
            def __init__(self) -> None:
                self.paths: list[str] = []

            def post(self, path: str, timeout: int = 0) -> tuple[int, dict[str, str]]:
                self.paths.append(path)
                return 200, {"primaryReadonlyMasterKey": "not-a-real-key"}

        arm = FakeArm()
        service = GraphService(
            arm,
            account="cosmos-other",
            database="otherdb",
            graph="othergraph",
            resource_group="rg-other",
            subscription="00000000-0000-0000-0000-000000000001",
        )
        self.assertEqual(service.target, ("cosmos-other", "otherdb", "othergraph"))
        service._account_key()
        self.assertEqual(len(arm.paths), 1)
        self.assertIn("/subscriptions/00000000-0000-0000-0000-000000000001/", arm.paths[0])
        self.assertIn("/resourceGroups/rg-other/", arm.paths[0])
        self.assertIn("/databaseAccounts/cosmos-other/readonlykeys", arm.paths[0])

    def test_an_unset_arm_coordinate_names_the_key_and_reads_nothing(self) -> None:
        from app.cybereye.backend.data.graph import GraphService, GraphUnavailable

        def refuse(*_args: Any, **_kwargs: Any) -> None:
            raise AssertionError("ARM was called with an incomplete target")

        service = GraphService(
            SimpleNamespace(post=refuse),
            account="cosmos-other",
            resource_group="rg-other",
        )
        service.subscription = ""
        with self.assertRaises(GraphUnavailable) as caught:
            service._account_key()
        self.assertIn("GREMLIN_SUBSCRIPTION_ID", str(caught.exception))


def graph_slot(account: str, *, database: str = "db", graph: str = "g") -> Any:
    """One gremlin source in a named account. Not from the shipped manifest."""
    from app.components.resource_explorer import InventorySource, SourceBinding

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


class RouterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = load_registry(env=LIVE_ENV)
        self.probe = RecordingProbe()
        self.client = api(self.registry, self.probe)

    def test_the_root_lists_exactly_the_declared_use_cases(self) -> None:
        response = self.client.get("/api/cyber/inventory/tree")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            [child["label"] for child in body["children"]],
            ["Perth Cybersec POC_0", "AIT", "Open-Source CyberSecurity"],
        )
        self.assertFalse(body["fixtures"])

    def test_every_response_refuses_caching(self) -> None:
        for path in (
            "/api/cyber/inventory/tree",
            "/api/cyber/inventory/selection",
            f"/api/cyber/inventory/resource?node={source_node('ait', 'ait.adx.events')}",
            f"/api/cyber/inventory/content?node={source_node('ait', 'ait.adx.events')}",
        ):
            with self.subTest(path):
                headers = self.client.get(path).headers
                self.assertEqual(headers["cache-control"], "no-store, private")
                self.assertEqual(headers["vary"], SELECTION_HEADER)

    def test_a_malformed_node_is_400_and_echoes_nothing(self) -> None:
        response = self.client.get("/api/cyber/inventory/tree?node=not-a-token!!")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_node")
        self.assertNotIn("not-a-token", response.text)
        self.assertEqual(self.probe.metadata_calls, [])

    def test_a_forged_cross_use_case_token_is_400_before_any_read(self) -> None:
        forged = source_node("ait", "perth.adx.events_unified")
        response = self.client.get(f"/api/cyber/inventory/resource?node={forged}")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_node")
        self.assertEqual(self.probe.metadata_calls, [])

    def test_an_unknown_use_case_is_400(self) -> None:
        response = self.client.get(f"/api/cyber/inventory/tree?node={use_case_node('nope')}")
        self.assertEqual(response.status_code, 400)

    def test_an_oversized_node_is_rejected_before_the_codec(self) -> None:
        response = self.client.get("/api/cyber/inventory/tree?node=" + "a" * 9000)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_node")
        self.assertEqual(response.headers["cache-control"], "no-store, private")
        self.assertEqual(self.probe.metadata_calls, [])

    def test_a_rejection_never_echoes_the_submitted_token(self) -> None:
        """The client already has its token; reflecting it buys nothing."""
        token = "z" * 200
        for path in (
            f"/api/cyber/inventory/tree?node={token}",
            f"/api/cyber/inventory/resource?node={token}",
            f"/api/cyber/inventory/content?node={token}",
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
                    f"/api/cyber/inventory/content?node={node}&limit={limit}"
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
        body = self.client.get(f"/api/cyber/inventory/resource?node={node}").json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["metrics"]["row_count"], 15520)
        self.assertEqual(body["coordinates"]["database"], "PerthCyber")
        self.assertEqual(body["coordinates"]["table"], "EventsUnified")
        self.assertTrue(body["coordinates"]["endpoint"].startswith("https://"))
        self.assertTrue(body["observedAt"].endswith("Z"))
        self.assertIn("replay", body["provenance"].lower())

    def test_an_unconfigured_search_slot_is_reported_without_a_probe(self) -> None:
        node = source_node("open_source_cybersecurity", "cyberkb.search.mitre_attack")
        body = self.client.get(f"/api/cyber/inventory/content?node={node}").json()
        self.assertEqual(body["status"], "unconfigured")
        self.assertEqual(body["contentKind"], "none")
        self.assertIn("CYBEREYE_SEARCH_ENDPOINT", body["error"])
        self.assertEqual(self.probe.preview_calls, [])

    def test_a_disabled_source_is_409_and_never_reaches_a_reader(self) -> None:
        node = source_node("ait", "ait.adx.events")
        response = self.client.get(
            f"/api/cyber/inventory/content?node={node}",
            headers={SELECTION_HEADER: "perth.adx.events_unified"},
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "source_disabled")
        self.assertEqual(self.probe.preview_calls, [])

    def test_the_same_source_still_answers_for_another_session(self) -> None:
        """Two requests, two selections, no shared state between them."""
        node = source_node("ait", "ait.adx.events")
        off = self.client.get(
            f"/api/cyber/inventory/content?node={node}",
            headers={SELECTION_HEADER: "none"},
        )
        on = self.client.get(
            f"/api/cyber/inventory/content?node={node}",
            headers={SELECTION_HEADER: "all"},
        )
        self.assertEqual(off.status_code, 409)
        self.assertEqual(on.status_code, 200)
        self.assertEqual(on.json()["status"], "ok")

    def test_an_empty_selection_means_none(self) -> None:
        body = self.client.get(
            "/api/cyber/inventory/selection", headers={SELECTION_HEADER: ""}
        ).json()
        self.assertEqual(body["mode"], "none")
        self.assertEqual(body["enabled"], [])

    def test_an_absent_selection_header_means_all(self) -> None:
        body = self.client.get("/api/cyber/inventory/selection").json()
        self.assertEqual(body["mode"], "all")
        self.assertEqual(len(body["enabled"]), len(self.registry.source_ids()))

    def test_an_unknown_id_in_the_selection_is_400(self) -> None:
        response = self.client.get(
            "/api/cyber/inventory/tree",
            headers={SELECTION_HEADER: "ait.adx.events,not.a.source"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_selection")

    def test_a_forged_endpoint_in_the_selection_is_400(self) -> None:
        response = self.client.get(
            "/api/cyber/inventory/tree",
            headers={SELECTION_HEADER: "https://attacker.example.net/index"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_selection")
        self.assertEqual(self.probe.metadata_calls, [])

    def test_a_preview_reports_the_bound_and_the_population(self) -> None:
        node = source_node("ait", "ait.adx.events")
        body = self.client.get(f"/api/cyber/inventory/content?node={node}&limit=2").json()
        self.assertEqual(body["rowLimit"], 2)
        self.assertEqual(body["sizeBytes"], 2)
        self.assertEqual(body["sampleOf"], 15520)
        self.assertTrue(body["truncated"])

    def test_no_response_carries_a_credential_shaped_string(self) -> None:
        node = source_node("perth_cybersec_poc_0", "perth.gremlin.ontology")
        for path in (
            "/api/cyber/inventory/tree",
            f"/api/cyber/inventory/tree?node={use_case_node('perth_cybersec_poc_0')}",
            f"/api/cyber/inventory/resource?node={node}",
            f"/api/cyber/inventory/content?node={node}",
            "/api/cyber/inventory/selection",
        ):
            with self.subTest(path):
                text = self.client.get(path).text.lower()
                for banned in ("accountkey", "primarykey", "sharedaccesskey", "password", "bearer "):
                    self.assertNotIn(banned, text)

    def test_the_scope_statement_does_not_overclaim(self) -> None:
        body = self.client.get("/api/cyber/inventory/selection").json()
        scope = body["scope"].lower()
        self.assertIn("data sources", scope)
        self.assertIn("does not change", scope)
        self.assertIn("scanner", scope)


class CompositionTests(unittest.TestCase):
    def test_the_router_is_mounted_by_the_application(self) -> None:
        from app.cybereye.backend.main import app

        paths = {route.path for route in app.routes}  # type: ignore[attr-defined]
        for path in (
            "/api/cyber/inventory/tree",
            "/api/cyber/inventory/resource",
            "/api/cyber/inventory/content",
            "/api/cyber/inventory/selection",
        ):
            self.assertIn(path, paths)

    def test_the_inventory_exposes_no_write_verb(self) -> None:
        from app.cybereye.backend.main import app

        for route in app.routes:  # type: ignore[attr-defined]
            path = getattr(route, "path", "")
            if path.startswith("/api/cyber/inventory"):
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
