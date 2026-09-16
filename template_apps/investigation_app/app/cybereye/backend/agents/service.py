"""Owner-bound native agents with host-owned evidence and presentation rules."""

from __future__ import annotations

import json
import inspect
import logging
import time
from collections.abc import AsyncIterator
from copy import copy
from typing import Any

from llm_interface import Capabilities, Connection, Limits, LlmError, Session, ToolCall, connect, tool

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
                 *, identity: Any = None, connection: Connection | None = None,
                 allow_model_calls: bool = False, authorize_tool: Any = None) -> None:
        self.adx = adx
        self.scanner = scanner
        self.spec = spec or load_agent_spec()
        self.tool_context = ToolContext(adx=adx, scanner=scanner)
        self.tools = {tool.metadata.name: tool for tool in self.spec.tools}
        self._owns_model = connection is None
        self.model = connection or connect(settings.openai_endpoint, self.spec.model, credential=identity,
            allow_model_calls=allow_model_calls, allowed_tools=tuple(self.tools),
            capabilities=Capabilities(reasoning=True), limits=Limits(timeout_seconds=600,
                max_model_calls=max(self.spec.max_tool_iterations, self.spec.diagnosis_max_tool_iterations),
                max_tool_calls=64, max_output_tokens=max(self.spec.max_output_tokens, self.spec.diagnosis_max_output_tokens, MAX_OUTPUT_TOKENS),
                max_input_bytes=1_048_576, max_output_bytes=2_097_152, max_tool_result_bytes=256_000))
        self._authorize_tool = authorize_tool

    async def aclose(self) -> None:
        if self._owns_model:
            await self.model.aclose()

    def with_spec(self, spec: AgentSpec) -> AgentService:
        if spec.model != self.model.config.model:
            raise ValueError("agent_model_not_bound")
        agent = copy(self)
        agent._owns_model = False
        agent.spec = spec
        agent.tools = {tool.metadata.name: tool for tool in spec.tools}
        return agent

    def _binding(self, principal: str, instructions: str | None = None, *, tools: bool = True):
        text = instructions or self.spec.instructions
        declared = []
        if tools:
            for resolved in self.spec.tools:
                def bind(resolved):
                    async def invoke(**arguments):
                        result = resolved.function(self.tool_context, **arguments)
                        return await result if inspect.isawaitable(result) else result
                    return tool(invoke, name=resolved.metadata.name, description=resolved.metadata.description,
                                schema=resolved.metadata.parameters)
                declared.append(bind(resolved))

        def authorize(call: ToolCall):
            if call.principal != principal or call.name not in self.tools or not call.run_id or not call.call_id:
                return False
            return self._authorize_tool(call) if self._authorize_tool is not None else True

        return self.model.agent(instructions=text, name=self.spec.agent_id,
            tools=declared, authorize_tool=authorize, required_capabilities=("streaming",))

    def create_session(self, *, principal: str) -> Session:
        return self._binding(principal).create_session(principal=principal)

    def _options(self, max_tokens: int, *, summarize: bool = False) -> dict[str, Any]:
        options: dict[str, Any] = {"max_tokens": max_tokens, "parallel_tool_calls": self.spec.parallel_tool_calls}
        if self.model.capabilities.reasoning:
            options["reasoning"] = self.spec.reasoning_request(summarize=summarize)
        return options

    async def summarize_situation(self, situation: Situation, *, principal: str) -> dict[str, Any]:
        started = time.monotonic()
        response = await self._binding(principal, SUMMARY_INSTRUCTIONS, tools=False).run(
            situation.model_dump_json(indent=2), principal=principal, options=self._options(400))
        return {
            "situation_id": situation.situation_id,
            "summary": response.text.strip(),
            "status": response.additional_properties["llm_interface"]["status"],
            "model": self.spec.model,
            "historical_replay": True,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }

    async def stream_summary(
        self, situation: Situation, *, principal: str,
    ) -> AsyncIterator[tuple[str, dict[str, Any]]]:
        """The same bounded summary call, streamed as the model produces it.

        Same instructions and same envelope as `summarize_situation`, which stays for
        callers that want one JSON response. The tokens are the model's own output as it
        arrives; nothing here is replayed character by character.
        """
        started = time.monotonic()
        text: list[str] = []
        stream = self._binding(principal, SUMMARY_INSTRUCTIONS, tools=False).run(
            situation.model_dump_json(indent=2), principal=principal, stream=True, options=self._options(400))
        async with stream:
            async for event in stream:
                if event.kind == "text.delta":
                    text.append(event.text)
                    yield "token", {"token": event.text, "native": self._event_identity(event)}
                elif event.kind == "run.started":
                    yield "metadata", {**event.data, "model": self.spec.model, "native": self._event_identity(event)}
            response = await stream.get_final_response()
        receipt = response.additional_properties["llm_interface"]
        summary = ("".join(text) or response.text).strip()
        payload = {
            "situation_id": situation.situation_id,
            "summary": summary,
            "status": receipt["status"],
            "model": self.spec.model,
            "historical_replay": True,
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }
        yield "summary", payload
        yield "done", {"situation_id": situation.situation_id,
                       "status": receipt["status"], "run_id": receipt["run_id"],
                       "elapsed_ms": payload["elapsed_ms"]}

    async def classify_situation(self, situation: Situation, *, principal: str) -> dict[str, Any]:
        """Name the kind of situation from retrieved candidates in one bounded model call."""
        async def invoke(payload: str) -> str:
            response = await self._binding(principal, CLASSIFY_INSTRUCTIONS, tools=False).run(
                payload, principal=principal, options=self._options(MAX_OUTPUT_TOKENS))
            if response.additional_properties["llm_interface"]["status"] != "completed":
                raise LlmError("classification_incomplete", category="interrupted")
            return response.text

        return await classify(situation, invoke, model=self.spec.model)

    async def stream_turn(
        self,
        message: str,
        *,
        principal: str,
        session: Session | None = None,
        situation: Situation | None,
        instructions: str | None = None,
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

        binding = self._binding(principal, instructions)
        names: dict[str, str] = {}
        reasoning: dict[str, str] = {}
        stream = binding.run(context, session=session, principal=principal, stream=True,
            options=self._options(max_output_tokens or self.spec.max_output_tokens, summarize=True))
        async with stream:
            async for event in stream:
                for name, data in self._frames(event, names, reasoning):
                    yield name, {**data, "native": self._event_identity(event)}
            await stream.get_final_response()

    def _frames(self, event, names, reasoning):
        data, kind = event.data, event.kind
        call_id = data.get("call_id", "")
        if kind in {"tool.call.delta", "tool.call.ready"}:
            name = data.get("name") or names.get(call_id, "")
            if call_id not in names:
                names[call_id] = name
                resolved = self.tools.get(name)
                yield "tool_call_start", {"id": call_id, "name": name,
                    "display_name": resolved.display_name if resolved else name,
                    "fallback": bool(resolved and resolved.metadata.fallback)}
            names[call_id] = name
            yield ("tool_call_end" if kind == "tool.call.ready" else "tool_call_delta"), {
                "id": call_id, "name": name,
                ("arguments" if kind == "tool.call.ready" else "delta"): data.get("arguments", "")}
        elif kind == "tool.result":
            yield "tool_result", {"id": call_id, "name": names.get(call_id, ""), "result": data["result"]}
        elif kind == "tool.failed":
            yield "tool_result", {"id": call_id, "name": names.get(call_id, data.get("name", "")),
                                   "result": {"error": "tool_failed", "detail": "Tool execution refused or failed."}}
        elif kind == "tool.progress":
            yield "tool_progress", {"id": call_id, **data}
        elif kind == "text.delta":
            yield "token", {"token": event.text}
        elif kind == "reasoning.summary.delta":
            identifier = data.get("id") or event.run_id
            if identifier not in reasoning:
                reasoning[identifier] = ""
                yield "reasoning_start", {"id": identifier}
            reasoning[identifier] += data.get("text", "")
            yield "reasoning_delta", {"id": identifier, "delta": data.get("text", "")}
        elif kind == "run.started":
            yield "metadata", {**data, "run_id": event.run_id, "model": self.spec.model,
                "agent_id": self.spec.agent_id, "agent_name": self.spec.name,
                "config_id": self.spec.config_id, "config_version": self.spec.config_version,
                "config_digest": self.spec.config_digest}
        elif kind in {"run.completed", "run.incomplete", "run.refused"}:
            for identifier, text in reasoning.items():
                yield "reasoning_end", {"id": identifier, "text": text}
            yield "done", {**data, "status": kind.removeprefix("run."), "run_id": event.run_id}
        elif kind == "run.failed":
            yield "error", {"error": data.get("code", "agent_run_failed"), "detail": data.get("action", "")}
        elif kind == "usage":
            yield "usage", data

    async def diagnose_situation(
        self, situation: Situation, *, principal: str,
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
            principal=principal,
            situation=situation,
            instructions=f"{self.spec.instructions}\n\n{DIAGNOSIS_INSTRUCTIONS}",
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
        sequence_emitted = False
        terminal_status = "incomplete"

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
                if finish and not sequence_emitted:
                    yield "sequence", emit_sequence(ordering_note)
                    sequence_emitted = True
                if event in FORWARDED:
                    yield event, data
                if event == "done":
                    terminal_status = str(data.get("status", "incomplete"))
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
        yield "done", {"recorded": recorded, "sequenced": sequenced, "status": terminal_status,
                       "elapsed_ms": round((time.monotonic() - started_at) * 1000)}


    @staticmethod
    def _event_identity(event) -> dict[str, Any]:
        return {"schema_version": event.schema_version, "run_id": event.run_id,
            "sequence": event.sequence, "kind": event.kind}
