"""Azure OpenAI Responses agent with a bounded ADX tool loop."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncIterator
from copy import copy
from typing import Any

from azure_llm_compat import AzureLlmClient, LlmConfig, response_events, stream_tool_turn

from ..config import settings
from ..data import ReadOnlyAdx
from ..investigation import Scanner
from ..knowledge.classification import CLASSIFY_INSTRUCTIONS, MAX_OUTPUT_TOKENS, classify
from ..models import Situation
from .tools import ToolContext
from .tools.diagnosis import EvidenceLedger, index_knowledge_rows, resolve_citations
from .config import AgentSpec, load_agent_spec

logger = logging.getLogger(__name__)


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"


SUMMARY_INSTRUCTIONS = (
    "Summarize one deterministic situation from a historical cybersecurity replay using only the "
    "supplied envelope. Never invent hosts, accounts, counts, or events. Write at most two "
    "sentences and no more than fifty words in total: what the correlated rules observed, and the "
    "largest remaining unknown. No preamble, no bullet list, no closing offer. Never claim live "
    "monitoring, execution, compromise, containment, or response."
)


DIAGNOSIS_INSTRUCTIONS = (
    "You are diagnosing one situation from a historical cybersecurity replay of a static "
    "export. Work in two phases and say which phase you are in.\n"
    "Phase one, the sequence of events. Before naming anything, use the evidence and "
    "activity tools to establish an ordered sequence of what the involved account and host "
    "did across the window: first observation, what followed, and what ended it, each with "
    "its timestamp and the tool that returned it. Establish whether the correlated rules "
    "describe one coherent activity or unrelated noise. Prefer purpose-built tools over raw "
    "KQL.\n"
    "Phase two, the closest situation type. With that sequence in hand, call "
    "search_mitre_attack to retrieve pinned ATT&CK material matching what you observed, "
    "then call record_situation_diagnosis exactly once. situation_type must be the "
    "title of a document that tool returned in this run, copied verbatim, and citation_ids "
    "must be doc_id values from those same rows; anything else is dropped server-side. The "
    "headline must be a plain sentence an analyst would say out loud, naming the activity, "
    "the host, and the account, for example 'A privileged account ran directory "
    "reconnaissance against svpmn082 after a burst of explicit-credential logons.' "
    "supporting_observations must carry the sequence you established. Never invent hosts, "
    "accounts, counts, timestamps, or citations. Never claim live monitoring, prevention, "
    "containment, or a confirmed breach.\n"
    "Phase three, the sequence for the reader. Immediately after recording the diagnosis, "
    "push the phase-one sequence one step at a time with record_sequence_step, starting at "
    "position 1 and working forward in time: one short past-tense line each, naming the "
    "account or host and what it did. Copy each timestamp verbatim from tool output, or "
    "leave it empty; never estimate one. Attach to each step only the resource_id or doc_id "
    "values a tool returned in this run that support that step; the server resolves them "
    "against what the tools actually returned and marks anything else unsupported, so "
    "inventing an id gains nothing. Then call complete_sequence_of_events exactly once and "
    "stop."
)

DIAGNOSIS_TOOL = "record_situation_diagnosis"
SEQUENCE_STEP_TOOL = "record_sequence_step"
SEQUENCE_TOOL = "complete_sequence_of_events"
#: Sink tools are intercepted for their own frames, so they never feed the evidence ledger.
SINK_TOOLS = {DIAGNOSIS_TOOL, SEQUENCE_STEP_TOOL, SEQUENCE_TOOL}
#: What the investigation stream relays from the underlying turn, verbatim.
FORWARDED = {"status", "tool_call_start", "tool_call_delta", "tool_call_end", "tool_result",
             "reasoning_start", "reasoning_delta", "reasoning_end", "metadata", "error"}


class AgentService:
    def __init__(self, adx: ReadOnlyAdx, scanner: Scanner, spec: AgentSpec | None = None,
                 *, identity: Any = None) -> None:
        self.model = AzureLlmClient(LlmConfig(endpoint=settings.openai_endpoint, timeout_seconds=600),
                                    credential=identity)
        self.client = self.model.client
        self.adx = adx
        self.scanner = scanner
        self.spec = spec or load_agent_spec()
        self.tool_context = ToolContext(adx=adx, scanner=scanner)
        self.tools = {tool.metadata.name: tool for tool in self.spec.tools}

    def with_spec(self, spec: AgentSpec) -> AgentService:
        agent = copy(self)
        agent.spec = spec
        agent.tools = {tool.metadata.name: tool for tool in spec.tools}
        return agent

    def summarize_situation(self, situation: Situation) -> dict[str, Any]:
        started = time.monotonic()
        response = self.client.responses.create(
            model=self.spec.model,
            instructions=SUMMARY_INSTRUCTIONS,
            input=situation.model_dump_json(indent=2),
            reasoning={"effort": self.spec.reasoning_effort},
            max_output_tokens=400,
        )
        return {
            "situation_id": situation.situation_id,
            "summary": (response.output_text or "").strip(),
            "model": self.spec.model,
            "historical_replay": True,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }

    async def stream_summary(
        self, situation: Situation,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """The same bounded summary call, streamed as the model produces it.

        Same instructions and same envelope as `summarize_situation`, which stays for
        callers that want one JSON response. The tokens are the model's own output as it
        arrives; nothing here is replayed character by character.
        """
        started = time.monotonic()
        yield "status", {"phase": "model", "label": "Connecting to model…"}
        text: list[str] = []
        response = None
        async for event in self._response_events(
            model=self.spec.model,
            instructions=SUMMARY_INSTRUCTIONS,
            input=situation.model_dump_json(indent=2),
            reasoning={"effort": self.spec.reasoning_effort},
            max_output_tokens=400,
        ):
            if event.type == "response.created":
                yield "metadata", {"response_id": event.response.id, "model": self.spec.model,
                                   "agent_id": self.spec.agent_id, "agent_name": self.spec.name,
                                   "config_version": self.spec.config_version}
                yield "status", {"phase": "model", "label": "Summarising the situation…"}
            elif event.type == "response.output_text.delta":
                text.append(event.delta)
                yield "token", {"token": event.delta}
            elif event.type in {"response.completed", "response.incomplete"}:
                response = event.response
            elif event.type in {"response.failed", "error"}:
                detail = getattr(getattr(event, "response", None), "error", None)
                yield "error", {"error": "summary_failed",
                                "detail": str(detail or "no detail returned")}
                return
        summary = ("".join(text) or getattr(response, "output_text", "") or "").strip()
        payload = {
            "situation_id": situation.situation_id,
            "summary": summary,
            "model": self.spec.model,
            "historical_replay": True,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
        yield "summary", payload
        yield "done", {"situation_id": situation.situation_id,
                       "elapsed_ms": payload["elapsed_ms"]}

    def classify_situation(self, situation: Situation) -> dict[str, Any]:
        """Name the kind of situation from retrieved candidates in one bounded model call."""
        def invoke(payload: str) -> str:
            response = self.client.responses.create(
                model=self.spec.model,
                instructions=CLASSIFY_INSTRUCTIONS,
                input=payload,
                reasoning={"effort": self.spec.reasoning_effort},
                max_output_tokens=MAX_OUTPUT_TOKENS,
            )
            return response.output_text or ""

        return classify(situation, invoke, model=self.spec.model)

    def execute_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            raise ValueError(f"unknown or unconfigured tool: {name}")
        if tool.metadata.fallback:
            logger.warning(
                "cybereye.agent.fallback agent=%s config=%s tool=%s",
                self.spec.agent_id, self.spec.config_id, name,
            )
        return tool.function(self.tool_context, **arguments)

    def _response_events(self, **request: Any) -> AsyncIterator[Any]:
        """This service's one model stream, so tests can replace it in one place."""
        return response_events(self.client.responses.create, **request)

    async def stream_turn(
        self,
        message: str,
        *,
        previous_response_id: str | None,
        situation: Situation | None,
        instructions: str | None = None,
        max_tool_iterations: int | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        context = message
        if situation:
            context = (
                "Selected situation envelope:\n"
                + situation.model_dump_json(indent=2)
                + "\n\nAnalyst request:\n"
                + message
            )

        turn = stream_tool_turn(
            events=self._response_events, execute_tool=self.execute_tool,
            input=context, previous_response_id=previous_response_id,
            model=self.spec.model, instructions=instructions or self.spec.instructions,
            tools=[tool.openai_schema() for tool in self.spec.tools],
            reasoning=self.spec.reasoning_request(summarize=True),
            parallel_tool_calls=self.spec.parallel_tool_calls,
            max_output_tokens=max_output_tokens or self.spec.max_output_tokens,
            max_tool_iterations=max_tool_iterations or self.spec.max_tool_iterations,
            metadata={"agent_id": self.spec.agent_id, "agent_name": self.spec.name,
                      "config_id": self.spec.config_id, "config_version": self.spec.config_version,
                      "config_digest": self.spec.config_digest},
            tool_metadata={name: {"display_name": tool.display_name, "fallback": bool(tool.metadata.fallback)}
                           for name, tool in self.tools.items()},
            result_metadata={"agent_id": self.spec.agent_id, "config_id": self.spec.config_id},
        )
        try:
            async for event in turn:
                yield event
        finally:
            await turn.aclose()

    async def diagnose_situation(
        self, situation: Situation,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """Run a longer tool-using investigation that must end in the diagnosis sink tool."""
        started_at = time.monotonic()
        request = (
            "Diagnose this situation for an analyst who has not seen the raw telemetry. "
            "Establish the sequence of events first, then name the closest situation type "
            "from the MITRE knowledge tool and record the diagnosis, then record the "
            "sequence of events for the reader."
        )
        turn = self.stream_turn(
            request,
            previous_response_id=None,
            situation=situation,
            instructions=f"{self.spec.instructions}\n\n{DIAGNOSIS_INSTRUCTIONS}",
            max_tool_iterations=self.spec.diagnosis_max_tool_iterations,
            max_output_tokens=self.spec.diagnosis_max_output_tokens,
        )
        recorded = False
        sequenced = False
        #: Provenance for citations comes only from knowledge rows this run actually returned.
        knowledge: dict[str, dict[str, str]] = {}
        #: And provenance for a step's evidence comes only from rows a tool returned here.
        ledger = EvidenceLedger()
        steps: list[dict[str, Any]] = []
        #: Every call that opened a card, and every one that has reached a terminal state.
        started: dict[str, str] = {}
        settled: set[str] = set()
        ordering_note = ""

        def emit_sequence(ordering_note: str) -> dict[str, Any]:
            return {
                "steps": list(steps),
                "ordering_note": ordering_note,
                "situation_id": situation.situation_id,
                "model": self.spec.model,
                "elapsed_ms": round((time.monotonic() - started_at) * 1000),
            }

        try:
            async for event, data in turn:
                if event == "tool_call_start":
                    started[str(data.get("id") or "")] = str(data.get("name") or "")
                if event == "tool_call_end":
                    ledger.note_call(str(data.get("id") or ""), data.get("arguments"))
                if event == "tool_result":
                    name = str(data.get("name") or "")
                    result = data.get("result") or {}
                    failed = "error" in result
                    settled.add(str(data.get("id") or ""))
                    if name == DIAGNOSIS_TOOL and not failed:
                        recorded = True
                        citations, unsupported, type_supported = resolve_citations(
                            knowledge, str(result.get("situation_type") or ""),
                            list(result.get("citation_ids") or []),
                        )
                        payload = {key: value for key, value in result.items()
                                   if key != "citation_ids"}
                        yield "diagnosis", {
                            **payload,
                            "citations": citations,
                            "unsupported_citations": unsupported,
                            "situation_type_supported": type_supported,
                            "situation_id": situation.situation_id,
                            "model": self.spec.model,
                            "elapsed_ms": round((time.monotonic() - started_at) * 1000),
                        }
                        yield "status", {"phase": "model",
                                         "label": "Writing the sequence of events…"}
                    elif name == SEQUENCE_STEP_TOOL and not failed:
                        evidence, unsupported_ids = ledger.resolve(
                            list(result.get("evidence_ids") or []))
                        step = {
                            "description": str(result.get("description") or ""),
                            "timestamp": str(result.get("timestamp") or ""),
                            "evidence_ids": list(result.get("evidence_ids") or []),
                            "evidence": evidence,
                            "unsupported_evidence_ids": unsupported_ids,
                        }
                        steps.append(step)
                        yield "sequence_step", {
                            **step,
                            "position": len(steps),
                            "situation_id": situation.situation_id,
                        }
                    elif name == SEQUENCE_TOOL and not failed:
                        sequenced = True
                        ordering_note = str(result.get("ordering_note") or "")
                    elif name not in SINK_TOOLS:
                        knowledge.update(index_knowledge_rows(data.get("result")))
                        tool = self.tools.get(name)
                        ledger.record(str(data.get("id") or ""), name,
                                      tool.display_name if tool else name, data.get("result"))
                finish = recorded and sequenced and started.keys() <= settled
                if finish:
                    yield "sequence", emit_sequence(ordering_note)
                if event in FORWARDED:
                    yield event, data
                if finish:
                    break
        finally:
            await turn.aclose()
        # A card that started must not be left spinning because the run ended first.
        for call_id, name in started.items():
            if call_id not in settled:
                yield "tool_result", {"id": call_id, "name": name, "result": {
                    "error": "no_result",
                    "detail": "the run ended before this call returned a result",
                }}
        if not recorded:
            yield "error", {
                "error": "diagnosis_not_recorded",
                "detail": f"the agent finished without calling {DIAGNOSIS_TOOL}",
            }
        # Steps pushed without the closing call are still the reader's; emit what was resolved
        # rather than leaving the section spinning.
        if steps and not sequenced:
            sequenced = True
            yield "sequence", emit_sequence("")
        yield "done", {"recorded": recorded, "sequenced": sequenced,
                       "elapsed_ms": round((time.monotonic() - started_at) * 1000)}
