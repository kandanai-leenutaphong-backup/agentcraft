/**
 * HelpOverlay \u2014 keyboard shortcut cheat-sheet modal.
 *
 * Opened with `?`, closed with Esc or the close button. Static content;
 * kept in this file alongside the shortcut definitions so it stays in
 * sync with the actual bindings wired up in useGlobalShortcuts.
 */

import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { usePaletteStore } from "@/stores/paletteStore";

/** One keyboard shortcut row. */
interface Shortcut {
  keys: string[];
  label: string;
}

/* The canonical shortcut table. Update this and useGlobalShortcuts in
   tandem. Keys are shown exactly as printed; use \u2318 / Ctrl conventions. */
const SHORTCUTS: { group: string; items: Shortcut[] }[] = [
  {
    group: "Navigation",
    items: [
      { keys: ["\u2318", "K"], label: "Open command palette" },
      { keys: ["Ctrl", "K"], label: "Open command palette (Windows/Linux)" },
      { keys: ["1"], label: "Priorities tab" },
      { keys: ["2"], label: "Pinned Situation tab" },
      { keys: ["3"], label: "Grid Status tab" },
      { keys: ["4"], label: "Topology tab" },
      { keys: ["5"], label: "Data Search Assistant tab" },
    ],
  },
  {
    group: "Focus",
    items: [
      { keys: ["/"], label: "Focus chat input" },
      { keys: ["Esc"], label: "Close overlay / clear focus" },
    ],
  },
  {
    group: "Help",
    items: [
      { keys: ["?"], label: "Show this cheat-sheet" },
    ],
  },
];

export function HelpOverlay() {
  const helpOpen = usePaletteStore((s) => s.helpOpen);
  const closeHelp = usePaletteStore((s) => s.closeHelp);

  if (!helpOpen) return null;

  return createPortal(
    <div
      data-testid="help-overlay"
      className="fixed inset-0 z-[60] flex items-start justify-center pt-24 bg-overlay-backdrop backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) closeHelp(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Keyboard shortcuts"
        className="w-[520px] max-w-[92vw] rounded-xl border border-border bg-neutral-bg1 shadow-xl overflow-hidden"
      >
        <div className="flex items-center gap-2 px-4 py-2 border-b border-border bg-neutral-bg2">
          <h3 className="text-sm font-bold text-text-primary flex-1">Keyboard Shortcuts</h3>
          <button
            onClick={closeHelp}
            className="p-1 rounded text-text-muted hover:text-text-primary hover:bg-neutral-bg3"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="p-4 space-y-4 max-h-[60vh] overflow-y-auto">
          {SHORTCUTS.map((g) => (
            <section key={g.group}>
              <h4 className="text-micro font-bold uppercase tracking-wider text-text-muted mb-2">
                {g.group}
              </h4>
              <ul className="space-y-1.5">
                {g.items.map((s) => (
                  <li key={s.label} className="flex items-center gap-2 text-sm">
                    <span className="flex-1 text-text-secondary">{s.label}</span>
                    <span className="flex items-center gap-1">
                      {s.keys.map((k, i) => (
                        <kbd
                          key={`${k}-${i}`}
                          className="px-1.5 py-0.5 text-micro font-mono font-bold rounded bg-neutral-bg3 border border-border text-text-primary"
                        >
                          {k}
                        </kbd>
                      ))}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
