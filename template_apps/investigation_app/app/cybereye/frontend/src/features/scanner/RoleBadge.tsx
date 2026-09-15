import { useRef, useState, type ReactNode } from "react";

const ROLE_MEANING: Record<string, string> = {
  anchor: "Anchor — strong enough on its own to open a situation. Anchors carry the highest score weight, and two qualifying anchors are what push a situation to critical.",
  corroborator: "Corroborator — independent supporting evidence. It adds score and confidence to a situation but does not open one by itself.",
  contextual: "Contextual — background signal. It is attached only when it correlates in both time and entity with a qualifying anchor, and it carries the lowest weight.",
};

export function RoleBadge({ role, children }: { role: string; children?: ReactNode }) {
  const meaning = ROLE_MEANING[role] ?? `${role} — role weighting used by the synthesis policy.`;
  const anchor = useRef<HTMLSpanElement>(null);
  const [box, setBox] = useState<{ top: number; left: number } | null>(null);

  // Fixed positioning keeps the tip out of the scrolling column's clipping box.
  function place() {
    const rect = anchor.current?.getBoundingClientRect();
    if (rect) setBox({ top: rect.bottom + 6, left: Math.min(rect.left, window.innerWidth - 300) });
  }

  return (
    <span
      ref={anchor} className="role-badge" tabIndex={0} aria-label={meaning}
      onMouseEnter={place} onFocus={place}
      onMouseLeave={() => setBox(null)} onBlur={() => setBox(null)}
    >
      <span className={`factor-role ${role}`}>{children ?? role}</span>
      {box && <span className="role-tip" role="tooltip" style={{ top: box.top, left: box.left }}>{meaning}</span>}
    </span>
  );
}
