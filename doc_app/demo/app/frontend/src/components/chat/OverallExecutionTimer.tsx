/**
 * OverallExecutionTimer — live wall-clock counter for the active assistant
 * turn.
 *
 * Role in system: rendered above the streaming MessageBubble while the
 * orchestrator (or a delegated specialist) is generating. Sources its
 * start time from the active agent slice's ``_sendTimestamp`` so the
 * counter reflects the moment the user pressed Send, not the moment
 * the first token arrived. Stops as soon as ``status`` leaves
 * "streaming".
 *
 * Side effects: schedules a 100 ms setInterval while mounted; cleared
 * on unmount.
 *
 * Designed to be placed beside per-tool timers so the operator can see
 * BOTH the cumulative turn time and the time spent inside the current
 * tool call.
 */

import { useEffect, useState } from "react";
import { Activity } from "lucide-react";
import { useChatStore } from "@/stores/chatStore";
import { useAgentStore } from "@/stores/agentStore";

/* Format milliseconds as compact "X.Ys" or "Xm Ys" for header display. */
function fmt(ms: number): string {
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)}s`;
  const m = Math.floor(s / 60);
  const r = Math.floor(s % 60);
  return `${m}m ${r}s`;
}

export function OverallExecutionTimer() {
  /* Subscribe to the active agent's slice — the slice already exposes
     `_sendTimestamp` (set when sendMessage fires) and `status`
     ("streaming" while the SSE stream is open). */
  const activeAgentId = useAgentStore((s) => s.activeAgentId);
  const sendTs = useChatStore((s) =>
    activeAgentId ? s.getSlice(activeAgentId)._sendTimestamp : null,
  );
  const status = useChatStore((s) =>
    activeAgentId ? s.getSlice(activeAgentId).status : "idle",
  );
  const active = status === "streaming" && sendTs !== null;

  /* Re-render every 100 ms while active so the counter ticks visibly
     without burning cycles on idle tabs. */
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => setNow(Date.now()), 100);
    return () => window.clearInterval(id);
  }, [active]);

  if (!active || !sendTs) return null;
  const elapsed = now - sendTs;

  return (
    <div
      data-testid="overall-execution-timer"
      className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-brand/10 text-brand text-label font-mono tabular-nums"
      title="Total time since you sent the message"
    >
      <Activity className="h-3 w-3 animate-pulse" />
      <span>{fmt(elapsed)}</span>
    </div>
  );
}
