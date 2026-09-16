/**
 * Bundled demo scenarios.
 *
 * Module role:
 *   Registry of every scenario that ships in the SPA. The PlayDemoButton
 *   reads this list to populate its dropdown. Adding a scenario =
 *   one split TS scenario directory or .json file in scenarios/ + one
 *   entry below.
 *
 * Lazy loading:
 *   Each scenario is lazy-imported via dynamic import() so its JSON is
 *   only fetched when the user actually selects it. Keeps the initial
 *   bundle small.
 */

import type { Scenario } from "./scenarioSchema";
import { assertScenario } from "./scenarioSchema";

/** Metadata for the picker dropdown. */
export interface ScenarioListEntry {
  id: string;
  label: string;
  description: string;
  /** Industry category for grouped dropdown display. */
  industry: string;
  /** Loads, validates, and returns the scenario JSON. */
  load: () => Promise<Scenario>;
}

/** Wraps a dynamic import so the scenario is validated at load time. */
function makeLoader(importFn: () => Promise<{ default: unknown }>): () => Promise<Scenario> {
  return async () => {
    const mod = await importFn();
    const data = mod.default;
    assertScenario(data);
    return data;
  };
}

/** All bundled scenarios, in display order. */
export const SCENARIOS: ScenarioListEntry[] = [
  {
    id: "ngm-busbar-trip",
    label: "NGM Busbar Trip",
    industry: "Energy",
    description:
      "275 kV busbar fault at MARRABEL_NX \u2014 412 MW generation loss, precursor detection, " +
      "classification, topology, investigator chat, dispatcher actions.",
    load: makeLoader(() => import("./scenarios/ngm_busbar_trip")),
  },
];
