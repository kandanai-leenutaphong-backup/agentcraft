/**
 * PlayDemoButton — header CTA + scenario picker for kiosk mode.
 *
 * Renders a persistent header dropdown listing every bundled scenario.
 * Picking a scenario loads it, starts playback via the framePlayer, and
 * leaves the selector visible so the operator can switch scenarios.
 *
 * State source: useDemoPlayerStore (mode, scenario).
 *
 * Side effects:
 *   - Calls SCENARIOS[i].load() to fetch the scenario JSON.
 *   - Calls demoPlayerStore.loadScenario() + start().
 *   - Kicks off the playScenario() promise (fire-and-forget; the player
 *     itself manages its lifecycle via abort).
 */

import { useState, useMemo } from "react";
import { ChevronDown, Play, Square } from "lucide-react";
import { SCENARIOS } from "@/demo";
import type { ScenarioListEntry } from "@/demo";
import { useDemoPlayerStore } from "@/demo/demoPlayerStore";
import { playScenario } from "@/demo/framePlayer";

/** Group scenarios by industry for the dropdown. */
function groupByIndustry(entries: ScenarioListEntry[]): { industry: string; scenarios: ScenarioListEntry[] }[] {
  const map = new Map<string, ScenarioListEntry[]>();
  for (const e of entries) {
    const group = map.get(e.industry) ?? [];
    group.push(e);
    map.set(e.industry, group);
  }
  return Array.from(map.entries()).map(([industry, scenarios]) => ({ industry, scenarios }));
}

export function PlayDemoButton() {
  const [open, setOpen] = useState(false);
  const mode = useDemoPlayerStore((s) => s.mode);
  const scenario = useDemoPlayerStore((s) => s.scenario);
  const stop = useDemoPlayerStore((s) => s.stop);
  /* Keep hook order stable across the idle and running button states. */
  const groups = useMemo(() => groupByIndustry(SCENARIOS), []);
  const currentEntry = useMemo(
    () => SCENARIOS.find((entry) => entry.id === scenario?.id) ?? null,
    [scenario?.id],
  );
  /* Initial-load coachmark — visible only before the operator selects a
     scenario. Once the dropdown opens or a scenario is loaded, the normal
     selector state is enough context. */
  const showScenarioPrompt = mode === "off" && currentEntry === null && !open;

  /* While the player is running, the button morphs into a Stop control. */
  const isRunning = mode === "playing" || mode === "paused" || mode === "ready";

  async function startScenario(entry: ScenarioListEntry) {
    console.info("[demo] startScenario:", entry.id);
    setOpen(false);
    /* Defensive: stop any prior run before starting a new one. */
    if (useDemoPlayerStore.getState().mode !== "off") {
      useDemoPlayerStore.getState().stop();
    }
    try {
      const scenario = await entry.load();
      console.info("[demo] scenario loaded:", scenario.id, "frames=", scenario.frames.length);
      useDemoPlayerStore.getState().loadScenario(scenario);
      useDemoPlayerStore.getState().start();
      console.info("[demo] player started — calling playScenario()");
      /* Fire-and-forget. playScenario handles its own errors and final state. */
      void playScenario();
    } catch (err) {
      console.error("[demo] failed to load scenario", entry.id, err);
    }
  }

  return (
    <div className="relative flex items-center gap-2">
      {isRunning && (
        <button
          type="button"
          onClick={stop}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded bg-red-600 text-white hover:bg-red-700"
          title="Stop the current scenario"
        >
          <Square className="h-3 w-3 fill-current" />
          Stop
        </button>
      )}
      <button
        type="button"
        data-testid="scenario-picker"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={[
          "inline-flex min-w-[250px] items-center justify-between gap-3 rounded border bg-neutral-bg2 px-3 py-1.5 text-left text-xs text-text-primary shadow-sm transition-all hover:bg-neutral-bg3",
          showScenarioPrompt
            ? "border-emerald-300/80 ring-2 ring-emerald-300/70 shadow-[0_0_20px_rgba(52,211,153,0.32)] animate-pulse"
            : "border-border",
        ].join(" ")}
      >
        <span className="min-w-0">
          <span className="block text-[10px] font-bold uppercase tracking-wider text-text-muted">Scenario</span>
          <span className="block truncate font-medium">
            {currentEntry?.label ?? "Select scenario"}
          </span>
        </span>
        <ChevronDown className={`h-4 w-4 shrink-0 text-text-muted transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {showScenarioPrompt && (
        <div
          data-testid="scenario-picker-hint"
          className="absolute right-0 top-full z-40 mt-2 w-72 rounded border border-emerald-300/50 bg-neutral-bg2 px-3 py-2 text-xs text-text-secondary shadow-lg"
        >
          <div className="absolute -top-1.5 right-6 h-3 w-3 rotate-45 border-l border-t border-emerald-300/50 bg-neutral-bg2" />
          <span className="font-medium text-emerald-200">Choose a scenario to trigger.</span>
        </div>
      )}
      {open && (
        <div className="absolute right-0 top-full mt-1 w-96 bg-neutral-bg2 border border-border rounded shadow-lg z-50 max-h-[70vh] overflow-y-auto">
          {groups.map(({ industry, scenarios }) => (
            <div key={industry}>
              <div className="px-3 py-1.5 text-[10px] font-bold uppercase tracking-wider text-text-muted bg-neutral-bg3/50 border-b border-border/30">
                {industry}
              </div>
              <ul>
                {scenarios.map((entry) => (
                  <li key={entry.id} className="border-b border-border/30 last:border-b-0">
                    <button
                      type="button"
                      onClick={() => startScenario(entry)}
                      role="menuitem"
                      className="flex w-full items-start gap-2 text-left px-3 py-2 hover:bg-neutral-bg3"
                    >
                      <Play className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-400" />
                      <span className="min-w-0">
                        <span className="flex items-center gap-2 font-medium text-sm text-text-primary">
                          {entry.label}
                          {scenario?.id === entry.id && (
                            <span className="rounded bg-brand/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-brand">
                              Selected
                            </span>
                          )}
                        </span>
                        <span className="block text-xs text-text-muted">{entry.description}</span>
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
