# AUTODEV.md — GridIQ Demo Framework Reference

Last updated: 2026-04-28

---

## What This Project Is

- **A kiosk-mode demo framework** — no backend, no LLM, no live data
- **Pure static SPA** — React + Zustand + Tailwind, served by nginx
- **Scenario-driven** — hand-authored JSON/TS scenarios drive every UI element
- **Deployed to Azure Container Apps** via `deploy_kiosk.sh` (ACR build → `gridiq-v2`)
- **Live URL**: `https://gridiq-v2.nicesmoke-72d7e88d.australiaeast.azurecontainerapps.io`

---

## Deploy

| Command | When | Time |
|---------|------|------|
| `./deploy_kiosk.sh --yes` | Any scenario or frontend change | ~2 min |
| `./deploy_kiosk.sh --build-only` | Build + push to ACR, don't roll out | ~1.5 min |
| `./deploy_kiosk.sh --update-only --tag <tag>` | Point Container App at existing ACR image | ~30s |

- **Image tag format**: `kiosk-YYYYMMDD-HHMMSS` by default; pass `--tag <tag>` to pin a known image
- **Container App**: `gridiq-v2`
- **ACR**: `crixksfd27yr7rc.azurecr.io`
- **RG**: `SAND-AISBX-MVP-POC-RG-AUE`
- **Dockerfile**: `Dockerfile.kiosk` (multi-stage: `mcr.microsoft.com/devcontainers/javascript-node:1-22-bookworm` build → `mcr.microsoft.com/cbl-mariner/base/nginx:1.22` runtime)
- **nginx config**: `deploy/nginx.kiosk.main.conf` (main config for MCR nginx) + `deploy/nginx.kiosk.conf` (SPA server block)

### Deploy Gotchas

- **`node_modules` stripped on deploy**: `deploy_kiosk.sh` deletes `app/frontend/node_modules/` before uploading to ACR. Run `cd app/frontend && npm install` after deploy if you need local tooling.
- **Local TS check ≠ Docker TS check**: VS Code language server may pass while Docker `tsc` (pinned TypeScript in the MCR Node 22 build image) fails. The deploy build is authoritative.
- **`az acr build` context**: Does NOT support stdin (`-`). Must be a directory path. WSL paths auto-converted by `_az_path()` helper in deploy script.

---

## Demo Scenario Framework

### Architecture

| Component | File | Role |
|-----------|------|------|
| Schema | `src/demo/scenarioSchema.ts` | Type definitions for `gridiq-demo/v1` format |
| Registry | `src/demo/index.ts` | `SCENARIOS[]` array, lazy-loaded via `import()` |
| Player | `src/demo/framePlayer.ts` | Walks `frames[]`, applies patches, waits `transition_ms` |
| Patch dispatcher | `src/demo/applyPatch.ts` | Translates ops → Zustand store mutations |
| Bootstrap | `src/demo/kioskBootstrap.ts` | Seeds default stores on mount and applies selected-scenario agent/dock/classification/vocabulary bootstrap |
| Vocabulary | `src/stores/vocabularyStore.ts` | Scenario-specific UI language and units |
| Spotlight | `src/stores/spotlightStore.ts` | Presentation callouts driven by frame annotations / spotlight ops |
| Kiosk detection | `src/foundation/constants.ts` | `IS_KIOSK = import.meta.env.VITE_KIOSK_MODE` |
| Canned replies | `src/demo/kioskReplies.ts` | Dock agent keyword-match reply engine |

All paths relative to `app/frontend/`.

### Patch Operations (12 ops)

| Op | Target store | Purpose |
|----|-------------|---------|
| `chat.append` | chatStore | Add user/assistant message with optional tool_calls |
| `chat.append_token` | chatStore | Stream text to last assistant message |
| `chat.update_tool` | chatStore | Update tool call status/result/duration by id |
| `panel.priority_action.append` | panelStore | Add priority action card |
| `panel.situations.set` | situationStore | Replace situations list (closes scan spinner) |
| `panel.situations.scan_start` | situationStore | Start radar/spinner animation |
| `panel.situations.classify` | situationStore | Inject classification badges |
| `agent.set_active` | agentStore | Switch active agent tab |
| `topology.set` | topologyStore | Load topology graph with alarm overlay |
| `topology.overlay.set` | topologyStore | Replace / clear topology alarm overlay without reloading graph |
| `ui.spotlight.set` | spotlightStore | Highlight one `data-spotlight-id` element with caption |
| `ui.spotlight.clear` | spotlightStore | Clear active presentation spotlight |

### Scenario Registry Shape

```ts
interface ScenarioListEntry {
  id: string;
  label: string;
  description: string;
  industry: string;              // dropdown group label
  load: () => Promise<Scenario>; // lazy import + assertScenario()
}
```

- Header scenario picker (`src/components/demo/PlayDemoButton.tsx`) is always a dropdown, even if the registry temporarily has one entry
- Picker lives top-right in the header, exposes `data-testid="scenario-picker"`, and groups entries by `industry`
- On first page load, before any scenario is selected, the picker has a visible ring + `scenario-picker-hint` coachmark: "Choose a scenario to trigger."
- Scenario rows use `role="menuitem"`; selecting one starts playback immediately and leaves the picker visible for switching scenarios
- When playback is active, a separate `Stop` button appears next to the picker instead of replacing it

### Scenario Object Shape

```ts
interface Scenario {
  schema: "gridiq-demo/v1";
  id: string;
  label: string;
  description: string;
  frames: Frame[];                   // ordered playback sequence
  kiosk_bootstrap?: KioskBootstrap;  // agents, dock replies, classifications, vocabulary
}
```

### KioskBootstrap Shape

```ts
interface KioskBootstrap {
  main_agents?: KioskAgentSeed[];          // right-column chat agents
  dock_agents?: KioskDockAgentSeed[];      // bottom-dock data agents with canned replies
  classifications?: Record<string, {      // pre-seeded situation classification badges
    classification: "credible" | "non_credible" | "non_event";
    ner_citation: string;                  // field name is ner_citation (historical)
    rationale: string;
  }>;
  vocabulary?: Partial<DomainVocabulary>;  // scenario UI labels/units/text overrides
}
```

- Default boot calls `seedKioskStores()` so the app has a usable energy roster before any scenario is selected
- Scenario selection calls `applyKioskBootstrap(scenario.kiosk_bootstrap ?? {})` from `demoPlayerStore.loadScenario()` before frames run
- `applyKioskBootstrap()` must update all scenario-scoped stores together: main agents, dock agents, canned replies, classifications, and vocabulary
- Do not apply only `kiosk_bootstrap.vocabulary`; alternate-domain agents will fail to appear in chat even though the scenario frames compile

### Frame Shape

```ts
interface Frame {
  id: string;
  chapter?: string;       // starts a new chapter (narration overlay, auto-pause)
  narration?: string;     // presenter script line
  transition_ms: number;  // wait after patch before next frame
  annotation?: {           // optional spotlight shown when annotations are enabled
    target: string;        // data-spotlight-id
    caption: string;
    placement?: "top" | "bottom" | "left" | "right" | "auto";
    padding?: number;
  };
  patch: FramePatch;      // one or more ops applied atomically
}
```

### Scenario Vocabulary

- Store: `src/stores/vocabularyStore.ts`
- Default: `ENERGY_VOCABULARY` is complete and always safe to render
- Scenario override: `kiosk_bootstrap.vocabulary?: Partial<DomainVocabulary>`
- Merge behavior: `setVocabulary(partial)` overlays partial keys on energy defaults; `classificationLabels` is shallow-merged
- Reset behavior: `demoPlayerStore.loadScenario()` calls `reset()` when a scenario has no vocabulary override
- Component access: `useVocab("key")`
- Non-React/store access: `getVocab()`

Common keys:

| Key | Purpose |
|-----|---------|
| `productName` | Header, empty states, gate, spotlight copy |
| `systemStatusLabel` | Left status panel + center tab |
| `primaryUnit`, `primaryUnitLabel` | MW / ops/hr / flow unit labels |
| `frequencyUnit`, `frequencyLabel`, `frequencyNominal` | Frequency-style metric display |
| `alertsLabel`, `telemetryLabel` | Alarm / SCADA / surveillance wording |
| `classificationLabels`, `classificationAuthority`, `classifyingText` | Situation card classification display |
| `scanMessages` | Rotating scan-progress text |
| `disclaimerPill`, `disclaimerHeading`, `disclaimerBody` | Public-demo disclaimer |
| `facilityTerm`, `facilityTermSingular`, `regionTerm`, `systemLabel` | Domain nouns |
| `capacityLabel`, `threatLabel`, `stepChangeLabel`, `impactLabel`, `impactBoostLabel` | Metric headings and badges |

---

## Bundled Scenarios

| ID | Label | Location | Frames | Runtime |
|----|-------|----------|--------|---------|
| `ngm-busbar-trip` | NGM Busbar Trip | `scenarios/ngm_busbar_trip/` (split TS) | 33 | ~95s |
| `atc-tcas-cascade` | TCAS RA Go-Around Cascade | `scenarios/atc_tcas_cascade/` (split TS) | ~32 | ~75s |

### NGM Busbar Trip — File Map

```
scenarios/ngm_busbar_trip/
  index.ts              — assembles Scenario, default export
  bootstrap.ts          — 2 main agents, 1 dock agent (scenario + generic replies), 5 classifications
  situations.ts         — 5 situation cards (1 precursor + 4 post-event)
  topology.ts           — MARRABEL_NX center + 3 1-hop + 3 2-hop neighbors
  phases/
    01_scan.ts          — f000a–f000c: scan start, 10s wait, situations set
    02_classify.ts      — f000d–f000e: classification spinner + badges
    03_topology.ts      — f000f: topology graph with CRITICAL overlay
    04_investigate.ts   — f001–f018: user msg, find_alarms, find_scada, 12 streamed tokens
    05_delegate.ts      — f019–f022: delegation, tab switch, search_procedures
    06_actions.ts       — f023–f027: 5 priority action cards
    07_precursor.ts     — f028–f032: precursor reveal (pattern_history + punchline)
```

### NGM Busbar Trip — Content Summary

- **Spec**: `DEMO_SCENARIO_SPEC.md` (older design reference; implemented scenario data is authoritative)
- **Grid**: EHR region, 7 fictional stations centered on MARRABEL_NX
- **Incident**: 275 kV Bus 275-1 fault / isolator flashover → 430 MW shown on the situation card, 412 MW described in scenario narration and registry copy
- **Date**: 2026-02-12 (fictional)
- **Two demo wins**:
  1. Correct busbar classification in seconds (vs 3h20m in comparable real incidents)
  2. Precursor detection 37 minutes before the trip
- **Dock replies**: scenario replies use legacy match aliases (`redcliff` → MARRABEL, `northvale` → KETTERING, `wentworth` → OAKBANK), plus generic operational replies (`load profile`, `by region`, `capacity headroom`, `equipment status`, `open switching`, fallback)

### ATC TCAS Cascade — File Map

```
scenarios/atc_tcas_cascade/
  index.ts              — assembles Scenario, default export
  bootstrap.ts          — Incident Investigator + ATC Dispatcher agents, data-search dock agent, ATC vocabulary
  situations.ts         — 5 fictional airspace situations centered on METROFIELD_APP
  topology.ts           — METROFIELD_APP corridor nodes and surveillance/fusion dependencies
  phases/
    01_scan.ts          — scan start and situation hydration
    02_classify.ts      — classification spinner + badges
    03_topology.ts      — topology graph with corridor overlay
    04_investigate.ts   — investigator tool calls, streamed root-cause analysis, delegation to dispatcher
    05_delegate.ts      — dispatcher procedure, traffic, surveillance, participant, and push-action audit trail
    06_actions.ts       — 5 priority action cards that mirror dispatcher push_action calls
    07_precursor.ts     — precursor reveal and prevention narrative
```

### ATC TCAS Cascade — Content Summary

- **Spec**: `ATC_SCENARIO_SPEC.md`
- **Domain**: fictional public-demo air traffic control environment, with real ATC data disabled
- **Incident**: tracker v4.7.2 fusion regression creates ghost-driven STCAs, leading to avoiding action and coordinated TCAS RAs
- **Second-agent flow**: `ATC Dispatcher` must visibly populate chat with `search_procedures`, `find_traffic`, `find_surveillance`, `search_participants`, and `push_action` evidence before operator priorities appear
- **Regression coverage**: `e2e/atc-scenario.spec.ts` verifies the ATC roster, vocabulary, dispatcher tool evidence, and pushed priority actions

### Anonymisation Map

All content is fully fictional. Zero references to real power assets, operators, or regulations.

| Real | Fictional |
|------|-----------|
| AEMO | NGA (National Grid Authority) |
| NEM | NGM (National Grid Market) |
| NER (rules) | GOR (Grid Operating Rules), clauses `GOR 5.x.x` |
| FCAS | FRS (Frequency Response Service) |
| NOFB / NOFEB | SOFB / SOFEB |
| TNSP | RTO (Regional Transmission Operator) |
| FOS | GFS (Grid Frequency Standard) |
| "reviewable operating incident" | "reportable grid incident" |
| NER (region) | kept — fictional North-East Region |

---

## Adding a New Scenario

Before writing scenario code, read `SCENARIO_DESIGN.md`. It captures the scenario quality bar: detector-led premise, evidence-first tool flow, concise markdown chat, specialist handoff, executable priority actions, domain vocabulary, and focused verification.

1. Create `app/frontend/src/demo/scenarios/my_scenario/` with same structure as `ngm_busbar_trip/`
2. Default-export a `Scenario` object from `index.ts`
3. Add scenario-specific labels/units in `bootstrap.ts` as `kiosk_bootstrap.vocabulary` when the domain is not energy
4. Register in `app/frontend/src/demo/index.ts`:
   ```ts
   {
     id: "my-id",
     label: "My Label",
     industry: "My Industry",
     description: "...",
     load: makeLoader(() => import("./scenarios/my_scenario")),
   }
   ```
5. Deploy: `./deploy_kiosk.sh --yes`

### Scenario Formats

- **Split TS module** (recommended for >20 frames): directory with `index.ts` assembler + data files + `phases/*.ts`
- **Single JSON file** (fine for small/throwaway): one `.json` file, registered with `import("./scenarios/file.json")`

### Writing Frames

- Each frame has `id`, `transition_ms`, `patch` (one or more ops)
- Set `chapter` to start a new narration chapter (auto-pause in step mode)
- Set `narration` for presenter script overlay text
- Set `annotation` for an optional chapter spotlight when the Annotations toggle is on
- Use `ui.spotlight.set` / `ui.spotlight.clear` for mandatory spotlight beats that should ignore the Annotations toggle
- For streamed text: first `chat.append` with `text: ""`, then `chat.append_token` in subsequent frames
- For tool calls: `chat.append` with `tool_calls: [{id, name, arguments, status: "running"}]`, then `chat.update_tool` with `status: "complete"` + `result` in a later frame
- `transition_ms` controls pacing — token chunks use 60ms, tool results use 1500–2000ms

---

## Frontend Architecture (Kiosk-Relevant)

### Stores (Zustand)

| Store | Key state | Kiosk-relevant? |
|-------|-----------|-----------------|
| `chatStore` | messages per agent, streaming state | Yes — all chat ops target this |
| `agentStore` | agent roster, active agent | Yes — `agent.set_active`, bootstrap seeds agents |
| `situationStore` | situations list, classifications, scan state | Yes — scan/set/classify ops |
| `panelStore` | priority actions | Yes — `panel.priority_action.append` |
| `topologyStore` | topology graph, overlay | Yes — `topology.set` |
| `spotlightStore` | presentation spotlight target/caption | Yes — frame annotations and `ui.spotlight.*` ops |
| `vocabularyStore` | active domain vocabulary | Yes — scenario-specific labels/units/disclaimer text |
| `lookupStore` | dock agent threads | Yes — dock canned replies |
| `sessionStore` | session ID | Minimal — kiosk generates a fake session |
| `toastStore` | toast notifications | No |

### SituationCard Classification Gate

- **File**: `src/components/panels/SituationCard.tsx`
- When `IS_KIOSK === true`, the `useEffect` that calls `triggerClassify` (backend API) early-returns
- Classifications come from `kiosk_bootstrap.classifications` (pre-seeded on mount) or `panel.situations.classify` frame op
- Both write to `situationStore.classifications[situation_id]` with `status: "ready"`

### Domain Vocabulary Gate

- **File**: `src/stores/vocabularyStore.ts`
- `kioskBootstrap.ts` applies `BOOTSTRAP.vocabulary` on mount when present
- `demoPlayerStore.ts` applies `scenario.kiosk_bootstrap.vocabulary` before first frame render
- Scenarios without vocabulary reset to `ENERGY_VOCABULARY`
- Add a new vocabulary key by updating `DomainVocabulary`, `ENERGY_VOCABULARY`, then consuming it with `useVocab()` or `getVocab()`

### Tool Result Renderers

Registry: `src/components/chat/tool-renderers/index.ts`

| Renderer | Tools | Shape |
|----------|-------|-------|
| `TabularResult` | `find_alarms`, `find_scada`, `find_asset`, etc. | `{columns, rows}` |
| `GraphResult` | `graph_node`, `graph_neighbors`, etc. | JSON array of objects |
| `SearchResultCards` | `search_procedures`, `search_paws`, etc. | `[{doc_id, title, snippet}]` |
| `DelegationResult` | `delegate_to_agent` | markdown body + badge |
| `PanelToolSummary` | `push_action` | compact badge |
| `JsonFallback` | any unregistered | pretty-printed JSON |

- In kiosk scenarios, tool results are embedded as JSON strings in `chat.update_tool` patches
- New tool names render via `JsonFallback` automatically — no registration needed unless custom rendering is wanted

---

## Playwright E2E Tests

Browser tests against the **live deployed kiosk app**. Validates UI rendering, demo playback, panel hydration, and component behavior.

### Setup

```bash
cd app/frontend
npm install                                # if node_modules missing
npx playwright install chromium            # install browser
```

### Run

```bash
cd app/frontend
npx playwright test --project chromium --reporter=list           # all tests
npx playwright test benchmark- --project chromium                # all benchmarks
npx playwright test situation-equipment --project chromium       # single spec
```

### Config

- **File**: `app/frontend/playwright.config.ts`
- **APP_URL**: Defaults to production kiosk URL. Override: `APP_URL=http://localhost:5173`
- **Timeout**: 300s per test
- **Workers**: 1 (sequential)
- **Artifacts**: Screenshots + traces on failure → `test-results/`

### Auth Bypass

- **Fixture**: `e2e/fixtures.ts` — provides `authedPage` that intercepts `GET /api/auth_setup` → `{useLogin: false}`
- **Import**: `import { test, expect } from "./fixtures";` (NOT `@playwright/test`)

### Test Files

| File | What it tests |
|------|---------------|
| `e2e/benchmark-liapoota.spec.ts` | Canonical 8-phase investigation flow |
| `e2e/benchmark-belmont.spec.ts` | Belmont bus section trip |
| `e2e/benchmark-davenport.spec.ts` | Davenport transformer + bus trip |
| `e2e/benchmark-altona.spec.ts` | Altona bus + KTS line trip |
| `e2e/benchmark-templers.spec.ts` | Templers tee-line + BESS trip |
| `e2e/benchmark-kempsey.spec.ts` | Kempsey lines trip (data gap) |
| `e2e/delegation-streaming.spec.ts` | Delegation + saved session hydration |
| `e2e/situation-equipment.spec.ts` | Equipment enrichment + alarm/SCADA sub-lists |
| `e2e/situation-capacity.spec.ts` | Capacity UI + MW prompt |
| `e2e/grid-status-panel.spec.ts` | NEM dashboard + threat breakdown |
| `e2e/situation-alerts-ux.spec.ts` | Station grouping + filters |
| `e2e/situation-detector.spec.ts` | Situation detector API |
| `e2e/situation-frequency.spec.ts` | Frequency tracking |
| `e2e/topology-map.spec.ts` | Topology graph rendering |
| `e2e/lookup-dock.spec.ts` | Dock agent interactions |
| `e2e/tool-arg-streaming.spec.ts` | Tool argument streaming |
| `e2e/atc-scenario.spec.ts` | Header scenario picker, first-load picker hint, ATC scenario selection, full bootstrap hydration, dispatcher tools, and priority actions |

### Writing New Tests

- Use `authedPage` fixture (NOT raw `page`)
- Chat input: `page.getByPlaceholder("Send a message")`
- Wait for app: `await expect(page.locator("text=NEM GEM")).toBeVisible()`
- Use `data-testid` attributes — no CSS selector fragility
- Generous timeouts: demo playback takes 10-120s depending on scenario
- Screenshots: `await page.screenshot({ path: "test-results/name.png" })`

### Benchmark Phase Pattern

```
Phase 1: Message sent         → user bubble appears
Phase 2: Investigator streams → streaming dot on tab
Phase 3: Tool calls render    → collapsible cards in chat
Phase 4: Delegation fires     → delegate_to_agent card
Phase 5: Dispatcher tab       → SubagentTab in tab bar
Phase 6: Dispatcher streams   → tokens + tool calls
Phase 7: Priority actions     → cards in Operator Priorities panel
Phase 8: Complete             → streaming dots gone, content static
```

### Convention: UI Behavior Benchmarks

Every UI behavior change must be validated by a Playwright spec:

1. Write/update spec describing expected behavior → run → should FAIL
2. Implement the change
3. Deploy: `./deploy_kiosk.sh --yes`
4. Run spec again → should PASS
5. Debug failures via `test-results/` screenshots and traces

---

## Critical Gotchas

- **Classification type mismatch**: `kioskBootstrap.ts` `classification` field must be typed as `SituationClassification` (union), not `string`. Fixed 2026-04-20 — cast `seed.classification as SituationClassification`.
- **`ner_citation` field name**: The schema field is `ner_citation` (historical naming). Content references fictional GOR rules but the field name stays `ner_citation` to match `situationStore.ClassificationState`.
- **Scenario split vs single JSON**: Split TS modules use `makeLoader(() => import("./scenarios/dir"))`. Single JSON files use `makeLoader(() => import("./scenarios/file.json"))`. Both work — `makeLoader` calls `mod.default` + `assertScenario()`.
- **Registry `industry` is required**: Every `ScenarioListEntry` needs `industry` so the dropdown can group scenarios once more than one ships.
- **Scenario picker is persistent**: Do not replace it with a one-shot play button while playback runs. Keep `data-testid="scenario-picker"` and menu rows as `role="menuitem"`; tests depend on these stable selectors.
- **First-load picker hint**: `PlayDemoButton` owns the initial "Choose a scenario to trigger." coachmark. It should disappear once the picker opens or a scenario is loaded.
- **Vocabulary overrides are partial**: Do not copy the full energy vocabulary into a new scenario. Override only domain-specific keys; missing keys fall back automatically.
- **Selected scenarios need full bootstrap hydration**: `demoPlayerStore.loadScenario()` must call `applyKioskBootstrap()`, not just `setVocabulary()`. Otherwise scenario-specific chat agents, dock replies, and classifications are absent at playback time.
- **`nem_live_mw` field remains in NGM situations**: Some older comments mention `ngm_live_mw`, but current NGM situation payloads still use `nem_live_mw`. Frontend does not key on this field name.
- **Docker build strips `node_modules`**: `deploy_kiosk.sh` removes `app/frontend/node_modules/` before tar upload. Run `npm install` locally after deploy if needed.

---

## Azure Infrastructure

| Resource | Name |
|----------|------|
| Container App (kiosk) | `gridiq-v2` |
| Container App (production) | `pathfinderiq-aemo` |
| Container App (dev) | `gridiq-dev` |
| CAE | `cae-v2-ixksfd27yr7rc` |
| ACR | `crixksfd27yr7rc.azurecr.io` |
| Resource Group | `SAND-AISBX-MVP-POC-RG-AUE` |
| Subscription | `af9ce6a9-ce44-4ae1-ae22-35e0dd26c38b` |
| Managed Identity | `id-app-ixksfd27yr7rc` (client `6b24d9a9-0a04-4d22-b45e-39acfd29814b`) |

### Logs

```bash
# Kiosk (nginx — minimal)
az containerapp logs show --name gridiq-v2 --resource-group SAND-AISBX-MVP-POC-RG-AUE --follow

# Production (backend)
az containerapp logs show --name pathfinderiq-aemo --resource-group SAND-AISBX-MVP-POC-RG-AUE --follow
```

---

## Key Files

| File | Purpose |
|------|---------|
| `SCENARIO_DESIGN.md` | Skill-style scenario design guide for new GridIQ kiosk scenarios |
| `DEMO_SCENARIO_SPEC.md` | NGM busbar trip scenario design spec |
| `ATC_SCENARIO_SPEC.md` | Air Traffic Control scenario design, implemented at `atc_tcas_cascade` |
| `deploy_kiosk.sh` | Kiosk build + deploy script |
| `Dockerfile.kiosk` | Multi-stage MCR Node build → MCR nginx runtime, with build-time scenario/nginx smoke checks |
| `deploy/nginx.kiosk.main.conf` | nginx main config for MCR CBL-Mariner runtime images |
| `deploy/nginx.kiosk.conf` | nginx SPA server block and routing config |
| `azure_config.env` | Infra outputs (ACR, RG, subscription) |
| `app/frontend/src/demo/scenarioSchema.ts` | Scenario type definitions |
| `app/frontend/src/demo/index.ts` | Scenario registry |
| `app/frontend/src/demo/applyPatch.ts` | Patch op → store mutation dispatcher |
| `app/frontend/src/demo/kioskBootstrap.ts` | Store seeding on mount |
| `app/frontend/src/demo/framePlayer.ts` | Frame playback engine |
| `app/frontend/src/demo/kioskReplies.ts` | Dock agent canned reply engine |
| `app/frontend/src/demo/scenarios/ngm_busbar_trip/` | NGM busbar trip scenario (11 files) |
| `app/frontend/src/stores/situationStore.ts` | Situations + classifications state |
| `app/frontend/src/stores/chatStore.ts` | Chat messages + streaming state |
| `app/frontend/src/stores/vocabularyStore.ts` | Scenario vocabulary defaults and overrides |
| `app/frontend/src/stores/spotlightStore.ts` | Presentation spotlight state |
| `app/frontend/src/components/panels/SituationCard.tsx` | Situation card (kiosk-gated classify) |
| `app/frontend/src/components/chat/tool-renderers/index.ts` | Tool result renderer registry |
| `app/frontend/e2e/fixtures.ts` | Playwright auth bypass fixture |
| `app/frontend/playwright.config.ts` | Playwright config |

---

## Legacy Backend Reference

The production backend (`pathfinderiq-aemo`) is a separate deployment with live LLM agents, KQL tools, Gremlin graph, Cosmos sessions, and AI Search. It is **not used by the kiosk demo**. The kiosk replays pre-authored scenarios with zero network calls.

Backend documentation (SSE protocol, agent config, tool schemas, Cosmos sessions, benchmark suite) archived in git history prior to 2026-04-20.

---

## Planning Document Standard

- **Prose-adverse**: No paragraphs. No narrative. Bullets and numbered items only.
- **Detail-heavy**: Exact files, function signatures, field names, data shapes.
- **Requirement IDs**: `R1`, `C1`, etc. for cross-referencing.
- **Test-paired**: Every requirement has a corresponding test spec.
- **File change summary**: Table at end listing every file touched.

### Requirement Structure

```
## R1 — [Short title]

- **Current**: What exists now (file, line, behavior).
- **Required**: What must change. Exact fields, types, functions.
- **Files**: Every file that needs modification.

### Test: R1
- Test file and test name
- Setup steps (numbered)
- Assertions (bulleted, specific, observable)
```

---

## Development Workflow

### 1. Plan
- Write spec per Planning Document Standard
- Identify all files to touch before writing code

### 2. Implement
- Read every file before modifying
- One requirement at a time

### 3. Deploy
- `./deploy_kiosk.sh --yes`
- Verify no `tsc` errors in ACR build log

### 4. Test
- Run relevant Playwright specs: `cd app/frontend && npx playwright test <spec> --project chromium`
- All specs must PASS

### 5. Regression
- Run ALL related specs, not just the one changed
