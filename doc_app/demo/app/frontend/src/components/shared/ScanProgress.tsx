/**
 * ScanProgress — animated progress indicator for the situation detector
 * scan.
 *
 * Role in system: Pure presentational component for the
 * SituationAlertsPanel. The underlying detector endpoint is single-shot
 * (no streaming), so the bar is **time-based**: it interpolates against
 * a rolling-average estimate from situationStore. Logarithmic easing
 * keeps the bar advancing past the estimate without ever hitting 100%
 * — completion is signalled by the parent unmounting the component.
 *
 * Two surfaces:
 *   - <ScanProgressBar />  : thin top-of-panel bar (header strip).
 *   - <ScanProgressPanel /> : full-body crunching status with rotating
 *                              messages, elapsed counter, and ETA.
 *
 * Both subscribe to the same situationStore fields:
 *   scanStartedAt, scanEstimateMs.
 *
 * Side effects: schedules a 100 ms requestAnimationFrame loop while
 * mounted to redraw the bar; stops on unmount. No network or store
 * mutations.
 */

import { useEffect, useState } from "react";
import { Loader2, Radar } from "lucide-react";
import { useSituationStore } from "@/stores/situationStore";

/* Status messages cycled through during a scan. The detector pipeline
   roughly mirrors this order (alarms → SCADA → join → score → rank),
   so the rotation gives operators a credible sense of progress even
   though we cannot observe each stage server-side. */
const STATUS_MESSAGES = [
  "Pulling alarms…",
  "Joining SCADA step-changes…",
  "Crunching frequency excursions…",
  "Scoring stations…",
  "Ranking severity…",
] as const;

/* How long each status message lingers before cycling to the next.
   2.5 s feels active without being twitchy. */
const STATUS_ROTATE_MS = 2500;

/* Asymptotic progress curve. Returns a value in [0, 0.99) — never 1.0
   so the bar visibly stalls near the end, signalling "almost there"
   rather than "stuck at 100% forever". The exponent controls how
   quickly the curve approaches its ceiling. */
function progressFraction(elapsedMs: number, estimateMs: number): number {
  if (estimateMs <= 0) return 0;
  const t = elapsedMs / estimateMs;
  /* 1 - exp(-1.6 t) hits 0.80 at t=1, 0.95 at t=2, 0.99 at t=2.9.
     A scan that takes 2.9× longer than estimate still won't claim
     completion — it'll just keep nudging upward. */
  return Math.min(0.99, 1 - Math.exp(-1.6 * t));
}

/* Subscribe to a 100 ms render tick while a scan is in flight so the
   elapsed/ETA strings update smoothly. Returns the current Date.now()
   value, or null when no scan is running. Stops the timer on unmount
   and whenever scanStartedAt becomes null. */
function useScanTick(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(id);
  }, [active]);
  return now;
}

/* Format milliseconds as "Xs" or "Xm Ys" for compact display. */
function fmtSeconds(ms: number): string {
  const s = Math.max(0, Math.floor(ms / 1000));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

/**
 * ScanProgressBar — slim 2 px progress bar suitable for a panel header.
 * Renders nothing when no scan is in flight. The bar fills against the
 * rolling estimate using a logarithmic curve so it never falsely claims
 * completion.
 */
export function ScanProgressBar() {
  const startedAt = useSituationStore((s) => s.scanStartedAt);
  const estimateMs = useSituationStore((s) => s.scanEstimateMs);
  const active = startedAt !== null;
  const now = useScanTick(active);

  if (!active || !startedAt || !estimateMs) return null;

  const elapsed = now - startedAt;
  const pct = progressFraction(elapsed, estimateMs) * 100;

  return (
    <div
      data-testid="scan-progress-bar"
      className="h-0.5 w-full bg-neutral-bg3 overflow-hidden"
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(pct)}
    >
      <div
        className="h-full bg-brand transition-[width] duration-100 ease-out"
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

/**
 * ScanProgressPanel — body-sized crunching status. Replaces the empty
 * "Click Scan to detect situations" placeholder while a scan is in
 * flight. Shows a spinning radar icon, a rotating status message, the
 * elapsed wall time, and a best-effort ETA derived from the rolling
 * average. Returns null when no scan is in flight so callers can
 * render their normal empty state.
 */
export function ScanProgressPanel() {
  const startedAt = useSituationStore((s) => s.scanStartedAt);
  const estimateMs = useSituationStore((s) => s.scanEstimateMs);
  const active = startedAt !== null;
  const now = useScanTick(active);

  /* Rotate the status message on its own timer — independent of the
     render tick so the cadence stays predictable regardless of how
     often the elapsed counter ticks. */
  const [statusIdx, setStatusIdx] = useState(0);
  useEffect(() => {
    if (!active) {
      setStatusIdx(0);
      return;
    }
    const id = window.setInterval(
      () => setStatusIdx((i) => (i + 1) % STATUS_MESSAGES.length),
      STATUS_ROTATE_MS,
    );
    return () => window.clearInterval(id);
  }, [active]);

  if (!active || !startedAt || !estimateMs) return null;

  const elapsed = now - startedAt;
  const pct = progressFraction(elapsed, estimateMs) * 100;
  /* ETA = max(estimate - elapsed, 1 s). Floor at 1 s so the badge does
     not flicker between "1s" and "0s" near the asymptote. */
  const remainingMs = Math.max(1000, estimateMs - elapsed);

  return (
    <div
      data-testid="scan-progress-panel"
      className="flex flex-col items-center justify-center gap-3 py-8 px-6 text-center"
    >
      {/* Radar + spinner stack — radar communicates the domain (scanning
          stations), the surrounding spinner communicates "in flight". */}
      <div className="relative">
        <Loader2 className="h-10 w-10 text-brand/30 animate-spin" />
        <Radar className="h-5 w-5 text-brand absolute inset-0 m-auto" />
      </div>

      <div className="text-sm font-semibold text-text-primary">
        {STATUS_MESSAGES[statusIdx]}
      </div>

      {/* Determinate progress bar — wider and taller than the header
          variant so the percentage is readable at a glance. */}
      <div className="w-full max-w-xs">
        <div
          className="h-1.5 w-full bg-neutral-bg3 rounded-full overflow-hidden"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(pct)}
        >
          <div
            className="h-full bg-brand transition-[width] duration-100 ease-out"
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="flex items-center justify-between mt-1.5 text-label font-mono text-text-muted">
          <span data-testid="scan-progress-elapsed">{fmtSeconds(elapsed)} elapsed</span>
          <span data-testid="scan-progress-eta">~{fmtSeconds(remainingMs)} left</span>
        </div>
      </div>

      <p className="text-label text-text-muted max-w-xs">
        Estimating from your last scan ({fmtSeconds(estimateMs)}). Larger
        time windows take longer.
      </p>
    </div>
  );
}
