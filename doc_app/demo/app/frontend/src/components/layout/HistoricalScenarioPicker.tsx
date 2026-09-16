/**
 * HistoricalScenarioPicker — top-left dropdown listing in-repo benchmark
 * scenarios. Selecting a row seeds the situation detector with the
 * scenario's trigger window (station + start/end) and immediately runs
 * a scan. The chat session is left untouched — this is a scan-only
 * shortcut, distinct from the `SavedSessionPicker` which hydrates a
 * full historical chat session.
 *
 * Data origin: the dropdown content is fetched from
 * ``GET /api/evaluations/scenarios/triggers``. Real station codes and
 * event timestamps live only inside ``data_processors/`` per the
 * data-boundary rule (README §3); this component never hardcodes them.
 */

import { useEffect, useRef, useState } from "react";
import { ChevronDown, FlaskConical, Loader2 } from "lucide-react";
import { listScenarioTriggers, type ScenarioTrigger } from "@/api/scenariosApi";
import { useSituationStore } from "@/stores/situationStore";
import { usePanelStore } from "@/stores/panelStore";
import { usePlaceholderStore } from "@/stores/placeholderStore";

export function HistoricalScenarioPicker() {
  const [open, setOpen] = useState(false);
  const [scenarios, setScenarios] = useState<ScenarioTrigger[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeId, setActiveId] = useState<string | null>(null);
  /* Couturier v2 R7: the amber pulsing attention tooltip was retired.
     It animated against a developer-fixture control on every first paint
     and competed with the chat surface for the operator's eye. Surface
     this picker via the Workspace overlay instead — it's a deliberate
     scan tool, not a first-run cue. */
  const ref = useRef<HTMLDivElement>(null);

  /* Eager fetch on mount — the scenarios list is small (≤ 20 rows) and
     served from the in-process yaml cache, so there is no reason to
     defer it. The dropdown is populated by the time the operator
     clicks the trigger. */
  useEffect(() => {
    let cancelled = false;
    listScenarioTriggers()
      .then((items) => {
        if (cancelled) return;
        setScenarios(items);
        setError(null);
      })
      .catch((err) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        setScenarios([]);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  /* Close on outside click — same pattern as SavedSessionPicker. */
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    if (open) document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  function handleSelect(scn: ScenarioTrigger) {
    setOpen(false);
    setActiveId(scn.scenario_id);

    /* Placeholder mode would mask real scan results; turn it off so the
       operator sees the detector output for the chosen window. */
    if (usePlaceholderStore.getState().enabled) {
      usePlaceholderStore.getState().toggle();
    }

    const sit = useSituationStore.getState();
    sit.setParams({
      start: scn.trigger.start,
      end: scn.trigger.end,
      station: scn.trigger.station,
    });
    /* Surface the scan in the centre column status tab — same UX as
       the in-panel Scan button. */
    usePanelStore.getState().setCenterTab("status");
    sit.fetchSituations();
  }

  return (
    <div ref={ref} className="relative">
      <button
        data-testid="historical-scenario-picker"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-text-secondary hover:text-text-primary hover:bg-neutral-bg2 rounded transition-shadow"
        title="Load a historical AEMO Reviewable Operating Incident as a detector scan"
      >
        <FlaskConical className="h-3.5 w-3.5" />
        Historical Test Scenarios
        {scenarios && scenarios.length > 0 && (
          <span className="ml-0.5 px-1.5 py-0.5 text-micro font-semibold rounded bg-brand/15 text-brand">
            {scenarios.length}
          </span>
        )}
        <ChevronDown className="h-3 w-3" />
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 w-80 bg-neutral-bg1 border border-border rounded-lg shadow-lg z-50 overflow-hidden">
          <div className="px-3 py-2 border-b border-border">
            <span className="text-label uppercase tracking-wider text-text-tertiary font-bold">
              Historical Test Scenarios
            </span>
          </div>

          {loading && (
            <div className="px-3 py-3 flex items-center gap-2 text-xs text-text-tertiary">
              <Loader2 className="h-3.5 w-3.5 animate-spin" /> Loading scenarios…
            </div>
          )}

          {!loading && error && (
            <div className="px-3 py-3 text-xs text-status-error">
              Failed to load scenarios: {error}
            </div>
          )}

          {!loading && !error && scenarios && scenarios.length === 0 && (
            <div className="px-3 py-3 text-xs text-text-tertiary">
              No scenarios available.
            </div>
          )}

          {!loading && scenarios && scenarios.length > 0 && (
            <div className="max-h-96 overflow-y-auto">
              {scenarios.map((scn) => (
                <button
                  key={scn.scenario_id}
                  data-testid="historical-scenario-option"
                  onClick={() => handleSelect(scn)}
                  className={`w-full text-left px-3 py-2.5 hover:bg-neutral-bg2 transition-colors border-b border-border/30 last:border-0 ${
                    scn.scenario_id === activeId ? "bg-brand/10" : ""
                  }`}
                >
                  <div className="text-sm font-medium text-text-primary">{scn.name}</div>
                  <div className="text-label text-text-tertiary mt-0.5">
                    {scn.trigger.station} · {scn.trigger.start} → {scn.trigger.end}
                  </div>
                  {scn.description && (
                    <div className="text-label text-text-secondary mt-1 leading-snug">
                      {scn.description}
                    </div>
                  )}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
