import { useEffect, useRef, useState } from "react";
import { Bot, ChevronRight, Code2, Database, RefreshCw, Wrench } from "lucide-react";
import { SourceCodeViewer } from "@harness/source-code";
import { InventoryExplorer } from "./InventoryExplorer";
import { ExplorerLayout } from "./ExplorerLayout";
import type { ClientOptions } from "./client";

export interface AgentDatasource {
  kind: string;
  label: string;
  target: string;
  target_label: string;
  endpoint: string;
  configured: boolean;
}

export interface AgentToolInfo {
  id: string;
  name: string;
  description: string;
  category: string;
  fallback: boolean;
  parameters: {
    properties?: Record<string, { type?: string; description?: string }>;
    required?: string[];
  };
  datasource: AgentDatasource;
  datasources?: AgentDatasource[];
  datasource_ids?: string[];
  source: {
    available: boolean; path: string; start_line: number; code: string; truncated: boolean;
  };
}

export interface AgentCatalogueEntry {
  id: string;
  name: string;
  description: string;
  model: string;
  config_id: string;
  config_version: number;
  config_digest: string;
  tools: AgentToolInfo[];
}

export interface ResourceExplorerProps extends ClientOptions {
  active?: boolean;
  previewRows?: number;
  loadAgents: (signal: AbortSignal) => Promise<{ agents: AgentCatalogueEntry[] }>;
}

const NO_DEPENDENCIES: readonly string[] = [];

export function ResourceExplorer({ active = true, loadAgents, previewRows,
  ...clientOptions }: ResourceExplorerProps) {
  const [agents, setAgents] = useState<AgentCatalogueEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [refresh, setRefresh] = useState(0);
  const [selected, setSelected] = useState<{ agent: string; tool: string } | null>(null);
  const [viewer, setViewer] = useState<"source" | "tool">("source");
  const viewerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    loadAgents(controller.signal).then((value) => {
      if (!controller.signal.aborted) setAgents(value.agents);
    }).catch((failure: unknown) => {
      if (!controller.signal.aborted) setError(failure instanceof Error ? failure.message : String(failure));
    }).finally(() => {
      if (!controller.signal.aborted) setLoading(false);
    });
    return () => controller.abort();
  }, [active, loadAgents, refresh]);

  const agent = agents.find((item) => item.id === selected?.agent);
  const tool = agent?.tools.find((item) => item.id === selected?.tool);
  const toolVisible = viewer === "tool";

  function showViewer(kind: "source" | "tool") {
    setViewer(kind);
    if (window.matchMedia("(max-width: 700px)").matches) {
      requestAnimationFrame(() => viewerRef.current?.scrollIntoView({ block: "start" }));
    }
  }

  return <InventoryExplorer {...clientOptions} previewRows={previewRows}
    onSelect={() => showViewer("source")} selectionActive={!toolVisible}
    highlightedSourceIds={toolVisible ? tool?.datasource_ids ?? NO_DEPENDENCIES : NO_DEPENDENCIES}
    renderLayout={({ navigation, detail }) => (
      <ExplorerLayout navigation={navigation} viewerRef={viewerRef}
        heading={<><Code2 size={15} aria-hidden="true" />Viewer</>}
        subtitle={toolVisible ? "Tool details" : "Source details"} agents={<>
          <header className="rex-header">
            <h2>Agents &amp; tools</h2>
            <div className="rex-controls">
              <span role="status">{loading ? "Loading agents..." : `${agents.length} loaded`}</span>
              <button type="button" title="Refresh agents" aria-label="Refresh agents" disabled={loading}
                onClick={() => setRefresh((value) => value + 1)}><RefreshCw size={15} /></button>
            </div>
          </header>
          {error && <div className="agents-error" role="alert">
            <p>{error}</p><button type="button" onClick={() => setRefresh((value) => value + 1)}>
              <RefreshCw size={13} /> Retry
            </button>
          </div>}
          <div className="agents-tree">
            <details className="agents-root" open>
              <summary><ChevronRight size={14} /><b>Agents</b><small>{agents.length}</small></summary>
              {!loading && !error && agents.length === 0 && <p className="agents-empty">No agents loaded</p>}
              {agents.map((item) => <details className="agent-branch" key={item.id}>
                <summary><ChevronRight size={14} /><span>{item.name}</span><small>{item.tools.length}</small></summary>
                <div className="agent-runtime"><span>{item.model}</span><code>{item.config_digest}</code></div>
                {item.tools.length === 0 && <p className="agents-empty">No tools registered</p>}
                <div className="agent-tool-list">
                  {item.tools.map((entry) => <button type="button" key={entry.id} title={entry.id}
                    aria-pressed={toolVisible && selected?.agent === item.id && selected?.tool === entry.id}
                    onClick={() => { setSelected({ agent: item.id, tool: entry.id }); showViewer("tool"); }}>
                    <Wrench size={14} /><span>{entry.name}</span>
                  </button>)}
                </div>
              </details>)}
            </details>
          </div>
        </>}>
          <div className="rex-pane" hidden={toolVisible}>{detail}</div>
          <div className="rex-pane" hidden={!toolVisible}>
            <div className="agent-detail" aria-live="polite">
              {agent && tool ? <AgentToolDetail key={`${agent.id}:${tool.id}`} agent={agent} tool={tool} />
                : <div className="agent-no-selection"><Code2 size={25} /><span>No tool selected</span></div>}
            </div>
          </div>
      </ExplorerLayout>
    )} />;
}

export function AgentToolDetail({ agent, tool }: { agent: Pick<AgentCatalogueEntry, "name" | "model">; tool: AgentToolInfo }) {
  const sources = tool.datasources ?? [tool.datasource];
  const parameters = Object.entries(tool.parameters.properties ?? {});

  return <article data-testid="agent-tool-detail">
    <header className="agent-detail-header">
      <div className="agent-detail-context"><Bot size={14} /><span>{agent.name}</span><span>{agent.model}</span></div>
      <h2>{tool.name}</h2>
      <div className="agent-tool-identity"><code>{tool.id}</code><span>{tool.category}</span>
        {tool.fallback && <span className="agent-fallback">KQL fallback</span>}
      </div>
      <p>{tool.description}</p>
    </header>
    <section className="agent-datasource" aria-label="Tool datasources">
      <h3><Database size={15} />{sources.length === 1 ? "Datasource" : "Datasources"}</h3>
      {sources.map((source, index) => <dl key={index}>
        <div><dt>Connection</dt><dd>{source.label}</dd></div>
        <div><dt>{source.target_label}</dt><dd><code>{source.target || "Not configured"}</code></dd></div>
        {source.endpoint && <div><dt>Endpoint</dt><dd><code>{source.endpoint}</code></dd></div>}
        <div><dt>Status</dt><dd className={source.configured ? "agent-configured" : "agent-unconfigured"}>
          {source.kind === "none" ? "Output only" : source.configured ? "Configured" : "Not configured"}
        </dd></div>
      </dl>)}
      {tool.fallback && <p className="agents-empty">Scope is determined by the submitted read-only KQL.</p>}
    </section>
    <section className="agent-source" aria-label="Tool source code">
      <h3><Code2 size={15} />Source code</h3>
      {tool.source.available ? <SourceCodeViewer code={tool.source.code} filename={tool.source.path}
        startLine={tool.source.start_line} truncated={tool.source.truncated} />
        : <p className="agents-empty">Source preview unavailable for this tool</p>}
    </section>
    <details className="agent-parameters">
      <summary><ChevronRight size={14} /><span>Parameters</span><small>{parameters.length}</small></summary>
      <dl>{parameters.map(([name, parameter]) => <div key={name}>
        <dt><code>{name}</code><span>{parameter.type ?? "any"}
          {tool.parameters.required?.includes(name) ? " / required" : " / optional"}</span></dt>
        <dd>{parameter.description || "No description declared"}</dd>
      </div>)}</dl>
      {parameters.length === 0 && <p className="agents-empty">No parameters</p>}
    </details>
  </article>;
}