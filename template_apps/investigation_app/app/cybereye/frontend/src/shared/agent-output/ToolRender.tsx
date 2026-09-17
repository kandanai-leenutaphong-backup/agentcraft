import { ResultTable, ToolResultCard, type ToolResultCardProps } from "@agentcraft/modular-agents";
import "@agentcraft/modular-agents/card-styles";
import { AlertTriangle, Radar, SearchX } from "lucide-react";
import { CATEGORY_META, parseToolEnvelope, signalChips, text, type ScanBrief, type ToolRenderModel } from "./envelope";

const meta = (category: string, tool: string) =>
  CATEGORY_META[category] ?? { title: tool.replace(/_/g, " "), note: "Bounded result returned by a purpose-built replay tool." };

const SIGNAL_TONES = { neutral: "neutral", good: "success", warn: "warning", bad: "error" } as const;

/** Single render surface for every tool envelope, in the chat panel and the tool board alike. */
export function ToolRender({ value }: { value: unknown }) {
  return <ToolRenderModelView model={parseToolEnvelope(value)} />;
}

export function ToolRenderModelView({ model }: { model: ToolRenderModel }) {
  if (model.kind === "refusal") return <ToolResultCard className="trender" refusal={model.refusal} />;
  if (model.kind === "duplicate") return <ToolResultCard className="trender" duplicate={model.duplicate} />;

  if (model.kind === "error") {
    return (
      <div className="trender trender-bad" role="alert">
        <header className="trender-head">
          <div className="trender-identity"><b>Tool failed</b><code>{model.tool}</code></div>
          <div className="trender-badges"><span className="trender-badge bad">{model.errorCode}</span></div>
        </header>
        <p className="trender-note">{model.message}</p>
      </div>
    );
  }

  if (model.kind === "raw") {
    return (
      <div className="trender">
        <header className="trender-head">
          <div className="trender-identity"><b>Unrecognised envelope</b><code>{model.tool}</code></div>
        </header>
        <pre className="trender-raw">{model.text}</pre>
      </div>
    );
  }

  const { title, note } = meta(model.category, model.tool);
  const tone = model.kind === "situations" ? (model.scan.critical > 0 ? "bad" : "default")
    : model.kind === "empty" || model.fallback ? "warn" : "default";
  const shared = {
    className: `trender trender-${tone}`,
    ariaLabel: `${title} tool result`,
    header: <header className="trender-head">
      <div className="trender-identity"><b>{title}</b>
        <code title={model.category ? `${model.tool} · ${model.category}` : model.tool}>{model.tool}</code>
      </div>
    </header>,
    scope: model.scope,
    signal: signalChips(model).map((chip) => ({ ...chip, tone: SIGNAL_TONES[chip.tone] })),
    note: model.fallback ? "Model-authored KQL, outside the purpose-built tool set." : tone === "warn" ? note : null,
    noteTone: model.fallback ? "warning" : "info",
    notePosition: "before-signal",
    bandLabels: { scope: "Inputs", result: "Results" },
    scopeLabel: "Query inputs",
    signalLabel: "Result signals",
    resizable: false,
    classNames: { scope: "trender-scope", signal: "trender-signals", body: "trender-body", note: `trender-advisory ${model.fallback ? "warn" : ""}` },
  } satisfies ToolResultCardProps;

  if (model.kind === "situations") {
    return (
      <ToolResultCard {...shared}>
        <p className="trender-window">{model.scan.window_start} → {model.scan.window_end}</p>
        <SituationChips scan={model.scan} />
      </ToolResultCard>
    );
  }

  if (model.kind === "empty") {
    return (
      <ToolResultCard {...shared}>
        <div className="trender-empty">
          {model.category === "not_found" ? <SearchX size={18} /> : <AlertTriangle size={18} />}
          <p>{model.reason}</p>
        </div>
      </ToolResultCard>
    );
  }

  const columns = model.columns.slice(0, 8);
  const rows = model.rows.slice(0, 12).map((row) => columns.map((_column, cell) => text(row[cell])));
  const hiddenRows = model.rowCount - rows.length;
  const hiddenColumns = model.columns.length - columns.length;
  return (
    <ToolResultCard {...shared}>
      <div className="trender-table">
        <div className="trender-table-scroll" tabIndex={0} role="group" aria-label="Bounded result rows, horizontally scrollable">
          <ResultTable headers={columns} rows={rows} previewRows={rows.length} maxHeightClass="" />
        </div>
        <p className="trender-cap">
          Showing {rows.length} of {model.rowCount} returned row{model.rowCount === 1 ? "" : "s"}
          {hiddenRows > 0 ? ` · ${hiddenRows} more not rendered` : ""}
          {hiddenColumns > 0 ? ` · ${hiddenColumns} more column${hiddenColumns === 1 ? "" : "s"} not rendered` : ""}
          {model.maxRows !== null ? ` · query row cap ${model.maxRows}` : ""}
          {model.truncated ? " · result hit the row cap and is truncated" : ""}
        </p>
      </div>
    </ToolResultCard>
  );
}

function SituationChips({ scan }: { scan: ScanBrief }) {
  if (!scan.situations.length) {
    return <div className="trender-empty"><Radar size={18} /><p>No rule qualified an entity in this replay window.</p></div>;
  }
  return (
    <ul className="trender-situations" aria-label="Situation envelopes returned">
      {scan.situations.slice(0, 6).map((situation) => (
        <li key={situation.situation_id}>
          <span className={`trender-sev ${situation.severity}`}>{situation.severity}</span>
          <span className="trender-entity">
            <b>{situation.host}</b>
            <small>{situation.principal}</small>
          </span>
          <span className="trender-rules" title={situation.rule_ids.join(", ") || "no rule ids returned"}>
            <b>{situation.detector_count}</b>
            <small>rules qualified</small>
          </span>
          <code>{situation.situation_id}</code>
        </li>
      ))}
      {scan.situations.length > 6 && <li className="trender-more">{scan.situations.length - 6} further situation envelope(s) not rendered</li>}
    </ul>
  );
}
