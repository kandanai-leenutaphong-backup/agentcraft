/**
 * Phase 7 — Precursor reveal (frames f028–f032).
 *
 * Module role:
 *   The headline win of the demo. The presenter scrolls back to the
 *   situation list, the operator asks about the 10:38 INVESTIGATE card,
 *   the agent calls pattern_history, and delivers the punchline: GridIQ
 *   flagged DS-275-13 37 minutes before the trip.
 *
 * Runtime: ~16 seconds.
 */

import type { Frame } from "../../../scenarioSchema";

export const precursorFrames: Frame[] = [
  /* f028 — Switch back to Investigator to bring situations list into focus.
     The narration sets up the callback to the 10:38 card; the spotlight
     fires on the next frame so the operator's eye knows where to look
     before the words "INVESTIGATE card from 10:38" land. */
  {
    id: "f028",
    chapter: "The precursor",
    narration:
      "Earlier, an INVESTIGATE card timestamped 10:38 was set aside.",
    transition_ms: 800,
    patch: {
      "agent.set_active": { agent: "investigator" },
    },
  },

  /* f028b — SPOTLIGHT the precursor situation card. The dim backdrop +
     amber ring pulls the operator's eye to the card while the caption
     bubble names what they are looking at. Held for ~3 s so the beat
     lands; cleared by f029 before the chat user message appears so the
     spotlight does not compete with the new chat bubble. */
  {
    id: "f028b",
    transition_ms: 3000,
    patch: {
      "ui.spotlight.set": {
        target: "situation-card-ngm-pre-1",
        caption:
          "The 10:38 INVESTIGATE on MARRABEL_NX. Same station as the trip — " +
          "37 minutes earlier. Filed before the busbar collapsed.",
        placement: "auto",
        padding: 6,
      },
    },
  },

  /* f028c — Clear the spotlight, then immediately drop the operator's
     follow-up question. Two ops in one frame so the visual handoff is
     clean: spotlight off → user message in. */
  {
    id: "f028c",
    transition_ms: 200,
    patch: {
      "ui.spotlight.clear": {},
    },
  },

  /* f029 — User asks about the precursor card. */
  {
    id: "f029",
    narration: "The operator asks the obvious follow-up.",
    transition_ms: 600,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "user",
        text: "What was the 10:38 INVESTIGATE on MARRABEL? Same station, just before the trip.",
      },
    },
  },

  /* f030 — pattern_history tool call: agent queries precursor pattern data. */
  {
    id: "f030",
    narration: "The agent pulls the pattern detail for that card.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text: "",
        tool_calls: [
          {
            id: "tc-pre-1",
            name: "pattern_history",
            arguments: {
              equipment: "MARRABEL_NX::B275-1",
              window_start: "2026-02-12 10:33",
              window_end: "2026-02-12 10:43",
            },
            status: "running",
          },
        ],
      },
    },
  },

  /* f031 — pattern_history result: the 15-second voltage transient. */
  {
    id: "f031",
    narration:
      "There it is. A 15-second voltage transient on the same busbar that later trips.",
    transition_ms: 1500,
    patch: {
      "chat.update_tool": {
        agent: "investigator",
        id: "tc-pre-1",
        status: "complete",
        duration_ms: 1500,
        result: JSON.stringify({
          columns: ["timestamp_aest", "TagId", "Value", "prev_val", "event"],
          data: [
            ["2026-02-12 10:38:30", "MARRABEL_NX::B275-1::volt_kv", 248.0, 275.5, "DIP -9.9%"],
            ["2026-02-12 10:38:45", "MARRABEL_NX::B275-1::volt_kv", 275.4, 248.0, "RECOVER +10.9%"],
          ],
          pattern: "transient_kv_dip",
          duration_s: 15,
          depth_pct: 9.9,
          alarm_raised: false,
          sub_threshold_reason: "sustained-low alarm requires >60s below 90% nominal",
          gridiq_advisory:
            "Insulation degradation pattern — recommend thermal scan of all bay equipment " +
            "connected to 275 kV Bus 275-1, prioritising bus section isolators (DS-275-11, DS-275-12, " +
            "DS-275-13, DS-275-14).",
        }),
      },
      /* Spotlight the bus on the topology pane — same severity tier as the
         situation card so the operator's eye locks onto where the transient
         landed before the punchline frame names DS-275-13. */
      "topology.overlay.set": {
        overlay: {
          equipmentIds: ["MARRABEL_NX::B275-1"],
          severity: "INVESTIGATE",
        },
      },
    },
  },

  /* f032 — Closing analysis: the punchline. DS-275-13 was on the recommended scan list. */
  {
    id: "f032",
    narration:
      "GridIQ flags the precursor 37 minutes before the event.",
    transition_ms: 200,
    patch: {
      "chat.append": {
        agent: "investigator",
        role: "assistant",
        agent_name: "Investigator",
        text:
          "At **10:38:30** — **37 minutes before the busbar trip** — the 275 kV Bus 275-1 voltage " +
          "at MARRABEL_NX dipped from 275.5 kV to 248.0 kV (9.9% depression) and recovered after " +
          "**15 seconds**. No SCADA alarm was raised because the duration was below the sustained-low " +
          "threshold (60 s).\n\n" +
          "GridIQ flagged the transient as INVESTIGATE-grade based on the dip depth and shape — " +
          "consistent with early-stage insulation breakdown on a connected primary plant element. " +
          "The recommendation issued at 10:39 was a thermal scan of all bay equipment on the 275 kV " +
          "Bus 275-1, prioritising bus section isolators (DS-275-11 through DS-275-14).\n\n" +
          "**DS-275-13 — the asset that flashed over at 11:15 — was on that recommended scan list.**\n\n" +
          "Had the precursor advisory been actioned, the trip and the 412 MW generation loss were preventable.",
      },
      /* Punchline overlay — promote the bus highlight to CRITICAL and add
         the four bus section isolators that were on the recommended scan
         list. DS-275-13 is the actual flashover asset. The map will pulse
         red on the bus row plus all four isolator rows so the visual lands
         the same instant the assistant message names them in bold. */
      "topology.overlay.set": {
        overlay: {
          equipmentIds: [
            "MARRABEL_NX::B275-1",
            "MARRABEL_NX::DS-275-11",
            "MARRABEL_NX::DS-275-12",
            "MARRABEL_NX::DS-275-13",
            "MARRABEL_NX::DS-275-14",
          ],
          severity: "CRITICAL",
        },
      },
    },
  },

  /* f033 — Closing wrap chapter. Without this trailing chapter the
     player ends mid-thought on f032's punchline; the presenter then
     has nothing to advance INTO when they press Next, and the Done
     button appears abruptly. This frame restates the value
     proposition in one line and gives the presenter a final beat to
     land before the playback bar dismisses. No patch — the UI stays
     exactly as f032 left it (red overlay on bus + isolators). */
  {
    id: "f033",
    chapter: "Wrap",
    narration:
      "The loop: detect, classify, investigate, dispatch. Where the data allows, warn beforehand.",
    transition_ms: 200,
    patch: {},
  },
];
