/**
 * FrequencyDisturbanceResult — renders `frequency_disturbance_profile`
 * inside the ToolResultCard scaffold.
 *
 * Envelope (see specs/T-C11_frequency_disturbance_profile_20260518.md §3):
 *   {
 *     "verdict":              "system_disturbance" | "local_excursion"
 *                              | "normal" | "no_data",
 *     "fos_classification":   "NORMAL" | "OPERATIONAL" | "BELOW_OPERATIONAL"
 *                              | "CONTAINMENT" | "EMERGENCY" | ...,
 *     "anchor_ts":            "<iso>",
 *     "pre_event_baseline_hz": <float>,
 *     "nem_wide_nadir_hz":    <float>,
 *     "max_delta_f_hz":       <float>,
 *     "recovery_time_s":      <float>,
 *     "regional_spread":      [ { cluster_label, n_stations,
 *                                  median_nadir_hz, median_delta_f_hz,
 *                                  clamped_at_band_edge, stations }, ... ],
 *     "caveats":              [ ... ],
 *     "hz_alarms_in_window":  [ ... ],
 *     "primitives_used":      [ ... ]
 *   }
 *
 * Layout:
 *   - scope band — anchor_ts.
 *   - signal band — verdict + FOS classification + Δf + nadir + recovery.
 *     Tones map to FOS severity (NORMAL/OPERATIONAL = success;
 *     BELOW_OPERATIONAL = warning; CONTAINMENT/EMERGENCY = error).
 *   - body — regional spread as compact cluster cards, then caveats
 *     and HZ-* alarm tally beneath.
 *
 * `verdict === "no_data"` short-circuits to an info note.
 */

import type { ToolResultProps } from "./index";
import { ToolResultCard } from "./ToolResultCard";
import type { ScopeBadge, SignalChip, SignalTone } from "./ToolResultCard";
import { JsonFallback } from "./JsonFallback";
import { extractError, parseToolResult } from "./helpers";

interface RegionalCluster {
  cluster_label?: string;
  n_stations?: number;
  median_nadir_hz?: number;
  median_delta_f_hz?: number;
  clamped_at_band_edge?: boolean;
  stations?: string[];
}

interface FrequencyEnvelope {
  verdict?: string;
  fos_classification?: string;
  anchor_ts?: string;
  pre_event_baseline_hz?: number;
  nem_wide_nadir_hz?: number;
  max_delta_f_hz?: number;
  recovery_time_s?: number;
  regional_spread?: RegionalCluster[];
  caveats?: string[];
  hz_alarms_in_window?: unknown[];
}

/* FOS-band → signal tone. Order of badness mirrors the AEMO FOS
   ladder; anything we do not recognise falls through to neutral so a
   new band added server-side does not crash the renderer. */
const FOS_TONE: Record<string, SignalTone> = {
  NORMAL: "success",
  OPERATIONAL: "success",
  BELOW_OPERATIONAL: "warning",
  CONTAINMENT: "error",
  EMERGENCY: "error",
};

const VERDICT_TONE: Record<string, SignalTone> = {
  normal: "success",
  local_excursion: "warning",
  system_disturbance: "error",
  no_data: "neutral",
};

export function FrequencyDisturbanceResult({ result }: ToolResultProps) {
  const parsed = parseToolResult<FrequencyEnvelope & Record<string, unknown>>(result);
  if (!parsed) return <JsonFallback result={result} />;

  const errDetail = extractError(parsed);
  if (errDetail) return <ToolResultCard error={{ detail: errDetail }} />;

  const verdict = parsed.verdict ?? "unknown";

  if (verdict === "no_data") {
    return (
      <ToolResultCard
        signal={[{ label: "verdict", value: "no data", tone: "neutral" }]}
        note="Fewer than 5 stations had HZ samples in the window — no frequency profile available."
        noteTone="info"
      />
    );
  }

  const scope: ScopeBadge[] = [];
  if (typeof parsed.anchor_ts === "string") {
    scope.push({ label: "anchor", value: parsed.anchor_ts });
  }

  const fos = parsed.fos_classification ?? "";
  const signal: SignalChip[] = [
    {
      label: "verdict",
      value: verdict.replace(/_/g, " "),
      tone: VERDICT_TONE[verdict] ?? "neutral",
    },
  ];
  if (fos) {
    signal.push({
      label: "FOS",
      value: fos,
      tone: FOS_TONE[fos] ?? "neutral",
    });
  }
  if (typeof parsed.max_delta_f_hz === "number") {
    signal.push({
      label: "Δf",
      value: `${parsed.max_delta_f_hz.toFixed(3)} Hz`,
      tone: "accent",
    });
  }
  if (typeof parsed.nem_wide_nadir_hz === "number") {
    signal.push({
      label: "nadir",
      value: `${parsed.nem_wide_nadir_hz.toFixed(3)} Hz`,
      tone: "accent",
    });
  }
  if (typeof parsed.recovery_time_s === "number") {
    signal.push({
      label: "recovery",
      value: `${parsed.recovery_time_s.toFixed(1)} s`,
      tone: "accent",
    });
  }

  const clusters = Array.isArray(parsed.regional_spread) ? parsed.regional_spread : [];
  const caveats = Array.isArray(parsed.caveats) ? (parsed.caveats as string[]) : [];
  const hzAlarmCount = Array.isArray(parsed.hz_alarms_in_window)
    ? parsed.hz_alarms_in_window.length
    : 0;

  return (
    <ToolResultCard scope={scope} signal={signal}>
      <div className="flex flex-col gap-1.5">
        {clusters.length > 0 && (
          <div className="flex flex-col gap-1">
            <span className="text-micro font-medium uppercase tracking-wider text-text-muted">
              Regional spread
            </span>
            {clusters.map((c, i) => (
              <ClusterCard key={`${c.cluster_label ?? "c"}-${i}`} cluster={c} />
            ))}
          </div>
        )}
        {hzAlarmCount > 0 && (
          <div className="text-label text-text-secondary">
            <span className="text-text-muted">HZ alarms in window:</span>{" "}
            <span className="font-mono">{hzAlarmCount}</span>
          </div>
        )}
        {caveats.length > 0 && (
          <ul className="list-disc list-inside text-label text-text-muted space-y-0.5">
            {caveats.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        )}
      </div>
    </ToolResultCard>
  );
}

/* Single-cluster compact card. Median Δf is the salient signal; the
   station list is space-separated and clamps to a single line with a
   tooltip-style title so the row stays scan-friendly. */
function ClusterCard({ cluster }: { cluster: RegionalCluster }) {
  const stations = Array.isArray(cluster.stations) ? cluster.stations : [];
  const stationsLabel = stations.join(", ");
  const median = cluster.median_delta_f_hz;
  const nadir = cluster.median_nadir_hz;
  return (
    <div className="rounded border border-border/60 bg-neutral-bg2/40 px-2 py-1">
      <div className="flex flex-wrap items-baseline gap-1.5 text-label">
        <span className="font-mono font-semibold text-text-primary">
          {cluster.cluster_label ?? "cluster"}
        </span>
        <span className="rounded bg-neutral-bg3 px-1.5 py-0.5 font-mono text-text-secondary">
          n={cluster.n_stations ?? stations.length}
        </span>
        {typeof median === "number" && (
          <span className="rounded bg-accent/10 text-accent px-1.5 py-0.5 font-mono">
            median Δf {median.toFixed(3)} Hz
          </span>
        )}
        {typeof nadir === "number" && (
          <span className="rounded bg-accent/10 text-accent px-1.5 py-0.5 font-mono">
            median nadir {nadir.toFixed(3)} Hz
          </span>
        )}
        {cluster.clamped_at_band_edge && (
          <span className="rounded bg-status-warning/10 text-status-warning px-1.5 py-0.5">
            clamped
          </span>
        )}
      </div>
      {stations.length > 0 && (
        <p
          className="mt-0.5 text-label text-text-muted truncate"
          title={stationsLabel}
        >
          {stationsLabel}
        </p>
      )}
    </div>
  );
}
