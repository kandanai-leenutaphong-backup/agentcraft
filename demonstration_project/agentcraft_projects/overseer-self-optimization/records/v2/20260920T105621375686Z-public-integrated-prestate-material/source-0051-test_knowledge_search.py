"""Knowledge binding, keyed identity and host-owned lifetime. Offline only."""

from __future__ import annotations

import asyncio
import unittest
from contextlib import ExitStack
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from azdata import ConnectorConfig, DataConnector, HttpResponse, Limits, OperationResult, Policy, QueryRequest, ResourceAddress

from app.cybereye.backend.knowledge import search


CONFIG = ConnectorConfig("https://unit.search.windows.net", ResourceAddress({"index": "fixture"}),
                         ("unit.search.windows.net",))
POLICY = Policy("offline", grants={"query", "read"}, max_concurrency=1, limits=Limits(max_attempts=1))


class KnowledgeCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await search.reset_client()
        self.addAsyncCleanup(search.reset_client)
        self.credential = SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline", expires_on=2**31)), close=Mock())

    async def configure(self, *responses):
        transport = SimpleNamespace(request=AsyncMock(side_effect=list(responses)))
        client = await search.configure(CONFIG, credential=self.credential, policy=POLICY, transport=transport)
        self.assertIsInstance(client, DataConnector)
        return client, transport

    async def test_owned_replacement_reset_and_same_binding_reuse(self):
        first = await search.configure(CONFIG, credential=self.credential, policy=POLICY)
        self.assertIs(first, await search.configure(CONFIG, credential=self.credential, policy=POLICY))
        second_config = replace(CONFIG, target=ResourceAddress({"index": "other"}))
        second = await search.configure(second_config, credential=self.credential, policy=POLICY)
        self.assertEqual((await first.query(QueryRequest(dialect="search", expression="*"))).errors[0].code, "connector_closed")
        self.assertEqual(search.index_name(), "other")
        await search.reset_client()
        self.assertEqual((await second.query(QueryRequest(dialect="search", expression="*"))).errors[0].code, "connector_closed")
        self.credential.close.assert_not_called()
        self.credential.get_token.assert_not_called()

    async def test_borrowed_set_client_is_never_closed(self):
        owned = await search.configure(CONFIG, credential=self.credential, policy=POLICY)
        borrowed = SimpleNamespace(aclose=AsyncMock())
        await search.set_client(borrowed)
        self.assertEqual((await owned.query(QueryRequest(dialect="search", expression="*"))).errors[0].code, "connector_closed")
        await search.reset_client()
        borrowed.aclose.assert_not_called()

    async def test_no_configured_binding_never_discovers_ambient_credentials(self):
        await search.configure(None, credential=None, policy=POLICY)
        with self.assertRaises(search.KnowledgeUnavailable):
            await search.retrieve(doc_kind="analytic", query="*", terms={}, top=1)
        self.assertEqual(search.describe()["metrics"]["submitted"], 0)

    async def test_metrics_known_zero_unknown_and_reset_during_operation(self):
        _, transport = await self.configure(HttpResponse(200, {"value": []}))
        with self.assertRaises(search.KnowledgeUnavailable):
            await search._CACHE.operation(QueryRequest(dialect="invalid", expression="*"))
        self.assertEqual(search.describe()["metrics"], {
            "submitted": 1, "completed": 1, "known_attempts": 0,
            "unknown_attempt_operations": 0, "operations": {"query": 1, "read": 0},
        })
        transport.request.assert_not_called()
        await search.retrieve(doc_kind="analytic", query="*", terms={}, top=1)
        self.assertEqual(search.describe()["metrics"]["known_attempts"], 1)
        entered, release = asyncio.Event(), asyncio.Event()

        async def pending(request):
            entered.set()
            await release.wait()
            return OperationResult("fixture", "query", "search", CONFIG.target, "success", metrics={"attempts": 7})

        borrowed = SimpleNamespace(query=AsyncMock(side_effect=pending), aclose=AsyncMock())
        await search.set_client(borrowed)
        task = asyncio.create_task(search._CACHE.operation(QueryRequest(dialect="search", expression="*")))
        await entered.wait()
        self.assertEqual(search.describe()["metrics"]["submitted"], 1)
        await search.reset_client()
        release.set()
        await task
        self.assertEqual(search.describe()["metrics"], {
            "submitted": 0, "completed": 0, "known_attempts": 0,
            "unknown_attempt_operations": 0, "operations": {"query": 0, "read": 0},
        })
        borrowed.aclose.assert_not_called()
        borrowed.query.side_effect = OSError("offline")
        await search.set_client(borrowed)
        with self.assertRaisesRegex(search.KnowledgeUnavailable, "knowledge_transport_unavailable"):
            await search._CACHE.operation(QueryRequest(dialect="search", expression="*"))
        snapshot = search.describe()["metrics"]
        self.assertEqual(snapshot["unknown_attempt_operations"], 1)
        snapshot["operations"]["query"] = 99
        self.assertEqual(search.describe()["metrics"]["operations"]["query"], 1)

    async def test_key_collision_absence_and_provider_failure(self):
        documents = [
            {"id": "analytic_T1001-0bc78cde", "doc_id": "T1001", "doc_kind": "analytic", "path": "analytic.yaml", "commit": "fixture"},
            {"id": "situation_type_T1001-adaac2e0", "doc_id": "T1001", "doc_kind": "situation_type", "path": "technique.yaml", "commit": "fixture"},
        ]
        _, transport = await self.configure(*(HttpResponse(200, document) for document in documents),
                                      HttpResponse(404), HttpResponse(403))
        self.assertEqual(await search.get_by_doc_id("analytic", "T1001"), documents[0])
        self.assertEqual(await search.get_by_doc_id("situation_type", "T1001"), documents[1])
        self.assertIsNone(await search.get_by_doc_id("analytic", "missing"))
        with self.assertRaises(search.KnowledgeUnavailable):
            await search.get_by_doc_id("analytic", "unavailable")
        self.assertEqual(transport.request.call_count, 4)

    async def test_status_preserves_counts_observed_before_later_failure(self):
        await self.configure(HttpResponse(200, {"value": [], "@odata.count": 7}),
                       HttpResponse(200, {"value": [], "@odata.count": 2}), HttpResponse(403))
        report = await search.status()
        self.assertFalse(report["available"])
        self.assertEqual(report["documents"], 7)
        self.assertEqual(report["situation_types"], 2)
        self.assertNotIn("analytics", report)
        self.assertFalse(report["local_fallback"])


class KnowledgeLifespanTests(unittest.TestCase):
    def exercise(self, startup_failure):
        from app.cybereye.backend import main as backend

        events = []
        credential = SimpleNamespace(get_token=Mock())

        class CredentialContext:
            async def __aenter__(self):
                events.append("credential-enter")
                return credential

            async def __aexit__(self, *args):
                events.append("credential-exit")

        async def close_knowledge():
            asyncio.get_running_loop()
            events.append("knowledge-close")

        handle = SimpleNamespace(aclose=close_knowledge)

        async def close_probe():
            asyncio.get_running_loop()
            events.append("probe-close")

        probes = {name: SimpleNamespace(aclose=close_probe) for name in ("adx", "search", "gremlin")}
        settings = SimpleNamespace(validate=Mock(), detector_config_path="offline.yaml",
                                   agent_store_dir="/tmp/offline-agent-store", agent_models=(),
                                   search_endpoint=CONFIG.endpoint, knowledge_index="fixture", allow_model_calls=False,
                                   graph_account="", graph_database="", graph_name="", graph_subscription_id="",
                                   graph_resource_group="")
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend, "settings", settings))
            stack.enter_context(patch.object(backend, "DefaultAzureCredential", return_value=CredentialContext()))
            stack.enter_context(patch.object(backend, "ReadOnlyAdx", return_value=SimpleNamespace(aclose=AsyncMock(side_effect=lambda: events.append("adx-close")))))
            for name in ("load_agent_spec", "load_configuration", "Scanner", "AgentEditor", "build_inventory_service"):
                stack.enter_context(patch.object(backend, name, return_value=SimpleNamespace()))
            stack.enter_context(patch.object(backend, "GraphService", return_value=SimpleNamespace(
                aclose=AsyncMock(side_effect=lambda: events.append("graph-close")))))
            stack.enter_context(patch.object(backend, "AgentService", side_effect=RuntimeError("startup") if startup_failure else None,
                return_value=SimpleNamespace(aclose=AsyncMock(side_effect=lambda: events.append("model-close")))))
            configure = stack.enter_context(patch.object(search, "configure", create=True, return_value=handle))
            stack.enter_context(patch.object(search, "reset_client", side_effect=close_knowledge))
            default_probes = stack.enter_context(patch.object(backend, "default_probes", create=True, return_value=probes))

            async def drive():
                async with backend.lifespan(backend.app):
                    events.append("running")

            if startup_failure:
                with self.assertRaisesRegex(RuntimeError, "startup"):
                    asyncio.run(drive())
            else:
                asyncio.run(drive())
            configure.assert_called_once()
            default_probes.assert_called_once()
            self.assertIs(default_probes.call_args.kwargs["credential_provider"](), credential)
            self.assertIs(configure.call_args.kwargs["credential"], credential)
            self.assertEqual(configure.call_args.kwargs["policy"].grants, {"query", "read"})
        self.assertEqual(events.count("knowledge-close"), 1)
        self.assertEqual(events.count("probe-close"), 3)
        self.assertLess(events.index("probe-close"), events.index("credential-exit"))
        self.assertLess(events.index("knowledge-close"), events.index("credential-exit"))
        self.assertLess(events.index("adx-close"), events.index("credential-exit"))
        if not startup_failure:
            for name in ("graph-close", "model-close"):
                self.assertEqual(events.count(name), 1)
                self.assertLess(events.index(name), events.index("credential-exit"))
        credential.get_token.assert_not_called()

    def test_normal_lifespan_closes_before_credential_exit(self):
        self.exercise(False)

    def test_partial_startup_closes_before_credential_exit(self):
        self.exercise(True)