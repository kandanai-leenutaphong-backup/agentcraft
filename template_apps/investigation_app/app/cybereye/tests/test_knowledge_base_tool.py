from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

from azdata import ConnectorConfig, HttpResponse, Limits, Policy, ResourceAddress

from app.cybereye.backend.agents.config import load_agent_spec
from app.cybereye.backend.investigation.detector.engine import _hit
from app.cybereye.backend.investigation.detector.rules import registry
from app.cybereye.backend.agents.tools import knowledge_base
from app.cybereye.backend.agents.tools.base import ToolContext
from app.cybereye.backend.agents.tools.knowledge_base import (
    MAX_PAYLOAD_BYTES, knowledge_status, search_mitre_attack,
)
from app.cybereye.tests.fake_search import install_fake_index
from app.cybereye.backend.knowledge import search as knowledge_search

BEHAVIOUR_BY_RULE = {
    "explicit_credential_burst": "credential_use",
    "directory_enumeration_alert": "directory_discovery",
    "tool_url_in_session_title": "privileged_session",
    "event_volume_excursion": "volume_anomaly",
    "fixed_interval_dns": "beaconing",
}


def document(**overrides: Any) -> dict[str, Any]:
    base = {
        "doc_id": "attack:000000000001", "source": "attack",
        "doc_type": "analytic", "title": "Explicit credential logon",
        "summary": "Detects suspicious explicit credential logon activity.",
        "body": "Detects suspicious processes logging on with explicit credentials.",
        "technique_ids": ["T1078"], "event_ids": ["4648"], "tool_names": [],
        "platforms": ["windows"], "log_sources": ["windows/security"],
        "data_connectors": [], "behaviour_class": ["credential_use"],
        "logic": "detection:\n  selection:\n    EventID: 4648", "logic_language": "sigma",
        "maturity": "", "severity": "medium",
        "path": ("cyber_kb/raw/sources/schemas-ontologies-standards/"
                 "att-ck-stix-data--f32b7fe344d3/repository/enterprise-attack/"
                 "enterprise-attack.json"),
        "native_id": "x-mitre-analytic--941e5c45", "commit": "d" * 40, "version": "",
        "license": "MITRE ATT&CK terms", "retrieved_at": "2026-08-29T16:32:57Z",
        "source_fields": {"attack_url": "https://attack.mitre.org/techniques/T1078"},
    }
    base.update(overrides)
    return base


PINNED_PATH = ("cyber_kb/raw/sources/schemas-ontologies-standards/"
               "att-ck-stix-data--f32b7fe344d3/repository/enterprise-attack/enterprise-attack.json")

CORPUS = [
    document(doc_id="attack:000000000001", title="Explicit credential logon analytic",
             summary="Detects suspicious explicit credential logon activity.",
             body="Detects suspicious processes logging on with explicit credentials.",
             technique_ids=["T1078"], behaviour_class=["credential_use"]),
    document(doc_id="attack:000000000002", doc_type="technique",
             title="T1087.002: Domain Account", summary="Adversaries enumerate domain accounts.",
             body="Account discovery against the domain.", technique_ids=["T1087.002"],
             event_ids=[], behaviour_class=["directory_discovery"], logic="",
             logic_language="", maturity="", severity=""),
    document(doc_id="attack:000000000003", doc_type="detection_strategy",
             title="Periodic DNS beacon cadence", summary="Fixed interval DNS lookups.",
             body="Beaconing cadence over DNS with jitter.", technique_ids=["T1071.004"],
             event_ids=[], behaviour_class=["beaconing"], platforms=["linux"],
             logic="", logic_language="", maturity="", severity="Low"),
]


class KnowledgeBaseToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = install_fake_index(self, CORPUS)
        self.context = ToolContext(adx=object(), scanner=object())  # type: ignore[arg-type]

    def search(self, **overrides: Any) -> dict[str, Any]:
        call: dict[str, Any] = {
            "question": "", "technique_ids": [], "behaviour_classes": [],
            "platforms": [], "max_results": 5,
        }
        call.update(overrides)
        return search_mitre_attack(self.context, **call)

    def test_returns_bounded_categorical_envelope(self) -> None:
        result = self.search(question="explicit credential logon")
        self.assertEqual(result["kind"], "cybereye_tool_result")
        self.assertEqual(result["category"], "mitre_attack")
        self.assertFalse(result["fallback"])
        self.assertTrue(result["historical_replay"])
        self.assertEqual(result["scope"]["retrieval"], "azure-ai-search")
        self.assertEqual(result["scope"]["row_count"], len(result["rows"]))
        self.assertEqual(result["rows"][0]["doc_id"], "attack:000000000001")
        self.assertEqual(sorted(result["rows"][0]), sorted(knowledge_base.COLUMNS))

    def test_the_answer_is_a_network_call_to_the_configured_index(self) -> None:
        self.client.calls.clear()
        self.search(question="explicit credential logon")
        self.assertEqual([call["index"] for call in self.client.calls], ["mitre-attack-test"])

    def test_exact_filters_are_pushed_into_the_index_filter(self) -> None:
        result = self.search(technique_ids=["T1087.002"])
        self.assertEqual([row["doc_id"] for row in result["rows"]], ["attack:000000000002"])
        self.assertIn("doc_kind eq 'analytic'", result["scope"]["index_filter"])
        self.assertEqual(result["scope"]["relaxed_filters"], [])
        self.assertEqual([row["doc_id"] for row in self.search(
            behaviour_classes=["beaconing"])["rows"]], ["attack:000000000003"])
        self.assertEqual([row["doc_id"] for row in self.search(
            platforms=["linux"])["rows"]], ["attack:000000000003"])

    def test_over_constrained_filters_relax_and_report_it(self) -> None:
        result = self.search(technique_ids=["T9999"], behaviour_classes=["beaconing"])
        self.assertEqual(result["scope"]["relaxed_filters"], ["technique_ids"])
        self.assertEqual([row["doc_id"] for row in result["rows"]], ["attack:000000000003"])

    def test_ranking_orders_by_question_relevance_and_is_deterministic(self) -> None:
        first = self.search(question="beaconing cadence jitter")
        self.assertEqual(first["rows"][0]["doc_id"], "attack:000000000003")
        self.assertGreater(first["rows"][0]["score"], 0.0)
        self.assertEqual(self.search(question="beaconing cadence jitter"), first)

    def test_max_results_bounds_the_payload(self) -> None:
        result = self.search(max_results=1)
        self.assertEqual(len(result["rows"]), 1)
        self.assertLess(len(json.dumps(result).encode("utf-8")), MAX_PAYLOAD_BYTES)

    def test_provenance_travels_with_every_row_and_is_never_invented(self) -> None:
        row = self.search(max_results=10)["rows"][0]
        self.assertEqual(row["path"], PINNED_PATH)
        self.assertEqual(row["commit"], "d" * 12)
        self.assertEqual(row["license"], "MITRE ATT&CK terms")
        self.assertLessEqual(len(row["snippet"]), knowledge_base.SNIPPET_CHARS + 1)

    def test_envelope_states_advisory_limits(self) -> None:
        advisory = self.search()["scope"]["advisory"]
        self.assertIn("not a verdict", advisory)
        self.assertIn("Only the telemetry tools observe", advisory)

    def test_status_reports_the_index_it_reads_and_no_local_fallback(self) -> None:
        status = knowledge_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["documents"], 3)
        self.assertEqual(status["index"], "mitre-attack-test")
        self.assertFalse(status["local_fallback"])


class UnreachableIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = install_fake_index(self, CORPUS)
        self.client.offline = True

    def test_an_unreachable_index_is_an_honest_envelope_not_a_local_answer(self) -> None:
        result = search_mitre_attack(
            ToolContext(adx=object(), scanner=object()),  # type: ignore[arg-type]
            question="anything", technique_ids=[], behaviour_classes=[], platforms=[],
            max_results=5,
        )
        self.assertEqual(result["category"], "mitre_attack_unavailable")
        self.assertEqual(result["rows"], [])
        self.assertFalse(result["fallback"])
        self.assertIn("could not be reached", result["scope"]["note"])
        self.assertIn("no local copy", result["scope"]["note"])

    def test_status_reports_unavailable(self) -> None:
        status = knowledge_status()
        self.assertFalse(status["available"])
        self.assertIn("reason", status)


class CanonicalKnowledgeTests(unittest.TestCase):
    def configure(self, *responses: HttpResponse, output_bytes: int = 1_048_576):
        transport = SimpleNamespace(request=AsyncMock(side_effect=list(responses)))
        credential = SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline", expires_on=2**31)))
        config = ConnectorConfig("https://fake-search.search.windows.net",
                                 ResourceAddress({"index": "mitre-attack-test"}),
                                 ("fake-search.search.windows.net",))
        policy = Policy("offline", grants={"query", "read"}, max_concurrency=1,
                        limits=Limits(max_attempts=1, max_output_bytes=output_bytes))
        knowledge_search.configure(config, credential=credential, policy=policy, transport=transport)
        self.addCleanup(knowledge_search.reset_client)
        return transport

    def test_canonical_blank_query_filter_insertion_order_and_ties(self):
        from app.cybereye.tests.fake_search import FROZEN_KNOWLEDGE_HITS

        transport = self.configure(HttpResponse(200, {"value": []}), HttpResponse(200, {"value": []}),
                                   HttpResponse(200, {"value": list(FROZEN_KNOWLEDGE_HITS)}))
        hits, relaxed, expression = knowledge_search.retrieve(
            doc_kind="analytic", query="  ", terms={"technique_ids": ["T9999"],
            "behaviour_class": ["missing"], "platforms": [" "]}, top=2)
        self.assertEqual([row["doc_id"] for row in hits], ["Z2", "A1"])
        self.assertIsNone(hits[0]["title"])
        self.assertNotIn("title", hits[1])
        self.assertEqual(relaxed, ["technique_ids", "behaviour_class"])
        self.assertEqual(expression, "doc_kind eq 'analytic'")
        bodies = [call.args[0].body for call in transport.request.call_args_list]
        self.assertEqual([body["filter"] for body in bodies], [
            "doc_kind eq 'analytic' and technique_ids/any(v: search.in(v, 'T9999', ',')) and behaviour_class/any(v: search.in(v, 'missing', ','))",
            "doc_kind eq 'analytic' and behaviour_class/any(v: search.in(v, 'missing', ','))",
            "doc_kind eq 'analytic'",
        ])
        for body in bodies:
            self.assertEqual(body["search"], "*")
            self.assertEqual(body["select"], ",".join(knowledge_search.SELECT))
            self.assertEqual(body["top"], 2)

    def test_canonical_empty_only_relaxes_terms_that_render_a_filter(self):
        transport = self.configure(HttpResponse(200, {"value": []}))
        hits, relaxed, expression = knowledge_search.retrieve(
            doc_kind="analytic", query="", terms={"platforms": [" ", ""]}, top=1)
        self.assertEqual((hits, relaxed, expression), ([], [], "doc_kind eq 'analytic'"))
        self.assertEqual(transport.request.call_count, 1)

    def test_canonical_failure_and_byte_loss_never_relax(self):
        for response in (HttpResponse(403), HttpResponse(200, {"value": [{"id": "one", "body": "x" * 1000}]})):
            with self.subTest(status=response.status):
                transport = self.configure(response, output_bytes=256)
                with self.assertRaises(knowledge_search.KnowledgeUnavailable):
                    knowledge_search.retrieve(doc_kind="analytic", query="x",
                                              terms={"technique_ids": ["T9999"]}, top=1)
                self.assertEqual(transport.request.call_count, 1)


class BehaviourClassWiringTests(unittest.TestCase):
    def test_every_rule_declares_its_anchored_behaviour_class(self) -> None:
        self.assertEqual({rule.rule_id: rule.behaviour_class for rule in registry()},
                         BEHAVIOUR_BY_RULE)

    def test_behaviour_class_reaches_a_situation_factor(self) -> None:
        rule = next(item for item in registry() if item.rule_id == "fixed_interval_dns")
        factor = _hit(rule, {
            "host": "10.0.128.50", "principal": "unattributed", "event_count": 72,
            "first_seen": "2026-08-13T02:30:00Z", "last_seen": "2026-08-13T03:40:00Z",
            "evidence_ids": ["r1", "r2"],
        })
        self.assertIsNotNone(factor)
        self.assertEqual(factor.behaviour_class, "beaconing")

    def test_registered_agent_spec_exposes_the_tool_before_the_fallback(self) -> None:
        spec = load_agent_spec()
        names = [tool.metadata.name for tool in spec.tools]
        self.assertIn("search_mitre_attack", names)
        self.assertNotIn("search_knowledge_base_local", names)
        self.assertLess(names.index("search_mitre_attack"), names.index("query_events_kql"))
        tool = next(item for item in spec.tools
                    if item.metadata.name == "search_mitre_attack")
        self.assertEqual(tool.display_name, "Search MITRE ATT&CK knowledge")
        self.assertFalse(tool.metadata.fallback)
        self.assertEqual(
            tool.openai_schema()["parameters"]["required"],
            ["question", "technique_ids", "behaviour_classes", "platforms", "max_results"],
        )
        self.assertIn("search_mitre_attack", spec.instructions)


if __name__ == "__main__":
    unittest.main()
