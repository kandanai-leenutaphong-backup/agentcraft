/**
 * Kiosk-mode bootstrap — seeds the stores with the minimum data needed
 * for the demo player to render against.
 *
 * Module role:
 *   In a normal build the agent list, session, and panel data all arrive
 *   via /api/* fetches. The kiosk build has no backend — so this module
 *   reads the kiosk_bootstrap section of the bundled scenario JSON and
 *   synthesises the same store shapes from it. Called once from App.tsx
 *   on mount when IS_KIOSK is true.
 *
 * Single-source-of-truth principle:
 *   Everything visible in the kiosk demo is authored in
 *   demo/scenarios/placeholder.json. This module is a thin adapter:
 *   read JSON → call setState. Do NOT add demo content here.
 */

import { useAgentStore } from "@/stores/agentStore";
import { useSessionStore } from "@/stores/sessionStore";
import { useLookupStore } from "@/stores/lookupStore";
import { useChatStore } from "@/stores/chatStore";
import { useSituationStore } from "@/stores/situationStore";
import type { SituationClassification } from "@/api/classifyApi";
import type { AgentInfo, ApiMessage } from "@/api/types";
import type { KioskBootstrap } from "./scenarioSchema";
import { setKioskRepliesFromBootstrap } from "./kioskReplies";
/* Static import — bootstrap data must be available synchronously on
  page load, before the user opens the scenario picker. The default bootstrap
   re-exports the active demo scenario's kiosk_bootstrap subtree so
   switching scenarios is a one-line change in defaultBootstrap.ts. */
import { defaultKioskBootstrap } from "./defaultBootstrap";

/** Active kiosk bootstrap — the agent roster, dock agents, and pre-seeded
 *  classifications used to seed the stores on page load. Falls back to an
 *  empty object so a scenario without a bootstrap section still loads. */
const BOOTSTRAP: KioskBootstrap = defaultKioskBootstrap ?? {};

/** Convert a KioskAgentSeed into the full AgentInfo shape the agent
 *  store expects. Tools list and counts are forced to empty since the
 *  main-column agent tabs do not surface tool metadata. */
function toAgentInfo(seed: NonNullable<KioskBootstrap["main_agents"]>[number]): AgentInfo {
  return {
    id: seed.id,
    name: seed.name,
    description: seed.description,
    tools: [],
    is_default: seed.is_default ?? false,
    tool_count: 0,
  };
}

/** Convert a KioskDockAgentSeed into the AgentInfo shape used by the
 *  dock UI. Surfaces the seeded tools list so the dock badges render. */
function toDockAgentInfo(seed: NonNullable<KioskBootstrap["dock_agents"]>[number]): AgentInfo {
  return {
    id: seed.id,
    name: seed.name,
    description: seed.description,
    tools: seed.tools ?? [],
    is_default: true,
    tool_count: (seed.tools ?? []).length,
  };
}

/** Build the welcome ApiMessage for a dock agent, or null if the
 *  scenario did not author one. */
function buildWelcome(seed: NonNullable<KioskBootstrap["dock_agents"]>[number]): ApiMessage | null {
  if (!seed.welcome) return null;
  return {
    id: `kiosk-welcome-${seed.id}`,
    role: "assistant",
    content: seed.welcome,
    parts: null,
    status: "complete",
    tool_calls: [],
    agent_name: seed.name,
    created_at: new Date().toISOString(),
  };
}

/** Apply one kiosk bootstrap to the stores. Used on first mount for the
 *  default scenario and again when a user selects an alternate scenario. */
export function applyKioskBootstrap(bootstrap: KioskBootstrap): void {
  /* Main-column agents — Investigator + Dispatcher in the default
     scenario. The first agent flagged is_default becomes the active
     tab; falls back to the first entry. */
  const mainAgents = (bootstrap.main_agents ?? []).map(toAgentInfo);
  const defaultMain = mainAgents.find((a) => a.is_default) ?? mainAgents[0];
  useAgentStore.setState({
    agents: mainAgents,
    activeAgentId: defaultMain?.id ?? null,
    toolDisplayNames: bootstrap.tool_display_names ?? {},
  });

  /* Synthetic session id so the chat panel renders past the
     activeSessionId guard. */
  useSessionStore.setState({
    activeSessionId: "demo-session",
  });

  /* Dock agents — drives the bottom Data tab. */
  const dockSeeds = bootstrap.dock_agents ?? [];
  const dockAgents = dockSeeds.map(toDockAgentInfo);
  useLookupStore.setState({
    dockAgents,
    activeDockAgentId: dockAgents[0]?.id ?? null,
    dockSessionId: "demo-dock-session",
  });

  /* Pre-populate each dock agent's chat slice with its welcome
     message so the dock greets the operator with capability hints
     rather than empty space. */
  for (const seed of dockSeeds) {
    const welcome = buildWelcome(seed);
    if (welcome) {
      useChatStore.getState().setMessages(seed.id, [welcome]);
    }
  }

  /* Pre-seed NER 4.2.3 classification results so the SituationCard
     badges render immediately when situations appear, without firing
     the classify API (which would 404 in kiosk mode). Each entry is
     written with status "ready" — the card skips the spinner and goes
     straight to the coloured badge. */
  const classSeeds = bootstrap.classifications ?? {};
  const classEntries: Record<string, { status: "ready"; classification?: SituationClassification; ner_citation?: string | null; rationale?: string }> = {};
  for (const [sitId, seed] of Object.entries(classSeeds)) {
    classEntries[sitId] = {
      status: "ready",
      classification: seed.classification as SituationClassification,
      ner_citation: seed.ner_citation,
      rationale: seed.rationale,
    };
  }
  if (Object.keys(classEntries).length > 0) {
    useSituationStore.setState({
      classifications: {
        ...useSituationStore.getState().classifications,
        ...classEntries,
      },
    });
  }

  setKioskRepliesFromBootstrap(bootstrap);
}

/** Seed all stores the kiosk player depends on. Idempotent. */
export function seedKioskStores(): void {
  applyKioskBootstrap(BOOTSTRAP);
}
