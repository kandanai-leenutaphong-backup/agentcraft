/**
 * SituationControlBar — compact parameter inputs.
 *
 * Sits above the left sidebar. The date-range picker edits the scan window;
 * the Scan button is always visible beside it.
 */

import { AlertTriangle, CheckCircle2, Loader2, Radar } from "lucide-react";
import { useSituationStore } from "@/stores/situationStore";
import { usePanelStore } from "@/stores/panelStore";
import { DateRangePicker } from "@/components/shared/DateRangePicker";
import { IS_KIOSK } from "@/foundation/constants";
import { isDemoIdle, startDemoScenario } from "@/demo/startDemo";

export function SituationControlBar() {
  const params = useSituationStore((s) => s.params);
  const setParams = useSituationStore((s) => s.setParams);
  const fetchSituations = useSituationStore((s) => s.fetchSituations);
  const loading = useSituationStore((s) => s.loading);
  /* Surface the store error so a failed scan does not just look like a
     successful scan with zero results (audit F-012). */
  const scanError = useSituationStore((s) => s.error);
  const situationCount = useSituationStore((s) => s.situations.length);
  const setCenterTab = usePanelStore((s) => s.setCenterTab);
  /* Detector-tuning dials (Window / Max Alarms / Max SCADA) are
     grid-detector controls; domains with pre-formed alert queues (e.g. a
     SOC) hide them via vocabulary so the control bar stays meaningful. */

  /* Date-range edits commit into store state. The always-visible Scan
   * button below is the only explicit detector run action. */
  const handleApply = (next: { start: string; end: string }) => {
    setParams({ ...next, station: params.station?.trim() || undefined });
  };

  const handleScan = () => {
    /* Kiosk builds have no scenario picker: Scan is what starts the demo. */
    if (IS_KIOSK && isDemoIdle()) {
      setCenterTab("status");
      void startDemoScenario();
      return;
    }
    setParams({ station: params.station?.trim() || undefined });
    setCenterTab("status");
    fetchSituations();
  };

  return (
    <div data-testid="situation-control-bar" className="px-3 py-2 bg-neutral-bg2 space-y-1.5">
      <div className="flex items-center gap-2">
        <div className="min-w-0 flex-1">
          <DateRangePicker
            start={params.start}
            end={params.end}
            onApply={handleApply}
          />
        </div>
        <button
          data-testid="situation-scan-button"
          type="button"
          onClick={handleScan}
          disabled={loading}
          className="h-8 shrink-0 flex items-center gap-1.5 px-3 text-xs font-semibold rounded bg-brand text-on-accent hover:bg-brand/80 disabled:opacity-50 transition-colors"
        >
          {loading ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Radar className="h-3.5 w-3.5" />
          )}
          {loading ? "Scanning" : "Scan"}
        </button>
      </div>


      {/* Scan result strip \u2014 promoted from `text-micro` (10 px) to
          `text-xs` (12 px) with a status icon so a successful or failed
          scan is unmistakable at a glance (audit F-012). Renders only
          when a scan has settled; in-flight scans rely on the
          ScanProgressBar above. */}
      {!loading && scanError && (
        <div
          data-testid="scan-error"
          className="flex items-center gap-1.5 text-xs text-status-error"
          title={scanError}
        >
          <AlertTriangle className="h-3.5 w-3.5 shrink-0" />
          <span className="truncate">Scan failed: {scanError}</span>
        </div>
      )}
      {!loading && !scanError && situationCount > 0 && (
        <div
          data-testid="scan-complete"
          className="flex items-center gap-1.5 text-xs text-text-secondary"
        >
          <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-status-success" />
          <span>
            {situationCount} situation{situationCount !== 1 ? "s" : ""} detected
          </span>
        </div>
      )}
    </div>
  );
}
