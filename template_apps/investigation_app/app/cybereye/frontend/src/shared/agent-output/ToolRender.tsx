import { AlertTriangle, Radar, SearchX } from "lucide-react";
import { BoundedTable } from "./BoundedTable";
import { ToolRenderCard } from "./ToolRenderCard";
import { CATEGORY_META, parseToolEnvelope, signalChips, type ScanBrief, type ToolRenderModel } from "./envelope";

const meta = (category: string, tool: string) =>
  CATEGORY_META[category] ?? { title: tool.replace(/_/g, " "), note: "Bounded result returned by a purpose-built replay tool." };

/** Single render surface for every tool envelope, in the chat panel and the tool board alike. */
export function ToolRender({ value }: { value: unknown }) {
  return <ToolRenderModelView model={parseToolEnvelope(value)} />;
}

export function ToolRenderModelView({ model }: { model: ToolRenderModel }) {
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
  const shared = {
    title, note, tool: model.tool, category: model.category, scope: model.scope,
    signals: signalChips(model), fallback: model.fallback, historicalReplay: model.historicalReplay,
  };

  if (model.kind === "situations") {
    return (
      <ToolRenderCard {...shared} tone={model.scan.critical > 0 ? "bad" : "default"}>
        <p className="trender-window">{model.scan.window_start} → {model.scan.window_end}</p>
        <SituationChips scan={model.scan} />
      </ToolRenderCard>
    );
  }

  if (model.kind === "empty") {
    return (
      <ToolRenderCard {...shared} tone="warn">
        <div className="trender-empty">
          {model.category === "not_found" ? <SearchX size={18} /> : <AlertTriangle size={18} />}
          <p>{model.reason}</p>
        </div>
      </ToolRenderCard>
    );
  }

  return (
    <ToolRenderCard {...shared} tone={model.fallback ? "warn" : "default"}>
      <BoundedTable
        columns={model.columns} rows={model.rows} rowCount={model.rowCount}
        maxRows={model.maxRows} truncated={model.truncated}
      />
    </ToolRenderCard>
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
