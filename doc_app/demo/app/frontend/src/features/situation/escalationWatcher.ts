/**
 * Escalation watcher \u2014 emits toasts when situation severity escalates.
 *
 * Role:
 *   Subscribes to situationStore.situations. After each scan, compares the
 *   new record set to the previous one (keyed by situation_id) and emits a
 *   toast whenever a situation's severity band moved up (e.g. MAJOR \u2192
 *   CRITICAL) or a brand-new CRITICAL / MAJOR situation appeared.
 *
 *   First scan of a session does not fire toasts \u2014 those situations are
 *   already displayed in the alerts panel and we don't want a flood of
 *   notifications on load. Only deltas between scans raise toasts.
 *
 * Why a watcher not a store action:
 *   Keeps escalation detection out of situationStore, which should stay a
 *   thin cache over the API response. The watcher is a pure side-effect
 *   boundary \u2014 read two store snapshots, emit zero-or-more toasts.
 *
 * Lifecycle:
 *   startEscalationWatcher() wires a zustand subscription and returns the
 *   unsubscribe fn. Mounted once by App.tsx.
 */

import { useSituationStore } from "@/stores/situationStore";
import { useToastStore } from "@/stores/toastStore";
import type { SituationRecord } from "@/api/situationApi";
import { rankFor } from "@/lib/severity";

/** Map a severity label to a toast tone. Critical/major use the alert tones,
 *  everything else stays informational to avoid noise. */
function toneForSeverity(severity: string): "info" | "warning" | "error" {
  if (severity === "CRITICAL") return "error";
  if (severity === "MAJOR") return "warning";
  return "info";
}

/**
 * Compare two situation arrays and return the set of records whose severity
 * escalated or that are entirely new at CRITICAL/MAJOR level.
 */
function diffEscalations(
  prev: SituationRecord[],
  next: SituationRecord[],
): SituationRecord[] {
  const prevById = new Map(prev.map((s) => [s.situation_id, s]));
  const escalated: SituationRecord[] = [];
  for (const n of next) {
    const rank = rankFor(n.severity);
    const old = prevById.get(n.situation_id);
    if (!old) {
      /* Brand-new situation. Only notify for CRITICAL or MAJOR to avoid
         flooding on routine INVESTIGATE-level activity. */
      if (rank <= 1) escalated.push(n);
      continue;
    }
    const oldRank = rankFor(old.severity);
    /* Severity rose in band (rank decreased). */
    if (rank < oldRank) escalated.push(n);
  }
  return escalated;
}

/**
 * Start the watcher. Returns an unsubscribe fn for cleanup in tests / HMR.
 */
export function startEscalationWatcher(): () => void {
  /* Previous snapshot lives in closure so the comparison is trivial. We
     initialise from the current store value so the very first scan after
     mount does not fire toasts for already-known situations. */
  let prev: SituationRecord[] = useSituationStore.getState().situations;
  let firstUpdate = true;

  const unsubscribe = useSituationStore.subscribe((state) => {
    const next = state.situations;
    /* Skip the first update fired by zustand on subscribe, and skip the
       case where the reference did not change (guard against re-renders
       that do not alter situations). */
    if (next === prev) return;
    if (firstUpdate) {
      firstUpdate = false;
      prev = next;
      return;
    }

    const escalations = diffEscalations(prev, next);
    prev = next;

    if (escalations.length === 0) return;

    const push = useToastStore.getState().pushToast;
    for (const sit of escalations) {
      push({
        title: `${sit.severity} \u2014 ${sit.station}`,
        body: sit.total_mw_lost > 0
          ? `${Math.round(sit.total_mw_lost)} MW threatened`
          : `Signals: alarm ${sit.alarm_score}, scada ${sit.scada_score}`,
        tone: toneForSeverity(sit.severity),
        durationMs: 6000,
        pulse: sit.severity === "CRITICAL",
      });
    }
  });

  return unsubscribe;
}
