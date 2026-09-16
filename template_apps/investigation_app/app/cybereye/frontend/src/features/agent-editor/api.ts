import type { AgentToolInfo } from "@agentcraft/resource-explorer";
import { requestJson } from "../../shared/api";

export interface InstructionFile { name: string; content: string }

export interface AgentDefinition {
  name: string;
  model: string;
  version_name: string;
  system_prompt: string;
  instruction_files: InstructionFile[];
  tool_ids: string[];
}

export interface SavedAgent extends AgentDefinition {
  agent_id: string;
  version: number;
  base_version: number;
  latest_version: number;
  versions: number[];
  version_names: Record<number, string>;
  created_at: string;
  builtin: boolean;
}

export interface AgentSummary {
  id: string;
  name: string;
  model: string;
  latest_version: number;
  versions: number[];
  version_names: Record<number, string>;
  builtin: boolean;
  tool_ids: string[];
}

export interface InvestigatorAssignment { agent_id: string; version: number; revision: number }

export interface AgentCatalogue {
  agents: AgentSummary[];
  models: { id: string; name: string }[];
  tools: AgentToolInfo[];
  foundation_files: InstructionFile[];
  investigator: InvestigatorAssignment;
  assigned_agent: { id: string; name: string; model: string; version: number; version_name: string };
  investigator_required_tools: string[];
}

const BASE = "/api/cyber/agent-editor";

export const agentEditorApi = {
  catalogue: (signal?: AbortSignal) => requestJson<AgentCatalogue>(BASE, { signal }),
  version: (id: string, version?: number, signal?: AbortSignal) => requestJson<SavedAgent>(
    `${BASE}/agents/${encodeURIComponent(id)}${version ? `?version=${version}` : ""}`, { signal }),
  save: (draft: AgentDefinition, previous: SavedAgent | null) => requestJson<SavedAgent>(
    previous ? `${BASE}/agents/${encodeURIComponent(previous.agent_id)}/versions` : `${BASE}/agents`, {
      method: "POST", body: JSON.stringify({ ...draft, base_version: previous?.version ?? 0,
        expected_latest_version: previous?.latest_version ?? 0 }),
    }),
  assign: (agent_id: string, version: number, expected_revision: number) => requestJson<InvestigatorAssignment>(
    `${BASE}/roles/investigator`, { method: "PUT", body: JSON.stringify({ agent_id, version, expected_revision }) }),
};

export function definitionOf(value: SavedAgent): AgentDefinition {
  return { name: value.name, model: value.model, version_name: value.version_name ?? "", system_prompt: value.system_prompt,
    instruction_files: value.instruction_files, tool_ids: value.tool_ids };
}

export function versionLabel(version: number, name = ""): string {
  return name.trim() ? `v${version} - ${name.trim()}` : `v${version}`;
}