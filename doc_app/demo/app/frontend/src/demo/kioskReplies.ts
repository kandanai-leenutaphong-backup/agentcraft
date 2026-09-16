/**
 * kioskReplies — canned assistant responses used when the public demo
 * build (IS_KIOSK) intercepts chatStore.sendMessage.
 *
 * Module role:
 *   Thin adapter that reads the kiosk_bootstrap.dock_agents[].replies
 *   tables out of the bundled scenario JSON. All canned content lives
 *   in demo/scenarios/placeholder.json — do NOT add reply entries here.
 *
 * Lookup rules:
 *   - First entry whose lowercased ``match`` substring appears in the
 *     prompt wins.
 *   - The entry with match === "" is the catch-all fallback.
 *   - Agents not present in the scenario get a generic placeholder.
 */

import type { KioskBootstrap, KioskReplyEntry } from "./scenarioSchema";
import { defaultKioskBootstrap } from "./defaultBootstrap";

/** Lift the per-agent reply tables out of the active default scenario
 *  once at module load. Re-keyed by agent id for O(1) lookup on each
 *  send. The default bootstrap is statically bundled so the lookup is
 *  available synchronously when the user hits Send. */
let REPLIES: Record<string, KioskReplyEntry[]> = (() => {
  const out: Record<string, KioskReplyEntry[]> = {};
  for (const seed of defaultKioskBootstrap?.dock_agents ?? []) {
    if (seed.replies && seed.replies.length > 0) {
      out[seed.id] = seed.replies;
    }
  }
  return out;
})();

/** Replace the active reply tables when the user selects a scenario.
 *  The kiosk app has no backend, so dock-agent chat must follow the
 *  selected scenario's bootstrap instead of the static default. */
export function setKioskRepliesFromBootstrap(bootstrap: KioskBootstrap): void {
  const next: Record<string, KioskReplyEntry[]> = {};
  for (const seed of bootstrap.dock_agents ?? []) {
    if (seed.replies && seed.replies.length > 0) {
      next[seed.id] = seed.replies;
    }
  }
  REPLIES = next;
}

/** Resolve a canned reply for an agent + user prompt. Returns a generic
 *  placeholder when no reply table exists for the agent. */
export function kioskFakeReply(agentId: string, prompt: string): string {
  const table = REPLIES[agentId];
  if (!table) {
    return "Demo mode: this agent has no canned responses configured.";
  }
  const needle = prompt.toLowerCase();
  for (const entry of table) {
    if (entry.match === "") continue;
    if (needle.includes(entry.match)) return entry.text;
  }
  /* Catch-all — entry with empty match. */
  const fallback = table.find((e) => e.match === "");
  return fallback?.text ?? "Demo mode response.";
}
