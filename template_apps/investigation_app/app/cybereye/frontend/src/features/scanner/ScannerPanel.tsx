import { useEffect, useState } from "react";
import { ChevronDown, Play, Radar, ShieldAlert } from "lucide-react";
import { DerivedExplanation } from "./DerivedExplanation";
import { linkEntities, useEntityIndex } from "../../shared/ui";
import { ExplainerHint, type ExplainerStage } from "../../shared/ui";
import { RoleBadge } from "./RoleBadge";
import { RecordGrid, type GridColumn } from "./RecordGrid";
import { formatUtc } from "./humanize";
import type { EvidenceRun, RuleRun, ScanResponse, Scenario, Situation, Pattern } from "../../shared/types";

function UtcStamp({ value, precise = true }: { value: string; precise?: boolean }) {
  const { date, time } = formatUtc(value);
  // Sub-second digits belong in the cited evidence, not in a summary cell.
  const shown = precise ? time : time.replace(/\.\d+/, "").replace(" UTC", "");
  return <span className="utc-stamp"><span>{date}</span>{shown && <span>{shown}</span>}</span>;
}

interface Props {
  selected: Situation | null;
  onSelect: (situation: Situation) => void;
  onInvestigate: (situation: Situation) => void;
  result: ScanResponse | null;
  situations: Situation[];
  ruleRuns: RuleRun[];
  evidenceRuns: Record<string, EvidenceRun>;
  loading: boolean;
  error: string;
  requestedStart: string;
  requestedEnd: string;
  scenarios: Scenario[];
  scenariosLoading: boolean;
  scenarioId: string;
  windowStart: string;
  windowEnd: string;
  onScenarioChange: (id: string) => void;
  onWindowStartChange: (value: string) => void;
  onWindowEndChange: (value: string) => void;
  onRunScan: () => void;
  onOpenEntity: (request: { id: number; nodeId: string; name: string; label: string }) => void;
}

function scanStages(result: ScanResponse, ruleRuns: RuleRun[]): ExplainerStage[] {
  const hits = ruleRuns.filter((rule) => rule.status === "hit");
  const misses = ruleRuns.filter((rule) => rule.status === "miss");
  const qualified = ruleRuns.reduce((total, rule) => total + (rule.hit_count ?? 0), 0);
  return [
    {
      kind: "input", label: "Bounded UTC window",
      detail: `${result.window_start} → ${result.window_end}. Every rule query is filtered to this interval, so a situation outside it cannot appear here.`,
    },
    {
      kind: "compute", label: `${ruleRuns.length || "No"} registered rule${ruleRuns.length === 1 ? "" : "s"} dispatched concurrently`,
      detail: ruleRuns.length
        ? `Each rule is a fixed, versioned KQL statement — ${ruleRuns.map((rule) => rule.rule_id).join(", ")}. No model writes or edits these queries.`
        : "The rule set is fixed and versioned in the backend detector.",
    },
    {
      kind: "corpus", label: "Read-only ADX EventsUnified",
      detail: "Queries run against the immutable historical export. The scanner has no write path and cannot block, isolate, or alter anything.",
    },
    {
      kind: "compute", label: "Qualification against rule thresholds",
      detail: `${hits.length} rule${hits.length === 1 ? "" : "s"} returned groups over threshold and ${misses.length} did not. ${qualified} group${qualified === 1 ? "" : "s"} qualified in total. A completed query that qualifies nothing is a miss, not a failure.`,
    },
    {
      kind: "output", label: "Synthesis into situations",
      detail: `Qualified groups sharing a host and principal are merged into one situation, severity taken from the strongest contributing pattern. ${result.summary.situations} situation${result.summary.situations === 1 ? "" : "s"} (${result.summary.critical} critical) in ${result.summary.elapsed_ms} ms.`,
    },
  ];
}

const FACTOR_COLUMNS: GridColumn[] = [
  { key: "rule", label: "Rule" },
  { key: "score", label: "Score", align: "right", numeric: true, width: "38px" },
  { key: "test", label: "Events / test", align: "right", numeric: true, width: "78px" },
];

const RULE_COLUMNS: GridColumn[] = [
  { key: "rule", label: "Rule" },
  { key: "status", label: "Result", align: "right", width: "38px" },
  { key: "ms", label: "Groups / time", align: "right", numeric: true, width: "76px" },
];

/** Each rule contributes a fixed score; severity is a threshold ladder over the sum. */
function ScoreLadder({ pattern, situation, total }: { pattern: Pattern; situation: Situation; total: number }) {
  const anchors = situation.patterns.filter((item) => item.role === "anchor").length;
  const step = total >= 80 && anchors >= 2
    ? `${total} ≥ 80 with ${anchors} anchors → critical`
    : total >= 50 || situation.patterns.length >= 2
      ? `${total} ≥ 50 or ${situation.patterns.length} rules qualified → high`
      : total >= 25 ? `${total} ≥ 25 → medium` : `${total} < 25 → low`;
  return (
    <p className="score-ladder">
      <b>+{pattern.score}</b> is this rule’s fixed contribution, not a computed weight.
      It is one of {situation.patterns.length} summed to <b>{total}</b>. <code>{step}</code>
    </p>
  );
}

export function ScannerPanel({ selected, onSelect, onInvestigate, result, situations, ruleRuns, evidenceRuns, loading, error, requestedStart, requestedEnd, scenarios, scenariosLoading, scenarioId, windowStart, windowEnd, onScenarioChange, onWindowStartChange, onWindowEndChange, onRunScan, onOpenEntity }: Props) {
  const entityIndex = useEntityIndex();
  const mention = (text: string) => linkEntities(text, entityIndex, (entity) =>
    onOpenEntity({ id: Date.now(), nodeId: entity.id, name: entity.name, label: entity.label }));
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [openFactors, setOpenFactors] = useState<Set<string>>(new Set());
  const [rulesOpen, setRulesOpen] = useState(false);
  const [openRules, setOpenRules] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (situations.length) setExpanded((current) => new Set([...current, ...situations.map((item) => item.situation_id)]));
  }, [situations]);

  return (
    <section className="scanner panel-column" aria-label="CyberEye scanner">
      <div className="scanner-controls" aria-label="ADX scan controls">
        <label className="scanner-scenario">
          <span>Scenario</span>
          <select aria-label="Test Scenarios" value={scenarioId} onChange={(event) => onScenarioChange(event.target.value)} disabled={loading || scenariosLoading}>
            <option value="">{scenariosLoading ? "Loading scenarios…" : "Choose scenario…"}</option>
            {scenarios.map((scenario) => <option key={scenario.id} value={scenario.id}>{scenario.name}</option>)}
          </select>
        </label>
        <div className="scanner-window-row">
          <label><span>Start · UTC</span><input aria-label="Scan start UTC" type="datetime-local" value={windowStart} onChange={(event) => onWindowStartChange(event.target.value)} disabled={loading} /></label>
          <label><span>End · UTC</span><input aria-label="Scan end UTC" type="datetime-local" value={windowEnd} onChange={(event) => onWindowEndChange(event.target.value)} disabled={loading} /></label>
        </div>
        <button className="primary-button scanner-scan-button" onClick={onRunScan} disabled={loading || !windowStart || !windowEnd}>
          <Play size={13} fill="currentColor" /> {loading ? "Scanning…" : "Scan ADX window"}
        </button>
      </div>
      {ruleRuns.length > 0 && (
        <section className="rule-board" aria-label="Historical replay rule execution">
          <button className="rule-board-title" type="button" aria-expanded={rulesOpen} onClick={() => setRulesOpen((value) => !value)}><ChevronDown size={13} className={rulesOpen ? "" : "closed"} /><b>Rule execution</b><span>{ruleRuns.filter((rule) => rule.status === "hit").length} hit · {ruleRuns.filter((rule) => rule.status === "miss").length} miss</span></button>
          {rulesOpen && <><div className="rule-window">{requestedStart} → {requestedEnd}</div>
          <RecordGrid
            className="rule-grid" caption="Rule execution"
            columns={RULE_COLUMNS} openIds={openRules}
            onToggle={(id) => setOpenRules((previous) => {
              const next = new Set(previous);
              // One explanation at a time: stacked panels are what made this disorienting.
              if (next.has(id)) next.delete(id); else { next.clear(); next.add(id); }
              return next;
            })}
            rows={ruleRuns.map((rule) => ({
              id: rule.rule_id,
              tone: rule.status,
              cells: {
                rule: <span className="rgrid-name"><i className={`rgrid-dot ${rule.status}`} /><b title={`${rule.rule_id} · v${rule.version}`}>{rule.label}</b></span>,
                status: <span className={`rgrid-status ${rule.status}`}>{rule.status}</span>,
                ms: <span className="rgrid-stack right"><b>{rule.hit_count ?? "—"}</b><small>{rule.elapsed_ms === undefined ? "—" : `${rule.elapsed_ms} ms`}</small></span>,
              },
              detail: (
                <div className="rule-explanation">
                  {rule.explanation
                    ? <DerivedExplanation explanation={rule.explanation} observation={rule.observation} />
                    : <p className="derived-caption">Query structure is derived once the rule starts.{rule.description ? ` ${rule.description}` : ""}</p>}
                </div>
              ),
            }))}
          />
          {loading && <p className="scan-live" role="status">Queries are running against the selected historical replay window. A completed query may be a miss.</p>}
          </>}
        </section>
      )}
      {error && <div className="error-box" role="alert"><b>Replay scan failed</b><span>{error}</span></div>}

      {(result || situations.length > 0) && (
        <>
          {result && <div className="scanned-window">
            <span className="scanned-window-head">
              <ExplainerHint
                title="How this scan was performed" subject="the scan result"
                stages={scanStages(result, ruleRuns)}
                footnote="Historical replay of a static export. Absence of a situation means no registered rule qualified in this window, not that the window is safe."
              />
              <b>Scanned UTC interval</b>
            </span>
            <span>{result.window_start} → {result.window_end}</span>
          </div>}
          {result && <div className="summary-strip">
            <span><b>{result.summary.situations}</b> situations</span>
            <span className="critical"><b>{result.summary.critical}</b> critical</span>
            <span><b>{result.summary.elapsed_ms}</b> ms</span>
          </div>}
          <div className="situation-list">
            {situations.map((situation) => {
              const open = expanded.has(situation.situation_id);
              return (
                <article key={situation.situation_id} className={`situation ${selected?.situation_id === situation.situation_id ? "selected" : ""}`}>
                  <button className="situation-head" onClick={() => {
                    onSelect(situation);
                    setExpanded((previous) => {
                      const next = new Set(previous);
                      if (next.has(situation.situation_id)) next.delete(situation.situation_id); else next.add(situation.situation_id);
                      return next;
                    });
                  }}>
                    <ChevronDown size={14} className={open ? "" : "closed"} />
                    <ShieldAlert size={15} />
                    <span className="situation-identity"><b>{situation.host}</b><small>{situation.principal}</small></span>
                    <span className={`severity ${situation.severity}`}>{situation.severity}</span>
                  </button>
                  {open && (
                    <div className="situation-body">
                      <div className="situation-meta">
                        <span title="Distinct deterministic rules that returned at least one threshold-qualified group for this entity.">{situation.detector_count} rules qualified</span>
                        <span title="Categorical confidence assigned by the synthesis policy from summed rule scores and anchor count.">{situation.confidence} confidence</span>
                        <span>{result ? "final" : "provisional"}</span>
                      </div>
                      <RecordGrid
                        caption="Rules that qualified this entity"
                        columns={FACTOR_COLUMNS}
                        openIds={openFactors}
                        onToggle={(id) => setOpenFactors((previous) => {
                          const next = new Set(previous);
                          if (next.has(id)) next.delete(id); else next.add(id);
                          return next;
                        })}
                        rows={situation.patterns.map((pattern) => {
                          const evidence = evidenceRuns[`${situation.situation_id}:${pattern.rule_id}`];
                          const total = situation.patterns.reduce((sum, item) => sum + item.score, 0);
                          return {
                            id: `${situation.situation_id}:${pattern.rule_id}`,
                            cells: {
                              rule: <span className="rgrid-stack"><b title={pattern.label}>{pattern.label}</b><RoleBadge role={pattern.role} /></span>,
                              score: <span className="rgrid-score">+{pattern.score}</span>,
                              test: <span className="rgrid-stack right"><b>{pattern.count}</b><small>{pattern.derivation?.observed.qualification_test ?? "—"}</small></span>,
                            },
                            detail: (
                              <div className="factor-body">
                                <ScoreLadder pattern={pattern} situation={situation} total={total} />
                                <p className="observed-fact"><b>Observed</b> {mention(pattern.observed_fact)}</p>
                                <dl className="fact-grid">
                                  <div><dt>Confidence</dt><dd>{pattern.confidence}</dd></div>
                                  <div><dt>Sampled ids</dt><dd className="num">{evidence?.evidence_count ?? pattern.evidence_ids.length}</dd></div>
                                  {pattern.first_seen === pattern.last_seen ? (
                                    <div className="span"><dt>Observed · UTC</dt><dd className="num"><UtcStamp value={pattern.first_seen} precise={false} /></dd></div>
                                  ) : (
                                    <>
                                      <div><dt>First seen · UTC</dt><dd className="num"><UtcStamp value={pattern.first_seen} precise={false} /></dd></div>
                                      <div><dt>Last seen · UTC</dt><dd className="num"><UtcStamp value={pattern.last_seen} precise={false} /></dd></div>
                                    </>
                                  )}
                                </dl>
                                <div className="factor-evidence" role="status">
                                  <b>Evidence</b>
                                  <span className="evidence-status">{evidence?.status ?? "pending"}</span>
                                </div>
                                <details className="factor-reasoning">
                                  <summary>How this rule decided, read from its own query</summary>
                                  {pattern.derivation
                                    ? <DerivedExplanation explanation={pattern.derivation} observed={pattern.derivation.observed} caption={false} />
                                    : <><p>{pattern.description}</p><p className="evidence-semantics">{pattern.evidence_semantics}</p></>}
                                </details>
                              </div>
                            ),
                          };
                        })}
                      />
                      <button className="investigate-button" onClick={() => onInvestigate(situation)}>Investigate</button>
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        </>
      )}
      {!result && !situations.length && !loading && !error && (
        <div className="empty-state"><Radar size={26} /><b>Scanner idle</b><p>Choose or edit the UTC window above, then run the deterministic ADX rules.</p></div>
      )}
    </section>
  );
}
