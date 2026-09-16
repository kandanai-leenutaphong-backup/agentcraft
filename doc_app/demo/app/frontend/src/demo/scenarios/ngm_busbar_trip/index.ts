/**
 * NGM Busbar Trip — scenario assembler.
 *
 * Module role:
 *   Assembles the complete Scenario object from split data and phase
 *   modules. This is the entry point for the dynamic import in
 *   demo/index.ts.
 *
 * Architecture:
 *   The scenario is split into ~10 files to keep each under ~150 lines.
 *   This file concatenates the phase frame arrays in playback order
 *   and attaches the kiosk bootstrap config.
 *
 * Key collaborators:
 *   - demo/index.ts — imports this module via dynamic import().
 *   - demo/scenarioSchema.ts — type definitions for Scenario, Frame, etc.
 *   - bootstrap.ts — kiosk agent roster, dock replies, classifications.
 *   - situations.ts — the 5 situation card payloads.
 *   - topology.ts — topology graph centered on MARRABEL_NX.
 *   - phases/*.ts — frame arrays for each demo phase.
 *
 * Disclaimer:
 *   Due to the highly sensitive and mission-critical nature of the data,
 *   this demo has been fully anonymised to avoid all reference to real
 *   power assets, activities, or configurations, while showcasing the
 *   unique advantages of GridIQ.
 */

import type { Scenario } from "../../scenarioSchema";
import { SCENARIO_SCHEMA } from "../../scenarioSchema";
import { bootstrap } from "./bootstrap";
import { scanFrames } from "./phases/01_scan";
import { classifyFrames } from "./phases/02_classify";
import { topologyFrames } from "./phases/03_topology";
import { investigateFrames } from "./phases/04_investigate";
import { differentialFrames, rootCauseFrames } from "./phases/04c_differential";
import { delegateFrames } from "./phases/05_delegate";
import { actionFrames } from "./phases/06_actions";
import { precursorFrames } from "./phases/07_precursor";

/** The complete NGM busbar trip demo scenario. ~33 frames, ~95 seconds runtime. */
const scenario: Scenario = {
  schema: SCENARIO_SCHEMA,
  id: "ngm-busbar-trip",
  label: "NGM Busbar Trip",
  description:
    "A 275 kV busbar fault at MARRABEL_NX causes 412 MW generation loss. " +
    "Demonstrates situation scan, classification, topology, investigator " +
    "chat with tool calls, dispatcher delegation, priority actions, and " +
    "precursor detection 37 minutes before the event.",
  kiosk_bootstrap: bootstrap,
  frames: [
    ...scanFrames,
    ...classifyFrames,
    ...topologyFrames,
    /* Handoff and the wide-angle station summary. */
    ...investigateFrames.slice(0, 3),
    /* Name three candidates, then eliminate two on evidence. */
    ...differentialFrames,
    /* Bus assignment from the CIM graph. */
    ...investigateFrames.slice(7, 9),
    /* Converge on the common-mode family, then system impact. */
    ...rootCauseFrames,
    /* Historical corroboration, participants, synthesis. */
    ...investigateFrames.slice(9),
    ...delegateFrames,
    ...actionFrames,
    ...precursorFrames,
  ],
};

/* Default export for dynamic import() compatibility — the makeLoader
 * wrapper in demo/index.ts expects `mod.default`. */
export default scenario;
