"""Contract tests for the diagnosis sink tool and the diagnosis run.

The model is never called: `stream_turn` is replaced with scripted async generators.
"""

from __future__ import annotations

import json
import unittest
from collections.abc import AsyncIterator
from typing import Any
from unittest import mock

from app.cybereye.backend.agents.service import (
    AgentService, DIAGNOSIS_TOOL, SEQUENCE_STEP_TOOL, SEQUENCE_TOOL,
)
from app.cybereye.backend.agents.tools.base import metadata
from app.cybereye.backend.agents.tools.diagnosis import (
    ASSESSMENTS, EvidenceLedger, complete_sequence_of_events, index_knowledge_rows,
    record_sequence_step, record_situation_diagnosis, resolve_citations,
)
from app.cybereye.tests.test_situation_classification import situation as situation_fixture

GOOD = {
    "headline": "A privileged account ran directory reconnaissance against svpmn082.",
    "narrative": "Explicit-credential logons preceded LDAP enumeration on the same host and account. "
                 "The sequence is consistent with post-access discovery in this replay window.",
    "assessment": "suspicious_requires_review",
    "confidence": "medium",
    "supporting_observations": ["24 Windows 4648 records counted for admLRhodes on svpmn082."],
    "would_change_the_call": ["A change ticket covering the enumeration would explain it."],
    "evidence_ids": ["event://priv:scwx.auth:1", "event://priv:scwx.auth:1", " "],
    "situation_type": "Account Discovery: Domain Account",
    "citation_ids": ["attack:aaa111", "attack:aaa111", " "],
}

GOOD_STEPS = [
    {"position": 1,
     "description": "admLRhodes signed in to svpmn082 with explicit credentials.",
     "timestamp": "2024-03-02T11:04:00Z",
     "evidence_ids": ["event://priv:scwx.auth:1", " ", "event://priv:scwx.auth:1"]},
    {"position": 2,
     "description": "The same account enumerated domain accounts from that host.",
     "timestamp": "", "evidence_ids": []},
]
ORDERING_NOTE = "The second step carries no timestamp, so its position rests on the session id alone."

#: One real telemetry envelope, shaped exactly as `query_envelope` returns it.
EVIDENCE_RESULT = {
    "kind": "cybereye_tool_result", "tool": "get_situation_evidence",
    "category": "cited_evidence",
    "scope": {"situation_id": "sit-1", "row_count": 1},
    "columns": ["source_time", "resource_id", "target_user_name"],
    "rows": [{"source_time": "2024-03-02T11:04:00Z", "resource_id": "event://priv:scwx.auth:1",
              "target_user_name": "admLRhodes", "service_name": ""}],
    "truncated": False, "historical_replay": True, "fallback": False,
}

KNOWLEDGE_RESULT = {
    "category": "mitre_attack",
    "rows": [
        {"doc_id": "attack:aaa111", "source": "mitre-attack",
         "title": "Account Discovery: Domain Account", "path": "attack/T1087.002.json",
         "commit": "abc123def456"},
        {"doc_id": "attack:bbb222", "source": "mitre-attack", "title": "Remote System Discovery",
         "path": "attack/T1018.json", "commit": "abc123def456"},
    ],
}


class DiagnosisToolTests(unittest.TestCase):
    def test_schema_is_strict_closed_and_requires_every_field(self) -> None:
        schema = metadata(record_situation_diagnosis).openai_schema()
        self.assertTrue(schema["strict"])
        self.assertFalse(schema["parameters"]["additionalProperties"])
        self.assertEqual(
            sorted(schema["parameters"]["required"]),
            sorted(schema["parameters"]["properties"]),
        )
        self.assertEqual(schema["parameters"]["properties"]["assessment"]["enum"], list(ASSESSMENTS))

    def test_result_is_bounded_deduplicated_and_marked_historical(self) -> None:
        payload = dict(GOOD)
        payload["supporting_observations"] = [f"observation {index}" for index in range(9)]
        payload["would_change_the_call"] = [f"gap {index}" for index in range(7)]
        result = record_situation_diagnosis(mock.Mock(), **payload)
        self.assertEqual(len(result["supporting_observations"]), 6)
        self.assertEqual(len(result["would_change_the_call"]), 4)
        self.assertEqual(result["evidence_ids"], ["event://priv:scwx.auth:1"])
        self.assertTrue(result["historical_replay"])
        self.assertFalse(result["fallback"])
        self.assertEqual(result["category"], "situation_diagnosis")

    def test_out_of_vocabulary_assessment_or_confidence_is_rejected(self) -> None:
        for field, value in [("assessment", "confirmed_breach"), ("confidence", "certain")]:
            with self.assertRaises(ValueError):
                record_situation_diagnosis(mock.Mock(), **{**GOOD, field: value})

    def test_citation_ids_are_deduplicated_and_the_type_is_carried(self) -> None:
        result = record_situation_diagnosis(mock.Mock(), **GOOD)
        self.assertEqual(result["citation_ids"], ["attack:aaa111"])
        self.assertEqual(result["situation_type"], GOOD["situation_type"])


class CitationResolutionTests(unittest.TestCase):
    def test_only_rows_this_run_returned_become_citations(self) -> None:
        index = index_knowledge_rows(KNOWLEDGE_RESULT)
        citations, unsupported, supported = resolve_citations(
            index, "Account Discovery: Domain Account", ["attack:aaa111", "attack:invented"],
        )
        self.assertEqual([cite["type_id"] for cite in citations], ["attack:aaa111"])
        self.assertEqual(citations[0]["path"], "attack/T1087.002.json")
        self.assertEqual(unsupported, ["attack:invented"])
        self.assertTrue(supported)

    def test_a_type_no_returned_row_carries_is_flagged(self) -> None:
        index = index_knowledge_rows(KNOWLEDGE_RESULT)
        _, _, supported = resolve_citations(index, "Something Invented", ["attack:bbb222"])
        self.assertFalse(supported)

    def test_a_non_knowledge_result_indexes_nothing(self) -> None:
        self.assertEqual(index_knowledge_rows({"category": "cited_evidence", "rows": [{"doc_id": "x"}]}), {})


class SequenceToolTests(unittest.TestCase):
    def test_the_step_schema_is_strict_closed_and_bounds_the_position(self) -> None:
        schema = metadata(record_sequence_step).openai_schema()
        self.assertTrue(schema["strict"])
        self.assertFalse(schema["parameters"]["additionalProperties"])
        self.assertEqual(
            sorted(schema["parameters"]["required"]),
            ["description", "evidence_ids", "position", "timestamp"],
        )
        self.assertEqual(schema["parameters"]["properties"]["position"]["maximum"], 10)
        self.assertEqual(schema["parameters"]["properties"]["evidence_ids"]["maxItems"], 4)

    def test_one_step_carries_its_own_position_and_deduplicated_evidence(self) -> None:
        result = record_sequence_step(mock.Mock(), **GOOD_STEPS[0])
        self.assertEqual(result["position"], 1)
        self.assertEqual(result["evidence_ids"], ["event://priv:scwx.auth:1"])
        self.assertEqual(result["category"], "sequence_step")
        self.assertTrue(result["historical_replay"])

    def test_a_blank_or_out_of_range_step_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            record_sequence_step(mock.Mock(), position=1, description="   ", timestamp="",
                                 evidence_ids=[])
        with self.assertRaises(ValueError):
            record_sequence_step(mock.Mock(), position=99, description="a real step line",
                                 timestamp="", evidence_ids=[])

    def test_the_closing_call_carries_only_the_ordering_note(self) -> None:
        schema = metadata(complete_sequence_of_events).openai_schema()
        self.assertEqual(schema["parameters"]["required"], ["ordering_note"])
        result = complete_sequence_of_events(mock.Mock(), ordering_note=ORDERING_NOTE)
        self.assertEqual(result["ordering_note"], ORDERING_NOTE)
        self.assertEqual(result["category"], "sequence_of_events")


class EvidenceLedgerTests(unittest.TestCase):
    def ledger(self) -> EvidenceLedger:
        ledger = EvidenceLedger()
        ledger.note_call("call-1", {"situation_id": "sit-1", "start": "2024-03-02T11:00:00Z",
                                    "end": "2024-03-02T12:00:00Z"})
        ledger.record("call-1", "get_situation_evidence", "Situation evidence", EVIDENCE_RESULT)
        return ledger

    def test_a_returned_row_resolves_to_its_record_and_its_real_provenance(self) -> None:
        resolved, unsupported = self.ledger().resolve(["event://priv:scwx.auth:1"])
        self.assertEqual(unsupported, [])
        self.assertEqual(len(resolved), 1)
        entry = resolved[0]
        self.assertEqual(entry["evidence_id"], "event://priv:scwx.auth:1")
        self.assertEqual(entry["record"]["target_user_name"], "admLRhodes")
        # Empty columns are dropped rather than shown as blank fields.
        self.assertNotIn("service_name", entry["record"])
        retrieval = entry["retrieval"]
        self.assertEqual(retrieval["tool"], "get_situation_evidence")
        self.assertEqual(retrieval["display_name"], "Situation evidence")
        self.assertIn("Azure Data Explorer table", retrieval["datasource"])
        self.assertIn("situation_id=sit-1", retrieval["query"])
        self.assertEqual(retrieval["row_count"], 1)
        self.assertTrue(retrieval["retrieved_at"].endswith("+00:00"))

    def test_an_id_no_tool_returned_is_unsupported_not_invented(self) -> None:
        resolved, unsupported = self.ledger().resolve(
            ["event://priv:scwx.auth:1", "event://never-returned"])
        self.assertEqual([entry["evidence_id"] for entry in resolved],
                         ["event://priv:scwx.auth:1"])
        self.assertEqual(unsupported, ["event://never-returned"])

    def test_a_failed_tool_call_contributes_no_provenance(self) -> None:
        ledger = EvidenceLedger()
        ledger.record("call-9", "get_situation_evidence", "Situation evidence",
                      {"error": "ValueError", "detail": "bad window"})
        self.assertEqual(ledger.retrievals, [])
        self.assertEqual(ledger.resolve(["event://priv:scwx.auth:1"]), ([], ["event://priv:scwx.auth:1"]))

    def test_knowledge_rows_name_the_search_index_and_raw_kql_carries_its_query(self) -> None:
        ledger = EvidenceLedger()
        ledger.record("call-2", "search_mitre_attack", "Search MITRE ATT&CK knowledge",
                      KNOWLEDGE_RESULT)
        resolved, _ = ledger.resolve(["attack:aaa111"])
        self.assertIn("Azure AI Search index", resolved[0]["retrieval"]["datasource"])
        ledger.note_call("call-3", {"query": "EventsUnified\n| take 1"})
        ledger.record("call-3", "query_events_kql", "Query EventsUnified (KQL fallback)",
                      {"category": "raw_kql", "rows": [{"resource_id": "event://raw:1"}]})
        resolved, _ = ledger.resolve(["event://raw:1"])
        self.assertEqual(resolved[0]["retrieval"]["query"], "EventsUnified | take 1")


def service_with(script) -> AgentService:
    service = AgentService.__new__(AgentService)
    service.spec = mock.Mock(
        model="test-model", diagnosis_max_tool_iterations=10, diagnosis_max_output_tokens=2600,
    )
    service.tools = {}
    service.stream_turn = script  # type: ignore[method-assign]
    return service


async def collect(service: AgentService, situation: Any) -> list[tuple[str, dict[str, Any]]]:
    return [item async for item in service.diagnose_situation(situation, principal="owner")]


class DiagnosisRunTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.situation = situation_fixture()

    async def test_the_run_uses_the_longer_diagnosis_budget(self) -> None:
        seen: dict[str, Any] = {}

        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            seen.update(kwargs)
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}

        await collect(service_with(script), self.situation)
        self.assertEqual(seen["max_output_tokens"], 2600)
        self.assertEqual(seen["principal"], "owner")
        self.assertNotIn("previous_response_id", seen)
        self.assertIn("Never invent hosts", seen["instructions"])
        self.assertIn("ordered sequence", seen["instructions"])
        self.assertIn("search_mitre_attack", seen["instructions"])
        self.assertIn(SEQUENCE_STEP_TOOL, seen["instructions"])
        self.assertIn(SEQUENCE_TOOL, seen["instructions"])

    async def test_each_step_is_pushed_separately_with_server_resolved_provenance(self) -> None:
        after = []

        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "status", {"label": "Connecting…"}
            yield "tool_call_start", {"id": "1", "name": "get_situation_evidence", "display_name": "Situation evidence"}
            yield "tool_call_end", {"id": "1", "name": "get_situation_evidence",
                                   "arguments": {"situation_id": "sit-1"}}
            yield "tool_result", {"id": "1", "name": "get_situation_evidence", "result": EVIDENCE_RESULT}
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}
            for step in GOOD_STEPS:
                yield "tool_result", {"name": SEQUENCE_STEP_TOOL,
                                      "result": record_sequence_step(mock.Mock(), **step)}
            yield "tool_result", {"name": SEQUENCE_TOOL, "result": complete_sequence_of_events(
                mock.Mock(), ordering_note=ORDERING_NOTE)}
            yield "status", {"phase": "model", "label": "Reasoning from tool evidence…"}
            after.append("continued")
            yield "token", {"token": "should never be reached"}

        events = await collect(service_with(script), self.situation)
        kinds = [event for event, _ in events]
        self.assertEqual(kinds[-1], "done")
        self.assertEqual(kinds.count("sequence"), 1)
        self.assertEqual(kinds.count("sequence_step"), 2)
        self.assertNotIn("token", kinds)
        self.assertEqual(after, ["continued"])
        # Each sink is re-emitted as its own event and *also* settles its own tool card;
        # a call that opened a card and never closed one span forever.
        self.assertEqual(
            [data.get("name") for event, data in events if event == "tool_result"],
            ["get_situation_evidence", DIAGNOSIS_TOOL, SEQUENCE_STEP_TOOL,
             SEQUENCE_STEP_TOOL, SEQUENCE_TOOL],
        )
        first = next(data for event, data in events if event == "sequence_step")
        self.assertEqual(first["position"], 1)
        self.assertEqual(first["situation_id"], self.situation.situation_id)
        self.assertEqual(len(first["evidence"]), 1)
        self.assertEqual(first["evidence"][0]["record"]["target_user_name"], "admLRhodes")
        self.assertEqual(first["evidence"][0]["retrieval"]["tool"], "get_situation_evidence")
        self.assertIn("situation_id=sit-1", first["evidence"][0]["retrieval"]["query"])
        self.assertEqual(first["unsupported_evidence_ids"], [])
        sequence = next(data for event, data in events if event == "sequence")
        self.assertEqual(sequence["situation_id"], self.situation.situation_id)
        self.assertEqual([step["description"] for step in sequence["steps"]],
                         [GOOD_STEPS[0]["description"], GOOD_STEPS[1]["description"]])
        self.assertEqual(sequence["ordering_note"], ORDERING_NOTE)
        self.assertTrue(events[-1][1]["recorded"])
        self.assertTrue(events[-1][1]["sequenced"])

    async def test_a_step_evidence_id_no_tool_returned_is_reported_unsupported(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}
            yield "tool_result", {"name": SEQUENCE_STEP_TOOL, "result": record_sequence_step(
                mock.Mock(), position=1, description="A step resting on an invented id.",
                timestamp="", evidence_ids=["event://never-returned"])}
            yield "tool_result", {"name": SEQUENCE_TOOL, "result": complete_sequence_of_events(
                mock.Mock(), ordering_note="")}

        events = await collect(service_with(script), self.situation)
        step = next(data for event, data in events if event == "sequence_step")
        self.assertEqual(step["evidence"], [])
        self.assertEqual(step["unsupported_evidence_ids"], ["event://never-returned"])
        self.assertEqual(step["description"], "A step resting on an invented id.")

    async def test_recorded_diagnosis_does_not_hide_later_native_failure(self) -> None:
        resumed = []

        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            for call_id, name, result in (("diagnosis", DIAGNOSIS_TOOL, dict(GOOD)),
                                         ("close", SEQUENCE_TOOL, {"ordering_note": ORDERING_NOTE})):
                yield "tool_call_start", {"id": call_id, "name": name}
                yield "tool_result", {"id": call_id, "name": name, "result": result}
            resumed.append(True)
            yield "error", {"error": "agent exceeded 10 tool iterations"}

        events = await collect(service_with(script), self.situation)
        self.assertEqual(resumed, [True])
        self.assertIn("error", [event for event, _ in events])
        self.assertEqual(events[-1][1]["status"], "incomplete")
        self.assertTrue(events[-1][1]["recorded"])
        self.assertTrue(events[-1][1]["sequenced"])

    async def test_native_run_settles_siblings_and_preserves_late_failure(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}
            for call_id, name in (("close", SEQUENCE_TOOL), ("step", SEQUENCE_STEP_TOOL),
                                  ("sibling", "get_situation_evidence")):
                yield "tool_call_start", {"id": call_id, "name": name}
            yield "tool_result", {"id": "close", "name": SEQUENCE_TOOL,
                                  "result": {"ordering_note": ORDERING_NOTE}}
            yield "tool_result", {"id": "step", "name": SEQUENCE_STEP_TOOL,
                                  "result": record_sequence_step(mock.Mock(), **GOOD_STEPS[0])}
            yield "tool_result", {"id": "sibling", "name": "get_situation_evidence",
                                  "result": {"error": "ValueError", "detail": "fixture refusal"}}
            yield "error", {"error": "agent exceeded 10 tool iterations"}

        events = await collect(service_with(script), self.situation)
        self.assertEqual([data["id"] for event, data in events
                          if event == "tool_result" and "id" in data], ["close", "step", "sibling"])
        sequences = [data for event, data in events if event == "sequence"]
        self.assertEqual(len(sequences), 1)
        self.assertEqual(len(sequences[0]["steps"]), 1)
        self.assertEqual(sequences[0]["ordering_note"], ORDERING_NOTE)
        self.assertIn("error", [event for event, _ in events])
        self.assertEqual(events[-1][1]["status"], "incomplete")

    async def test_limit_error_remains_when_the_sequence_never_completes(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}
            yield "tool_result", {"name": SEQUENCE_TOOL, "result": {"error": "failed"}}
            yield "error", {"error": "agent exceeded 10 tool iterations"}

        events = await collect(service_with(script), self.situation)
        self.assertIn(("error", {"error": "agent exceeded 10 tool iterations"}), events)
        self.assertFalse(events[-1][1]["sequenced"])

    async def test_steps_without_the_closing_call_still_reach_the_reader(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}
            yield "tool_result", {"name": SEQUENCE_STEP_TOOL,
                                  "result": record_sequence_step(mock.Mock(), **GOOD_STEPS[0])}
            yield "done", {}

        events = await collect(service_with(script), self.situation)
        sequence = next(data for event, data in events if event == "sequence")
        self.assertEqual(len(sequence["steps"]), 1)
        self.assertEqual(sequence["ordering_note"], "")
        self.assertTrue(events[-1][1]["sequenced"])

    async def test_a_run_that_records_no_sequence_still_delivers_the_diagnosis(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}
            yield "done", {}

        events = await collect(service_with(script), self.situation)
        kinds = [event for event, _ in events]
        self.assertIn("diagnosis", kinds)
        self.assertNotIn("sequence", kinds)
        self.assertTrue(events[-1][1]["recorded"])
        self.assertFalse(events[-1][1]["sequenced"])

    async def test_a_failed_sequence_call_does_not_end_the_run_or_emit_a_sequence(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}
            yield "tool_result", {"name": SEQUENCE_STEP_TOOL, "result": {"error": "ValueError", "detail": "blank step"}}
            yield "tool_result", {"name": SEQUENCE_TOOL, "result": {"error": "ValueError", "detail": "no steps"}}
            yield "tool_result", {"name": SEQUENCE_STEP_TOOL,
                                  "result": record_sequence_step(mock.Mock(), **GOOD_STEPS[0])}
            yield "tool_result", {"name": SEQUENCE_TOOL, "result": complete_sequence_of_events(
                mock.Mock(), ordering_note=ORDERING_NOTE)}

        events = await collect(service_with(script), self.situation)
        self.assertEqual(len([1 for event, _ in events if event == "sequence"]), 1)
        self.assertEqual(len([1 for event, _ in events if event == "sequence_step"]), 1)
        self.assertTrue(events[-1][1]["sequenced"])

    async def test_citations_are_resolved_only_from_this_run_s_knowledge_rows(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_result", {"name": "search_mitre_attack", "result": KNOWLEDGE_RESULT}
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": {
                **GOOD, "citation_ids": ["attack:aaa111", "attack:never-returned"],
            }}

        events = await collect(service_with(script), self.situation)
        diagnosis = next(data for event, data in events if event == "diagnosis")
        self.assertEqual([cite["type_id"] for cite in diagnosis["citations"]], ["attack:aaa111"])
        self.assertEqual(diagnosis["unsupported_citations"], ["attack:never-returned"])
        self.assertTrue(diagnosis["situation_type_supported"])
        self.assertNotIn("citation_ids", diagnosis)

    async def test_a_type_with_no_supporting_row_is_flagged_not_silently_accepted(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}

        events = await collect(service_with(script), self.situation)
        diagnosis = next(data for event, data in events if event == "diagnosis")
        self.assertFalse(diagnosis["situation_type_supported"])
        self.assertEqual(diagnosis["citations"], [])

    async def test_a_failed_sink_call_does_not_count_as_a_diagnosis(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": {"error": "ValueError", "detail": "bad enum"}}

        events = await collect(service_with(script), self.situation)
        kinds = [event for event, _ in events]
        self.assertNotIn("diagnosis", kinds)
        self.assertEqual(kinds[-2], "error")
        self.assertEqual(events[-1][1]["recorded"], False)

    async def test_a_run_that_never_calls_the_sink_reports_it_rather_than_inventing_one(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "token", {"token": "Here is my prose answer instead."}
            yield "done", {}

        events = await collect(service_with(script), self.situation)
        kinds = [event for event, _ in events]
        self.assertNotIn("diagnosis", kinds)
        errors = [data for event, data in events if event == "error"]
        self.assertEqual(errors[-1]["error"], "diagnosis_not_recorded")

    async def test_intermediate_prose_tokens_are_not_forwarded_to_the_panel(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "token", {"token": "thinking out loud"}
            yield "metadata", {"response_id": "resp_1"}
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}

        kinds = [event for event, _ in await collect(service_with(script), self.situation)]
        self.assertEqual([kind for kind in kinds if kind != "status"],
                         ["metadata", "diagnosis", "tool_result", "done"])
        self.assertNotIn("token", kinds)

    async def test_every_call_that_opens_a_card_also_closes_one(self) -> None:
        """A sink that never settles leaves a spinner and a timer that keeps counting."""
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            for call_id, name in (("1", DIAGNOSIS_TOOL), ("2", SEQUENCE_STEP_TOOL),
                                  ("3", SEQUENCE_TOOL)):
                yield "tool_call_start", {"id": call_id, "name": name}
                yield "tool_call_delta", {"id": call_id, "arguments_delta": '{"a":'}
                yield "tool_call_end", {"id": call_id, "name": name, "arguments": {}}
            yield "tool_result", {"id": "1", "name": DIAGNOSIS_TOOL, "result": dict(GOOD)}
            yield "tool_result", {"id": "2", "name": SEQUENCE_STEP_TOOL,
                                  "result": record_sequence_step(mock.Mock(), **GOOD_STEPS[0])}
            yield "tool_result", {"id": "3", "name": SEQUENCE_TOOL,
                                  "result": complete_sequence_of_events(
                                      mock.Mock(), ordering_note=ORDERING_NOTE)}

        events = await collect(service_with(script), self.situation)
        opened = [data["id"] for event, data in events if event == "tool_call_start"]
        closed = [data["id"] for event, data in events if event == "tool_result"]
        self.assertEqual(opened, ["1", "2", "3"])
        self.assertEqual(closed, ["1", "2", "3"])
        # Arguments have to arrive too, or the card sits on "Composing input…" forever.
        self.assertEqual([data["id"] for event, data in events if event == "tool_call_end"],
                         ["1", "2", "3"])
        self.assertIn("tool_call_delta", [event for event, _ in events])

    async def test_a_call_the_run_outlives_is_failed_not_left_running(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "tool_call_start", {"id": "1", "name": "get_situation_evidence"}
            yield "tool_call_start", {"id": "2", "name": "profile_host_activity"}
            yield "tool_result", {"id": "1", "name": "get_situation_evidence",
                                  "result": EVIDENCE_RESULT}
            yield "tool_result", {"id": "9", "name": DIAGNOSIS_TOOL, "result": dict(GOOD)}

        events = await collect(service_with(script), self.situation)
        orphan = [data for event, data in events
                  if event == "tool_result" and data["id"] == "2"]
        self.assertEqual(len(orphan), 1)
        self.assertEqual(orphan[0]["result"]["error"], "no_result")
        self.assertEqual(orphan[0]["name"], "profile_host_activity")

    async def test_reasoning_summaries_reach_the_stream_and_no_recorded_artefact(self) -> None:
        async def script(message: str, **kwargs: Any) -> AsyncIterator[tuple[str, dict[str, Any]]]:
            yield "reasoning_start", {"id": "rs_1:0"}
            yield "reasoning_delta", {"id": "rs_1:0", "delta": "Weighing the logon burst"}
            yield "reasoning_end", {"id": "rs_1:0", "text": "Weighing the logon burst"}
            yield "tool_result", {"name": DIAGNOSIS_TOOL, "result": dict(GOOD)}

        events = await collect(service_with(script), self.situation)
        self.assertEqual([event for event, _ in events if event.startswith("reasoning")],
                         ["reasoning_start", "reasoning_delta", "reasoning_end"])
        diagnosis = next(data for event, data in events if event == "diagnosis")
        self.assertNotIn("reasoning", json.dumps(diagnosis))


if __name__ == "__main__":
    unittest.main()
