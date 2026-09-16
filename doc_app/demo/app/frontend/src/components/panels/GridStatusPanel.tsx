/**
 * GridStatusPanel — centre "Status" tab body.
 *
 * Renders the `grid_status` payload produced by the detector layer
 * `tools/situations/detector/layers/grid_status.py`. Always anchored to
 * the operator's scan window; never labelled "live" unless the
 * underlying corpus is realtime (see spec §14).
 *
 * Layout (mockup `/tmp/grid_status_mockup.html`):
 *   1. Anchor strip — scan window + tag-dict version.
 *   2. Hero — Frequency / Reserve / Generation+Renewable% / Threat.
 *   3. Per-region grid — Hz, Generation, Demand, Reserve, Wind/Solar,
 *      Threatened, situation count.
 *   4. Severity distribution + top threat rows.
 *   5. Data-quality footer.
 *
 * Renders an empty state until the first scan returns; the parent tab
 * stays visible so the operator can switch to it before scanning.
 */

import { useState } from "react";
import { Activity, AlertTriangle, ChevronDown, ChevronRight } from "lucide-react";
import { useSituationStore } from "@/stores/situationStore";
import type {
  GridStatus,
  GridStatusDataQuality,
  GridStatusMetric,
  GridStatusRegion,
} from "@/api/situationApi";

const REGIONS = ["NSW", "VIC", "QLD", "SA", "TAS"] as const;

/* Frequency band → operator-facing badge classes. Same vocabulary as
   OperatingStatePanel's previous BAND_BADGE so the visual language is
   familiar across surfaces. */
const BAND_CLASS: Record<string, string> = {
  none:       "bg-status-success/15 text-status-success",
  normal:     "bg-status-warning/15 text-status-warning",
  generation: "bg-status-warning/20 text-status-warning font-bold",
  network:    "bg-status-error/15 text-status-error",
  protected:  "bg-status-error/25 text-status-error font-bold",
};
const BAND_LABEL: Record<string, string> = {
  none:       "OK",
  normal:     "NORMAL",
  generation: "GEN",
  network:    "NET",
  protected:  "PROT",
};

function fmtNumber(n: number | null | undefined, digits = 0): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (digits > 0) return n.toFixed(digits);
  return Math.round(n).toLocaleString();
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toFixed(1)}%`;
}

function heroValue(metric: GridStatusMetric | null | undefined): number | null {
  if (!metric) return null;
  return metric.latest ?? metric.avg ?? null;
}

function tileTitle(metric: GridStatusMetric | null | undefined): string {
  if (!metric) return "no metric";
  const tag = metric.tag_id ?? "—";
  const avg = metric.avg != null ? fmtNumber(metric.avg, 1) : "—";
  const min = metric.min != null ? fmtNumber(metric.min, 1) : "—";
  const max = metric.max != null ? fmtNumber(metric.max, 1) : "—";
  const latest = metric.latest != null ? fmtNumber(metric.latest, 1) : "—";
  const ts = metric.latest_ts ?? "—";
  const cnt = metric.sample_count ?? 0;
  return `${tag}\nlatest ${latest} @ ${ts}\navg ${avg} · min ${min} · max ${max}\nsamples ${cnt}`;
}

function RegionFrequency({ region }: { region: GridStatusRegion }) {
  const f = region.frequency;
  const cls = BAND_CLASS[f.band_breached] ?? BAND_CLASS.none;
  const label = BAND_LABEL[f.band_breached] ?? f.band_label ?? "OK";
  return (
    <div className="flex flex-col gap-0.5">
      <span className="font-mono text-sm text-text-primary">
        {f.min_hz != null ? f.min_hz.toFixed(2) : "—"}–{f.max_hz != null ? f.max_hz.toFixed(2) : "—"}
        <span className="text-text-muted text-xs"> Hz</span>
      </span>
      <span className={`px-1.5 py-0.5 text-micro font-bold rounded inline-block self-start ${cls}`}>
        {label}{f.excursion_count > 0 ? ` · ${f.excursion_count} exc` : ""}
      </span>
    </div>
  );
}

function MetricCell({ metric, digits = 0 }: { metric: GridStatusMetric | null | undefined; digits?: number }) {
  const v = heroValue(metric);
  return (
    <div className="flex flex-col gap-0.5" title={tileTitle(metric)}>
      <span className="font-mono text-sm font-bold text-text-primary">
        {fmtNumber(v, digits)}<span className="text-text-muted text-xs"> MW</span>
      </span>
      <span className="text-micro text-text-muted font-mono truncate">
        {metric?.tag_id ?? "—"}
      </span>
    </div>
  );
}

export function GridStatusPanel() {
  const gridStatus = useSituationStore((s) => s.gridStatus);
  const [dqOpen, setDqOpen] = useState(false);  const [threatsOpen, setThreatsOpen] = useState(true);

  if (!gridStatus) {
    return (
      <div data-testid="grid-status-empty" className="h-full flex flex-col items-center justify-center text-center px-6 gap-3 text-text-muted">
        <Activity className="h-8 w-8 text-text-tertiary" />
        <div className="space-y-1">
          <p className="text-sm font-semibold text-text-secondary">No Grid Status yet</p>
          <p className="text-xs text-text-muted max-w-xs">
            Run a Situation Detector scan to populate the dashboard. Values
            anchor to the scan window.
          </p>
        </div>
      </div>
    );
  }

  const gs: GridStatus = gridStatus;
  const nem = gs.nem;
  const nemFreqCls = BAND_CLASS[nem.frequency.worst_band] ?? BAND_CLASS.none;
  const nemFreqLabel = BAND_LABEL[nem.frequency.worst_band] ?? "OK";
  // Surface scan-window sparsity prominently: when the backend reports
  // that every canonical region/NEM tag returned zero samples, the panel
  // would otherwise look "broken" because every numeric tile is —.
  const sparseWindow = gs.data_quality.find((d) => d.code === "no_metric_samples_in_window");

  return (
    <div data-testid="grid-status-panel" className="p-3 space-y-2.5">
      {/* Anchor strip */}
      <div className="flex items-center justify-between text-micro text-text-muted font-mono">
        <span>scan {gs.window.start} → {gs.window.end} AEST · source <span className="text-text-secondary">{gs.window.source}</span></span>
        <span>tags <span className="text-text-secondary">{gs.tag_dict_version}</span></span>
      </div>

      {sparseWindow && (
        <div
          data-testid="grid-status-sparse-window-banner"
          className="border border-status-warning/40 bg-status-warning/10 rounded px-3 py-2 flex items-start gap-2 text-xs"
        >
          <AlertTriangle className="h-3.5 w-3.5 text-status-warning shrink-0 mt-0.5" />
          <span className="text-text-secondary">
            <span className="font-bold text-status-warning">No telemetry samples in window.</span>{" "}
            {sparseWindow.message}
          </span>
        </div>
      )}

      {/* Hero strip */}
      <div className="grid grid-cols-4 gap-1 bg-border/30 rounded overflow-hidden">
        {/* Frequency */}
        <div className="bg-neutral-bg2 p-3 flex flex-col gap-1.5" data-testid="grid-status-hero-frequency">
          <span className="text-micro text-text-muted uppercase tracking-wider font-bold">NEM Frequency</span>
          <span className="text-2xl font-mono font-bold text-text-primary">
            {nem.frequency.min_hz != null ? nem.frequency.min_hz.toFixed(2) : "—"}–{nem.frequency.max_hz != null ? nem.frequency.max_hz.toFixed(2) : "—"}
            <span className="text-sm text-text-muted font-semibold"> Hz</span>
          </span>
          <span className={`px-1.5 py-0.5 text-micro font-bold rounded self-start ${nemFreqCls}`}>
            {nemFreqLabel}{nem.frequency.worst_region ? ` · ${nem.frequency.worst_region}` : ""}
          </span>
        </div>
        {/* Reserve */}
        <div className="bg-neutral-bg2 p-3 flex flex-col gap-1.5" data-testid="grid-status-hero-reserve" title={tileTitle(nem.reserve_mw)}>
          <span className="text-micro text-text-muted uppercase tracking-wider font-bold">NEM Reserve</span>
          <span className="text-2xl font-mono font-bold text-text-primary">
            {fmtNumber(heroValue(nem.reserve_mw))}<span className="text-sm text-text-muted font-semibold"> MW</span>
          </span>
          <span className="text-micro text-text-muted font-mono truncate">{nem.reserve_mw?.tag_id ?? "—"}</span>
        </div>
        {/* Generation + Renewable% */}
        <div className="bg-neutral-bg2 p-3 flex flex-col gap-1.5" data-testid="grid-status-hero-generation">
          <span className="text-micro text-text-muted uppercase tracking-wider font-bold">NEM Generation</span>
          <span className="text-2xl font-mono font-bold text-text-primary">
            {fmtNumber(nem.generation_mw.value)}<span className="text-sm text-text-muted font-semibold"> MW</span>
          </span>
          <span className="text-micro text-text-muted">
            Renew <span className="text-text-secondary font-mono">{fmtPct(nem.renewable_pct_generation)}</span>
            <span className="text-text-tertiary"> · {fmtNumber(nem.renewable_mw.value)} MW</span>
          </span>
        </div>
        {/* Threat */}
        <div className="bg-neutral-bg2 p-3 flex flex-col gap-1.5" data-testid="grid-status-hero-threat">
          <span className="text-micro text-text-muted uppercase tracking-wider font-bold">Threatened</span>
          <span className={`text-2xl font-mono font-bold ${(nem.threatened_pct_generation ?? 0) > 5 ? "text-status-error" : (nem.threatened_pct_generation ?? 0) > 1 ? "text-status-warning" : "text-text-primary"}`}>
            {fmtNumber(nem.threatened_mw)}<span className="text-sm text-text-muted font-semibold"> MW</span>
          </span>
          <span className="text-micro text-text-muted">
            <span className="font-mono text-text-secondary">{fmtPct(nem.threatened_pct_generation)}</span> of generation · {gs.situations.count} sit
          </span>
        </div>
      </div>

      {/* Per-region grid */}
      <div className="border border-border rounded overflow-hidden">
        <div className="grid grid-cols-7 bg-neutral-bg3 text-micro text-text-muted uppercase tracking-wider font-bold">
          <div className="px-2 py-1.5">Region</div>
          <div className="px-2 py-1.5">Frequency</div>
          <div className="px-2 py-1.5">Generation</div>
          <div className="px-2 py-1.5">Demand</div>
          <div className="px-2 py-1.5">Reserve</div>
          <div className="px-2 py-1.5">Renew (W / S)</div>
          <div className="px-2 py-1.5">Threat</div>
        </div>
        {REGIONS.map((r) => {
          const region = gs.regions[r];
          if (!region) return null;
          const threatColour = region.threatened_pct_generation != null && region.threatened_pct_generation > 10
            ? "text-status-error"
            : region.threatened_pct_generation != null && region.threatened_pct_generation > 1
              ? "text-status-warning"
              : "text-text-primary";
          return (
            <div key={r} data-testid={`grid-status-region-${r}`} className="grid grid-cols-7 border-t border-border/40 text-xs items-center">
              <div className="px-2 py-1.5 font-bold text-text-primary">{r}</div>
              <div className="px-2 py-1.5"><RegionFrequency region={region} /></div>
              <div className="px-2 py-1.5"><MetricCell metric={region.generation_mw} /></div>
              <div className="px-2 py-1.5"><MetricCell metric={region.demand_mw} /></div>
              <div className="px-2 py-1.5"><MetricCell metric={region.reserve_mw} /></div>
              <div className="px-2 py-1.5">
                <div className="flex flex-col gap-0.5" title={`wind ${tileTitle(region.wind_mw)}\nsolar ${tileTitle(region.solar_mw)}`}>
                  <span className="font-mono text-sm text-text-primary">
                    W {fmtNumber(heroValue(region.wind_mw))} / S {fmtNumber(heroValue(region.solar_mw))}
                  </span>
                  <span className="text-micro text-text-muted">{fmtPct(region.renewable_pct_generation)} of gen</span>
                </div>
              </div>
              <div className="px-2 py-1.5">
                <span className={`font-mono text-sm font-bold ${threatColour}`}>
                  {fmtNumber(region.threatened_mw)}<span className="text-text-muted text-xs font-normal"> MW</span>
                </span>
                <div className="text-micro text-text-muted">
                  {region.situation_count} sit · {fmtPct(region.threatened_pct_generation)}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Severity distribution + top threats */}
      <div className="border border-border rounded">
        <button
          type="button"
          className="w-full flex items-center gap-2 px-3 py-2 bg-neutral-bg2"
          onClick={() => setThreatsOpen(!threatsOpen)}
        >
          {threatsOpen ? <ChevronDown className="h-3 w-3 text-text-muted" /> : <ChevronRight className="h-3 w-3 text-text-muted" />}
          <span className="text-xs font-bold uppercase tracking-wider text-text-secondary">Situations</span>
          <span className="text-micro text-text-muted font-mono">
            {gs.situations.count} sit · {gs.situations.station_count} stn · {fmtNumber(gs.situations.threatened_mw)} MW threatened
          </span>
        </button>
        {threatsOpen && (
          <div className="p-3 space-y-3">
            {/* Severity distribution */}
            <div className="flex items-center gap-3 text-micro">
              {Object.entries(gs.situations.severity_counts).map(([bucket, n]) => (
                <span key={bucket} data-testid={`grid-status-sev-${bucket}`} className="font-mono">
                  <span className="text-text-muted">{bucket}:</span>{" "}
                  <span className="text-text-primary font-bold">{n}</span>
                </span>
              ))}
            </div>
            {/* Top threats table */}
            {gs.situations.top_threats.length === 0 ? (
              <div className="text-micro italic text-text-muted">No MW threats in this window.</div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-micro">
                  <thead className="text-text-muted uppercase tracking-wider">
                    <tr>
                      <th className="px-1 py-0.5 text-left font-semibold">Station</th>
                      <th className="px-1 py-0.5 text-left font-semibold">Region</th>
                      <th className="px-1 py-0.5 text-right font-semibold">MW</th>
                      <th className="px-1 py-0.5 text-right font-semibold">Sit</th>
                      <th className="px-1 py-0.5 text-left font-semibold">Worst</th>
                    </tr>
                  </thead>
                  <tbody>
                    {gs.situations.top_threats.map((row) => (
                      <tr key={row.station} className="even:bg-neutral-bg2/30">
                        <td className="px-1 py-0.5 font-mono font-bold text-text-primary">{row.station}</td>
                        <td className="px-1 py-0.5 text-text-secondary">{row.region}</td>
                        <td className="px-1 py-0.5 text-right font-mono text-text-primary">{fmtNumber(row.mw)}</td>
                        <td className="px-1 py-0.5 text-right font-mono text-text-secondary">{row.situation_count}</td>
                        <td className="px-1 py-0.5 text-text-secondary uppercase">{row.worst_severity}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Data quality footer */}
      {gs.data_quality.length > 0 && (
        <div className="border border-border rounded">
          <button
            type="button"
            className="w-full flex items-center gap-2 px-3 py-1.5 bg-neutral-bg2"
            onClick={() => setDqOpen(!dqOpen)}
            data-testid="grid-status-data-quality-toggle"
          >
            {dqOpen ? <ChevronDown className="h-3 w-3 text-text-muted" /> : <ChevronRight className="h-3 w-3 text-text-muted" />}
            <AlertTriangle className="h-3 w-3 text-text-muted" />
            <span className="text-micro font-bold uppercase tracking-wider text-text-muted">
              Data notes ({gs.data_quality.length})
            </span>
          </button>
          {dqOpen && (
            <ul className="p-3 space-y-1 text-micro">
              {gs.data_quality.map((dq: GridStatusDataQuality, i) => (
                <li key={i} className="flex gap-2">
                  <span
                    className={
                      dq.severity === "error"
                        ? "text-status-error font-bold"
                        : dq.severity === "warning"
                          ? "text-status-warning font-bold"
                          : "text-text-muted"
                    }
                  >
                    [{dq.severity.toUpperCase()}]
                  </span>
                  <span className="text-text-secondary">{dq.code}</span>
                  <span className="text-text-muted">— {dq.message}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
