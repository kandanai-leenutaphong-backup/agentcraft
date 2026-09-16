---
name: scenario-design
description: "Use when: designing, writing, reviewing, or implementing a GridIQ kiosk demo scenario from scratch under app/frontend/src/demo/scenarios; includes scenario structure, credibility standards, chat style, phase design, action-card quality, vocabulary, registry, and verification requirements."
---

# Scenario Design Skill

Use this skill when asked to design, implement, review, or improve a GridIQ kiosk demo scenario under:

`app/frontend/src/demo/scenarios`

The goal is not to write an impressive story. The goal is to build a serious operational simulation that a domain expert can tolerate, a business viewer can follow, and a Copilot agent can implement without inventing framework patterns.

## Core Standard

A good scenario feels like a real incident workflow, not a marketing animation.

It must show:

- A detector or operator trigger with specific signals, time windows, and impact.
- Evidence collection through tool calls before conclusions.
- Clear separation between confirmed evidence, inferred mechanism, and unknowns.
- A second-agent handoff that turns findings into concrete operational actions.
- Priority cards that are executable now by named roles.
- A precursor or prevention beat only when the evidence trail supports it.
- Fictional but plausible data, facilities, people, procedures, and identifiers.

Avoid:

- Broad human prompts like "What happened?" when the app is simulating detection.
- Sales language, dramatic claims, or patronising explanations.
- Vague action labels such as "stop trusting the system" or "investigate further".
- Long chat paragraphs that make the agent look like a productivity sink.
- Claims of cause, danger, safety, blame, or preventability before evidence supports them.

## Reference Implementation

Read these before designing a new scenario:

- `app/frontend/src/demo/scenarios/telco_slice_cascade/` — **canonical reference.** The most domain-coherent scenario: fully vocabulary-driven, zero energy-term leakage, dedicated status panel, ~20-row tool tables. Start every new non-energy scenario by copying this directory's shape.
- `app/frontend/src/demo/scenarios/ngm_busbar_trip/`
- `app/frontend/src/demo/scenarios/atc_tcas_cascade/`
- `app/frontend/src/demo/scenarioSchema.ts`
- `app/frontend/src/demo/index.ts`
- `app/frontend/src/demo/kioskBootstrap.ts`
- `app/frontend/src/demo/applyPatch.ts`
- `app/frontend/src/stores/vocabularyStore.ts`
- `TELECOM_SCENARIO_SPEC.md` — worked example of a full scenario spec.

The scenario directory should use the split TypeScript structure:

```text
scenarios/<scenario_id>/
  index.ts
  bootstrap.ts
  situations.ts
  topology.ts
  phases/
    01_scan.ts
    02_classify.ts
    03_topology.ts
    04_investigate.ts
    05_delegate.ts
    06_actions.ts
    07_precursor.ts
```

Keep each file focused. Do not collapse a serious scenario into one giant JSON blob unless explicitly requested.

## Workflow

### 1. Define The Operational Premise

Before writing code, define the scenario in operational terms:

- Industry and operational environment.
- Fictional facility, network, sector, site, route, system, or asset.
- Event window and precursor window.
- Detector signals: alarms, telemetry, surveillance, traffic, capacity, impact.
- What is confirmed immediately.
- What is plausible but not yet proven.
- What action a real operator can take now.
- What the second agent owns.

The premise must survive a domain-expert sanity check. If a real operator would ask "what exactly am I supposed to do?", the scenario is not ready.

### 2. Invent A Domain Without Leaking Reality

Use fictional names and identifiers, but make them structurally plausible.

Good fictional data includes:

- Facility IDs that look like local conventions.
- Asset, runway, sector, equipment, or system identifiers with consistent syntax.
- Timestamped events with sensible ordering.
- Tool results with columns a real analyst would expect.
- Procedure names and section numbers that read like internal manuals.
- Contacts with roles that match the action they own.

Do not use real confidential assets, real incident details, real personnel, or real operator procedures unless the user explicitly provides permission and scope.

### 3. Build The Scenario As A Product Flow

The user will experience the scenario through UI state, not through the spec. Design the flow as a sequence of visible product beats:

1. Scan starts and detects situations.
2. Classification badges resolve.
3. Topology/facility map shows where the issue sits.
4. Investigator receives a detector payload or operational brief.
5. Investigator calls tools before writing conclusions.
6. Investigator delegates a bounded task to the second agent.
7. Dispatcher calls procedures, traffic, participants, or other operational tools.
8. Dispatcher pushes actions.
9. Priority panel receives action cards that mirror the push actions.
10. Precursor/replay beat shows what could be caught earlier, with evidence boundaries.

Do not make the scenario depend on narration alone. The app should make sense with narration hidden.

## Required Files

### `index.ts`

Owns only assembly:

- Import `Scenario` and `SCENARIO_SCHEMA`.
- Import `bootstrap`, situations/topology phase arrays, and all phase arrays.
- Export one `Scenario` object as default.
- Keep `frames` in playback order.

Register the scenario in `app/frontend/src/demo/index.ts` with:

- `id`
- `label`
- `industry`
- `description`
- `load: makeLoader(() => import("./scenarios/<scenario_id>"))`

### `bootstrap.ts`

Seeds the selected scenario into kiosk state. It should define:

- `main_agents`: usually `investigator` plus a second specialist such as `dispatcher`.
- `dock_agents`: data-search agent, welcome text, tools, and canned replies.
- `classifications`: keyed by `situation_id`, with citation and rationale.
- `vocabulary`: required for non-energy domains.

Domain vocabulary must relabel visible UI terms, not just scenario copy. Examples:

- `productName`
- `systemStatusLabel`
- `primaryUnit`
- `primaryUnitLabel`
- `telemetryLabel`
- `classificationLabels`
- `scanMessages`
- disclaimer text
- facility/system/region terms

Do not override the full vocabulary when only a few keys differ. Partial overrides merge with the energy default.

### `situations.ts`

Defines the situation cards loaded by `panel.situations.set`.

Every situation should include:

- Stable `situation_id`.
- Window start/end.
- Facility/station/asset identifier.
- Severity.
- Scores and signal JSON strings.
- Affected tags/equipment.
- Pattern names and details.
- Capacity or impact fields, even when a non-energy domain uses relabelled units.

Situation cards are the user's first evidence surface. They must not overstate cause. Use classification rationale to distinguish confirmed event, flow consequence, false alarm, non-event, or advisory.

### `topology.ts`

Defines the operational graph.

The graph should show:

- A center node where the incident occurs.
- One-hop neighbors directly affected.
- Two-hop neighbors for flow or dependency context.
- Equipment rows that align with the incident mechanism.
- Overlay equipment IDs that make the issue visible in the topology panel.

Do not build a generic map. The graph must help explain why the incident propagates.

### `phases/01_scan.ts`

Starts scan animation and loads situations.

Use:

- `panel.situations.scan_start`
- wait frame for apparent scan duration
- `panel.situations.set`

The scan narration can orient the viewer, but the situation cards must carry the real content.

### `phases/02_classify.ts`

Loads classification results from `bootstrap.classifications` through `panel.situations.classify`.

The classification rationale must be domain-specific and cite the fictional authority/procedure. Do not reuse energy terms like NER/GOR for another industry unless the scenario is energy.

### `phases/03_topology.ts`

Loads topology through `topology.set`.

Use topology to show causal location or dependency, not decoration.

### `phases/04_investigate.ts`

This is the most important credibility phase.

The first message should usually be a detector or operational handoff, not a casual user question.

Good opener:

```md
**Situation Detector trigger:** `SD-ATC-20260314-0830`

Investigate `METROFIELD_APP` from `2026-03-14 08:29:00` to `08:34:00` UTC.

- **Alerts:** `stca=3`, `tcas_ra=1`, `apw=2`
- **Surveillance:** `fused_ghost=2`, `mode_s_latch=2`, `adsb_disagree=2`
- **Traffic:** `go_around=1`, `approach_break=1`, `hold_initiated=2`
- **Impact:** `5 ops` affected
```

Bad opener:

```md
What just happened? Was anyone in danger?
```

Investigator workflow:

1. Call broad context tool first when available.
2. Call event timeline / alert chronology.
3. Call telemetry / surveillance / SCADA changes.
4. Call cross-reference or clue search only after primary evidence.
5. Call participants/contacts if needed for the handoff.
6. Write a concise markdown finding.
7. Delegate a bounded task to the second agent.

Investigator findings should be concise markdown:

```md
## Investigation update

`FACILITY` · `window`

**Confirmed**
- Fact supported by returned tool data.
- Fact supported by returned tool data.

**Mismatch**
- Evidence disagreement or ambiguity.

**Working hypothesis**
- Plausible mechanism, explicitly not confirmed.

**Handoff**
- Concrete task set for dispatcher.
```

Rules:

- Do not lead with conclusion before tools return.
- Do not narrate what the UI already shows.
- Do not explain basic domain facts unless necessary for the action.
- Use markdown headings and bullets.
- Keep each paragraph to 1-2 lines.
- Preserve uncertainty.

### `phases/05_delegate.ts`

The second agent must look like an operational specialist, not a second narrator.

Required pattern:

- Receive investigator handoff as `is_delegation: true`.
- Pull procedures/runbooks.
- Pull affected traffic/assets/equipment/participants.
- Pull contacts or owners.
- Write a concise basis for action.
- Push `push_action` tool calls that match the priority cards.

Dispatcher output should be compact:

```md
## Dispatcher basis

- **Event:** confirmed event.
- **Mode:** degraded/normal/unknown.
- **Boundary:** what is not proven.

**Actions to push**
1. Concrete task.
2. Concrete task.
3. Concrete task.
```

Every dispatcher action must be something a role can do now:

- call a named control room
- set a rate cap
- hold a route or flow
- isolate an asset
- mark a system degraded
- preserve evidence
- file a report
- dispatch inspection
- confirm status with a named owner

### `phases/06_actions.ts`

Action cards are not summaries. They are work instructions.

Each card must include:

- `action`: one concrete verb phrase.
- `reasoning`: confirmed evidence, why the action is needed, uncertainty boundary.
- `guide`: numbered operational steps.
- `priority`: 5 for immediate safety/security/continuity tasks, 4 for urgent supporting tasks, lower only when genuinely secondary.
- `contacts`: names, roles, phone, Teams alias.
- `sources`: procedure/tool/evidence citations.

Quality bar for action headlines:

- Good: `Mark 27L fused tracker degraded and require ADS-B validation for every 27L STCA`
- Good: `Confirm MARRABEL_NX 275 kV Bus 275-1 is de-energised, isolated, and locked out`
- Bad: `Investigate tracker issue`
- Bad: `Stop trusting fused radar`
- Bad: `Coordinate with stakeholders`

Reasoning format:

```md
**Confirmed evidence**
- Tool-backed fact.
- Tool-backed fact.

**Why this action is needed**
- Operational reason.

**Boundary condition**
- What this action does not assume.
```

### `phases/07_precursor.ts`

Use a precursor only if it is supported by data in the scenario.

The precursor should show:

- Earlier signal.
- Matching pattern or relationship.
- Why it was not obvious.
- What could have been done.
- What remains unproven.

Do not claim the incident was preventable unless the scenario has enough evidence and the action path is realistic.

Good precursor language:

```md
## Precursor check

- Earlier signal.
- Matching pattern.
- No matching truth source.

**Assessment:** relevant precursor evidence, not proof of cause.

**Control note:** concrete operating constraint until cleared.
```

## Chat Style Rules

Chats must be concise and efficient.

Use:

- Markdown headings.
- Bullets.
- Inline code for identifiers, times, callsigns, tags, assets, and procedure IDs.
- Short sections: `Confirmed`, `Mismatch`, `Working hypothesis`, `Handoff`, `Actions to push`.
- Tool calls as the evidence trail.

Avoid:

- Long paragraphs.
- Dramatic phrasing.
- Repeating all tool rows in prose.
- Explaining why the product is valuable.
- Saying an issue is solved when evidence only supports a hypothesis.
- Soft filler like "I am going to" or "we have our answer".

The chat should make an expert think: "This is a useful triage assistant." It should not make them think: "This is a verbose chatbot." 

## Tool Result Design

Tool results are the scenario's audit trail. They must look like real data products.

Use table-like JSON shapes that match existing renderers:

- Tabular tools: `JSON.stringify({ columns, data, ...metadata })`
- Search tools: `JSON.stringify({ results: [{ title, source, score, text }], count })`
- Delegation: `JSON.stringify({ agent_id, status, duration_ms, response })`

Tool call names should either already be registered in `components/chat/tool-renderers/index.ts` or be added there with the correct renderer. If a tool falls back to raw JSON, the demo looks unfinished.

**Data richness.** Tabular tool results should carry roughly **20 rows** so the evidence reads like a real data product, not a stub. Keep every row timeline-coherent: order by timestamp, tie each row back to the incident mechanism, and include benign/context rows (prior unrelated changes, unaffected slices, the red-herring asset) so the operator sees the agent *discriminating signal from noise*, not just listing the obvious. Add a summary metadata object (`{ window, total_alarms, critical, major, ... }` or an `assessment` string) so the table has a headline read. The Telco `04_tool_suite.ts` tables are the reference: 20-row alarm log, 20-row KPI delta table, 20-row change timeline with the trigger change plus 19 context/unrelated changes.

## Scenario Vocabulary

For a non-energy scenario, define vocabulary in `bootstrap.ts`.

Minimum useful overrides:

- `productName`
- `systemStatusLabel`
- `primaryUnit`
- `primaryUnitLabel`
- `telemetryLabel`
- `classificationLabels`
- `classificationAuthority`
- `classifyingText`
- `scanMessages`
- `disclaimerPill`
- `disclaimerHeading`
- `disclaimerBody`
- `facilityTerm`
- `facilityTermSingular`
- `regionTerm`
- `systemLabel`
- `threatLabel`
- `stepChangeLabel`
- `impactLabel`

Domain-coherence overrides (added with the Telco scenario — set these for **every** non-energy domain or energy units leak into the situation card and topology surfaces):

- `impactUnit` — short head-row magnitude unit (energy `MW`, telecom `subs`, ATC `ops`).
- `equipmentTerm` — generic asset noun (energy `Equipment`, telecom `Network element`, ATC `System`).
- `identifierLabel` — per-asset external id label in the topology detail pane (energy `SCADA ID`, telecom `Element ID`, ATC `Surveillance ID`).
- `equipmentClassLabel` — asset classification label (energy `CIM classes`, telecom `Function classes`).
- `equipmentGroupUnit` — topology grouping dimension. Energy `kV`; set `""` for any domain without a voltage-tier concept so the grouping rows and headers disappear.
- `topologyStats` — declarative `[{ label, field }]` grid for the topology detail pane. `field` is one of `nominal_kv | mw_max | mva_rated`. Energy shows all three; telecom shows `[{ label: "Gbps", field: "mw_max" }]`; ATC shows `[{ label: "ops/hr", field: "mw_max" }]`.

After selecting a scenario, `demoPlayerStore.loadScenario()` applies full `kiosk_bootstrap`; do not bypass this by applying vocabulary alone.

## Domain Credibility Checklist

Before implementation, verify:

- The incident has a plausible operational trigger.
- The detector payload includes counts and impact, not a vague instruction.
- Tool calls follow the order a serious analyst would use.
- Every conclusion is supported by a displayed tool result.
- Every hypothesis is labelled as a hypothesis.
- The second agent has a real job, not just a summary role.
- Every priority action is executable now.
- Every contact owns the action assigned to them.
- Every procedure/source looks like something that would govern the action.
- The precursor beat does not overclaim.
- The chat is concise enough to read during a demo.
- The full vocabulary (including `impactUnit`, `equipmentTerm`, `identifierLabel`, `equipmentClassLabel`, `equipmentGroupUnit`, `topologyStats`) is set, and no other domain's units (`MW`, `SCADA`, `kV`, `Hz`, `MVA`, `NEM`, `CIM`) appear on any viewer-reachable surface.

## Implementation Checklist

When adding a new scenario:

1. Copy `app/frontend/src/demo/scenarios/telco_slice_cascade/` to `app/frontend/src/demo/scenarios/<scenario_id>/` and rewrite content.
2. Keep `index.ts`, `bootstrap.ts`, `situations.ts`, `topology.ts`, and phase files; add `networkStatus.ts`-style payload only if the status board needs a new data shape.
3. Export `Scenario` with `schema: SCENARIO_SCHEMA`.
4. Set the **full** `kiosk_bootstrap.vocabulary`, including the domain-coherence keys (`impactUnit`, `equipmentTerm`, `identifierLabel`, `equipmentClassLabel`, `equipmentGroupUnit`, `topologyStats`).
5. Field-map `topology.ts` to the domain and null inapplicable electrical fields (`nominal_kv`, `mva_rated`, `hz`, `freq`).
6. Register it in `app/frontend/src/demo/index.ts` with `industry`.
7. Add or reuse tool renderers for any new tool names; aim for ~20-row tabular results.
8. Add a Playwright spec that asserts domain vocabulary present AND zero crossover (`MW`/`SCADA`/`kV`/`Hz`/`MVA`/`NEM`), using the `unlockKioskGate` helper.
9. Update scenario documentation such as `AUTODEV.md` or a scenario spec when behavior changes.
10. Run focused Playwright from `app/frontend`.
11. Run `npm run build` from `app/frontend`.
12. Restore tracked `test-results` artifacts if Playwright deletes or rewrites them.

Known command shape:

```bash
APP_URL=http://127.0.0.1:5173 npx playwright test atc-scenario --project chromium --reporter=list
npm run build
git status --short test-results
git restore test-results
```

Do not run the Playwright command from the repo root unless the root has the matching Playwright config. In this project, focused frontend tests run from `app/frontend`.

## Review Checklist

When reviewing a scenario, reject it if:

- The first investigator message is a vague human question instead of a detector/operator payload.
- The investigator reaches conclusions before tool evidence appears.
- The dispatcher does not visibly call tools.
- Action cards are generic advice rather than executable tasks.
- A chat message is mostly prose when markdown bullets would work.
- The UI still contains vocabulary from the wrong domain.
- Any energy unit (`MW`, `SCADA`, `kV`, `Hz`, `MVA`, `NEM`, `CIM`) leaks into the situation card, topology map, detail pane, or command palette for a non-energy scenario.
- The scenario uses real-world names or incidents without explicit approval.
- The precursor is framed as proof without enough evidence.
- The scenario cannot be selected through the scenario picker.
- The focused browser test does not cover the scenario selection and at least one distinctive scenario outcome.

## Canonical Domain-Coherent Blueprint (start here)

The Telco `5G Slice Cascade` scenario is the reference build. Every new scenario should reuse its modular pattern so domains stay fully decoupled and the project stays extensible. The principle: **everything domain-specific is controllable from one central source — the vocabulary store — and shared components never hardcode a single domain's wording.**

### 1. Copy the directory shape

Start by copying `scenarios/telco_slice_cascade/` to `scenarios/<scenario_id>/` and rewriting content. You get the proven file map for free:

```text
scenarios/<scenario_id>/
  index.ts           — assembles Scenario, default export, registry metadata
  bootstrap.ts       — agents, dock replies, classifications, FULL vocabulary
  situations.ts      — 5 situation cards (precursor + critical + consequences + red herring)
  topology.ts        — center + 1-hop + 2-hop graph, field-mapped to the domain
  networkStatus.ts   — (optional) dedicated status-board payload, if data shape differs
  phases/
    01_scan.ts  02_classify.ts  03_topology.ts  04_tool_suite.ts  07_precursor.ts
```

### 2. Vocabulary is the single source of truth

Label-only differences between domains are **never** hardcoded in components — they live in `DomainVocabulary` (`src/stores/vocabularyStore.ts`) and are overridden per scenario via `kiosk_bootstrap.vocabulary`. A scenario that sets its vocabulary completely relabels the situation cards, topology map, command palette, scan messages, classification badges, and disclaimer with zero component edits.

Set the **full** vocabulary, including the domain-coherence keys (`impactUnit`, `equipmentTerm`, `identifierLabel`, `equipmentClassLabel`, `equipmentGroupUnit`, `topologyStats`). Omitting them re-exposes energy defaults (`MW`, `SCADA ID`, `kV`, `CIM classes`).

### 3. Data-shape differences get a dedicated component, gated on a typed store field

When a domain needs a genuinely different *data shape* (not just different labels) — e.g. the Telco NOC "Network Health" board vs the energy "Grid Status" dashboard — add a dedicated component, not a forked card:

1. Add a typed payload interface to `src/api/situationApi.ts` (e.g. `NetworkStatus`).
2. Add a nullable field to `situationStore` and reset it in **all** sites: initial state, `fetchSituations` reset, `applyPatch` `situations.set` + `scan_start`, and `resetDemoState`. Missing one leaks stale state across scenario switches.
3. Add the field to `SituationsSetOp` in `scenarioSchema.ts` and route it through `applyPatch`.
4. Gate the panel in `Workspace.tsx` status-tab ternary: `hasNetworkStatus ? <NetworkStatusPanel/> : hasAirspaceStatus ? <AirspaceStatusPanel/> : <GridStatusPanel/>`.
5. Seed the payload from a `panel.situations.set` frame in `01_scan.ts`.

Delete the scenario directory and the rest of the app must still boot — domains are bolt-ons, never cross-imports.

### 4. Topology field-mapping

The shared topology schema is electrical (`nominal_kv`, `mw_max`, `mva_rated`, `live.mw`, `live.hz`, `live.freq`). Map it to your domain through vocabulary, and **null what does not apply**:

- Carry the domain's primary throughput in `mw_max` / `live.mw` (relabelled by `primaryUnit`).
- Set `equipmentGroupUnit: ""` so no voltage grouping renders.
- Set `topologyStats` to the columns that make sense.
- Set `nominal_kv` and `mva_rated` to `null`; omit `live.hz` and set `live_summary.freq` to `null` unless the domain has a real oscillation metric — otherwise a stray `Hz`/`%` value renders.

### 5. Zero domain crossover — the leak rule

A scenario is not domain-coherent until **no other domain's units appear anywhere a viewer can reach.** The recurring leak set is `MW`, `SCADA`, `kV`, `Hz`, `MVA`, `NEM`, `CIM`. The shared components that now read vocabulary (do not regress these): `SituationCard`, `TopologyDetailPane`, `StationNode`, `EquipmentRow`, `CommandPalette`, `Workspace`. If you add a new shared surface that prints a unit or domain noun, route it through `useVocab(...)`.

### 6. Verify coherence in the e2e spec

Every scenario spec must assert **both** presence of the domain's vocabulary and absence of crossover. Expand a situation card and read the topology detail pane, then:

```ts
// labels are CSS-uppercased → use case-insensitive matchers
expect(detailText).toMatch(/Element ID/i);   // domain vocabulary present
expect(detailText).toContain("Gbps");
expect(detailText).not.toMatch(/SCADA ID/i); // zero crossover
expect(detailText).not.toMatch(/\bMVA\b/);
expect(cardText).not.toMatch(/\bMW\b/);
```

e2e gotchas learned on this build:
- Action cards live in the priorities tab — click `center-tab-priorities` before asserting them.
- Precursor chapter narration is overwritten by later phases — assert the persistent `Precursor check` chat on the investigator tab instead of the chapter title.
- Use the central `unlockKioskGate(page)` helper from `e2e/fixtures.ts` (the internal build has a passcode gate; the public build does not).
- Specs are **not** bundled into the image — you can fix a spec and re-run it against the live URL without redeploying the app.

## Golden Rule

Design scenarios from the point of view of the operator who must act in the next five minutes.

If the scenario does not help that operator understand what is confirmed, what is uncertain, what changed, and what to do next, keep revising.