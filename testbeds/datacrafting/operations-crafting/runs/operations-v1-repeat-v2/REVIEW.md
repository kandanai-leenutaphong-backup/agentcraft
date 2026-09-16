# Operations Dataset Review

Visibility: evaluator_only. Do not give this review, labels, provenance or raw pack paths to a predictor.

Reports anchor authored events, not universal policy. Every KB action rule, waveform, cadence, alarm code, topology detail and availability assumption is simulated.
Source PDF/extraction hashes and exact page-scoped quotes are retained only in private provenance. Byte/quote agreement is not proof that a report is universally correct.
Yallourn support concerns synchronous-unit combinations/system strength, not replacement of exactly 597 MW. Protection/control classification and flooding/control-circuit explanations are later forensic truth.
Murray trip/restoration source times have minute precision; synthetic seconds do not improve report precision. No generation or customer load loss is attributed to that busbar event; pre-existing outages are not new trips.
AEST means fixed UTC+10, including October and January. Current policy without valid_to is assumed valid indefinitely; topology is static synthetic context.
Mode defaults: 300-second latest-sample freshness; 300-second detection latency budget unless authored; zero extra event-time tolerance beyond the source interval. Thresholds (5/25 MW, 10%/80% nominal voltage) are synthetic decision assumptions.
No physical operations, model calls, optimizer or training loop. Future campaign ownership remains the public OptimizationService.

## Replay Measurements

One synthetic process test, not learning or demonstrated generalization. Holdout is inspected; no untouched holdout claim.

Event precision/recall require matching event type, exact asset set and source-tolerant time. Null means no denominator.

| Run | Cases | Passed | Status Accuracy | Event P/R | FP | Action Recall/Exact | Unsupported Causes |
| --- | ---: | ---: | ---: | --- | ---: | --- | ---: |
| power_only | 22 | 13 | 0.590909 | 1.0 / 0.5 | 0 | 0.5 / 0.5 | 0 |
| reference | 22 | 22 | 1.0 | 1.0 / 1.0 | 0 | 1.0 / 1.0 | 0 |
| reference.confirm_cause | 22 | 10 | 1.0 | 1.0 / 1.0 | 0 | 1.0 / 1.0 | 12 |
| reference.deny_scada | 22 | 4 | 0.272727 | None / 0.0 | 0 | 0.25 / 0.25 | 0 |
| reference.drop_records | 22 | 6 | 0.272727 | None / 0.0 | 0 | 0.25 / 0.25 | 0 |
| reference.wrong_rule | 22 | 10 | 0.454545 | None / 0.0 | 0 | 0.166667 / 0.25 | 0 |

All denominators include missing and failed predictions. Complete requests, returned evidence IDs, errors and per-case diagnoses: `replay/cases.jsonl`.

Correct expected insufficiency is a pass; a resource gap is not automatically a predictor failure.

## c-b52d9eea22e9c4d7f2c6 (s001)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: initial-transition.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:34:31Z (2025-10-16T13:34:31+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": ["YWPS_U4"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:30Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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
- power_only: event, generator_trip, assets ["YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-1e8da6cf44423164e894 (s002)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: correlated-state.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": ["YWPS_U4", "YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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
- power_only: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-e928049057da8d6943e3 (s003)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: restoration.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T06:26:00Z (2025-10-16T16:26:00+10:00 AEST); decision 2025-10-16T06:28:15Z (2025-10-16T16:28:15+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": ["YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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
- power_only: event, restoration, assets ["YWPS_U3"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, restoration, assets ["YWPS_U3"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-2e10935ce667f4111a44 (s004)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: normal-baseline.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:29:29Z (2025-10-16T13:29:29+10:00 AEST); decision 2025-10-16T03:31:29Z (2025-10-16T13:31:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
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
- power_only: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-6f422bea5321c887ae13 (s005)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: preexisting-outage.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:29:29Z (2025-10-16T13:29:29+10:00 AEST); decision 2025-10-16T03:31:29Z (2025-10-16T13:31:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
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
- power_only: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-eb99cd25658543b65546 (s006)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: bad-and-stale-signals.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
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
- power_only: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-576625e809733e613779 (s007)

Task/split/incident: detection / development / yallourn. Template: operations.generator_transition.v1; variant: late-alarms.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
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
- power_only: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-09241b3ce39676faf608 (s008)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: appropriate-response.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:37:29Z (2025-10-16T13:37:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": ["confirm_event", "assess_system_strength", "consult_limit_advice", "request_authorized_support", "notify_operator", "investigate_cooling"], "asset_ids": ["YWPS_U4", "YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 2, "knowledge": 3, "scada": 1710, "topology": 397}
Reference produced: {"action_ids": ["confirm_event", "assess_system_strength", "consult_limit_advice", "request_authorized_support", "notify_operator", "investigate_cooling"], "asset_ids": ["YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "event_time": "2025-10-16T03:34:29Z", "event_type": "generator_trip", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established. Declared actions are simulated recommendations requiring operator authorization; nothing is executed.", "status": "event"}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 1710; complete True; first six evidence IDs ["e-09e1b45bba4c8b8427ccccba", "e-0d49b4700fd73818f38480c8", "e-1804c6b7163dfef429e58940", "e-1dbfdbc5eced81b35f56ffb4", "e-1e15c81d8a72c66c37f452fc", "e-24f5e568488e6185c383daab"]; quality counts {"good": 50}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-484521fc7882d5091fa4f0c6", "e-96b6e5e6411c9407faccc374"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-4e87146b1efe9b82f8dda348", "e-53a91b779566f65d88fda549"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 340; complete True; first six evidence IDs ["e-3f561d4f959f8081d146924a", "e-5325dc70e145a27f4a8d0e53", "e-7070a6d8e961e9141d52e926", "e-926b7b8295116c43d22dee3a", "e-ab5240503fbc30748619e769", "e-bf592ea2d0207a72476d7baf"]; quality counts {"good": 10}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-484521fc7882d5091fa4f0c6", "e-96b6e5e6411c9407faccc374"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-4e87146b1efe9b82f8dda348", "e-53a91b779566f65d88fda549"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 62; complete True; first six evidence IDs ["e-fb6a5c024c5a461473db3a63", "e-97b50c5510b78c423b07422f", "e-a73b9acab61e081a31756e96", "e-fb056cc5b16a5b61fb21b9da", "e-09270172b790df8757b1276b", "e-1d47c1f4aac82fb750eb9b9a"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-24882b60ecac8f579eaa (s009)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: restoration-response.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T06:26:00Z (2025-10-16T16:26:00+10:00 AEST); decision 2025-10-16T06:28:30Z (2025-10-16T16:28:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": ["verify_restoration", "notify_operator"], "asset_ids": ["YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T06:28:00Z", "start": "2025-10-16T06:27:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 3, "scada": 968, "topology": 397}
Reference produced: {"action_ids": ["verify_restoration", "notify_operator"], "asset_ids": ["YWPS_U3"], "cause_status": "not_established", "classification": "return_to_service", "event_time": "2025-10-16T06:27:30Z", "event_type": "restoration", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established. Declared actions are simulated recommendations requiring operator authorization; nothing is executed.", "status": "event"}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 968; complete True; first six evidence IDs ["e-0091607cc3686f101bbb31c8", "e-120fc8b01aab37a1e70364f9", "e-128cc0e3ba762e6d0f210c2c", "e-12dffae39813c9e742b1f4c4", "e-1789bae95fa6dae5c1963c7c", "e-181372564b7dc5440546b96b"]; quality counts {"good": 50}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-d59187fa72c96a3a93dcfe16"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-4e87146b1efe9b82f8dda348", "e-53a91b779566f65d88fda549"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 98; complete True; first six evidence IDs ["e-128cc0e3ba762e6d0f210c2c", "e-443c60918c8f1ee7a3bda18a", "e-883571c3b4afc1bef79d2079", "e-b83b436733fbe5f37262b477", "e-d95ef819b214bdaa68aa858e", "e-186ca79e797c6cc4c038db8a"]; quality counts {"good": 5}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-d59187fa72c96a3a93dcfe16"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-4e87146b1efe9b82f8dda348", "e-53a91b779566f65d88fda549"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 31; complete True; first six evidence IDs ["e-fb6a5c024c5a461473db3a63", "e-97b50c5510b78c423b07422f", "e-a73b9acab61e081a31756e96", "e-fb056cc5b16a5b61fb21b9da", "e-09270172b790df8757b1276b", "e-1d47c1f4aac82fb750eb9b9a"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only: event, restoration, assets ["YWPS_U3"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, restoration, assets ["YWPS_U3"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-155f77e2df398504763d (s010)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: knowledge-tool-unavailable.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:37:29Z (2025-10-16T13:37:29+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["YWPS_U4", "YWPS_U3"], "cause_status": "not_established", "event_interval": {"end": "2025-10-16T03:34:33Z", "start": "2025-10-16T03:34:29Z"}, "event_type": "generator_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "tooling_gap", "status": "event"}
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only."]; parameters: {"alarm_mode": "normal", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 2, "scada": 1710, "topology": 397}
Reference produced: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["YWPS_U3", "YWPS_U4"], "cause_status": "not_established", "classification": "generation_disconnection", "event_time": "2025-10-16T03:34:29Z", "event_type": "generator_trip", "gap": "tooling_gap", "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established. Policy tool unavailable; no operational recommendation is authorized.", "status": "event"}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 1710; complete True; first six evidence IDs ["e-04a0c3e84b13804444c46564", "e-0632e544e9d8044bf46585fd", "e-086cb94d2d94ba846551e7d0", "e-0a4c7807acaf689455134307", "e-0d844d44b1f3a3b9a5be0d2b", "e-117a3dd091bfa4842cd36768"]; quality counts {"good": 50}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-7e479428b2b5622fa4e71da0", "e-117ff31acc016c1c9f1c0264"]; quality counts {}.
- Request {"asset_ids": ["YWPS_U3", "YWPS_U4"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome denied; rows 0; complete None; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass True; gap None. No failed expectation.
- reference.confirm_cause: event, generator_trip, assets ["YWPS_U3", "YWPS_U4"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.

## c-db44bff9dc182abcb37e (s011)

Task/split/incident: action / development / yallourn. Template: operations.generator_response.v1; variant: vital-data-missing.
Assets: Jeeralang A2 [JEERALANG_A2, generator]; Jeeralang A3 [JEERALANG_A3, generator]; Jeeralang B3 [JEERALANG_B3, generator]; Loy Yang A unit 1 [LYA_U1, generator]; Loy Yang A unit 3 [LYA_U3, generator]; Loy Yang B unit 2 [LYB_U2, generator]; Yallourn common cooling [YWPS_COOLING, cooling_system]; Yallourn unit 3 transformer [YWPS_T3, transformer]; Yallourn unit 4 transformer [YWPS_T4, transformer]; Yallourn W unit 1 [YWPS_U1, generator]; Yallourn W unit 2 [YWPS_U2, generator]; Yallourn W unit 3 [YWPS_U3, generator]; Yallourn W unit 4 [YWPS_U4, generator]
Window starts 2025-10-16T03:32:59Z (2025-10-16T13:32:59+10:00 AEST); decision 2025-10-16T03:35:59Z (2025-10-16T13:35:59+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report."]; parameters: {"alarm_mode": "absent", "asset_kind": "generator", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["YWPS_U1", "YWPS_U2", "YWPS_U3", "YWPS_U4", "YWPS_T3", "YWPS_T4", "YWPS_COOLING", "JEERALANG_A2", "JEERALANG_A3", "JEERALANG_B3", "LYA_U1", "LYA_U3", "LYB_U2"], "dependent": ["YWPS_T3", "YWPS_T4", "YWPS_COOLING"], "previously_unavailable": ["YWPS_U2"], "primary": ["YWPS_U4", "YWPS_U3"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 0, "knowledge": 3, "scada": 807, "topology": 397}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 807; complete True; first six evidence IDs ["e-024c201c0f8111fbe7941dc2", "e-0ac80e0ec39d1a7e7479bad8", "e-0e835b147795af3a5bdc8fc5", "e-0f01fe9932bcc84de61ce9d2", "e-13b1d901d876063116c7d965", "e-24e5df734ab92054a63820ee"]; quality counts {"bad": 7, "good": 32, "missing": 7, "stale": 4}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-195fe70478b7a5cb71fe (s012)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: initial-transition.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:10Z (2026-01-29T10:09:10+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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
- power_only: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-b23b9c1aa95eee1fed60 (s013)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: correlated-state.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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
- power_only: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-04224109b2ecba7b671a (s014)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: restoration.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T01:17:00Z (2026-01-29T11:17:00+10:00 AEST); decision 2026-01-29T01:19:15Z (2026-01-29T11:19:15+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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
- power_only: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, restoration, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-9e9e632d7d37778cc0c0 (s015)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: normal-baseline.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:03:00Z (2026-01-29T10:03:00+10:00 AEST); decision 2026-01-29T00:05:00Z (2026-01-29T10:05:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
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
- power_only: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-a233f9ec3ba92da849ee (s016)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: preexisting-outage.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:03:00Z (2026-01-29T10:03:00+10:00 AEST); decision 2026-01-29T00:05:00Z (2026-01-29T10:05:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "no_event"}
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
- power_only: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.confirm_cause: no_event, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass True; gap None. No failed expectation.

## c-97d93d5aa619e50b3800 (s017)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: bad-and-stale-signals.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
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
- power_only: no_event, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-8631726f1ad02a71f5a1 (s018)

Task/split/incident: detection / holdout / murray. Template: operations.busbar_transition.v1; variant: late-alarms.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": [], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
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
- power_only: no_event, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

## c-70cc3497c56beeadcc71 (s019)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: appropriate-response.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:11:00Z (2026-01-29T10:11:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": ["confirm_event", "review_protection_work", "consult_limit_advice", "apply_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 5, "scada": 766, "topology": 239}
Reference produced: {"action_ids": ["confirm_event", "review_protection_work", "consult_limit_advice", "apply_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "busbar_deenergization", "event_time": "2026-01-29T00:08:30Z", "event_type": "busbar_trip", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established. Declared actions are simulated recommendations requiring operator authorization; nothing is executed.", "status": "event"}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 766; complete True; first six evidence IDs ["e-0c47947e7b9ae1afa2e201fa", "e-2b9c6244dde767e963a7b2ed", "e-349c8a43e750e8b2a98bbcfc", "e-374287d61859f0aedb0479e9", "e-3ff3c70cb7e90dc9350f7d6d", "e-440b4ee9af8aa4f184f30fc2"]; quality counts {"good": 26}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-b845488bd4c617c4436008ea"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 88; complete True; first six evidence IDs ["e-440b4ee9af8aa4f184f30fc2", "e-77feee0e35bf56b55b9986a7", "e-fc4787544bc6b578a0cb39c8", "e-b11221100874f1d3e9ce1c5a", "e-d1c2bc0246cbe15f2516a2fb", "e-f3639f18b21294b3a72157ed"]; quality counts {"good": 3}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-b845488bd4c617c4436008ea"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 31; complete True; first six evidence IDs ["e-01a3ab01228391cfe128c7e2", "e-944c215d3a2a0a12e79d9d4f", "e-c40a9ef18bd07df22c9bff5a", "e-0b26c2185433df424b5e28c1", "e-4db9809811a652dc313b3fa3", "e-62d70f143d96812bbc83b5e4"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-4b40601af0239b577132 (s020)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: restoration-response.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T01:17:00Z (2026-01-29T11:17:00+10:00 AEST); decision 2026-01-29T01:19:30Z (2026-01-29T11:19:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": ["verify_restoration", "remove_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T01:19:00Z", "start": "2026-01-29T01:18:00Z"}, "event_type": "restoration", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": null, "status": "event"}
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "knowledge": 5, "scada": 452, "topology": 239}
Reference produced: {"action_ids": ["verify_restoration", "remove_temporary_line_ratings", "notify_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "return_to_service", "event_time": "2026-01-29T01:18:30Z", "event_type": "restoration", "gap": null, "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established. Declared actions are simulated recommendations requiring operator authorization; nothing is executed.", "status": "event"}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 452; complete True; first six evidence IDs ["e-1a49bc34ec2ee51fe4f903ab", "e-1a9db1b7be81f47e52981325", "e-2114306494aa6047c273cc77", "e-211e239aed6e7a9da62b7ded", "e-39a8be444139ca2016544329", "e-3afffd08ee22e029a61dddb7"]; quality counts {"good": 26}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-92cc9142e15be5e8c05c1e42"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 52; complete True; first six evidence IDs ["e-1a49bc34ec2ee51fe4f903ab", "e-211e239aed6e7a9da62b7ded", "e-ee3bd1426b8c66cad5fdbfce", "e-1a48a8ba3836a49ce1d84747", "e-b8330d1a5891063c489938fd", "e-f0591b4f2ec957144063d112"]; quality counts {"good": 3}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-92cc9142e15be5e8c05c1e42"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome ok; rows 2; complete True; first six evidence IDs ["e-842f507f4b84a80d9de5fbc2", "e-b0446ae5948372173aff3f9b"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "topology"}; outcome ok; rows 31; complete True; first six evidence IDs ["e-01a3ab01228391cfe128c7e2", "e-944c215d3a2a0a12e79d9d4f", "e-c40a9ef18bd07df22c9bff5a", "e-0b26c2185433df424b5e28c1", "e-4db9809811a652dc313b3fa3", "e-62d70f143d96812bbc83b5e4"]; quality counts {}.

Counterfactual replay diagnostics:
- power_only: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.
- reference.confirm_cause: event, restoration, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap logic_gap. Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.

## c-1b70c44aff25df57fc66 (s021)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: knowledge-tool-unavailable.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:11:00Z (2026-01-29T10:11:00+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "event_interval": {"end": "2026-01-29T00:09:00Z", "start": "2026-01-29T00:08:00Z"}, "event_type": "busbar_trip", "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "tooling_gap", "status": "event"}
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only."]; parameters: {"alarm_mode": "normal", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["logic_gap", "unsupported_inference"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "complete"}.
Public evidence row counts: {"alarms": 1, "scada": 766, "topology": 239}
Reference produced: {"action_ids": ["request_tool_access", "escalate_to_operator"], "asset_ids": ["MURRAY_5B2"], "cause_status": "not_established", "classification": "busbar_deenergization", "event_time": "2026-01-29T00:08:30Z", "event_type": "busbar_trip", "gap": "tooling_gap", "hypotheses": [], "message": "Observed as-of transitions support an event; ultimate cause is not established. Policy tool unavailable; no operational recommendation is authorized.", "status": "event"}
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
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 766; complete True; first six evidence IDs ["e-0aad20b3d313338a112f564a", "e-16e87ade3abe31b27e4dac92", "e-2933a6f9e0547329e5ca29ed", "e-2c0c0f16a2c5b96973efd51c", "e-34eb79854d42e239c089f6ff", "e-414de61f2c3304d299ea24e0"]; quality counts {"good": 26}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 1; complete True; first six evidence IDs ["e-b74bed698bbc86fe64530304"]; quality counts {}.
- Request {"asset_ids": ["MURRAY_5B2"], "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "knowledge"}; outcome denied; rows 0; complete None; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only: no_event, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.confirm_cause: event, busbar_trip, assets ["MURRAY_5B2"]; pass False; gap unsupported_inference. Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.wrong_rule: no_event, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.

## c-af4a0b0c4fd4f46c1808 (s022)

Task/split/incident: action / holdout / murray. Template: operations.busbar_response.v1; variant: vital-data-missing.
Assets: Dederang - Murray line 67 [DMDM_67, line]; Dederang - Murray line 68 [DMDM_68, line]; Murray 5B1 330 kV busbar [MURRAY_5B1, busbar]; Murray 5B2 330 kV busbar [MURRAY_5B2, busbar]; Murray reactor 1 [MURRAY_R1, reactor]; Murray reactor 3 [MURRAY_R3, reactor]; Murray 1 Power Station unit 1 [MURRAY_U1, generator]
Window starts 2026-01-29T00:06:30Z (2026-01-29T10:06:30+10:00 AEST); decision 2026-01-29T00:09:30Z (2026-01-29T10:09:30+10:00 AEST).
Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness 60 seconds; latency budget 120 seconds; extra tolerance 0 seconds.
Expected detection: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "event_interval": null, "event_type": null, "forbidden_action_ids": ["operate_switchgear", "dispatch_without_authorization", "assert_confirmed_cause"], "gap": "data_gap", "status": "insufficient_evidence"}
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

Synthetic authoring assumptions: ["Manual source/fixture-authored expectation; never obtained from pipeline/reference-agent predictions.", "Second 30 inside every minute-precision transition is SIMULATED, not extra report precision.", "Fixture data availability, sensor cadence, quality, noise and decision deadlines are invented.", "Pre-dated generic runbooks are invented fixture policies, not authentic historical AEMO procedures; actions are recommendations/escalations only.", "Counterfactual signal coverage/arrival impairment; no such telemetry failure is claimed by the report."]; parameters: {"alarm_mode": "absent", "asset_kind": "busbar", "cadence_seconds": 10, "diagnostic_risks": ["data_gap"], "event_time_tolerance_seconds": 0, "future_timeline_anchors": false, "label_basis": "report transition intervals plus independent handwritten synthetic policy expectations", "max_latency_seconds": 2, "maximum_detection_latency_seconds": 120, "noise_mw": 0.35, "roles": {"context": ["MURRAY_5B1", "MURRAY_5B2", "DMDM_67", "DMDM_68", "MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "dependent": [], "previously_unavailable": ["MURRAY_U1", "MURRAY_R1", "MURRAY_R3"], "primary": ["MURRAY_5B2"]}, "seed": 20260916, "simulated_minute_second": 30, "stale_after_seconds": 60, "telemetry_mode": "invalid"}.
Public evidence row counts: {"alarms": 0, "knowledge": 5, "scada": 469, "topology": 239}
Reference produced: {"action_ids": ["request_missing_data", "escalate_to_operator"], "asset_ids": [], "cause_status": "not_established", "classification": null, "event_time": null, "event_type": null, "gap": "data_gap", "hypotheses": [], "message": "Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "status": "insufficient_evidence"}
Pass: True; observed gap: data_gap; failure gap: None; failures: [].
Next diagnosis: No failed expectation in this synthetic case; no generalization claim.

Representative public samples (first/last per affected point; complete values in the public input file):

| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |
| --- | --- | --- | ---: | --- | --- |
| No affected-asset usable sample | - | - | - | - | - |

Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "scada"}; outcome ok; rows 469; complete True; first six evidence IDs ["e-1e9bd6d9b5fb746c28f199e2", "e-2a25b1804d213025c2f19089", "e-32b9b63c145431232c6b6e69", "e-4ae7f334d3d9d683ab0ce8cb", "e-5204a98b87ea9ad12682e44b", "e-545ef69b27486f2e4e9b9142"]; quality counts {"bad": 1, "good": 23, "missing": 1, "stale": 1}.
- Request {"asset_ids": null, "case_id": null, "end": null, "limit": 10000, "start": null, "tool": "alarms"}; outcome ok; rows 0; complete True; first six evidence IDs []; quality counts {}.

Counterfactual replay diagnostics:
- power_only: no_event, None, assets []; pass False; gap data_gap. Restore fresh pre/post records and availability coverage; do not train a rule to invent absent evidence.
- reference.confirm_cause: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.deny_scada: insufficient_evidence, None, assets []; pass False; gap tooling_gap. Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.
- reference.drop_records: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.
- reference.wrong_rule: insufficient_evidence, None, assets []; pass True; gap None. No failed expectation.

