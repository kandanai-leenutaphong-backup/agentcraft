"""Knowledge binding, keyed identity and host-owned lifetime. Offline only."""

from __future__ import annotations

import asyncio
import unittest
from contextlib import ExitStack
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from azdata import ConnectorConfig, HttpResponse, Limits, Policy, ResourceAddress
from template_foundations.azure_search import SearchReadClient

from app.cybereye.backend.knowledge import search


CONFIG = ConnectorConfig("https://unit.search.windows.net", ResourceAddress({"index": "fixture"}),
                         ("unit.search.windows.net",))
POLICY = Policy("offline", grants={"query", "read"}, max_concurrency=1, limits=Limits(max_attempts=1))


class KnowledgeCacheTests(unittest.TestCase):
    def setUp(self):
        search.reset_client()
        self.addCleanup(search.reset_client)
        self.credential = SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline", expires_on=2**31)), close=Mock())

    def configure(self, *responses):
        transport = SimpleNamespace(request=AsyncMock(side_effect=list(responses)))
        client = search.configure(CONFIG, credential=self.credential, policy=POLICY, transport=transport)
        self.assertIsInstance(client, SearchReadClient)
        return client, transport

    def test_owned_replacement_reset_and_same_binding_reuse(self):
        first = search.configure(CONFIG, credential=self.credential, policy=POLICY)
        self.assertIs(first, search.configure(CONFIG, credential=self.credential, policy=POLICY))
        second_config = replace(CONFIG, target=ResourceAddress({"index": "other"}))
        second = search.configure(second_config, credential=self.credential, policy=POLICY)
        self.assertTrue(first.describe()["closed"])
        self.assertEqual(search.index_name(), "other")
        search.reset_client()
        self.assertTrue(second.describe()["closed"])
        self.credential.close.assert_not_called()
        self.credential.get_token.assert_not_called()

    def test_borrowed_set_client_is_never_closed(self):
        owned = search.configure(CONFIG, credential=self.credential, policy=POLICY)
        borrowed = SimpleNamespace(close=Mock())
        search.set_client(borrowed)
        self.assertTrue(owned.describe()["closed"])
        search.reset_client()
        borrowed.close.assert_not_called()

    def test_no_configured_binding_never_discovers_ambient_credentials(self):
        search.configure(None, credential=None, policy=POLICY)
        with self.assertRaises(search.KnowledgeUnavailable):
            search.retrieve(doc_kind="analytic", query="*", terms={}, top=1)

    def test_key_collision_absence_and_provider_failure(self):
        documents = [
            {"id": "analytic_T1001-0bc78cde", "doc_id": "T1001", "doc_kind": "analytic", "path": "analytic.yaml", "commit": "fixture"},
            {"id": "situation_type_T1001-adaac2e0", "doc_id": "T1001", "doc_kind": "situation_type", "path": "technique.yaml", "commit": "fixture"},
        ]
        _, transport = self.configure(*(HttpResponse(200, document) for document in documents),
                                      HttpResponse(404), HttpResponse(403))
        self.assertEqual(search.get_by_doc_id("analytic", "T1001"), documents[0])
        self.assertEqual(search.get_by_doc_id("situation_type", "T1001"), documents[1])
        self.assertIsNone(search.get_by_doc_id("analytic", "missing"))
        with self.assertRaises(search.KnowledgeUnavailable):
            search.get_by_doc_id("analytic", "unavailable")
        self.assertEqual(transport.request.call_count, 4)

    def test_status_preserves_counts_observed_before_later_failure(self):
        self.configure(HttpResponse(200, {"value": [], "@odata.count": 7}),
                       HttpResponse(200, {"value": [], "@odata.count": 2}), HttpResponse(403))
        report = search.status()
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
            def __enter__(self):
                events.append("credential-enter")
                return credential

            def __exit__(self, *args):
                events.append("credential-exit")

        def close_knowledge():
            with self.assertRaises(RuntimeError):
                asyncio.get_running_loop()
            events.append("knowledge-close")

        handle = SimpleNamespace(close=close_knowledge)

        async def close_probe():
            asyncio.get_running_loop()
            events.append("probe-close")

        probes = {"adx": SimpleNamespace(aclose=close_probe), "search": SimpleNamespace(aclose=close_probe)}
        settings = SimpleNamespace(validate=Mock(), detector_config_path="offline.yaml",
                                   agent_store_dir="/tmp/offline-agent-store", agent_models=(),
                                   search_endpoint=CONFIG.endpoint, knowledge_index="fixture")
        with ExitStack() as stack:
            stack.enter_context(patch.object(backend, "settings", settings))
            stack.enter_context(patch.object(backend, "DefaultAzureCredential", return_value=CredentialContext()))
            stack.enter_context(patch.object(backend, "ReadOnlyAdx", return_value=SimpleNamespace(close=lambda: events.append("adx-close"))))
            for name in ("load_agent_spec", "load_configuration", "Scanner", "AgentEditor", "GraphService", "build_inventory_service"):
                stack.enter_context(patch.object(backend, name, return_value=SimpleNamespace()))
            stack.enter_context(patch.object(backend, "AgentService", side_effect=RuntimeError("startup") if startup_failure else None))
            configure = stack.enter_context(patch.object(search, "configure", create=True, return_value=handle))
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
        self.assertEqual(events.count("probe-close"), 2)
        self.assertLess(events.index("probe-close"), events.index("credential-exit"))
        self.assertLess(events.index("knowledge-close"), events.index("credential-exit"))
        self.assertLess(events.index("adx-close"), events.index("credential-exit"))
        credential.get_token.assert_not_called()

    def test_normal_lifespan_closes_before_credential_exit(self):
        self.exercise(False)

    def test_partial_startup_closes_before_credential_exit(self):
        self.exercise(True)