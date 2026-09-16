/**
 * Placeholder store — toggles demo/placeholder data for rapid UI development.
 *
 * Placeholder data has been removed from the deliverable. The store shell
 * is retained so existing imports compile without changes.
 */

import { create } from "zustand";
import type { SituationRecord } from "@/api/situationApi";
import type { PriorityAction } from "./panelStore";

interface PlaceholderStore {
  enabled: boolean;
  toggle: () => void;
  situations: SituationRecord[];
}

export const PLACEHOLDER_ACTIONS: PriorityAction[] = [];

export const usePlaceholderStore = create<PlaceholderStore>((set) => ({
  enabled: false,
  toggle: () => set((s) => ({ enabled: !s.enabled })),
  situations: [],
}));
