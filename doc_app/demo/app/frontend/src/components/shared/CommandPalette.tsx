/**
 * CommandPalette \u2014 quick-action popover opened with \u2318K / Ctrl+K.
 *
 * Role:
 *   Single modal overlay rendered in App.tsx. Indexes a small set of
 *   high-signal commands \u2014 switch centre tab, activate agent, pin
 *   situation, clear pin, scan, toggle help, toggle placeholders \u2014
 *   and filters them with a case-insensitive substring match against
 *   label + keywords. Arrow keys navigate, Enter executes, Esc closes.
 *
 *   Intentionally free-standing: no Fuse.js, no cmdk. A hand-rolled
 *   matcher is plenty fast for the ~20\u201350 entries the palette
 *   exposes and saves the bundle size + dependency.
 *
 * Key collaborators:
 *   - panelStore:   setCenterTab, clearPinnedStations
 *   - agentStore:   agents list + setActiveAgent
 *   - situationStore: fetchSituations ("Scan")
 *   - placeholderStore: toggle placeholders
 *   - paletteStore: open/close state (sibling file)
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Search, ArrowRight } from "lucide-react";
import { createPortal } from "react-dom";
import { usePanelStore } from "@/stores/panelStore";
import { useAgentStore } from "@/stores/agentStore";
import { useSituationStore } from "@/stores/situationStore";
import { useVocab } from "@/stores/vocabularyStore";
import { usePlaceholderStore } from "@/stores/placeholderStore";
import { usePaletteStore } from "@/stores/paletteStore";

/** A single palette command. `run` is fire-and-forget; the palette closes
 *  after invoking it regardless of whether `run` returns a promise. */
interface Command {
  id: string;
  label: string;
  /** Optional right-aligned hint (e.g. "Tab 1", agent id). */
  hint?: string;
  /** Extra search tokens beyond the label. Lower-cased. */
  keywords?: string[];
  /** Grouping bucket for sectioning the results list. */
  group: "Navigation" | "Agents" | "Actions" | "Help";
  run: () => void | Promise<void>;
}

/** Score a command against a query. Lower is better; -1 means no match. */
function score(cmd: Command, q: string): number {
  if (!q) return 0;
  const hay = [cmd.label, cmd.hint ?? "", ...(cmd.keywords ?? [])]
    .join(" ")
    .toLowerCase();
  const needle = q.toLowerCase();
  const idx = hay.indexOf(needle);
  if (idx < 0) return -1;
  /* Earlier matches ranked better; label hits outrank keyword hits. */
  const labelIdx = cmd.label.toLowerCase().indexOf(needle);
  return labelIdx >= 0 ? labelIdx : idx + 100;
}

export function CommandPalette() {
  const open = usePaletteStore((s) => s.open);
  const close = usePaletteStore((s) => s.close);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  /* Store actions pulled once \u2014 individual selectors so the palette does
     not re-render on every agent-thread update. */
  const setCenterTab = usePanelStore((s) => s.setCenterTab);
  const clearPinnedStations = usePanelStore((s) => s.clearPinnedStations);
  const agents = useAgentStore((s) => s.agents);
  const setActiveAgent = useAgentStore((s) => s.setActiveAgent);
  const fetchSituations = useSituationStore((s) => s.fetchSituations);
  const togglePlaceholder = usePlaceholderStore((s) => s.toggle);
  const statusLabel = useVocab("systemStatusLabel");

  /* Build the command list. Memoised so the agents fan-out is not rebuilt
     on every keystroke. */
  const commands = useMemo<Command[]>(() => {
    const nav: Command[] = [
      { id: "tab-priorities", group: "Navigation", label: "View Priorities", hint: "1", keywords: ["actions", "priority"], run: () => setCenterTab("priorities") },
      { id: "tab-situation",  group: "Navigation", label: "View Pinned Stations", hint: "2", keywords: ["pin", "alerts"], run: () => setCenterTab("situation") },
      { id: "tab-status",     group: "Navigation", label: `View ${statusLabel}`, hint: "3", keywords: ["nem", "mw", "frequency", "hz", "status", "health"], run: () => setCenterTab("status") },
      { id: "tab-topology",   group: "Navigation", label: "View Topology", hint: "4", keywords: ["map", "station", "graph"], run: () => setCenterTab("topology") },
      { id: "tab-data",       group: "Navigation", label: "View Data Search Assistant", hint: "5", keywords: ["lookup", "query"], run: () => setCenterTab("data") },
      { id: "tab-tuning",     group: "Navigation", label: "View Detector Tuning", hint: "6", keywords: ["situation", "detector", "threshold", "config"], run: () => setCenterTab("tuning") },
      /* `evaluations` has no digit shortcut by design — dev surface,
         palette-only entry point. Added in C1 (2026-05-17) when the
         Workshop overflow dropdown was retired; without this command
         the System Evaluations mode would be unreachable except via
         direct localStorage manipulation. */
      { id: "tab-evaluations", group: "Navigation", label: "View System Evaluations", keywords: ["audit", "session", "judge", "eval"], run: () => setCenterTab("evaluations") },
    ];
    const actionCmds: Command[] = [
      { id: "scan", group: "Actions", label: "Scan situations", keywords: ["refresh", "detect"], run: () => { void fetchSituations(); } },
      { id: "clear-pin", group: "Actions", label: "Clear pinned stations", keywords: ["unpin"], run: () => clearPinnedStations() },
      { id: "toggle-placeholders", group: "Actions", label: "Toggle placeholder data", keywords: ["demo", "sample"], run: () => togglePlaceholder() },
    ];
    const agentCmds: Command[] = agents.map((a) => ({
      id: `agent-${a.id}`,
      group: "Agents" as const,
      label: `Activate ${a.name ?? a.id}`,
      hint: a.id,
      keywords: [a.id, (a as any).description ?? ""],
      run: () => setActiveAgent(a.id),
    }));
    const help: Command[] = [
      { id: "help", group: "Help", label: "Show keyboard shortcuts", hint: "?", keywords: ["keys", "cheatsheet"], run: () => { usePaletteStore.getState().openHelp(); } },
    ];
    return [...nav, ...actionCmds, ...agentCmds, ...help];
  }, [agents, setCenterTab, clearPinnedStations, fetchSituations, togglePlaceholder, setActiveAgent, statusLabel]);

  /* Filter + sort. Stable ordering inside each group when the query is empty. */
  const filtered = useMemo(() => {
    if (!query.trim()) return commands;
    const scored = commands
      .map((c) => ({ cmd: c, s: score(c, query.trim()) }))
      .filter((x) => x.s >= 0)
      .sort((a, b) => a.s - b.s);
    return scored.map((x) => x.cmd);
  }, [commands, query]);

  /* Reset state when the palette opens. Focus the input on the next tick so
     the browser has the dialog mounted. */
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setCursor(0);
    const t = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(t);
  }, [open]);

  /* Clamp cursor to available results \u2014 typing can shrink the list. */
  useEffect(() => {
    if (cursor >= filtered.length) setCursor(0);
  }, [filtered.length, cursor]);

  if (!open) return null;

  const runAndClose = (cmd: Command) => {
    try { void cmd.run(); }
    finally { close(); }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") { e.preventDefault(); close(); return; }
    if (e.key === "ArrowDown") { e.preventDefault(); setCursor((c) => Math.min(filtered.length - 1, c + 1)); return; }
    if (e.key === "ArrowUp") { e.preventDefault(); setCursor((c) => Math.max(0, c - 1)); return; }
    if (e.key === "Enter") {
      e.preventDefault();
      const cmd = filtered[cursor];
      if (cmd) runAndClose(cmd);
    }
  };

  /* Group the filtered list for visual sectioning. Stable insertion order. */
  const groups: { name: Command["group"]; items: Command[] }[] = [];
  for (const c of filtered) {
    let g = groups.find((x) => x.name === c.group);
    if (!g) { g = { name: c.group, items: [] }; groups.push(g); }
    g.items.push(c);
  }
  /* Index commands in the flattened render order so the cursor index lines
     up with rendered rows. */
  const flat = groups.flatMap((g) => g.items);

  return createPortal(
    <div
      data-testid="command-palette"
      className="fixed inset-0 z-[60] flex items-start justify-center pt-24 bg-overlay-backdrop backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="w-[560px] max-w-[92vw] rounded-xl border border-border bg-neutral-bg1 shadow-xl overflow-hidden"
      >
        <div className="flex items-center gap-2 px-3 py-2 border-b border-border bg-neutral-bg2">
          <Search className="h-4 w-4 text-text-muted" />
          <input
            ref={inputRef}
            data-testid="command-palette-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Search commands, agents, tabs\u2026"
            className="flex-1 bg-transparent outline-none text-sm text-text-primary placeholder:text-text-muted"
          />
          <span className="text-micro font-mono text-text-muted uppercase tracking-wider">Esc to close</span>
        </div>
        <div className="max-h-[50vh] overflow-y-auto py-1">
          {flat.length === 0 && (
            <div className="px-3 py-6 text-center text-sm text-text-muted">No matching commands</div>
          )}
          {groups.map((g) => (
            <div key={g.name} className="py-1">
              <div className="px-3 pt-1 pb-0.5 text-micro font-bold uppercase tracking-wider text-text-muted">
                {g.name}
              </div>
              {g.items.map((cmd) => {
                const idx = flat.indexOf(cmd);
                const active = idx === cursor;
                return (
                  <button
                    key={cmd.id}
                    data-testid={`command-${cmd.id}`}
                    onMouseEnter={() => setCursor(idx)}
                    onMouseDown={(e) => { e.preventDefault(); runAndClose(cmd); }}
                    className={[
                      "w-full flex items-center gap-2 px-3 py-1.5 text-left text-sm",
                      active ? "bg-brand/15 text-text-primary" : "text-text-secondary hover:bg-neutral-bg2",
                    ].join(" ")}
                  >
                    <ArrowRight className={`h-3 w-3 ${active ? "text-brand" : "text-text-muted"}`} />
                    <span className="flex-1 truncate">{cmd.label}</span>
                    {cmd.hint && (
                      <span className="shrink-0 text-micro font-mono text-text-muted uppercase tracking-wider">
                        {cmd.hint}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>,
    document.body,
  );
}
