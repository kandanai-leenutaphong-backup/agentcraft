/**
 * SpotlightOverlay — Module role:
 *
 *   A single, optional, full-screen overlay that draws a bright outlined
 *   box around one DOM element identified by its ``data-spotlight-id``
 *   attribute, and renders an accompanying caption bubble next to it.
 *   Driven by ``stores/spotlightStore.ts``; patched in by demo scenario
 *   frames via the ``ui.spotlight.set`` / ``ui.spotlight.clear`` ops.
 *
 *   The visual treatment is deliberately loud — animated yellow ring +
 *   subtle dim of the rest of the screen — because the spotlight is
 *   used SPARINGLY to land a single beat of narration on a single
 *   element. The caption is positioned with viewport-edge avoidance.
 *
 * Key collaborators:
 *   - stores/spotlightStore.ts — source of truth.
 *   - demo/applyPatch.ts — wires the patch ops to store actions.
 *
 * Lifecycle:
 *   Mounted once at the App root. Renders nothing when no spotlight is
 *   active. While active, it polls the target's bounding rect on every
 *   animation frame so the box tracks scrolls, layout shifts, or
 *   resizes without re-renders elsewhere in the app.
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useSpotlightStore, type SpotlightPlacement } from "@/stores/spotlightStore";
import { useVocabularyStore } from "@/stores/vocabularyStore";

/** Resolved on-screen geometry of the spotlit target plus the caption. */
interface Geometry {
  /** Viewport-space rect of the spotlit element including padding. */
  rect: { x: number; y: number; width: number; height: number };
  /** Viewport-space top-left of the caption bubble. */
  caption: { x: number; y: number };
  /** Final placement chosen for the caption (after auto-resolution). */
  placement: Exclude<SpotlightPlacement, "auto">;
}

/* Caption bubble dimensions — used to keep the bubble inside the
   viewport when auto-placing. The bubble itself is constrained by
   max-width via Tailwind so these are upper bounds. */
const CAPTION_MAX_W = 360;
const CAPTION_EST_H = 96;
/* Gap between the spotlit rect and the caption bubble. */
const CAPTION_GAP = 16;

/** Compute the caption position for a given placement, given the
 *  spotlit rect and viewport bounds. Returns the top-left of the
 *  bubble. Caller must clamp the result to the viewport. */
function placeCaption(
  rect: Geometry["rect"],
  placement: Exclude<SpotlightPlacement, "auto">,
): { x: number; y: number } {
  switch (placement) {
    /* Above the rect, horizontally centred. */
    case "top":
      return {
        x: rect.x + rect.width / 2 - CAPTION_MAX_W / 2,
        y: rect.y - CAPTION_EST_H - CAPTION_GAP,
      };
    /* Below the rect, horizontally centred. */
    case "bottom":
      return {
        x: rect.x + rect.width / 2 - CAPTION_MAX_W / 2,
        y: rect.y + rect.height + CAPTION_GAP,
      };
    /* Left of the rect, vertically centred. */
    case "left":
      return {
        x: rect.x - CAPTION_MAX_W - CAPTION_GAP,
        y: rect.y + rect.height / 2 - CAPTION_EST_H / 2,
      };
    /* Right of the rect, vertically centred. */
    case "right":
      return {
        x: rect.x + rect.width + CAPTION_GAP,
        y: rect.y + rect.height / 2 - CAPTION_EST_H / 2,
      };
  }
}

/** Pick the best placement when ``auto``: prefer right, then left, then
 *  bottom, then top, choosing whichever fits in the viewport. */
function autoPlacement(rect: Geometry["rect"]): Exclude<SpotlightPlacement, "auto"> {
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  if (vw - (rect.x + rect.width) >= CAPTION_MAX_W + CAPTION_GAP) return "right";
  if (rect.x >= CAPTION_MAX_W + CAPTION_GAP) return "left";
  if (vh - (rect.y + rect.height) >= CAPTION_EST_H + CAPTION_GAP) return "bottom";
  return "top";
}

export function SpotlightOverlay() {
  const active = useSpotlightStore((s) => s.active);
  const [geom, setGeom] = useState<Geometry | null>(null);
  /* RAF handle for the bounding-rect poller — cancelled on unmount or
     when the spotlight clears. */
  const rafRef = useRef<number | null>(null);

  /* Re-resolve the target's bounding rect on every animation frame so
     the spotlight tracks scrolls, layout shifts, transitions, and
     resizes without subscribing to a thicket of events. The cost is
     negligible while a spotlight is active and zero when it is not. */
  useLayoutEffect(() => {
    if (!active) {
      setGeom(null);
      return;
    }
    const padding = active.padding ?? 8;
    const tick = () => {
      /* Find the first element with the requested data-spotlight-id.
         If none, the overlay renders nothing this frame; the next
         frame may pick it up if the element appears later. */
      const el = document.querySelector<HTMLElement>(
        `[data-spotlight-id="${CSS.escape(active.targetId)}"]`,
      );
      if (!el) {
        setGeom(null);
        rafRef.current = requestAnimationFrame(tick);
        return;
      }
      const r = el.getBoundingClientRect();
      const rect = {
        x: r.left - padding,
        y: r.top - padding,
        width: r.width + padding * 2,
        height: r.height + padding * 2,
      };
      /* Resolve auto placement and compute the caption anchor. */
      const placement: Exclude<SpotlightPlacement, "auto"> =
        active.placement && active.placement !== "auto"
          ? active.placement
          : autoPlacement(rect);
      let caption = placeCaption(rect, placement);
      /* Clamp the caption inside the viewport with an 8px margin so it
         never spills off the edge of the screen on small displays. */
      caption = {
        x: Math.max(8, Math.min(window.innerWidth - CAPTION_MAX_W - 8, caption.x)),
        y: Math.max(8, Math.min(window.innerHeight - CAPTION_EST_H - 8, caption.y)),
      };
      setGeom({ rect, caption, placement });
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    };
  }, [active]);

  /* Auto-scroll the spotlit element into view once on activation so the
     operator's eye lands somewhere visible. Uses center alignment with
     smooth behaviour; safe across all browsers we target. */
  useEffect(() => {
    if (!active) return;
    const el = document.querySelector<HTMLElement>(
      `[data-spotlight-id="${CSS.escape(active.targetId)}"]`,
    );
    if (el) el.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
  }, [active]);

  if (!active) return null;
  if (!geom) {
    /* Target not yet in the DOM — render only the dim backdrop so the
       screen does not flash bare while the next frame retries. */
    return (
      <div
        data-testid="spotlight-overlay-pending"
        className="pointer-events-none fixed inset-0 z-[60] bg-black/35"
      />
    );
  }

  return (
    <div
      data-testid="spotlight-overlay"
      className="pointer-events-none fixed inset-0 z-[60]"
    >
      {/* Dim backdrop with a transparent rectangular cut-out aligned to
          the spotlit element. Implemented with four absolutely-positioned
          panels so the cut-out region is genuinely click-through (CSS
          mask would also work but has weaker browser support and worse
          interaction with backdrop filters). */}
      <div className="absolute bg-black/45" style={{ left: 0, top: 0, right: 0, height: geom.rect.y }} />
      <div className="absolute bg-black/45" style={{ left: 0, top: geom.rect.y + geom.rect.height, right: 0, bottom: 0 }} />
      <div className="absolute bg-black/45" style={{ left: 0, top: geom.rect.y, width: geom.rect.x, height: geom.rect.height }} />
      <div
        className="absolute bg-black/45"
        style={{
          left: geom.rect.x + geom.rect.width,
          top: geom.rect.y,
          right: 0,
          height: geom.rect.height,
        }}
      />

      {/* The spotlight ring itself — animated amber outline + soft glow.
          ``ring-spotlight`` and ``glow-spotlight`` are inline styles so
          the component is self-contained and does not require a tailwind
          config edit. The ``animate-pulse`` driver gives the ring a slow
          breathing pulse for ~2s on activation; CSS keyframes keep it
          alive while the spotlight stays up. */}
      <div
        data-testid="spotlight-ring"
        className="absolute rounded-lg pointer-events-none animate-pulse"
        style={{
          left: geom.rect.x,
          top: geom.rect.y,
          width: geom.rect.width,
          height: geom.rect.height,
          /* Three-layer glow: inner bright amber, outer soft amber,
             plus a thick solid outline so the box reads even on busy
             backgrounds. Colours match a tailwind amber-300/400 pair. */
          boxShadow:
            "0 0 0 3px rgb(252 211 77), 0 0 0 6px rgb(251 191 36 / 0.55), 0 0 32px 4px rgb(251 191 36 / 0.45)",
        }}
      />

      {/* Caption bubble — pointer-events enabled so a click handler
          could be added later, but we leave the overlay
          ``pointer-events-none`` so the rest of the UI remains
          interactive when the spotlight is up. */}
      <div
        data-testid="spotlight-caption"
        className="absolute pointer-events-auto rounded-xl bg-amber-50 text-gray-900 shadow-2xl ring-1 ring-amber-300 px-4 py-3"
        style={{
          left: geom.caption.x,
          top: geom.caption.y,
          maxWidth: CAPTION_MAX_W,
        }}
      >
        <div className="text-[10px] font-bold uppercase tracking-widest text-amber-700 mb-1">
          {useVocabularyStore.getState().vocab.spotlightPrefix}
        </div>
        <div className="text-sm leading-snug font-medium whitespace-pre-line">
          {active.caption}
        </div>
      </div>
    </div>
  );
}
