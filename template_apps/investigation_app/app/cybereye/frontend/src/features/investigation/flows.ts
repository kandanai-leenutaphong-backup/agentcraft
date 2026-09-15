/**
 * The app-owned flow state for the two situation workloads.
 *
 * WHY IT LIVES HERE AND NOT IN A PANEL
 * ------------------------------------
 * The summary and the investigation are each one server run whose output two places need:
 * the board keeps the final result, and a chat tab shows the run happening. Owned by a
 * panel, each run would either fire twice or exist only where it was started. Owned here,
 * the run happens once and both readers see the same state.
 *
 * RACE FENCES
 * -----------
 * Every run is stamped with the situation id it was started for and a monotonic run number.
 * A late event from a superseded run is dropped rather than written into the current one,
 * so changing selection mid-flight cannot paint the previous situation's answer under the
 * new situation's heading. Switching chat tabs cancels nothing: a tab is a view of a run,
 * not the run itself.
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { streamDiagnosis, streamSummary } from "../../shared/api";
import { agentIdentity, applyReasoning, appendToolArguments, settleToolArguments, finishTool } from "../../shared/api";
import type { AgentIdentity, ReasoningBlock, Situation, SituationDiagnosis, SituationSequence, ToolRun } from "../../shared/types";

export type FlowState = "idle" | "running" | "done" | "failed";

export interface SummaryFlow {
  agent?: AgentIdentity;
  situationId: string;
  state: FlowState;
  activity: string;
  text: string;
  meta: string;
  error: string;
}

export interface DiagnosisFlow {
  agent?: AgentIdentity;
  situationId: string;
  state: FlowState;
  activity: string;
  tools: ToolRun[];
  //: The model's narration of the run. Never written into the result or the sequence.
  reasoning: ReasoningBlock[];
  result: SituationDiagnosis | null;
  //: Produced later in the same run, so it carries its own state rather than the run's.
  sequence: SituationSequence | null;
  sequenceState: FlowState;
  error: string;
}

const EMPTY_SUMMARY: SummaryFlow = {
  situationId: "", state: "idle", activity: "", text: "", meta: "", error: "",
};
const EMPTY_DIAGNOSIS: DiagnosisFlow = {
  situationId: "", state: "idle", activity: "", tools: [], reasoning: [], result: null,
  sequence: null, sequenceState: "idle", error: "",
};

export interface SituationFlows {
  summary: SummaryFlow;
  diagnosis: DiagnosisFlow;
  //: Force a fresh investigation, superseding any run in flight for this situation.
  runDiagnosis: (situation: Situation) => void;
  //: Start one only if this situation has not already started one.
  ensureDiagnosis: (situation: Situation) => void;
}

export function useSituationFlows(selected: Situation | null): SituationFlows {
  const [summary, setSummary] = useState<SummaryFlow>(EMPTY_SUMMARY);
  const [diagnosis, setDiagnosis] = useState<DiagnosisFlow>(EMPTY_DIAGNOSIS);

  const summaryRun = useRef(0);
  const diagnosisRun = useRef(0);
  const summaryAbort = useRef<AbortController | null>(null);
  const diagnosisAbort = useRef<AbortController | null>(null);
  //: The situation whose investigation has already been started, so nothing double-fires.
  const diagnosisStartedFor = useRef("");

  const runDiagnosis = useCallback((situation: Situation) => {
    diagnosisAbort.current?.abort();
    const controller = new AbortController();
    diagnosisAbort.current = controller;
    const run = ++diagnosisRun.current;
    const id = situation.situation_id;
    diagnosisStartedFor.current = id;
    const current = () => run === diagnosisRun.current;
    const patch = (update: (flow: DiagnosisFlow) => DiagnosisFlow) => {
      if (current()) setDiagnosis(update);
    };
    setDiagnosis({ situationId: id, state: "running", activity: "Opening the investigation…",
                   tools: [], reasoning: [], result: null, sequence: null,
                   sequenceState: "idle", error: "" });
    streamDiagnosis(situation, {
      metadata: (value) => patch((flow) => ({ ...flow, agent: agentIdentity(value) ?? flow.agent })),
      status: (activity) => patch((flow) => ({ ...flow, activity })),
      toolStart: (name, displayName, toolId) => patch((flow) => ({
        ...flow,
        tools: [...flow.tools, { id: toolId, name, displayName, fallback: false,
                                 status: "running", startedAt: Date.now() }],
      })),
      toolDelta: (toolId, delta) => patch((flow) => ({
        ...flow, tools: appendToolArguments(flow.tools, toolId, delta),
      })),
      toolEnd: (toolId, args) => patch((flow) => ({
        ...flow, tools: settleToolArguments(flow.tools, toolId, args),
      })),
      toolResult: (toolId, _name, result) => patch((flow) => ({
        ...flow, tools: finishTool(flow.tools, toolId, result),
      })),
      reasoning: (blockId, delta, state) => patch((flow) => ({
        ...flow, reasoning: applyReasoning(flow.reasoning, blockId, delta, state),
      })),
      diagnosis: (value) => patch((flow) => ({
        ...flow, result: value, state: "done",
        sequenceState: flow.sequence ? flow.sequenceState : "running",
      })),
      sequenceStep: (value) => patch((flow) => {
        // Each step arrives on its own, so a late duplicate of a position replaces it
        // rather than appending a second card.
        const steps = [...(flow.sequence?.steps ?? [])];
        const step = { description: value.description, timestamp: value.timestamp,
                       evidence_ids: value.evidence_ids ?? [], evidence: value.evidence ?? [],
                       unsupported_evidence_ids: value.unsupported_evidence_ids ?? [] };
        steps[Math.max(0, value.position - 1)] = step;
        return {
          ...flow, sequenceState: "running",
          sequence: {
            situation_id: value.situation_id, ordering_note: flow.sequence?.ordering_note ?? "",
            model: flow.sequence?.model ?? "", elapsed_ms: flow.sequence?.elapsed_ms ?? 0,
            steps: steps.filter(Boolean),
          },
        };
      }),
      sequence: (value) => patch((flow) => ({
        ...flow, sequence: value, sequenceState: "done",
      })),
      error: (detail) => patch((flow) => ({ ...flow, error: detail, state: "failed" })),
      done: () => patch((flow) => ({
        ...flow, activity: "",
        state: flow.state === "running" ? (flow.result ? "done" : "failed") : flow.state,
        sequenceState: flow.sequenceState === "running"
          ? (flow.sequence && flow.sequence.steps.length > 0 ? "done" : "failed")
          : flow.sequenceState,
      })),
    }, controller.signal).catch((err: Error) => {
      if (err.name === "AbortError") return;
      patch((flow) => ({ ...flow, error: err.message, state: "failed", activity: "" }));
    });
  }, []);

  const ensureDiagnosis = useCallback((situation: Situation) => {
    if (diagnosisStartedFor.current === situation.situation_id) return;
    runDiagnosis(situation);
  }, [runDiagnosis]);

  useEffect(() => {
    // A new selection supersedes both runs. Aborting first means the old stream's own
    // callbacks stop arriving; the run fence covers whatever is already in flight.
    summaryAbort.current?.abort();
    diagnosisAbort.current?.abort();
    summaryRun.current += 1;
    diagnosisRun.current += 1;
    setDiagnosis(EMPTY_DIAGNOSIS);
    diagnosisStartedFor.current = "";
    if (!selected) {
      setSummary(EMPTY_SUMMARY);
      return;
    }

    const controller = new AbortController();
    summaryAbort.current = controller;
    const run = summaryRun.current;
    const id = selected.situation_id;
    const patch = (update: (flow: SummaryFlow) => SummaryFlow) => {
      if (run === summaryRun.current) setSummary(update);
    };
    setSummary({ situationId: id, state: "running", activity: "Connecting to model…",
                 text: "", meta: "", error: "" });
    streamSummary(selected, {
      metadata: (value) => patch((flow) => ({ ...flow, agent: agentIdentity(value) ?? flow.agent })),
      status: (activity) => patch((flow) => ({ ...flow, activity })),
      token: (token) => patch((flow) => ({ ...flow, text: flow.text + token })),
      summary: (value) => patch((flow) => ({
        ...flow, text: value.summary || flow.text,
        meta: `${value.model} · ${value.elapsed_ms} ms`, state: "done", activity: "",
      })),
      error: (detail) => patch((flow) => ({ ...flow, error: detail, state: "failed",
                                            activity: "" })),
      done: () => patch((flow) => ({
        ...flow, activity: "", state: flow.state === "running" ? "done" : flow.state,
      })),
    }, controller.signal).catch((err: Error) => {
      if (err.name === "AbortError") return;
      patch((flow) => ({ ...flow, error: err.message, state: "failed", activity: "" }));
    });

    // The investigation is the situation's own workload, not a button the analyst must find.
    runDiagnosis(selected);

    return () => controller.abort();
  }, [selected, runDiagnosis]);

  return { summary, diagnosis, runDiagnosis, ensureDiagnosis };
}
