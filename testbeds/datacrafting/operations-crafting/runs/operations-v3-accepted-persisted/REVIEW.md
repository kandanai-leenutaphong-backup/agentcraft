# Offline Replay Review

Visibility: evaluator_only.

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
