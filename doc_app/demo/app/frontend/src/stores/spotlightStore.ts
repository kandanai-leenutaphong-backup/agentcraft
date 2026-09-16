/**
 * spotlightStore — Module role:
 *
 *   Zustand store that drives the demo presentation spotlight. The
 *   spotlight is a single, optional, screen-wide overlay used SPARINGLY
 *   to draw the operator's eye to one specific UI element while a piece
 *   of narration calls it out. Set by demo scenario frames via the
 *   ``ui.spotlight.set`` patch op; cleared by ``ui.spotlight.clear`` or
 *   by another set call.
 *
 * Key collaborators:
 *   - components/demo/SpotlightOverlay.tsx — reads the store, resolves
 *     the target element by ``[data-spotlight-id="<targetId>"]``, draws
 *     a bright outlined box around it, and renders the caption.
 *   - demo/applyPatch.ts — translates the ``ui.spotlight.*`` ops into
 *     setSpotlight / clearSpotlight calls.
 *
 * Lifecycle:
 *   The store is module-scoped (singleton). State is null/empty when no
 *   spotlight is active; the overlay component renders nothing in that
 *   case.
 */

import { create } from "zustand";

/** Where the caption sits relative to the spotlit element.
 *  - ``auto`` lets the overlay decide based on viewport space. */
export type SpotlightPlacement = "top" | "bottom" | "left" | "right" | "auto";

/** Single active spotlight descriptor. */
export interface SpotlightTarget {
  /** Value of the ``data-spotlight-id`` attribute on the element to
   *  highlight. The overlay queries the DOM for the first match. */
  targetId: string;
  /** Short caption displayed inside the spotlight callout bubble. */
  caption: string;
  /** Optional preferred placement. Defaults to ``auto``. */
  placement?: SpotlightPlacement;
  /** Optional padding (px) added around the target's bounding box when
   *  drawing the spotlight outline. Default 8. */
  padding?: number;
}

interface SpotlightState {
  /** Currently active spotlight descriptor, or ``null`` if none. */
  active: SpotlightTarget | null;
  /** Replace the active spotlight (or initialise it). */
  setSpotlight: (target: SpotlightTarget) => void;
  /** Clear the active spotlight. No-op if none is active. */
  clearSpotlight: () => void;
}

/** Zustand hook for the singleton spotlight store. */
export const useSpotlightStore = create<SpotlightState>((set) => ({
  active: null,
  setSpotlight: (target) => set({ active: target }),
  clearSpotlight: () => set({ active: null }),
}));
