/**
 * GridStatusSummaryPanel — left-sidebar compact Grid Status view.
 *
 * Replaces the dense duplicate render of `OperatingStatePanel` at the
 * bottom of the left column with a 3-line at-a-glance summary:
 *   - NEM frequency band + range
 *   - NEM reserve MW
 *   - Threatened MW + situation count
 *
 * Reads the same `gridStatus` store slot as the centre tab so the two
 * surfaces never disagree. Empty state mirrors the centre tab.
 */

import { Activity } from "lucide-react";
import { useSituationStore } from "@/stores/situationStore";

const BAND_LABEL: Record<string, string> = {
  none: "OK",
  normal: "NORMAL",
  generation: "GEN",
  network: "NET",
  protected: "PROT",
};

const BAND_TEXT: Record<string, string> = {
  none: "text-status-success",
  normal: "text-status-warning",
  generation: "text-status-warning",
  network: "text-status-error",
  protected: "text-status-error",
};

function fmtMw(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return Math.round(n).toLocaleString();
}

export function GridStatusSummaryPanel() {
  const gs = useSituationStore((s) => s.gridStatus);

  if (!gs) {
    return (
      <div className="border border-border rounded-lg p-3 bg-neutral-bg2" data-testid="grid-status-summary-empty">
        <h3 className="text-sm uppercase tracking-wider text-text-secondary font-bold flex items-center gap-1.5">
          <Activity className="h-3.5 w-3.5" />
          Grid Status
        </h3>
        <p className="text-text-tertiary text-sm mt-1 italic">Run a scan to assess</p>
      </div>
    );
  }

  const reserve = gs.nem.reserve_mw?.latest ?? gs.nem.reserve_mw?.avg ?? null;
  const bandCls = BAND_TEXT[gs.nem.frequency.worst_band] ?? "text-text-muted";
  const bandLabel = BAND_LABEL[gs.nem.frequency.worst_band] ?? "OK";

  return (
    <div className="border border-border rounded-lg p-3 bg-neutral-bg2 space-y-1.5" data-testid="grid-status-summary">
      <h3 className="text-sm uppercase tracking-wider text-text-secondary font-bold flex items-center gap-1.5">
        <Activity className="h-3.5 w-3.5" />
        Grid Status
      </h3>
      {/* Frequency line */}
      <div className="text-xs flex items-baseline gap-1.5">
        <span className="text-text-muted uppercase tracking-wider font-semibold text-micro">Hz</span>
        <span className="font-mono text-text-primary">
          {gs.nem.frequency.min_hz != null ? gs.nem.frequency.min_hz.toFixed(2) : "—"}–{gs.nem.frequency.max_hz != null ? gs.nem.frequency.max_hz.toFixed(2) : "—"}
        </span>
        <span className={`font-bold text-micro ${bandCls}`}>
          {bandLabel}{gs.nem.frequency.worst_region ? ` · ${gs.nem.frequency.worst_region}` : ""}
        </span>
      </div>
      {/* Reserve line */}
      <div className="text-xs flex items-baseline gap-1.5">
        <span className="text-text-muted uppercase tracking-wider font-semibold text-micro">Reserve</span>
        <span className="font-mono text-text-primary">{fmtMw(reserve)} <span className="text-text-muted text-micro">MW</span></span>
      </div>
      {/* Threat line */}
      <div className="text-xs flex items-baseline gap-1.5">
        <span className="text-text-muted uppercase tracking-wider font-semibold text-micro">Threat</span>
        <span className={`font-mono ${gs.nem.threatened_mw > 0 ? "text-status-warning" : "text-text-primary"}`}>
          {fmtMw(gs.nem.threatened_mw)} <span className="text-text-muted text-micro">MW</span>
        </span>
        <span className="text-text-muted text-micro">· {gs.situations.count} sit</span>
      </div>
    </div>
  );
}
