# Operations Dataset Review

Visibility: evaluator_only. Do not give this review, labels, provenance or raw pack paths to a predictor.

Reports anchor authored events, not universal policy. Every KB action rule, waveform, cadence, alarm code, topology detail and availability assumption is simulated.
Source PDF/extraction hashes and exact page-scoped quotes are retained only in private provenance. Byte/quote agreement is not proof that a report is universally correct.
Yallourn support concerns synchronous-unit combinations/system strength, not replacement of exactly 597 MW. Protection/control classification and flooding/control-circuit explanations are later forensic truth.
Murray trip/restoration source times have minute precision; synthetic seconds do not improve report precision. No generation or customer load loss is attributed to that busbar event; pre-existing outages are not new trips.
AEST means fixed UTC+10, including October and January. Current policy without valid_to is assumed valid indefinitely; topology is static synthetic context.
Mode defaults: 300-second latest-sample freshness; 300-second detection latency budget unless authored; zero extra event-time tolerance beyond the source interval. Thresholds (5/25 MW, 10%/80% nominal voltage) are synthetic decision assumptions.
Action starts from explicit simulated operator notifications, preserving source intervals and assuming notification availability at cutoff, not report availability. Current affected-asset SCADA and scoped KB/topology/tool prerequisites still require verification. Alarm records are latched event indications, not periodically sampled freshness evidence; latest conflicting protection/return indications refuse.
No physical operations, model calls, optimizer or training loop. Future campaign ownership remains the public OptimizationService.

## Replay Measurements

One synthetic process test, not learning or demonstrated generalization. Holdout is inspected; no untouched holdout claim.

Detection-only precision/recall require event type, exact assets and source-tolerant time. Given action notifications never enter event/localization/time denominators. Null means no denominator.

| Run | Detection Cases | Passed | Status Accuracy | Event P/R | FP | Localization Recall | Time Accuracy |
| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |
| power_only_detection.defer_action | 14 | 9 | 0.642857 | 1.0 / 0.5 | 0 | 0.571429 | 0.5 |
| reference | 14 | 14 | 1.0 | 1.0 / 1.0 | 0 | 1.0 | 1.0 |
| reference.confirm_cause | 14 | 8 | 1.0 | 1.0 / 1.0 | 0 | 1.0 | 1.0 |
| reference.deny_scada | 14 | 0 | 0.285714 | None / 0.0 | 0 | 0.0 | 0.0 |
| reference.drop_records | 14 | 4 | 0.285714 | None / 0.0 | 0 | 0.0 | 0.0 |
| reference.wrong_rule | 14 | 8 | 0.571429 | None / 0.0 | 0 | 0.0 | 0.0 |

Conditional action scores assess recommendations from GIVEN notifications, not independent event detection.

| Run | Action Cases | Passed | Recall / Exact | Prerequisites | Status / Gap | Input Consistency | Communication | Unsupported Causes |
| --- | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: |
| power_only_detection.defer_action | 8 | 2 | 0.25 / 0.25 | 0.25 | 0.25 / 0.25 | 1.0 | 1.0 | 0 |
| reference | 8 | 8 | 1.0 / 1.0 | 1.0 | 1.0 / 1.0 | 1.0 | 1.0 | 0 |
| reference.confirm_cause | 8 | 2 | 1.0 / 1.0 | 1.0 | 1.0 / 1.0 | 1.0 | 0.25 | 6 |
| reference.deny_scada | 8 | 0 | 0.25 / 0.25 | 0.25 | 0.25 / 0.25 | 1.0 | 1.0 | 0 |
| reference.drop_records | 8 | 2 | 0.25 / 0.25 | 0.25 | 0.25 / 0.25 | 1.0 | 1.0 | 0 |
| reference.wrong_rule | 8 | 2 | 0.166667 / 0.25 | 0.25 | 0.25 / 1.0 | 0.25 | 0.25 | 0 |

All denominators include missing and failed predictions. Complete requests, returned evidence IDs, errors and per-case diagnoses: `replay/cases.jsonl`.

Baseline: power-only transition detection; action always defers for verification and operator escalation without querying tools. No action detection credit is awarded.
Correct expected insufficiency is a pass; a resource gap is not automatically a predictor failure. Required classification, cause status and gap must match without private defaults or undocumented alternatives.
Communication measures declared event/asset/interval/state/uncertainty/next-step fields; narrative usefulness remains human-reviewed. Prerequisite completeness requires the expected or alternative action set with evidence (or the required safe refusal). Separate action_prerequisite_safety can pass on safe refusal without completeness credit.

## c-e6d04f04ed33b4d3b148 (s001)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: initial-transition.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 01 [AS_WR_VENT_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 01 [AS_YW_CHARGER_01, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:34:31Z (2025-10-16T13:34:31+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["YWPS_U4"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "generation_disconnection". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:f0c254aa-a611-5f75-8f77-d0f58ba8ea63 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1773c911-0841-5653-99e1-26c746ada2d1 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- e-53a91b779566f65d88fda549, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: confirm_event, assess_system_strength, consult_limit_advice, request_authorized_support, notify_operator, investigate_cooling. Required tools: scada, alarms, knowledge, topology. Rationale: Confirm observed loss, review system strength rather than replace a MW total, then recommend authorized follow-up with uncertainty.

Source event yallourn-unit4-trip: 16 October 2025, 1334.29 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit4-trip: later classification "Protection/control system (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "Cooling water loss followed unintended valve operation. Actuator control circuit damage was likely due to long-term flooding; power loss alone does not establish this cause."}.
- Historical action yallourn-support-direction: Historical direction to Jeeralang A2, A3, B3 for system strength; not a fixture dispatch command. Time: 16 October 2025, 1350 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a2-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-b3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1405 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-direction-cancellation: Directions cancelled at 1755, effective from 1800. No generation stop at 1800 is inferred. Time: 16 October 2025, 1755 hrs AEST; effective 1800 hrs; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-actuator-isolation: Reported permanent electrical isolation by EnergyAustralia; no exact time available and no replay control action. Time: Immediately following the incident; precision: unavailable; uncertainty: No exact simulated isolation time or live isolation state is inferred..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 11, "knowledge": 4, "scada": 3348, "topology": 781}
Reference produced: {"action_ids": [], "asset_ids": ["YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "event_time": "2025-10-16T03:34:29Z", "event_type": "generator_trip", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| YWPS_U4 / active_power_mw | 2025-10-16T03:32:59Z | 2025-10-16T03:33:00Z | 298.11 | MW | e-9cb0f0c28dd833411e74ddeb |
| YWPS_U4 / active_power_mw | 2025-10-16T03:34:31Z | 2025-10-16T03:34:31Z | 0.0 | MW | e-ce10cc4fa47b9f4abe8e2c4f |
| YWPS_U4 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 1.0 | 1 | e-8bd838c97a9a633678f063cb |
| YWPS_U4 / breaker_closed | 2025-10-16T03:34:30Z | 2025-10-16T03:34:30Z | 0.0 | 1 | e-bfb74985f1ddde7af24e5526 |
| YWPS_U4 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:33:01Z | 19.999 | kV | e-419161705f1ae2027ea1f1b4 |
| YWPS_U4 / voltage_kv | 2025-10-16T03:34:30Z | 2025-10-16T03:34:31Z | 19.745185 | kV | e-f62add58c6cf56f74ae0baef |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 3348; complete True; first six evidence IDs ["e-053f4413072a89aa3bfbf571", "e-06b138c1799b9037257cf423", "e-095f54c939c874f3e9f3aa88", "e-09f2c1fab7efb2f2e313d633", "e-0b4e11e97abeba859b2eb2be", "e-129b412608c92a93b75e4a31"]; quality counts {"good": 130}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 11; complete True; first six evidence IDs ["e-6435891ba773fc03803072c7", "e-9b945ce4ef7357370ea7ef50", "e-a9badf0b11febeb6874c7fbb", "e-4182311bc1fa6341a1ab6d26", "e-8d33ac06b14a8f7f062489d6", "e-b08b3c93648e43d8c006cddb"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: event, generator_trip, assets ["YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-b7ae2135afb1343a0ff3 (s002)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: correlated-state.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service charger AC input 02 [AS_WR_CHARGER_02, auxiliary]; Wattle Reach Station-service ventilation feeder 01 [AS_WR_VENT_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 01 [AS_YW_CHARGER_01, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Yallourn W Station-service ventilation feeder 02 [AS_YW_VENT_02, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["YWPS_U4", "YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "generation_disconnection". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_CHARGER_02 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:da77f0c2-a95e-5060-80a3-c81a6e097b91 |
| AS_WR_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:f0c254aa-a611-5f75-8f77-d0f58ba8ea63 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1773c911-0841-5653-99e1-26c746ada2d1 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| AS_YW_VENT_02 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ef002a2b-4043-55ba-9c53-644c5fa0d826 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- e-53a91b779566f65d88fda549, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: confirm_event, assess_system_strength, consult_limit_advice, request_authorized_support, notify_operator, investigate_cooling. Required tools: scada, alarms, knowledge, topology. Rationale: Confirm observed loss, review system strength rather than replace a MW total, then recommend authorized follow-up with uncertainty.

Source event yallourn-unit4-trip: 16 October 2025, 1334.29 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.
Source event yallourn-unit3-trip: 16 October 2025, 1334.32 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit4-trip: later classification "Protection/control system (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "Cooling water loss followed unintended valve operation. Actuator control circuit damage was likely due to long-term flooding; power loss alone does not establish this cause."}.
- Historical action yallourn-support-direction: Historical direction to Jeeralang A2, A3, B3 for system strength; not a fixture dispatch command. Time: 16 October 2025, 1350 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a2-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-b3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1405 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-direction-cancellation: Directions cancelled at 1755, effective from 1800. No generation stop at 1800 is inferred. Time: 16 October 2025, 1755 hrs AEST; effective 1800 hrs; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-actuator-isolation: Reported permanent electrical isolation by EnergyAustralia; no exact time available and no replay control action. Time: Immediately following the incident; precision: unavailable; uncertainty: No exact simulated isolation time or live isolation state is inferred..
- yallourn-unit3-trip: later classification "Protection/control system (later report classification)"; later cause {"available_at": "2026-08-01T00:00:00Z", "same_as_event": "yallourn-unit4-trip", "status": "later_investigation"}.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": true, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 16, "knowledge": 4, "scada": 6231, "topology": 829}
Reference produced: {"action_ids": [], "asset_ids": ["YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "event_time": "2025-10-16T03:34:29Z", "event_type": "generator_trip", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| YWPS_U3 / active_power_mw | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 298.792 | MW | e-a619b17b103d520c16abf78e |
| YWPS_U3 / active_power_mw | 2025-10-16T03:35:49Z | 2025-10-16T03:35:51Z | 0.0 | MW | e-3b4386b77f0d9d73526730b4 |
| YWPS_U3 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:33:01Z | 1.0 | 1 | e-5d569d3f9fd8d985f82fa655 |
| YWPS_U3 / breaker_closed | 2025-10-16T03:35:59Z | 2025-10-16T03:35:59Z | 0.0 | 1 | e-3fb06768639c5d5190dcf3d7 |
| YWPS_U3 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 20.014 | kV | e-fe498bc760cf691a3974c6e8 |
| YWPS_U3 / voltage_kv | 2025-10-16T03:35:49Z | 2025-10-16T03:35:50Z | 0.0 | kV | e-87e382f404b45b6a65049c23 |
| YWPS_U4 / active_power_mw | 2025-10-16T03:32:59Z | 2025-10-16T03:33:00Z | 298.11 | MW | e-49ee3201f7ff626a6004d373 |
| YWPS_U4 / active_power_mw | 2025-10-16T03:35:59Z | 2025-10-16T03:35:59Z | 0.0 | MW | e-705877fe23e99da9d8b75b71 |
| YWPS_U4 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 1.0 | 1 | e-ebffc932d5d7936990a3c9ce |
| YWPS_U4 / breaker_closed | 2025-10-16T03:35:49Z | 2025-10-16T03:35:51Z | 0.0 | 1 | e-2a9de378c5c6f20826972ec6 |
| YWPS_U4 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:33:01Z | 19.999 | kV | e-ff87200f6d059136ad018493 |
| YWPS_U4 / voltage_kv | 2025-10-16T03:35:59Z | 2025-10-16T03:35:59Z | 0.0 | kV | e-5a40811409bd258ab2da481e |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 6231; complete True; first six evidence IDs ["e-0437cac0028132d91bb0a5bb", "e-0a93618829ba60c0d6671ff6", "e-0af9bf26cfa4822623e17074", "e-0cd68df0d03f4985c4286dd6", "e-0f46ee4c910980ade5312984", "e-11312935c310519a00354ed1"]; quality counts {"good": 140}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 16; complete True; first six evidence IDs ["e-3b7304a8d43810985f7660a9", "e-56b196fbb0e03489d33d7586", "e-88d74942a16c8cf7da53f2a7", "e-48ae95aa55987290d1ff56dd", "e-b2647f12ea2ab566ded7bd3a", "e-f444ac1f12e5454d93b13a23"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-b4d6e1f97b8505e7f59d (s003)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: restoration.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 01 [AS_YW_CHARGER_01, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T06:26:00Z (2025-10-16T16:26:00+10:00 AEST); decision 2025-10-16T06:28:15Z (2025-10-16T16:28:15+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "return_to_service". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1773c911-0841-5653-99e1-26c746ada2d1 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- e-53a91b779566f65d88fda549, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: verify_restoration, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Verify return with fresh state evidence and notify the operator; do not infer all other units restored.

Source event yallourn-unit3-restoration: 16 October 2025, 1627 hrs AEST; minute precision; UTC interval {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit3-restoration: later classification "Reported resynchronization; subsequent MW ramp is invented"; later cause null.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 13, "knowledge": 4, "scada": 3444, "topology": 757}
Reference produced: {"action_ids": [], "asset_ids": ["YWPS_U3"], "cause_status": "not_established", "classification": "return_to_service", "event_time": "2025-10-16T06:27:30Z", "event_type": "restoration", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| YWPS_U3 / active_power_mw | 2025-10-16T06:26:00Z | 2025-10-16T06:26:00Z | 0.0 | MW | e-30878fd4a57dc6e3e6efcd3d |
| YWPS_U3 / active_power_mw | 2025-10-16T06:28:10Z | 2025-10-16T06:28:10Z | 38.536 | MW | e-65a50ba8a9b1c5460334d247 |
| YWPS_U3 / breaker_closed | 2025-10-16T06:26:00Z | 2025-10-16T06:26:02Z | 0.0 | 1 | e-ca198c31f3b2c193e5cc69bd |
| YWPS_U3 / breaker_closed | 2025-10-16T06:28:15Z | 2025-10-16T06:28:15Z | 1.0 | 1 | e-edc2c73e98e51d5b83c88b99 |
| YWPS_U3 / voltage_kv | 2025-10-16T06:26:00Z | 2025-10-16T06:26:01Z | 0.0 | kV | e-d22d633c7e0be51c682324d7 |
| YWPS_U3 / voltage_kv | 2025-10-16T06:28:10Z | 2025-10-16T06:28:11Z | 20.027 | kV | e-e52c11d7d630a7c5cdb2e739 |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 3444; complete True; first six evidence IDs ["e-0357f10bca7007486b2775cf", "e-092319a9fae91cf6f8fed58f", "e-092d04410025fac61e27677f", "e-0aa85ad17042f2fb75a4583e", "e-0baa465bf758defc5b574fa3", "e-0c89115a1b0dc25bef63c541"]; quality counts {"good": 125}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 13; complete True; first six evidence IDs ["e-00543e99c6830b4f995279df", "e-f553c8155b3e57fe9809a1fe", "e-7212413ee710ed5252013a90", "e-c4465b38dfecfe33926c7b12", "e-61b5124a60cecb58679374b9", "e-801a665f5026130a1ea429d6"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: event, restoration, assets ["YWPS_U3"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, restoration, assets ["YWPS_U3"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-c1f8d1317a630cca3631 (s004)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: normal-baseline.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:29:29Z (2025-10-16T13:29:29+10:00 AEST); decision 2025-10-16T03:31:29Z (2025-10-16T13:31:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event yallourn-unit4-trip: 16 October 2025, 1334.29 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.
Source event yallourn-unit3-trip: 16 October 2025, 1334.32 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit4-trip: later classification "Protection/control system (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "Cooling water loss followed unintended valve operation. Actuator control circuit damage was likely due to long-term flooding; power loss alone does not establish this cause."}.
- Historical action yallourn-support-direction: Historical direction to Jeeralang A2, A3, B3 for system strength; not a fixture dispatch command. Time: 16 October 2025, 1350 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a2-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-b3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1405 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-direction-cancellation: Directions cancelled at 1755, effective from 1800. No generation stop at 1800 is inferred. Time: 16 October 2025, 1755 hrs AEST; effective 1800 hrs; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-actuator-isolation: Reported permanent electrical isolation by EnergyAustralia; no exact time available and no replay control action. Time: Immediately following the incident; precision: unavailable; uncertainty: No exact simulated isolation time or live isolation state is inferred..
- yallourn-unit3-trip: later classification "Protection/control system (later report classification)"; later cause {"available_at": "2026-08-01T00:00:00Z", "same_as_event": "yallourn-unit4-trip", "status": "later_investigation"}.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 6, "knowledge": 4, "scada": 2799, "topology": 733}
Reference produced: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": null, "hypotheses": [], "message": "No qualifying unplanned transition in usable as-of samples; steady outages are not new trips.", "status": "no_event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 2799; complete True; first six evidence IDs ["e-02827584f144761fc9f12524", "e-047a48a7711195015bceb79c", "e-095a46bf951add33badd601a", "e-0a3f9a45a158491fd9380802", "e-0e2397e449f1f4b17abad380", "e-18b9ef75318ca97520bf742e"]; quality counts {"good": 120}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 6; complete True; first six evidence IDs ["e-0b7643c9723d910efa3243fa", "e-52697e6b2e83dd294297ccc0", "e-4c00359834f711ab1439ac9c", "e-e0877221e0784d97cfc6f055", "e-f34f12e4f1b489a8de155927", "e-d697c4f333590d2165d271b2"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-6e66095f8085901050af (s005)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: preexisting-outage.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 01 [AS_YW_CHARGER_01, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:29:29Z (2025-10-16T13:29:29+10:00 AEST); decision 2025-10-16T03:31:29Z (2025-10-16T13:31:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1773c911-0841-5653-99e1-26c746ada2d1 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event yallourn-unit4-trip: 16 October 2025, 1334.29 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.
Source event yallourn-unit3-trip: 16 October 2025, 1334.32 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit4-trip: later classification "Protection/control system (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "Cooling water loss followed unintended valve operation. Actuator control circuit damage was likely due to long-term flooding; power loss alone does not establish this cause."}.
- Historical action yallourn-support-direction: Historical direction to Jeeralang A2, A3, B3 for system strength; not a fixture dispatch command. Time: 16 October 2025, 1350 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a2-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-b3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1405 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-direction-cancellation: Directions cancelled at 1755, effective from 1800. No generation stop at 1800 is inferred. Time: 16 October 2025, 1755 hrs AEST; effective 1800 hrs; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-actuator-isolation: Reported permanent electrical isolation by EnergyAustralia; no exact time available and no replay control action. Time: Immediately following the incident; precision: unavailable; uncertainty: No exact simulated isolation time or live isolation state is inferred..
- yallourn-unit3-trip: later classification "Protection/control system (later report classification)"; later cause {"available_at": "2026-08-01T00:00:00Z", "same_as_event": "yallourn-unit4-trip", "status": "later_investigation"}.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Benign planned/test alarm is invented. YWPS_U2 pre-existing unavailability is a fixture assumption, not resolved from diagram text order.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "benign", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 10, "knowledge": 4, "scada": 2859, "topology": 757}
Reference produced: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": null, "hypotheses": [], "message": "No qualifying unplanned transition in usable as-of samples; steady outages are not new trips.", "status": "no_event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 2859; complete True; first six evidence IDs ["e-020f69ef55ebd1f1fea57136", "e-024d69e85146cdc70dccb716", "e-0af9c8ca94b0cb5fe85a8f2e", "e-125ddd17a9aed742878f7aba", "e-1488ef8e3ca345116ec19df4", "e-18fb1937513d3b440324629b"]; quality counts {"good": 125}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 10; complete True; first six evidence IDs ["e-3b0a183ac5e8c11ded28a298", "e-0b308678d5f662ba494302e9", "e-c41f089a40790916ea8b76f8", "e-2db802e01ead37df3f0ecc0b", "e-c3ef340e2974698c8df40c97", "e-31b982328d266e1e41f4d7d8"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-07691f9b229d43fd18f0 (s006)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: bad-and-stale-signals.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event yallourn-unit4-trip: 16 October 2025, 1334.29 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.
Source event yallourn-unit3-trip: 16 October 2025, 1334.32 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit4-trip: later classification "Protection/control system (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "Cooling water loss followed unintended valve operation. Actuator control circuit damage was likely due to long-term flooding; power loss alone does not establish this cause."}.
- Historical action yallourn-support-direction: Historical direction to Jeeralang A2, A3, B3 for system strength; not a fixture dispatch command. Time: 16 October 2025, 1350 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a2-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-b3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1405 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-direction-cancellation: Directions cancelled at 1755, effective from 1800. No generation stop at 1800 is inferred. Time: 16 October 2025, 1755 hrs AEST; effective 1800 hrs; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-actuator-isolation: Reported permanent electrical isolation by EnergyAustralia; no exact time available and no replay control action. Time: Immediately following the incident; precision: unavailable; uncertainty: No exact simulated isolation time or live isolation state is inferred..
- yallourn-unit3-trip: later classification "Protection/control system (later report classification)"; later cause {"available_at": "2026-08-01T00:00:00Z", "same_as_event": "yallourn-unit4-trip", "status": "later_investigation"}.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "absent", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 6, "knowledge": 4, "scada": 3987, "topology": 733}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 3987; complete True; first six evidence IDs ["e-031b08d5bc7c1ccbe1ef9008", "e-03c5c67ed9ab45c418972218", "e-0880bfe49e5cc80627394cff", "e-12ca0fa80d512ed1fa9c2f12", "e-1be3197ef4627afb930d3afe", "e-1c3e8f6f980ebb098fa24f45"]; quality counts {"bad": 7, "good": 102, "missing": 7}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 6; complete True; first six evidence IDs ["e-ea6a7752a6a96f94d1bd9c57", "e-1e9fb6a4932cd8c7309807ff", "e-ef795abee88f7c6fa624cef6", "e-447208d4cff4c456d18cf0e2", "e-3ade7260fbf5ad851c3cbfe6", "e-23c6a8cc83bc47b6dbae32e4"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-4c7343d51ed40de84047 (s007)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: late-alarms.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 01 [AS_WR_VENT_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 01 [AS_YW_CHARGER_01, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:f0c254aa-a611-5f75-8f77-d0f58ba8ea63 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1773c911-0841-5653-99e1-26c746ada2d1 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event yallourn-unit4-trip: 16 October 2025, 1334.29 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.
Source event yallourn-unit3-trip: 16 October 2025, 1334.32 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit4-trip: later classification "Protection/control system (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "Cooling water loss followed unintended valve operation. Actuator control circuit damage was likely due to long-term flooding; power loss alone does not establish this cause."}.
- Historical action yallourn-support-direction: Historical direction to Jeeralang A2, A3, B3 for system strength; not a fixture dispatch command. Time: 16 October 2025, 1350 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a2-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-b3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1405 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-direction-cancellation: Directions cancelled at 1755, effective from 1800. No generation stop at 1800 is inferred. Time: 16 October 2025, 1755 hrs AEST; effective 1800 hrs; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-actuator-isolation: Reported permanent electrical isolation by EnergyAustralia; no exact time available and no replay control action. Time: Immediately following the incident; precision: unavailable; uncertainty: No exact simulated isolation time or live isolation state is inferred..
- yallourn-unit3-trip: later classification "Protection/control system (later report classification)"; later cause {"available_at": "2026-08-01T00:00:00Z", "same_as_event": "yallourn-unit4-trip", "status": "later_investigation"}.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "delayed", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "missing"}.
Public evidence row counts: {"alarms": 10, "knowledge": 4, "scada": 4107, "topology": 781}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 4107; complete True; first six evidence IDs ["e-0191c2ed6ca939b9b3256782", "e-02f98c22cb4fdb3cee1c8fe4", "e-03f814afd76e950171c98a03", "e-083b045b55191224240d1a4c", "e-0a62eeea7e4cdd04d4ffde14", "e-0cfbf70ae94f942d3510282a"]; quality counts {"good": 112, "missing": 18}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 10; complete True; first six evidence IDs ["e-ee19487dc82a09484cc2c33d", "e-34465a59ee01a28fdc51f4a8", "e-ba2778bdaec09bf6c9befd8d", "e-0be0bad7c9f4a2f8cf154b4b", "e-ed90b854ea9d188ca8fbd83d", "e-1f5d6294cebe8bf173906e82"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-7d95f19397c0b8c69b23 (s008)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: appropriate-response.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 01 [AS_WR_VENT_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 01 [AS_YW_CHARGER_01, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:37:29Z (2025-10-16T13:37:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["confirm_event", "assess_system_strength", "consult_limit_advice", "request_authorized_support", "notify_operator", "investigate_cooling"], "asset_ids": ["YWPS_U4", "YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["YWPS_U4"], "available_at": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "notification_id": "e-f09c3bf33a07068bac8d6f5d", "origin": "simulated_operator_notification", "synthetic": true}, {"asset_ids": ["YWPS_U3"], "available_at": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"}, "event_type": "generator_trip", "notification_id": "e-385e031fb1c88e80a4c18a11", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "generation_disconnection". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:f0c254aa-a611-5f75-8f77-d0f58ba8ea63 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1773c911-0841-5653-99e1-26c746ada2d1 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- e-53a91b779566f65d88fda549, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: confirm_event, assess_system_strength, consult_limit_advice, request_authorized_support, notify_operator, investigate_cooling. Required tools: scada, alarms, knowledge, topology. Rationale: Confirm observed loss, review system strength rather than replace a MW total, then recommend authorized follow-up with uncertainty.

Source event yallourn-unit4-trip: 16 October 2025, 1334.29 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.
Source event yallourn-unit3-trip: 16 October 2025, 1334.32 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit4-trip: later classification "Protection/control system (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "Cooling water loss followed unintended valve operation. Actuator control circuit damage was likely due to long-term flooding; power loss alone does not establish this cause."}.
- Historical action yallourn-support-direction: Historical direction to Jeeralang A2, A3, B3 for system strength; not a fixture dispatch command. Time: 16 October 2025, 1350 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a2-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-b3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1405 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-direction-cancellation: Directions cancelled at 1755, effective from 1800. No generation stop at 1800 is inferred. Time: 16 October 2025, 1755 hrs AEST; effective 1800 hrs; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-actuator-isolation: Reported permanent electrical isolation by EnergyAustralia; no exact time available and no replay control action. Time: Immediately following the incident; precision: unavailable; uncertainty: No exact simulated isolation time or live isolation state is inferred..
- yallourn-unit3-trip: later classification "Protection/control system (later report classification)"; later cause {"available_at": "2026-08-01T00:00:00Z", "same_as_event": "yallourn-unit4-trip", "status": "later_investigation"}.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source events and the scenario's generator/busbar subject class; associated transformers remain context. Notifications are assumed available at cutoff, not dated by report publication, and establish neither current state, prerequisites nor cause.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 12, "knowledge": 4, "scada": 6570, "topology": 781}
Reference produced: {"action_ids": ["confirm_event", "assess_system_strength", "consult_limit_advice", "request_authorized_support", "notify_operator", "investigate_cooling"], "asset_ids": ["YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "communication": {"asset_ids": ["YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "decision_time": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "evidence_ids": ["e-0353768364e99b4d21fbf2b5", "e-07a32330dffc55f33cb862a7", "e-09270172b790df8757b1276b", "e-1039da05a7cfbf7f0f905668", "e-16e17b076fb1548812644235", "e-17ee3c4c71e1f6f6e49c19f9", "e-1d47c1f4aac82fb750eb9b9a", "e-207718d199a5e2cb1d4fe0f7", "e-3467b673e06e203e93f2627c", "e-385e031fb1c88e80a4c18a11", "e-3d8b1b98a1ad4b5f125d0c17", "e-3f3a19e60b8f2ed57f5e6a56", "e-3f9c7ea5537c960b07303aca", "e-41b9d08dc1ceee5fe07b59dc", "e-443117a16e5268ae24352cef", "e-484521fc7882d5091fa4f0c6", "e-494c555e7faba3b6cb81db16", "e-4c720a6507b9b40684bd9e54", "e-4d6e9084a65157d82dd2a0f5", "e-4dfc7a7e82e36ae383f44c9b", "e-4e87146b1efe9b82f8dda348", "e-512efa5fc16140c6c207d98f", "e-53a91b779566f65d88fda549", "e-554ea8648e61a1d0db31add7", "e-5dab50f70427fd791283924d", "e-60690149dae57c6ee6c49cdc", "e-66ef70b093715fe649a47c94", "e-6afe422f3fe9d5da699ef598", "e-6c118ff127ce1c48eb7ab7cf", "e-74c9f66ef804e7756bf95b9e", "e-7dceb7661d0f802b30bac12a", "e-7f7e577577ad3f71eb8086cd", "e-82e0f74cc112d10cd99e0804", "e-86fb8fe5bac7208243492f31", "e-8748ece25f7eb8d70a765799", "e-93b51ab3343dabdbdb7c1301", "e-94d9fadaa769df97b937ce90", "e-96b6e5e6411c9407faccc374", "e-96daa753d7be7bcab0189097", "e-97b50c5510b78c423b07422f", "e-9ce9c3e8e3bf9b969e928850", "e-9ef384eb3baf16cfd6bfe0cf", "e-9f4e6c1def1eb172678db507", "e-a07e44dbd5d0bfd688dde690", "e-a0e9f1453af4718cbfb93bc6", "e-a31769ee1c7c2a755eec9948", "e-a6b896b5745be01b28beb740", "e-a73b9acab61e081a31756e96", "e-adb990f04ee1166f0d0091e2", "e-afd324ee6a04050eec2a0dbd", "e-b67b4dc8e1d1d846386f6faf", "e-b82066d01999b8db75b4b1ca", "e-b870224aac4141d2ae80998a", "e-bad13b1ad9224065b7107bca", "e-bc0a7b973a430832304995cf", "e-be5bd46f03fdec46d700a511", "e-c114f005913dfcb9969b3770", "e-c55519ed9496f1a34377a99c", "e-cd331fd2af9bb2d12447736f", "e-d20f6aac301057d8eecb793a", "e-d528151baf749f9b0869fe15", "e-de6ee08f81a2da42ff538c98", "e-e36661c8993c272faca7b2a6", "e-e92acd3c889be4f1baf484e3", "e-e94fb8ed2eb6200c1908679a", "e-efe29f8aca9a118486fa0377", "e-f09c3bf33a07068bac8d6f5d", "e-f2ce47ca12485f9533f9cef8", "e-f632bdf61098fcf33b4cf97e", "e-f71fe111e35b2db033a74e4a", "e-f960ca123e2a428c76f8a13d", "e-fb056cc5b16a5b61fb21b9da", "e-fb6a5c024c5a461473db3a63", "e-fc9764d50e676f5f1b7e7578", "e-ff248f28d83215dced058e58"], "next_steps": ["confirm_event", "assess_system_strength", "consult_limit_advice", "request_authorized_support", "notify_operator", "investigate_cooling"], "notification_ids": ["e-385e031fb1c88e80a4c18a11", "e-f09c3bf33a07068bac8d6f5d"], "state": "verified"}, "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_time": null, "event_type": "generator_trip", "gap": null, "hypotheses": [], "message": "Given simulated notifications: generator_trip for YWPS_U4 in [2025-10-16T03:34:29Z, 2025-10-16T03:34:30Z); generator_trip for YWPS_U3 in [2025-10-16T03:34:32Z, 2025-10-16T03:34:33Z). As of 2025-10-16T03:37:29Z, current state is verified: YWPS_U3 active_power_mw=0.0 MW at 2025-10-16T03:37:19Z; YWPS_U3 breaker_closed=0.0 1 at 2025-10-16T03:37:19Z; YWPS_U3 voltage_kv=0.0 kV at 2025-10-16T03:37:19Z; YWPS_U4 active_power_mw=0.0 MW at 2025-10-16T03:37:19Z; YWPS_U4 breaker_closed=0.0 1 at 2025-10-16T03:37:19Z; YWPS_U4 voltage_kv=0.0 kV at 2025-10-16T03:37:19Z. Fresh current measurements agree with the given event; original transition detection was not required. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: confirm_event, assess_system_strength, consult_limit_advice, request_authorized_support, notify_operator, investigate_cooling. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| YWPS_U3 / active_power_mw | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 298.792 | MW | e-c9bfd1ec981849ef9c1cb2fc |
| YWPS_U3 / active_power_mw | 2025-10-16T03:37:19Z | 2025-10-16T03:37:19Z | 0.0 | MW | e-b82066d01999b8db75b4b1ca |
| YWPS_U3 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:33:01Z | 1.0 | 1 | e-926b7b8295116c43d22dee3a |
| YWPS_U3 / breaker_closed | 2025-10-16T03:37:19Z | 2025-10-16T03:37:19Z | 0.0 | 1 | e-554ea8648e61a1d0db31add7 |
| YWPS_U3 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 20.014 | kV | e-ab5240503fbc30748619e769 |
| YWPS_U3 / voltage_kv | 2025-10-16T03:37:19Z | 2025-10-16T03:37:21Z | 0.0 | kV | e-f2ce47ca12485f9533f9cef8 |
| YWPS_U4 / active_power_mw | 2025-10-16T03:32:59Z | 2025-10-16T03:33:00Z | 298.11 | MW | e-d7c260b4c75bb30f1771c4d3 |
| YWPS_U4 / active_power_mw | 2025-10-16T03:37:19Z | 2025-10-16T03:37:21Z | 0.0 | MW | e-1039da05a7cfbf7f0f905668 |
| YWPS_U4 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 1.0 | 1 | e-bf592ea2d0207a72476d7baf |
| YWPS_U4 / breaker_closed | 2025-10-16T03:37:19Z | 2025-10-16T03:37:20Z | 0.0 | 1 | e-9ef384eb3baf16cfd6bfe0cf |
| YWPS_U4 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:33:01Z | 19.999 | kV | e-def20b0822861ca21e1d15bc |
| YWPS_U4 / voltage_kv | 2025-10-16T03:37:19Z | 2025-10-16T03:37:19Z | 0.0 | kV | e-3d8b1b98a1ad4b5f125d0c17 |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 390; complete True; first six evidence IDs ["e-3f561d4f959f8081d146924a", "e-5325dc70e145a27f4a8d0e53", "e-7070a6d8e961e9141d52e926", "e-926b7b8295116c43d22dee3a", "e-ab5240503fbc30748619e769", "e-bf592ea2d0207a72476d7baf"]; quality counts {"good": 10}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-484521fc7882d5091fa4f0c6", "e-96b6e5e6411c9407faccc374"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 3; complete True; first six evidence IDs ["e-4e87146b1efe9b82f8dda348", "e-53a91b779566f65d88fda549", "e-96daa753d7be7bcab0189097"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 390; complete True; first six evidence IDs ["e-3f561d4f959f8081d146924a", "e-5325dc70e145a27f4a8d0e53", "e-7070a6d8e961e9141d52e926", "e-926b7b8295116c43d22dee3a", "e-ab5240503fbc30748619e769", "e-bf592ea2d0207a72476d7baf"]; quality counts {"good": 10}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-484521fc7882d5091fa4f0c6", "e-96b6e5e6411c9407faccc374"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 3; complete True; first six evidence IDs ["e-4e87146b1efe9b82f8dda348", "e-53a91b779566f65d88fda549", "e-96daa753d7be7bcab0189097"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 62; complete True; first six evidence IDs ["e-fb6a5c024c5a461473db3a63", "e-97b50c5510b78c423b07422f", "e-a73b9acab61e081a31756e96", "e-fb056cc5b16a5b61fb21b9da", "e-09270172b790df8757b1276b", "e-1d47c1f4aac82fb750eb9b9a"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-7cd5f29c9cb59aeb5590 (s009)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: restoration-response.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 01 [AS_YW_CHARGER_01, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T06:26:00Z (2025-10-16T16:26:00+10:00 AEST); decision 2025-10-16T06:28:30Z (2025-10-16T16:28:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["verify_restoration", "notify_operator"], "asset_ids": ["YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["YWPS_U3"], "available_at": "2025-10-16T06:28:30Z", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "notification_id": "e-34fa5d226d16713bbe743352", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "return_to_service". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1773c911-0841-5653-99e1-26c746ada2d1 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- e-53a91b779566f65d88fda549, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: verify_restoration, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Verify return with fresh state evidence and notify the operator; do not infer all other units restored.

Source event yallourn-unit3-restoration: 16 October 2025, 1627 hrs AEST; minute precision; UTC interval {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit3-restoration: later classification "Reported resynchronization; subsequent MW ramp is invented"; later cause null.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source events and the scenario's generator/busbar subject class; associated transformers remain context. Notifications are assumed available at cutoff, not dated by report publication, and establish neither current state, prerequisites nor cause.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 13, "knowledge": 4, "scada": 3753, "topology": 757}
Reference produced: {"action_ids": ["verify_restoration", "notify_operator"], "asset_ids": ["YWPS_U3"], "cause_status": "not_established", "classification": "return_to_service", "communication": {"asset_ids": ["YWPS_U3"], "cause_status": "not_established", "decision_time": "2025-10-16T06:28:30Z", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "evidence_ids": ["e-09270172b790df8757b1276b", "e-16e17b076fb1548812644235", "e-17ee3c4c71e1f6f6e49c19f9", "e-1d47c1f4aac82fb750eb9b9a", "e-24509b3cc2cea46e8a925612", "e-336c207483f4c370312bd09e", "e-3467b673e06e203e93f2627c", "e-34fa5d226d16713bbe743352", "e-3f3a19e60b8f2ed57f5e6a56", "e-41b9d08dc1ceee5fe07b59dc", "e-443117a16e5268ae24352cef", "e-4d6e9084a65157d82dd2a0f5", "e-4e87146b1efe9b82f8dda348", "e-512efa5fc16140c6c207d98f", "e-53a91b779566f65d88fda549", "e-5dab50f70427fd791283924d", "e-60690149dae57c6ee6c49cdc", "e-74c9f66ef804e7756bf95b9e", "e-82e0f74cc112d10cd99e0804", "e-8748ece25f7eb8d70a765799", "e-93b51ab3343dabdbdb7c1301", "e-94d9fadaa769df97b937ce90", "e-96daa753d7be7bcab0189097", "e-97b50c5510b78c423b07422f", "e-9ce9c3e8e3bf9b969e928850", "e-a68b8991d9d781ea574aac0f", "e-a6b896b5745be01b28beb740", "e-a73b9acab61e081a31756e96", "e-a8024e348704cf23c8c7fd42", "e-afd324ee6a04050eec2a0dbd", "e-b870224aac4141d2ae80998a", "e-bad13b1ad9224065b7107bca", "e-d20f6aac301057d8eecb793a", "e-d528151baf749f9b0869fe15", "e-e36661c8993c272faca7b2a6", "e-f632bdf61098fcf33b4cf97e", "e-fb056cc5b16a5b61fb21b9da", "e-fb6a5c024c5a461473db3a63", "e-fc9764d50e676f5f1b7e7578"], "next_steps": ["verify_restoration", "notify_operator"], "notification_ids": ["e-34fa5d226d16713bbe743352"], "state": "verified"}, "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_time": null, "event_type": "restoration", "gap": null, "hypotheses": [], "message": "Given simulated notifications: restoration for YWPS_U3 in [2025-10-16T06:27:00Z, 2025-10-16T06:28:00Z). As of 2025-10-16T06:28:30Z, current state is verified: YWPS_U3 active_power_mw=45.057 MW at 2025-10-16T06:28:30Z; YWPS_U3 breaker_closed=1.0 1 at 2025-10-16T06:28:30Z; YWPS_U3 voltage_kv=19.975 kV at 2025-10-16T06:28:20Z. Fresh current measurements agree with the given event; original transition detection was not required. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: verify_restoration, notify_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| YWPS_U3 / active_power_mw | 2025-10-16T06:26:00Z | 2025-10-16T06:26:00Z | 0.0 | MW | e-128cc0e3ba762e6d0f210c2c |
| YWPS_U3 / active_power_mw | 2025-10-16T06:28:30Z | 2025-10-16T06:28:30Z | 45.057 | MW | e-24509b3cc2cea46e8a925612 |
| YWPS_U3 / breaker_closed | 2025-10-16T06:26:00Z | 2025-10-16T06:26:02Z | 0.0 | 1 | e-443c60918c8f1ee7a3bda18a |
| YWPS_U3 / breaker_closed | 2025-10-16T06:28:30Z | 2025-10-16T06:28:30Z | 1.0 | 1 | e-336c207483f4c370312bd09e |
| YWPS_U3 / voltage_kv | 2025-10-16T06:26:00Z | 2025-10-16T06:26:01Z | 0.0 | kV | e-883571c3b4afc1bef79d2079 |
| YWPS_U3 / voltage_kv | 2025-10-16T06:28:20Z | 2025-10-16T06:28:21Z | 19.975 | kV | e-a8024e348704cf23c8c7fd42 |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 118; complete True; first six evidence IDs ["e-128cc0e3ba762e6d0f210c2c", "e-443c60918c8f1ee7a3bda18a", "e-883571c3b4afc1bef79d2079", "e-b83b436733fbe5f37262b477", "e-d95ef819b214bdaa68aa858e", "e-186ca79e797c6cc4c038db8a"]; quality counts {"good": 5}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 4; complete True; first six evidence IDs ["e-9487a3f5da929b7384bd9f0b", "e-81e151a8e5e532da70d55879", "e-a68b8991d9d781ea574aac0f", "e-bf2198fe99b69db89281ddb9"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 3; complete True; first six evidence IDs ["e-4e87146b1efe9b82f8dda348", "e-53a91b779566f65d88fda549", "e-96daa753d7be7bcab0189097"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 118; complete True; first six evidence IDs ["e-128cc0e3ba762e6d0f210c2c", "e-443c60918c8f1ee7a3bda18a", "e-883571c3b4afc1bef79d2079", "e-b83b436733fbe5f37262b477", "e-d95ef819b214bdaa68aa858e", "e-186ca79e797c6cc4c038db8a"]; quality counts {"good": 5}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 4; complete True; first six evidence IDs ["e-9487a3f5da929b7384bd9f0b", "e-81e151a8e5e532da70d55879", "e-a68b8991d9d781ea574aac0f", "e-bf2198fe99b69db89281ddb9"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 3; complete True; first six evidence IDs ["e-4e87146b1efe9b82f8dda348", "e-53a91b779566f65d88fda549", "e-96daa753d7be7bcab0189097"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 31; complete True; first six evidence IDs ["e-fb6a5c024c5a461473db3a63", "e-97b50c5510b78c423b07422f", "e-a73b9acab61e081a31756e96", "e-fb056cc5b16a5b61fb21b9da", "e-09270172b790df8757b1276b", "e-1d47c1f4aac82fb750eb9b9a"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, restoration, assets ["YWPS_U3"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, restoration, assets ["YWPS_U3"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, restoration, assets ["YWPS_U3"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, restoration, assets ["YWPS_U3"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-475f2ca4571736799e0c (s010)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: knowledge-tool-unavailable.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 01 [AS_WR_VENT_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 01 [AS_YW_CHARGER_01, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:37:29Z (2025-10-16T13:37:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["YWPS_U4", "YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "tooling_gap", "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["YWPS_U4"], "available_at": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "notification_id": "e-e8be85d63807870fd3be955e", "origin": "simulated_operator_notification", "synthetic": true}, {"asset_ids": ["YWPS_U3"], "available_at": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"}, "event_type": "generator_trip", "notification_id": "e-742ede2c81cfc6ddd8767d1d", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "generation_disconnection". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:f0c254aa-a611-5f75-8f77-d0f58ba8ea63 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1773c911-0841-5653-99e1-26c746ada2d1 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event yallourn-unit4-trip: 16 October 2025, 1334.29 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.
Source event yallourn-unit3-trip: 16 October 2025, 1334.32 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit4-trip: later classification "Protection/control system (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "Cooling water loss followed unintended valve operation. Actuator control circuit damage was likely due to long-term flooding; power loss alone does not establish this cause."}.
- Historical action yallourn-support-direction: Historical direction to Jeeralang A2, A3, B3 for system strength; not a fixture dispatch command. Time: 16 October 2025, 1350 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a2-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-b3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1405 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-direction-cancellation: Directions cancelled at 1755, effective from 1800. No generation stop at 1800 is inferred. Time: 16 October 2025, 1755 hrs AEST; effective 1800 hrs; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-actuator-isolation: Reported permanent electrical isolation by EnergyAustralia; no exact time available and no replay control action. Time: Immediately following the incident; precision: unavailable; uncertainty: No exact simulated isolation time or live isolation state is inferred..
- yallourn-unit3-trip: later classification "Protection/control system (later report classification)"; later cause {"available_at": "2026-08-01T00:00:00Z", "same_as_event": "yallourn-unit4-trip", "status": "later_investigation"}.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source events and the scenario's generator/busbar subject class; associated transformers remain context. Notifications are assumed available at cutoff, not dated by report publication, and establish neither current state, prerequisites nor cause.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 12, "scada": 6570, "topology": 781}
Reference produced: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "communication": {"asset_ids": ["YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "decision_time": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "evidence_ids": ["e-117ff31acc016c1c9f1c0264", "e-28bc2203d27ed883d152875a", "e-3c6d6891407664154e11eb03", "e-5c1b38b3c3226af971c50138", "e-742ede2c81cfc6ddd8767d1d", "e-7e479428b2b5622fa4e71da0", "e-cc6b86892b596dee11d79f57", "e-dcf83c4dcb42ab23b84dc3cf", "e-e8be85d63807870fd3be955e", "e-efb8d5820aa7a2ca12898ccc"], "next_steps": ["request_tool_access", "escalate_to_operator"], "notification_ids": ["e-742ede2c81cfc6ddd8767d1d", "e-e8be85d63807870fd3be955e"], "state": "verified"}, "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_time": null, "event_type": "generator_trip", "gap": "tooling_gap", "hypotheses": [], "message": "Given simulated notifications: generator_trip for YWPS_U4 in [2025-10-16T03:34:29Z, 2025-10-16T03:34:30Z); generator_trip for YWPS_U3 in [2025-10-16T03:34:32Z, 2025-10-16T03:34:33Z). As of 2025-10-16T03:37:29Z, current state is verified: YWPS_U3 active_power_mw=0.0 MW at 2025-10-16T03:37:19Z; YWPS_U3 breaker_closed=0.0 1 at 2025-10-16T03:37:19Z; YWPS_U3 voltage_kv=0.0 kV at 2025-10-16T03:37:19Z; YWPS_U4 active_power_mw=0.0 MW at 2025-10-16T03:37:19Z; YWPS_U4 breaker_closed=0.0 1 at 2025-10-16T03:37:19Z; YWPS_U4 voltage_kv=0.0 kV at 2025-10-16T03:37:19Z. Policy tool is unavailable; request access before recommendations. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: request_tool_access, escalate_to_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "event"}
Pass: True; observed gap: tooling_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| YWPS_U3 / active_power_mw | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 298.792 | MW | e-cb143cb1c259e883c66b128f |
| YWPS_U3 / active_power_mw | 2025-10-16T03:37:19Z | 2025-10-16T03:37:19Z | 0.0 | MW | e-dcf83c4dcb42ab23b84dc3cf |
| YWPS_U3 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:33:01Z | 1.0 | 1 | e-7ecc51741f104cd84be8df64 |
| YWPS_U3 / breaker_closed | 2025-10-16T03:37:19Z | 2025-10-16T03:37:19Z | 0.0 | 1 | e-efb8d5820aa7a2ca12898ccc |
| YWPS_U3 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 20.014 | kV | e-a7bdd040cbfdd20a65e6ea6b |
| YWPS_U3 / voltage_kv | 2025-10-16T03:37:19Z | 2025-10-16T03:37:21Z | 0.0 | kV | e-3c6d6891407664154e11eb03 |
| YWPS_U4 / active_power_mw | 2025-10-16T03:32:59Z | 2025-10-16T03:33:00Z | 298.11 | MW | e-7caa381b913065acd3de5f52 |
| YWPS_U4 / active_power_mw | 2025-10-16T03:37:19Z | 2025-10-16T03:37:21Z | 0.0 | MW | e-5c1b38b3c3226af971c50138 |
| YWPS_U4 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 1.0 | 1 | e-8c9f07533261796863a9eae0 |
| YWPS_U4 / breaker_closed | 2025-10-16T03:37:19Z | 2025-10-16T03:37:20Z | 0.0 | 1 | e-28bc2203d27ed883d152875a |
| YWPS_U4 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:33:01Z | 19.999 | kV | e-31fc8dd35e2b54faaa5f615c |
| YWPS_U4 / voltage_kv | 2025-10-16T03:37:19Z | 2025-10-16T03:37:19Z | 0.0 | kV | e-cc6b86892b596dee11d79f57 |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 390; complete True; first six evidence IDs ["e-31fc8dd35e2b54faaa5f615c", "e-6d6ef0e01fd40abcbce2d046", "e-7caa381b913065acd3de5f52", "e-7ecc51741f104cd84be8df64", "e-8c9f07533261796863a9eae0", "e-9926382f4702d3b10af9fdbb"]; quality counts {"good": 10}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-7e479428b2b5622fa4e71da0", "e-117ff31acc016c1c9f1c0264"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome denied; rows 0; complete None; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.

## c-202b1618bea17541cec9 (s011)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: vital-data-missing.
Assets: Wattle Reach Station-service charger AC input 01 [AS_WR_CHARGER_01, auxiliary]; Wattle Reach Station-service ventilation feeder 03 [AS_WR_VENT_03, auxiliary]; Yallourn W Station-service charger AC input 03 [AS_YW_CHARGER_03, auxiliary]; Yallourn W Station-service ventilation feeder 01 [AS_YW_VENT_01, auxiliary]; Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]; Yallourn W east general services feeder [SS_YW_E1, auxiliary]; Yallourn W east workshop machines feeder [SS_YW_E2, auxiliary]; Yallourn W east stores lighting feeder [SS_YW_E3, auxiliary]; Yallourn W west materials handling feeder [SS_YW_W1, auxiliary]; Yallourn W west building ventilation feeder [SS_YW_W2, auxiliary]; Yallourn W west utility services feeder [SS_YW_W3, auxiliary]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): [{"asset_ids": ["YWPS_U4"], "available_at": "2025-10-16T03:35:59Z", "event_interval": {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "notification_id": "e-6c23f555ece2a65411be3816", "origin": "simulated_operator_notification", "synthetic": true}, {"asset_ids": ["YWPS_U3"], "available_at": "2025-10-16T03:35:59Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"}, "event_type": "generator_trip", "notification_id": "e-2a597ee3f7d06458fee9fc5d", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_WR_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:50b4c519-4645-5cdd-a3cd-56a93f52c685 |
| AS_WR_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:523e570b-d0fa-52a7-a446-c07840c7c733 |
| AS_YW_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a5f5d841-8551-52db-8e77-f27873f99154 |
| AS_YW_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:42350635-5810-5d35-940f-84518c711627 |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |
| SS_YW_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fda4ba60-c397-57df-8431-79cd1f51a23b |
| SS_YW_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:3f13603b-9e7f-5dd9-9d37-57884b64c535 |
| SS_YW_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ffabb70f-9d75-59d5-94d8-6b58e50c92d5 |
| SS_YW_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:0086e6b4-8014-5e1a-aa69-a519400d68dc |
| SS_YW_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:53060aee-b39b-555c-b3ab-347118375603 |
| SS_YW_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:58f7785a-3612-509f-ac99-8055d92ffe46 |
| YWPS_COOLING | YWPS unit 3 and unit 4 common cooling system | available, cooling_flow_pct | synthetic only; urn:uuid:0678ec06-1bf0-5e46-a0f6-cca4528503f5 |
| YWPS_T3 | unit 3 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:80a3e32c-603b-52c6-b5f9-35d0c1860d32 |
| YWPS_T4 | unit 4 220/20 kV transformer | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:98140c6e-6b1a-5ca2-8232-a8829b62a086 |
| YWPS_U1 | YWPS unit 1, Yallourn unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45107198-3cbe-5bf5-93cf-f2fbd67f4bd8 |
| YWPS_U2 | YWPS unit 2, Yallourn unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:45a4e530-5113-5958-afb0-e4bcf4cd6530 |
| YWPS_U3 | YWPS unit 3, Yallourn unit 3 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:d4e47430-978e-50ef-996f-d38f66bbe980 |
| YWPS_U4 | YWPS unit 4, Yallourn unit 4 | active_power_mw, available, breaker_closed, vacuum_kpa, voltage_kv | synthetic only; urn:uuid:a4a6698f-04e5-53c0-a661-5de27d70c776 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event yallourn-unit4-trip: 16 October 2025, 1334.29 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.
Source event yallourn-unit3-trip: 16 October 2025, 1334.32 hrs AEST; second precision; UTC interval {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"} (exclusive end).
Source reference yallourn page 3; PDF SHA-256 1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20; extraction SHA-256 e63e6c2dac31ce6b5080aeafb623eeffec6761815242ceb947a0cc470815c86b. Exact quote: private provenance.

Later/investigator truth, not early inference:
- yallourn-unit4-trip: later classification "Protection/control system (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "Cooling water loss followed unintended valve operation. Actuator control circuit damage was likely due to long-term flooding; power loss alone does not establish this cause."}.
- Historical action yallourn-support-direction: Historical direction to Jeeralang A2, A3, B3 for system strength; not a fixture dispatch command. Time: 16 October 2025, 1350 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a2-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-a3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1401 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action jeeralang-b3-synchronized: Reported synchronization, not a report-backed MW output. Time: 16 October 2025, 1405 hrs AEST; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-direction-cancellation: Directions cancelled at 1755, effective from 1800. No generation stop at 1800 is inferred. Time: 16 October 2025, 1755 hrs AEST; effective 1800 hrs; precision: minute; uncertainty: none additionally asserted.
- Historical action yallourn-actuator-isolation: Reported permanent electrical isolation by EnergyAustralia; no exact time available and no replay control action. Time: Immediately following the incident; precision: unavailable; uncertainty: No exact simulated isolation time or live isolation state is inferred..
- yallourn-unit3-trip: later classification "Protection/control system (later report classification)"; later cause {"available_at": "2026-08-01T00:00:00Z", "same_as_event": "yallourn-unit4-trip", "status": "later_investigation"}.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source events and the scenario's generator/busbar subject class; associated transformers remain context. Notifications are assumed available at cutoff, not dated by report publication, and establish neither current state, prerequisites nor cause.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "absent", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 6, "knowledge": 4, "scada": 3987, "topology": 733}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": ["YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "communication": {"asset_ids": ["YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "decision_time": "2025-10-16T03:35:59Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "evidence_ids": ["e-2a597ee3f7d06458fee9fc5d", "e-6c23f555ece2a65411be3816"], "next_steps": ["request_missing_data", "escalate_to_operator"], "notification_ids": ["e-2a597ee3f7d06458fee9fc5d", "e-6c23f555ece2a65411be3816"], "state": "unverified"}, "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_time": null, "event_type": "generator_trip", "gap": "data_gap", "hypotheses": [], "message": "Given simulated notifications: generator_trip for YWPS_U4 in [2025-10-16T03:34:29Z, 2025-10-16T03:34:30Z); generator_trip for YWPS_U3 in [2025-10-16T03:34:32Z, 2025-10-16T03:34:33Z). As of 2025-10-16T03:35:59Z, current state is unverified: no verified current measurements. YWPS_U3 lacks a fresh usable post-notification active_power_mw sample. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: request_missing_data, escalate_to_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {"bad": 4, "missing": 4}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.

## c-da814412ade714bd7cda (s012)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: initial-transition.
Assets: Murray Station-service charger AC input 01 [AS_MY_CHARGER_01, auxiliary]; Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:10Z (2026-01-29T10:09:10+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "busbar_deenergization". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fa7e055c-6474-5bc8-85b5-1d292ecfb136 |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: confirm_event, review_protection_work, consult_limit_advice, apply_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Separate busbar availability from already-offline generation; review protection work and temporary line-rating advice without asserting a confirmed cause.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 9, "knowledge": 6, "scada": 1867, "topology": 599}
Reference produced: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "busbar_deenergization", "event_time": "2026-01-29T00:08:30Z", "event_type": "busbar_trip", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| MURRAY_5B2 / breaker_closed | 2026-01-29T00:06:30Z | 2026-01-29T00:06:30Z | 1.0 | 1 | e-c44fcd3bd6239e1e7741eff0 |
| MURRAY_5B2 / breaker_closed | 2026-01-29T00:09:00Z | 2026-01-29T00:09:01Z | 0.0 | 1 | e-b147f362418720119879b9e3 |
| MURRAY_5B2 / voltage_kv | 2026-01-29T00:06:30Z | 2026-01-29T00:06:30Z | 329.596 | kV | e-c2b4cbca81c1cc616efa5d4f |
| MURRAY_5B2 / voltage_kv | 2026-01-29T00:09:00Z | 2026-01-29T00:09:01Z | 0.0 | kV | e-5a167c7648dfe26c2f8f4fa6 |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 1867; complete True; first six evidence IDs ["e-0dfd02931c6533e5be0aea79", "e-121de1ddf2c0cbccebb88475", "e-12c68feeec5af8e48911ac67", "e-15abc28e2435f7e100b6caed", "e-1b16cb306e4cb299c1b4ad79", "e-1d5c5a0471a883393ae7a8fe"]; quality counts {"good": 101}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 9; complete True; first six evidence IDs ["e-d8f5801a534c931e6d348bcd", "e-d87f59e9fe28b69c623dd0c6", "e-18f3babd64d066d667131c99", "e-8b156129624b29a970cc2438", "e-d8e418501bbf3b37f7dd8c5c", "e-cd612b195f8883a0e731286a"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-04539d99ec4c35a28dbd (s013)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: correlated-state.
Assets: Murray Station-service charger AC input 01 [AS_MY_CHARGER_01, auxiliary]; Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 01 [AS_QB_VENT_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "busbar_deenergization". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fa7e055c-6474-5bc8-85b5-1d292ecfb136 |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:041918b6-da23-504a-af4d-f831a9e7cd0c |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: confirm_event, review_protection_work, consult_limit_advice, apply_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Separate busbar availability from already-offline generation; review protection work and temporary line-rating advice without asserting a confirmed cause.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": true, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 11, "knowledge": 6, "scada": 2650, "topology": 623}
Reference produced: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "busbar_deenergization", "event_time": "2026-01-29T00:08:30Z", "event_type": "busbar_trip", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| MURRAY_5B2 / breaker_closed | 2026-01-29T00:06:30Z | 2026-01-29T00:06:30Z | 1.0 | 1 | e-17a2fbb4063e7b0e2a6a42e5 |
| MURRAY_5B2 / breaker_closed | 2026-01-29T00:09:20Z | 2026-01-29T00:09:20Z | 0.0 | 1 | e-d1acc96f3619161d3fae258f |
| MURRAY_5B2 / voltage_kv | 2026-01-29T00:06:30Z | 2026-01-29T00:06:30Z | 329.596 | kV | e-480d0836aa7123f81d8b8cbd |
| MURRAY_5B2 / voltage_kv | 2026-01-29T00:09:30Z | 2026-01-29T00:09:30Z | 0.0 | kV | e-15472a5d821ab25bfa848680 |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 2650; complete True; first six evidence IDs ["e-00ccc6f2e353ecd5647f4985", "e-00ce16b132cf5e5636ae8c71", "e-074e9b59f247983f25830219", "e-077d7bbcf2e9ee548f0e9fbd", "e-117daaaf220149f30623e629", "e-1515af6f87f899936af80317"]; quality counts {"good": 106}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 11; complete True; first six evidence IDs ["e-f3231a9bfa1c84baf4a3a3dc", "e-a1ea340c24504bd8f85657db", "e-92d79d5e52357972aac60480", "e-d38b325f87e1c5877d5c9186", "e-c5cc7b9358bac9a96ea68b9d", "e-02df1a71068bbd0739d47612"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-b61875d651d61ed4e689 (s014)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: restoration.
Assets: Murray Station-service charger AC input 01 [AS_MY_CHARGER_01, auxiliary]; Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T01:17:00Z (2026-01-29T11:17:00+10:00 AEST); decision 2026-01-29T01:19:15Z (2026-01-29T11:19:15+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "return_to_service". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fa7e055c-6474-5bc8-85b5-1d292ecfb136 |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: verify_restoration, remove_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Verify the restored busbar and applicable limits before recommending removal of temporary EMS ratings.

Source event murray-busbar-restoration: 29 January 2026, 1118 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-restoration: later classification "Reported return to service"; later cause null.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 12, "knowledge": 6, "scada": 1814, "topology": 599}
Reference produced: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "return_to_service", "event_time": "2026-01-29T01:18:30Z", "event_type": "restoration", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| MURRAY_5B2 / breaker_closed | 2026-01-29T01:17:00Z | 2026-01-29T01:17:02Z | 0.0 | 1 | e-70ff633be4400bf57d85977a |
| MURRAY_5B2 / breaker_closed | 2026-01-29T01:19:15Z | 2026-01-29T01:19:15Z | 1.0 | 1 | e-231ddf5f7232acdb6e001ee9 |
| MURRAY_5B2 / voltage_kv | 2026-01-29T01:17:00Z | 2026-01-29T01:17:01Z | 0.0 | kV | e-f53a5edd324a53676224ffd0 |
| MURRAY_5B2 / voltage_kv | 2026-01-29T01:19:15Z | 2026-01-29T01:19:15Z | 330.269 | kV | e-4ebf6b706d2753bc34df65ed |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 1814; complete True; first six evidence IDs ["e-00bc401dfa8f63d743f3cdac", "e-0102983ae863c18b7c0209b7", "e-069cafbbd52dbeac79993dee", "e-07469a1a98febc1c9d241127", "e-09914285b964d8437869d88a", "e-0d6da10200260ad799c2705a"]; quality counts {"good": 101}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 12; complete True; first six evidence IDs ["e-4761918ee34d4c3520276813", "e-6d52746a0b6506df6de8e6e5", "e-5a5294cdffd4df69ce638c69", "e-845b92f5310938568f11288a", "e-ea3ed43fc9f2503721d34097", "e-4be29f8e9fb042c714e22b09"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, restoration, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-a5d2a598c634c133700d (s015)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: normal-baseline.
Assets: Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T00:03:00Z (2026-01-29T10:03:00+10:00 AEST); decision 2026-01-29T00:05:00Z (2026-01-29T10:05:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 6, "knowledge": 6, "scada": 1354, "topology": 575}
Reference produced: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": null, "hypotheses": [], "message": "No qualifying unplanned transition in usable as-of samples; steady outages are not new trips.", "status": "no_event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 1354; complete True; first six evidence IDs ["e-01cad2313c8c279976827449", "e-0727379a544e542cc00a5423", "e-073d8d5be5f6eb6bc658175b", "e-0b080b0c1fabf98afc11b17c", "e-10c88dc8e261d941d0a30f5f", "e-14cdbe698e00d724621c148a"]; quality counts {"good": 96}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 6; complete True; first six evidence IDs ["e-b86730422ac8a90c36e67e69", "e-423a367658482ee6763ff0bb", "e-071f5d194808bc967c374e4f", "e-56130875c421d59bab2b532b", "e-27c2958aa5969529cda0aa60", "e-bd8f5caca94bce1f465336d9"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-5e54b90b9746120c4d91 (s016)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: preexisting-outage.
Assets: Murray Station-service charger AC input 01 [AS_MY_CHARGER_01, auxiliary]; Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Murray Station-service ventilation feeder 02 [AS_MY_VENT_02, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 01 [AS_QB_VENT_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T00:03:00Z (2026-01-29T10:03:00+10:00 AEST); decision 2026-01-29T00:05:00Z (2026-01-29T10:05:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fa7e055c-6474-5bc8-85b5-1d292ecfb136 |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_MY_VENT_02 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:2053f0b7-ce1e-53d0-a859-14b7b5ae4a17 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:041918b6-da23-504a-af4d-f831a9e7cd0c |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Benign planned/test alarm is invented. YWPS_U2 pre-existing unavailability is a fixture assumption, not resolved from diagram text order.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "benign", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 18, "knowledge": 6, "scada": 1534, "topology": 647}
Reference produced: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": null, "hypotheses": [], "message": "No qualifying unplanned transition in usable as-of samples; steady outages are not new trips.", "status": "no_event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 1534; complete True; first six evidence IDs ["e-0a2a29091e123a87dd1d5508", "e-0d638d5111768f5d89a688ab", "e-10a5bd25922a067603d177af", "e-1a74b1e7380ae772883abbdb", "e-22abc5fb672ed5e0d0189403", "e-2821623c225ffea864b469f4"]; quality counts {"good": 111}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 18; complete True; first six evidence IDs ["e-437574ee3951d897d4d03aa8", "e-dd3fe7937d4d7725c2f5d31f", "e-dde6696da0d43da9d2335c83", "e-8cf8e3a1700f021269a496c0", "e-9ff74061ec7ac1a5ea95582c", "e-c2fc941250d5ec8281d3830e"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-db74d7b0912ff22a2003 (s017)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: bad-and-stale-signals.
Assets: Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "absent", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 6, "knowledge": 6, "scada": 1949, "topology": 575}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 1949; complete True; first six evidence IDs ["e-01cfb563b4d7f71f8c60ba5b", "e-05193fed4e658e4f065c9448", "e-0de5fa19ea586efb288d5c3e", "e-12783ae1781d246333d29ec5", "e-12e5347f9cdb6dfd4e01c993", "e-1437dc1c9b03611d9d845d2b"]; quality counts {"bad": 1, "good": 93, "missing": 1}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 6; complete True; first six evidence IDs ["e-8943300025888035376960d8", "e-d788340eeda53669ebcbc96a", "e-78062c3ed202b491ae6bb8a3", "e-55fb3b0dc5976a8170589bd8", "e-de00d41d1f4cb4612bdd9d2f", "e-d43dd38b1b09a087b92a6cdb"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-9104378f208acc9c2747 (s018)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: late-alarms.
Assets: Murray Station-service charger AC input 01 [AS_MY_CHARGER_01, auxiliary]; Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fa7e055c-6474-5bc8-85b5-1d292ecfb136 |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "delayed", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "missing"}.
Public evidence row counts: {"alarms": 8, "knowledge": 6, "scada": 2009, "topology": 599}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 2009; complete True; first six evidence IDs ["e-01936c5d73343bbe932af9e3", "e-06ad63428f470b92d87f4856", "e-0a3e97ca4d8e77a8d9b8d4cd", "e-0e7db5385d0aef5a6b755ac5", "e-17f8dddaa77f7be094163c34", "e-1af6b79126b3d4cc6108586e"]; quality counts {"good": 98, "missing": 3}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 8; complete True; first six evidence IDs ["e-eda37982109712adb3a8d028", "e-32ac6288ce9e59f61dafcfbf", "e-2f2526ee713fc88e23c3bc3b", "e-bb8f6c588ad282505e8ceb49", "e-9a779b2d110d63979f5fe939", "e-8934654fdcd281af3285c255"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-5d12a794b4971bb7ccaf (s019)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: appropriate-response.
Assets: Murray Station-service charger AC input 01 [AS_MY_CHARGER_01, auxiliary]; Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:11:00Z (2026-01-29T10:11:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["confirm_event", "review_protection_work", "consult_limit_advice", "apply_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["MURRAY_5B2"], "available_at": "2026-01-29T00:11:00Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "notification_id": "e-881544f54095acb9fecfa1ab", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "busbar_deenergization". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fa7e055c-6474-5bc8-85b5-1d292ecfb136 |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: confirm_event, review_protection_work, consult_limit_advice, apply_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Separate busbar availability from already-offline generation; review protection work and temporary line-rating advice without asserting a confirmed cause.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source events and the scenario's generator/busbar subject class; associated transformers remain context. Notifications are assumed available at cutoff, not dated by report publication, and establish neither current state, prerequisites nor cause.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 9, "knowledge": 6, "scada": 2956, "topology": 599}
Reference produced: {"action_ids": ["confirm_event", "review_protection_work", "consult_limit_advice", "apply_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "busbar_deenergization", "communication": {"asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "decision_time": "2026-01-29T00:11:00Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "evidence_ids": ["e-01a3ab01228391cfe128c7e2", "e-08197f2af555809c58174675", "e-08c1fbf8018cd6c094cd6a46", "e-0b26c2185433df424b5e28c1", "e-0df597a786c1927f599f3731", "e-1300724d75c36ebe3d6219bc", "e-3c463663c00a6b25cb5705af", "e-41e45cc3568b134c0008d699", "e-4db9809811a652dc313b3fa3", "e-5e39c23e130d232a0dfbe887", "e-5f848d0a2619a0c5c9c09127", "e-62d70f143d96812bbc83b5e4", "e-66ea3a1edc8cb0476e79a52e", "e-7a6fa93e073f9a623ae8ce89", "e-804c8cf70afb09329482a85d", "e-842f507f4b84a80d9de5fbc2", "e-854498af1145d90e7491b745", "e-864c64db1411d315a423fb55", "e-873386539926a3af60f21900", "e-881544f54095acb9fecfa1ab", "e-8c94137db89790a710005211", "e-944c215d3a2a0a12e79d9d4f", "e-95a35f2e9d1a439954df930b", "e-96daa753d7be7bcab0189097", "e-9835938e4721c4a0a5b4c1a3", "e-a080de9833dc652a94146b69", "e-aee49928b5c42db6d0ac961f", "e-b0446ae5948372173aff3f9b", "e-b1abf94e6e5431a474400f02", "e-b35d42ae3d673591938a4181", "e-b845488bd4c617c4436008ea", "e-ba3569591741cbf3301b92cd", "e-c40a9ef18bd07df22c9bff5a", "e-d10c1bc983adfd8519d312ca", "e-d68477bbb4faa42adde5ca28", "e-d9320ef260da0a7a8fea6074", "e-e5a4c23818bef33601c09f46", "e-f3370518f2f3328fef506ac7"], "next_steps": ["confirm_event", "review_protection_work", "consult_limit_advice", "apply_temporary_line_ratings", "notify_operator"], "notification_ids": ["e-881544f54095acb9fecfa1ab"], "state": "verified"}, "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_time": null, "event_type": "busbar_trip", "gap": null, "hypotheses": [], "message": "Given simulated notifications: busbar_trip for MURRAY_5B2 in [2026-01-29T00:08:00Z, 2026-01-29T00:09:00Z). As of 2026-01-29T00:11:00Z, current state is verified: MURRAY_5B2 breaker_closed=0.0 1 at 2026-01-29T00:10:50Z; MURRAY_5B2 voltage_kv=0.0 kV at 2026-01-29T00:10:50Z. Fresh current measurements agree with the given event; original transition detection was not required. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: confirm_event, review_protection_work, consult_limit_advice, apply_temporary_line_ratings, notify_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| MURRAY_5B2 / breaker_closed | 2026-01-29T00:06:30Z | 2026-01-29T00:06:30Z | 1.0 | 1 | e-77feee0e35bf56b55b9986a7 |
| MURRAY_5B2 / breaker_closed | 2026-01-29T00:10:50Z | 2026-01-29T00:10:52Z | 0.0 | 1 | e-d68477bbb4faa42adde5ca28 |
| MURRAY_5B2 / voltage_kv | 2026-01-29T00:06:30Z | 2026-01-29T00:06:30Z | 329.596 | kV | e-fc4787544bc6b578a0cb39c8 |
| MURRAY_5B2 / voltage_kv | 2026-01-29T00:10:50Z | 2026-01-29T00:10:51Z | 0.0 | kV | e-d10c1bc983adfd8519d312ca |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 88; complete True; first six evidence IDs ["e-440b4ee9af8aa4f184f30fc2", "e-77feee0e35bf56b55b9986a7", "e-fc4787544bc6b578a0cb39c8", "e-b11221100874f1d3e9ce1c5a", "e-d1c2bc0246cbe15f2516a2fb", "e-f3639f18b21294b3a72157ed"]; quality counts {"good": 3}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-b845488bd4c617c4436008ea"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 3; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-96daa753d7be7bcab0189097", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 88; complete True; first six evidence IDs ["e-440b4ee9af8aa4f184f30fc2", "e-77feee0e35bf56b55b9986a7", "e-fc4787544bc6b578a0cb39c8", "e-b11221100874f1d3e9ce1c5a", "e-d1c2bc0246cbe15f2516a2fb", "e-f3639f18b21294b3a72157ed"]; quality counts {"good": 3}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-b845488bd4c617c4436008ea"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 3; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-96daa753d7be7bcab0189097", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 31; complete True; first six evidence IDs ["e-01a3ab01228391cfe128c7e2", "e-944c215d3a2a0a12e79d9d4f", "e-c40a9ef18bd07df22c9bff5a", "e-0b26c2185433df424b5e28c1", "e-4db9809811a652dc313b3fa3", "e-62d70f143d96812bbc83b5e4"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-d4ba8661af4f9290119c (s020)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: restoration-response.
Assets: Murray Station-service charger AC input 01 [AS_MY_CHARGER_01, auxiliary]; Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T01:17:00Z (2026-01-29T11:17:00+10:00 AEST); decision 2026-01-29T01:19:30Z (2026-01-29T11:19:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["verify_restoration", "remove_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["MURRAY_5B2"], "available_at": "2026-01-29T01:19:30Z", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "notification_id": "e-95fa43d833fa7b028ff9c9b1", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "return_to_service". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fa7e055c-6474-5bc8-85b5-1d292ecfb136 |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: verify_restoration, remove_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Verify the restored busbar and applicable limits before recommending removal of temporary EMS ratings.

Source event murray-busbar-restoration: 29 January 2026, 1118 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-restoration: later classification "Reported return to service"; later cause null.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source events and the scenario's generator/busbar subject class; associated transformers remain context. Notifications are assumed available at cutoff, not dated by report publication, and establish neither current state, prerequisites nor cause.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 12, "knowledge": 6, "scada": 1792, "topology": 599}
Reference produced: {"action_ids": ["verify_restoration", "remove_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "return_to_service", "communication": {"asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "decision_time": "2026-01-29T01:19:30Z", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "evidence_ids": ["e-01a3ab01228391cfe128c7e2", "e-08197f2af555809c58174675", "e-08c1fbf8018cd6c094cd6a46", "e-0b26c2185433df424b5e28c1", "e-0df597a786c1927f599f3731", "e-1300724d75c36ebe3d6219bc", "e-1cb666ecfaca16f718dd8094", "e-3c463663c00a6b25cb5705af", "e-41e45cc3568b134c0008d699", "e-4d8ab3d24ab7a0ba31bfa3de", "e-4db9809811a652dc313b3fa3", "e-5e39c23e130d232a0dfbe887", "e-5f848d0a2619a0c5c9c09127", "e-62d70f143d96812bbc83b5e4", "e-66ea3a1edc8cb0476e79a52e", "e-7a6fa93e073f9a623ae8ce89", "e-804c8cf70afb09329482a85d", "e-842f507f4b84a80d9de5fbc2", "e-854498af1145d90e7491b745", "e-864c64db1411d315a423fb55", "e-873386539926a3af60f21900", "e-8c94137db89790a710005211", "e-944c215d3a2a0a12e79d9d4f", "e-95a35f2e9d1a439954df930b", "e-95fa43d833fa7b028ff9c9b1", "e-96daa753d7be7bcab0189097", "e-9835938e4721c4a0a5b4c1a3", "e-a080de9833dc652a94146b69", "e-aee49928b5c42db6d0ac961f", "e-b0446ae5948372173aff3f9b", "e-b1abf94e6e5431a474400f02", "e-b35d42ae3d673591938a4181", "e-ba3569591741cbf3301b92cd", "e-c40a9ef18bd07df22c9bff5a", "e-d9320ef260da0a7a8fea6074", "e-e160c951f9de48e92a59ae75", "e-e5a4c23818bef33601c09f46", "e-f3370518f2f3328fef506ac7"], "next_steps": ["verify_restoration", "remove_temporary_line_ratings", "notify_operator"], "notification_ids": ["e-95fa43d833fa7b028ff9c9b1"], "state": "verified"}, "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_time": null, "event_type": "restoration", "gap": null, "hypotheses": [], "message": "Given simulated notifications: restoration for MURRAY_5B2 in [2026-01-29T01:18:00Z, 2026-01-29T01:19:00Z). As of 2026-01-29T01:19:30Z, current state is verified: MURRAY_5B2 breaker_closed=1.0 1 at 2026-01-29T01:19:20Z; MURRAY_5B2 voltage_kv=329.691 kV at 2026-01-29T01:19:30Z. Fresh current measurements agree with the given event; original transition detection was not required. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: verify_restoration, remove_temporary_line_ratings, notify_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| MURRAY_5B2 / breaker_closed | 2026-01-29T01:17:00Z | 2026-01-29T01:17:02Z | 0.0 | 1 | e-211e239aed6e7a9da62b7ded |
| MURRAY_5B2 / breaker_closed | 2026-01-29T01:19:20Z | 2026-01-29T01:19:21Z | 1.0 | 1 | e-1cb666ecfaca16f718dd8094 |
| MURRAY_5B2 / voltage_kv | 2026-01-29T01:17:00Z | 2026-01-29T01:17:01Z | 0.0 | kV | e-1a49bc34ec2ee51fe4f903ab |
| MURRAY_5B2 / voltage_kv | 2026-01-29T01:19:30Z | 2026-01-29T01:19:30Z | 329.691 | kV | e-4d8ab3d24ab7a0ba31bfa3de |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 52; complete True; first six evidence IDs ["e-1a49bc34ec2ee51fe4f903ab", "e-211e239aed6e7a9da62b7ded", "e-ee3bd1426b8c66cad5fdbfce", "e-1a48a8ba3836a49ce1d84747", "e-b8330d1a5891063c489938fd", "e-f0591b4f2ec957144063d112"]; quality counts {"good": 3}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 4; complete True; first six evidence IDs ["e-7abfd3a4b622c5954968ecd8", "e-e177bbd3488f140918c6a69e", "e-e160c951f9de48e92a59ae75", "e-93924b373d823742f4b0302f"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 3; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-96daa753d7be7bcab0189097", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 52; complete True; first six evidence IDs ["e-1a49bc34ec2ee51fe4f903ab", "e-211e239aed6e7a9da62b7ded", "e-ee3bd1426b8c66cad5fdbfce", "e-1a48a8ba3836a49ce1d84747", "e-b8330d1a5891063c489938fd", "e-f0591b4f2ec957144063d112"]; quality counts {"good": 3}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 4; complete True; first six evidence IDs ["e-7abfd3a4b622c5954968ecd8", "e-e177bbd3488f140918c6a69e", "e-e160c951f9de48e92a59ae75", "e-93924b373d823742f4b0302f"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 3; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-96daa753d7be7bcab0189097", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 31; complete True; first six evidence IDs ["e-01a3ab01228391cfe128c7e2", "e-944c215d3a2a0a12e79d9d4f", "e-c40a9ef18bd07df22c9bff5a", "e-0b26c2185433df424b5e28c1", "e-4db9809811a652dc313b3fa3", "e-62d70f143d96812bbc83b5e4"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, restoration, assets ["MURRAY_5B2"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, restoration, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, restoration, assets ["MURRAY_5B2"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, restoration, assets ["MURRAY_5B2"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-97632d985dd7836bafc1 (s021)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: knowledge-tool-unavailable.
Assets: Murray Station-service charger AC input 01 [AS_MY_CHARGER_01, auxiliary]; Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:11:00Z (2026-01-29T10:11:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "tooling_gap", "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["MURRAY_5B2"], "available_at": "2026-01-29T00:11:00Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "notification_id": "e-8ac5dae6f8459e5df1e465bd", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "busbar_deenergization". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fa7e055c-6474-5bc8-85b5-1d292ecfb136 |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source events and the scenario's generator/busbar subject class; associated transformers remain context. Notifications are assumed available at cutoff, not dated by report publication, and establish neither current state, prerequisites nor cause.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 9, "scada": 2956, "topology": 599}
Reference produced: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "busbar_deenergization", "communication": {"asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "decision_time": "2026-01-29T00:11:00Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "evidence_ids": ["e-8ac5dae6f8459e5df1e465bd", "e-b74bed698bbc86fe64530304", "e-c5bfd8f4567e7484ea7f4db8", "e-fc859ccc52e647aaf521aefa"], "next_steps": ["request_tool_access", "escalate_to_operator"], "notification_ids": ["e-8ac5dae6f8459e5df1e465bd"], "state": "verified"}, "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_time": null, "event_type": "busbar_trip", "gap": "tooling_gap", "hypotheses": [], "message": "Given simulated notifications: busbar_trip for MURRAY_5B2 in [2026-01-29T00:08:00Z, 2026-01-29T00:09:00Z). As of 2026-01-29T00:11:00Z, current state is verified: MURRAY_5B2 breaker_closed=0.0 1 at 2026-01-29T00:10:50Z; MURRAY_5B2 voltage_kv=0.0 kV at 2026-01-29T00:10:50Z. Policy tool is unavailable; request access before recommendations. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: request_tool_access, escalate_to_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "event"}
Pass: True; observed gap: tooling_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| MURRAY_5B2 / breaker_closed | 2026-01-29T00:06:30Z | 2026-01-29T00:06:30Z | 1.0 | 1 | e-f5391f563c9507ebcc0e42b3 |
| MURRAY_5B2 / breaker_closed | 2026-01-29T00:10:50Z | 2026-01-29T00:10:52Z | 0.0 | 1 | e-c5bfd8f4567e7484ea7f4db8 |
| MURRAY_5B2 / voltage_kv | 2026-01-29T00:06:30Z | 2026-01-29T00:06:30Z | 329.596 | kV | e-ee9672d682cc693d466842b1 |
| MURRAY_5B2 / voltage_kv | 2026-01-29T00:10:50Z | 2026-01-29T00:10:51Z | 0.0 | kV | e-fc859ccc52e647aaf521aefa |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 88; complete True; first six evidence IDs ["e-ee9672d682cc693d466842b1", "e-f473a910910c23de30637c5b", "e-f5391f563c9507ebcc0e42b3", "e-2c29ab9455162fbe739685f9", "e-95f650fc68733b1eaed6cc95", "e-cdd218a4127fbda6747d3675"]; quality counts {"good": 3}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-b74bed698bbc86fe64530304"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome denied; rows 0; complete None; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.

## c-9767074947f0c2f3444a (s022)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: vital-data-missing.
Assets: Murray Station-service charger AC input 03 [AS_MY_CHARGER_03, auxiliary]; Murray Station-service ventilation feeder 01 [AS_MY_VENT_01, auxiliary]; Quartz Bend Station-service charger AC input 01 [AS_QB_CHARGER_01, auxiliary]; Quartz Bend Station-service ventilation feeder 03 [AS_QB_VENT_03, auxiliary]; Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]; Murray east general services feeder [SS_MU_E1, auxiliary]; Murray east machine hall lighting feeder [SS_MU_E2, auxiliary]; Murray east workshop machines feeder [SS_MU_E3, auxiliary]; Murray west gallery ventilation feeder [SS_MU_W1, auxiliary]; Murray west utility services feeder [SS_MU_W2, auxiliary]; Murray west stores handling feeder [SS_MU_W3, auxiliary]; Wattle Junction north general services feeder [SS_WJ_N1, auxiliary]; Wattle Junction north depot lighting feeder [SS_WJ_N2, auxiliary]; Wattle Junction south transfer drive feeder [SS_WJ_S1, auxiliary]; Wattle Junction south warehouse services feeder [SS_WJ_S2, auxiliary]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): [{"asset_ids": ["MURRAY_5B2"], "available_at": "2026-01-29T00:09:30Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "notification_id": "e-632e1e260d1e3d0a3eecfd76", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| AS_MY_CHARGER_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:ddf57bc7-bca8-5a7e-a3ea-f8ad3e319e59 |
| AS_MY_VENT_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1bc19b4f-48ed-5007-82d7-1c4b7e4d14f8 |
| AS_QB_CHARGER_01 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a8bd6c27-328c-55c9-89d0-90d41db1f6ce |
| AS_QB_VENT_03 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fce02cd6-3e85-51b7-a373-7ac92f25abb4 |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |
| SS_MU_E1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:24fe260d-4f66-5498-a313-7348cf0004b4 |
| SS_MU_E2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:1ee8bc50-d263-5715-b039-d77e798fc846 |
| SS_MU_E3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a641f9f4-4029-5906-bfd6-331033227920 |
| SS_MU_W1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c5508e9b-1c17-5367-87bf-80883c2be94a |
| SS_MU_W2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:67c405a1-fbc6-504b-8331-42904b29f8b1 |
| SS_MU_W3 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:a3e56868-65ed-53c9-913c-11f82909f8e7 |
| SS_WJ_N1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:fcffa5fc-fc5c-57f2-84d9-f5eb23ce7337 |
| SS_WJ_N2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:c61df5ae-2e1e-5219-9236-8bada8cfc4b1 |
| SS_WJ_S1 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:dfc3d2f1-da7b-5f1a-ab89-51f487837aaa |
| SS_WJ_S2 |  | active_power_mw, available, breaker_closed, flow_mva, voltage_kv | synthetic only; urn:uuid:064b3d0c-9eca-5b88-ba1a-028d8b7a358c |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source events and the scenario's generator/busbar subject class; associated transformers remain context. Notifications are assumed available at cutoff, not dated by report publication, and establish neither current state, prerequisites nor cause.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report.", "V3 instrument, acquisition and indication semantics are synthetic; see the time-valid maintenance dictionary. Source facts and expected outcomes are unchanged."]; parameters: {"alarm_mode": "absent", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 6, "knowledge": 6, "scada": 1949, "topology": 575}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "busbar_deenergization", "communication": {"asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "decision_time": "2026-01-29T00:09:30Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "evidence_ids": ["e-632e1e260d1e3d0a3eecfd76"], "next_steps": ["request_missing_data", "escalate_to_operator"], "notification_ids": ["e-632e1e260d1e3d0a3eecfd76"], "state": "unverified"}, "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_time": null, "event_type": "busbar_trip", "gap": "data_gap", "hypotheses": [], "message": "Given simulated notifications: busbar_trip for MURRAY_5B2 in [2026-01-29T00:08:00Z, 2026-01-29T00:09:00Z). As of 2026-01-29T00:09:30Z, current state is unverified: no verified current measurements. MURRAY_5B2 lacks a fresh usable post-notification breaker_closed sample. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: request_missing_data, escalate_to_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {"bad": 1, "missing": 1}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass True; gap None. No failed expectation.

