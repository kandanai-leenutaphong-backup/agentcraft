/**
 * paletteStore \u2014 open/close state for the command palette and help overlay.
 *
 * Two booleans with toggle actions. Kept separate from panelStore so the
 * palette/help lifecycle does not entangle with the control-room data
 * flow (priorities, grid status, etc.).
 */

import { create } from "zustand";

interface PaletteStore {
  /** Command palette visible. */
  open: boolean;
  /** Help overlay visible. */
  helpOpen: boolean;

  openPalette: () => void;
  close: () => void;
  togglePalette: () => void;

  openHelp: () => void;
  closeHelp: () => void;
  toggleHelp: () => void;
}

export const usePaletteStore = create<PaletteStore>((set, get) => ({
  open: false,
  helpOpen: false,

  openPalette: () => set({ open: true, helpOpen: false }),
  close: () => set({ open: false }),
  togglePalette: () => set({ open: !get().open, helpOpen: false }),

  openHelp: () => set({ helpOpen: true, open: false }),
  closeHelp: () => set({ helpOpen: false }),
  toggleHelp: () => set({ helpOpen: !get().helpOpen, open: false }),
}));
