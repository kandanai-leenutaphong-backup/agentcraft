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
| power_only_detection.defer_action | 8 | 2 | 0.25 / 0.25 | 1.0 | 0.25 / 0.25 | 1.0 | 1.0 | 0 |
| reference | 8 | 5 | 0.625 / 0.625 | 1.0 | 0.625 / 0.625 | 1.0 | 1.0 | 0 |
| reference.confirm_cause | 8 | 2 | 0.625 / 0.625 | 1.0 | 0.625 / 0.625 | 1.0 | 0.625 | 3 |
| reference.deny_scada | 8 | 0 | 0.25 / 0.25 | 1.0 | 0.25 / 0.25 | 1.0 | 1.0 | 0 |
| reference.drop_records | 8 | 2 | 0.25 / 0.25 | 1.0 | 0.25 / 0.25 | 1.0 | 1.0 | 0 |
| reference.wrong_rule | 8 | 2 | 0.208333 / 0.25 | 1.0 | 0.25 / 0.625 | 0.625 | 0.625 | 0 |

All denominators include missing and failed predictions. Complete requests, returned evidence IDs, errors and per-case diagnoses: `replay/cases.jsonl`.

Baseline: power-only transition detection; action always defers for verification and operator escalation without querying tools. No action detection credit is awarded.
Correct expected insufficiency is a pass; a resource gap is not automatically a predictor failure. Required classification, cause status and gap must match without private defaults or undocumented alternatives.
Communication measures declared event/asset/interval/state/uncertainty/next-step fields; narrative usefulness remains human-reviewed. Safe refusals can satisfy prerequisite safety without satisfying the expected recommendation set.

## c-cfee5b92f5fae7b3358a (s001)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: initial-transition.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:34:31Z (2025-10-16T13:34:31+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["YWPS_U4"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "generation_disconnection". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 3, "scada": 703, "topology": 397}
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
| YWPS_U4 / voltage_kv | 2025-10-16T03:34:30Z | 2025-10-16T03:34:31Z | 0.0 | kV | e-f62add58c6cf56f74ae0baef |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 703; complete True; first six evidence IDs ["e-053f4413072a89aa3bfbf571", "e-095f54c939c874f3e9f3aa88", "e-0b4e11e97abeba859b2eb2be", "e-129b412608c92a93b75e4a31", "e-1d74f11e86a9df1780102e4c", "e-3130ee77e0d1955410036d72"]; quality counts {"good": 50}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-aacb041ecb03c29168b6b012"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: event, generator_trip, assets ["YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-7cf8e4a84e7026799eec (s002)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: correlated-state.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["YWPS_U4", "YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "generation_disconnection". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": true, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 2, "knowledge": 3, "scada": 1266, "topology": 397}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 1266; complete True; first six evidence IDs ["e-0437cac0028132d91bb0a5bb", "e-11312935c310519a00354ed1", "e-13a13f22ac65ecb77e628a6f", "e-1940a8c50e9c388347aaa1ed", "e-1eef856b37623ef742e86175", "e-1ef32cb94ba8e2cf200e30d0"]; quality counts {"good": 50}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-48ae95aa55987290d1ff56dd", "e-b2647f12ea2ab566ded7bd3a"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-b0f2e994ffc790a4942f (s003)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: restoration.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T06:26:00Z (2025-10-16T16:26:00+10:00 AEST); decision 2025-10-16T06:28:15Z (2025-10-16T16:28:15+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "return_to_service". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 3, "scada": 909, "topology": 397}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 909; complete True; first six evidence IDs ["e-0357f10bca7007486b2775cf", "e-092319a9fae91cf6f8fed58f", "e-0c89115a1b0dc25bef63c541", "e-0e2cdded8d1edd91938fe6c1", "e-0e6e4524f01bff15f0ab7511", "e-17156247ebcea683c75ecfd7"]; quality counts {"good": 50}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-40a8807595df79d0e0f3db0b"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: event, restoration, assets ["YWPS_U3"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, restoration, assets ["YWPS_U3"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-ff527e8df5079b5834cd (s004)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: normal-baseline.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:29:29Z (2025-10-16T13:29:29+10:00 AEST); decision 2025-10-16T03:31:29Z (2025-10-16T13:31:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 0, "knowledge": 3, "scada": 619, "topology": 397}
Reference produced: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": null, "hypotheses": [], "message": "No qualifying unplanned transition in usable as-of samples; steady outages are not new trips.", "status": "no_event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 619; complete True; first six evidence IDs ["e-095a46bf951add33badd601a", "e-0e2397e449f1f4b17abad380", "e-18b9ef75318ca97520bf742e", "e-1daf09b1f9f221c5b429142c", "e-24c0819371932983a33cd85e", "e-274593e87db22634800908d7"]; quality counts {"good": 50}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-1c1004a79b003317f3a8 (s005)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: preexisting-outage.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:29:29Z (2025-10-16T13:29:29+10:00 AEST); decision 2025-10-16T03:31:29Z (2025-10-16T13:31:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Benign planned/test alarm is invented. YWPS_U2 pre-existing unavailability is a fixture assumption, not resolved from diagram text order."]; parameters: {"alarm_mode": "benign", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 3, "scada": 619, "topology": 397}
Reference produced: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": null, "hypotheses": [], "message": "No qualifying unplanned transition in usable as-of samples; steady outages are not new trips.", "status": "no_event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 619; complete True; first six evidence IDs ["e-024d69e85146cdc70dccb716", "e-0af9c8ca94b0cb5fe85a8f2e", "e-125ddd17a9aed742878f7aba", "e-1488ef8e3ca345116ec19df4", "e-1e50714a07c98548bb55b7e5", "e-2717f0d5f12581ba434d3305"]; quality counts {"good": 50}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-0b308678d5f662ba494302e9"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-00ca0b3b957eb8180527 (s006)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: bad-and-stale-signals.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report."]; parameters: {"alarm_mode": "absent", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 0, "knowledge": 3, "scada": 807, "topology": 397}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 807; complete True; first six evidence IDs ["e-031b08d5bc7c1ccbe1ef9008", "e-1be3197ef4627afb930d3afe", "e-1c3e8f6f980ebb098fa24f45", "e-2c814ce92f6f234b2a25c502", "e-37c3cee3ba2c4b43bcce0791", "e-39b2e23ced77fd0430202791"]; quality counts {"bad": 7, "good": 32, "missing": 7, "stale": 4}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-a0e662af125a08d6bb12 (s007)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: late-alarms.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report."]; parameters: {"alarm_mode": "delayed", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "missing"}.
Public evidence row counts: {"alarms": 0, "knowledge": 3, "scada": 807, "topology": 397}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 807; complete True; first six evidence IDs ["e-0191c2ed6ca939b9b3256782", "e-03f814afd76e950171c98a03", "e-083b045b55191224240d1a4c", "e-0cfbf70ae94f942d3510282a", "e-128f445bd50d1aa78f700a42", "e-142c4b14bb31157f52fdf91a"]; quality counts {"good": 32, "missing": 18}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-d0fd593da0c54237ffbf (s008)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: appropriate-response.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:37:29Z (2025-10-16T13:37:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["confirm_event", "assess_system_strength", "consult_limit_advice", "request_authorized_support", "notify_operator", "investigate_cooling"], "asset_ids": ["YWPS_U4", "YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["YWPS_U4", "YWPS_T4"], "available_at": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "notification_id": "e-f09c3bf33a07068bac8d6f5d", "origin": "simulated_operator_notification", "synthetic": true}, {"asset_ids": ["YWPS_U3", "YWPS_T3"], "available_at": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"}, "event_type": "generator_trip", "notification_id": "e-385e031fb1c88e80a4c18a11", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "generation_disconnection". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source event definitions and assumed available at the decision cutoff. This synthetic availability does not date the report or establish current state, prerequisites or cause."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 2, "knowledge": 3, "scada": 1710, "topology": 397}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "communication": {"asset_ids": ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "decision_time": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "evidence_ids": ["e-385e031fb1c88e80a4c18a11", "e-f09c3bf33a07068bac8d6f5d"], "next_steps": ["request_missing_data", "escalate_to_operator"], "notification_ids": ["e-385e031fb1c88e80a4c18a11", "e-f09c3bf33a07068bac8d6f5d"], "state": "conflicting"}, "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_time": null, "event_type": "generator_trip", "gap": "data_gap", "hypotheses": [], "message": "Given simulated notifications: generator_trip for YWPS_U4, YWPS_T4 in [2025-10-16T03:34:29Z, 2025-10-16T03:34:30Z); generator_trip for YWPS_U3, YWPS_T3 in [2025-10-16T03:34:32Z, 2025-10-16T03:34:33Z). As of 2025-10-16T03:37:29Z, current state is conflicting: no verified current measurements. Notification type does not match the declared asset class for YWPS_T3. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: request_missing_data, escalate_to_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "insufficient_evidence"}
Pass: False; observed gap: data_gap; failure gap: logic_gap; failures: ["status: expected event, produced insufficient_evidence", "gap: expected None, produced data_gap", "action set differs from reviewed expectation/alternatives"].
Next diagnosis: Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| YWPS_T3 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 1.0 | 1 | e-722fff380572808b1d06c79e |
| YWPS_T3 / breaker_closed | 2025-10-16T03:37:29Z | 2025-10-16T03:37:29Z | 0.0 | 1 | e-117f4a4cd05a4f26acb1e088 |
| YWPS_T3 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 220.328 | kV | e-f10dc667eea9816b313343af |
| YWPS_T3 / voltage_kv | 2025-10-16T03:37:19Z | 2025-10-16T03:37:21Z | 0.0 | kV | e-64a03e1e03620c754e0dc8dc |
| YWPS_T4 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 1.0 | 1 | e-c28eeee4b8bc574af01b1632 |
| YWPS_T4 / breaker_closed | 2025-10-16T03:37:29Z | 2025-10-16T03:37:29Z | 0.0 | 1 | e-afca8175e5490745d4930ff9 |
| YWPS_T4 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 219.898 | kV | e-7767302c1b64dd1a2b64af83 |
| YWPS_T4 / voltage_kv | 2025-10-16T03:37:19Z | 2025-10-16T03:37:21Z | 0.0 | kV | e-7759a99f55c68e93815fb7f9 |
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
- Request {"asset_ids": ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 547; complete True; first six evidence IDs ["e-1dbfdbc5eced81b35f56ffb4", "e-3f561d4f959f8081d146924a", "e-5325dc70e145a27f4a8d0e53", "e-7070a6d8e961e9141d52e926", "e-722fff380572808b1d06c79e", "e-7767302c1b64dd1a2b64af83"]; quality counts {"good": 16}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.deny_scada: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-87aa835fc8754d9a773e (s009)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: restoration-response.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T06:26:00Z (2025-10-16T16:26:00+10:00 AEST); decision 2025-10-16T06:28:30Z (2025-10-16T16:28:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["verify_restoration", "notify_operator"], "asset_ids": ["YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["YWPS_U3", "YWPS_T3"], "available_at": "2025-10-16T06:28:30Z", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "notification_id": "e-34fa5d226d16713bbe743352", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "return_to_service". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source event definitions and assumed available at the decision cutoff. This synthetic availability does not date the report or establish current state, prerequisites or cause."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 3, "scada": 968, "topology": 397}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": ["YWPS_T3", "YWPS_U3"], "cause_status": "not_established", "classification": "return_to_service", "communication": {"asset_ids": ["YWPS_T3", "YWPS_U3"], "cause_status": "not_established", "decision_time": "2025-10-16T06:28:30Z", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "evidence_ids": ["e-34fa5d226d16713bbe743352"], "next_steps": ["request_missing_data", "escalate_to_operator"], "notification_ids": ["e-34fa5d226d16713bbe743352"], "state": "conflicting"}, "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_time": null, "event_type": "restoration", "gap": "data_gap", "hypotheses": [], "message": "Given simulated notifications: restoration for YWPS_U3, YWPS_T3 in [2025-10-16T06:27:00Z, 2025-10-16T06:28:00Z). As of 2025-10-16T06:28:30Z, current state is conflicting: no verified current measurements. Notification type does not match the declared asset class for YWPS_T3. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: request_missing_data, escalate_to_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "insufficient_evidence"}
Pass: False; observed gap: data_gap; failure gap: logic_gap; failures: ["status: expected event, produced insufficient_evidence", "gap: expected None, produced data_gap", "action set differs from reviewed expectation/alternatives"].
Next diagnosis: Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| YWPS_T3 / breaker_closed | 2025-10-16T06:26:00Z | 2025-10-16T06:26:02Z | 0.0 | 1 | e-1789bae95fa6dae5c1963c7c |
| YWPS_T3 / breaker_closed | 2025-10-16T06:28:20Z | 2025-10-16T06:28:22Z | 1.0 | 1 | e-1b5fa84a03481b584e056e58 |
| YWPS_T3 / voltage_kv | 2025-10-16T06:26:00Z | 2025-10-16T06:26:01Z | 0.0 | kV | e-3aec429b0bfc032f93d241c2 |
| YWPS_T3 / voltage_kv | 2025-10-16T06:28:20Z | 2025-10-16T06:28:20Z | 219.97 | kV | e-2bfc37e9d21f7d8c089876d4 |
| YWPS_U3 / active_power_mw | 2025-10-16T06:26:00Z | 2025-10-16T06:26:00Z | 0.0 | MW | e-128cc0e3ba762e6d0f210c2c |
| YWPS_U3 / active_power_mw | 2025-10-16T06:28:30Z | 2025-10-16T06:28:30Z | 45.057 | MW | e-24509b3cc2cea46e8a925612 |
| YWPS_U3 / breaker_closed | 2025-10-16T06:26:00Z | 2025-10-16T06:26:02Z | 0.0 | 1 | e-443c60918c8f1ee7a3bda18a |
| YWPS_U3 / breaker_closed | 2025-10-16T06:28:30Z | 2025-10-16T06:28:30Z | 1.0 | 1 | e-336c207483f4c370312bd09e |
| YWPS_U3 / voltage_kv | 2025-10-16T06:26:00Z | 2025-10-16T06:26:01Z | 0.0 | kV | e-883571c3b4afc1bef79d2079 |
| YWPS_U3 / voltage_kv | 2025-10-16T06:28:20Z | 2025-10-16T06:28:21Z | 19.975 | kV | e-a8024e348704cf23c8c7fd42 |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["YWPS_T3", "YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 155; complete True; first six evidence IDs ["e-128cc0e3ba762e6d0f210c2c", "e-1789bae95fa6dae5c1963c7c", "e-3aec429b0bfc032f93d241c2", "e-443c60918c8f1ee7a3bda18a", "e-485ff9c941c0769bae4cbb92", "e-883571c3b4afc1bef79d2079"]; quality counts {"good": 8}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, restoration, assets ["YWPS_T3", "YWPS_U3"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: insufficient_evidence, restoration, assets ["YWPS_T3", "YWPS_U3"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.deny_scada: insufficient_evidence, restoration, assets ["YWPS_T3", "YWPS_U3"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, restoration, assets ["YWPS_T3", "YWPS_U3"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: insufficient_evidence, restoration, assets ["YWPS_T3", "YWPS_U3"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-d3f7e76d8afe7479cf74 (s010)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: knowledge-tool-unavailable.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:37:29Z (2025-10-16T13:37:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["YWPS_U4", "YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "tooling_gap", "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["YWPS_U4", "YWPS_T4"], "available_at": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "notification_id": "e-e8be85d63807870fd3be955e", "origin": "simulated_operator_notification", "synthetic": true}, {"asset_ids": ["YWPS_U3", "YWPS_T3"], "available_at": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"}, "event_type": "generator_trip", "notification_id": "e-742ede2c81cfc6ddd8767d1d", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "generation_disconnection". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source event definitions and assumed available at the decision cutoff. This synthetic availability does not date the report or establish current state, prerequisites or cause."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 2, "scada": 1710, "topology": 397}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "communication": {"asset_ids": ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "decision_time": "2025-10-16T03:37:29Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "evidence_ids": ["e-742ede2c81cfc6ddd8767d1d", "e-e8be85d63807870fd3be955e"], "next_steps": ["request_missing_data", "escalate_to_operator"], "notification_ids": ["e-742ede2c81cfc6ddd8767d1d", "e-e8be85d63807870fd3be955e"], "state": "conflicting"}, "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_time": null, "event_type": "generator_trip", "gap": "data_gap", "hypotheses": [], "message": "Given simulated notifications: generator_trip for YWPS_U4, YWPS_T4 in [2025-10-16T03:34:29Z, 2025-10-16T03:34:30Z); generator_trip for YWPS_U3, YWPS_T3 in [2025-10-16T03:34:32Z, 2025-10-16T03:34:33Z). As of 2025-10-16T03:37:29Z, current state is conflicting: no verified current measurements. Notification type does not match the declared asset class for YWPS_T3. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: request_missing_data, escalate_to_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "insufficient_evidence"}
Pass: False; observed gap: data_gap; failure gap: tooling_gap; failures: ["status: expected event, produced insufficient_evidence", "gap: expected tooling_gap, produced data_gap", "action set differs from reviewed expectation/alternatives"].
Next diagnosis: Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| YWPS_T3 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 1.0 | 1 | e-0d844d44b1f3a3b9a5be0d2b |
| YWPS_T3 / breaker_closed | 2025-10-16T03:37:29Z | 2025-10-16T03:37:29Z | 0.0 | 1 | e-beb030e69577584cd3f37eee |
| YWPS_T3 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 220.328 | kV | e-f16d876ebb939cd96e0decf5 |
| YWPS_T3 / voltage_kv | 2025-10-16T03:37:19Z | 2025-10-16T03:37:21Z | 0.0 | kV | e-1d1390180aac55b6ebe61491 |
| YWPS_T4 / breaker_closed | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 1.0 | 1 | e-ab53dc908484c7b10cccd6c9 |
| YWPS_T4 / breaker_closed | 2025-10-16T03:37:29Z | 2025-10-16T03:37:29Z | 0.0 | 1 | e-e89166e05216e6de18910174 |
| YWPS_T4 / voltage_kv | 2025-10-16T03:32:59Z | 2025-10-16T03:32:59Z | 219.898 | kV | e-3b577358cd53f98e7bcf9f19 |
| YWPS_T4 / voltage_kv | 2025-10-16T03:37:19Z | 2025-10-16T03:37:21Z | 0.0 | kV | e-9d183426474cad251ebb6300 |
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
- Request {"asset_ids": ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 547; complete True; first six evidence IDs ["e-0d844d44b1f3a3b9a5be0d2b", "e-117a3dd091bfa4842cd36768", "e-31fc8dd35e2b54faaa5f615c", "e-3b577358cd53f98e7bcf9f19", "e-6d6ef0e01fd40abcbce2d046", "e-7caa381b913065acd3de5f52"]; quality counts {"good": 16}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.confirm_cause: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.deny_scada: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.

## c-40da3b6fffda58543c9d (s011)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: vital-data-missing.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): [{"asset_ids": ["YWPS_U4", "YWPS_T4"], "available_at": "2025-10-16T03:35:59Z", "event_interval": {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "notification_id": "e-6c23f555ece2a65411be3816", "origin": "simulated_operator_notification", "synthetic": true}, {"asset_ids": ["YWPS_U3", "YWPS_T3"], "available_at": "2025-10-16T03:35:59Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:32Z"}, "event_type": "generator_trip", "notification_id": "e-2a597ee3f7d06458fee9fc5d", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| JEERALANG_A2 | Jeeralang unit A2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:09ad80f4-6fbc-5f5e-bb77-14ff9df40442 |
| JEERALANG_A3 | Jeeralang unit A3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:b5cfc255-70d1-5eff-ae44-3348c39d4caa |
| JEERALANG_B3 | Jeeralang unit B3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:9dbb3af3-b1ff-5bcc-bd2c-a1111d24e5e2 |
| LYA_U1 | LYA PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:39cc2868-1c93-5273-82be-b0e24e3c64bb |
| LYA_U3 | LYA PS unit 3 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c4fe4ed3-5a10-5f64-966f-286ac45e100f |
| LYB_U2 | LYB PS unit 2 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:5b756a79-766f-54eb-8a5a-2ea70f18aeda |
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source event definitions and assumed available at the decision cutoff. This synthetic availability does not date the report or establish current state, prerequisites or cause.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report."]; parameters: {"alarm_mode": "absent", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 0, "knowledge": 3, "scada": 807, "topology": 397}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "communication": {"asset_ids": ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "decision_time": "2025-10-16T03:35:59Z", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "evidence_ids": ["e-2a597ee3f7d06458fee9fc5d", "e-6c23f555ece2a65411be3816"], "next_steps": ["request_missing_data", "escalate_to_operator"], "notification_ids": ["e-2a597ee3f7d06458fee9fc5d", "e-6c23f555ece2a65411be3816"], "state": "conflicting"}, "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_time": null, "event_type": "generator_trip", "gap": "data_gap", "hypotheses": [], "message": "Given simulated notifications: generator_trip for YWPS_U4, YWPS_T4 in [2025-10-16T03:34:29Z, 2025-10-16T03:34:30Z); generator_trip for YWPS_U3, YWPS_T3 in [2025-10-16T03:34:32Z, 2025-10-16T03:34:33Z). As of 2025-10-16T03:35:59Z, current state is conflicting: no verified current measurements. Notification type does not match the declared asset class for YWPS_T3. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: request_missing_data, escalate_to_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {"bad": 6, "missing": 6, "stale": 4}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, generator_trip, assets ["YWPS_T3", "YWPS_T4", "YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.

## c-49031b19efe15133cc4c (s012)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: initial-transition.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:10Z (2026-01-29T10:09:10+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "busbar_deenergization". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: confirm_event, review_protection_work, consult_limit_advice, apply_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Separate busbar availability from already-offline generation; review protection work and temporary line-rating advice without asserting a confirmed cause.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 5, "scada": 477, "topology": 239}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 477; complete True; first six evidence IDs ["e-1b16cb306e4cb299c1b4ad79", "e-1d5c5a0471a883393ae7a8fe", "e-389d3f6548c6974d3440e805", "e-45fee327cd81552c95ef7dc9", "e-466c26c4b78d2a71c4ef7faf", "e-4c419d66d0c989f19527174b"]; quality counts {"good": 26}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-cd612b195f8883a0e731286a"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-e3b33a98de99d72f2ba4 (s013)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: correlated-state.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "busbar_deenergization". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: confirm_event, review_protection_work, consult_limit_advice, apply_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Separate busbar availability from already-offline generation; review protection work and temporary line-rating advice without asserting a confirmed cause.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": true, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 5, "scada": 530, "topology": 239}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 530; complete True; first six evidence IDs ["e-17a2fbb4063e7b0e2a6a42e5", "e-24adf604b4b0d005225bfc0a", "e-2631bb2afee30c30ca6d1cd2", "e-30211323833e6b3fd353e706", "e-37b4affe266ea62866352cf7", "e-404ef5fcb9bb41e339b36eda"]; quality counts {"good": 26}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-02df1a71068bbd0739d47612"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-ae466d24708b8ba4519c (s014)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: restoration.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T01:17:00Z (2026-01-29T11:17:00+10:00 AEST); decision 2026-01-29T01:19:15Z (2026-01-29T11:19:15+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): []
Observable class: "return_to_service". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: verify_restoration, remove_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Verify the restored busbar and applicable limits before recommending removal of temporary EMS ratings.

Source event murray-busbar-restoration: 29 January 2026, 1118 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-restoration: later classification "Reported return to service"; later cause null.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 5, "scada": 424, "topology": 239}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 424; complete True; first six evidence IDs ["e-069cafbbd52dbeac79993dee", "e-09914285b964d8437869d88a", "e-1acc7e4c4397fdbbb03581d5", "e-4521d730617a2b7fb4747cf5", "e-49385573457b51ce8e7c3d2e", "e-4b5794b3f1aeaead4cec7d1b"]; quality counts {"good": 26}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-2082398008496094e55f25fe"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, restoration, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-d929d78830df3569be55 (s015)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: normal-baseline.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:03:00Z (2026-01-29T10:03:00+10:00 AEST); decision 2026-01-29T00:05:00Z (2026-01-29T10:05:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 0, "knowledge": 5, "scada": 324, "topology": 239}
Reference produced: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": null, "hypotheses": [], "message": "No qualifying unplanned transition in usable as-of samples; steady outages are not new trips.", "status": "no_event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 324; complete True; first six evidence IDs ["e-0727379a544e542cc00a5423", "e-073d8d5be5f6eb6bc658175b", "e-10c88dc8e261d941d0a30f5f", "e-14fbc45ea5972a7554d25ef2", "e-152091f5ae6b0cf14f4dc207", "e-1db0b7f112a5783b37ba8249"]; quality counts {"good": 26}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-0fc9dd7f4bb86d4b6b6e (s016)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: preexisting-outage.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:03:00Z (2026-01-29T10:03:00+10:00 AEST); decision 2026-01-29T00:05:00Z (2026-01-29T10:05:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Benign planned/test alarm is invented. YWPS_U2 pre-existing unavailability is a fixture assumption, not resolved from diagram text order."]; parameters: {"alarm_mode": "benign", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 3, "knowledge": 5, "scada": 324, "topology": 239}
Reference produced: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": null, "hypotheses": [], "message": "No qualifying unplanned transition in usable as-of samples; steady outages are not new trips.", "status": "no_event"}
Pass: True; observed gap: None; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 324; complete True; first six evidence IDs ["e-0a2a29091e123a87dd1d5508", "e-0d638d5111768f5d89a688ab", "e-1a74b1e7380ae772883abbdb", "e-2821623c225ffea864b469f4", "e-283a79a386c50a15e48a946e", "e-30801c2884a45bb702510fe8"]; quality counts {"good": 26}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 3; complete True; first six evidence IDs ["e-8cf8e3a1700f021269a496c0", "e-9ff74061ec7ac1a5ea95582c", "e-c2fc941250d5ec8281d3830e"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-defabadeb24e25c75d86 (s017)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: bad-and-stale-signals.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report."]; parameters: {"alarm_mode": "absent", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 0, "knowledge": 5, "scada": 469, "topology": 239}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 469; complete True; first six evidence IDs ["e-01cfb563b4d7f71f8c60ba5b", "e-05193fed4e658e4f065c9448", "e-0de5fa19ea586efb288d5c3e", "e-12e5347f9cdb6dfd4e01c993", "e-1437dc1c9b03611d9d845d2b", "e-1ab82b96b69299331f60777b"]; quality counts {"bad": 1, "good": 23, "missing": 1, "stale": 1}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-3501bce2c0b1a054e4d5 (s018)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: late-alarms.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection outcome: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): []
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report."]; parameters: {"alarm_mode": "delayed", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "missing"}.
Public evidence row counts: {"alarms": 0, "knowledge": 5, "scada": 469, "topology": 239}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 469; complete True; first six evidence IDs ["e-1b58af527264d1c5d3146250", "e-1ecd37d10a51203b42992f13", "e-2fbffcdfc3f6c3350b563811", "e-3e59b8b2bd46df3fafcabdd1", "e-4a294870b49ae1296af6387e", "e-5072073d638e16ed0e183175"]; quality counts {"good": 23, "missing": 3}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: no_event, None, assets []; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-ea498de21167d5cff09a (s019)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: appropriate-response.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:11:00Z (2026-01-29T10:11:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["confirm_event", "review_protection_work", "consult_limit_advice", "apply_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["MURRAY_5B2"], "available_at": "2026-01-29T00:11:00Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "notification_id": "e-881544f54095acb9fecfa1ab", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "busbar_deenergization". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: confirm_event, review_protection_work, consult_limit_advice, apply_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Separate busbar availability from already-offline generation; review protection work and temporary line-rating advice without asserting a confirmed cause.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source event definitions and assumed available at the decision cutoff. This synthetic availability does not date the report or establish current state, prerequisites or cause."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 5, "scada": 766, "topology": 239}
Reference produced: {"action_ids": ["confirm_event", "review_protection_work", "consult_limit_advice", "apply_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "busbar_deenergization", "communication": {"asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "decision_time": "2026-01-29T00:11:00Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "evidence_ids": ["e-01a3ab01228391cfe128c7e2", "e-08197f2af555809c58174675", "e-08c1fbf8018cd6c094cd6a46", "e-0b26c2185433df424b5e28c1", "e-0df597a786c1927f599f3731", "e-1300724d75c36ebe3d6219bc", "e-3c463663c00a6b25cb5705af", "e-41e45cc3568b134c0008d699", "e-4db9809811a652dc313b3fa3", "e-5e39c23e130d232a0dfbe887", "e-5f848d0a2619a0c5c9c09127", "e-62d70f143d96812bbc83b5e4", "e-66ea3a1edc8cb0476e79a52e", "e-7a6fa93e073f9a623ae8ce89", "e-804c8cf70afb09329482a85d", "e-842f507f4b84a80d9de5fbc2", "e-854498af1145d90e7491b745", "e-864c64db1411d315a423fb55", "e-873386539926a3af60f21900", "e-881544f54095acb9fecfa1ab", "e-8c94137db89790a710005211", "e-944c215d3a2a0a12e79d9d4f", "e-95a35f2e9d1a439954df930b", "e-9835938e4721c4a0a5b4c1a3", "e-a080de9833dc652a94146b69", "e-aee49928b5c42db6d0ac961f", "e-b0446ae5948372173aff3f9b", "e-b1abf94e6e5431a474400f02", "e-b35d42ae3d673591938a4181", "e-b845488bd4c617c4436008ea", "e-ba3569591741cbf3301b92cd", "e-c40a9ef18bd07df22c9bff5a", "e-d10c1bc983adfd8519d312ca", "e-d68477bbb4faa42adde5ca28", "e-d9320ef260da0a7a8fea6074", "e-e5a4c23818bef33601c09f46", "e-f3370518f2f3328fef506ac7"], "next_steps": ["confirm_event", "review_protection_work", "consult_limit_advice", "apply_temporary_line_ratings", "notify_operator"], "notification_ids": ["e-881544f54095acb9fecfa1ab"], "state": "verified"}, "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_time": null, "event_type": "busbar_trip", "gap": null, "hypotheses": [], "message": "Given simulated notifications: busbar_trip for MURRAY_5B2 in [2026-01-29T00:08:00Z, 2026-01-29T00:09:00Z). As of 2026-01-29T00:11:00Z, current state is verified: MURRAY_5B2 breaker_closed=0.0 1 at 2026-01-29T00:10:50Z; MURRAY_5B2 voltage_kv=0.0 kV at 2026-01-29T00:10:50Z. Fresh current measurements agree with the given event; original transition detection was not required. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: confirm_event, review_protection_work, consult_limit_advice, apply_temporary_line_ratings, notify_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "event"}
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
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 88; complete True; first six evidence IDs ["e-440b4ee9af8aa4f184f30fc2", "e-77feee0e35bf56b55b9986a7", "e-fc4787544bc6b578a0cb39c8", "e-b11221100874f1d3e9ce1c5a", "e-d1c2bc0246cbe15f2516a2fb", "e-f3639f18b21294b3a72157ed"]; quality counts {"good": 3}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-b845488bd4c617c4436008ea"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 31; complete True; first six evidence IDs ["e-01a3ab01228391cfe128c7e2", "e-944c215d3a2a0a12e79d9d4f", "e-c40a9ef18bd07df22c9bff5a", "e-0b26c2185433df424b5e28c1", "e-4db9809811a652dc313b3fa3", "e-62d70f143d96812bbc83b5e4"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-b68dab61ccac6dd033f5 (s020)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: restoration-response.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T01:17:00Z (2026-01-29T11:17:00+10:00 AEST); decision 2026-01-29T01:19:30Z (2026-01-29T11:19:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["verify_restoration", "remove_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["MURRAY_5B2"], "available_at": "2026-01-29T01:19:30Z", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "notification_id": "e-95fa43d833fa7b028ff9c9b1", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "return_to_service". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- e-b0446ae5948372173aff3f9b, valid from 2025-01-01T00:00:00Z, available 2025-01-01T00:00:00Z: verify_restoration, remove_temporary_line_ratings, notify_operator. Required tools: scada, alarms, knowledge, topology. Rationale: Verify the restored busbar and applicable limits before recommending removal of temporary EMS ratings.

Source event murray-busbar-restoration: 29 January 2026, 1118 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-restoration: later classification "Reported return to service"; later cause null.

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source event definitions and assumed available at the decision cutoff. This synthetic availability does not date the report or establish current state, prerequisites or cause."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 5, "scada": 452, "topology": 239}
Reference produced: {"action_ids": ["verify_restoration", "remove_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "return_to_service", "communication": {"asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "decision_time": "2026-01-29T01:19:30Z", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "evidence_ids": ["e-01a3ab01228391cfe128c7e2", "e-08197f2af555809c58174675", "e-08c1fbf8018cd6c094cd6a46", "e-0b26c2185433df424b5e28c1", "e-0df597a786c1927f599f3731", "e-1300724d75c36ebe3d6219bc", "e-1cb666ecfaca16f718dd8094", "e-3c463663c00a6b25cb5705af", "e-41e45cc3568b134c0008d699", "e-4d8ab3d24ab7a0ba31bfa3de", "e-4db9809811a652dc313b3fa3", "e-5e39c23e130d232a0dfbe887", "e-5f848d0a2619a0c5c9c09127", "e-62d70f143d96812bbc83b5e4", "e-66ea3a1edc8cb0476e79a52e", "e-7a6fa93e073f9a623ae8ce89", "e-804c8cf70afb09329482a85d", "e-842f507f4b84a80d9de5fbc2", "e-854498af1145d90e7491b745", "e-864c64db1411d315a423fb55", "e-873386539926a3af60f21900", "e-8c94137db89790a710005211", "e-92cc9142e15be5e8c05c1e42", "e-944c215d3a2a0a12e79d9d4f", "e-95a35f2e9d1a439954df930b", "e-95fa43d833fa7b028ff9c9b1", "e-9835938e4721c4a0a5b4c1a3", "e-a080de9833dc652a94146b69", "e-aee49928b5c42db6d0ac961f", "e-b0446ae5948372173aff3f9b", "e-b1abf94e6e5431a474400f02", "e-b35d42ae3d673591938a4181", "e-ba3569591741cbf3301b92cd", "e-c40a9ef18bd07df22c9bff5a", "e-d9320ef260da0a7a8fea6074", "e-e5a4c23818bef33601c09f46", "e-f3370518f2f3328fef506ac7"], "next_steps": ["verify_restoration", "remove_temporary_line_ratings", "notify_operator"], "notification_ids": ["e-95fa43d833fa7b028ff9c9b1"], "state": "verified"}, "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_time": null, "event_type": "restoration", "gap": null, "hypotheses": [], "message": "Given simulated notifications: restoration for MURRAY_5B2 in [2026-01-29T01:18:00Z, 2026-01-29T01:19:00Z). As of 2026-01-29T01:19:30Z, current state is verified: MURRAY_5B2 breaker_closed=1.0 1 at 2026-01-29T01:19:20Z; MURRAY_5B2 voltage_kv=329.691 kV at 2026-01-29T01:19:30Z. Fresh current measurements agree with the given event; original transition detection was not required. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: verify_restoration, remove_temporary_line_ratings, notify_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "event"}
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
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-92cc9142e15be5e8c05c1e42"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 52; complete True; first six evidence IDs ["e-1a49bc34ec2ee51fe4f903ab", "e-211e239aed6e7a9da62b7ded", "e-ee3bd1426b8c66cad5fdbfce", "e-1a48a8ba3836a49ce1d84747", "e-b8330d1a5891063c489938fd", "e-f0591b4f2ec957144063d112"]; quality counts {"good": 3}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-92cc9142e15be5e8c05c1e42"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 31; complete True; first six evidence IDs ["e-01a3ab01228391cfe128c7e2", "e-944c215d3a2a0a12e79d9d4f", "e-c40a9ef18bd07df22c9bff5a", "e-0b26c2185433df424b5e28c1", "e-4db9809811a652dc313b3fa3", "e-62d70f143d96812bbc83b5e4"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, restoration, assets ["MURRAY_5B2"]; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, restoration, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, restoration, assets ["MURRAY_5B2"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, restoration, assets ["MURRAY_5B2"]; pass False; gap data_gap. Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-1c30fea6b26578ff73ff (s021)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: knowledge-tool-unavailable.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:11:00Z (2026-01-29T10:11:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "tooling_gap", "status": "event"}
Given event conditions (action inputs only): [{"asset_ids": ["MURRAY_5B2"], "available_at": "2026-01-29T00:11:00Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "notification_id": "e-8ac5dae6f8459e5df1e465bd", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: "busbar_deenergization". Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source event definitions and assumed available at the decision cutoff. This synthetic availability does not date the report or establish current state, prerequisites or cause."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "scada": 766, "topology": 239}
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

## c-65eb5b7970b65b3c5c82 (s022)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: vital-data-missing.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected action outcome: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
Given event conditions (action inputs only): [{"asset_ids": ["MURRAY_5B2"], "available_at": "2026-01-29T00:09:30Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "notification_id": "e-632e1e260d1e3d0a3eecfd76", "origin": "simulated_operator_notification", "synthetic": true}]
Observable class: null. Contemporaneous cause status: not_established.

Source instance bindings:

| Canonical Asset | Source Aliases | Bound Points | Binding |
| --- | --- | --- | --- |
| DMDM_67 | Dederang - Murray 330 kV No. 67 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:5c48438c-5dd3-533e-b572-95242cef2db7 |
| DMDM_68 | Dederang - Murray 330 kV No. 68 line | available, breaker_closed, flow_mva, rating_mva, voltage_kv | synthetic only; urn:uuid:b08172a6-ebca-56d6-a694-eb07368701ba |
| MURRAY_5B1 | Murray 5B1, Murray 5B1 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:a07e926f-b7c2-5dc4-b47d-3bec7a6ce28b |
| MURRAY_5B2 | Murray 5B2, Murray 5B2 330 kV busbar | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:37572b06-0aa9-53a6-a8fc-538aa06b9d6f |
| MURRAY_R1 | Murray 330 kV No. 1 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:c5fc538d-0399-5363-9cd4-e60cdf96680d |
| MURRAY_R3 | Murray 330 kV No. 3 reactor | available, breaker_closed, voltage_kv | synthetic only; urn:uuid:13d26bf6-3791-580b-a295-f9ef35280493 |
| MURRAY_U1 | Murray 1 PS unit 1 | active_power_mw, available, breaker_closed, voltage_kv | synthetic only; urn:uuid:df4d3094-7a18-556c-a857-76ed6935b461 |

Valid simulated action-policy prerequisites:
- No applicable as-of rule; required response is judged independently from the private label.

Source event murray-busbar-trip: 29 January 2026, 1008 hrs AEST; minute precision; UTC interval {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"} (exclusive end).
Source reference murray page 3; PDF SHA-256 a77f71573d84070c5ba57910d842ce4e0d711adb8c2be2e60451099f531ee43a; extraction SHA-256 73dd153abfe27fbb08bde1731b6f5baf5d26343a02d02b43e5e95ae3571ae405. Exact quote: private provenance.

Later/investigator truth, not early inference:
- murray-busbar-trip: later classification "Other causes - human error (later report classification)"; later cause {"availability_basis": "fixture conservative late-knowledge boundary, not historical discovery time", "available_at": "2026-08-01T00:00:00Z", "status": "later_investigation", "summary": "During work associated with in-service 5B1, a misidentified test lead connected to a live 5B2 protection link. Ordinary busbar signals do not establish human error."}.
- Historical action murray-ratings-applied: Historical manual EMS rating override, not a physical switching command. Time: 29 January 2026, approximately 1025 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-ratings-removed: Historical removal of manual rating override following restoration. Time: 29 January 2026, approximately 1120 hrs AEST; precision: approximate_minute; uncertainty: Fixture +/-120 seconds around the reported minute, with SIMULATED second 30. Source supplies no numerical error bound..
- Historical action murray-protection-work-ceased: Protection returned to normal and work ceased. No exact timestamp available. Time: Shortly following the incident; precision: unavailable; uncertainty: Unknown completion time; recommendations request verification, never assume completion at a fabricated time..

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Operator/event-service notifications are independently authored from selected source event definitions and assumed available at the decision cutoff. This synthetic availability does not date the report or establish current state, prerequisites or cause.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report."]; parameters: {"alarm_mode": "absent", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 0, "knowledge": 5, "scada": 469, "topology": 239}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "busbar_deenergization", "communication": {"asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "decision_time": "2026-01-29T00:09:30Z", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "evidence_ids": ["e-632e1e260d1e3d0a3eecfd76"], "next_steps": ["request_missing_data", "escalate_to_operator"], "notification_ids": ["e-632e1e260d1e3d0a3eecfd76"], "state": "unverified"}, "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_time": null, "event_type": "busbar_trip", "gap": "data_gap", "hypotheses": [], "message": "Given simulated notifications: busbar_trip for MURRAY_5B2 in [2026-01-29T00:08:00Z, 2026-01-29T00:09:00Z). As of 2026-01-29T00:09:30Z, current state is unverified: no verified current measurements. MURRAY_5B2 lacks a fresh usable post-notification breaker_closed sample. Cause is not established; notifications do not prove recommendation prerequisites. Next steps: request_missing_data, escalate_to_operator. All steps are simulated recommendations or requests for an authorized operator; nothing is executed.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {"bad": 1, "missing": 1, "stale": 1}.

Counterfactual replay diagnostics:
- power_only_detection.defer_action: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, busbar_trip, assets ["MURRAY_5B2"]; pass True; gap None. No failed expectation.

