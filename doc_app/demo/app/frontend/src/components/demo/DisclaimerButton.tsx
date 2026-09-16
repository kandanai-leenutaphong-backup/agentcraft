/**
 * DisclaimerButton — collapsible kiosk data-provenance notice.
 *
 * Module role:
 *   The kiosk URL is shared externally during demos. We need a clear
 *   "this is not real operational data" notice visible in every
 *   captured screenshot, but the full legal-grade text was eating
 *   significant header real estate. This component renders a compact
 *   amber pill in the header that, when clicked, opens a popover
 *   containing the full disclaimer. The pill itself carries the
 *   headline phrase so even the collapsed state communicates the
 *   essential claim ("Demo data only") without requiring a click.
 *
 * Lifecycle:
 *   - Click the pill → expanded=true → popover renders below it.
 *   - Click the pill again, click the close X, or click outside the
 *     popover → expanded=false.
 *   - Escape key while open also closes (presenter-clicker friendly).
 *
 * Key collaborators:
 *   - Mounted by App.tsx in the header, kiosk-only (gated by IS_KIOSK).
 *   - No store coupling — local React state is sufficient because no
 *     other component cares whether the disclaimer is open.
 */

import { useEffect, useRef, useState } from "react";
import { Info, X } from "lucide-react";
import { useVocab } from "@/stores/vocabularyStore";

export function DisclaimerButton() {
  const [expanded, setExpanded] = useState(false);
  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const disclaimerPill = useVocab("disclaimerPill");
  const disclaimerHeading = useVocab("disclaimerHeading");
  const disclaimerBody = useVocab("disclaimerBody");

  /* Outside-click + Escape close. Only attach listeners when expanded
     to keep the header inert during the 99% of the session the popover
     is closed. */
  useEffect(() => {
    if (!expanded) return undefined;
    const onDown = (e: MouseEvent) => {
      const target = e.target as Node | null;
      if (wrapperRef.current && target && !wrapperRef.current.contains(target)) {
        setExpanded(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [expanded]);

  return (
    <div ref={wrapperRef} className="relative">
      {/* Collapsed pill. The headline ("Demo data only") still
          communicates the core claim even without expansion, so a
          casual screenshot is still self-explanatory. */}
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        data-testid="kiosk-disclaimer-toggle"
        aria-expanded={expanded}
        aria-controls="kiosk-disclaimer-popover"
        title="Click for full data-provenance disclaimer"
        className="flex items-center gap-1.5 rounded-full border border-amber-400/40 bg-amber-400/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-amber-200 hover:bg-amber-400/20 transition-colors"
      >
        <Info className="h-3 w-3" />
        <span>{disclaimerPill}</span>
      </button>

      {/* Expanded popover — full legal text, kept below the header so
          it never obstructs the playback controls. Right-aligned so it
          stays inside the viewport on narrow widths. */}
      {expanded && (
        <div
          id="kiosk-disclaimer-popover"
          data-testid="kiosk-disclaimer-popover"
          role="dialog"
          aria-label="Data provenance disclaimer"
          className="absolute right-0 top-full z-50 mt-2 w-[28rem] rounded-lg border border-amber-400/40 bg-gray-950/95 p-4 text-[11px] leading-relaxed text-amber-100 shadow-2xl backdrop-blur"
        >
          <button
            type="button"
            onClick={() => setExpanded(false)}
            aria-label="Close disclaimer"
            className="absolute right-2 top-2 rounded p-1 text-amber-300/70 hover:bg-amber-400/10 hover:text-amber-100"
          >
            <X className="h-3.5 w-3.5" />
          </button>
          <div className="mb-2 pr-6 font-bold uppercase tracking-wider text-amber-200">
            {disclaimerHeading}
          </div>
          {disclaimerBody.map((para, i) => (
            <p key={i} className="mb-2">
              {para}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
