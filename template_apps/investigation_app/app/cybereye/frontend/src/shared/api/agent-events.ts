import type { ReasoningState } from "./api";
import type { AgentIdentity, ReasoningBlock, ToolRun } from "../types";

export function agentIdentity(value: Record<string, unknown>): AgentIdentity | undefined {
  if (typeof value.agent_id !== "string" || typeof value.agent_name !== "string"
      || typeof value.model !== "string" || typeof value.config_version !== "number") return undefined;
  return { id: value.agent_id, name: value.agent_name, model: value.model, version: value.config_version };
}

export function applyReasoning(
  blocks: ReasoningBlock[], id: string, delta: string, state: ReasoningState,
): ReasoningBlock[] {
  const known = blocks.some((block) => block.id === id);
  const next = known ? blocks : [...blocks, { id, text: "", done: false }];
  return next.map((block) => block.id !== id ? block : {
    ...block,
    text: state === "end" ? (block.text || delta) : block.text + delta,
    done: state === "end" || block.done,
  });
}

export function toolOutcome(result: unknown): "done" | "error" {
  return result && typeof result === "object" && "error" in result ? "error" : "done";
}

export function appendToolArguments(tools: ToolRun[], id: string, delta: string): ToolRun[] {
  return tools.map((tool) => tool.id === id
    ? { ...tool, pendingArgs: (tool.pendingArgs ?? "") + delta } : tool);
}

export function settleToolArguments(tools: ToolRun[], id: string, args: Record<string, unknown>): ToolRun[] {
  return tools.map((tool) => tool.id === id ? { ...tool, args, pendingArgs: undefined } : tool);
}

export function finishTool(tools: ToolRun[], id: string, result: unknown, finishedAt = Date.now()): ToolRun[] {
  return tools.map((tool) => tool.id === id ? {
    ...tool, result, status: toolOutcome(result), durationMs: finishedAt - tool.startedAt,
  } : tool);
}