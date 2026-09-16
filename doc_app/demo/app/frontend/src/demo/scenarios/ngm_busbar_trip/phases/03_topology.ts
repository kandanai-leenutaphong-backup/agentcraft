/**
 * Phase 3 — Topology graph load (frame f000f).
 *
 * Module role:
 *   Loads the topology graph centered on MARRABEL_NX with alarm overlay
 *   highlighting Units 3 and 4 in red.
 *
 * Runtime: ~1 second.
 */

import type { Frame } from "../../../scenarioSchema";
import { TOPOLOGY_PAYLOAD } from "../topology";

export const topologyFrames: Frame[] = [
  /* f000f — Topology graph loads with CRITICAL overlay on GEN.3 and GEN.4. */
  {
    id: "f000f",
    chapter: "Topology",
    narration:
      "Topology auto-loads, centred on MARRABEL_NX, the station behind the CRITICAL card.",
    annotation: {
      target: "panel-center",
      caption:
        "Centre panel switches to topology view. Red equipment is alarmed; line loadings update live as the grid compensates.",
      placement: "left",
    },
    transition_ms: 600,
    patch: {
      "topology.set": TOPOLOGY_PAYLOAD,
    },
  },
];
