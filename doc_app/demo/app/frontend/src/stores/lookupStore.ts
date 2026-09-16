/**
 * Data Search Assistant store — manages the center-tab dock state.
 *
 * Tracks the dock-surface assistant, active assistant ID, and dock session ID.
 * Completely independent from the main chatStore and sessionStore; the
 * assistant uses its own session.
 */

import { create } from "zustand";
import type { AgentInfo } from "@/api/types";
import * as api from "@/api/client";
import { IS_KIOSK } from "@/foundation/constants";

interface LookupStore {
  /** Whether the dock is visible. */
  isOpen: boolean;
  /** Dock panel height in pixels. */
  height: number;
  /** Assistants available in the dock surface. Expected to be data_assistant. */
  dockAgents: AgentInfo[];
  /** Currently active dock assistant. */
  activeDockAgentId: string | null;
  /** Session ID for dock conversations. Created on first use. */
  dockSessionId: string | null;
  /** Whether a dock session is being created. */
  creatingSession: boolean;
  /** Tool display name mapping (shared with main). */
  toolDisplayNames: Record<string, string>;

  /** Toggle dock open/closed. */
  toggle: () => void;
  /** Set dock height (from resize). */
  setHeight: (h: number) => void;
  /** Switch active dock assistant. */
  setActiveDockAgent: (id: string) => void;
  /** Fetch dock agents from API. */
  fetchDockAgents: () => Promise<void>;
  /** Ensure a dock session exists. Creates one if needed. */
  ensureDockSession: () => Promise<string | null>;
}

export const useLookupStore = create<LookupStore>((set, get) => ({
  isOpen: false,
  height: 300,
  dockAgents: [],
  activeDockAgentId: null,
  dockSessionId: null,
  creatingSession: false,
  toolDisplayNames: {},

  toggle: () => set((s) => ({ isOpen: !s.isOpen })),

  setHeight: (h) => set({ height: Math.max(150, Math.min(h, window.innerHeight * 0.85)) }),

  setActiveDockAgent: (id) => set({ activeDockAgentId: id }),

  fetchDockAgents: async () => {
    if (IS_KIOSK) return;
    try {
      const response = await api.getAgents("dock");
      const agents = response.agents ?? [];
      const toolDisplayNames = response.tool_display_names ?? {};
      const first = agents[0];
      set({
        dockAgents: agents,
        activeDockAgentId: first?.id ?? null,
        toolDisplayNames,
      });
    } catch (err) {
      console.error("[lookupStore] fetchDockAgents failed:", err);
    }
  },

  ensureDockSession: async () => {
    const { dockSessionId, creatingSession } = get();
    if (dockSessionId) return dockSessionId;
    if (IS_KIOSK) {
      const id = "demo-dock-session";
      set({ dockSessionId: id, creatingSession: false });
      return id;
    }
    if (creatingSession) return null;

    set({ creatingSession: true });
    try {
      const session = await api.createSession({ title: "Data Search Assistant" });
      set({ dockSessionId: session.id, creatingSession: false });
      return session.id;
    } catch (err) {
      console.error("[lookupStore] createSession failed:", err);
      set({ creatingSession: false });
      return null;
    }
  },
}));
