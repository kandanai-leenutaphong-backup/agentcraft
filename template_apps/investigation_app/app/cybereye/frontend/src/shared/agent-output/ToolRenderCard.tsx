import type { ReactNode } from "react";
import type { ScopeEntry, SignalChip } from "./envelope";

interface Props {
  title: string;
  note: string;
  tool: string;
  category: string;
  scope: ScopeEntry[];
  signals: SignalChip[];
  fallback?: boolean;
  historicalReplay?: boolean;
  tone?: "default" | "warn" | "bad";
  children: ReactNode;
}

/**
 * Three bands only: Inputs, Advisory, Results. Historical replay is true of every row in the
 * system and is asserted once in the app header, so repeating it per card is noise.
 */
export function ToolRenderCard({
  title, note, tool, category, scope, signals, fallback, tone = "default", children,
}: Props) {
  const advisory = fallback
    ? "Model-authored KQL, outside the purpose-built tool set."
    : tone === "warn" ? note : "";
  return (
    <section className={`trender trender-${tone}`} aria-label={`${title} tool result`}>
      <header className="trender-head">
        <div className="trender-identity">
          <b>{title}</b>
          <code title={category ? `${tool} · ${category}` : tool}>{tool}</code>
        </div>
      </header>

      {scope.length > 0 && (
        <div className="trender-band">
          <span className="trender-band-label">Inputs</span>
          <dl className="trender-scope" aria-label="Query inputs">
            {scope.map((entry) => (
              <div key={entry.label}><dt>{entry.label}</dt><dd>{entry.value}</dd></div>
            ))}
          </dl>
        </div>
      )}

      {advisory && <p className={`trender-advisory ${fallback ? "warn" : ""}`} role="note">{advisory}</p>}

      <div className="trender-band">
        <span className="trender-band-label">Results</span>
        {signals.length > 0 && (
          <ul className="trender-signals" aria-label="Result signals">
            {signals.map((chip) => (
              <li key={chip.label} className={`tone-${chip.tone}`}><b>{chip.value}</b><span>{chip.label}</span></li>
            ))}
          </ul>
        )}
        <div className="trender-body">{children}</div>
      </div>
    </section>
  );
}
