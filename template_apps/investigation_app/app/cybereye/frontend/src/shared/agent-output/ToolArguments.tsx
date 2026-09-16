import { SourceCodeViewer } from "@agentcraft/source-code";
import { ResourceChip } from "../ui";

const LONG_VALUE = 56;
const KQL_HINT = /\b(EventsUnified|summarize|project|where|extend)\b/;
const UTC = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/;
const RESOURCE = /^(cyb_|[a-f0-9]{16,})/i;

function label(key: string): string {
  return key.replace(/_/g, " ");
}

/** Objects must never reach the screen as JSON; an unhandled shape is a missing type case. */
function TypedValue({ name, value }: { name: string; value: unknown }) {
  if (value === null || value === undefined || value === "") return <span className="targ-empty">—</span>;
  if (typeof value === "boolean") return <span className="targ-bool">{value ? "yes" : "no"}</span>;
  if (typeof value === "number") return <span className="targ-num">{value.toLocaleString()}</span>;
  if (Array.isArray(value)) {
    return <span className="targ-chips">{value.slice(0, 12).map((item, index) => (
      <em key={index}>{String(item)}</em>
    ))}{value.length > 12 && <em className="targ-more">+{value.length - 12}</em>}</span>;
  }
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return <span className="targ-chips">{entries.slice(0, 8).map(([key, item]) => (
      <em key={key}>{label(key)} {String(item)}</em>
    ))}</span>;
  }
  const text = String(value);
  const isKql = KQL_HINT.test(text);
  if (isKql || text.includes("\n")) {
    return <SourceCodeViewer code={text} language={isKql ? "kql" : "text"}
      filename={`${isKql ? "KQL" : "code"} · ${label(name)}`} defaultWrap maxHeight={220} />;
  }
  if (UTC.test(text)) return <span className="targ-utc">{text.replace("T", " ").replace(/Z$/, " UTC")}</span>;
  if (RESOURCE.test(text) && text.length > 10) return <ResourceChip value={text} />;
  return <span>{text}</span>;
}

function isBlock(value: unknown): boolean {
  return typeof value === "string" && (value.length > LONG_VALUE || value.includes("\n") || value.includes("|"));
}

/** Partial JSON arrives one fragment at a time; show whatever already parses. */
function parsePartial(text: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(text);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null;
  } catch {
    return null;
  }
}

interface Props {
  args?: Record<string, unknown>;
  streaming?: string;
}

export function ToolArguments({ args, streaming }: Props) {
  const resolved = args ?? (streaming ? parsePartial(streaming) : null);

  if (!resolved) {
    return (
      <div className="tool-args">
        <div className="tool-args-caption">Inputs · composing</div>
        <div className="tool-args-progress"><i /><i /><i /></div>
      </div>
    );
  }

  const entries = Object.entries(resolved);
  return (
    <div className="tool-args">
      <div className="tool-args-caption">{args ? "Inputs" : "Inputs · streaming"}</div>
      <dl className="tool-arg-rows">
        {entries.map(([key, value]) => (
          <div key={key} className={isBlock(value) ? "block" : ""}>
            <dt>{label(key)}</dt>
            <dd><TypedValue name={key} value={value} /></dd>
          </div>
        ))}
      </dl>
      {entries.length === 0 && <p className="tool-args-empty">This tool was called with no arguments.</p>}
    </div>
  );
}
