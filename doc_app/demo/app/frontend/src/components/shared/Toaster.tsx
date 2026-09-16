/**
 * Toaster \u2014 fixed-position stack that renders active toasts from toastStore.
 *
 * Role:
 *   Single instance is mounted once in App.tsx. Subscribes to toastStore and
 *   renders each active toast as a slide-in card in the bottom-right corner.
 *   Handles auto-dismiss timers and click-to-dismiss.
 *
 * Why framer-motion:
 *   The codebase already depends on framer-motion; using it here for
 *   enter/exit gives us consistent spring physics for free. Respects
 *   `prefers-reduced-motion` via the shared CSS layer in index.css.
 */

import { useEffect } from "react";
import { AlertTriangle, CheckCircle2, Info, X, XCircle } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useToastStore } from "@/stores/toastStore";
import type { ToastEntry, ToastTone } from "@/stores/toastStore";

/* Tone \u2192 visual mapping. Keeps the palette anchored in the severity tokens
   defined by Tier 1 instead of introducing a new colour set. */
const TONE_ICON: Record<ToastTone, LucideIcon> = {
  info: Info,
  success: CheckCircle2,
  warning: AlertTriangle,
  error: XCircle,
};

const TONE_STRIP: Record<ToastTone, string> = {
  info: "border-l-situation-investigate",
  success: "border-l-status-success",
  warning: "border-l-situation-major",
  error: "border-l-situation-critical",
};

const TONE_ICON_COLOR: Record<ToastTone, string> = {
  info: "text-situation-investigate",
  success: "text-status-success",
  warning: "text-situation-major",
  error: "text-situation-critical",
};

/** Single-toast card with its own auto-dismiss timer. */
function ToastCard({ toast }: { toast: ToastEntry }) {
  const dismiss = useToastStore((s) => s.dismissToast);
  const Icon = TONE_ICON[toast.tone];

  /* Auto-dismiss after `durationMs`. 0 disables \u2014 used for sticky toasts
     (e.g. error toasts that must be acknowledged). */
  useEffect(() => {
    if (toast.durationMs <= 0) return;
    const timer = window.setTimeout(() => dismiss(toast.id), toast.durationMs);
    return () => window.clearTimeout(timer);
  }, [toast.id, toast.durationMs, dismiss]);

  return (
    <div
      data-testid={`toast-${toast.tone}`}
      role="status"
      className={[
        "pointer-events-auto flex items-start gap-2 rounded-lg border border-border bg-neutral-bg1 px-3 py-2 shadow-lg",
        "border-l-[3px]",
        TONE_STRIP[toast.tone],
        /* `fade-in` keyframe comes from index.css and already respects the
           `prefers-reduced-motion` guard, so we reuse it rather than adding
           a second animation. */
        "animate-[fade-in_150ms_var(--motion-ease)]",
        toast.pulse ? "animate-fresh-hairline" : "",
      ].join(" ")}
      style={{ minWidth: 260, maxWidth: 360 }}
    >
      <Icon className={`h-4 w-4 shrink-0 mt-0.5 ${TONE_ICON_COLOR[toast.tone]}`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-text-primary leading-tight">{toast.title}</p>
        {toast.body && (
          <p className="text-xs text-text-secondary mt-0.5 leading-snug break-words">{toast.body}</p>
        )}
      </div>
      <button
        data-testid={`toast-dismiss-${toast.id}`}
        onClick={() => dismiss(toast.id)}
        className="shrink-0 p-0.5 rounded text-text-muted hover:text-text-primary hover:bg-neutral-bg3"
        aria-label="Dismiss notification"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}

/** Fixed stack in the bottom-right corner. Pointer-events-none on the wrapper
 *  so the toast column never blocks interaction with underlying UI; each
 *  card re-enables pointer-events on itself. */
export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  return (
    <div
      data-testid="toaster"
      aria-live="polite"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2 items-end"
    >
      {toasts.map((t) => (
        <ToastCard key={t.id} toast={t} />
      ))}
    </div>
  );
}
