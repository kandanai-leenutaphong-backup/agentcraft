/**
 * Scenario API — scenario and scenario-scoped metadata calls.
 *
 * Extracted from client.ts for domain-specific organization.
 */

import type {
  AgentInfo,
  ScenarioDetail,
} from "./types";
import { BASE, authHeaders, handleResponse } from "./client";

/** Response shape from GET /api/agents — agents list + tool display names. */
export interface AgentsResponse {
  agents: AgentInfo[];
  tool_display_names: Record<string, string>;
}

/** Fetch agent definitions and tool display name mapping.
 *  @param surface - Optional filter: 'chat' for main agents, 'dock' for lookup dock agents.
 */
export async function getAgents(surface?: string): Promise<AgentsResponse> {
  const params = surface ? `?surface=${encodeURIComponent(surface)}` : "";
  const res = await fetch(`${BASE}/agents/${params}`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<AgentsResponse>(res);
}

/** Fetch the active scenario's detail metadata (display_name, examples, demo_flows). */
export async function getScenarioDetail(): Promise<ScenarioDetail> {
  const res = await fetch(`${BASE}/scenario`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<ScenarioDetail>(res);
}

/** Fetch the active scenario's graph topology data. */
export async function getTopology(signal?: AbortSignal): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/scenario/topology`, {
    headers: { ...await authHeaders() },
    signal,
  });
  return handleResponse<Record<string, unknown>>(res);
}

/** Fetch the full assembled prompt text for an agent. */
export async function getAgentPrompt(agentId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${BASE}/scenario/agent-prompt?agent_id=${encodeURIComponent(agentId)}`, {
    headers: { ...await authHeaders() },
  });
  return handleResponse<Record<string, unknown>>(res);
}
