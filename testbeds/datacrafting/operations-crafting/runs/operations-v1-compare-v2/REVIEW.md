# Offline Replay Review

Visibility: evaluator_only.

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
