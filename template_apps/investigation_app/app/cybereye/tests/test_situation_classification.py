"""Situation-type retrieval, symptom-query assembly, and enforced classification shape."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from app.cybereye.backend.knowledge import classification, search as knowledge_search
from app.cybereye.backend.agents.config import load_agent_spec
from app.cybereye.backend.agents.editor import AgentEditor
from app.cybereye.backend.knowledge.classification import (
    build_model_input, build_symptom_query, classify, parse_model_output,
)
from app.cybereye.backend.models import Pattern, Situation
from app.cybereye.backend.knowledge import situation_types
from app.cybereye.backend.knowledge.situation_types import (
    classification_status, search_situation_types,
)
from app.cybereye.tests.fake_search import FakeSearchIndexClient, install_fake_index
from app.cybereye.backend.security import Principal

MODEL = "gpt-5.6-luna"
FIRST = datetime(2026, 8, 13, 2, 30, tzinfo=timezone.utc)
LAST = datetime(2026, 8, 13, 3, 40, tzinfo=timezone.utc)


def situation_type(**overrides: Any) -> dict[str, Any]:
    base = {
        "type_id": "guardsight:000000000001", "source": "guardsight",
        "doc_type": "situation_type", "label": "OS Credential Dumping",
        "family": "Credential Access",
        "definition": "GuardSight CIRT battle card GSPBC-1024 covering Credential Access.",
        "symptoms": ["Identify unexpected processes interacting with lsass.exe",
                     "Monitor processes and command-line arguments for credential dumping"],
        "response_phases": {"identification": "Monitor processes and command-line arguments"},
        "technique_ids": ["T1003"], "behaviour_class": ["credential_use"],
        "keywords": ["access", "credential", "dumping"],
        "path": "cyber_kb/raw/sources/x/GSPBC-1024.md", "native_id": "GSPBC-1024",
        "commit": "a" * 40, "license": "MIT", "retrieved_at": "2026-08-29T16:29:25Z",
        "source_fields": {},
    }
    base.update(overrides)
    return base


CORPUS = [
    situation_type(),
    situation_type(
        type_id="guardsight:000000000002", label="Password Policy Discovery",
        family="Discovery",
        definition="GuardSight CIRT battle card GSPBC-1054 covering Discovery.",
        symptoms=["Monitor for LDAP directory enumeration of domain accounts and groups"],
        technique_ids=["T1201"], behaviour_class=["directory_discovery"],
        keywords=["discovery", "password", "policy"], native_id="GSPBC-1054"),
    situation_type(
        type_id="veris:000000000003", source="veris", label="Use of stolen creds",
        family="action.hacking",
        definition="Use of stolen or default authentication credentials.",
        symptoms=[], response_phases={}, technique_ids=[],
        behaviour_class=["credential_use"], keywords=["creds", "stolen"],
        path="cyber_kb/raw/sources/y/verisc-labels.json",
        native_id="action.hacking.variety.Use of stolen creds", license="CC-BY-SA-4.0"),
    situation_type(
        type_id="attack:000000000004", source="attack", label="Credential Access",
        family="attack.tactic",
        definition="The adversary is trying to steal account names and passwords.",
        symptoms=[], response_phases={}, technique_ids=[], behaviour_class=[],
        keywords=["access", "credential"], path="cyber_kb/raw/sources/z/enterprise-attack.json",
        native_id="x-mitre-tactic--2558fd61", license="MITRE ATT&CK terms"),
]


def pattern(**overrides: Any) -> Pattern:
    base = {
        "detector": "cybereye", "rule_id": "explicit_credential_burst",
        "rule_version": "1.0.0", "label": "Explicit credential use",
        "description": "A host and target principal produced at least five Windows event "
                       "4648 records.",
        "observed_fact": "30 event-4648 records for svpmn082 / admLRhodes",
        "count": 30, "score": 35, "confidence": "high", "role": "anchor",
        "behaviour_class": "credential_use", "first_seen": FIRST, "last_seen": LAST,
        "summary": "Explicit credential use observed on one host.",
        "evidence_columns": ["source_time", "resource_id"],
        "evidence_ids": ["r1", "r2"],
        "evidence_semantics": "Up to eight resource IDs sampled from the group.",
        "derivation": {"filters": ['win_event_id == "4648" and isnotempty(target_host_name)']},
    }
    base.update(overrides)
    return Pattern(**base)


def situation(**overrides: Any) -> Situation:
    base = {
        "situation_id": "sit-1", "host": "svpmn082", "principal": "admLRhodes",
        "severity": "critical", "confidence": "high", "first_seen": FIRST,
        "last_seen": LAST, "detector_count": 3,
        "patterns": [
            pattern(),
            pattern(rule_id="tool_url_in_session_title", label="Tool URL in privileged session",
                    behaviour_class="privileged_session", role="anchor", score=30,
                    description="A CyberArk privileged-session record contains a WinPEAS "
                                "reference.",
                    observed_fact="1 CyberArk session record carrying a winPEAS URL",
                    count=1, derivation={}),
            pattern(rule_id="directory_enumeration_alert",
                    label="Directory enumeration alert representation",
                    behaviour_class="directory_discovery", role="corroborator", score=25,
                    confidence="medium",
                    description="A Defender for Identity alert represents LDAP reconnaissance "
                                "mapped to T1087.002.",
                    observed_fact="1 LdapSearchReconnaissance alert naming actors on svpmn082",
                    count=1, derivation={}),
        ],
    }
    base.update(overrides)
    return Situation(**base)


class CorpusFixture(unittest.TestCase):
    """Serve the candidate types from a fake Azure AI Search index, never from disk."""

    documents: list[dict[str, Any]] = CORPUS

    def setUp(self) -> None:
        self.client = install_fake_index(self, self.documents)


class SymptomQueryTests(unittest.TestCase):
    def test_assembly_is_pure_deterministic_and_ordered_by_rule_id(self) -> None:
        first = build_symptom_query(situation())
        self.assertEqual(first, build_symptom_query(situation()))
        self.assertEqual(first.signs[0].split(":")[0],
                         "Directory enumeration alert representation")
        self.assertEqual(first.behaviour_classes,
                         ("credential_use", "directory_discovery", "privileged_session"))

    def test_technique_and_event_ids_are_lifted_from_factor_text_only(self) -> None:
        query = build_symptom_query(situation())
        self.assertEqual(query.technique_ids, ("T1087.002",))
        self.assertEqual(query.event_ids, ("4648",))

    def test_entity_shape_names_the_convention_without_claiming_authorisation(self) -> None:
        shape = build_symptom_query(situation()).entity_shape
        self.assertEqual(shape[0], "one named host")
        self.assertIn("administrative naming convention", shape[1])
        self.assertIn("not an authorisation fact", shape[1])

    def test_unattributed_entities_are_described_as_such(self) -> None:
        shape = build_symptom_query(
            situation(host="unattributed", principal="unattributed"),
        ).entity_shape
        self.assertEqual(shape, ("host is unattributed", "principal is unattributed"))

    def test_query_text_carries_signs_behaviours_techniques_and_events(self) -> None:
        text = build_symptom_query(situation()).text
        self.assertIn("Explicit credential use: 30 event-4648 records", text)
        self.assertIn("behaviour class privileged_session", text)
        self.assertIn("ATT&CK T1087.002", text)
        self.assertIn("Windows event 4648", text)
        self.assertLessEqual(len(text), classification.MAX_QUERY_CHARS)


class RetrievalTests(CorpusFixture):
    def test_canonical_situation_retrieval_preserves_kind_projection_and_citation(self) -> None:
        from unittest.mock import AsyncMock, Mock
        from azdata import ConnectorConfig, HttpResponse, Limits, Policy, ResourceAddress
        from knowledge_documents import build_document

        hit = dict(build_document(CORPUS[0]), **{"@search.score": 1.25})
        transport = SimpleNamespace(request=AsyncMock(return_value=HttpResponse(200, {"value": [hit]})))
        config = ConnectorConfig("https://fake-search.search.windows.net",
                                 ResourceAddress({"index": "mitre-attack-test"}), ("fake-search.search.windows.net",))
        credential = SimpleNamespace(get_token=Mock(return_value=SimpleNamespace(token="offline", expires_on=2**31)))
        knowledge_search.configure(config, credential=credential, transport=transport,
                                   policy=Policy("offline", max_concurrency=1, limits=Limits(max_attempts=1)))
        result = search_situation_types(query="credential", max_results=1)
        self.assertEqual(result["rows"][0]["type_id"], "guardsight:000000000001")
        self.assertEqual(result["rows"][0]["path"], "cyber_kb/raw/sources/x/GSPBC-1024.md")
        self.assertEqual(result["rows"][0]["commit"], "a" * 12)
        body = transport.request.call_args.args[0].body
        self.assertEqual(body["filter"], "doc_kind eq 'situation_type'")
        self.assertEqual(body["select"], ",".join(knowledge_search.SELECT))
        self.assertEqual(body["top"], 1)

    def test_returns_a_bounded_cited_envelope(self) -> None:
        result = search_situation_types(query="credential dumping lsass")
        self.assertEqual(result["kind"], "cybereye_situation_types")
        self.assertEqual(result["category"], "situation_types")
        self.assertTrue(result["historical_replay"])
        self.assertEqual(result["scope"]["retrieval"], "azure-ai-search")
        self.assertEqual(result["rows"][0]["type_id"], "guardsight:000000000001")
        self.assertEqual(sorted(result["rows"][0]), sorted(situation_types.COLUMNS))

    def test_every_answer_is_one_network_call_to_the_configured_index(self) -> None:
        self.client.calls.clear()
        search_situation_types(query="credential dumping lsass")
        self.assertEqual([call["index"] for call in self.client.calls], ["mitre-attack-test"])

    def test_symptom_text_is_part_of_the_ranked_surface(self) -> None:
        result = search_situation_types(query="unexpected processes interacting with lsass.exe")
        self.assertEqual(result["rows"][0]["label"], "OS Credential Dumping")
        self.assertGreater(result["rows"][0]["score"], 0.0)

    def test_exact_filters_are_pushed_into_the_index_filter(self) -> None:
        result = search_situation_types(query="", technique_ids=["T1201"])
        self.assertEqual([row["label"] for row in result["rows"]],
                         ["Password Policy Discovery"])
        self.assertIn("technique_ids/any(v: search.in(v, 'T1201', ','))",
                      result["scope"]["index_filter"])
        self.assertIn("doc_kind eq 'situation_type'", result["scope"]["index_filter"])

    def test_over_constrained_filters_relax_and_report_it(self) -> None:
        result = search_situation_types(query="", technique_ids=["T9999"],
                                        behaviour_classes=["credential_use"])
        self.assertEqual(result["scope"]["relaxed_filters"], ["technique_ids"])
        self.assertTrue(result["rows"])
        self.assertTrue(all("credential_use" in row["behaviour_class"]
                            for row in result["rows"]))

    def test_ranking_is_deterministic_and_bounded(self) -> None:
        first = search_situation_types(query="stolen credentials", max_results=2)
        self.assertEqual(first, search_situation_types(query="stolen credentials",
                                                       max_results=2))
        self.assertEqual(len(first["rows"]), 2)
        self.assertLess(len(json.dumps(first).encode("utf-8")),
                        situation_types.MAX_PAYLOAD_BYTES)

    def test_status_reports_the_index_it_reads_and_never_a_local_corpus(self) -> None:
        status = classification_status()
        self.assertTrue(status["available"])
        self.assertEqual(status["documents"], 4)
        self.assertEqual(status["situation_types"], 4)
        self.assertEqual(status["retrieval"], "azure-ai-search")
        self.assertFalse(status["local_fallback"])
        self.assertEqual(status["index"], "mitre-attack-test")

    def test_a_citation_opens_the_document_the_classifier_was_shown(self) -> None:
        row = search_situation_types(query="credential dumping lsass")["rows"][0]
        document = situation_types.get_situation_type(row["type_id"])
        self.assertIsNotNone(document)
        self.assertEqual(document["label"], row["label"])
        self.assertEqual(document["path"], row["path"])
        self.assertEqual(document["commit"], "a" * 40)

    def test_envelope_states_what_a_classification_does_not_establish(self) -> None:
        advisory = search_situation_types(query="")["scope"]["advisory"]
        self.assertIn("not a verdict", advisory)
        self.assertIn("names no actor", advisory)


class StrictJsonTests(CorpusFixture):
    def rows(self) -> list[dict[str, Any]]:
        return search_situation_types(query="credential", max_results=4)["rows"]

    def test_accepts_a_well_formed_choice_and_takes_provenance_from_the_corpus(self) -> None:
        parsed = parse_model_output(json.dumps({
            "situation_type": "OS Credential Dumping", "family": "invented family",
            "confidence": "medium", "basis": ["30 event-4648 records"],
            "alternatives": [{"label": "Use of stolen creds", "why_not": "no reuse observed"}],
            "not_established": ["no execution observed"],
        }), self.rows())
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["chosen"]["family"], "Credential Access")
        self.assertEqual(parsed["alternatives"],
                         [{"label": "Use of stolen creds", "why_not": "no reuse observed"}])
        self.assertIn(classification._NOT_ESTABLISHED_FLOOR, parsed["not_established"])

    def test_strips_a_markdown_fence_the_model_should_not_have_sent(self) -> None:
        parsed = parse_model_output(
            '```json\n{"situation_type": "Credential Access", "confidence": "low", '
            '"basis": [], "alternatives": [], "not_established": []}\n```', self.rows())
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["chosen"]["label"], "Credential Access")

    def test_rejects_a_type_that_was_not_retrieved(self) -> None:
        self.assertIsNone(parse_model_output(json.dumps({
            "situation_type": "Ransomware", "confidence": "high", "basis": [],
            "alternatives": [], "not_established": [],
        }), self.rows()))

    def test_rejects_prose_and_non_object_json(self) -> None:
        self.assertIsNone(parse_model_output("This looks like credential theft.", self.rows()))
        self.assertIsNone(parse_model_output("[]", self.rows()))
        self.assertIsNone(parse_model_output("", self.rows()))

    def test_rejects_an_out_of_vocabulary_confidence(self) -> None:
        self.assertIsNone(parse_model_output(json.dumps({
            "situation_type": "OS Credential Dumping", "confidence": "certain",
            "basis": [], "alternatives": [], "not_established": [],
        }), self.rows()))

    def test_drops_alternatives_that_are_not_candidates_or_repeat_the_choice(self) -> None:
        parsed = parse_model_output(json.dumps({
            "situation_type": "OS Credential Dumping", "confidence": "low", "basis": [],
            "alternatives": [{"label": "OS Credential Dumping", "why_not": "same"},
                             {"label": "Nation State Intrusion", "why_not": "invented"},
                             {"label": "Credential Access", "why_not": "too coarse"}],
            "not_established": [],
        }), self.rows())
        assert parsed is not None
        self.assertEqual([item["label"] for item in parsed["alternatives"]],
                         ["Credential Access"])

    def test_caps_basis_and_not_established_lengths(self) -> None:
        parsed = parse_model_output(json.dumps({
            "situation_type": "OS Credential Dumping", "confidence": "low",
            "basis": [f"reason {index}" for index in range(9)],
            "alternatives": [], "not_established": ["x" * 500],
        }), self.rows())
        assert parsed is not None
        self.assertEqual(len(parsed["basis"]), classification.MAX_BASIS)
        self.assertEqual(len(parsed["not_established"][0]), classification.MAX_STRING_CHARS)


class ClassifyTests(CorpusFixture):
    def test_end_to_end_choice_is_cited_bounded_and_serialisable(self) -> None:
        captured: dict[str, str] = {}

        def invoke(payload: str) -> str:
            captured["payload"] = payload
            return json.dumps({
                "situation_type": "OS Credential Dumping", "confidence": "medium",
                "basis": ["30 event-4648 records for svpmn082 / admLRhodes"],
                "alternatives": [{"label": "Use of stolen creds", "why_not": "no reuse shown"}],
                "not_established": ["no execution or authorisation is established"],
            })

        result = classify(situation(), invoke, model=MODEL)
        self.assertEqual(result["situation_id"], "sit-1")
        self.assertEqual(result["situation_type"], "OS Credential Dumping")
        self.assertEqual(result["family"], "Credential Access")
        self.assertEqual(result["confidence"], "medium")
        # The tactic row carries no behaviour class, so the situation's behaviour filter
        # legitimately keeps it out of the shortlist.
        self.assertEqual(result["candidates_considered"], 3)
        self.assertEqual(result["model"], MODEL)
        self.assertTrue(result["historical_replay"])
        self.assertNotIn("error", result)
        self.assertEqual(result["citations"][0],
                         {"type_id": "guardsight:000000000001",
                          "label": "OS Credential Dumping", "source": "guardsight",
                          "path": "cyber_kb/raw/sources/x/GSPBC-1024.md",
                          "commit": "a" * 12})
        self.assertEqual([item["label"] for item in result["citations"]],
                         ["OS Credential Dumping", "Use of stolen creds"])
        self.assertEqual(sorted(result), sorted([
            "situation_id", "situation_type", "family", "confidence", "basis", "citations",
            "alternatives", "not_established", "candidates_considered", "model",
            "elapsed_ms", "historical_replay"]))
        self.assertEqual(json.loads(json.dumps(jsonable_encoder(result))), result)
        self.assertIn("CANDIDATE SITUATION TYPES", captured["payload"])

    def test_malformed_model_output_returns_an_envelope_and_never_raises(self) -> None:
        result = classify(situation(), lambda payload: "I think this is ransomware.",
                          model=MODEL)
        self.assertEqual(result["error"], "unparseable_model_output")
        self.assertEqual(result["situation_type"], "")
        self.assertEqual(result["confidence"], "low")
        self.assertEqual(result["candidates_considered"], 3)
        self.assertTrue(result["citations"])
        self.assertEqual(result["not_established"], [classification._NOT_ESTABLISHED_FLOOR])
        self.assertTrue(result["historical_replay"])

    def test_the_model_is_called_exactly_once(self) -> None:
        calls: list[str] = []

        def invoke(payload: str) -> str:
            calls.append(payload)
            return json.dumps({"situation_type": "OS Credential Dumping", "confidence": "low",
                               "basis": [], "alternatives": [], "not_established": []})

        classify(situation(), invoke, model=MODEL)
        self.assertEqual(len(calls), 1)

    def test_prompt_carries_the_situation_the_query_and_every_candidate(self) -> None:
        query = build_symptom_query(situation())
        rows = search_situation_types(query=query.text, max_results=4)["rows"]
        payload = build_model_input(situation(), query, rows)
        self.assertIn("SITUATION ENVELOPE", payload)
        self.assertIn("DERIVED SIGNS AND SYMPTOMS", payload)
        for row in rows:
            self.assertIn(row["label"], payload)
        self.assertIn("(this source lists none)", payload)


class EndpointContractTests(CorpusFixture):
    caller = Principal("local:workstation", issuer="local-preview")

    def editor(self) -> AgentEditor:
        directory = self.enterContext(tempfile.TemporaryDirectory())
        return AgentEditor(Path(directory), load_agent_spec())

    def call(self, agent: Any) -> dict[str, Any]:
        from app.cybereye.backend.api import situations

        state = SimpleNamespace(agent=agent, agent_editor=self.editor(), adx=SimpleNamespace(
            health=lambda: {"reachable": True}))
        request = SimpleNamespace(app=SimpleNamespace(state=state))
        return asyncio.run(situations.situation_classify(situation(), request, self.caller))  # type: ignore[arg-type]

    def test_route_is_registered_for_post_only(self) -> None:
        from app.cybereye.backend import main

        route = next(item for item in main.app.routes
                     if getattr(item, "path", "") == "/api/cyber/situations/classify")
        self.assertEqual(sorted(route.methods), ["POST"])

    def test_endpoint_returns_a_json_serialisable_envelope(self) -> None:
        agent = SimpleNamespace(classify_situation=lambda body: classify(
            body,
            lambda payload: json.dumps({"situation_type": "OS Credential Dumping",
                                        "confidence": "low", "basis": ["30 event-4648 records"],
                                        "alternatives": [], "not_established": []}),
            model=MODEL,
        ))
        result = self.call(agent)
        self.assertEqual(result["situation_type"], "OS Credential Dumping")
        self.assertEqual(json.loads(json.dumps(jsonable_encoder(result))), result)

    def test_transport_failure_becomes_a_502_rather_than_a_silent_envelope(self) -> None:
        def explode(body: Situation) -> dict[str, Any]:
            raise RuntimeError("connection reset")

        with self.assertRaises(HTTPException) as caught:
            self.call(SimpleNamespace(classify_situation=explode))
        self.assertEqual(caught.exception.status_code, 502)
        self.assertIn("situation classification failed", str(caught.exception.detail))

    def test_health_agent_block_carries_the_classification_kb_sub_block(self) -> None:
        from app.cybereye.backend.api import health as health_route

        state = SimpleNamespace(
            adx=SimpleNamespace(health=lambda: {"reachable": True}),
            agent=SimpleNamespace(spec=load_agent_spec()),
            agent_editor=self.editor(),
        )
        request = SimpleNamespace(app=SimpleNamespace(state=state))
        report = asyncio.run(health_route.health(request, self.caller))  # type: ignore[arg-type]
        block = report["agent"]["classification_kb"]
        self.assertTrue(block["available"])
        self.assertEqual(block["documents"], 4)
        self.assertEqual(block["index"], "mitre-attack-test")
        self.assertFalse(block["local_fallback"])
        self.assertIn("knowledge_base", report["agent"])


class UnreachableIndexTests(CorpusFixture):
    """The index is configured but the network is not there. Nothing answers from disk."""

    def setUp(self) -> None:
        super().setUp()
        self.client.offline = True

    def test_an_unreachable_index_returns_a_bounded_envelope_not_an_exception(self) -> None:
        result = search_situation_types(query="anything")
        self.assertEqual(result["category"], "situation_types_unavailable")
        self.assertEqual(result["rows"], [])
        self.assertIn("could not be reached", result["scope"]["note"])
        self.assertIn("no local", result["scope"]["note"])

    def test_classify_reports_the_unreachable_index_without_calling_the_model(self) -> None:
        def invoke(payload: str) -> str:
            raise AssertionError("the model must not be called without candidates")

        result = classify(situation(), invoke, model=MODEL)
        self.assertEqual(result["error"], "classification_corpus_unavailable")
        self.assertEqual(result["candidates_considered"], 0)
        self.assertIn("could not be reached", result["detail"])
        self.assertTrue(result["historical_replay"])

    def test_status_reports_unavailable_and_names_no_build_command(self) -> None:
        status = classification_status()
        self.assertFalse(status["available"])
        self.assertNotIn("build_command", status)
        self.assertIn("reason", status)


class UnconfiguredIndexTests(unittest.TestCase):
    def setUp(self) -> None:
        previous = {key: os.environ.get(key) for key in
                    ("CYBEREYE_SEARCH_ENDPOINT", "CYBEREYE_MITRE_SEARCH_INDEX")}
        os.environ["CYBEREYE_SEARCH_ENDPOINT"] = ""
        os.environ["CYBEREYE_MITRE_SEARCH_INDEX"] = ""
        knowledge_search.reset_client()

        def restore() -> None:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            knowledge_search.reset_client()

        self.addCleanup(restore)

    def test_an_unconfigured_index_never_falls_back_to_a_local_corpus(self) -> None:
        result = search_situation_types(query="credential dumping")
        self.assertEqual(result["category"], "situation_types_unavailable")
        self.assertEqual(result["rows"], [])
        self.assertIn("not configured", result["scope"]["note"])


if __name__ == "__main__":
    unittest.main()
