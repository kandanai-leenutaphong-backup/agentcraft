# Operations Testbed Exchange Contract

Version 1. Shared input boundary between deterministic mock-resource generation and
the mode-aware crafting pipeline. Neither implementation may import the other's
source; both use this data contract and the isolated uv environment in `libraries/`.
The source specification is [dataset crafting](../../../specs/20260916T102835Z_DATASET_CRAFTING.md).

## Commands And Ownership

From the repository root:

```bash
uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python testbeds/datacrafting/mock-resources/generate.py --source-root testbeds/datacrafting --output NEW_PACK
uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python testbeds/datacrafting/operations-crafting/craft.py --mode operations --resources NEW_PACK --source-root testbeds/datacrafting --output NEW_RUN
```

`--output` must not exist. No overwrite or destructive cleanup. `source-root` is
the trusted host's retained extraction/source root. Relative manifest paths cannot
escape their declared root; no symlink/URL/code loading. All CSVs use UTF-8,
one header row and standard CSV quoting. All timestamps use canonical UTC ISO 8601
`YYYY-MM-DDTHH:MM:SSZ`; source AEST/precision is retained in authoring records.

## Resource Pack

`manifest.json`: `schema_version: 1`, `synthetic: true`, `seed: 20260916`,
`resource_pack_id`, `resources` and `authoring` lists. Each list entry has
`id`, `path`, `sha256` and `description`. Resources are exactly `assets`, `scada`,
`alarms`, `knowledge`, `topology`. Authoring entries are exactly `source_events`
and `scenarios`. Every path is relative to the pack, immutable and hash-checked.
The manifest additionally documents synthetic assumptions and real-binding gaps.

Files:

| ID / File | Shape |
| --- | --- |
| `assets`, `assets.json` | Object with `synthetic: true`, `assets: [...]` |
| `scada`, `scada.csv` | Columns `row_id,scenario_id,ts,available_at,asset_id,point,value,unit,quality,synthetic` |
| `alarms`, `alarms.csv` | Columns `row_id,scenario_id,ts,available_at,asset_id,code,state,severity,message,synthetic` |
| `knowledge`, `knowledge.json` | Object with `synthetic: true`, `documents: [...]` |
| `topology`, `topology.rdf` | RDF/XML using CIM vocabulary plus a declared mock namespace; explicit no full-CGMES-conformance claim |
| `source_events`, `authoring/source_events.json` | Object with `schema_version: 1`, `visibility: evaluator_only`, `documents`, `events` |
| `scenarios`, `authoring/scenarios.json` | Object with `schema_version: 1`, `synthetic: true`, `visibility: evaluator_only`, `scenarios: [...]` |

CSV `synthetic` is the literal `true`. SCADA value is numeric text, or empty only
for missing quality. Quality is `good`, `missing`, `stale` or `bad`. Alarm state
is `active` or `cleared`. No text field carries expected labels/cause truth.

Assets require `asset_id`, `name`, `aliases` (list), `kind`, `station`, `cim_id`,
`synthetic: true`, `attributes` (object). Optional source evidence belongs in the
authoring records, not an agent-visible inventory. Canonical IDs used for joining:
`YWPS_U1`, `YWPS_U2`, `YWPS_U3`, `YWPS_U4`, `YWPS_T3`, `YWPS_T4`,
`YWPS_COOLING`, `JEERALANG_A2`, `JEERALANG_A3`, `JEERALANG_B3`,
`LYA_U1`, `LYA_U3`, `LYB_U2`, `MURRAY_5B1`, `MURRAY_5B2`,
`DMDM_67`, `DMDM_68`, `MURRAY_U1`, `MURRAY_R1`, `MURRAY_R3` as needed.
These are mock IDs, not actual SCADA point IDs or official CIM mRIDs.

Supported point names: `active_power_mw`, `breaker_closed`, `voltage_kv`,
`flow_mva`, `rating_mva`, `cooling_flow_pct`, `vacuum_kpa`, `available`.
Digital states are 0/1. Signals that are not physically measured are explicitly
synthetic, not reconstructed from source. IDs, voltages and topology must agree.

Knowledge documents require `id`, `title`, `kind`, `asset_ids`, `valid_from`,
`available_at`, `text`, `synthetic: true`, `action_rules: [...]`. `kind` is
`runbook`, `limits`, `maintenance` or `forensic`. Generic fixture runbooks can
pre-date incidents; incident-specific investigation text must be later and must
not enter an as-of agent view. `action_rules` are plain data:
`event_type`, `action_ids` (list), `required_tools` (list), `rationale`.
No arbitrary expressions, code or network paths. These are simulated policies,
not instructions to operate real equipment. Capability IDs are `scada`, `alarms`,
`knowledge`, `topology`.

## Report Evidence And Scenarios

Source documents carry `id`, `pdf_path`, `pdf_sha256`, `extraction_path`,
`extraction_sha256`, `timezone: AEST`, `utc_offset: +10:00`. Paths are relative
to the separately supplied trusted source root. Event records carry `id`,
`incident_id`, `asset_ids`, `event_type`, `reported_time`, `precision`,
`event_interval: {start,end}`, `classification`, `cause`, `source_refs`,
`actual_actions`. `source_refs` contain `document_id`, `page`, `quote`; each quote
must be an exact substring of the declared CU Markdown and manually attributable
to that page. Source `end` is exclusive. Second-precision events span one second;
minute-precision events span sixty seconds. Approximate actions retain their text
and a named synthetic uncertainty assumption rather than fake exact source time.

Each scenario requires:

```json
{
  "scenario_id": "s001",
  "incident_id": "yallourn",
  "split": "development",
  "kind": "detection",
  "template_id": "operations.generator_transition.v1",
  "variant": "report-aligned",
  "source_event_ids": ["yallourn-unit4-trip"],
  "window_start": "2025-10-16T03:33:00Z",
  "decision_time": "2025-10-16T03:34:31Z",
  "asset_ids": ["YWPS_U3", "YWPS_U4"],
  "tools": ["scada", "alarms", "knowledge", "topology"],
  "parameters": {},
  "assumptions": [],
  "expected": {
    "status": "event",
    "event_type": "generator_trip",
    "asset_ids": ["YWPS_U4"],
    "event_interval": {"start": "2025-10-16T03:34:29Z", "end": "2025-10-16T03:34:30Z"},
    "cause_status": "not_established",
    "action_ids": [],
    "forbidden_action_ids": [],
    "gap": null
  }
}
```

Examples fix field names, not performance targets. `kind`: `detection` or `action`.
`split`: `development` for all Yallourn variants, `holdout` for all Murray variants.
Status: `event`, `no_event`, `insufficient_evidence`. `event_type`:
`generator_trip`, `busbar_trip`, `restoration`, or null. Multiple generator trips
share one type and multiple asset IDs. For non-events and unobservable cases the
expected interval can be null. `gap`: null, `data_gap`, `logic_gap`, `tooling_gap`,
`knowledge_gap` or `unsupported_inference`. Scenario IDs must be opaque and never
encode their label. Reference-agent logic must not branch on IDs, incident names,
report times or the synthetic `variant`.

Action IDs are a closed mock vocabulary: `confirm_event`, `assess_system_strength`,
`consult_limit_advice`, `request_authorized_support`, `notify_operator`,
`investigate_cooling`, `review_protection_work`, `apply_temporary_line_ratings`,
`verify_restoration`, `remove_temporary_line_ratings`, `request_missing_data`,
`request_tool_access`, `escalate_to_operator`. Forbidden examples:
`operate_switchgear`, `dispatch_without_authorization`, `assert_confirmed_cause`.
Action records use the same evidence/time fields; expected actions are grader-only.

### Conditional Action Inputs

An action scenario additionally carries `event_conditions`: an explicitly authored
list of simulated operator/event-service notifications. These are **task inputs**,
not the agent's detection answers. Each notification requires `notification_id`,
`event_type`, `asset_ids`, `event_interval`, `available_at`,
`origin: simulated_operator_notification`, `synthetic: true`. No source-report
quotes, expected actions or causal truth belong here. The generator owns their
values independently of predictor outputs. They need not claim a precise second
beyond the source interval and must be available no later than the case cutoff.

All known-event notifications are explicitly assumed for this synthetic action
task. The agent must still query the currently available resource tools to verify
the event state and satisfy recommendation prerequisites. Missing measurements
can correctly lead to `insufficient_evidence` even when an operator notification
exists. A notification is not permission to switch, dispatch or assert a cause.

Detection scenarios do not carry these notifications. Crafting must not manufacture
them by copying private `expected` labels. Agent action views materialize only the
validated as-of notifications, with asset/time confinement. Grading action quality
does not score receipt of this supplied event as an independently detected event;
aggregate event precision/recall and localization denominators use detection cases
only. Action views without a defined conditional input contract must refuse.

## Crafting Outputs And Agent Boundary

Operations mode produces `detection.inputs.jsonl`, `detection.labels.jsonl`,
`action.inputs.jsonl`, `action.labels.jsonl`, parameterized `templates.json`,
`provenance.json`, an immutable manifest, scored replay results and `REVIEW.md`.
Label/provenance files are evaluator-only; agent execution receives a separately
materialized case view containing only task, IDs/assets, time bounds and bounded
as-of evidence/tool capabilities. No raw manifest paths, report text, expected
values, variant/split labels or future investigation documents enter that view.

Mock query functions enforce case scenario/asset scope, event-time and
availability-time cutoffs, accepted quality and bounded rows. Unknown tables/tools,
asset widening and label access refuse. A function receives a host-vetted case
view, not a filesystem handle to authoring records. This is an API/data boundary,
not a malicious-code sandbox; no arbitrary callback code is executed.

Reference predictions use `status`, `event_type`, `asset_ids`, `event_time`,
`cause_status`, `action_ids`, `gap`, `message`, `evidence_ids`. Score them against
private expectations; keep prediction errors/abstentions/missing outputs visible.
Synthetic baseline/reference and ablations prove the workflow, not model learning.

The trusted mode registry supports `operations` and injectible test implementations;
no mode string is passed to an import, `eval`, shell or dynamic loader. Validation
must precede output creation. Both generator and crafting artifacts are reproducible
from identical inputs, seed and mode version, excluding only a separate run receipt
if it contains timing metadata. Hashes must identify every included artifact.