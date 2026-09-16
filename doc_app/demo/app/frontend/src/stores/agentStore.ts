/**
 * Agent store — configured agent tabs + active selection + delegated tabs.
 *
 * Module role:
 *   Fetches agent metadata from GET /api/agents and tracks which tab is
 *   currently active. The simplified two-agent flow (Investigator,
 *   Investigator, Dispatcher) registers all three as configured agents,
 *   so the delegated-agent registry only fires for the rare ad-hoc
 *   specialist that is NOT in agent_config.yaml.
 *
 * Key collaborators:
 *   - api/client.ts:getAgents()       — fetches agent list
 *   - components/chat/AgentTabBar.tsx  — renders tabs from agents array
 *   - stores/chatStore.ts             — reads activeAgentId for slice routing
 *
 * Dependents:
 *   Used by: AgentTabBar, ChatPanel, ChatInput, App.tsx (init)
 */

import { create } from "zustand";
import type { AgentInfo } from "@/api/types";
import * as api from "@/api/client";

/** Ephemeral delegated-agent tab info — created on delegation_start when
 *  the target id is not a configured agent. The simplified runtime keeps
 *  this only for safety; in practice all three agents are configured. */
export interface DelegatedAgent {
  id: string;
  name: string;
  task: string;
  status: "streaming" | "complete" | "error";
}

interface AgentStore {
  /** All agents defined in the active scenario. */
  agents: AgentInfo[];
  /** Currently selected agent tab. Null until agents are fetched. */
  activeAgentId: string | null;
  /** If set, the agent to return to when "Return to Origin" is clicked. */
  returnToAgentId: string | null;
  /** Active delegated-agent tabs for non-configured specialist instances. */
  delegatedAgents: DelegatedAgent[];
  /** Tool function name → human-readable display name mapping from config. */
  toolDisplayNames: Record<string, string>;
  /** Fetch agent definitions from GET /api/agents. Sets activeAgentId to default. */
  fetchAgents: () => Promise<void>;
  /** Switch the active tab to a configured agent. */
  setActiveAgent: (id: string) => void;
  /** Navigate to a delegated agent's tab with return tracking. */
  viewDelegatedTab: (targetAgentId: string) => void;
  /** Return to the origin agent tab (clears returnToAgentId). */
  returnToOrigin: () => void;
  /** Register an ephemeral subagent tab on delegation_start. No-op when the
   *  target id matches a configured agent (those have permanent header tabs). */
  addDelegatedAgent: (id: string, name: string, task: string) => void;
  /** Mark a delegated agent as complete or error. */
  updateDelegatedStatus: (id: string, status: "complete" | "error") => void;
  /** Clear all delegated agent tabs (on new message or session switch). */
  clearDelegatedAgents: () => void;
}

export const useAgentStore = create<AgentStore>((set, get) => ({
  agents: [],
  activeAgentId: null,
  returnToAgentId: null,
  delegatedAgents: [],
  toolDisplayNames: {},

  fetchAgents: async () => {
    const maxRetries = 3;
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const response = await api.getAgents("chat");
        const agents = response.agents ?? (response as any);
        const toolDisplayNames = response.tool_display_names ?? {};
        if (agents.length === 0) {
          console.warn(`[agentStore] fetchAgents returned 0 agents (attempt ${attempt + 1})`);
          if (attempt < maxRetries) {
            await new Promise((r) => setTimeout(r, 1000));
            continue;
          }
        }
        const defaultAgent = agents.find((a: AgentInfo) => a.is_default) ?? agents[0];
        set({
          agents,
          activeAgentId: defaultAgent?.id ?? null,
          toolDisplayNames,
        });
        return;
      } catch (err) {
        console.warn(`[agentStore] fetchAgents failed (attempt ${attempt + 1}/${maxRetries + 1}):`, err);
        if (attempt < maxRetries) {
          await new Promise((r) => setTimeout(r, 1000));
        }
      }
    }
  },

  setActiveAgent: (id: string) => set({
    activeAgentId: id,
    returnToAgentId: null,
  }),

  viewDelegatedTab: (targetAgentId: string) => {
    const current = get().activeAgentId;
    set({
      activeAgentId: targetAgentId,
      returnToAgentId: current,
    });
  },

  returnToOrigin: () => {
    const returnTo = get().returnToAgentId;
    if (returnTo) {
      set({ activeAgentId: returnTo, returnToAgentId: null });
    }
  },

  addDelegatedAgent: (id, name, task) => {
    const { agents, delegatedAgents } = get();
    /* Configured agents own permanent header tabs — never duplicate them. */
    if (agents.some((agent) => agent.id === id)) return;
    if (delegatedAgents.some((d) => d.id === id)) return;
    set({
      delegatedAgents: [
        ...delegatedAgents,
        { id, name, task, status: "streaming" },
      ],
    });
  },

  updateDelegatedStatus: (id: string, status: "complete" | "error") => {
    set({
      delegatedAgents: get().delegatedAgents.map((d) =>
        d.id === id ? { ...d, status } : d,
      ),
    });
  },

  clearDelegatedAgents: () => {
    set({ delegatedAgents: [], returnToAgentId: null });
  },
}));
