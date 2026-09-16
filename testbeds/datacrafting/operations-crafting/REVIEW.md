# Operations V3 Dataset

**V3 ready for human review.** Independent teams audited every SCADA/alarm row,
authored unrelated signals, and checked the combined dataset against both reports.
The same 14 detection and 8 conditional-action cases now include more than twice
the v2 row count in additional, as-of-visible noise. Source expectations are unchanged.
This is a source-consistent synthetic process fixture, not authentic telemetry or
a trained or operationally validated agent.

This review and all labels are evaluator-only. An evaluated agent receives only
the materialized input files or their bounded tool views, never this answer-bearing
review, source reports, raw pack, label files or provenance.

## Review Files

| Item | Accepted Artifact |
| --- | --- |
| Full request and mode design | [Specification](../../../specs/20260916T102835Z_DATASET_CRAFTING.md) |
| Replicable test skill | [SKILL.md](./SKILL.md) |
| Mock resource inventory and hashes | [Resource manifest](../mock-resources/packs/operations-v3-accepted/manifest.json) |
| Fake SCADA | [scada.csv](../mock-resources/packs/operations-v3-accepted/scada.csv): 75,908 rows |
| Fake alarms | [alarms.csv](../mock-resources/packs/operations-v3-accepted/alarms.csv): 322 rows |
| Fake knowledge base | [knowledge.json](../mock-resources/packs/operations-v3-accepted/knowledge.json): 8 documents, including the synthetic instrument/alarm dictionary |
| Fake CIM topology | [topology.rdf](../mock-resources/packs/operations-v3-accepted/topology.rdf): 1,525 triples |
| Asset/resource bindings | [assets.json](../mock-resources/packs/operations-v3-accepted/assets.json): 51 assets |
| Detection dataset | [Agent inputs](./runs/operations-v3-accepted/detection.inputs.jsonl), [private labels](./runs/operations-v3-accepted/detection.labels.jsonl) |
| Action dataset | [Agent inputs](./runs/operations-v3-accepted/action.inputs.jsonl), [private labels](./runs/operations-v3-accepted/action.labels.jsonl) |
| Generalizable structure | [Parameterized templates](./runs/operations-v3-accepted/templates.json), [source provenance](./runs/operations-v3-accepted/provenance.json) |
| Complete case walkthroughs | [Generated review](./runs/operations-v3-accepted/REVIEW.md) |
| Actual predictions and tool evidence | [Replay cases](./runs/operations-v3-accepted/replay/cases.jsonl), [metrics](./runs/operations-v3-accepted/replay/metrics.json) |

## Noise And Source Corrections

| Records | V2 Original | V3 Corrected Base | Added Noise | V3 Total |
| --- | ---: | ---: | ---: | ---: |
| SCADA | 22,088 | 22,098 | 53,810 | 75,908 |
| Alarms | 70 | 138 | 184 | 322 |

Additions alone exceed the required **44,176 SCADA / 140 alarm** floors; corrections
receive no noise credit. Every one of the 22 cases passes both raw-baseline and
visible-baseline 2x checks. All added rows reach actual public inputs/tool queries.
Same-station versus other-station additions: **32,015 / 21,795 SCADA** and
**102 / 82 alarms**. Auxiliary equipment is fictional even at named real stations;
Wattle Junction, Wattle Reach and Quartz Bend are fictional other stations.

SCADA profiles use independent seeded smooth loads and board-correlated voltage,
not cloned rows. Alarms have supporting measurements, threshold/dwell/hysteresis
rules, 70 complete noise episodes and 44 still-active warnings. The full alarm
table has 132 completed episodes and 58 right-censored actives. There are zero
duplicate row IDs or natural keys and no silent truncation; the largest view has
6,570 SCADA/quality records against the unchanged 10,000-row cap.

The base audit led to named repairs: remove a duplicate late-probe key; make
cooling loss precede absolute-pressure deterioration and protection trips; model
machine excitation separately from breaker closure; give indication/clear records
consistent lifecycle semantics; and represent genuine old stale acquisitions plus
bounded bad readings. Report-backed times, MW anchors, outages and private labels
remain intact. All invented response times and instrument meanings are documented.

## Independent Team Reports

| Team | Method And Evidence |
| --- | --- |
| Source verifier | [Baseline source audit](../mock-resources/reviews/v3/source-audit.md), independent all-row oracle |
| SCADA author | [SCADA method](../mock-resources/reviews/v3/scada-method.md), seed domain `scada-v3` |
| Alarm author | [Alarm method](../mock-resources/reviews/v3/alarm-method.md), separate seed domain `alarms-v3` |
| Integrator | [Corrections and census](../mock-resources/reviews/v3/integration-method.md), [final private origin audit](../mock-resources/reviews/v3/accepted-integration-audit.json) |
| Independent source reviewer | [Final source/engineering audit](../mock-resources/reviews/v3/final-source-review.md), all rows checked without author imports |
| Independent noise reviewer | [Final noise/public-view audit](../mock-resources/reviews/v3/final-noise-review.md), quotas, duplication and bias checks |
| Independent closeout reviewer | [Accepted delta review](../mock-resources/reviews/v3/accepted-review.md), final dictionary scope, immutable signals and label verification |

Final source review found no substantive report/engineering contradiction under
the stated mock model. Ninety-nine missing simultaneous support joins remain
explicit unknowns, not fabricated evidence. The final dictionary correction makes
both auxiliary codes and settings available in 20 knowledge-enabled cases; two
deliberately denied cases still refuse. Earlier candidate reviews remain unchanged;
the closeout proves the accepted signals match the reviewed candidate byte-for-byte.

## What The Cases Ask

Detection: given telemetry available by a cutoff, identify event, asset, time and
observable classification; distinguish normal, pre-existing outage and insufficient
evidence. Reports provide private truth and source timing, not agent-visible answers.

Action: given an explicit simulated event notification, verify current state,
applicable policy and tool prerequisites, then recommend the next steps. It does
not ask the agent to detect the same event again. Eleven notifications occur only
in the eight action inputs and contribute no detection credit.

| Case | Decision Time, AEST | Expected Outcome |
| --- | --- | --- |
| s001, detection | 16 Oct 2025 13:34:31 | Detect YWPS unit 4 trip at 13:34:29 from 298 MW to zero plus breaker evidence. Residual machine-terminal voltage does not imply connection. Unit 3 has not yet tripped at this cutoff. |
| s002, detection | 16 Oct 2025 13:35:59 | Correlate unit 4 and unit 3 trips, with 298/299 MW pre-event values. Describe generation disconnection; do not claim the flooded circuit is proven by SCADA. |
| s012, detection | 29 Jan 2026 10:09:10 | Detect Murray 5B2 busbar de-energization in the reported 10:08 minute. No generation loss is required; other units/reactors were already unavailable. |
| s008, action | 16 Oct 2025 13:37:29 | Given the two unit trips, confirm current state, assess system strength, consult advice, request authorized support, notify and investigate cooling evidence. Not a rule to replace exactly 597 MW. |
| s019, action | 29 Jan 2026 10:11:00 | Given the busbar trip, confirm state, review protection work and limits, recommend authorized temporary line-rating action, and notify. The mock policy is not authentic AEMO procedure. |
| s020, action | 29 Jan 2026 11:19:30 | Given restoration, verify return and recommend removal of applicable temporary ratings before notifying. Reported restoration is minute-precision 11:18. |
| s017 / s022 | 29 Jan 2026 10:09:30 | Missing vital SCADA is a data gap. State insufficiency and request data/escalation; a known notification does not authorize blind action. |
| s010 / s021 | Respective action cutoff | Knowledge capability is unavailable: request tool access and escalate, not invent policy. |

AEST is fixed UTC+10, not Melbourne daylight-saving time. Minute-precision report
times remain intervals; simulated second 30 is not extra historical precision.
Report causes and final findings remain private hindsight. Earlier agent cause
status is `not_established`, even when the grader knows the later explanation.

## Measured Outcome

| Predictor | Detection Passed | Detection Precision / Recall | False Positives | Action Passed | Action Recall / Exact |
| --- | --- | --- | --- | --- | --- |
| Weak MW-only detector / notification-only deferral | 9/14 | 1.0 / 0.5 | 0 | 2/8 | 0.25 / 0.25 |
| Evidence-based deterministic reference | 14/14 | 1.0 / 1.0 | 0 | 8/8 | 1.0 / 1.0 |

There are six positive detection cases, four normal controls and four expected
insufficiency cases. Missing predictions/errors remain in denominators. Action
conditions are supplied inputs, not scored detections. Safe deferral and a complete
recommendation are scored separately; correct escalation in a gap case can pass.

Controlled failures demonstrate that this dataset can identify what needs work:

- Remove records: 16 failures diagnosed as data gaps; six already-insufficient
  cases still correctly abstain.
- Deny SCADA: 22 tooling-gap failures, kept distinct from missing measurements.
- Corrupt the decision rule: 12 failed cases, with observed diagnoses preserved
  rather than forcing every failure into the injected label.
- Assert unsupported causes: 12 claims rejected despite otherwise correct event
  and action fields. Matching hindsight by guessing does not earn credit.

These scores test a small deterministic reference against authored synthetic rules.
No LLM, learning campaign, weight fine-tuning, cloud call or physical operation ran.

## Verification And Iteration

154 implementation tests pass: 70 crafting/replay and 84 base/noise/integration
checks. They cover source/schema/hash/point integrity, causal profile and alarm
semantics, source precision, all-case quotas, public visibility, duplication,
refusals, dictionary scope, strict grading, deterministic generation and replay.
Independent reviewers ran their own source and public-boundary checks separately;
their observations are not counted as implementation tests or statistical confidence.

A fresh [persisted replay](./runs/operations-v3-accepted-persisted/REVIEW.md)
reproduced all predictions, traces and metrics without rereading reports.
The accepted pack's only changes from the independently audited candidate are
the public dictionary and manifest. Source, waveform, alarm, asset/topology and
scenario bytes are unchanged. The v2 packs and all candidate/repeat runs remain.

The first implementation coupled action to redetection and gave implicit credit
for missing classifications. Those defects were corrected and regression-tested.
An initial v2 fixture included transformer context as notification subjects; the
rejected pack/run remains, and the accepted pack selects source event subjects.
Old artifacts are historical; no scores or inputs were overwritten to appear green.

## Review Limits

**Noise exposure is proven, training robustness is not.** All new equipment is
auxiliary, so the reference's generator/busbar classification can reject it by
kind; action scopes appropriately select the given event assets. Row-count,
cadence and cutoff patterns still expose fixture construction. Alarm-author
profiles are independent case realizations and can disagree across overlapping
cases for the same asset/time; do not concatenate them into a continuous station
history. The public dictionary declares dwell ranges, not each private episode's
exact selected configuration. These reviewer findings remain explicit, not fixed
by a perfect reference score. Larger balanced backgrounds and competing in-class
events would require another benchmark increment, not a stronger claim about v3.

Runbooks, waveforms, alarm codes/arrival times, exact knowledge dates and detailed
CIM connectivity are invented. Real tag/mRID mapping, resource permissions,
sampling, authentic operating policies and physical behavior remain unverified.
The RDF/XML is a CIM-namespace subset, not full CGMES validation or a power-flow model.

Action grading checks recommendation categories, evidence prerequisites and
structured communication. It does not yet prove an optimized dispatch choice,
correct real-world setpoint, detailed action timing or retrospective root-cause
reasoning. Narrative quality remains a human review dimension.

Yallourn variants remain development and Murray variants remain holdout, but both
were inspected during this process. There is no untouched holdout or demonstrated
generalization. For meaningful agent improvement, review labels/policies first,
bind real resources, then run a separately frozen evaluation on additional incidents.