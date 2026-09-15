import { useCallback, useEffect, useRef, useState } from "react";
import { BarChart3, ChevronDown, Clock3, Database, Info, Network, Pin, Sparkles, Stethoscope } from "lucide-react";
import { api } from "../../shared/api";
import { DerivedExplanation } from "../scanner";
import { ExplainerHint, type ExplainerStage } from "../../shared/ui";
import { linkEntities, useEntityIndex } from "../../shared/ui";
import { EntityTray } from "./EntityTray";
import { GraphPanel } from "../graph";
import { ResourceChip } from "../../shared/ui";
import { ToolRenderModelView, fromQueryResult, type ToolRenderModel } from "../../shared/agent-output";
import { CodeBlock } from "../../shared/ui";
import { FullscreenButton, FullscreenExit, useFullscreen } from "../../shared/ui";
import { Section } from "./Section";
import { renderCorpusText } from "./markup";
import type { SituationFlows } from "./flows";
import type { GraphEntity, RuleExecution, Situation, SituationDiagnosis, SituationMetric, StepEvidence } from "../../shared/types";

interface Props {
  selected: Situation | null;
  scanElapsed: number | null;
  ruleExecutions: RuleExecution[];
  //: The window the current scan used. Sent with evidence requests so any replica can serve them.
  scanWindow: { start: string; end: string } | null;
  graphWindow: { id: number; start: string; end: string; label: string } | null;
  entityRequest: { id: number; nodeId: string; name: string; label: string } | null;
  investigateRequest: { id: number } | null;
  onAskAgent: (prompt: string) => void;
  //: Both workloads are owned by the app so one run feeds the board and its chat tab.
  flows: SituationFlows;
}

//: Beyond this a selection stops being a comparison and becomes the whole graph.
const MAX_PICKED = 8;

const tools = [
  {
    id: "timeline", label: "Situation timeline", icon: Clock3, category: "event_timeline",
    query: "EventsUnified | where source_time between (datetime(2026-08-13T02:30:00Z) .. datetime(2026-08-13T03:40:59Z)) | summarize events=count() by bin(source_time, 1m), event_type_recovered | order by source_time asc",
  },
  {
    id: "products", label: "Product composition", icon: Database, category: "product_composition",
    query: "EventsUnified | summarize events=count() by product | order by events desc",
  },
  {
    id: "auth", label: "Authentication mix", icon: BarChart3, category: "authentication_mix",
    query: "EventsUnified | where isnotempty(win_event_id) | summarize events=count() by win_event_id | order by events desc",
  },
  {
    id: "egress", label: "Firewall baseline", icon: Network, category: "firewall_baseline",
    query: "EventsUnified | where isnotempty(flow_action) | summarize flows=count(), blocked=countif(flow_action == 'FW_BLOCKED') by bin(source_time, 1d) | order by source_time asc",
  },
];

/** The backend emits no metric entry for scan time; derive it from the real per-rule executions. */
function scanTimeMetric(scanElapsed: number | null, executions: RuleExecution[]): SituationMetric {
  const summed = executions.reduce((total, item) => total + item.elapsed_ms, 0);
  const slowest = executions.reduce<RuleExecution | null>(
    (best, item) => (!best || item.elapsed_ms > best.elapsed_ms ? item : best), null,
  );
  const qualified = executions.filter((item) => item.hit_count > 0).length;
  return {
    metric_id: "scan_query_time",
    label: "scan query time",
    value: scanElapsed === null ? "—" : `${scanElapsed} ms`,
    definition: "Wall-clock time the scan took to dispatch every registered rule query against ADX and synthesise situations for this window. Measured by the scan orchestrator, not an ADX service metric.",
    derivation: executions.length
      ? `${executions.length} rule quer${executions.length === 1 ? "y" : "ies"} dispatched concurrently · ${summed} ms summed rule time · slowest ${slowest?.rule_id ?? "—"} at ${slowest?.elapsed_ms ?? 0} ms · ${qualified} qualified / ${executions.length - qualified} did not · ${scanElapsed ?? "—"} ms scan wall clock`
      : "No per-rule execution timings were returned with this scan.",
    contributions: executions.map((item) => ({
      source: item.rule_id,
      detail: `${item.observation?.groups_returned ?? 0} group(s) returned · ${item.hit_count} qualified · ${item.observation?.outcome ?? "unknown"}${item.hit_count === 0 && (item.observation?.groups_returned ?? 0) > 0 ? ` · largest group ${item.observation?.max_group_count ?? 0}, needs ${item.observation?.threshold_expression ?? ""}` : ""}`,
      value: `${item.elapsed_ms} ms`,
    })),
  };
}

function summaryStages(situation: Situation, meta: string): ExplainerStage[] {
  const patterns = situation.patterns.length;
  const evidence = situation.patterns.reduce((total, pattern) => total + pattern.evidence_ids.length, 0);
  return [
    {
      kind: "input", label: "Deterministic situation envelope",
      detail: `${patterns} pattern${patterns === 1 ? "" : "s"}, ${situation.metrics?.length ?? 0} metric${(situation.metrics?.length ?? 0) === 1 ? "" : "s"}, and ${evidence} cited resource id${evidence === 1 ? "" : "s"} already produced by the rule engine.`,
    },
    {
      kind: "compute", label: "Serialised, not re-queried",
      detail: "The envelope is sent as JSON. The summariser holds no tools, so it cannot reach ADX and cannot introduce a fact the scan did not observe.",
    },
    {
      kind: "model", label: "Model under a brevity contract",
      detail: "Instructions cap the answer at two sentences and fifty words, require the largest remaining unknown to be named, and forbid containment or prevention language.",
    },
    {
      kind: "output", label: "Summary text",
      detail: meta ? `Produced by ${meta}.` : "Awaiting the model response.",
    },
  ];
}

function diagnosisStages(value: SituationDiagnosis | null, toolsUsed: string[]): ExplainerStage[] {
  return [
    {
      kind: "input", label: "Situation envelope as the opening brief",
      detail: "The agent starts from the deterministic situation — the rules that fired, the entity, and the window — not from free text.",
    },
    {
      kind: "compute", label: "Its own investigation against ADX",
      detail: toolsUsed.length
        ? `Tools it chose to run this time: ${toolsUsed.join(", ")}. Each returns bounded read-only rows from the historical export.`
        : "It establishes the sequence of events from the telemetry tools, then retrieves pinned MITRE ATT&CK material to name the closest type.",
    },
    {
      kind: "corpus", label: "Type and citations taken from retrieved rows",
      detail: value
        ? `The type ${value.situation_type_supported ? "matches" : "does not match"} a document returned in this run, and ${value.citations.length} citation${value.citations.length === 1 ? "" : "s"} were resolved against those rows. Anything the run did not return is dropped server-side.`
        : "Only documents search_mitre_attack returned in this run can be cited; the server drops the rest.",
    },
    {
      kind: "model", label: "A sink tool it must call to conclude",
      detail: "The run only completes when the agent calls record_situation_diagnosis. Free prose is not accepted as a diagnosis, so the wording, assessment, and citations are always structured.",
    },
    {
      kind: "output", label: "Plain-language diagnosis",
      detail: value
        ? `${value.assessment.replace(/_/g, " ")} at ${value.confidence} confidence, resting on ${value.supporting_observations.length} stated observation${value.supporting_observations.length === 1 ? "" : "s"} and citing ${value.evidence_ids.length} record id${value.evidence_ids.length === 1 ? "" : "s"}. ${value.elapsed_ms} ms.`
        : "Pending.",
    },
  ];
}

export function ToolBoard({ selected, scanElapsed, ruleExecutions, scanWindow, graphWindow, entityRequest, investigateRequest, onAskAgent, flows }: Props) {
  const [tab, setTab] = useState<"situation" | "tools" | "evidence" | "graph">("situation");
  const [activeTool, setActiveTool] = useState<string | null>(null);
  const [queryRender, setQueryRender] = useState<ToolRenderModel | null>(null);
  const [evidenceRender, setEvidenceRender] = useState<ToolRenderModel | null>(null);
  const [error, setError] = useState("");
  const [openMetric, setOpenMetric] = useState<string | null>(null);
  const [openPatterns, setOpenPatterns] = useState<Set<string>>(new Set());
  const [openDoc, setOpenDoc] = useState<Record<string, unknown> | null>(null);
  const [openDocId, setOpenDocId] = useState("");
  const [diagnosisDetail, setDiagnosisDetail] = useState(false);
  const [openSteps, setOpenSteps] = useState<Set<number>>(new Set());
  const [focusRequest, setFocusRequest] = useState<{ id: number; nodeId: string; name: string } | null>(null);
  const [picked, setPicked] = useState<GraphEntity[]>([]);
  const [selectionRequest, setSelectionRequest] = useState<{ id: number; ids: string[] } | null>(null);
  const entityIndex = useEntityIndex();

  // Clicking a mention collects the entity rather than navigating, so several can be
  // compared in one graph. The tray is the only thing that navigates.
  const pick = useCallback((entity: GraphEntity) => {
    setPicked((current) => current.some((item) => item.id === entity.id)
      ? current
      : [...current, entity].slice(0, MAX_PICKED));
  }, []);
  const mention = useCallback((text: string) => linkEntities(text, entityIndex, pick), [entityIndex, pick]);

  function visualize(ids: string[]) {
    if (ids.length === 0) return;
    setSelectionRequest({ id: Date.now(), ids });
    setFocusRequest(null);
    setTab("graph");
  }

  // A mention clicked in the scanner column collects here too, so both panels share one tray.
  useEffect(() => {
    if (!entityRequest) return;
    setPicked((current) => current.some((item) => item.id === entityRequest.nodeId)
      ? current
      : [...current, {
          id: entityRequest.nodeId, name: entityRequest.name,
          label: entityRequest.label, event_count: 0,
        }].slice(0, MAX_PICKED));
  }, [entityRequest]);
  // The two model workloads are the app's, not this panel's: read the state, start the
  // investigation through the same callback the chat tab watches, never run one here.
  const { summary, diagnosis: diagnosisFlow, runDiagnosis, ensureDiagnosis } = flows;
  const summaryText = summary.error ? `Summary unavailable: ${summary.error}` : summary.text;
  const summaryLoading = summary.state === "running" && !summary.text;
  const summaryMeta = summary.meta;
  const diagnosis = diagnosisFlow.result;
  const diagnosisState = diagnosisFlow.state === "done" ? "idle" : diagnosisFlow.state;
  const diagnosisActivity = diagnosisFlow.activity;
  const diagnosisTools = diagnosisFlow.tools.map((tool) => tool.displayName ?? tool.name);
  const diagnosisError = diagnosisFlow.error;
  const sequence = diagnosisFlow.sequence;
  const sequenceState = diagnosisFlow.sequenceState;

  useEffect(() => {
    setEvidenceRender(null);
    setOpenMetric(null); setOpenPatterns(new Set());
    setOpenDoc(null); setOpenDocId("");
    setDiagnosisDetail(false);
    setOpenSteps(new Set());
    if (!selected) return;
    api.evidence(selected.situation_id, scanWindow)
      .then((result) => setEvidenceRender(fromQueryResult(
        "get_situation_evidence", "cited_evidence", { situation_id: selected.situation_id }, result,
      )))
      .catch((err: Error) => setError(err.message));
  }, [selected]);
  const board = useFullscreen("board");
  const appliedInvestigation = useRef(0);

  // The scanner's investigate link reuses the run the selection already started.
  useEffect(() => {
    if (!investigateRequest || investigateRequest.id === appliedInvestigation.current) return;
    appliedInvestigation.current = investigateRequest.id;
    if (!selected) return;
    setTab("situation");
    ensureDiagnosis(selected);
  }, [investigateRequest, selected, ensureDiagnosis]);

  async function runTool(id: string, category: string, query: string) {
    setActiveTool(id); setError("");
    try {
      const result = await api.query(query, 100);
      setQueryRender(fromQueryResult(id, category, { query }, result));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setActiveTool(null);
    }
  }

  const current = tools.find((item) => item.id === activeTool);
  const metrics: SituationMetric[] = selected
    ? [...(selected.metrics ?? []), scanTimeMetric(scanElapsed, ruleExecutions)]
    : [];
  const openEntry = metrics.find((metric) => metric.metric_id === openMetric) ?? null;

  return (
    <section className={`board panel-column ${board.active ? "panel-fullscreen" : ""}`} aria-label="Central tool board">
      <nav className="board-tabs" aria-label="Tool board views">
        {(["situation", "tools", "evidence", "graph"] as const).map((item) => (
          <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}>{item}</button>
        ))}
        <FullscreenButton active={board.active} onToggle={board.toggle} label={`the ${tab} tab`} />
      </nav>

      <div className="board-content">
        {tab === "situation" && (
          selected ? (
            <div className="selected-board">
              <Section
                id="summary" title="Situation summary" className="luna-summary" defaultOpen
                badge={<span className="fold-meta">{summaryMeta}</span>}
                digest={summaryLoading ? "reading…" : summaryText.slice(0, 90)}
                hint={<ExplainerHint
                  title="How this summary was produced" subject="the situation summary"
                  stages={summaryStages(selected, summaryMeta)}
                  footnote="Historical replay. The summary restates observed telemetry; it is not a detection or a response action."
                />}
              >
                <p>{summaryLoading ? (summary.activity || "Reading the deterministic situation envelope…") : mention(summaryText)}</p>
              </Section>
              <div className="board-hero">
                <div><span className="eyebrow">Selected situation</span><h1>{selected.host}</h1><p>{selected.principal}</p></div>
                <span className={`large-severity ${selected.severity}`}>{selected.severity}</span>
              </div>
              <Section
                id="diagnosis" title="Situation investigation" className="diagnosis-inset" defaultOpen
                digest={diagnosis?.headline ?? (diagnosisState === "running" ? "investigating…" : "not run")}
                badge={diagnosis
                  ? <span className={`diagnosis-assessment ${diagnosis.assessment}`}>{diagnosis.assessment.replace(/_/g, " ")}</span>
                  : <span className="classification-state">{diagnosisState === "running" ? "Investigating…" : diagnosisState === "failed" ? "Unavailable" : "Not run"}</span>}
                hint={<ExplainerHint
                  title="How this diagnosis was reached" subject="the diagnosis"
                  stages={diagnosisStages(diagnosis, diagnosisTools)}
                  footnote="Historical replay of a static export. A diagnosis describes what the evidence looks like; it is not a confirmed breach, an attribution, or a response."
                />}
              >
                {diagnosis ? (
                  <>
                    {diagnosis.situation_type && (
                      <p className="classification-type" data-testid="diagnosis-type">
                        {diagnosis.situation_type}
                        <small>{diagnosis.situation_type_supported
                          ? "closest MITRE ATT&CK type returned in this run"
                          : "unverified: no document returned in this run carries this title"}</small>
                      </p>
                    )}
                    <p className="diagnosis-headline">{mention(diagnosis.headline)}</p>
                    <p className="diagnosis-narrative">{mention(diagnosis.narrative)}</p>
                    <button type="button" className="classification-toggle" aria-expanded={diagnosisDetail} onClick={() => setDiagnosisDetail((value) => !value)}>
                      {diagnosisDetail ? "Hide" : "Show"} what it rests on and what would change it
                    </button>
                    {diagnosisDetail && (
                      <div className="classification-detail">
                        <b>Rests on</b>
                        <ul>{diagnosis.supporting_observations.map((line) => <li key={line}>{mention(line)}</li>)}</ul>
                        <b>Would change the call</b>
                        <ul>{diagnosis.would_change_the_call.map((line) => <li key={line}>{mention(line)}</li>)}</ul>
                        {diagnosis.citations.length > 0 && <>
                          <b>Cited types</b>
                          <ul>{diagnosis.citations.map((cite) => (
                            <li key={cite.type_id || cite.label}>
                              <button
                                type="button" className="citation-open"
                                aria-expanded={openDocId === cite.type_id}
                                onClick={() => {
                                  if (openDocId === cite.type_id) { setOpenDocId(""); setOpenDoc(null); return; }
                                  setOpenDocId(cite.type_id); setOpenDoc(null);
                                  api.knowledgeType(cite.type_id)
                                    .then(setOpenDoc)
                                    .catch((err: Error) => setOpenDoc({ error: err.message }));
                                }}
                              >
                                <code>{cite.source}</code> {cite.label} <small>{cite.commit}</small>
                              </button>
                              {openDocId === cite.type_id && <CitationDocument document={openDoc} />}
                            </li>
                          ))}</ul>
                        </>}
                        {diagnosis.unsupported_citations.length > 0 && (
                          <p className="classification-meta">Dropped as unsupported by this run: {diagnosis.unsupported_citations.join(", ")}</p>
                        )}
                        {diagnosis.evidence_ids.length > 0 && <>
                          <b>Cited records</b>
                          <ul className="diagnosis-ids">{diagnosis.evidence_ids.map((id) => <li key={id}><ResourceChip value={id} /></li>)}</ul>
                        </>}
                        <p className="classification-meta">{diagnosis.confidence} confidence · {diagnosis.model} · {diagnosis.elapsed_ms} ms</p>
                      </div>
                    )}
                    <div className="diagnosis-followup">
                      <button type="button" onClick={() => onAskAgent(`You diagnosed this situation as "${diagnosis.headline}". Take the investigation further: reconstruct the timeline, test the alternatives you set aside, and cite the ADX evidence you use.`)}>
                        <Sparkles size={12} /> Take it further in chat
                      </button>
                      <button type="button" onClick={() => selected && runDiagnosis(selected)}>
                        <Stethoscope size={12} /> Investigate again
                      </button>
                    </div>
                  </>
                ) : diagnosisState === "running" ? (
                  <div className="diagnosis-progress" role="status">
                    <span className="thinking"><i />{diagnosisActivity || "Investigating…"}</span>
                    {diagnosisTools.length > 0 && <p>{diagnosisTools.join(" · ")}</p>}
                  </div>
                ) : (
                  <div className="diagnosis-progress">
                    <p>{diagnosisState === "failed"
                      ? `Investigation unavailable: ${diagnosisError}`
                      : "Nothing has been investigated yet."}</p>
                    <button type="button" className="primary-button wide" onClick={() => selected && runDiagnosis(selected)}>
                      <Stethoscope size={13} /> {diagnosisState === "failed" ? "Retry investigation" : "Investigate"}
                    </button>
                  </div>
                )}
              </Section>
              <Section
                id="sequence" title="Sequence of events" className="sequence-inset" defaultOpen
                digest={sequence
                  ? `${sequence.steps.length} steps`
                  : sequenceState === "running" ? "writing…" : "not run"}
                badge={<span className="classification-state">{sequence
                  ? `${sequence.steps.length} steps`
                  : sequenceState === "running" ? "Writing…"
                  : sequenceState === "failed" ? "Unavailable" : "Not run"}</span>}
              >
                {sequence && sequence.steps.length > 0 ? (
                  <>
                    <ol className="sequence-steps" data-testid="sequence-steps">
                      {sequence.steps.map((step, index) => {
                        const open = openSteps.has(index);
                        const panelId = `sequence-step-panel-${index}`;
                        return (
                          <li key={`${index}-${step.description}`} className={`sequence-step ${open ? "open" : ""}`}>
                            <button
                              type="button" className="sequence-step-toggle"
                              aria-expanded={open} aria-controls={panelId}
                              onClick={() => setOpenSteps((current) => {
                                const next = new Set(current);
                                if (!next.delete(index)) next.add(index);
                                return next;
                              })}
                            >
                              <ChevronDown size={10} className={open ? "" : "closed"} aria-hidden="true" />
                              <time>{step.timestamp || "no timestamp recorded"}</time>
                              <small>{open ? "hide the records behind this step" : "show the records behind this step"}</small>
                            </button>
                            <span className="sequence-step-line">{mention(step.description)}</span>
                            {open && (
                              <div className="sequence-evidence" id={panelId} data-testid={`sequence-evidence-${index}`}>
                                {step.evidence.map((item) => (
                                  <SequenceEvidenceCard key={item.evidence_id} evidence={item} />
                                ))}
                                {step.unsupported_evidence_ids.length > 0 && (
                                  <p className="classification-meta">Cited for this step but returned by no tool in this run, so nothing is shown for it: {step.unsupported_evidence_ids.join(", ")}</p>
                                )}
                                {step.evidence.length === 0 && step.unsupported_evidence_ids.length === 0 && (
                                  <p className="classification-meta">No telemetry record was attached to this step, so it rests on the surrounding sequence rather than a row of its own.</p>
                                )}
                              </div>
                            )}
                          </li>
                        );
                      })}
                    </ol>
                    {sequence.ordering_note && (
                      <p className="classification-meta">{sequence.ordering_note}</p>
                    )}
                  </>
                ) : sequenceState === "running" ? (
                  <div className="diagnosis-progress" role="status">
                    <span className="thinking"><i />Writing the sequence of events…</span>
                  </div>
                ) : (
                  <div className="diagnosis-progress">
                    <p>{sequenceState === "failed"
                      ? "The investigation ended without recording a sequence of events."
                      : "The ordered sequence appears here once the investigation records its diagnosis."}</p>
                  </div>
                )}
              </Section>
              <div className="metric-grid" role="group" aria-label="Situation metrics — select one to see how it was derived">
                {metrics.map((metric) => {
                  const open = openMetric === metric.metric_id;
                  return (
                    <button
                      key={metric.metric_id}
                      type="button"
                      className={`metric-cell ${open ? "open" : ""}`}
                      aria-expanded={open}
                      aria-controls={`metric-panel-${metric.metric_id}`}
                      onClick={() => setOpenMetric(open ? null : metric.metric_id)}
                    >
                      <b>{metric.value}</b>
                      <span>{metric.label}</span>
                      <small><Info size={10} aria-hidden="true" />{open ? "Hide derivation" : "How is this derived?"}</small>
                    </button>
                  );
                })}
              </div>
              {openEntry && (
                <div className="metric-panel" id={`metric-panel-${openEntry.metric_id}`}>
                  <header>
                    <b>{openEntry.label}</b>
                    <span>{openEntry.value}</span>
                    <button type="button" onClick={() => setOpenMetric(null)} aria-label={`Hide ${openEntry.label} derivation`}><ChevronDown size={13} /></button>
                  </header>
                  <p className="metric-definition">{openEntry.definition}</p>
                  <div className="metric-derivation"><b>Derivation</b><code>{openEntry.derivation}</code></div>
                  {openEntry.contributions.length > 0 && (
                    <ul className="metric-contributions" aria-label={`${openEntry.label} contributions`}>
                      {openEntry.contributions.map((item, index) => (
                        <li key={`${item.source}-${index}`}>
                          <code>{item.source}</code>
                          <span>{item.detail}</span>
                          <b>{item.value}</b>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
              <div className="pattern-board">
                {selected.patterns.map((pattern, index) => {
                  const open = openPatterns.has(pattern.rule_id);
                  return (
                    <article key={pattern.detector} className={open ? "open" : ""}>
                      <button
                        type="button" className="pattern-head" aria-expanded={open}
                        onClick={() => setOpenPatterns((previous) => {
                          const next = new Set(previous);
                          if (next.has(pattern.rule_id)) next.delete(pattern.rule_id); else next.add(pattern.rule_id);
                          return next;
                        })}
                      >
                        <span className="step">{String(index + 1).padStart(2, "0")}</span>
                        <span className="pattern-headline">
                          <b>{pattern.label}</b>
                          <small>{pattern.derivation ? `${pattern.derivation.observed.qualification_test} · ${pattern.detector}` : pattern.detector}</small>
                        </span>
                        <strong
                          className="pattern-count"
                          title={`${pattern.count} EventsUnified record(s) counted by ${pattern.detector} that met its threshold test.`}
                        >
                          <b>{pattern.count}</b><small>qualified events</small>
                        </strong>
                      </button>
                      {open && (
                        <div className="pattern-body">
                          {pattern.derivation
                            ? <DerivedExplanation explanation={pattern.derivation} observed={pattern.derivation.observed} />
                            : <p>{pattern.summary}</p>}
                          <code>{pattern.detector}</code>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
              <div className="boundary-note">
                <b>Evidence boundary</b> Rows are a static historical export replayed for review. Nothing shown is live monitoring, detection, prevention, or containment.
                <ul>
                  {selected.patterns.map((pattern) => (
                    <li key={pattern.rule_id}>
                      <code>{pattern.rule_id}</code>{" "}
                      {pattern.derivation
                        ? `counted ${pattern.derivation.observed.event_count} record(s) and returned ${pattern.derivation.observed.evidence_ids_returned} sampled resource_id value(s) from ${pattern.derivation.observed.returned_columns.join(", ")}.`
                        : pattern.evidence_semantics}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          ) : <div className="empty-state"><Pin size={25} /><b>No situation selected</b><p>Run the scanner and select a situation to pin it here.</p></div>
        )}

        {tab === "tools" && (
          <div className="tools-view">
            <p className="section-copy">These are real, bounded ADX queries. Run one directly, or ask the agent to choose and execute a query.</p>
            <div className="tool-grid">
              {tools.map((tool) => {
                const Icon = tool.icon;
                return <button key={tool.id} className="tool-button" onClick={() => runTool(tool.id, tool.category, tool.query)} disabled={activeTool !== null}>
                  <Icon size={17} /><span><b>{tool.label}</b><small>{activeTool === tool.id ? "Running against ADX…" : "Run query"}</small></span>
                </button>;
              })}
            </div>
            {current && <div className="query-running">Running {current.label}…</div>}
            {queryRender && <ToolRenderModelView model={queryRender} />}
            <button className="agent-link" onClick={() => onAskAgent("Choose an ADX query that best explains the selected situation, run it, and explain the result.")}>Let the agent choose a tool →</button>
          </div>
        )}

        {tab === "evidence" && (
          selected ? (
            <div className="evidence-view">
              <p className="section-copy">Bounded row evidence cited by the situation envelope. Stable identity is <code>resource_id</code>.</p>
              {evidenceRender ? <ToolRenderModelView model={evidenceRender} /> : <div className="query-running">Loading evidence from ADX…</div>}
            </div>
          ) : <div className="empty-state"><Database size={25} /><b>No evidence context</b><p>Select a situation first.</p></div>
        )}
        {tab === "graph" && <GraphPanel scenarioWindow={graphWindow} focusRequest={focusRequest} selectionRequest={selectionRequest} wide={board.active} />}
        {error && <div className="error-box">{error}</div>}
      </div>
      {/* On the graph tab the selection is already drawn as rings, so the tray steps aside. */}
      {board.active && <FullscreenExit onExit={board.exit} label="tool board" />}
      {tab !== "graph" && <EntityTray
        picked={picked} max={MAX_PICKED}
        onRemove={(id) => setPicked((current) => current.filter((item) => item.id !== id))}
        onClear={() => setPicked([])}
        onVisualize={() => visualize(picked.map((item) => item.id))}
      />}
    </section>
  );
}

/** One telemetry record behind a sequence step, with the retrieval the server observed. */
function SequenceEvidenceCard({ evidence }: { evidence: StepEvidence }) {
  const fields = Object.entries(evidence.record);
  const { retrieval } = evidence;
  return (
    <div className="sequence-record">
      <ResourceChip value={evidence.evidence_id} />
      <dl className="sequence-record-fields">
        {fields.map(([key, value]) => (
          <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>
        ))}
      </dl>
      <p className="sequence-provenance">
        <span>Retrieved by {retrieval.display_name} · <code>{retrieval.query}</code></span>
        <span>From {retrieval.datasource}</span>
        <span>Returned {retrieval.row_count} row{retrieval.row_count === 1 ? "" : "s"} at {retrieval.retrieved_at}</span>
      </p>
    </div>
  );
}

function CitationDocument({ document }: { document: Record<string, unknown> | null }) {
  const [full, setFull] = useState(false);
  if (document === null) return <p className="citation-doc loading">Loading the corpus document…</p>;
  if (typeof document.error === "string") return <p className="citation-doc error">{document.error}</p>;
  const symptoms = Array.isArray(document.symptoms) ? document.symptoms.map(String) : [];
  const techniques = Array.isArray(document.technique_ids) ? document.technique_ids.map(String) : [];
  const source = String(document.definition ?? "");
  const clipped = !full && source.length > 900;
  // Cutting mid-markup is what produced the dangling syntax, so clip on a sentence.
  const shown = clipped ? `${source.slice(0, source.lastIndexOf(". ", 900) + 1 || 900)}` : source;
  const rendered = renderCorpusText(shown || "No definition recorded.");
  const logic = String(document.logic ?? "");
  return (
    <div className="citation-doc">
      <div className="corpus-body">{rendered.body}</div>
      {clipped && <button type="button" className="corpus-more" onClick={() => setFull(true)}>Show the whole definition</button>}
      {logic && <CodeBlock language={String(document.logic_language ?? "")} caption="Detection logic as published">{logic}</CodeBlock>}
      {rendered.citations.length > 0 && (
        <p className="corpus-citations"><b>Cites</b> {rendered.citations.join(" · ")}</p>
      )}
      {techniques.length > 0 && <p className="citation-meta">Techniques: {techniques.join(", ")}</p>}
      {symptoms.length > 0 && <><b>Identification signs</b><ul>{symptoms.slice(0, 8).map((line) => <li key={line}>{line}</li>)}</ul></>}
      <p className="citation-meta">{String(document.path ?? "")}</p>
      <p className="citation-meta">licence {String(document.license ?? "unverified")} · commit {String(document.commit ?? "")}</p>
    </div>
  );
}
