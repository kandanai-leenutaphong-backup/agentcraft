# KIOSK_PORT_SPEC.md

Concrete porting spec: rebase kiosk frontend onto `gridiq_current_070526/app/frontend`.

- Source-of-truth new code: `~/CURRENT270425/gridiq_current_070526/app/frontend/`
- Current kiosk: `~/gridiq_public_kiosks/gridiq_global_kiosks/app/frontend/`
- Strategy: copy new `src/` → kiosk `src/`, then re-apply kiosk delta in place.

---

## 0. Glossary

- **NEW** = `gridiq_current_070526` (target baseline)
- **KIOSK** = `gridiq_global_kiosks` (current public demo)
- **PORTED** = the rebased kiosk after this spec executes
- **op** = scenario patch operation (key under `Frame.patch`)
- **vocab thread** = `useVocab(key)` call replacing a hardcoded string

---

## 1. Inventory — files moving where

### 1.1 Wholesale copy NEW → PORTED

```
src/App.tsx
src/api/*                               (incl. new auditApi.ts, scenariosApi.ts, summaryApi.ts; updated chatApi, classifyApi, sessionApi, situationApi, topologyApi, types.ts, client.ts)
src/auth/*                              (LoginScreen, authConfig, useAuth — kiosk diffs reapplied later)
src/components/chat/*                   (incl. updated AgentTabBar, ChatInput, ChatPanel, MessageBubble, MessageList, OverallExecutionTimer, ToolCallDisplay)
src/components/chat/tool-renderers/*    (10 new renderers + updates)
src/components/layout/*                 (incl. new HistoricalScenarioPicker; updated SavedSessionPicker)
src/components/lookup/LookupDock.tsx
src/components/panels/Workspace.tsx     (NEW; replaces CenterTabs)
src/components/panels/ClassifyVerdictCard.tsx        (NEW)
src/components/panels/SessionAuditPanel.tsx          (NEW)
src/components/panels/SignalEvidenceDisclosure.tsx   (NEW)
src/components/panels/SituationDetectorTuningPanel.tsx (NEW)
src/components/panels/SituationSummaryCard.tsx       (NEW)
src/components/panels/{Operating,Pinned,PriorityActions,SituationAlerts,SituationCard,SituationControl,PanelLayout}*.tsx (updated)
src/components/panels/__tests__/*
src/components/shared/*                 (incl. updated CommandPalette, DateRangePicker, HelpOverlay, MarkdownRenderer, ScanProgress, TeamsCallModal, Toaster, WindowMinutesDial, normalizeBullets)
src/components/topology/*               (updated)
src/features/*                          (chat, situation — escalationWatcher updated)
src/foundation/constants.ts             (re-merge IS_KIOSK)
src/hooks/*                             (updated)
src/lib/*                               (updated)
src/stores/agentStore.ts                (updated, similar API)
src/stores/auditStore.ts                (NEW)
src/stores/chatStore.ts                 (updated, 957 → 984 LOC; setMessages API preserved)
src/stores/lookupStore.ts               (updated)
src/stores/paletteStore.ts              (unchanged-ish)
src/stores/panelStore.ts                (266 → 504 LOC; updatePanel API preserved; centerTab expanded)
src/stores/placeholderStore.ts          (updated)
src/stores/sessionStore.ts              (updated)
src/stores/situationStore.ts            (236 → 1038 LOC; setState bypass still works)
src/stores/summaryStore.ts              (NEW)
src/stores/toastStore.ts                (unchanged)
src/stores/topologyStore.ts             (updated)
src/theme/*                             (updated)
src/utils/*                             (updated)
src/index.css                           (updated)
src/main.tsx                            (updated)
package.json                            (add @tailwindcss/container-queries; eslint v10; syntax-highlighter v16)
tailwind.config.js                      (updated)
postcss.config.js                       (unchanged)
vite.config.ts                          (updated)
tsconfig.json                           (updated)
playwright.config.ts                    (updated)
```

### 1.2 Kept from KIOSK (re-applied after copy)

```
src/demo/applyPatch.ts                  (extend dispatcher — see §3)
src/demo/scenarioSchema.ts              (add ops — see §3)
src/demo/framePlayer.ts                 (unchanged)
src/demo/demoPlayerStore.ts             (touch loadScenario for new stores reset)
src/demo/kioskBootstrap.ts              (extend seedKioskStores for audit/summary)
src/demo/defaultBootstrap.ts            (unchanged)
src/demo/kioskReplies.ts                (unchanged)
src/demo/index.ts                       (unchanged)
src/demo/scenarios/ngm_busbar_trip/**   (verify situations schema — see §6)
src/demo/scenarios/atc_tcas_cascade/**  (same)
src/components/demo/*                   (PlayDemoButton, NarrationOverlay, SpotlightOverlay, ChapterProgressBar, PlaybackControls, AutostepControl, DisclaimerButton)
src/components/kiosk/PasswordGate.tsx
src/stores/spotlightStore.ts
src/stores/vocabularyStore.ts
src/foundation/constants.ts             IS_KIOSK constant
.env.production has VITE_KIOSK_MODE=1   (kiosk build flag)
Dockerfile.kiosk
deploy_kiosk*.sh
deploy/nginx.kiosk*.conf
azure_config*.env
```

### 1.3 Dropped from KIOSK

```
src/components/panels/CenterTabs.tsx    (replaced by Workspace; test-ids preserved)
src/stores/replayStore.ts               (NEW lacks; defer until needed — see §9)
src/components/replay/*                 (defer)
src/features/replay/*                   (defer)
```

---

## 2. Store API compatibility — op-by-op

Confirmed by reading [stores/chatStore.ts L166-680](app/frontend/src/stores/chatStore.ts), [stores/panelStore.ts L239-495](app/frontend/src/stores/panelStore.ts), [stores/situationStore.ts L73-240](app/frontend/src/stores/situationStore.ts), [stores/topologyStore.ts L65-86](app/frontend/src/stores/topologyStore.ts), [stores/agentStore.ts L48-99](app/frontend/src/stores/agentStore.ts).

| KIOSK op | NEW store API hit | Compatible? | Notes |
|---|---|---|---|
| `chat.append` | `useChatStore.setMessages(agent, ApiMessage[])` | YES | Signature unchanged. Verify `ApiMessage` shape — see §5. |
| `chat.append_token` | same `setMessages` (parts: null forces re-derive) | YES | Same as above. |
| `chat.update_tool` | same `setMessages` | YES | Tool-call lookup by id unchanged. |
| `panel.priority_action.append` | `usePanelStore.updatePanel("update_priority_actions", {actions})` | YES | NEW retains `update_priority_actions` case. `PriorityAction` now has `action_id`, `step`, `status`, `pinned`. `normalizePriorityAction` adds defaults so existing scenario shape (`action`, `reasoning`, `guide`, `priority`, `contacts`, `sources`) still works. |
| `panel.situations.set` | `useSituationStore.setState({situations, loading: false, scanStartedAt: null, scanEstimateMs: null})` | PARTIAL | NEW store has `rawSituations` + derived `situations` (capped). Direct `setState` skips `rawSituations`. **Action**: set BOTH `rawSituations` and `situations` to the same list. SituationRecord schema gained fields — see §6. |
| `panel.situations.scan_start` | `setState({situations, loading: true, scanStartedAt, scanEstimateMs})` | PARTIAL | Add `rawSituations: []`. |
| `panel.situations.classify` | `setState({classifications})` | YES | `ClassificationState` shape compatible (adds optional `confidence`; legacy entries without it are fine — `status: "ready"`, `classification`, `ner_citation`, `rationale`). |
| `agent.set_active` | `useAgentStore.setActiveAgent(id)` | YES | Unchanged. |
| `topology.set` | `useTopologyStore.setState({...})` | YES | All fields still exist. |
| `topology.overlay.set` | `setState({overlay})` | YES | Unchanged. |
| `ui.spotlight.set` | `useSpotlightStore.setSpotlight(...)` | YES | spotlightStore re-added from KIOSK. |
| `ui.spotlight.clear` | `useSpotlightStore.clearSpotlight()` | YES | Same. |

### 2.1 New ops required (see §3)

NEW frontend gained surfaces with no current op. Add:

| New op | Target | Use case |
|---|---|---|
| `panel.summary.set` | `useSummaryStore.setState` | Demo summarizer card |
| `panel.classify_verdict.set` | `usePanelStore.updatePanel("update_classifier_verdict", ...)` or direct `set({classifyVerdict})` | Demo classify-verdict card |
| `panel.audit.set` | `useAuditStore.setState({report, reportSource: "live", status: "completed"})` | Demo audit report (optional — leave empty if scenarios don't use it) |
| `panel.center_tab.set` | `usePanelStore.setCenterTab(tab)` | Drive Workspace mode chips from frames |
| `panel.priority_action.set` | `updatePanel("update_priority_actions", ...)` | Replace full list (currently append-only) |
| `panel.priority_action.decision` | `usePanelStore.recordLocalPriorityActionDecision(action, status, note)` | Optional demo of operator decisions |

**Decision**: add `panel.center_tab.set`, `panel.summary.set`, `panel.classify_verdict.set` mandatory for Phase 1; the rest are Phase 2 if scenarios want them.

---

## 3. `applyPatch.ts` + `scenarioSchema.ts` extension

### 3.1 Schema additions

In `scenarioSchema.ts`:

```ts
import type { CenterTab } from "@/stores/panelStore";
import type { SummaryState } from "@/api/types";
import type { ClassifyVerdictState } from "@/stores/panelStore";

export interface CenterTabSetOp { tab: CenterTab; }
export interface SummarySetOp { summary: SummaryState | null; }
export interface ClassifyVerdictSetOp { verdict: ClassifyVerdictState | null; }

export interface FramePatch {
  // ...existing 12 ops...
  "panel.center_tab.set"?: CenterTabSetOp;
  "panel.summary.set"?: SummarySetOp;
  "panel.classify_verdict.set"?: ClassifyVerdictSetOp;
}
```

### 3.2 Dispatcher additions in `applyPatch.ts`

```ts
import { useSummaryStore } from "@/stores/summaryStore";

if (patch["panel.center_tab.set"]) {
  usePanelStore.getState().setCenterTab(patch["panel.center_tab.set"].tab);
}
if (patch["panel.summary.set"]) {
  const op = patch["panel.summary.set"];
  useSummaryStore.setState({
    summaryState: op.summary ?? EMPTY_SUMMARY_STATE,
    loading: false,
    error: null,
    streamingText: "",
  });
}
if (patch["panel.classify_verdict.set"]) {
  usePanelStore.setState({ classifyVerdict: patch["panel.classify_verdict.set"].verdict });
}
```

### 3.3 `panel.situations.set` patch — handle `rawSituations`

```ts
if (patch["panel.situations.set"]) {
  const op = patch["panel.situations.set"];
  useSituationStore.setState({
    rawSituations: op.situations as never,
    situations: op.situations as never,
    loading: false, error: null,
    scanStartedAt: null, scanEstimateMs: null,
  });
}
```

### 3.4 `resetDemoStores` — extend

```ts
useSummaryStore.getState().resetLocal();
useAuditStore.getState().reset();
useSituationStore.setState({
  rawSituations: [], situations: [], loading: false, error: null,
  classifications: {}, queryTimeMs: null, freqSummary: null,
  scanStartedAt: null, scanEstimateMs: null,
});
usePanelStore.setState({ classifyVerdict: null, pinnedStations: [] });
```

---

## 4. `IS_KIOSK` gate sites

Verified in KIOSK source. Re-apply to PORTED:

| File | Gate | Effect |
|---|---|---|
| `foundation/constants.ts` | `IS_KIOSK = !!import.meta.env.VITE_KIOSK_MODE` | Single source. |
| `App.tsx` | `if (IS_KIOSK) seedKioskStores(); else fetchAgents();` | Skip backend agent fetch. |
| `App.tsx` | `if (!IS_KIOSK) usePersistence();` | Skip localStorage backend sync. |
| `App.tsx` | `if (IS_KIOSK) return undefined;` inside escalationWatcher effect | Skip toast watcher. |
| `App.tsx` | Conditional `<SavedSessionPicker />`, `<HistoricalScenarioPicker />` hidden in kiosk; render `<PlayDemoButton />`, `<DisclaimerButton />` instead. | Header swap. |
| `App.tsx` | Mount `<ChapterProgressBar />`, `<NarrationOverlay />`, `<SpotlightOverlay />`, `<PlaybackControls />`, `<AutostepControl />` | Demo overlays. |
| `auth/useAuth.ts` | Short-circuit `useAuth` when `IS_KIOSK` — return `{isAuthenticated: true, user: null, login: noop, logout: noop}` | Or mount `<PasswordGate>` before app — choose one (see §7). |
| `auth/authConfig.ts` | Skip MSAL init when IS_KIOSK. | No Entra dependency in kiosk bundle. |
| `api/client.ts` | When IS_KIOSK, no-op all fetch calls or throw guarded errors. Existing pattern in KIOSK strips network entirely. | Confirm new `client.ts` integrates cleanly. |
| `components/panels/SituationCard.tsx` | Skip the `triggerClassify(id)` `useEffect` when IS_KIOSK. | Classifications come from `kiosk_bootstrap.classifications`. NEW `SituationCard` is 1064 LOC — find the classifier effect and add the early-return. |
| `components/chat/ChatInput.tsx` | Existing kiosk shim to route sends through `kioskReplies` for dock agents. Re-thread against NEW ChatInput. |
| `stores/chatStore.ts` | `sendMessage` branch that consults `kioskReplies` for dock agent ids. Re-apply against NEW chatStore. |
| `stores/topologyStore.ts` | `loadStation` short-circuit when graph already pre-loaded by `topology.set` and code matches `activeStation`. Re-apply. |
| `stores/lookupStore.ts` | Dock chat in-memory only — skip network. Re-apply. |
| `stores/summaryStore.ts` | Skip `streamSummary` API call when IS_KIOSK; just keep what `panel.summary.set` wrote. | Add new gate. |
| `stores/auditStore.ts` | Skip `streamAudit` SSE when IS_KIOSK. | Add new gate. |
| `components/panels/SituationDetectorTuningPanel.tsx` | Hide entire panel when IS_KIOSK, OR show read-only with seeded draft. | Phase-1 choice: hide (mode chip omitted from Workspace when IS_KIOSK). |
| `components/panels/SessionAuditPanel.tsx` | Same: hide or show pre-seeded report. | Phase-1: hide. |
| `components/layout/HistoricalScenarioPicker.tsx` | Hide in kiosk; replaced by `<PlayDemoButton />`. | App.tsx conditional. |
| `components/panels/Workspace.tsx` | Filter mode chips: omit `tuning` and `evaluations` when IS_KIOSK. | Single conditional on chip list. |

Total estimated touch: ~14 files for gates + 1 hidden mode chip.

---

## 5. `ApiMessage` and `ToolCall` schema check

`applyPatch.ts` constructs `ApiMessage`:
- `id, role, content, parts: null, status: "complete", tool_calls, agent_name, created_at`
- `_isDelegation?: true` (KIOSK extension)

Action: read NEW `api/types.ts` `ApiMessage` and `ToolCall` definitions; confirm field names. If NEW renamed `content → text` or `tool_calls → toolCalls`, update `buildMessage()` and `toToolCall()`.

`unknown:` — diff was 130 lines for `api/types.ts`. Likely added optional fields (delegation, audit metadata). Plan: read both files top-to-bottom and patch `buildMessage` to whatever NEW expects, keeping `_isDelegation` as a kiosk-private flag.

---

## 6. `SituationRecord` schema delta

Source diff: `api/situationApi.ts` grew 347 lines. New required-or-optional fields:

```
input_row_cap, max_alarm_rows, max_scada_rows  (request params — N/A for scenarios)
signal_evidence: string (JSON-encoded)
unit_offline_summary: { trip_count, cb_count, mwcc_count, kv_emer_count, score_contribution_total }
score_contributions: ScoreContribution[]
```

`SignalEvidenceDisclosure.tsx` (192 LOC) consumes `signal_evidence`. New `SituationCard` (1064 LOC) likely renders `score_contributions` and `unit_offline_summary` if present.

**Action**: regenerate or hand-edit each scenario's `situations.ts` to either:
1. Omit new fields (renderer must degrade gracefully — verify with empty fixture); OR
2. Add minimal `signal_evidence: "{}"`, `score_contributions: []`, `unit_offline_summary: {}`.

Phase-1: option 1 first; if `SignalEvidenceDisclosure` crashes on undefined, switch to option 2.

**Test**: render NGM `panel.situations.set` payload against new `SituationCard` in isolation (vitest) BEFORE wiring the full player.

---

## 7. Auth strategy in kiosk

NEW `App.tsx` reads `useAuth()` and renders user chip; on failure renders nothing. NEW `LoginScreen.tsx` exists.

Two paths:
- **A**: `IS_KIOSK` → `useAuth` returns `{isAuthenticated: false, user: null}` and `PasswordGate` mounts in `App.tsx` before `<AuthenticatedApp/>`. Matches current kiosk.
- **B**: Drop PasswordGate, accept open access. Simpler. Public demo URL is already public.

Recommendation: **A** — keep `PasswordGate` for parity. Add IS_KIOSK branch in `App` root:

```tsx
export default function App() {
  if (IS_KIOSK) {
    return (
      <PasswordGate>
        <AuthenticatedApp />
      </PasswordGate>
    );
  }
  // ... existing MsalAuthProvider / LoginScreen path
  return <AuthenticatedApp />;
}
```

---

## 8. Vocabulary re-threading

NEW frontend has no `vocabularyStore`. KIOSK threads `useVocab(key)` through ~18 files (App, ChatPanel, DisclaimerButton, SpotlightOverlay, CenterTabs, OperatingStatePanel, PanelLayout, SituationCard, CommandPalette, ScanProgress, EquipmentRow, StationNode, TopologyDetailPane, TopologyMap, kioskBootstrap, escalationWatcher, situationStore, vocabularyStore).

After copy, re-add `vocabularyStore.ts` verbatim, then re-thread:

| NEW file | Hardcoded strings to replace |
|---|---|
| `App.tsx` | "GridIQ" wordmark, "Ask GridIQ" → `useVocab("productName")` |
| `components/panels/PanelLayout.tsx` | Header captions, "Ask GridIQ" |
| `components/panels/Workspace.tsx` | Chip labels: hardcoded "Priorities", "Situation", "Status", "Topology", "Data Search", "Tuning", "Evaluations". Replace status chip with `useVocab("systemStatusLabel")`. Other labels remain English. |
| `components/panels/OperatingStatePanel.tsx` | Status panel heading |
| `components/panels/SituationCard.tsx` | "MW", classification authority, classification labels, "Classifying per NER 4.2.3…", facility terms, capacity/threat labels |
| `components/panels/SituationSummaryCard.tsx` | "Summary" → probably keep; check |
| `components/panels/ClassifyVerdictCard.tsx` | Verdict labels — vocab.classificationLabels |
| `components/panels/PriorityActionsPanel.tsx` | Empty text → `priorityEmptyText` |
| `components/chat/ChatPanel.tsx` | Empty-state description |
| `components/topology/*` | Facility/station nouns, primary unit |
| `components/shared/ScanProgress.tsx` | Rotating scan messages |
| `components/shared/CommandPalette.tsx` | Action labels for tabs |
| `features/situation/escalationWatcher.ts` | Toast copy |

Mechanical pass: grep each NEW component for `"MW"`, `"Grid"`, `"NER"`, `"station"`, `"alarms"`, `"SCADA"`, `"Frequency"`, `"Hz"`, replace with `useVocab(...)`. Estimated ~50 string sites.

---

## 9. Replay system — defer

KIOSK `replay/` reconstructs saved sessions for live-app re-watching. NEW frontend lacks it; the live app uses `SavedSessionPicker` instead.

Decision: drop replay from PORTED. The kiosk doesn't expose saved-session replay today in scenario flows; remove `replayStore`, `components/replay/`, `features/replay/`. Re-add later if needed.

---

## 10. Build & deploy delta

| File | Action |
|---|---|
| `Dockerfile.kiosk` | Verify Node 22 build image still matches NEW package.json. Strip dev deps from build. Unchanged otherwise. |
| `deploy_kiosk.sh` | Unchanged — still calls `az acr build` against the renamed `app/frontend`. |
| `deploy/nginx.kiosk.main.conf`, `nginx.kiosk.conf` | Unchanged. |
| `package.json` | Add `@tailwindcss/container-queries`. Bump syntax-highlighter to `^16`. Bump eslint to `^10`. Add `test:e2e` script. |
| `.env.production` | Add `VITE_KIOSK_MODE=1` if not already present. |
| `tailwind.config.js` | Pull NEW (adds container-queries plugin). Re-add any kiosk-specific theme tokens after merge. |

---

## 11. Test surface

### 11.1 Unit (vitest)

- `panel.situations.set` against new SituationCard rendering — no crashes on missing `signal_evidence`, `score_contributions`.
- `applyPatch` new ops: `panel.summary.set`, `panel.classify_verdict.set`, `panel.center_tab.set`.
- `vocabularyStore.setVocabulary` merge semantics (existing kiosk test).

### 11.2 Playwright (kiosk specs)

KIOSK has 17 specs. Map status after port:

| Spec | Risk | Action |
|---|---|---|
| `benchmark-altona/belmont/davenport/kempsey/liapoota/templers.spec.ts` | MEDIUM — assert situation card content; new fields may shift DOM | Re-record selectors; keep assertions on `data-testid` |
| `atc-scenario.spec.ts` | MEDIUM — vocabulary + dispatcher tools | Re-validate ATC vocab threading |
| `delegation-streaming.spec.ts` | LOW | data-testids preserved |
| `grid-status-panel.spec.ts` | LOW (NEM dashboard largely intact) | re-run |
| `lookup-dock.spec.ts` | LOW | LookupDock still mounts in `Workspace` "data" mode |
| `situation-*.spec.ts` (5 specs) | MEDIUM | depends on situationStore growth — may need fixture updates |
| `tool-arg-streaming.spec.ts` | LOW | chat-renderer changes only |
| `topology-map.spec.ts` | LOW | TopologyMap same shape |

NEW frontend has 24 specs — kiosk runs only the 17 currently bundled; backend-dependent specs (e.g. detector-tuning, summarizer-agent) are skipped in kiosk mode.

---

## 12. Migration order (concrete steps)

1. **Branch** kiosk: `git checkout -b modernize/rebase-2026-07`.
2. **Snapshot** kiosk delta: `mkdir -p /tmp/kiosk-delta && cp -r app/frontend/src/{demo,components/demo,components/kiosk,stores/vocabularyStore.ts,stores/spotlightStore.ts,foundation/constants.ts} /tmp/kiosk-delta/`.
3. **Wipe + copy** `app/frontend/src/` from NEW. Also overwrite `package.json`, `tailwind.config.js`, `vite.config.ts`, `tsconfig.json`, `index.html`, `e2e/fixtures.ts`.
4. **Restore** kiosk delta files into `src/` from `/tmp/kiosk-delta`.
5. **Patch `App.tsx`** — apply §4 gate sites + §7 PasswordGate wrap + mount demo overlays.
6. **Patch `foundation/constants.ts`** — re-add `IS_KIOSK`.
7. **Patch `applyPatch.ts` + `scenarioSchema.ts`** — apply §3 new ops + `rawSituations` fix.
8. **Patch `auth/`** — `useAuth` short-circuit for IS_KIOSK.
9. **Patch `api/client.ts`** — IS_KIOSK no-op shim (copy logic from KIOSK).
10. **Patch `stores/chatStore.ts`** — re-add `kioskReplies` branch in `sendMessage`.
11. **Patch `stores/topologyStore.ts`** — re-add `loadStation` pre-load cache hit.
12. **Patch `stores/summaryStore.ts`, `stores/auditStore.ts`** — IS_KIOSK guards on network calls.
13. **Patch `SituationCard.tsx`** — IS_KIOSK skip on classifier `useEffect`.
14. **Patch `Workspace.tsx`** — filter `tuning`/`evaluations` chips when IS_KIOSK.
15. **Patch `SituationDetectorTuningPanel.tsx`, `SessionAuditPanel.tsx`** — IS_KIOSK render guard.
16. **Re-thread vocabulary** — §8 mechanical pass. Run `grep "MW\|Grid\|NER"` to verify zero hardcoded domain strings in panels touched.
17. **Verify ApiMessage** — §5; patch `buildMessage` if needed.
18. **Verify scenario data** — §6; smoke-render NGM via vitest harness; patch situations if `SignalEvidenceDisclosure` crashes.
19. **Build local**: `cd app/frontend && npm install && npm run build`. Resolve TS errors. Verify NEW Tailwind v3 + container-queries plugin loads.
20. **Run kiosk locally**: `VITE_KIOSK_MODE=1 npm run dev`. Walk one scenario manually.
21. **Run e2e**: `APP_URL=http://localhost:5173 npx playwright test --project chromium`.
22. **Deploy preview**: `./deploy_kiosk.sh --build-only`, point a test Container App at the image, verify production parity.
23. **Cut over**: `./deploy_kiosk.sh --yes`.

---

## 13. Risk register

| Risk | Severity | Mitigation |
|---|---|---|
| `SituationCard` renderer expects fields scenarios don't supply | HIGH | §6 — vitest harness before player wiring |
| `ApiMessage` shape rename breaks scenario chat | MED | §5 — type-check during build |
| `Workspace` mode chip filtering accidentally hides "topology" or "data" in kiosk | LOW | E2E `benchmark-*` specs catch |
| Tailwind v3 + container-queries plugin breaks existing kiosk CSS | LOW | Local `npm run build` and visual diff |
| New `panelStore.priorityActionState` (decisions/timeline) breaks demo `update_priority_actions` payloads | MED | `normalizePriorityAction` defaults; supply minimal action shape; verify |
| NEW agents API expects different fetch shape | LOW | `seedKioskStores` writes agents directly; `fetchAgents` skipped under IS_KIOSK |
| `useAuth` MSAL init runs even under IS_KIOSK | MED | Confirm short-circuit; otherwise bundle pulls Entra deps unnecessarily |
| Bundle size grows (NEW has more panels) | LOW | NEW already production-built; size known |

---

## 14. Acceptance criteria

PORTED is shippable when:

- [ ] `VITE_KIOSK_MODE=1 npm run build` succeeds.
- [ ] App boots in browser with no network requests (DevTools Network panel empty after initial load).
- [ ] Header shows `productName` (NGM default) and `PlayDemoButton` + `DisclaimerButton`.
- [ ] Selecting NGM scenario plays end-to-end: scan spinner → situations → classifications → topology → chat investigate → delegate → priority actions → precursor reveal.
- [ ] Selecting ATC scenario re-skins vocab and plays end-to-end.
- [ ] No `vocabularyStore` reads return `undefined`.
- [ ] No console errors during scenario playback.
- [ ] All currently-passing kiosk Playwright specs pass (17 specs).
- [ ] `deploy_kiosk.sh --build-only` succeeds against `crixksfd27yr7rc.azurecr.io`.

---

## 15. Open questions

1. **RESOLVED** — `ApiMessage` + `ToolCall` identical kiosk → NEW. No `buildMessage()` patch needed.
2. `unknown:` — does NEW `SituationCard` crash on `signal_evidence: undefined`, or render fallback? **Action**: vitest harness in step 18.
3. **RESOLVED** — `PasswordGate` kept. App-root wrap as in §7 option A.
4. **RESOLVED** — Replay dropped. Rationale: feature was added for backend-loaded Cosmos sessions which kiosk never had; zero current scenarios use it; NEW frontend uses its own `SavedSessionPicker` path; 700 LOC maintenance cost.
5. **RESOLVED** — Phase 1: hide audit + tuning chips. Phase 2: pre-seed if stakeholder asks for tunability/audit-trail demo story.

---

## 16. Field map — kiosk scenario fixtures → NEW frontend

Verified by reading `api/situationApi.ts`, `api/types.ts`, `stores/panelStore.ts`, `stores/situationStore.ts`.

### 16.1 `SituationRecord` delta

**Unchanged (33 required fields, all retain shape):**
```
situation_id, window_start, window_end, station, severity, total_score,
alarm_score, scada_score, mw_boost, total_mw_lost, max_mw_drop,
alarm_count, step_changes, alarm_signals, scada_signals, alarm_mrids,
affected_tags, affected_equipment, patterns, pattern_details,
detected_at, detector_version, config_hash, station_region,
station_rated_mw, station_unit_count, region_rated_mw, region_live_mw,
nem_live_mw, impact_station_pct, impact_region_pct, impact_nem_pct
```

**Added (all optional):**
| Field | Type | Render surface | Phase-1 value |
|---|---|---|---|
| `signal_evidence` | `string` (JSON `SignalEvidence`) | `SignalEvidenceDisclosure.tsx` | `"{}"` |
| `unit_offline_summary` | `{trip_count?, cb_count?, mwcc_count?, kv_emer_count?, score_contribution_total?}` | `SituationCard` unit-trip rollup | `{}` |
| `score_contributions` | `ScoreContribution[]` | `SituationCard` "why scored" disclosure | `[]` |

**Deleted:** none.

**Nested types** (only if Phase-2 populated `signal_evidence`):
```ts
SignalEvidence = { alarm: Record<id, AlarmSignalEvidence>, scada: Record<id, ScadaSignalEvidence>, patterns: Record<id, PatternEvidence> }
AlarmSignalEvidence = { rule: AlarmSignalEvidenceRule, rows: AlarmEvidenceRow[], count: number }
ScadaSignalEvidence = { rule: ScadaSignalEvidenceRule, rows: ScadaEvidenceRow[], count: number }
AlarmSignalEvidenceRule = { id, col: "alarm_label"|"alarm_text"|"client_composite_id"|"priority", op: "=="|"contains", val, points, min_count?, extra_col?, extra_op?, extra_val? }
ScadaSignalEvidenceRule = { id, tag_contains: string[], meas, cond_type, threshold?, baseline?, direction?, points }
AlarmEvidenceRow = { timestamp_aest, alarm_label, alarm_text, priority, client_composite_id?, mrid? }
ScadaEvidenceRow = { timestamp_aest, TagId, measurement, Value, prev_val, abs_drop, pct_change }
ScoreContribution = { group: "alarm"|"scada"|"mw"|"pattern"|"frequency", signal_id, label, points, count?, evidence?: string[] }
```

### 16.2 `PriorityAction` delta

**Kiosk fields used by `panel.priority_action.append`:**
```
action, reasoning, guide, priority, contacts?, sources?
```

**Added in NEW (auto-defaulted by `normalizePriorityAction` — scenario need not author):**
| Field | Default |
|---|---|
| `action_id` | derived from arg hash + index |
| `step` | array index + 1 |
| `status` | `"pending"` |
| `pinned` | `false` |

**Deleted:** none.

### 16.3 `ApiMessage` + `ToolCall` delta

IDENTICAL. Re-verified at `api/types.ts:82-149` (NEW) vs `api/types.ts:77-145` (KIOSK). `_isDelegation` flag preserved.

### 16.4 `Session` delta

Added optional `summary_state?: SummaryState` and `priority_action_state?: PriorityActionState`. **No scenario impact** — kiosk never writes `Session` objects.

### 16.5 New top-level types (Phase-2 only)

**`SummaryState`** — see §3 `panel.summary.set` op. Shape:
```ts
SummaryState = {
  status: "idle" | "queued" | "running" | "error",
  current: SituationSummary | null,
  revisions: SummaryRevision[],
  processed_event_ids: string[],
  pending_event_ids: string[],
  last_error: string | null,
}
SituationSummary = { headline, bullets: string[], open_questions: string[], confidence: "low"|"medium"|"high", source_event_ids: string[], updated_at }
SummaryRevision = { revision_id, sequence, summary: SituationSummary, trigger_event_ids: string[], created_at }
```

**`ClassifyVerdictState`** — see §3 `panel.classify_verdict.set`. Shape:
```ts
{
  verdict: "credible_event" | "non_credible_event" | "non_event" | "indeterminate",
  justification: string,
  sources: string[],
  updated_at: string,
}
```
**Translation rule** from kiosk `kiosk_bootstrap.classifications.classification`:
- `"credible"` → `"credible_event"`
- `"non_credible"` → `"non_credible_event"`
- `"non_event"` → `"non_event"`

Add helper in `kioskBootstrap.ts`:
```ts
function toVerdictState(entry: SituationClassificationEntry): ClassifyVerdictState {
  const map = { credible: "credible_event", non_credible: "non_credible_event", non_event: "non_event" } as const;
  return {
    verdict: map[entry.classification] ?? "indeterminate",
    justification: entry.rationale,
    sources: [entry.ner_citation],
    updated_at: new Date().toISOString(),
  };
}
```

Call from `applyKioskBootstrap` for the first scenario classification (= session verdict).

### 16.6 `TopologyGraph` — `unknown:`

Diff `api/topologyApi.ts` before scenario regen. If new required fields exist on `center`/`neighbors`/`links`, append to kiosk `topology.ts` data. Action: step 6.5 (new): `diff api/topologyApi.ts` before step 7.

### 16.7 Deletions across all wire types

None. NEW is purely additive at the wire level.

---

## 17. Scenario regeneration plan (concrete)

### 17.1 Phase 1 — minimum viable port

Per scenario (`scenarios/ngm_busbar_trip/`, `scenarios/atc_tcas_cascade/`):

**`situations.ts`** — append three optional fields to each `SituationRecord`:
```ts
signal_evidence: "{}",
unit_offline_summary: {},
score_contributions: [],
```
Estimated edit: 5 situations × 3 fields × 2 scenarios = 30 line additions.

**`bootstrap.ts`** — no change required. Existing `classifications` + `vocabulary` + `main_agents` + `dock_agents` shape preserved.

**`phases/*.ts`** — no change required. Existing 12 ops compatible (with §3 `rawSituations` fix in the dispatcher).

### 17.2 Phase 2 — full evidence + verdict + summary narrative (optional)

**`situations.ts`** — populate `signal_evidence` and `score_contributions` from existing scenario alarm/SCADA narrative.

For NGM:
- Reuse `affected_equipment` decoded alarms as `AlarmEvidenceRow`s under one `"275kv_busfault"` signal id.
- Reuse `affected_equipment` SCADA step-changes as `ScadaEvidenceRow`s under `"voltage_collapse"` signal id.
- Add `score_contributions` for each: `{group: "alarm", signal_id, label, points: <scenario_score>, count}`.

Estimated: ~2 hr per scenario for hand-authored evidence.

**`bootstrap.ts`** — extend `applyKioskBootstrap` to set `panelStore.classifyVerdict` via `toVerdictState()` helper from the first situation's classification.

**`phases/06_actions.ts`** (or new `06b_verdict.ts`) — add one frame:
```ts
{ id: "f023a", chapter: "Verdict", narration: "Investigator's classification:",
  transition_ms: 1500,
  patch: { "panel.classify_verdict.set": { verdict: { verdict: "credible_event", justification: "...", sources: ["NER 4.2.3"], updated_at: "<iso>" } } } }
```

**`phases/08_summary.ts`** (NEW phase, optional) — hydrate the SituationSummaryCard:
```ts
{ id: "f033", chapter: "Summary", narration: "Operator brief delivered:",
  transition_ms: 2000,
  patch: { "panel.summary.set": { summary: { status: "idle", current: { headline: "275 kV busbar fault at MARRABEL_NX", bullets: [...], open_questions: [...], confidence: "high", source_event_ids: [], updated_at: "<iso>" }, revisions: [], processed_event_ids: [], pending_event_ids: [], last_error: null } } } }
```

### 17.3 Per-store reset on scenario change

`resetDemoStores` in `applyPatch.ts` extended (§3.4):
- `useSummaryStore.resetLocal()`
- `useAuditStore.reset()` (no-op when hidden)
- `useSituationStore.setState({rawSituations: [], situations: [], classifications: {}, ...})`
- `usePanelStore.setState({classifyVerdict: null, pinnedStations: []})`

---

## 18. Execution checks

1. `unknown:` — does NEW `SituationCard` (1064 LOC) render cleanly when `signal_evidence`, `score_contributions`, `unit_offline_summary` are absent? **Verify in step 18 (vitest harness).**
2. `unknown:` — `TopologyGraph` field additions. **Verify in step 6.5 (diff topologyApi.ts).**
3. `assumes:` — `windowMinutes` dial in `SituationControlBar` is irrelevant under kiosk; control bar likely needs IS_KIOSK gate to hide the dial when no scan is possible. **Add to §4 gate list during step 5.**

---

## 19. Pending Future Features + Decisions

Keep all non-blocking future decisions here. Do not let these block Phase 1 port.

### 19.1 Audit + tuning demo story

Decision now: hide `tuning` + `evaluations` Workspace chips under `IS_KIOSK`.

Future option: pre-seed both panels if demo narrative needs detector-tuning or compliance/audit-trail story.

Required work:
- Add `panel.audit.set` op.
- Add `panel.tuning.set` op or a read-only tuning-state seed.
- Author one canned audit report per scenario.
- Author one canned detector comparison per scenario.

### 19.2 Full signal evidence authoring

Decision now: Phase 1 scenario regeneration adds safe defaults:
```ts
signal_evidence: "{}",
unit_offline_summary: {},
score_contributions: [],
```

Future option: populate rich `signal_evidence` + `score_contributions` from scenario alarm/SCADA narrative.

Required work:
- NGM: map busbar alarms to `AlarmEvidenceRow[]`, voltage/current drops to `ScadaEvidenceRow[]`, precursor pattern to `PatternEvidence`.
- ATC: map surveillance/tracker events into scenario-compatible evidence buckets or extend vocabulary/types for aviation-specific evidence display.
- Add regression screenshots for expanded evidence disclosures.

### 19.3 Operator priority-action decisions

Decision now: operator decision state not part of Phase 1 scenario narrative. NEW `PriorityActionState` defaults empty.

Future option: show operator approving/declining actions during playback.

Required work:
- Add `panel.priority_action.decision` op.
- Map action lookup by `action_id` or `step`.
- Add frames such as "approve action 1" / "decline action 3".
- Extend e2e assertions for decision timeline.

### 19.4 Summary card narrative

Decision now: summary surface remains present but unseeded unless needed.

Future option: add `panel.summary.set` frames to hydrate `SituationSummaryCard` near scenario close.

Required work:
- Author one `SummaryState` per scenario.
- Add optional phase `08_summary.ts`.
- Assert card headline + bullet render in Playwright.

### 19.5 Replay system

Decision now: drop kiosk replay system during port.

Reason: current bundled scenarios use `demo/` frame playback, not saved-session replay; NEW frontend owns saved sessions via `SavedSessionPicker`; old replay layer adds ~700 LOC of maintenance for no active flow.

Future option: restore from git history only if a stakeholder asks for saved-session after-action playback in public kiosk.

Required work:
- Reconcile replay converter with NEW `ApiMessage`, `PriorityActionState`, and `SummaryState`.
- Add explicit route or Workspace mode for replay.
- Add e2e coverage.
