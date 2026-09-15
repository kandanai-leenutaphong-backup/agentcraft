import { CSSProperties, useEffect, useRef, useState } from "react";
import { ResourceExplorer } from "@components/resource_explorer/frontend";
import { api, streamScan } from "../shared/api";
import { useSituationFlows } from "../features/investigation";
import type { Caller } from "../shared/api";
import { ScannerPanel } from "../features/scanner";
import { ToolBoard } from "../features/investigation";
import { ChatPanel } from "../features/chat";
import { AgentEditor } from "../features/agent-editor";
import type { AgentIdentity, EvidenceRun, RuleDefinition, RuleRun, ScanResponse, Scenario, Situation } from "../shared/types";
import { ConfigurationDialog } from "./ConfigurationDialog";
import { Header, type Workspace } from "./Header";
import { useResizableColumns } from "./useResizableColumns";

const toDateTimeLocal = (value: string) => value.replace(" ", "T").replace(/Z$/, "").slice(0, 16);
const toUtc = (value: string) => `${value}:00Z`;

export default function App() {
  const [workspace, setWorkspace] = useState<Workspace>("investigation");
  const [selected, setSelected] = useState<Situation | null>(null);
  const [scan, setScan] = useState<ScanResponse | null>(null);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [rules, setRules] = useState<RuleDefinition[]>([]);
  const [scenarioId, setScenarioId] = useState("");
  const [graphWindow, setGraphWindow] = useState<{ id: number; start: string; end: string; label: string } | null>(null);
  const [entityRequest, setEntityRequest] = useState<{ id: number; nodeId: string; name: string; label: string } | null>(null);
  const [investigateRequest, setInvestigateRequest] = useState<{ id: number } | null>(null);
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [scanLoading, setScanLoading] = useState(false);
  const [scanError, setScanError] = useState("");
  const [situations, setSituations] = useState<Situation[]>([]);
  const [ruleRuns, setRuleRuns] = useState<RuleRun[]>([]);
  const [evidenceRuns, setEvidenceRuns] = useState<Record<string, EvidenceRun>>({});
  const [health, setHealth] = useState<"checking" | "ok" | "degraded">("checking");
  const [caller, setCaller] = useState<Caller | null>(null);
  const [investigator, setInvestigator] = useState<AgentIdentity | null>(null);
  const [requestedPrompt, setRequestedPrompt] = useState<{ id: number; text: string } | null>(null);
  const [scenariosLoading, setScenariosLoading] = useState(true);
  const { columns, shell, resizerProps } = useResizableColumns([25, 45, 30]);
  const configuration = useRef<HTMLDialogElement>(null);
  // One owner for the situation workloads: the board keeps the results, a chat tab shows the run.
  const flows = useSituationFlows(selected);

  useEffect(() => {
    if (workspace !== "investigation") return;
    const controller = new AbortController();
    api.agents(controller.signal).then(({ agents }) => {
      const agent = agents[0];
      if (agent && !controller.signal.aborted) setInvestigator({ id: agent.id, name: agent.name,
        model: agent.model, version: agent.config_version });
    }).catch(() => {});
    return () => controller.abort();
  }, [workspace]);

  useEffect(() => {
    api.health().then((value) => setHealth(value.status === "ok" ? "ok" : "degraded")).catch(() => setHealth("degraded"));
    // Who the server says we are, not who the page assumed. A failure here is silent on
    // purpose: the gate already refused anything that matters, so an absent chip is a
    // cosmetic loss rather than a reason to interrupt the analyst.
    api.whoami().then(setCaller).catch(() => setCaller(null));
    api.scenarios().then(setScenarios).catch((error: Error) => setScanError(`Could not load test scenarios: ${error.message}`)).finally(() => setScenariosLoading(false));
    api.rules().then(setRules).catch(() => setRules([]));
  }, []);

  function ask(text: string) { setRequestedPrompt({ id: Date.now(), text }); }

  function selectScenario(id: string) {
    setScenarioId(id);
    const scenario = scenarios.find((item) => item.id === id);
    if (!scenario) return;
    setWindowStart(toDateTimeLocal(scenario.start));
    setWindowEnd(toDateTimeLocal(scenario.end));
    // The graph tab follows the scenario so both panels describe the same interval.
    setGraphWindow({ id: Date.now(), start: scenario.start, end: scenario.end, label: scenario.name });
    setScanError("");
  }

  async function runScan() {
    if (!windowStart || !windowEnd) return;
    const start = toUtc(windowStart);
    const end = toUtc(windowEnd);
    if (new Date(end) <= new Date(start)) {
      setScanError("Window end must be after window start.");
      return;
    }
    setScanLoading(true); setScanError(""); setScan(null); setSelected(null); setSituations([]); setEvidenceRuns({});
    setRuleRuns(rules.map((rule) => ({ rule_id: rule.rule_id, label: rule.label, version: rule.version, status: "pending" })));
    try {
      await streamScan(start, end, ({ type, data }) => {
        if (type === "rule_started") {
          setRuleRuns((runs) => runs.map((run) => run.rule_id === data.rule_id ? { ...run, label: data.name, version: data.version, description: data.description, role: data.role, evidence_semantics: data.evidence_semantics, explanation: data.explanation, status: "running" } : run));
        } else if (type === "rule_completed") {
          setRuleRuns((runs) => runs.map((run) => run.rule_id === data.rule_id ? { ...run, label: data.name, version: data.version, description: data.description, role: data.role, evidence_semantics: data.evidence_semantics, explanation: data.explanation, observation: data.observation, status: data.hit_count > 0 ? "hit" : "miss", hit_count: data.hit_count, elapsed_ms: data.elapsed_ms } : run));
        } else if (type === "situation_partial" || type === "situation") {
          setSituations((items) => {
            const index = items.findIndex((item) => item.situation_id === data.situation_id);
            return index < 0 ? [...items, data] : items.map((item) => item.situation_id === data.situation_id ? data : item);
          });
          setSelected((current) => !current || current.situation_id === data.situation_id ? data : current);
        } else if (type === "evidence_started" || type === "evidence_completed") {
          const key = `${data.situation_id}:${data.rule_id}`;
          setEvidenceRuns((runs) => ({ ...runs, [key]: type === "evidence_started" ? { status: "running" } : { status: "complete", evidence_count: data.evidence_count } }));
        } else if (type === "done") {
          setScan(data); setSituations(data.situations); setSelected(data.situations[0] ?? null);
        } else if (type === "error") {
          throw new Error(`${data.error_code}: ${data.message}`);
        }
      });
    } catch (error) {
      setScanError(error instanceof Error ? error.message : "ADX replay scan failed.");
    } finally {
      setScanLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <Header workspace={workspace} onWorkspaceChange={setWorkspace} configuration={configuration} />
      <ConfigurationDialog dialog={configuration} health={health} caller={caller} investigator={investigator} />
      {/* All workspaces stay mounted: switching tabs must not discard a scan,
          a chat session, or a half-read inventory pane. */}
      <div id="workspace-investigation" className="workspace" role="tabpanel"
           aria-labelledby="tab-investigation" hidden={workspace !== "investigation"}>
      {/* Widths travel as custom properties, not as grid-template-columns. As a
          direct declaration the inline style outranked every media query, so the
          three desktop columns survived onto a phone and the chat drawer painted
          over the tab strip. */}
      <main ref={shell} className="three-column resizable-columns" style={{ "--col-a": `${columns[0]}fr`, "--col-b": `${columns[1]}fr`, "--col-c": `${columns[2]}fr` } as CSSProperties}>
        <ScannerPanel selected={selected} onSelect={setSelected} result={scan} situations={situations} ruleRuns={ruleRuns} evidenceRuns={evidenceRuns} loading={scanLoading} error={scanError} requestedStart={windowStart ? toUtc(windowStart) : ""} requestedEnd={windowEnd ? toUtc(windowEnd) : ""} scenarios={scenarios} scenariosLoading={scenariosLoading} scenarioId={scenarioId} windowStart={windowStart} windowEnd={windowEnd} onScenarioChange={selectScenario} onWindowStartChange={setWindowStart} onWindowEndChange={setWindowEnd} onRunScan={runScan} onOpenEntity={setEntityRequest} onInvestigate={(situation) => {
          setSelected(situation); setInvestigateRequest({ id: Date.now() });
        }} />
        <div {...resizerProps(0, "Resize scanner and tool board")} />
        <ToolBoard selected={selected} scanElapsed={scan?.summary.elapsed_ms ?? null} ruleExecutions={scan?.rule_executions ?? []} scanWindow={scan ? { start: scan.window_start, end: scan.window_end } : null} graphWindow={graphWindow} entityRequest={entityRequest} investigateRequest={investigateRequest} onAskAgent={ask} flows={flows} />
        <div {...resizerProps(1, "Resize tool board and agent chat")} />
        <ChatPanel situation={selected} requestedPrompt={requestedPrompt} flows={flows} investigator={investigator} />
      </main>
      </div>
       <div id="workspace-explorer" className="workspace" role="tabpanel"
         aria-labelledby="tab-explorer" hidden={workspace !== "explorer"}>
        <ResourceExplorer active={workspace === "explorer"} loadAgents={api.agents} />
      </div>
      <div id="workspace-agent-editor" className="workspace" role="tabpanel"
           aria-labelledby="tab-agent-editor" hidden={workspace !== "agent-editor"}>
        <AgentEditor active={workspace === "agent-editor"} onAssigned={(agent) => setInvestigator({
          id: agent.agent_id, name: agent.name, model: agent.model, version: agent.version,
        })} />
      </div>
    </div>
  );
}
