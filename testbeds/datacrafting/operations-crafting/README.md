# Operations Dataset Crafting

Reusable, mode-aware source/resource validation, private detection/action labels,
public as-of evidence views and deterministic offline callback replay. Synthetic
process validation only: no trained agent, inference, cloud calls or physical action.
Detection discovers events; action starts from independently authored simulated
operator notifications and verifies current recommendation prerequisites.

Start with [REVIEW.md](./REVIEW.md) for the first accepted set and
[SKILL.md](./SKILL.md) for exact locked uv commands and authoring/review procedure.
[CONTRACT.md](./CONTRACT.md) is the input authority;
[specification](../../../specs/20260916T102835Z_DATASET_CRAFTING.md) records intent.

## Capability Ownership

| Outcome | Owner / Public Surface | Dependencies | Verification |
| --- | --- | --- | --- |
| Hash/schema/source evidence and unique resources | [core.py](./core.py): load_bundle, resolve_asset | stdlib, jsonschema, RDFLib | test_core.py |
| Bounded public as-of views | [core.py](./core.py): materialize_view, EvidenceReader.query | Validated bundle, host case scope | test_core.py |
| Operations meaning, labels/templates, observations and recommendations | [operations.py](./operations.py): OperationsMode, reference, power_only | Core public evidence, fixed v1 data contracts | test_operations.py |
| Finite callback replay and separate grading | [replay.py](./replay.py): evaluate, compare, grade_case | Host callback, public view, evaluator-only labels | test_operations.py |
| Immutable run artifacts / trusted mode composition | [craft.py](./craft.py): main, MODES, load_dataset; core.craft_dataset | Known mode object, local roots | test_cli.py |
| Versioned input/output contracts | [schemas.py](./schemas.py) | jsonschema 4.26.0 | Core/CLI contract checks |

No shared library imports or dependency changes. Future campaigns remain owned by
the public [OptimizationService](../../../libraries/agent-optimization/CONTRACT.md).
No arbitrary callback loader, dynamic import, eval, exec or subprocess authoring.

## Input And Output

Independent generator owns the synthetic pack. Craft reads it, source PDFs and
native CU outputs immutably. Mode strings are selected before input filesystem I/O.
Paths must be relative, non-symlink, hash-pinned and confined to their declared root.
CSV/JSON/RDF use stdlib/jsonschema/RDFLib, not handwritten parsers.

Output must not exist. Run contains:

- detection.inputs.jsonl and action.inputs.jsonl: public materialized views only.
- detection.labels.jsonl and action.labels.jsonl: reviewed private truth and bindings.
- templates.json: generic slots plus private source instance bindings.
- provenance.json: private original authoring data, exact quotes/pages/source hashes.
- replay/metrics.json, replay/metrics.csv, replay/cases.jsonl: measured baseline,
  reference and controlled ablations; structured failures and evidence traces.
- REVIEW.md: human-readable named assets, UTC/AEST source precision, evidence windows,
  contemporaneous expected/produced outcomes, forensic truth and gap diagnoses.
- manifest.json: sorted hashes, byte sizes, versions and visibility. Written last;
  its own digest is returned by the CLI. Byte-identical repeated inputs are tested.

All timestamps use canonical UTC; source clocks retain fixed AEST UTC+10. Source
interval ends are exclusive. Source second/minute precision remains distinct from
simulated timing and detection latency. Every view filters both ts and available_at.
Forensic documents are withheld even if a later case cutoff could admit them;
the v1 predictor has no established-causal-evidence contract.

Action views require nonempty `event_conditions`: notification ID, event type,
subject assets, source interval, synthetic availability, fixed operator origin and
synthetic flag. Public IDs are opaque. Associated source assets can remain context
without becoming notification subjects. No quotes, cause, expected actions, future
notifications or private-label backfill. Detection forbids notifications. Current
unpublished schema v1 requires explicit re-authoring of old action inputs; old
packs/runs remain immutable historical evidence, not runnable current datasets.

## Verification

```bash
PYTHONPATH=testbeds/datacrafting/operations-crafting uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B -m unittest discover -s testbeds/datacrafting/operations-crafting/tests -v
```

Independent lightweight fixtures exercise core, CLI and callback behavior without
waiting for the generator. Safety checks include unknown modes/capabilities,
source forgery, path/symlink escape, ambiguous/missing assets, RDF entities and
dangling references, timezone/precision, dual cutoffs, bad/stale/all-unavailable
data, label separation, no-event controls, grouping, wrong assets, overconfident
causes, forbidden actions, missing-output denominators, replay hash tampering,
non-overwrite and deterministic output bytes.

## Observed Run

**Current acceptance: v3**, after independent source/plausibility and noise reviews.
[Review](./REVIEW.md), [accepted run](./runs/operations-v3-accepted/manifest.json),
[persisted replay](./runs/operations-v3-accepted-persisted/REVIEW.md),
[independent closeout](../mock-resources/reviews/v3/accepted-review.md).

- Resource pack: 75,908 SCADA rows, 322 alarms, 51 assets. Added noise alone:
  53,810 SCADA rows and 184 alarms, every row visible by its case cutoff. Every
  case exceeds both original-v2 raw and visible 2x floors. No quota credit for
  baseline corrections, duplicates, late rows or excluded quality.
- 154 implementation tests pass: 70 Operations and 84 generator/noise/integration.
  Independent source/noise audits separately scan all records, check source and
  engineering rules, and document their own reproducible methods.
- Reference remains 14/14 detection and 8/8 action; baseline remains 9/14 and 2/8.
  Given action conditions never earn detection credit. Full persisted replay
  predictions, traces and metrics match the accepted run byte-for-byte.
- Generator connection decisions now distinguish residual/pre-synchronization
  terminal voltage from actual breaker/MW connection. Busbar rules stay unchanged.
  Latched protection snapshots and resets are not new incident edges. No labels
  were changed to repair these semantics.
- Source profiles are plausible synthetic assumptions, not a validated physical
  simulation. All distractors are auxiliary, and scenario cadence/count/cutoff
  patterns still reveal fixture structure. AS_ histories are separate case
  realizations; do not concatenate them. These are explicit reviewer limitations,
  not passed robustness or generalization tests.

## Historical V2 Run

2026-09-16: **66 Operations tests and 36 generator tests pass**, retaining the
original 49 and 34 tests with updated action semantics. Locked runtime
observed: Python 3.12.3, jsonschema 4.26.0, RDFLib 7.6.0. Editor diagnostics clear.
The full command above runs all three suites; focused commands are in the skill.

- [Accepted review](./runs/operations-v2-accepted/REVIEW.md): 14 detection
  and 8 action cases; 11 notifications across the action inputs only.
- [Measured results](./runs/operations-v2-accepted/replay/metrics.json):
  reference detection 14/14 passes, event P/R 1.0/1.0, zero false positives;
  reference action 8/8 passes, recommendation recall/exact, prerequisite completeness,
  status/gap, input consistency and structured communication all 1.0. Detection
  event denominator is 6, not 12; action conditions never add detection credit.
- Baseline `power_only_detection.defer_action`: detection 9/14 passes, recall 0.5;
  action 2/8 passes, recall/exact/prerequisite completeness 0.25. Deferral does not
  earn missing-prerequisite credit. Safety and completeness are separate metrics.
- Ablation failures: dropped records 16 `data_gap`; denied SCADA 22 `tooling_gap`;
  wrong rule 10 `logic_gap` and 2 `tooling_gap`; confirmed cause 12
  `unsupported_inference`. Correct expected insufficiency remains a pass.
- [Published pack](../mock-resources/packs/operations-v2-accepted/manifest.json):
  `operations-v2-1608c23b93bcef8a499f`; manifest SHA-256
  `dd107ec3e7bd7f6d124c366c337713de84f7e720e931ac8d403706d08a0eef3d`.
- [Repeat](./runs/operations-v2-review-corrected-repeat/manifest.json): 10 artifacts
  plus manifest; separate-process manifest SHA-256
  `6379c87ea1bd5602169b3c43269c8e4cef629b01fb86cc0ac2dc23b24865dd5f`.
  [Persisted comparison](./runs/operations-v2-review-corrected-compare/REVIEW.md)
  repeats all six configurations from pinned inputs/labels without raw reports.
- Parent integration regenerated the published pack and accepted run in fresh
  destinations: both match the independent corrected/repeat artifacts. A fresh
  [accepted-run replay](./runs/operations-v2-accepted-replay/REVIEW.md) also matches
  predictions, traces and metrics byte-for-byte. Both full suites were rerun.
- All original private expectations, source-event bytes, assets, SCADA, alarms and
  topology are unchanged. Legacy v1 crafting/replay refuse before output creation.

The requested [operations-v2 pack](../mock-resources/packs/operations-v2/manifest.json)
and [first v2 review](./runs/operations-v2-review/REVIEW.md) retain the failed attempt:
three Yallourn actions incorrectly treated associated transformers as generator
notification subjects. Source-class authoring fixed that; no labels were changed.
The corrected pack was published into the fresh `operations-v2-accepted` directory;
the occupied v2 path and all prior runs were not overwritten. Historical v1 scores
used the old conditional/grading semantics and are not current acceptance evidence.

This is a synthetic process test, not learning/generalization. Holdout was inspected;
compatibility and review changes followed. No untouched-holdout claim. Next step:
human review, not a model campaign or operation.

## Limits And Assumptions

- Callbacks are trusted local functions. Public data is partitioned; Python is not
  a malicious-code sandbox. Do not expose labels/provenance/raw paths to an agent.
- Core byte bound: 64 MiB/file; row/triple bound: 100,000; public view/tool bound:
  10,000 rows per table; authored evidence window: seven days maximum. Oversized
  views refuse instead of dropping tails. Query truncation is explicitly marked.
- Default freshness and detection latency budget: 300 seconds. Extra event-time
  tolerance: zero beyond the source interval, unless explicitly authored. These
  are synthetic assumptions, not operating limits or source assertions. Input
  parameters.stale_after_seconds may narrow freshness; the integrated pack uses
  60 seconds. parameters.maximum_detection_latency_seconds supplies its authored
  120-second detection budget. No expected label is used to choose these values.
- Reference uses 5/25 MW thresholds and 10%/80% nominal-voltage states plus digital
  transitions. Available alarms corroborate; only declared generic trip/planned
  codes carry semantic state. Asset dispatch availability is not breaker state.
- Action rules are valid scoped KB data; all plans are simulated recommendations.
  Action checks fresh current subject-asset state without requiring the original
  pre/post transition. Latest protection/return indications are latched event
  records; a cleared or benign alarm cannot satisfy a required trip indication.
  Missing current SCADA yields insufficiency; missing tools yield `tooling_gap`;
  incomplete policy scope yields `knowledge_gap`. Action `event_time` stays null;
  `event_interval` preserves notification uncertainty, even if its exclusive end
  extends past cutoff. Structured communication does not self-grade narrative quality.
  Yallourn support is about synchronous-unit combinations/system strength, never
  automatic 597 MW replacement. Source causes/classifications remain forensic.
- Classification, cause status and expected gap must match explicitly. No scoring
  defaults come from private truth; no undocumented cause alternative is accepted.
  Detection rejects operational recommendations; justified data/access escalation
  is allowed. Mock tool/asset/state checks are not real protection or limit approval.
- Topology/inventory are assumed static and contemporaneously known. KB without
  valid_to remains valid indefinitely. No real asset mapping, authorization,
  physical fidelity, source completeness or policy correctness is established.
- All Yallourn variants remain development; all Murray variants holdout. Full
  comparisons explicitly disclose holdout exposure and make no untouched-holdout,
  training, generalization or production-readiness claim.
- Manifest integrity detects changes against recorded hashes, not authenticity of
  a malicious author who can replace the manifest and all inputs together.
- Optional generator/review/source-manifest digests without an exchange file path
  remain declared provenance, not independently authenticated source artifacts.

No separate investigation notebook: reproducible local tests and generated review
carry this increment's evidence; rediscovery requires one offline command.