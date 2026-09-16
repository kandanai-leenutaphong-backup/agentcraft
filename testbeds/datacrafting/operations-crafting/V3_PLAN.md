# Operations V3: Plausibility And Distractor Signals

Requested 2026-09-16. Status: v3 accepted for synthetic process review, with explicit
training-realism limitations. Every accepted v2 artifact is preserved; v3 has a
new resource pack, dataset run and independent review evidence.

## User Outcome

Verify SCADA and alarms against the source reports, add at least twice the prior
row count in unrelated noise, and prepare v3. Multiple independent teams generate
and review the work to reduce shared assumptions and accidental duplication.
Each team documents its evidence, method, seed policy, checks and limitations.

## Frozen Acceptance

- Baseline: accepted v2 pack, 22,088 SCADA rows and 70 alarm records.
- Added distractors: at least 44,176 SCADA rows and 140 alarm records. These are
  additions, not total-row targets. Corrections to existing signals are not noise.
- Count raw records and actual as-of visible additions separately, per scenario.
  Required 2x ratios must also hold on the corresponding visible baseline rows;
  future, late, out-of-scope, duplicate or bad-quality records earn no quota credit.
- Noise includes unrelated equipment at the incident stations and clearly
  synthetic other stations. Assets, point semantics, timestamps, units and CIM
  relationships must be consistent; no invented station is claimed as real.
- Noise comes from seeded, temporally coherent scripts, not copied rows with new
  IDs or independent white-noise values that imply impossible equipment behavior.
- No duplicated row IDs or natural keys. Alarm active/clear transitions are
  paired and chronologically coherent. Legitimate repeated measurements over
  time are not duplicates. Same-station and other-station IDs remain disjoint
  between the independent SCADA and alarm authors.
- All baseline/corrected/noise rows are audited. Checked report facts and
  engineering assumptions remain distinct; realistic mock data is not authentic
  AEMO telemetry or a validated power-system simulation.
- Reported chronology, AEST UTC+10, source precision, unaffected/pre-existing
  outages, generation impact, protection behavior and later cause uncertainty
  remain intact. Any corrections are named, never silently relabeled as noise.
- Noise classification and generation policy stay evaluator-only. Public views
  include the distractors, ordinary asset descriptions and as-of data, not a
  per-row `noise` flag, expected label or future report information.
- Keep bounded views. Do not increase query caps or silently truncate data merely
  to meet row targets. Keep old expectations unless independent source review
  establishes an actual error; do not tune fixtures to the reference predictor.
- Run independent source/plausibility and final-artifact reviews, then replay the
  dataset. Correctness/refusal tests, preserved input hashes and deterministic
  repeated generation must pass. Report failures as failures, not target scores.

## Team Boundaries

1. Source verification: read reports and baseline independently; write a bounded
   source-truth/plausibility audit. No generator or grader changes.
2. SCADA noise author: own SCADA distractor module/tests/method report only; no
   alarm or shared integration edits.
3. Alarm noise author: own alarm distractor module/tests/method report only; no
   SCADA or shared integration edits.
4. Final reviewers: independently inspect complete v3 data and public views after
   authors return. They do not grade work they authored or patch generation.

Parent owns shared contracts, integration, necessary source-consistency repairs,
v3 artifacts, replay and final acceptance. No cloud/model calls, resource changes,
physical actions, existing-artifact deletion or changes to canonical skills.

## Baseline Audit And Repair Decisions

Independent source reviewer examined all 22,088 SCADA and 70 alarm records, with
no contradiction in the checked report timestamps, MW anchors or standing outages.
The [audit](../mock-resources/reviews/v3/source-audit.md) nevertheless found one
duplicate natural key and weaknesses in pressure/voltage, alarm lifecycle and
acquisition-quality semantics. Those are not evidence that the source provides
actual waveforms, alarm codes or protection thresholds.

V3 repairs, distinct from noise additions:

- Preserve each original sample's identity unless its measurement time/meaning
  changes; choose an unused timestamp for the late-delivery duplicate probe.
- Define `vacuum_kpa` as absolute condenser pressure. Model a bounded, explicitly
  invented deterioration after common cooling loss and before unchanged source
  trip times; do not claim a real trip threshold or thermodynamic simulation.
- Define generator `voltage_kv` as machine-terminal voltage. Excitation can precede
  synchronization while the breaker stays open and export stays zero. Keep other
  equipment's measurement side documented. Evidence of energization is not by
  itself proof of grid connection or a new event.
- Give ordinary alarms consistent active/clear lifecycle and explicit latching,
  reset and left/right-censoring semantics. A return indication is not a magic
  clear of another code; synthetic reset timing must be named as an assumption.
- Retain missing/flagged test cases, but make stale acquisition and bad numeric
  readings exercise declared held-value/old-time and fault mechanisms. Do not
  count any such excluded rows toward visible-noise quotas.
- Expand the generator's old 30,000-row pack guard only to the already supported
  100,000-row ingestion bound for v3. The 10,000-row per-view/tool limit remains
  unchanged; no data truncation or target-only visibility to manufacture success.

Independent noise authors returned 48,290 SCADA distractors and 184 alarm records
with 5,520 supporting SCADA rows. Counts are pre-integration observations, not yet
final acceptance. Both authors document disjoint assets, deterministic scripts,
seed/parameter choices and unreported engineering assumptions in their own reports.

## Accepted Outcome

[Final review](./REVIEW.md) and
[independent closeout](../mock-resources/reviews/v3/accepted-review.md) own the
source/plausibility, quota, visibility and changed-artifact evidence.

| Acceptance | Observation |
| --- | --- |
| Frozen original denominators | 22,088 SCADA and 70 alarms; v2 hashes unchanged |
| Added noise | 53,810 SCADA and 184 alarms, all as-of visible; every case passes raw/visible 2x floors |
| Full v3 census | 75,908 SCADA, 322 alarms, 51 assets, 8 knowledge documents, 1,525 RDF triples |
| Source/engineering audit | Every row checked; no substantive report or declared-profile contradiction; missing support joins recorded as unknown |
| Uniqueness and bounds | Zero duplicate IDs/natural keys; maximum SCADA/quality view 6,570; no truncation or per-view cap increase |
| Alarm lifecycle | 132 completed same-code episodes and 58 right-censored actives, including 44 auxiliary warnings |
| Public dictionary | Both auxiliary codes/threshold and dwell ranges visible in 20 knowledge-enabled cases; two intentional denials preserved |
| Frozen case truth | All 22 expectations and 11 action notifications unchanged |
| Executable checks | 154 implementation tests pass; independent reviewers document their own checks separately |
| Replay | Reference 14/14 detection and 8/8 action; baseline 9/14 and 2/8; persisted comparison byte-identical |

The independent reviewers did not author the data they audited. Source audit,
SCADA/noise authors, integration, final source/noise reviews and the accepted
delta review each have a distinct method/report under `mock-resources/reviews/v3/`.
The final dictionary correction changed no signal, alarm, asset, topology,
source-event or scenario payload from the independently audited candidate.

Accepted pack manifest SHA-256:
`7c66ded30a1bc631d7cf7ba11b3e6425ccf2afa1e83cea498ed9039bd80238de`.
Accepted dataset manifest SHA-256:
`503e24ddd6dd465cc1a86c59f9cf037ac50f170eec38bfa0c57ed970edb66fca`.

Remaining reviewer findings are not hidden: auxiliary-only distractors can be
filtered by kind; quota-driven cadence/counts and cutoff-relative warnings expose
fixture design; the alarm-author stream can differ across overlapping independent
cases and is not one station history. The public dictionary gives a dwell range,
not each private episode's configuration. V3 therefore establishes source-consistent
mock records and noise exposure, not robust training data, continuous-history
reconstruction, actual instrument accuracy, model performance or generalization.
No cloud/model calls, real telemetry access, physical actions or deletion occurred.