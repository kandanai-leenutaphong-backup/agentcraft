import { useLayoutEffect, useRef, useState } from "react";
import { HelpCircle } from "lucide-react";

export interface ExplainerStage {
  label: string;
  detail: string;
  kind?: "input" | "compute" | "corpus" | "model" | "output";
}

interface Props {
  title: string;
  subject: string;
  stages: ExplainerStage[];
  footnote?: string;
}

const PANEL_WIDTH = 350;

/** Hover/focus explainer that renders the derivation of a value as a stage diagram. */
export function ExplainerHint({ title, subject, stages, footnote }: Props) {
  const anchor = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [box, setBox] = useState<{ top: number; left: number }>({ top: -9999, left: -9999 });

  // Fixed placement keeps the panel clear of the scrolling column's clipping box.
  useLayoutEffect(() => {
    if (!open) return;
    const seat = anchor.current?.getBoundingClientRect();
    const height = panel.current?.offsetHeight ?? 0;
    if (!seat) return;
    const left = Math.max(8, Math.min(seat.left + seat.width / 2 - PANEL_WIDTH / 2, window.innerWidth - PANEL_WIDTH - 8));
    const below = seat.bottom + 8;
    setBox({ top: below + height > window.innerHeight - 8 ? Math.max(8, seat.top - height - 8) : below, left });
  }, [open, stages]);

  const visible = open || pinned;

  return (
    <span
      className="explainer"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        ref={anchor} type="button" className={`explainer-mark ${visible ? "on" : ""}`}
        aria-expanded={visible} aria-label={`How ${subject} was derived`}
        onFocus={() => setOpen(true)} onBlur={() => setOpen(false)}
        onClick={() => setPinned((value) => !value)}
      >
        <HelpCircle size={12} />
      </button>
      {visible && (
        <div
          ref={panel} className="explainer-panel" role="tooltip"
          style={{ top: box.top, left: box.left, width: PANEL_WIDTH }}
        >
          <b className="explainer-title">{title}</b>
          <ol className="explainer-flow">
            {stages.map((stage, index) => (
              <li key={stage.label} className={`explainer-stage ${stage.kind ?? "compute"}`}>
                <span className="explainer-node"><i>{index + 1}</i><b>{stage.label}</b></span>
                <p>{stage.detail}</p>
              </li>
            ))}
          </ol>
          {footnote && <p className="explainer-footnote">{footnote}</p>}
          {pinned && <p className="explainer-footnote">Click the mark again to unpin.</p>}
        </div>
      )}
    </span>
  );
}
