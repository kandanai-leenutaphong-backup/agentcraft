# KIOSK_UX_SPEC.md — Presentation, Adaptivity, and Direct Manipulation

Status: Spec — not yet implemented
Date: 2026-07-28
Scope: `app/frontend/` shell, demo player, and the `ngm-busbar-trip` scenario as the reference case
Supersedes: nothing. Complements `SCENARIO_DESIGN.md` (content quality bar) and `AUTODEV.md` (framework reference)

Goal: a futuristic, clean kiosk that tells the GridIQ story without a presenter, on a screen whose
size and aspect ratio are unknown until the morning of the event.

---

## 0. Verified baseline

Measured 2026-07-28 against the internal build
(`gridiq-internal.thankfuldesert-df64df28.swedencentral.azurecontainerapps.io`), energy scenario,
by DOM measurement and live capture. Not inferred from source.

### 0.1 Layout adaptivity

| Viewport | Ratio | Left px | Centre px | Chat px | Horizontal overflow |
|---|---|---|---|---|---|
| 1366 × 768 (laptop) | 16:9 | 337 | 608 | 405 | **125 px — broken** |
| 1920 × 1080 (reference) | 16:9 | 474 | 855 | 570 | 0 |
| 2560 × 1440 (QHD) | 16:9 | 638 | 1148 | 766 | 0 |
| 3440 × 1440 (ultrawide) | 21:9 | 858 | 1545 | 1030 | 0 |
| 1080 × 1920 (portrait kiosk) | 9:16 | 266 | 479 | 319 | **411 px — broken** |

- Columns are a fixed 25 / 45 / 30 percentage split at every size:
  [PanelLayout.tsx](app/frontend/src/components/panels/PanelLayout.tsx#L34).
- The entire `src/` tree contains **two** responsive utilities:
  [SituationDetectorTuningPanel.tsx](app/frontend/src/components/panels/SituationDetectorTuningPanel.tsx#L359)
  `xl:grid-cols-5` and [TopologyPanel.tsx](app/frontend/src/components/topology/TopologyPanel.tsx#L175)
  `hidden md:block`. No `matchMedia`, no container queries, no breakpoint ladder.
- `ResizeObserver` is used once, for topology fit:
  [TopologyMap.tsx](app/frontend/src/components/topology/TopologyMap.tsx#L358).
- At 1366 × 768 the header wraps into a four-line disclaimer blob, the `Next` button flex-grows into
  a full-width bar, the scenario chip clips at the right edge, and the playback bar overlaps the
  workspace.

### 0.2 Direct manipulation

| Capability | State | Evidence |
|---|---|---|
| Column resize | Works — `react-resizable-panels` `Separator` drag handles | [PanelLayout.tsx](app/frontend/src/components/panels/PanelLayout.tsx#L44) |
| Column size persistence | **Documented but not implemented.** The docstring claims "sizes persist to localStorage via `autoSaveId`"; no `autoSaveId` prop is passed to `Group`. | [PanelLayout.tsx](app/frontend/src/components/panels/PanelLayout.tsx#L14) |
| Priority action reorder | Button-only (`pin-action-N`, "Pin position"). No drag. | PriorityActionsPanel |
| Situation → chat drag | Does not exist | — |
| Topology pan/zoom | Works (React Flow). Loads at 30 % zoom with illegible labels; no fit-on-load, no reset. | TopologyMap |
| `framer-motion` | Installed, used in exactly one component | [Toaster.tsx](app/frontend/src/components/shared/Toaster.tsx#L9) |

### 0.3 Type scale cannot be density-scaled

[tokens.css](app/frontend/src/theme/tokens.css#L271) mixes units:

```
--font-size-micro:  10px      /* absolute */
--font-size-label:  11px      /* absolute */
--font-size-xs:     0.75rem   /* relative */
--font-size-sm:     0.875rem  /* relative */
...
```

A root-font-size density strategy scales five of eight steps and leaves badge and micro-label text
frozen. Any "scale up on a 4K kiosk" work is blocked until this is uniform.

### 0.4 Story choreography

- [03_topology.ts](app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/03_topology.ts#L31) fires
  `topology.set` only. The centre panel never switches, so the narrated graph is never shown. All
  three cyber scenarios do it correctly:
  [cyber 03_topology.ts](app/frontend/src/demo/scenarios/cyber_credential_dumping/phases/03_topology.ts#L14).
- Every investigator tool card and every `push_action` card renders collapsed. No frame op opens one.
  ~743 lines of authored tool payloads never reach the screen.
- Cold start leaves the chat column empty for ~16 s.
- Wall-clock timestamps ("Updated 9:28:00 AM", bubbles at "10:33 AM") render against a 2026-02-12
  11:15 incident.

---

## 1. Principles

1. **The screen is unknown.** Design for an aspect-ratio class, never a pixel width.
2. **The demo narrates itself.** If narration references a surface, a frame op must put that surface
   on screen. No presenter-dependent beats.
3. **Evidence over chrome.** Tool results and action reasoning are the product; presenter controls
   are scaffolding. Screen area allocates in that order.
4. **Direct manipulation where it earns its place.** Drag is for operator work, not for demo
   theatre. See §4 for what is explicitly refused.
5. **Restraint reads as futuristic.** Three motion moments, mono for all numerics, no emoji, no
   ambient animation.
6. **Kiosk mode subtracts.** Controls that cannot act must not render.

---

## 2. Workstream A — Story choreography

Highest value-to-effort ratio in the document. A1 and A2 are close to free.

| ID | Change | File | Accept |
|---|---|---|---|
| A1 | Add `"panel.center_tab.set": { tab: "topology" }` to the topology frame | [03_topology.ts](app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/03_topology.ts#L31) | Topology chapter shows the graph |
| A2 | Add `"panel.center_tab.set": { tab: "priorities" }` to the first action frame | [06_actions.ts](app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/06_actions.ts#L28) | Cards land on a visible panel |
| A3 | New op `chat.expand_tool` — opens a tool card by id | [applyPatch.ts](app/frontend/src/demo/applyPatch.ts#L121), [scenarioSchema.ts](app/frontend/src/demo/scenarioSchema.ts#L1) | Named tool card is expanded on screen |
| A4 | Expand one evidence card per investigation beat; collapse the previous | phases 04/05 | At most one open card at a time |
| A5 | Cold-open state: seed the operator prompt into chat at `f000a` instead of an empty column | [01_scan.ts](app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/01_scan.ts#L23) | No empty column at first paint |
| A6 | Scenario-clock timestamps. Replace `new Date()` in [05_delegate.ts](app/frontend/src/demo/scenarios/ngm_busbar_trip/phases/05_delegate.ts#L192) and drive card "Updated" stamps from a scenario `clock` field | scenarioSchema, panelStore, summaryStore | No wall-clock time on screen; screenshots reproducible |
| A7 | Re-pace: phase 8 tab dwell 4500 → 2000 ms; precursor punchline `f032` 200 → 4000 ms; scan hold 10000 → 5000 ms | phases 01, 07, 08 | Total ≈ 60 s, punchline is the longest single beat |
| A8 | Severity vocabulary alignment — narration says CRITICAL/MAJOR/SERIOUS/INVESTIGATE, panel renders Critical/Major/Minor/Minor | [situations.ts](app/frontend/src/demo/scenarios/ngm_busbar_trip/situations.ts#L162), vocabularyStore `classificationLabels` | Spoken and rendered labels match |

### A9 — Narration band

Current: floating overlay anchored bottom-centre of the centre column. It occludes action-card text
and sits on top of the MARRABEL topology node.

Target: a layout-reserved band, not an overlay.

- Grid row owned by the shell, height `clamp(72px, 8vh, 128px)`.
- Chapter title left (mono, uppercase, muted), script right (sans, `--font-size-base`).
- Never overlaps a panel. Hidden entirely when no scenario is playing — the row collapses to `0`.
- Presenter-only detail (frame id, elapsed) behind the presenter drawer (§5).

---

## 3. Workstream B — Adaptive layout

### B1. Aspect-ratio classes

Replace the fixed 25/45/30 split with a class resolved from viewport width **and** ratio. One hook,
one context value, consumed by the shell.

```ts
export type LayoutClass = "compact" | "standard" | "wide" | "ultrawide" | "portrait";

/** Resolved once per resize, debounced 120 ms, exposed via context. */
export function useLayoutClass(): {
  layout: LayoutClass;
  ratio: number;      // width / height
  density: "cosy" | "default" | "roomy";
};
```

| Class | Condition | Column model |
|---|---|---|
| `portrait` | ratio < 1.0 | Vertical stack: situation strip (fixed 22 vh) / workspace (flex) / chat (fixed 30 vh). Narration band pinned bottom. |
| `compact` | width < 1200 | Two columns: workspace + chat. Situations become an overlay drawer on a left edge rail. |
| `standard` | 1200 ≤ width < 1600 | Three columns 22 / 48 / 30. Left rail icon-compressed. |
| `wide` | 1600 ≤ width < 2400, ratio < 2.0 | Three columns 25 / 45 / 30 (today's reference). |
| `ultrawide` | ratio ≥ 2.0 or width ≥ 2400 | Four columns: situations / workspace / **evidence** / chat. Evidence column hosts the expanded tool result so the chat stops scrolling it away. |

The `ultrawide` evidence column is the payoff: on a 21:9 event screen the demo stops looking like a
stretched 16:9 layout and starts using the extra width for the thing the story is about.

### B2. Overflow is a defect

- Root shell gets `min-width: 0` discipline and `overflow-x: hidden` at the app frame.
- A regression test asserts `document.body.scrollWidth <= window.innerWidth` at all five viewports
  in the §0.1 table. Currently fails at two of five.

### B3. Density scaling

- Normalise [tokens.css](app/frontend/src/theme/tokens.css#L271): every `--font-size-*` becomes
  `rem`. `micro` → `0.625rem`, `label` → `0.6875rem`.
- Root font size by density: `cosy` 14 px, `default` 16 px, `roomy` 18 px.
- `roomy` selected when width ≥ 2400 **or** the shell detects a viewing-distance hint
  (`?density=roomy` query param for event operators).
- Spacing scale follows the same rem base so padding tracks type.

### B4. Header

Current failure at 1366: the disclaimer pill wraps to four lines, `Next` flex-grows into a bar, the
scenario chip clips.

- Header becomes a three-slot grid: wordmark (fixed) / presenter cluster (collapsible) / scenario +
  disclaimer (fixed, right).
- Presenter cluster collapses to a single icon button below `standard`.
- Disclaimer pill: fixed single-line chip with a tooltip, never a wrapping paragraph.
- No flex-grow on transport buttons.

### B5. Topology

- `fitView` on payload load, with `maxZoom: 1.0` and padding `0.15` — never open at 30 %.
- Hub-and-spoke layout centred on the incident station, replacing the vertical stack. The narration
  says "the KETTERING link out to the right"; the layout should honour that.
- Edge width and colour encode `% thermal`. "710 MW, 89 % thermal" becomes visible, not spoken.
- De-energised equipment renders desaturated with a dashed outline.
- Detail pane: `hidden md:block` becomes a bottom sheet in `portrait` and `compact` rather than
  disappearing.

---

## 4. Workstream C — Direct manipulation

### C1. Build

| ID | Interaction | Rationale | Gate |
|---|---|---|---|
| C1a | Pass `autoSaveId="gridiq-workspace"` to `Group` | The docstring already promises this and it does not work. One line. | always |
| C1b | Double-click a `Separator` to reset that boundary to its default | Recovery from an over-dragged column with no menu dive | always |
| C1c | Keyboard resize on focused separator (`←`/`→` = 2 %, `Home` = reset) | Accessibility; separators are currently mouse-only | always |
| C1d | Drag a situation row onto the chat panel to start an investigation | Highest-value new drag: it makes agency visible. Chat panel shows a drop target with the resolved prompt. | `!IS_KIOSK` |
| C1e | Drag-reorder priority action cards | Natural upgrade of the existing `pin-action-N` buttons. Keyboard equivalent required (`Space` to lift, arrows to move). | `!IS_KIOSK` |
| C1f | Topology: drag to pan, wheel to zoom, `F` to fit, double-click node to focus | Already partly present; formalise and document the shortcuts | always |

Drag implementation constraint: no new dependency. `react-resizable-panels` covers C1a–C1c; C1d and
C1e use native HTML5 drag events with a pointer-event fallback. `framer-motion` is already a
dependency used once — either adopt it for the drag ghost and the three motion moments (§6) or drop
it from `package.json`. Do not leave it half-used.

### C2. Refuse

| Refused | Reason |
|---|---|
| Draggable / floating panels | A kiosk that can be dragged into an unrecoverable state before a demo is a liability. Fixed regions, resizable boundaries only. |
| Drag-to-rearrange columns | Same. The column order is part of the story grammar (input → work → agent). |
| Draggable narration band | It should not overlap anything, so there is nothing to drag it away from. Fix the layout instead (§A9). |
| Drag interactions inside scripted playback | A canned replay cannot demonstrate a drag without a synthetic cursor, and a synthetic cursor reads as a fake. Drag is operator-mode only. |

### C3. Kiosk-mode subtraction

Gate on `IS_KIOSK` ([constants.ts](app/frontend/src/foundation/constants.ts)) — these currently
render and cannot act:

- Scan button and the three tuning dials (Window / Max Alarms / Max SCADA) in `SituationControlBar`
- Per-station `pin-station-*` and `investigate-station-*` buttons
- "N critical actions — tap to bring to top" banners in `PriorityActionsPanel`
- "New Chat" / "Clear session" in the agent tab bar
- Chat composer (or make it a labelled decorative affordance, not a live input)

Recovers roughly the top third of the left column and removes every dead-end click.

---

## 5. Workstream D — Presenter chrome

Current: nine header controls plus a thirteen-control bottom bar (Restart / Chapter / End / eight
speed buttons / Narration). Scaffolding outweighs product surface.

- Visible at all times: scenario picker, play/pause, chapter position (`4 / 15`).
- Everything else moves into a presenter drawer, opened by `P` or a single header icon.
- Full keyboard map, documented in the drawer: `Space` next, `←`/`→` prev/next, `1`–`9` speed,
  `R` restart, `E` end, `N` narration, `A` annotations, `P` drawer.
- Drawer state is not persisted — every session opens clean.

---

## 6. Visual language

- **Motion budget: three moments.** Scan sweep, classification verdict landing, precursor spotlight.
  Everything else static. Existing `highlight-pulse` / `fly-from-origin` keyframes
  ([index.css](app/frontend/src/index.css#L202)) are retained only for these.
- **Mono for every numeric.** `--font-mono` already carries Grid Status. Extend to situation scores,
  MW deltas, timestamps, topology node values, tool durations.
- **No emoji.** Replace 🏭 📅 ⚡ 📊 🔎 👥 in tool-call headers with the Lucide set used everywhere
  else.
- **Anonymisation is a visual rule.** `NSW`/`VIC`/`QLD`/`SA`/`TAS` and `NEM.*` tag names currently
  render on Grid Status ~90 s after the "everything is fictional" opening line. Region model becomes
  `EHR`/`NER`/`WER`/`NOR` in [gridStatus.ts](app/frontend/src/demo/scenarios/ngm_busbar_trip/gridStatus.ts#L70).
- **One MW figure.** 430 (card), 412 (chat), 442 (Grid Status hero) are simultaneously reachable.
  430 is arithmetically load-bearing — `impact_station_pct 43.0` and `impact_region_pct 6.9` both
  derive from it. Adopt 430 everywhere; 442 stays only if explicitly labelled as the five-situation
  sum.

---

## 7. Framework additions

```ts
/* scenarioSchema.ts */
interface ExpandToolOp { agent: string; id: string; expanded: boolean }
interface FramePatch { "chat.expand_tool"?: ExpandToolOp; /* ...existing */ }

/** Scenario-owned clock. All rendered timestamps derive from this, never Date.now(). */
interface Scenario { clock?: { start: string; tz: string } }

/** Load-time guard. Duplicate ids are currently silent — ATC ships five. */
export function assertUniqueFrameIds(frames: Frame[]): void;
```

`assertUniqueFrameIds` is called from `assertScenario`. The shipped ATC scenario generates
`f003…f025` from 23 tools while hardcoding `f013`–`f017` in the same array
([04_tool_suite.ts](app/frontend/src/demo/scenarios/atc_tcas_cascade/phases/04_tool_suite.ts#L178)).

---

## 8. Verification

### 8.1 Adaptive matrix — new spec `e2e/layout-adaptive.spec.ts`

For each of 1366×768, 1920×1080, 2560×1440, 3440×1440, 1080×1920:

1. `document.body.scrollWidth <= window.innerWidth`
2. Header renders on one line; scenario chip fully within viewport
3. Narration band does not intersect any panel bounding box
4. Expected `LayoutClass` is applied (`data-layout-class` on the shell)
5. No text node clipped (`scrollWidth > clientWidth` on any leaf)

### 8.2 Story guard — new spec `e2e/ngm-scenario.spec.ts`

The energy scenario is the largest, is the vocabulary default, and is currently the only major
scenario with no e2e guard.

1. Picker → `NGM Busbar Trip`; exactly one agent tab (`GridManager`), no dispatcher tab
2. Topology chapter → `center-tab-body-topology` visible, `MARRABEL_NX` centred
3. Action chapter → `center-tab-body-priorities` visible, five cards, P5 first
4. At least one tool card expanded during the investigation chapter
5. Single MW figure regex across card + chat + registry description
6. No `/\d{1,2}:\d{2}:\d{2}\s?(AM|PM)/` wall-clock text anywhere
7. No `/\bNSW\b|\bVIC\b|\bQLD\b|\bTAS\b|NEM\./` in rendered text

### 8.3 Interaction

Unit tests for `useLayoutClass` boundaries; component test for separator keyboard resize; a
`localStorage` round-trip test for `autoSaveId`.

---

## 9. Sequencing

| Tranche | Contents | Why first |
|---|---|---|
| 1 | A1, A2, A6, C1a, §6 anonymisation + MW | Near-zero cost, removes every audience-visible contradiction |
| 2 | 8.2 story guard spec | Lock the fixed behaviour before refactoring |
| 3 | A3, A4, A9 | Evidence reaches the screen; narration stops occluding |
| 4 | B1, B2, B3, B4 | Adaptive shell; unblocks unknown-screen deployment |
| 5 | B5 topology, A7 pacing, §6 motion/mono/icons | Visual quality pass |
| 6 | C1b–C1f, C3, §5 drawer | Interaction polish |

Tranche 4 is the largest and should not start before tranche 2 exists.

---

## 10. Out of scope

- Backend or live-data work of any kind. The kiosk stays a static replay.
- Touch gestures. Event kiosks here are screen-and-presenter, not touch. Revisit if a touch panel
  is confirmed.
- Mobile viewports below 768 px. `portrait` targets a rotated 1080×1920 display panel, not a phone.
- Theming beyond the existing token file. One dark control-room scheme.
