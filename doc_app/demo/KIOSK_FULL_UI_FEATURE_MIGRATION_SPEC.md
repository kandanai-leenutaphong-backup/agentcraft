# KIOSK_FULL_UI_FEATURE_MIGRATION_SPEC.md

Purpose: show every meaningful UI feature from the main GridIQ frontend in kiosk demo mode with spoofed but convincing values for both scenarios.

Source UI baseline: `/home/hanchoong/CURRENT270425/gridiq_current_070526/app/frontend/src`

Target kiosk: `/home/hanchoong/gridiq_public_kiosks/gridiq_global_kiosks/app/frontend/src`

Scenarios:
- NGM Busbar Trip — energy customer demo.
- ATC TCAS Cascade — aviation demo, domain-relabelled where appropriate.

Non-goal:
- No backend calls.
- No fake generic JSON blobs where a typed renderer exists.
- No UI surface left in empty state after the relevant scenario beat.

---

## 1. Migration Principle

Each main-codebase UI surface gets one of three treatments:

| Treatment | Meaning | Example |
|---|---|---|
| Direct reuse | Same domain, same UI, spoofed data | `GridStatusPanel` for NGM |
| Domain-specific peer | Same design spirit, different operational grammar | `AirspaceStatusPanel` for ATC |
| Hidden/seeded surface | Backend-driven surface is visible with kiosk-local report/state | `SessionAuditPanel`, `SituationDetectorTuningPanel` |

Rule: component should look like production GridIQ, but data comes from scenario TS modules.

---

## 2. Required Scenario Ops

Current kiosk ops are insufficient for full UI coverage. Add these ops to `demo/scenarioSchema.ts` + `demo/applyPatch.ts`.

### 2.1 Status Ops

```ts
"panel.situations.set": {
  situations: SituationRecord[];
  grid_status?: GridStatus | null;
  airspace_status?: AirspaceStatus | null;
}
```

Already partly present. Keep it.

### 2.2 Detector Tuning Ops

```ts
"panel.detector_config.set": {
  detectorConfig: DetectorConfigResponse;
  detectorDraft?: DetectorConfigPatch;
  detectorDirty?: boolean;
  detectorComparison?: DetectorComparisonResult | null;
}

"panel.detector_config.preview": {
  detectorDraft: DetectorConfigPatch;
  detectorComparison: DetectorComparisonResult;
  situations?: SituationRecord[];
}
```

Store target:
```ts
useSituationStore.setState({ detectorConfig, detectorDraft, detectorDirty, detectorComparison })
```

Purpose:
- Populate `SituationDetectorTuningPanel` without backend.
- Show control dials, signal rules, comparison rows, draft/apply states.

### 2.3 Audit Ops

```ts
"panel.audit.set": {
  status: "completed" | "running";
  auditId: string;
  report: AuditReport;
  streamEvents?: AuditStreamEvent[];
  partialNarration?: string;
}
```

Store target:
```ts
useAuditStore.setState({
  status,
  auditId,
  report,
  reportSource: "live",
  streamEvents: streamEvents ?? [],
  partialNarration: partialNarration ?? "",
  error: null,
})
```

Purpose:
- Populate `SessionAuditPanel` with a believable hidden-auditor report.
- Show rubric, gaps, improvements, tool stream cards.

### 2.4 Data Search Seed Op

```ts
"dock.thread.set": {
  agent: string;
  messages: ApiMessage[];
}
```

Store target:
```ts
useChatStore.getState().setMessages(agent, messages)
```

Purpose:
- Data Search tab should not sit at welcome-only state.
- Scenario can show a preloaded exchange with tool cards and answers.

### 2.5 Center Tab Op

Already present:
```ts
"panel.center_tab.set": { tab: CenterTab }
```

Use to show every tab during playback:
- `priorities`
- `status`
- `topology`
- `data`
- `tuning`
- `evaluations`

Kiosk currently hides `tuning` and `evaluations`; for full UI demo, unhide them when seeded demo data exists.

---

## 3. Main UI Surfaces To Cover

### 3.1 Situation Alerts Panel

Source:
- `components/panels/SituationAlertsPanel.tsx`

Must show:
- Station accordion grouping.
- Severity filter pills.
- Station text filter.
- Row-level situation table.
- Row expansion into embedded `SituationCard`.
- Manual pin station icon.
- Station investigate icon.
- Scan progress state.
- Empty state before scan.

Demo requirements:
- At least 4 station groups.
- At least 1 station with 2 situations.
- At least 1 Critical, 1 Major, 2 Minor/Investigate rows.
- Top-level station headers must be clean: severity + station only.
- Child rows keep time windows, equipment, severity, score.

NGM values:
- `MARRABEL_NX`: Critical + Minor precursor.
- `KETTERING_NX`: Major.
- `GLENRIDGE_NX`: Minor/normal response.
- `OAKBANK_NX`: Minor/credible transformer trip.

ATC values:
- `METROFIELD_APP`: Critical + precursor.
- `NORTHGATE_TWR`: Major runway suspension.
- `EASTVALE_CTR`: Minor flow restriction.
- `CROSSWIND_TWR`: Minor diversion standby.

---

### 3.2 Situation Card + Signal Evidence

Source:
- `components/panels/SituationCard.tsx`
- `components/panels/SignalEvidenceDisclosure.tsx`
- `lib/situationRecord.ts`

Must show:
- Classification/credibility subpanel.
- Investigate subpanel.
- Score breakdown / why scored.
- Affected equipment expansion.
- Alarm rows.
- SCADA rows.
- Alarm signal chips expanding to rule + matched rows.
- SCADA signal chips expanding to rule + matched rows.
- Pattern evidence expansion.
- Unit/offline summary where relevant.
- Topology link/focus actions.
- Contacts/Teams modal where available.

Data requirements per high-priority situation:
```ts
signal_evidence: JSON.stringify({
  alarm: {
    bus_diff: {
      rule: { id: "bus_diff", col: "alarm_label", op: "contains", val: "BUS DIFF", points: 4 },
      rows: [...],
      count: 2,
    },
  },
  scada: {
    bus_collapse: {
      rule: { id: "bus_collapse", tag_contains: ["B275"], meas: "KV", cond_type: "drops_below", threshold: 20, points: 4 },
      rows: [...],
      count: 3,
    },
  },
  patterns: {
    busbar_fault: { id: "busbar_fault", details: { support: "bus diff + earth fault + voltage collapse" } },
  },
})
score_contributions: [
  { group: "alarm", signal_id: "bus_diff", label: "Bus differential", points: 4, count: 2 },
  { group: "scada", signal_id: "bus_collapse", label: "Bus voltage collapse", points: 4, count: 3 },
]
```

NGM must populate:
- `ngm-crit-1`: bus differential, CB trip, earth fault, bus voltage collapse, generator MW drops.
- `ngm-pre-1`: transient kV dip, sub-threshold no alarm, pattern evidence.
- `ngm-maj-1`: thermal advisory + flow surge.
- `ngm-inv-1`: transformer trip / load redistribution.

ATC must populate aviation-equivalent evidence:
- `atc-crit-1`: STCA, TCAS RA, fused ghost track, ADS-B disagreement.
- `atc-pre-1`: 12-second ghost track, no STCA.
- `atc-maj-1`: runway suspension, rate drop.
- `atc-ser-1`: APW/flow restriction, holds.

Even though field names are `alarm`/`scada`, labels should render via vocabulary/tool names.

---

### 3.3 Status Tab

#### NGM: Grid Status

Source:
- `components/panels/GridStatusPanel.tsx`
- `components/panels/GridStatusSummaryPanel.tsx`

Treatment:
- Direct reuse.

Must show:
- NEM frequency hero.
- NEM reserve hero.
- NEM generation/renewable hero.
- Threatened MW hero.
- Per-region grid.
- Severity distribution.
- Top threats table.
- Data-quality footer.

NGM spoof values:
- Frequency: `49.71-50.06 Hz`, worst band `network`, worst region `NSW`.
- Reserve: `2510 MW`.
- Threatened: `442 MW`, `1.8% generation`, `5 sit`.
- NSW row: `8240 MW gen`, `7890 MW demand`, `680 MW reserve`, `430 MW threat`.
- Data-quality: warning `FREQ_EXCURSION`, info `DEMO_SYNTHETIC`.

#### ATC: Airspace Status

Source:
- custom peer component `AirspaceStatusPanel.tsx`.

Treatment:
- Domain-specific peer.

Must show:
- Separation hero: `1 RA`, `3 STCA`, `2 APW`.
- Surveillance hero: `FUSED DEGRADED`, `ADS-B nominal`, `2 ghost`.
- Runway hero: `27L hold`, `27R open`, `75% recovery`.
- Flow hero: `2 holding`, `4 resequenced`, `14 min delay`.
- Facility matrix: `METROFIELD_APP`, `NORTHGATE_TWR`, `EASTVALE_CTR`, `CROSSWIND_TWR`.
- Evidence chips: fused replay, ADS-B truth-track, Mode S state, change log, audio pending, MOR package open.

No MW/frequency/NEM language in ATC status.

---

### 3.4 Priority Actions Panel

Source:
- `components/panels/PriorityActionsPanel.tsx`
- `components/shared/TeamsCallModal.tsx`

Must show:
- Summary card above actions.
- Classify verdict card above actions.
- Pending actions.
- Completed actions.
- Priority badges.
- Guide disclosure.
- Why/reasoning disclosure.
- Sources.
- Contacts.
- Pin action control.
- Decision form, completed/declined states.
- Timeline state if possible.

NGM values:
- 5 actions from existing busbar scenario.
- Mark first two pending, one completed, one declined/blocked, one standard follow-up.
- Contacts: MARRABEL Station Manager, EHRT Protection, KETTERING Control, Generation Controller, Market Operator.

ATC values:
- 2 actions only, per current narrative:
  1. Resequence and hold 27L arrivals.
  2. Preserve fused/ADS-B replay, Mode S state, audio, change log.
- Include contacts: METROFIELD Watch Supervisor, Surveillance Systems Engineer.
- Add one completed state during later frame if demo needs decision UI.

Required new op for decision demo:
```ts
"panel.priority_action.decision": {
  action_id?: string;
  step: number;
  status: "completed" | "declined";
  note: string;
}
```

---

### 3.5 Summary Card

Source:
- `components/panels/SituationSummaryCard.tsx`
- `stores/summaryStore.ts`

Must show:
- Empty state before evidence.
- Streaming state at least once in playback.
- Final headline + bullets.
- Open questions.
- Updated timestamp.

Required ops:
```ts
"panel.summary.stream": { text: string }
"panel.summary.set": { summary: SummaryState }
```

NGM final summary:
- Headline: `MARRABEL_NX busbar fault drove 430 MW threatened/lost generation and regional frequency stress.`
- Bullets:
  - Bus 275-1 de-energised after bus differential + DS-275-13 earth-fault indications.
  - Units 3/4 disconnected; Unit 1 remained stable on Bus 275-2.
  - KETTERING/OAKBANK are downstream consequences.
- Open question: confirm DS-275-13 physical mechanism.

ATC final summary:
- Headline: `TCAS RA was real; first STCA geometry was fused-track only.`
- Bullets:
  - XKL-417/ZQM-205 generated coordinated RA.
  - ADS-B does not support first two STCA geometries.
  - Two operator actions cover recovery + evidence preservation.
- Open question: confirm v4.7.2 root cause.

---

### 3.6 Classification Card

Source:
- `components/panels/ClassifyVerdictCard.tsx`

Must show:
- Empty state before classification tool.
- Tool call card for `classify` / domain display name.
- Final panel verdict.

NGM:
```ts
verdict: "non_credible_event"
label: "NON-CREDIBLE"
justification: "Simultaneous loss of two generating units through a shared 275 kV busbar fault exceeds the single-element credible-contingency boundary."
```

ATC:
```ts
verdict: "credible_event"
label: "CREDIBLE"
justification: "Coordinated TCAS RA occurred, 27L arrivals were suspended, and ADS-B disagreed with initial fused-track STCA geometry."
```

---

### 3.7 Data Search Assistant

Source:
- `components/lookup/LookupDock.tsx`
- `stores/lookupStore.ts`
- `stores/chatStore.ts`

Must show:
- Data Search tab populated with a conversation, not only welcome text.
- User query.
- Assistant answer.
- At least 2 tool cards rendered inside dock thread.
- Domain-specific reply labels.

Required op:
```ts
"dock.thread.set": { agent: string; messages: ApiMessage[] }
```

NGM dock conversation:
1. User: `Show MARRABEL alarms around 11:15 and the Bus 275-1 voltage drop.`
2. Tool cards:
   - `find_alarms` -> table of bus diff / CB trips / earth fault.
   - `find_scada` -> voltage and generator MW drops.
3. Assistant: concise answer with key rows and next lookup suggestions.

Second NGM query:
1. User: `Any precursor pattern on the same bus?`
2. Tool card:
   - `pattern_history` or active equivalent -> transient kV dip.
3. Assistant: 10:38 transient summary.

ATC dock conversation:
1. User: `Show fused vs ADS-B evidence for METROFIELD_APP.`
2. Tool cards display names:
   - `read_surveillance_feed`
   - `replay_alert_timeline`
3. Assistant: fused ghost / ADS-B disagreement summary.

Second ATC query:
1. User: `Which procedures and participants are relevant?`
2. Tool cards:
   - `search_atc_procedures`
   - `search_safety_clues`
3. Assistant: SOP + watch supervisor + surveillance engineer.

---

### 3.8 Session Audit Panel

Source:
- `components/panels/SessionAuditPanel.tsx`
- `stores/auditStore.ts`
- `api/auditApi.ts`

Kiosk state:
- Currently backend-only. Must seed with scenario data.

Required op:
```ts
"panel.audit.set": {
  status: "completed";
  auditId: string;
  report: AuditReport;
  streamEvents?: AuditStreamEvent[];
}
```

Workspace:
- For full UI demo, unhide `evaluations` tab in kiosk if `auditStore.report` exists.
- Or reveal tab after audit op fires.

NGM audit spoof:
```ts
band: "strong"
weighted_score: 18
score_pct: 0.86
headline: "Investigation correctly separated confirmed busbar evidence from the DS-275-13 hypothesis."
gaps: [
  "Protection record request should happen before market-notice drafting.",
  "Topology dependency should be cited in final action rationale."
]
improvements: [
  { category: "process", text: "Move protection-record retrieval to the first two operator actions." },
  { category: "tooling", text: "Add one graph_switch_state_snapshot call before push_action." }
]
rubric dimensions: evidence coverage, tool coverage, actionability, uncertainty handling, operator clarity.
```

ATC audit spoof:
```ts
band: "strong"
weighted_score: 17
score_pct: 0.81
headline: "ATC flow preserved operational truth: RA real, initial STCAs fused-track only, tracker root cause unconfirmed."
gaps: [
  "Audio transcript remains pending at time of action push.",
  "Controller instruction log should be explicitly attached to MOR package."
]
improvements: [
  { category: "data", text: "Capture tower audio before tracker rollback begins." },
  { category: "process", text: "Add a mandatory evidence checklist before classify_occurrence." }
]
```

Stream events:
- Include 3-5 fake tool cards in audit stream so the stream area is not empty.
- Use real active tool names for NGM; ATC display names via bootstrap override.

---

### 3.9 Situation Detector Tuning Panel

Source:
- `components/panels/SituationDetectorTuningPanel.tsx`
- `components/shared/ValueDial.tsx`
- `stores/situationStore.ts`

Must show:
- Detector tuning tab visible in kiosk once seeded.
- Sensitivity controls.
- Detection Window dial.
- Max Alarm/SCADA row controls (in `SituationControlBar`, currently hidden under `IS_KIOSK`; for full UI demo, show as disabled/seeded controls or in tuning tab).
- Draft config.
- Comparison rows.
- Save/apply/reset disabled or spoofed.
- Plain-English rules.
- Advanced signal editor with alarm + SCADA tabs.

Required ops:
```ts
"panel.detector_config.set"
"panel.detector_config.preview"
```

NGM tuning seed:
- Alarm signals: `bus_diff`, `cb_trip`, `earth_fault`, `prot_op`, `thermal_advisory`.
- SCADA signals: `bus_collapse`, `gen_trip`, `line_overload`, `tx_overload`, `kv_transient`.
- Draft comparison:
  - Current detects 5 situations.
  - Sensitive profile detects precursor 37 minutes earlier with +1 INVESTIGATE.
  - Severity mismatch: `MARRABEL_NX` remains Critical, KETTERING remains Major.

ATC tuning seed:
- Alarm signals mapped to ATC labels but active type fields:
  - `stca`, `tcas_ra`, `apw`, `runway_suspend`.
- SCADA/surveillance signals:
  - `ghost_track`, `adsb_disagree`, `go_around`, `hold_initiated`, `flow_restriction`.
- Draft comparison:
  - Current detects 5 situations.
  - Sensitive profile flags 08:17 precursor earlier.

---

### 3.10 Topology Panel

Source:
- `components/topology/*`

Must show:
- Center station/facility graph.
- Neighbors.
- Link flow labels.
- Alarm overlay.
- Equipment rows.
- Detail pane.
- Breadcrumb.
- Expand neighbor if feasible.

NGM:
- Use current MARRABEL topology.
- Ensure graph has live summaries, links, equipment live tags.
- Use overlay on Bus 275-1 and DS-275-13.

ATC:
- Use METROFIELD topology.
- Rename facilities via payload labels:
  - METROFIELD_APP, NORTHGATE_TWR, EASTVALE_CTR, CROSSWIND_TWR, SURV_MAINT.
- Overlay fused tracker / 27L corridor.

---

### 3.11 Command Palette + Help Overlay + Toaster

Source:
- `components/shared/CommandPalette.tsx`
- `components/shared/HelpOverlay.tsx`
- `components/shared/Toaster.tsx`

Must show at least once:
- Command palette opens with keyboard or button.
- Navigation actions include status/data/topology/tuning/evaluations.
- Help overlay available.
- Toast triggered on a spoofed action or audit completion.

Scenario op proposal:
```ts
"ui.toast.show": { level: "success" | "info" | "warning"; message: string }
"ui.command_palette.open"?: {}
```

Optional. Not critical if demo stage does not want overlay interrupts.

---

## 4. Scenario Timeline: NGM Full UI Showcase

Recommended compact sequence:

1. **Pre-scan empty state**
   - Situations empty.
   - Summary empty.
   - Classification empty.
   - Grid Status empty.

2. **Scan start**
   - `panel.situations.scan_start`
   - Scan progress bar/panel active.
   - Detector dials visible in tuning tab or top strip if enabled.

3. **Scan complete**
   - `panel.situations.set` with `situations`, `grid_status`.
   - Station groups visible.
   - Status tab populated.

4. **Classification reveal**
   - `panel.situations.classify`
   - `panel.classify_verdict.set`
   - Summary optionally starts streaming.

5. **Evidence expansion beat**
   - Programmatically expand `ngm-crit-1` row? If no op exists, instruct presenter to click.
   - Ensure signal evidence and affected equipment are populated.

6. **Tool suite chat**
   - One investigation prompt.
   - 10-15 active tools.
   - Tight cluster.

7. **Data Search tab**
   - `dock.thread.set` for data_search.
   - Switch to `data` tab.
   - Show two preloaded data-search exchanges.

8. **Topology tab**
   - `topology.set`.
   - Switch to `topology`.
   - Show overlay and links.

9. **Actions**
   - `push_action` tool calls.
   - `panel.priority_action.append` cards.
   - Optional `panel.priority_action.decision` for one completed action.

10. **Tuning tab**
    - `panel.detector_config.set`
    - Switch to `tuning`.
    - Show sensitive profile + comparison.

11. **Audit tab**
    - `panel.audit.set`
    - Switch to `evaluations`.
    - Show auditor report + stream events.

12. **Precursor reveal**
    - Existing final phase.
    - Should reference detector tuning/sensitive profile if used.

---

## 5. Scenario Timeline: ATC Full UI Showcase

1. **Pre-scan empty state**
   - Airspace Status empty.

2. **Scan start**
   - `panel.situations.scan_start` with ATC scan messages.

3. **Scan complete**
   - `panel.situations.set` with `situations`, `airspace_status`.
   - Airspace Status panel populated.

4. **Situation card expansion beat**
   - Expand `atc-crit-1` with STCA/RA/ADS-B evidence.

5. **One prompt + 15 active GridIQ tools**
   - Current compact suite already close.
   - Keep internal active tool IDs.
   - Keep ATC display names via `tool_display_names`.

6. **Data Search tab**
   - Preloaded surveillance/procedure/participants conversation.

7. **Topology tab**
   - Show facility dependency map.

8. **Two operator actions**
   - Current flow already good.

9. **Classification**
   - Current flow already good.

10. **Tuning tab**
    - Show `ghost_track` sensitivity profile and precursor detection improvement.

11. **Audit tab**
    - Show ATC audit report.

12. **Precursor reveal**
    - Existing phase should tie to tuning/audit evidence.

---

## 6. Data Module Layout

Per scenario, split demo data by surface.

```text
scenarios/ngm_busbar_trip/
  gridStatus.ts
  detectorConfig.ts
  auditReport.ts
  dataSearchThread.ts
  signalEvidence.ts        # optional helper if situations.ts gets large

scenarios/atc_tcas_cascade/
  airspaceStatus.ts
  detectorConfig.ts
  auditReport.ts
  dataSearchThread.ts
  signalEvidence.ts
```

Avoid bloating `phases/*.ts` with giant data constants.

---

## 7. Acceptance Criteria

### Both Scenarios

- [ ] No visible empty major panel after its showcase beat.
- [ ] Situation Alerts station headers clean: severity + station only.
- [ ] Child situation rows keep time/equipment/severity/score.
- [ ] At least one expanded situation row shows full SituationCard.
- [ ] At least one situation shows alarm signal evidence disclosure.
- [ ] At least one situation shows SCADA signal evidence disclosure.
- [ ] At least one situation shows affected-equipment expansion with alarms and SCADA.
- [ ] Summary card has headline, bullets, open questions.
- [ ] Classification card has final verdict.
- [ ] Priority panel has at least two actions.
- [ ] Data Search tab has preloaded conversation with tool cards.
- [ ] Topology tab has graph + overlay.
- [ ] Tuning tab has seeded config + comparison.
- [ ] Audit tab has seeded report + rubric + gaps + improvements.
- [ ] Tool cards use typed renderers, not JSON fallback except allowed tools.
- [ ] Kiosk build passes.
- [ ] Playwright smoke verifies NGM and ATC status/summary/classification/data/audit/tuning surfaces.

### NGM Only

- [ ] Uses `GridStatusPanel`.
- [ ] No `AirspaceStatusPanel` visible.
- [ ] Uses energy vocabulary and MW/Hz labels.

### ATC Only

- [ ] Uses `AirspaceStatusPanel`.
- [ ] No NEM/MW/Frequency grid status language in status tab.
- [ ] Uses ATC tool display names.

---

## 8. Risk Register

| Risk | Severity | Mitigation |
|---|---|---|
| Large data blobs make phase files unreadable | M | Split data modules per surface |
| Kiosk hidden tabs (`tuning`, `evaluations`) never visible | H | Conditional reveal when seeded data exists |
| SituationCard signal evidence malformed | H | Add local smoke that expands first high-priority row |
| Data Search dock still welcome-only | M | `dock.thread.set` op + seeded messages |
| Audit report shape mismatches `AuditReport` | M | Import `AuditReport` type into data modules |
| ATC accidentally shows GridStatus | H | Workspace chooses `AirspaceStatusPanel` when `airspaceStatus` exists |
| Tool cards fall to JSON | M | Registry coverage check for scenario tool names |
| Main and global kiosk drift | M | Apply shared spec to both or document intentional divergence |

---

## 9. Work Plan

1. Add missing patch ops: audit, detector config, dock thread, optional decision/toast.
2. Add data modules for NGM + ATC.
3. Populate rich signal evidence in `situations.ts` or helper modules.
4. Unhide `tuning` + `evaluations` conditionally in kiosk Workspace.
5. Seed Data Search conversation after scan or before data-tab showcase.
6. Seed audit report before evaluations-tab showcase.
7. Seed detector config before tuning-tab showcase.
8. Build and run local Playwright smoke for both scenarios.
9. Deploy internal global kiosk.
10. Verify live NGM + ATC flows.
11. Mirror energy-only subset to `gridiq_main_kiosk` as needed.

---

## 10. Definition Of Done

- NGM and ATC both feel like real product demos, not only scenario playback.
- Every main UI feature has a visible, populated, believable state.
- Domain-specific surfaces remain domain-correct:
  - NGM = Grid Status.
  - ATC = Airspace Status.
- No panel reads as placeholder/empty after its beat.
- Live deployed kiosk passes smoke for both scenarios.
