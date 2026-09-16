# MODERNIZATION.md — Kiosk Demo Alignment with Live GridIQ Surface

> **Status:** Spec only — not yet implemented.
> **Last updated:** 2026-05-26 (R9–R20 added — full capability showcase).
> **Targets:** `app/frontend/src/demo/scenarios/ngm_busbar_trip/` (Grid) + `app/frontend/src/demo/scenarios/atc_tcas_cascade/` (ATC).
> **Source-of-truth for live behaviour:** `/home/hanchoong/CURRENT270425/gridiq_current_070526/` — `control/agent_config.yaml`, `README.md`, `AUTODEV.md`.

---

## 0. Purpose

- Kiosk demos represent the ~2025-Q4 product (two-agent Investigator→Dispatcher delegation, thin tool surface, no audit, no auto-summary, no mandatory classify verdict).
- Live GridIQ moved on substantially in the 2026-05 sweep: single GridManager flow, mandatory in-turn `classify`, auto-summary fired on every `done`/`abort`, Session Auditor with rubric'd `submit_audit_report`, five Cosmos `graph_extras` tools, four Phase 1 compound investigation tools, situation streaming + cluster grouping, priority action decision lifecycle, detector tuning panel, Data Search Assistant with raw KQL/Gremlin, background dispatcher events, tool-argument streaming, oversized-envelope truncation banner, saved-session replay, frequency profile bespoke renderer, breaker-fail-signature bespoke renderer.
- Goal of this spec: rewrite both scenarios + extend the kiosk framework so every live surface and every live tool family is exercised at least once per playback.
- Non-goal: replicate live backend internals (LLM, KQL, Gremlin). Everything still ships as canned frames + pre-baked tool envelopes.
- **Capability matrix (every row must be visibly exercised in each scenario):**

| # | Capability | Live source | Showcased in spec |
|---|---|---|---|
| 1 | Streaming radar scan with `partial`→`enrich` patch-by-id | AUTODEV §0.8 (streaming detector) | R5 |
| 2 | Cluster grouping by `(station, severity)` | AUTODEV 2026-05-23 (`SituationClusterCard`) | R5 |
| 3 | Background NER 4.2.3 classifier prior on each card | README §15a, `kiosk_bootstrap.classifications` | existing |
| 4 | Topology graph + CRITICAL overlay | live `topology.set` op | existing |
| 5 | Single-agent GridManager turn (no delegation) | `control/agent_config.yaml` comment | R1 |
| 6 | `detect_situations` as agent-callable tool | live config | R6 / R10 |
| 7 | All eight watcher KQL tools | `tools/watcher/_watcher_tools.py` | R10 |
| 8 | Three Fabric V2 graph tools | `tools/fabric_graph/` | R10 |
| 9 | Five Cosmos `graph_extras` tools | `tools/watcher/_graph_extras/` | R10 |
| 10 | Four Phase 1 compound investigation tools | `reconstruct_event_timeline_causal`, `bus_zone_audit`, `breaker_fail_signature`, `frequency_disturbance_profile` | R10 + R11 |
| 11 | Tool-argument streaming (`tool_call_delta`) | live SSE contract | R9 |
| 12 | Oversized-envelope truncation banner | `MAX_SSE_FRAME_BYTES=65536` | R12 |
| 13 | Four search KB tools | `search_paws` / `search_nearhit_reports` / `search_smirks` / `search_investigation_clues` | R10 |
| 14 | Mandatory `classify` verdict + coloured banner | AUTODEV §15a | R2 |
| 15 | `push_action` ×N priority cards | `tools/panels/_push_action.py` | existing |
| 16 | Priority-action decision lifecycle (complete / decline / reopen + note) | README §12 | R7 |
| 17 | Auto-summary stream on `done` | README §15a | R3 |
| 18 | Session Audit panel — 6-row rubric + band + markdown | README §14 | R4 |
| 19 | Detector Tuning panel — rule edit + Apply | README §15 | R13 |
| 20 | Data Search Assistant — multi-turn dock agent with raw KQL + graph + KBs | `data_assistant` in live config | R14 |
| 21 | Saved Session Picker — re-hydrate a prior similar incident | README §10 | R15 |
| 22 | Background dispatcher events panel | live `background_token` / `background_tool_*` | R16 |
| 23 | Grid Status / Airspace Status dashboard with regional threat breakdown | live grid-status panel | R17 |
| 24 | Vocabulary switching (energy ↔ ATC) | live `vocabularyStore` | existing + R8 |
| 25 | Spotlight annotations on every surface | main-kiosk `ui.spotlight.*` | R8 |
| 26 | First-run coachmark on the scenario picker | main-kiosk AUTODEV `scenario-picker-hint` | R18 |
| 27 | Tool-result `ToolResultCard` scaffold + `ResultTable` primitive | live couturier audit | R19 |
| 28 | Replay / Step-through / Annotated-mode playback | main-kiosk player | R20 |

---

## 1. Framework changes (apply to both scenarios)

### R1 — Retire delegation as the cross-agent pattern

- **Current**: Both scenarios stage `Investigator` → `delegate_to_agent("dispatcher")` → Dispatcher pushes actions. `DelegationResult` renderer is used for the hand-off card. `bootstrap.ts` ships `investigator` + `dispatcher` as two separate main agents.
- **Required**:
  - Drop `delegate_to_agent` tool calls from `phases/04_investigate.ts` and `phases/05_delegate.ts` in both scenarios.
  - Collapse the two phases into a single GridManager turn. Investigation tool calls, `classify`, knowledge-base searches, and `push_action` calls all stream inside one assistant message in one chat thread.
  - `bootstrap.ts` ships a single main agent `grid_manager` (display name: `GridManager` for the energy scenario, `Incident Investigator` for ATC — vocabulary-driven). `investigator` and `dispatcher` are still seeded as hidden aliases so any saved-session replay path continues to resolve, mirroring live `control/agent_config.yaml`.
- **Files**:
  - `app/frontend/src/demo/scenarios/ngm_busbar_trip/bootstrap.ts`
  - `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/04_investigate.ts`
  - `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/05_delegate.ts` → renamed `05_actions.ts` (action-synthesis half of the single GM turn).
  - `app/frontend/src/demo/scenarios/atc_tcas_cascade/bootstrap.ts`
  - `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/04_investigate.ts`
  - `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/05_delegate.ts` → renamed `05_actions.ts`.

### Test: R1

- Playwright spec `e2e/single-agent-flow.spec.ts`:
  1. Load the kiosk URL, pick `ngm-busbar-trip`.
  2. Assert exactly one main agent tab visible (`grid_manager` / `Incident Investigator`).
  3. Assert no `delegate_to_agent` tool card renders anywhere in the chat scroll.
  4. Assert `push_action` cards land in the same chat thread as the investigation tool calls.

---

### R2 — Mandatory `classify` tool call surfaces inside the turn

- **Current**: Classifications are pre-seeded via `kiosk_bootstrap.classifications`. The badge appears as if it materialised on its own. No tool call event is shown.
- **Required**:
  - Inside the single GridManager turn, immediately before the final assistant text, emit a `tool_call_start` + `tool_call_end` for `classify` with arguments `{verdict, justification}` (live signature per `tools/panels/_classify.py`).
  - Tool result envelope: `{"panel":"classify_verdict","verdict":"credible_event"|"non_credible_event"|"non_event"|"indeterminate","justification":"...","pushed_at":"<iso>"}`.
  - Frontend reads the call and renders a coloured banner above the Operator Priorities panel (kiosk equivalent of the live `ClassifyVerdictCard`). Banner colours: `credible_event` → red, `non_credible_event` → amber, `non_event` → grey, `indeterminate` → blue.
  - `kiosk_bootstrap.classifications` is retained ONLY for the situation-card badge (the background NER 4.2.3 advisory prior). The in-turn `classify` call is the agent's own verdict and may agree or disagree with the prior.
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — extend `ToolCall.name` literal union (or leave as `string`) and document `classify` envelope shape in a JSDoc.
  - `app/frontend/src/demo/scenarios/*/phases/04_investigate.ts` — add two new frames near the end (pre-final-text) per scenario.
  - `app/frontend/src/components/chat/tool-renderers/index.ts` — register a `ClassifyVerdictResult` renderer (or extend `PanelToolSummary` to dispatch on `panel === "classify_verdict"`).
  - `app/frontend/src/components/panels/ClassifyVerdictBanner.tsx` — new component, mounted above `PriorityActionsPanel`. Reads `chatStore.lastClassifyVerdict` (new selector) and renders the banner.
  - `app/frontend/src/stores/chatStore.ts` — add `lastClassifyVerdict` selector that scans the active session's tool calls newest-first for `name === "classify"`.

### Test: R2

- Vitest unit `app/frontend/tests/chat/classifyVerdictBanner.test.tsx`:
  1. Mount the banner with a chat-store stub containing a `classify` tool call with `verdict: "non_credible_event"`.
  2. Assert banner background is amber and copy quotes the `justification` field.
- Playwright spec `e2e/classify-verdict-banner.spec.ts`:
  1. Run `ngm-busbar-trip`.
  2. After phase 4 completes, assert a `data-testid="classify-verdict-banner"` is visible with `data-verdict="non_credible_event"`.
  3. Assert a `tool_call_start` card with `data-tool="classify"` is visible in the chat scroll.

---

### R3 — Auto-summary fires on chat `done`

- **Current**: No summary stream after the GridManager turn finishes. SituationSummaryCard stays empty.
- **Required**:
  - After the final `chat.append_token` of the GridManager turn, append a synthetic `summary.append_token` patch sequence that streams `headline` + 3–4 `bullets` + 1–2 `open_questions` into the SituationSummaryCard.
  - Implement two new patch ops:
    - `summary.start` — clears the card, sets `loading: true`.
    - `summary.append` — appends one bullet/headline/open-question chunk; updates `summaryStore.current`.
    - `summary.done` — clears `loading`, marks `auto: true`.
  - SituationSummaryCard must render the streaming card as it would when the live `POST /api/summaries/{sid}/run/stream` fires.
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — add three new ops to `FramePatch` union.
  - `app/frontend/src/demo/applyPatch.ts` — wire the ops to `summaryStore`.
  - `app/frontend/src/stores/summaryStore.ts` — add `start()`, `append()`, `done()` actions (idempotent; tolerate replay).
  - Both scenarios' `phases/05_actions.ts` (or new `phases/06_summary.ts`) carry the new frames.

### Test: R3

- Vitest unit `app/frontend/tests/stores/summaryStore.test.ts`:
  1. Call `start()`, three `append()` calls, then `done()`.
  2. Assert final `current` has `auto === true`, three bullets, `loading === false`.
- Playwright spec `e2e/auto-summary-stream.spec.ts`:
  1. Run `atc-tcas-cascade`.
  2. After phase 4 ends, assert SituationSummaryCard visibly streams (text expanding frame-by-frame).
  3. Assert the card shows an `Auto` badge.

---

### R4 — Session Audit surface

- **Current**: No audit panel. No rubric. No band/score verdict. Live operators see a `Run audit` button next to the chat composer (per `README.md` §14).
- **Required**:
  - Add a `SessionAuditPanel` to the kiosk UI mounted on the right of the Operator Priorities column (toggleable tab).
  - New patch ops:
    - `audit.start` — sets `auditStore.running = true`, opens the panel.
    - `audit.tool_call` — appends one entry to `auditStore.toolTrail` (mirror live `tool_call_start`/`tool_call_end` shape).
    - `audit.report` — writes the terminal envelope.
    - `audit.done` — clears `running`.
  - Final `audit.report` envelope mirrors live `submit_audit_report`:
    ```ts
    {
      audit_id: string,
      headline: string,
      band: "excellent"|"strong"|"adequate"|"weak"|"poor",
      score_pct: number,           // 0..1
      weighted_score: number,      // 0..21
      duration_seconds: number,
      tool_call_count: number,
      rubric: {
        evidence_completeness: {score: 0|1|2|3, note: string},
        topology_coverage:    {score: 0|1|2|3, note: string},
        hypothesis_quality:   {score: 0|1|2|3, note: string},
        action_grounding:     {score: 0|1|2|3, note: string},
        summary_quality:      {score: 0|1|2|3, note: string},
        grounding:            {score: 0|3,     note: string}  // binary, weight 2
      },
      gaps: string[],
      improvements: string[],
      markdown: string             // full narrative
    }
    ```
  - Render: header strip with band pill + `score_pct` + `weighted_score / 21`; six rubric rows with one-line notes; collapsible markdown body; gaps + improvements lists.
  - The auditor's tool calls (`find_event_timeline`, `graph_corridor_endpoints`, `search_smirks`, etc.) stream as a compact `toolTrail` list in the panel — NOT as chat bubbles.
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — add four new ops.
  - `app/frontend/src/demo/applyPatch.ts` — wire to new store.
  - `app/frontend/src/stores/auditStore.ts` — new file.
  - `app/frontend/src/components/panels/SessionAuditPanel.tsx` — new component.
  - Both scenarios get a new `phases/07_audit.ts` (NGM was previously `07_precursor.ts` — renumber to `08_precursor.ts`).
  - `app/frontend/src/foundation/vocabulary/index.ts` (or wherever `DomainVocabulary` lives) — add `auditPanelLabel`, `auditAuthority` keys with energy defaults + ATC overrides.

### Test: R4

- Vitest unit `app/frontend/tests/stores/auditStore.test.ts`:
  1. Apply `audit.start`, three `audit.tool_call`, one `audit.report` (band: `strong`, score_pct: 0.71), one `audit.done`.
  2. Assert store ends in `{running: false, report: {band:"strong", score_pct:0.71, ...}}` and `toolTrail.length === 3`.
- Playwright spec `e2e/session-audit-panel.spec.ts`:
  1. Run `ngm-busbar-trip` to completion.
  2. Click the Audit tab.
  3. Assert band pill reads `strong` (or scenario-specific value) and exactly six rubric rows render.
  4. Assert `toolTrail` has ≥ 4 entries.
  5. Expand the markdown body, assert ≥ 200 chars present.

---

### R5 — Situation streaming + cluster grouping

- **Current**: `panel.situations.set` injects all five situation cards at once. Each card is a single row.
- **Required**:
  - Replace `panel.situations.set` with a streaming sequence:
    - `panel.situations.scan_start` (existing).
    - `panel.situations.partial` — appends one provisional card (skeleton fields, no `affected_equipment`).
    - `panel.situations.enrich` — patches an existing card by `situation_id` with `affected_equipment`, `pattern_details`, `step_changes`. Tolerates missing-id (warns, no-op).
    - `panel.situations.done` — closes the spinner; merges any final aggregates.
  - Cluster grouping: where two or more situations share `(station, severity)`, the feed groups them under a single `SituationClusterCard` with chevron-expand for the per-window children. Cluster-of-1 stays default-expanded (mirrors live `groupIntoClusters` 2026-05-23).
  - `panel.situations.classify` (existing) operates on individual `situation_id`s — cluster card aggregates the badges of its children for the collapsed view.
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — replace single `set` op with three.
  - `app/frontend/src/demo/applyPatch.ts` — wire `partial`/`enrich`/`done`.
  - `app/frontend/src/stores/situationStore.ts` — add `partial()`, `enrich()`, `done()` actions; expose a `clusters` selector grouping by `(station, severity)`.
  - `app/frontend/src/components/panels/SituationClusterCard.tsx` — new (mirror live module of same name).
  - `app/frontend/src/components/panels/SituationAlertsPanel.tsx` — switch the flat-view feed to render clusters by default; keep the by-station accordion as the alternate tab.
  - Both scenarios' `phases/01_scan.ts` rewritten to stream 5 partials → 5 enrichments → done.

### Test: R5

- Vitest unit `app/frontend/tests/stores/situationStore.cluster.test.ts`:
  1. Insert three situations: `(REDCLIFF_PS, CRITICAL)`, `(REDCLIFF_PS, CRITICAL)`, `(NORTHVALE_SS, MAJOR)`.
  2. Assert `clusters` selector returns 2 clusters; the first has 2 children, the second has 1.
- Playwright spec `e2e/situation-streaming.spec.ts`:
  1. Run `ngm-busbar-trip`.
  2. Watch for `panel.situations.partial` patches — assert at least one card with `data-situation-state="partial"` is visible mid-scan.
  3. Wait for `done` — assert all cards transition to `data-situation-state="enriched"`.
  4. Assert any `(station, severity)` duplicates render under a single `SituationClusterCard`.

---

### R6 — Tool surface expansion (per live `control/agent_config.yaml`)

- **Current**: Demos invoke `find_station_summary`, `find_event_timeline`, `find_scada_changes`, `search_investigation_clues`, `search_participants`, `graph_bus_topology` (Grid) and `find_alerts`, `find_surveillance` ×2, `find_traffic`, `search_procedures` (ATC). `find_station_summary` and `search_participants` do not exist in the live config.
- **Required**:
  - Rename `find_station_summary` → `find_station_assets` everywhere (Grid scenario + dock replies + `TOOL_PROMINENT_COLUMNS` hints).
  - Replace `search_participants` with `search_smirks` (current AEMO OERs / Direction Reports) — provide a corresponding result envelope citing fictional SMIRKS report IDs (`SMIRKS-2025-Q4-014` style) for the Grid scenario. For ATC, replace with an ICAO/ANSP equivalent: `search_safety_recs` returning fictional state-safety-program advisories.
  - Add at least one compound graph extra and one compound investigation tool to each scenario's GridManager turn:
    - Grid: `graph_corridor_endpoints` (lists endpoint substations + bay paths for the affected line) + `reconstruct_event_timeline_causal` (causal event timeline; live tool added 2026-05-18). For ATC, the analogue is `surveillance_corridor_trace` (corridor of fused tracks affected) + `reconstruct_alert_cascade_causal`.
  - Add `detect_situations` as an agent-callable tool call within the GridManager turn — confirms the radar finding was retained in-thread.
  - All envelopes adopt `{columns, rows}` shape (live README §6 contract). Demo currently mixes `{columns, data}` and `{columns, rows}` — pick `rows` everywhere. The `TabularResult` renderer accepts both today; we still standardise on `rows`.
- **Files**:
  - `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/04_investigate.ts` — full tool-list rewrite (see §2 below).
  - `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/04_investigate.ts` — full tool-list rewrite (see §3 below).
  - `app/frontend/src/demo/scenarios/*/bootstrap.ts` — dock replies updated to mention the new tool names.
  - `app/frontend/src/components/chat/tool-renderers/index.ts` — confirm `TOOL_PROMINENT_COLUMNS` entries for the new compound tools; add bespoke renderer for `reconstruct_event_timeline_causal` mirroring the live `CausalEventTimelineResult`.

### Test: R6

- Vitest registry-coverage `app/frontend/tests/chat/toolResultCard.coverage.test.ts`:
  1. Iterate every tool name referenced from any `phases/*.ts`.
  2. Assert every name resolves to a registered renderer OR appears in `JSON_FALLBACK_ALLOWLIST` (forbidden for tabular tools).
- Playwright spec `e2e/tool-coverage.spec.ts`:
  1. Run `ngm-busbar-trip`.
  2. Grep DOM for `data-tool="<name>"` cards. Assert at least: `find_station_assets`, `find_event_timeline`, `find_scada_changes`, `graph_corridor_endpoints`, `reconstruct_event_timeline_causal`, `search_investigation_clues`, `search_smirks`, `detect_situations`, `search_paws`, `search_nearhit_reports`, `push_action` (×N), `classify`.

---

### R7 — Priority action decision lifecycle

- **Current**: `panel.priority_action.append` only adds the card. There is no Complete / Decline / Reopen affordance and no decision trail.
- **Required**:
  - New op `panel.priority_action.decide`: `{action_id, decision: "complete"|"declined"|"reopened", note?: string, decided_at: string}`.
  - Each priority-action card renders Complete + Decline buttons. Both open the optional note form. Submitting writes a `decisions[action_id]` entry on `panelStore` and an append-only `timeline` row. Completed / declined cards collapse with an expand-to-review affordance.
  - Demo frames in `phases/06_actions.ts` (or wherever the scenario chooses to dramatise it) script ONE Complete + ONE Decline so the audience sees the closed-loop behaviour.
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — new op.
  - `app/frontend/src/demo/applyPatch.ts` — wire to `panelStore`.
  - `app/frontend/src/stores/panelStore.ts` — add `decide()` action + `decisions` + `timeline` state.
  - `app/frontend/src/components/panels/PriorityActionCard.tsx` — buttons + collapse logic.

### Test: R7

- Vitest unit `app/frontend/tests/stores/panelStore.decisions.test.ts`:
  1. Append two actions; decide one `complete` with a note, one `declined`.
  2. Assert collapsed render, decision timeline length 2, note preserved on the completed entry.
- Playwright spec `e2e/priority-action-decisions.spec.ts`:
  1. Run `ngm-busbar-trip` through phase 6.
  2. Assert one action card shows `data-decision="complete"` and one shows `data-decision="declined"`.
  3. Click the reopen affordance on the declined card; assert it returns to `pending`.

---

### R8 — Spotlight + annotation pass over every new surface

- **Current**: `ui.spotlight.set` exists in the main-kiosk framework but the global-kiosks Grid scenario does not exercise it. ATC uses `annotation` on individual frames.
- **Required**:
  - Every new surface (classify banner, audit panel, summary streaming, priority-action decision UI, cluster card, detector tuning panel, data search dock, grid status dashboard, background dispatcher panel, saved session picker) gets at least one frame with an `annotation` highlighting its first appearance + a one-line caption that opens with the business framing then names the technical surface (per ATC narration style guide §0).
  - Captions for the energy scenario adopt the live operator vernacular; ATC captions adopt the ICAO vernacular. Vocabulary store gates language.
- **Files**:
  - Both scenarios' phase files for the new frames.
  - `app/frontend/src/foundation/vocabulary/atc.ts` (or wherever ATC overrides live) — add captions where they differ.

### Test: R8

- Playwright spec `e2e/spotlight-coverage.spec.ts`:
  1. Run each scenario in `--annotations` mode.
  2. Assert every new surface (`data-spotlight-id="classify-verdict-banner"`, `"audit-panel"`, `"summary-card"`, `"priority-decision-buttons"`, `"situation-cluster-card"`, `"detector-tuning-panel"`, `"data-search-dock"`, `"grid-status-dashboard"`, `"background-dispatcher-panel"`, `"saved-session-picker"`) is annotated at least once during playback.

---

### R9 — Tool-argument streaming (`tool_call_delta`)

- **Current**: Tool calls appear instantly with full `arguments` object set. The live SSE contract streams arguments as partial JSON chunks via `tool_call_delta` between `tool_call_start` and `tool_call_end` (AUTODEV — SSE event contract).
- **Required**:
  - New patch op `chat.append_tool_delta`: `{tool_call_id, delta: string}` — appends a JSON fragment to the live `arguments_buffer` of the open tool call. Frontend renders a typewriter effect on the argument JSON within the collapsed tool card header.
  - At least two tool calls per scenario (the long-string ones — `search_*` queries and `reconstruct_event_timeline_causal` arguments) stream their `arguments` over 4–6 delta frames before the `tool_call_end` lands.
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — new op + `ToolCall.arguments_buffer?: string` field.
  - `app/frontend/src/demo/applyPatch.ts` — append delta to current tool call's buffer.
  - `app/frontend/src/components/chat/ToolCallDisplay.tsx` — show buffer when status === "running".
  - Both scenarios — phase 4 long-argument tool calls broken into delta frames.

### Test: R9

- Vitest unit `app/frontend/tests/chat/toolDelta.test.ts`:
  1. Append a tool call with empty arguments_buffer, then five delta frames.
  2. Assert buffer concatenates correctly in order; final parsed JSON matches expected shape.
- Playwright spec `e2e/tool-arg-streaming.spec.ts`:
  1. Run `ngm-busbar-trip`.
  2. Pause player after `tool_call_start` for `search_investigation_clues` (or hook via `data-tool-state="streaming-args"`).
  3. Assert visible arguments grow chunk-by-chunk for at least 200 ms before `tool_call_end`.

---

### R10 — Full live tool family coverage per scenario

- **Current**: ≤ 8 tool calls per scenario. Misses every `graph_extras`, every Phase 1 compound investigation tool, and `search_smirks`.
- **Required**:
  - Every scenario's GridManager turn invokes at minimum:
    - All eight watcher KQL tools: `find_station_assets`, `find_event_timeline`, `find_scada_changes`, `find_asset`, `find_alarms`, `find_scada`, `find_alarm_by_mrid`, `detect_situations`.
    - Two Fabric V2 graph tools: `graph_bus_topology`, `graph_equipment_connections`.
    - All five Cosmos graph_extras: `graph_bus_boundary`, `graph_corridor_endpoints`, `graph_breaker_neighbourhood`, `graph_common_mode_devices`, `graph_switch_state_snapshot`.
    - All four Phase 1 compound tools: `reconstruct_event_timeline_causal`, `bus_zone_audit`, `breaker_fail_signature`, `frequency_disturbance_profile`.
    - All four search KBs: `search_investigation_clues`, `search_smirks`, `search_paws`, `search_nearhit_reports`.
    - `push_action` ×5.
    - `classify` ×1.
  - For ATC, the tool names are skinned but the count and family coverage are identical (see §3.3 below for the rename table).
  - Total tool calls per scenario ≈ 24. Stretch the playback by stripping each tool's render to ~1.5 s so the whole sequence still fits ~60 s of chat time.
- **Files**:
  - Both `phases/04_*.ts` files — full rewrite.
  - `app/frontend/src/components/chat/tool-renderers/index.ts` — confirm every tool name has a registered renderer; add bespoke ones for the four compound tools (see R11).

### Test: R10

- Vitest registry-coverage `app/frontend/tests/chat/toolFamilyCoverage.test.ts`:
  1. Import scenario; flatten frames; collect every tool name fired.
  2. Assert each of the 24 names in the required list above appears at least once.
- Playwright spec `e2e/tool-family-coverage.spec.ts`:
  1. Run each scenario to completion.
  2. Grep DOM for `data-tool="<name>"`; assert all 24 distinct names present.

---

### R11 — Bespoke renderers for the four Phase 1 compound tools

- **Current**: Live ships bespoke renderers (`CausalEventTimelineResult`, `BusZoneAuditResult`, `BreakerFailSignatureResult`, `FrequencyDisturbanceProfileResult`) per couturier audit 2026-05-18. Kiosk has none.
- **Required**:
  - `CausalEventTimelineResult` — three columns: `t (relative seconds)`, `actor`, `causal note`. Stacked vertical rail with branch markers where the causal chain forks (sympathetic trips). Note bubble per row.
  - `BusZoneAuditResult` — bus-section grid showing each connected element, its modelled `NormalOpen` / `CurrentOpen` state, whether an OPEN alarm fired, and the `adjacency_gap` flag if a zone element fired no OPEN alarm.
  - `BreakerFailSignatureResult` — per-CB scorecard: `cbf_score 0..1`, `reasoning` chip strip, `modelled_open`, `OPEN alarm latency ms`.
  - `FrequencyDisturbanceProfileResult` — sparkline of frequency over the window; chips for `nadir_hz`, `time_below_SOFEB_s`, `time_below_SOFB_s`, `recovery_seconds`, `GFS_met` boolean.
  - All four consume the shared `<ToolResultCard>` scaffold (R19) and the shared `<ResultTable>` primitive where tabular.
- **Files**:
  - `app/frontend/src/components/chat/tool-renderers/CausalEventTimelineResult.tsx` (new).
  - `app/frontend/src/components/chat/tool-renderers/BusZoneAuditResult.tsx` (new).
  - `app/frontend/src/components/chat/tool-renderers/BreakerFailSignatureResult.tsx` (new).
  - `app/frontend/src/components/chat/tool-renderers/FrequencyDisturbanceProfileResult.tsx` (new).
  - `app/frontend/src/components/chat/tool-renderers/index.ts` — wire all four into `TOOL_RENDERERS`.

### Test: R11

- Vitest snapshot `app/frontend/tests/chat/compoundRenderers.test.tsx`:
  1. Mount each renderer with a representative envelope.
  2. Snapshot-assert layout; assert `data-tool-card` root attribute present (R19 compliance).

---

### R12 — Oversized-envelope truncation banner

- **Current**: No demonstration of the live `MAX_SSE_FRAME_BYTES=65536` rewrite-to-preview behaviour.
- **Required**:
  - One scenario (the Grid scenario, on the `graph_switch_state_snapshot` call — typically the chunkiest envelope) ships a truncated tool result: `{"truncated":true,"preview":"<≤4 KiB prefix>","original_event":"tool_result","original_bytes":421837}`.
  - `ToolResultCard` renders a yellow banner: "Result truncated — 421 KiB. Showing first 4 KiB." with a chip linking to a synthetic "Download full envelope" affordance (no-op in kiosk).
- **Files**:
  - `app/frontend/src/components/chat/tool-renderers/ToolResultCard.tsx` — banner branch when `parsed.truncated === true`.
  - Grid scenario `phases/04_gridmanager.ts` — one tool call uses a truncated envelope.

### Test: R12

- Playwright spec `e2e/truncation-banner.spec.ts`:
  1. Run `ngm-busbar-trip`.
  2. Locate the `graph_switch_state_snapshot` card.
  3. Assert `data-truncated="true"` on the card and the yellow banner copy is visible.

---

### R13 — Detector Tuning panel — live rule edit + Apply

- **Current**: No detector-tuning surface in the kiosk.
- **Required**:
  - New centre-column tab `Detector Tuning` (kiosk equivalent of live `SituationControlBar` + tuning UI).
  - New patch ops:
    - `panel.detector.show` — opens the tab + highlights it via spotlight.
    - `panel.detector.edit_rule` — `{rule_id, field, value}` — animates a typed value into a rule input.
    - `panel.detector.apply` — flips the `Apply settings` button to a busy state then green-tick; triggers a synthetic re-scan that streams a SIXTH situation card (one that wouldn't have surfaced under default rules).
  - Panel UI: three sections — `Window` (window_minutes, input_row_cap, max_hours), `Alarm signals` (severity threshold + named rule chips), `SCADA conditions` (drop-below-threshold, percent-change, near-zero — visible as plain-English rule rows).
  - The demo shows tightening the SCADA "drop below threshold" rule on `KV` so that the sub-threshold transient at 13:55:30 (Grid) / 08:17:30 (ATC) bumps from `INVESTIGATE` to `MAJOR` severity.
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — three new ops.
  - `app/frontend/src/demo/applyPatch.ts` — wire to new store.
  - `app/frontend/src/stores/detectorTuningStore.ts` (new).
  - `app/frontend/src/components/panels/DetectorTuningPanel.tsx` (new).
  - Both scenarios — new `phases/09_tuning.ts` after the audit phase.

### Test: R13

- Vitest unit `app/frontend/tests/stores/detectorTuningStore.test.ts`:
  1. Apply edit_rule + apply ops.
  2. Assert config snapshot updated and `lastAppliedAt` set.
- Playwright spec `e2e/detector-tuning.spec.ts`:
  1. Run `ngm-busbar-trip` through phase 9.
  2. Assert `data-rule="scada.kv_drop_below_threshold"` value changes from `90` to `94`.
  3. Click Apply; assert the green-tick appears and a sixth situation card streams in.

---

### R14 — Data Search Assistant dock agent — multi-turn

- **Current**: Dock agent in both scenarios is a single keyword-match reply engine — one question, one canned answer. Live `data_assistant` is a multi-turn tool-using agent with raw KQL, raw Gremlin, and all four search KBs.
- **Required**:
  - Promote the dock agent from "canned reply machine" to "scripted multi-turn agent" that walks through three operator follow-ups:
    1. "Show MARRABEL alarms around 11:15." → calls `find_alarms` → renders `TabularResult`.
    2. "Run a raw KQL — give me every BKR transition in the last 30 minutes for the four units." → calls `query_kql` → renders `TabularResult` with the raw KQL fragment in `query_text` chip.
    3. "Walk the Gremlin from CB-031 two hops." → calls `query_gremlin` → renders `GraphResult` array.
  - The dock conversation is scripted via the same `chat.append` / `chat.append_token` / `chat.update_tool` ops, but routed to the dock agent thread (`agent.set_active` for the dock).
  - The dock agent gets its own `agent.set_active` toggle frame so the audience watches the centre column switch to it briefly before bouncing back.
- **Files**:
  - Both scenarios' `bootstrap.ts` — dock agent gains `tools: ["find_alarms","query_kql","query_gremlin","search_paws"]` for documentation (kiosk doesn't validate).
  - Both scenarios — new `phases/10_data_search.ts` (after detector tuning).

### Test: R14

- Playwright spec `e2e/data-search-dock.spec.ts`:
  1. Run scenario through phase 10.
  2. Assert centre column shows the Data Search dock with at least three assistant messages.
  3. Assert at least one `query_kql` and one `query_gremlin` tool card render under the dock.

---

### R15 — Saved Session Picker — replay a prior similar incident

- **Current**: No saved-session affordance. Live UI surfaces a header `SavedSessionPicker` that re-hydrates a previous session into the chat + panels (README §10).
- **Required**:
  - New header dropdown `Saved Sessions` containing at least two synthetic entries per scenario:
    - Grid: `GLENRIDGE_NX 2022-10-08 — bus 275-1 trip`, `BIRRALEE_NX 2021-05-04 — bus zone trip`.
    - ATC: `METROFIELD_APP 2025-11-12 — fusion ghost (resolved)`, `RIDGEMONT_APP 2024-07-22 — STCA chatter (false alerts)`.
  - Selecting an entry triggers a `session.hydrate` patch that swaps in a pre-baked chat thread + summary + audit + priority actions for that prior session. The whole UI re-renders without re-running playback.
  - New patch ops:
    - `session.hydrate` — `{session_id, payload}` where payload contains thread + summary + audit + priority_action_state.
    - `session.clear` — back to current scenario.
  - When a saved session is active, a banner reads "Replay mode — read-only". Decision affordances on priority cards disable in replay.
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — new ops.
  - `app/frontend/src/components/header/SavedSessionPicker.tsx` (new).
  - `app/frontend/src/stores/sessionStore.ts` — add `replayMode: boolean`.
  - Both scenarios — `bootstrap.ts` carries a `saved_sessions: SavedSession[]` block with the two pre-baked replays each.

### Test: R15

- Playwright spec `e2e/saved-session-picker.spec.ts`:
  1. Open the kiosk.
  2. Click Saved Sessions; select `GLENRIDGE_NX 2022-10-08`.
  3. Assert chat thread re-renders with 2022 content and replay banner visible.
  4. Assert priority-action Complete buttons are disabled.

---

### R16 — Background dispatcher panel

- **Current**: No background event surface. Live runs a long-lived `dispatcher` agent that publishes `background_token` + `background_tool_*` events into `BackgroundEventBroker` (README §9).
- **Required**:
  - New collapsible left-column panel `Background Watcher` showing a rolling feed of `background_token` text + `background_tool_start/end/result` chips for a long-running synthetic task ("re-checking nearby substations every 60 s").
  - New patch ops:
    - `background.token` — append text chunk to current background message.
    - `background.tool_start` / `background.tool_end` / `background.tool_result` — mirror live event shape.
    - `background.done` — mark message complete.
  - The background feed fires opportunistically across the scenario — at least one full background loop completes during the audit phase.
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — four new ops.
  - `app/frontend/src/stores/backgroundStore.ts` (new).
  - `app/frontend/src/components/panels/BackgroundDispatcherPanel.tsx` (new).
  - Both scenarios — frames interleaved across phases 4 / 6 / 7.

### Test: R16

- Playwright spec `e2e/background-dispatcher.spec.ts`:
  1. Run `atc-tcas-cascade`.
  2. Assert `BackgroundDispatcherPanel` shows at least three chips and one `background.done` event during playback.

---

### R17 — Grid Status / Airspace Status dashboard

- **Current**: Kiosk has no domain-status dashboard. Live ships a NEM Grid Status panel with regional threat breakdown.
- **Required**:
  - New centre-column tab `System Status` (vocabulary key `systemStatusLabel`).
  - Renders five regions, current load vs capacity, threat severity per region (CRITICAL/MAJOR/SERIOUS/INVESTIGATE/CLEAR), frequency sparkline (or traffic sparkline for ATC).
  - New patch op `panel.system_status.set` — `{regions: RegionStatus[], frequency_series: number[]}`.
  - The dashboard updates twice across a scenario: once at scan start, once after the audit lands (the affected region's severity drops back to CLEAR).
- **Files**:
  - `app/frontend/src/demo/scenarioSchema.ts` — new op.
  - `app/frontend/src/stores/systemStatusStore.ts` (new).
  - `app/frontend/src/components/panels/SystemStatusDashboard.tsx` (new).
  - Both scenarios — frames at scan-start and post-audit.

### Test: R17

- Playwright spec `e2e/system-status-dashboard.spec.ts`:
  1. Run `ngm-busbar-trip`.
  2. Assert SER region severity badge transitions from CLEAR → CRITICAL → CLEAR over playback.

---

### R18 — First-run coachmark on the picker

- **Current**: Global-kiosks repo lacks the main-kiosk picker coachmark (`scenario-picker-hint`).
- **Required**:
  - Port the picker-hint behaviour: on first page load, render a coachmark ring + tooltip "Choose a scenario to trigger." pointing at `data-testid="scenario-picker"`. Coachmark dismisses on first picker click and stays dismissed (localStorage).
- **Files**:
  - `app/frontend/src/components/demo/PlayDemoButton.tsx` — coachmark logic.
  - `app/frontend/src/stores/coachmarkStore.ts` (new).

### Test: R18

- Playwright spec `e2e/first-run-coachmark.spec.ts`:
  1. Clear localStorage; open the kiosk.
  2. Assert `data-coachmark="scenario-picker-hint"` is visible.
  3. Click the picker; assert coachmark dismisses.
  4. Reload; assert coachmark stays dismissed.

---

### R19 — `<ToolResultCard>` scaffold + `<ResultTable>` primitive

- **Current**: Each renderer hand-rolls its own card chrome and table.
- **Required**:
  - Adopt the live couturier-audit invariants: every tool-result renderer wraps its body in `<ToolResultCard>` exposing slots `scope` (identifier chips), `signal` (summary chips), `note` (banner), children (body), `error` (red-banner short-circuit). Root attribute `data-tool-card` mandatory.
  - All tabular renderers consume the shared `<ResultTable>` primitive with `previewRows` cap (default 5) + `prominentColumns` hint per tool, declared in `TOOL_PROMINENT_COLUMNS`.
  - `extractError(parsed)` helper short-circuits to a red banner for `{error: true, detail}` / `{error: "msg"}` / `{status: "error", detail}`.
  - `JSON_FALLBACK_ALLOWLIST` shrinks to `{graph_property_keys, present_options}`.
- **Files**:
  - `app/frontend/src/components/chat/tool-renderers/ToolResultCard.tsx` (new).
  - `app/frontend/src/components/chat/tool-renderers/ResultTable.tsx` (new).
  - `app/frontend/src/components/chat/tool-renderers/helpers.ts` (new — `formatCell`, `extractError`).
  - `app/frontend/src/components/chat/tool-renderers/index.ts` — add `TOOL_PROMINENT_COLUMNS` + `JSON_FALLBACK_ALLOWLIST`.
  - Every existing renderer — refactor to consume the scaffold.

### Test: R19

- Vitest unit `app/frontend/tests/chat/toolResultCard.scaffold.test.tsx`:
  1. Iterate over `TOOL_RENDERERS`.
  2. Mount each with a sample envelope.
  3. Assert every rendered DOM has `[data-tool-card]` at the root.
  4. Mount with an error envelope; assert red banner.

---

### R20 — Player modes: Replay / Step / Annotated

- **Current**: Global-kiosks player has neither step-through nor annotated mode.
- **Required**:
  - Player gains three modes: `auto` (default), `step` (advance frame-by-frame on Space), `annotated` (auto + spotlight captions visible). Keyboard shortcuts: `Space` (step / pause), `A` (toggle annotations), `R` (restart). Toolbar with mode toggles + frame counter `n / total`.
  - In `step` mode every `chapter` frame auto-pauses; presenter advances manually.
  - In `annotated` mode the spotlight ring + caption are always visible; in `auto` they only appear for frames carrying an `annotation` block.
- **Files**:
  - `app/frontend/src/demo/framePlayer.ts` — mode handling.
  - `app/frontend/src/demo/demoPlayerStore.ts` — `mode: "auto"|"step"|"annotated"`.
  - `app/frontend/src/components/demo/PlayerToolbar.tsx` (new).

### Test: R20

- Playwright spec `e2e/player-modes.spec.ts`:
  1. Run scenario in `step` mode.
  2. Advance with Space; assert frame counter increments.
  3. Toggle annotations with `A`; assert spotlight ring visible.
  4. Press `R`; assert playback restarts.

---

## 2. Grid (NGM Busbar Trip) — modernized scenario spec

### 2.1 Narrative invariants

- Anonymisation map unchanged (NGM / NGA / EHR / GFS / SOFB / FRS).
- Two value wins unchanged: (1) correct busbar classification in seconds, (2) precursor detection 37 min ahead.
- All real-station-derived strings stay out — fictional MARRABEL_NX centred topology stays.

### 2.2 Phase layout (modernized)

| Phase | File | Frames | Surface exercised |
|---|---|---|---|
| 1 — Streamed scan | `phases/01_scan.ts` | f000a–f000g | `panel.situations.scan_start`, 5× `partial`, 5× `enrich`, `done`. Cluster card for `(REDCLIFF_PS / MARRABEL_NX, CRITICAL)` if scenario ships two critical rows. |
| 2 — Classify (background NER prior) | `phases/02_classify.ts` | f000h–f000i | `panel.situations.classify` ×5. Badges seeded by `kiosk_bootstrap.classifications`. |
| 3 — Topology + Grid Status | `phases/03_topology.ts` | f000j–f000l | `topology.set` + `topology.overlay.set` with 275 kV Bus 275-1 highlighted CRITICAL; first `panel.system_status.set` showing SER region CRITICAL. |
| 4 — GridManager turn (investigate + verdict + actions, one thread) | `phases/04_gridmanager.ts` | f001–f060 | All 24 tool calls per §2.3, including delta-streamed args (R9) and one truncated envelope (R12). Background dispatcher events (R16) interleave. |
| 5 — Auto-summary stream | `phases/05_summary.ts` | f061–f065 | `summary.start` → 5× `summary.append` → `summary.done`. |
| 6 — Priority-action decisions | `phases/06_decisions.ts` | f066–f072 | Complete (A1) + Decline (A3) + Reopen (A3) + Complete-with-note (A5). |
| 7 — Session Audit | `phases/07_audit.ts` | f073–f092 | `audit.start` → 12× `audit.tool_call` → `audit.report` (`band: strong`, `score_pct: 0.7619`, `weighted_score: 16`) → `audit.done`; second `panel.system_status.set` showing SER region CLEAR. |
| 8 — Precursor reveal + classify diff | `phases/08_precursor.ts` | f093–f100 | Investigator re-fires `find_scada_changes` over 13:55 window, surfaces 15 s KV transient, classifies as `non_event` advisory. Banner colour updates accordingly. |
| 9 — Detector Tuning | `phases/09_tuning.ts` | f101–f110 | Operator tightens SCADA `KV` drop-below-threshold from 90 → 94; Apply re-runs detector; sixth situation card streams in. |
| 10 — Data Search Assistant | `phases/10_data_search.ts` | f111–f125 | Three-turn dock conversation hitting `find_alarms`, `query_kql`, `query_gremlin`. |

Total ~125 frames, ~210 s runtime (up from 33/95 s).

### 2.3 GridManager turn — full tool sequence (phase 4)

Every tool family in the live `control/agent_config.yaml` GridManager surface is exercised. 24 distinct tool calls + 5 `push_action` + 1 `classify`.

| # | Tool | Renderer | Why it's here |
|---|---|---|---|
| 1 | `detect_situations` | bespoke (`SituationDetectorResult`) | Agent-callable confirmation of the radar feed; `from_chat:true` marker de-duplicates against panel. |
| 2 | `find_station_assets` | `TabularResult` via `<ResultTable>` | High-level MARRABEL_NX inventory. Args stream via R9 deltas. |
| 3 | `find_asset` | `TabularResult` | Drill into `DS-275-13` itself — type, voltage, commissioning year. |
| 4 | `find_event_timeline` | `TabularResult` | Unified alarm + SCADA timeline 11:13 → 11:28 AEST. |
| 5 | `find_alarms` | `TabularResult` | Raw 6-alarm burst at 11:15:14. |
| 6 | `find_alarm_by_mrid` | `TabularResult` | Resolves `mrid-mb-bus-01` → alarm body for citation. |
| 7 | `find_scada` | `TabularResult` | Pre-event SCADA snapshot for the four units. |
| 8 | `find_scada_changes` | `TabularResult` | Significant-change subset — 412 MW lost + 89 % interconnector loading. |
| 9 | `reconstruct_event_timeline_causal` | `CausalEventTimelineResult` (R11) | Causal chain: DS-275-13 flashover → Scheme A → CB-031/041 → unit trips. Args delta-streamed. |
| 10 | `bus_zone_audit` | `BusZoneAuditResult` (R11) | Per-element OPEN-alarm coverage for Bus 275-1; flags adjacency gaps. |
| 11 | `breaker_fail_signature` | `BreakerFailSignatureResult` (R11) | CBF scoring across the bay; rules out CBF as the trigger cause. |
| 12 | `frequency_disturbance_profile` | `FrequencyDisturbanceProfileResult` (R11) | Nadir 49.71 Hz, GFS_met: true, recovery 100 s. |
| 13 | `graph_station_equipment` | `GraphResult` | Equipment list with CIM classes. |
| 14 | `graph_equipment_connections` | `GraphResult` | Connections from CB-031 outward. |
| 15 | `graph_bus_topology` | `GraphEnvelopeResult` | Bus 275-1 vs Bus 275-2 unit assignment. |
| 16 | `graph_bus_boundary` | `GraphEnvelopeResult` | Bus 275-1 boundary set (CBs + DSs). |
| 17 | `graph_corridor_endpoints` | `GraphEnvelopeResult` | MARRABEL→KETTERING No. 1 line corridor endpoints. |
| 18 | `graph_breaker_neighbourhood` | `GraphEnvelopeResult` | CB-031 sympathetic-trip neighbourhood. |
| 19 | `graph_common_mode_devices` | `GraphEnvelopeResult` | Bus-section isolator family flagged as suspect failure class. |
| 20 | `graph_switch_state_snapshot` | `GraphEnvelopeResult` (TRUNCATED, R12) | Modelled vs current switch state across the station — envelope > 64 KiB, ships truncated. |
| 21 | `search_investigation_clues` | `SearchResultCards` | GLENRIDGE_NX 2022 (0.94 similarity). Args delta-streamed. |
| 22 | `search_smirks` | `SearchResultCards` | Recent SMIRKS reports on isolator silver-plating wear. |
| 23 | `search_paws` | `SearchResultCards` | OP-NET-5520, OP-NET-3120, OP-NET-4410, OP-NET-2210. |
| 24 | `search_nearhit_reports` | `SearchResultCards` | Bus-zone trip lessons (BIRRALEE_NX 2021). |
| 25–29 | `push_action` ×5 | `PanelToolSummary` | A1 busbar restoration, A2 unit resync prep, A3 market notice, A4 isolator replacement, A5 precursor thermal-scan ticket. Each `reasoning` cites a source id. |
| 30 | `classify` | `ClassifyVerdictResult` (R2) | Verdict `non_credible_event`, justification quoting Operating Code §4.3.1A(c). Banner amber. |
| 31 | Final streamed assistant text | — | 4–5 paragraphs framing verdict + precursor link + action set. |

### 2.4 Bootstrap changes (Grid)

- `main_agents`: single `grid_manager` (display name `GridManager`). Hidden seeds `investigator` + `dispatcher` aliasing the same thread (so the saved-session migration story is intact).
- `dock_agents`: keep `data_search`. Dock replies updated to reference the new tool names (`find_station_assets`, `search_smirks`).
- `vocabulary`: ensure `auditPanelLabel: "Investigation Audit"`, `auditAuthority: "Internal review — Grid Operating Rules §5.2.3A"`, `classifyVerdictLabel: "Classification Verdict"`.
- `classifications`: unchanged shape — five entries keyed by the five `situation_id`s. These remain the background NER 4.2.3 prior shown on each situation card.

### 2.5 Audit report — pre-baked envelope (Grid)

```jsonc
{
  "audit_id": "aud-ngm-001",
  "headline": "Strong investigation — busbar fault correctly classified, precursor link surfaced, two of five actions need tighter procedure citation.",
  "band": "strong",
  "score_pct": 0.7619,
  "weighted_score": 16,
  "duration_seconds": 142,
  "tool_call_count": 14,
  "rubric": {
    "evidence_completeness": {"score": 3, "note": "Alarm + SCADA + event-timeline coverage of the right station and window. find_event_timeline + reconstruct_event_timeline_causal both fired."},
    "topology_coverage":    {"score": 3, "note": "Bus tie + corridor endpoints + common-mode devices all walked. graph_bus_topology distinguished Bus 275-1 vs Bus 275-2."},
    "hypothesis_quality":   {"score": 2, "note": "Mechanism correctly identified (inter-phase flashover on DS-275-13). Could have flagged silver-plating wear as a named failure mode earlier."},
    "action_grounding":     {"score": 2, "note": "Actions 1, 2, 5 cite OP-NET source ids. Actions 3 and 4 reference procedures by name only."},
    "summary_quality":      {"score": 3, "note": "Headline + 3 evidence bullets + 1 open question (next bus-zone outage scope)."},
    "grounding":            {"score": 3, "note": "No fabricated equipment ids or measurements; all referenced rows traceable to find_* tool envelopes."}
  },
  "gaps": [
    "No call to graph_breaker_neighbourhood — CB-031/041 sympathetic trip risk not explicitly ruled out.",
    "Precursor advisory missing thermal-scan window estimate."
  ],
  "improvements": [
    "Cite OP-NET-3120 §(b) on Action 3 directly.",
    "Add a search_nearhit_reports filter for silver-plating wear before Action 5."
  ],
  "markdown": "## Investigation audit — MARRABEL_NX bus 275-1 trip\n\n…"
}
```

### 2.6 Priority-action decisions — pre-baked (Grid)

| Action | Pre-baked decision | Note |
|---|---|---|
| A1 — Busbar restoration kickoff | `complete` | "EHRT confirmed bus state at 14:41; tests scheduled 15:15." |
| A2 — Generator resync prep | `pending` (no decision) | — |
| A3 — Market notice 30-min deadline | `declined` then `reopened` | Declined "Wrong workflow — handled by NGA market desk." Reopened 8 s later "On second look this is ours; will file." |
| A4 — Isolator replacement scope | `pending` | — |
| A5 — Precursor thermal-scan ticket | `pending` | — |

### 2.7 Streamed summary — pre-baked (Grid)

- Headline: "MARRABEL_NX 275 kV Bus 275-1 — non-credible contingency, 412 MW lost, precursor signature 37 min ahead."
- Bullets:
  1. DS-275-13 inter-phase flashover at 11:15:14 → Bus 275-1 differential (Scheme A) cleared; Bus 275-2 unaffected.
  2. Units 3 + 4 tripped on consequential reverse-power / under-frequency; Unit 1 stable on Bus 275-2.
  3. EHR frequency nadir 49.71 Hz, recovered to SOFB within 100 s via FRS.
  4. Precursor: 15 s sub-threshold KV transient at 13:55:30 — same bay, no alarm fired.
- Open questions:
  1. Whether the v2024 isolator inspection programme should be accelerated across all EHR 275 kV bus sections.

---

## 3. ATC (TCAS RA Go-Around Cascade) — modernized scenario spec

### 3.1 Narrative invariants

- Anonymisation unchanged (METROFIELD_APP / NORTHGATE_TWR / fictional XKL-/YEA-/ZQM- callsigns).
- Two value wins unchanged: (1) correct surveillance-induced classification in seconds vs 30–45 min replay, (2) precursor detection 12 min ahead.
- ICAO Doc 4444 / Annex 13 / EU 376/2014 citations retained.
- Narration style guide (§0 of ATC_SCENARIO_SPEC.md) is non-negotiable — business framing first, technical proof second.

### 3.2 Phase layout (modernized)

| Phase | File | Frames | Surface exercised |
|---|---|---|---|
| 1 — Streamed scan | `phases/01_scan.ts` | f000a–f000g | Same shape as Grid — five situations streamed as `partial` → `enrich`. Vocabulary overrides so the spinner says "Correlating radar tracks…". |
| 2 — Classify (background prior) | `phases/02_classify.ts` | f000h–f000i | `panel.situations.classify` ×5. Badges: FALSE ALARM (precursor) / CONFIRMED (critical) / CONFIRMED (major) / UNCONFIRMED (serious) / FALSE ALARM (investigate). |
| 3 — Topology + Airspace Status | `phases/03_topology.ts` | f000j–f000l | METROFIELD_APP centre + neighbours + CRITICAL overlay on `TRACKER.FUSION` + `STCA.PROCESSOR`; first `panel.system_status.set` showing METRO TMA CRITICAL. |
| 4 — Incident Investigator turn (one thread) | `phases/04_investigator.ts` | f001–f060 | All 24 ATC-skinned tool calls per §3.3, including delta-streamed args + truncated envelope on `graph_switch_state_snapshot`. Background dispatcher events interleave. |
| 5 — Auto-summary stream | `phases/05_summary.ts` | f061–f065 | Streamed safety-investigation summary. |
| 6 — Action decisions | `phases/06_decisions.ts` | f066–f072 | Complete (A2 — surveillance degraded flag), Decline + Reopen (A3 — flow restriction), Complete-with-note (A5 — MOR filing). |
| 7 — Session Audit | `phases/07_audit.ts` | f073–f092 | 12× `audit.tool_call` → `audit.report` (`band: excellent`, `0.8571`, `18`); second `panel.system_status.set` showing METRO TMA CLEAR. |
| 8 — Precursor reveal + classify diff | `phases/08_precursor.ts` | f093–f100 | Investigator re-pulls 08:17 fused-tracker window; classifies precursor as `non_event` advisory linked to v4.7.2 patch deploy. |
| 9 — Detector Tuning | `phases/09_tuning.ts` | f101–f110 | Operator tightens fused-vs-ADS-B divergence threshold so the 12 s precursor would have surfaced MAJOR. |
| 10 — Data Search Assistant | `phases/10_data_search.ts` | f111–f125 | Three-turn dock conversation hitting `find_alarms` (alerts variant), `query_kql`, `query_gremlin`. |

Total ~125 frames, ~180 s runtime.

### 3.3 Investigator turn — full tool sequence (phase 4)

ATC re-skin of the live GridManager surface. Every energy tool maps to an ATC analogue with identical envelope shape so the live renderer registry stays unified.

| # | Energy tool | ATC tool name | Renderer | Purpose |
|---|---|---|---|---|
| 1 | `detect_situations` | `detect_situations` | bespoke | Confirms radar feed in-thread. |
| 2 | `find_station_assets` | `find_facility_assets` | `TabularResult` | METROFIELD_APP equipment inventory (TRACKER, PSR, MSSR, ADS-B, STCA, ILS). |
| 3 | `find_asset` | `find_asset` | `TabularResult` | `TRACKER.FUSION` detail — vendor, version, last patch. |
| 4 | `find_event_timeline` | `find_event_timeline` | `TabularResult` | Unified alert + surveillance timeline 08:29 → 08:34 UTC. |
| 5 | `find_alarms` | `find_alerts` | `TabularResult` | 3× STCA + 1× TCAS RA + 2× APW in 36 s. |
| 6 | `find_alarm_by_mrid` | `find_alert_by_id` | `TabularResult` | Resolve alert `STCA-08-29-54` → full body. |
| 7 | `find_scada` | `find_surveillance` | `TabularResult` | Fused tracker output, 08:29 → 08:34. |
| 8 | `find_scada_changes` | `find_surveillance_changes` | `TabularResult` | Fused-vs-ADS-B truth-track diff — the smoking gun. |
| 9 | `reconstruct_event_timeline_causal` | `reconstruct_alert_cascade_causal` | `CausalEventTimelineResult` (R11) | tracker fault → ghost STCA #1 → breakout → ghost STCA #2 → avoiding action → coordinated RA. |
| 10 | `bus_zone_audit` | `surveillance_zone_audit` | `BusZoneAuditResult` (R11) | Per-track ADS-B-vs-fused coverage; flags ghost tracks. |
| 11 | `breaker_fail_signature` | `tracker_fault_signature` | `BreakerFailSignatureResult` (R11) | Mis-correlation scoring per phantom return. |
| 12 | `frequency_disturbance_profile` | `runway_capacity_profile` | `FrequencyDisturbanceProfileResult` (R11) | 27L capacity sparkline: 18/hr → 0 → 18/hr; runway-rate nadir + recovery. |
| 13 | `graph_station_equipment` | `graph_facility_equipment` | `GraphResult` | Facility equipment graph. |
| 14 | `graph_equipment_connections` | `graph_equipment_connections` | `GraphResult` | TRACKER → STCA → controller-display dependency chain. |
| 15 | `graph_bus_topology` | `graph_facility_topology` | `GraphEnvelopeResult` | METROFIELD_APP system adjacency. |
| 16 | `graph_bus_boundary` | `graph_sector_boundary` | `GraphEnvelopeResult` | Sector boundary set for the affected 27L corridor. |
| 17 | `graph_corridor_endpoints` | `surveillance_corridor_trace` | `GraphEnvelopeResult` | Fused-tracker cells along the 27L approach corridor. |
| 18 | `graph_breaker_neighbourhood` | `tracker_dependent_subsystems` | `GraphEnvelopeResult` | Downstream STCA + display systems impacted. |
| 19 | `graph_common_mode_devices` | `graph_common_mode_devices` | `GraphEnvelopeResult` | Identifies fusion engine as the common-mode device across both STCAs. |
| 20 | `graph_switch_state_snapshot` | `surveillance_state_snapshot` | `GraphEnvelopeResult` (TRUNCATED, R12) | Full surveillance state — envelope > 64 KiB, ships truncated. |
| 21 | `search_investigation_clues` | `search_investigation_clues` | `SearchResultCards` | EUROCONTROL voluntary safety DB — prior fusion-engine regressions. |
| 22 | `search_smirks` | `search_safety_recs` | `SearchResultCards` | Fictional `SSP-2025-Q4-008` advisory on tracker patch regressions. |
| 23 | `search_paws` | `search_sops` | `SearchResultCards` | SOP-ATM-042 (surveillance degradation), SOP-ATM-233 (runway recovery), MOR template. |
| 24 | `search_nearhit_reports` | `search_nearhit_reports` | `SearchResultCards` | Internal incident-review excerpts on patch-deploy regressions. |
| 25–29 | `push_action` ×5 | `push_action` ×5 | `PanelToolSummary` | A1 27L suspend + resequence, A2 fused-tracker degraded + ADS-B validation, A3 EASTVALE flow restriction, A4 capture surveillance evidence pre-rollback, A5 file TCAS RA MOR. |
| 30 | `classify` | `classify` | `ClassifyVerdictResult` (R2) | Verdict `credible_event` (CONFIRMED). Banner red. ICAO Annex 13 / EU 376/2014. |
| 31 | Final streamed text | — | — | 3–4 paragraphs. Plain-English win line opens; precursor link closes. |

### 3.4 Bootstrap changes (ATC)

- `main_agents`: single `grid_manager` aliased to display name `Incident Investigator`. Hidden `investigator` + `dispatcher` aliases retained.
- `dock_agents`: keep `data_search`. Reply keywords updated for `find_facility_assets`, `surveillance_corridor_trace`, `search_safety_recs`.
- `vocabulary`: add `auditPanelLabel: "Safety Investigation Review"`, `auditAuthority: "ICAO Annex 13 / EU 376/2014"`, `classifyVerdictLabel: "Occurrence Classification"`. `classificationLabels.credible` remains `CONFIRMED` per existing ATC vocab override.
- `classifications`: existing five entries retained, citation field continues to use `ner_citation` (historical name).

### 3.5 Audit report — pre-baked envelope (ATC)

```jsonc
{
  "audit_id": "aud-atc-001",
  "headline": "Excellent investigation — fusion-engine root cause identified within the first three tool calls and linked to the morning v4.7.2 patch deploy.",
  "band": "excellent",
  "score_pct": 0.8571,
  "weighted_score": 18,
  "duration_seconds": 118,
  "tool_call_count": 13,
  "rubric": {
    "evidence_completeness": {"score": 3, "note": "Fused tracker, ADS-B truth track, alert log, traffic state all pulled. find_surveillance_changes confirms the geometry mismatch directly."},
    "topology_coverage":    {"score": 3, "note": "Facility topology + surveillance corridor + common-mode devices walked. Common-mode device call returned the tracker fusion engine cleanly."},
    "hypothesis_quality":   {"score": 3, "note": "Surveillance-induced root cause identified; linked to v4.7.2 patch deploy via the precursor window."},
    "action_grounding":     {"score": 3, "note": "Every action cites SOP-ATM-042 or SOP-ATM-233 or ICAO Doc 4444 §15.7.4 by id."},
    "summary_quality":      {"score": 3, "note": "Headline + bullets + open questions; explicit RA-pair callout."},
    "grounding":            {"score": 3, "note": "No fabricated callsigns or alert tags; ADS-B truth-track cited as the disambiguating source."}
  },
  "gaps": [
    "No explicit search_nearhit_reports lookup for prior fusion-engine regressions before classify fired — minor sequencing nit."
  ],
  "improvements": [
    "Pre-flight a search_nearhit_reports call as the third tool in future surveillance-fault investigations."
  ],
  "markdown": "## Safety investigation audit — METROFIELD_APP TCAS RA cascade\n\n…"
}
```

### 3.6 Streamed summary — pre-baked (ATC)

- Headline: "METROFIELD_APP — surveillance-induced coordinated TCAS RA, 5 aircraft affected, root cause linked to morning patch deploy."
- Bullets:
  1. Two false STCA events drove correct controller breakouts that converged geometry; TCAS II v7.1 fired a real coordinated RA.
  2. ADS-B truth-track confirms both phantom conflicts were fictitious; fused tracker mis-correlated PSR returns with active Mode S codes.
  3. Fault signature matches a 12-second precursor at 08:17:30 in the same 27L approach corridor.
  4. Tracker software v4.7.2 deployed 06:00 UTC is the suspect regression — rollback under engineering review.
- Open questions:
  1. Whether ADS-B-only separation should be invoked across all 27L approaches pending v4.7.2 rollback.

---

## 4. Scenario-agnostic deferred items

- **`BACKGROUND_ERROR` / `DELEGATION_ERROR` overflow markers**: backend rate-limit safety net not visible to the audience; do not model.
- **`BoundedEventChannel` per-key 5 s rate limit**: same reasoning.
- **Live RBAC / Entra / Ed25519 devauth**: kiosk has no real auth surface; the demo simulates a logged-in operator only.
- **CHAOS-fix per-replica concurrency guards** (per-session abort registry, devauth signature replay cache): irrelevant outside the live backend.

---

## 5. File change summary

| Path | Action |
|---|---|
| `app/frontend/src/demo/scenarioSchema.ts` | Extend `FramePatch` union with `summary.start`/`append`/`done`, `audit.start`/`tool_call`/`report`/`done`, `panel.situations.partial`/`enrich`/`done`, `panel.priority_action.decide`. Document `classify` tool envelope in JSDoc. |
| `app/frontend/src/demo/applyPatch.ts` | Wire all new ops to the relevant stores. |
| `app/frontend/src/stores/summaryStore.ts` | Add `start()`, `append()`, `done()`. |
| `app/frontend/src/stores/auditStore.ts` | New file — `running`, `toolTrail`, `report` + actions. |
| `app/frontend/src/stores/situationStore.ts` | Add `partial()`, `enrich()`, `done()`; expose `clusters` selector grouping by `(station, severity)`. |
| `app/frontend/src/stores/panelStore.ts` | Add `decide()` + `decisions` + `timeline` state. |
| `app/frontend/src/stores/chatStore.ts` | Add `lastClassifyVerdict` selector. |
| `app/frontend/src/components/panels/ClassifyVerdictBanner.tsx` | New — coloured banner above Operator Priorities. |
| `app/frontend/src/components/panels/SessionAuditPanel.tsx` | New — band pill + 6 rubric rows + markdown body + tool trail. |
| `app/frontend/src/components/panels/SituationClusterCard.tsx` | New — `(station, severity)` cluster wrapper. |
| `app/frontend/src/components/panels/SituationAlertsPanel.tsx` | Switch flat view to cluster rendering. |
| `app/frontend/src/components/panels/PriorityActionCard.tsx` | Complete / Decline / Reopen affordances + collapse. |
| `app/frontend/src/components/chat/tool-renderers/index.ts` | Register `ClassifyVerdictResult`, `CausalEventTimelineResult`; add `TOOL_PROMINENT_COLUMNS` for new tools; standardise envelope shape to `{columns, rows}`. |
| `app/frontend/src/components/chat/tool-renderers/CausalEventTimelineResult.tsx` | New — bespoke renderer mirroring live tool. |
| `app/frontend/src/foundation/vocabulary/index.ts` | Add `auditPanelLabel`, `auditAuthority`, `classifyVerdictLabel` keys + ATC overrides. |
| `app/frontend/src/demo/scenarios/ngm_busbar_trip/bootstrap.ts` | Single `grid_manager` agent + hidden aliases; dock replies updated; vocabulary keys added. |
| `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/01_scan.ts` | Rewrite to stream `partial` → `enrich` → `done`. |
| `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/04_investigate.ts` → `04_gridmanager.ts` | Full rewrite per §2.3. |
| `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/05_delegate.ts` | Delete. |
| `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/05_summary.ts` | New. |
| `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/06_decisions.ts` | New. |
| `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/07_audit.ts` | New. |
| `app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/08_precursor.ts` | Renumbered (was `07_precursor.ts`). |
| `app/frontend/src/demo/scenarios/atc_tcas_cascade/bootstrap.ts` | Same shape as Grid bootstrap. |
| `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/01_scan.ts` | Stream `partial` → `enrich` → `done`. |
| `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/04_investigate.ts` → `04_investigator.ts` | Full rewrite per §3.3. |
| `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/05_delegate.ts` | Delete. |
| `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/05_summary.ts` | New. |
| `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/06_decisions.ts` | New. |
| `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/07_audit.ts` | New. |
| `app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/08_precursor.ts` | Renumbered (was `07_precursor.ts`). |
| `app/frontend/tests/chat/classifyVerdictBanner.test.tsx` | New — R2. |
| `app/frontend/tests/stores/summaryStore.test.ts` | New — R3. |
| `app/frontend/tests/stores/auditStore.test.ts` | New — R4. |
| `app/frontend/tests/stores/situationStore.cluster.test.ts` | New — R5. |
| `app/frontend/tests/stores/panelStore.decisions.test.ts` | New — R7. |
| `app/frontend/tests/chat/toolResultCard.coverage.test.ts` | New — R6. |
| `app/frontend/e2e/single-agent-flow.spec.ts` | New — R1. |
| `app/frontend/e2e/classify-verdict-banner.spec.ts` | New — R2. |
| `app/frontend/e2e/auto-summary-stream.spec.ts` | New — R3. |
| `app/frontend/e2e/session-audit-panel.spec.ts` | New — R4. |
| `app/frontend/e2e/situation-streaming.spec.ts` | New — R5. |
| `app/frontend/e2e/tool-coverage.spec.ts` | New — R6. |
| `app/frontend/e2e/priority-action-decisions.spec.ts` | New — R7. |
| `app/frontend/e2e/spotlight-coverage.spec.ts` | New — R8. |
| `app/frontend/src/components/chat/tool-renderers/BusZoneAuditResult.tsx` | New — R11. |
| `app/frontend/src/components/chat/tool-renderers/BreakerFailSignatureResult.tsx` | New — R11. |
| `app/frontend/src/components/chat/tool-renderers/FrequencyDisturbanceProfileResult.tsx` | New — R11. |
| `app/frontend/src/components/chat/tool-renderers/ToolResultCard.tsx` | New — R19 scaffold. |
| `app/frontend/src/components/chat/tool-renderers/ResultTable.tsx` | New — R19 primitive. |
| `app/frontend/src/components/chat/tool-renderers/helpers.ts` | New — R19 `formatCell` + `extractError`. |
| `app/frontend/src/components/chat/ToolCallDisplay.tsx` | Updated — R9 streaming args render. |
| `app/frontend/src/stores/detectorTuningStore.ts` | New — R13. |
| `app/frontend/src/components/panels/DetectorTuningPanel.tsx` | New — R13. |
| `app/frontend/src/components/header/SavedSessionPicker.tsx` | New — R15. |
| `app/frontend/src/stores/sessionStore.ts` | Updated — R15 replay mode. |
| `app/frontend/src/stores/backgroundStore.ts` | New — R16. |
| `app/frontend/src/components/panels/BackgroundDispatcherPanel.tsx` | New — R16. |
| `app/frontend/src/stores/systemStatusStore.ts` | New — R17. |
| `app/frontend/src/components/panels/SystemStatusDashboard.tsx` | New — R17. |
| `app/frontend/src/stores/coachmarkStore.ts` | New — R18. |
| `app/frontend/src/components/demo/PlayDemoButton.tsx` | Updated — R18 coachmark. |
| `app/frontend/src/components/demo/PlayerToolbar.tsx` | New — R20 mode toggles. |
| `app/frontend/src/demo/framePlayer.ts` | Updated — R20 step/annotated modes. |
| `app/frontend/src/demo/demoPlayerStore.ts` | Updated — R20 mode state. |
| Both `scenarios/*/phases/09_tuning.ts` | New — R13. |
| Both `scenarios/*/phases/10_data_search.ts` | New — R14. |
| `app/frontend/tests/chat/toolDelta.test.ts` | New — R9. |
| `app/frontend/tests/chat/toolFamilyCoverage.test.ts` | New — R10. |
| `app/frontend/tests/chat/compoundRenderers.test.tsx` | New — R11. |
| `app/frontend/tests/chat/toolResultCard.scaffold.test.tsx` | New — R19. |
| `app/frontend/tests/stores/detectorTuningStore.test.ts` | New — R13. |
| `app/frontend/e2e/tool-arg-streaming.spec.ts` | New — R9. |
| `app/frontend/e2e/tool-family-coverage.spec.ts` | New — R10. |
| `app/frontend/e2e/truncation-banner.spec.ts` | New — R12. |
| `app/frontend/e2e/detector-tuning.spec.ts` | New — R13. |
| `app/frontend/e2e/data-search-dock.spec.ts` | New — R14. |
| `app/frontend/e2e/saved-session-picker.spec.ts` | New — R15. |
| `app/frontend/e2e/background-dispatcher.spec.ts` | New — R16. |
| `app/frontend/e2e/system-status-dashboard.spec.ts` | New — R17. |
| `app/frontend/e2e/first-run-coachmark.spec.ts` | New — R18. |
| `app/frontend/e2e/player-modes.spec.ts` | New — R20. |

---

## 6. Out-of-scope explicit list

- Wiring the kiosk to a real backend. Everything stays canned.
- Reproducing the live truncation envelope, BACKGROUND_ERROR / DELEGATION_ERROR overflow markers, or per-stream lifecycle logs. Not visible to audience.
- Reproducing `BoundedEventChannel` rate-limit behaviour.
- Live RBAC / Entra / Ed25519 devauth.
- Detector configuration patching from the UI.

---

## 7. Acceptance — single visual pass per scenario

A reviewer pointing the live deployed kiosk at each scenario and watching it once must observe, in order:

1. First-page coachmark ring + tooltip on the scenario picker (R18). Dismisses on click.
2. Picker dropdown shows two scenarios grouped by industry.
3. Selecting a scenario starts the radar — five cards stream `partial` → `enrich`, at least one cluster card collapses duplicates (R5).
4. Background NER 4.2.3 classification badges fade in per card.
5. Topology graph renders with CRITICAL overlay; System Status dashboard shows affected region CRITICAL (R17).
6. ONE chat thread runs the entire investigation — no tab switch, no delegation card (R1).
7. Tool calls render in the documented order — all 24 distinct tool families are visible at least once (R10), with two long-argument tools streaming their args via `tool_call_delta` (R9), and one tool result rendering the truncation banner (R12).
8. The four compound investigation tools each render their bespoke layouts: causal timeline, bus-zone audit, breaker-fail-signature scorecard, frequency disturbance profile sparkline (R11).
9. Background dispatcher panel publishes at least one full background loop during the chat (R16).
10. Mandatory `classify` tool fires before final text; coloured banner above Operator Priorities quotes the justification (R2).
11. SituationSummaryCard streams the summary inline with an `Auto` badge (R3).
12. Priority-action cards demonstrate Complete + Decline + Reopen + Complete-with-note (R7).
13. Session Audit panel opens; band pill + 6 rubric rows + tool trail + markdown body all populate (R4); System Status flips back to CLEAR after audit lands.
14. Precursor phase re-fires the investigator on the early window and closes the loop with an updated `classify` verdict.
15. Detector Tuning tab demonstrates a live rule edit + Apply that streams a sixth situation card (R13).
16. Data Search Assistant dock runs a three-turn conversation hitting raw KQL + Gremlin + a KB search (R14).
17. Saved Session Picker swaps in a prior similar incident with replay banner + disabled decision affordances (R15).
18. Player toolbar exposes auto / step / annotated modes; `R` restarts (R20).
19. Every new surface above carried at least one spotlight + caption during playback (R8).

No backend call, no LLM, no real codes — the entire product surface visible end-to-end.
