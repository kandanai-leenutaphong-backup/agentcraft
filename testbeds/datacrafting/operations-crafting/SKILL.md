---
name: operations-crafting
description: 'Use when crafting resource-aligned Operations detection/action evaluation datasets from retained native report evidence, validating synthetic CSV/JSON/RDF packs, or running deterministic offline replay and gap diagnostics. Testbed only; no inference, training, arbitrary code, cloud access or physical operations.'
---

# Operations Crafting

## Contract And Authority

Read [CONTRACT.md](./CONTRACT.md) first, then the
[source specification](../../../specs/20260916T102835Z_DATASET_CRAFTING.md).
The shared input names/fields are authoritative. This skill does not change the
contract or generate another optimizer. Future campaigns belong to the public
[OptimizationService contract](../../../libraries/agent-optimization/CONTRACT.md).

Writable scope follows the user's task, not this skill. Generator and pipeline
share the declared data contract, never source imports. Source PDFs, CU outputs,
reviewed source records and accepted packs/runs are immutable inputs. Author a new
version and an explicit migration when a contract changes; do not rewrite old
evidence. Preserve failed/partial outputs. Local generation and replay grant no
cloud/model calls, physical operations or authority over production resources.

This is an explicitly loaded test skill, not automatically installed native skill
discovery under .github/skills. Name matches this directory: operations-crafting.

## Runtime

From repository root. Prerequisites: Linux, uv, Python **3.12**,
the existing locked local project with **jsonschema 4.26.0** and **RDFLib 7.6.0**.
Use the bundled lock. A dependency change requires an explicit scope decision and
regenerated lock plus tests. First-time setup may need package download;
it is not authorization for model calls or source re-extraction.

```bash
uv --version
uv sync --locked --project testbeds/datacrafting/operations-crafting/libraries
uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B -c "import sys; from importlib.metadata import version; print(sys.version); print(version('jsonschema'), version('rdflib'))"
```

Full offline suite, independent of generator completion:

```bash
PYTHONPATH=testbeds/datacrafting/operations-crafting uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B -m unittest discover -s testbeds/datacrafting/operations-crafting/tests -v
```

Focused negative/integrity and decision checks:

```bash
PYTHONPATH=testbeds/datacrafting/operations-crafting uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B -m unittest discover -s testbeds/datacrafting/operations-crafting/tests -p test_core.py -v
PYTHONPATH=testbeds/datacrafting/operations-crafting uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B -m unittest discover -s testbeds/datacrafting/operations-crafting/tests -p test_operations.py -v
PYTHONPATH=testbeds/datacrafting/operations-crafting uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B -m unittest discover -s testbeds/datacrafting/operations-crafting/tests -p test_cli.py -v
```

Tests create temporary lightweight fixtures inside tests/ and remove
only those temporary fixtures. They do not consume or rewrite the generator pack.

## Authoring Procedure

1. Inspect the immutable native CU Markdown and its retained PDF/extraction hashes.
   Existing [native extraction evidence](../content-understanding/SKILL.md) and
   [canonical CU skill](../../../.github/skills/azure-content-understanding/SKILL.md)
   own extraction. Do not re-extract these reports. New extraction requires separate
   input/target authority, not a fallback parser introduced here.
2. Author source event records using exactly the shared contract. Each fact needs
   document ID, SHA-256-pinned PDF and Markdown, exact quote and page. Quote checks
   use CU PageBreak/PageNumber boundaries; unmarked single-page fixtures count as
   page 1. Review factual attribution yourself; substring identity alone does not
   prove a causal conclusion. Preserve actual-actions text and uncertainty verbatim.
3. Normalize AEST with fixed UTC+10, never daylight-saving Australia/Melbourne.
   Yallourn unit 4: 2025-10-16T03:34:29Z; unit 3: 03:34:32Z, one-second intervals.
   Murray trip: 2026-01-29T00:08:00Z; restoration: 01:18:00Z, sixty-second intervals
   with exclusive end. Exact simulated seconds are not source precision. Record
   approximately 1025/1120 or shortly following as uncertain source action text.
4. Resolve canonical IDs and unique aliases against assets. Map point units,
   asset kinds, topology, windows and capabilities before writing labels. Unknown
   real-estate mappings remain binding gaps. RDF/XML is a synthetic CIM-namespace
   subset, not proof of full CGMES conformity or real physical connectivity.
5. Bind generic template slots: asset class/role, event window, observed signature,
   impact, action preconditions and uncertainty. Author positive, negative,
   restoration, multi-asset, bad/stale/missing/delayed and tool-denied cases.
   Planned transitions and pre-existing outages must not become unplanned trips.
   Keep Yallourn development and Murray's holdout split label; holdout is already
   exposed, not an untouched generalization test.
6. Author scenario.expected as reviewed private truth, never a predictor shortcut.
   Operations labels separate observable classification from forensic source class
   and cause. Early cause_status normally stays not_established. Do not require
   exact flooding/control-circuit or staff-error cause from telemetry. Any plausible
   hypothesis is explicitly hypothetical and separate from known facts.
   Classification when required, cause_status and gap must be present and correct;
   a hypothesis is not an implicit alternative to expected not_established.
7. Independently author action event_conditions from source-event definitions and
   scenario subject class, not scenario.expected or predictor output. Each requires
   notification_id, event_type, asset_ids, event_interval, available_at,
   origin=simulated_operator_notification and synthetic=true. Keep source precision;
   select generator/busbar subjects, leaving associated transformers as context.
   Availability at cutoff is a synthetic operator-notification assumption, never
   report availability. No quotes, expected actions, causal truth or future inputs.
   Data-gap actions still get known notifications; detection gets none. Empty action
   conditions refuse. Event start is inside the public window, availability is between
   that start and cutoff; an uncertain interval end may extend beyond cutoff.
8. Action expectations require contemporaneously valid, asset-scoped simulated KB
   action_rules. Historical response is not universally correct policy or a deadline.
   Yallourn support is synchronous-unit/system-strength constraint, not exactly
   597 MW replacement. Request evidence/tool access and escalate where prerequisites
   are absent. Action IDs are recommendations only, never executed operations.
   Reference verifies fresh current state, applicable alarms and every scoped tool
   prerequisite; it does not redetect the original transition. A notification is
   neither proof of state/preconditions nor permission to assert a cause.
9. Use coding-assistant judgment to propose cases, but promote only schema-valid,
   source-verified and human-reviewed instances. No text stubs keyed to expected
   answers. No arbitrary expressions, callback modules, endpoints or subprocess
   definitions in a manifest. Unknown modes fail before data-path access.

## Generate, Craft, Replay, Compare

The accepted pack is [operations-v3-accepted](../mock-resources/packs/operations-v3-accepted/manifest.json).
Start with the [concise review](./REVIEW.md) and [complete accepted cases](./runs/operations-v3-accepted/REVIEW.md).
V3 independently audits source plausibility and adds more than 2x original-row
noise, measured inside actual as-of views. Read [V3_PLAN.md](./V3_PLAN.md) and
the independent reports linked from the review before changing signal semantics.
Earlier packs/runs retain failed and superseded attempts. Use new output directories
for every generation and crafting run. The following command creates a fresh replay
pack; it does not replace the accepted pack:

```bash
uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B testbeds/datacrafting/mock-resources/generate_v3.py --source-root testbeds/datacrafting --baseline testbeds/datacrafting/mock-resources/packs/operations-v2-accepted --output testbeds/datacrafting/mock-resources/packs/operations-next --audit testbeds/datacrafting/mock-resources/reviews/v3/next-integration-audit.json
uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B -m unittest discover -s testbeds/datacrafting/mock-resources/tests -q
```

When that pack exists, craft all cases and execute baseline/reference/ablations:

```bash
uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B testbeds/datacrafting/operations-crafting/craft.py --mode operations --resources testbeds/datacrafting/mock-resources/packs/operations-next --source-root testbeds/datacrafting --output testbeds/datacrafting/operations-crafting/runs/operations-next-review
```

Choose a new basename if output already exists. Identical inputs produce identical
artifact and manifest bytes; no wall-clock timestamp is embedded. Exit 2 means
refusal/integrity failure, not an empty successful dataset. Metrics may honestly
contain failed reference cases even when crafting exits 0.

```bash
PYTHONHASHSEED=311 uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B testbeds/datacrafting/operations-crafting/craft.py --mode operations --resources testbeds/datacrafting/mock-resources/packs/operations-next --source-root testbeds/datacrafting --output testbeds/datacrafting/operations-crafting/runs/operations-next-repeat
uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B testbeds/datacrafting/operations-crafting/craft.py --mode operations --replay testbeds/datacrafting/operations-crafting/runs/operations-v3-accepted --predictor reference --output testbeds/datacrafting/operations-crafting/runs/operations-replay-next
uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B testbeds/datacrafting/operations-crafting/craft.py --mode operations --compare testbeds/datacrafting/operations-crafting/runs/operations-v3-accepted --output testbeds/datacrafting/operations-crafting/runs/operations-compare-next
uv run --locked --project testbeds/datacrafting/operations-crafting/libraries python -B testbeds/datacrafting/operations-crafting/craft.py --mode operations --replay testbeds/datacrafting/operations-crafting/runs/operations-v3-accepted --predictor reference --ablation drop_records --output testbeds/datacrafting/operations-crafting/runs/operations-data-gap-next
```

Other closed ablations: deny_scada, wrong_rule, confirm_cause. They remove data,
deny a capability, corrupt a generic decision rule or assert an unsupported cause.
They do not read labels to manufacture responses. There is no CLI callback loader.
Comparison names the baseline power_only_detection.defer_action: detection uses
MW transitions, action only requests verification/escalation without inspecting
tools. The legacy --predictor power_only selector uses that same split behavior.

## Public Boundary And Callable Use

[craft.py](./craft.py) composes the host registry. [core.py](./core.py) owns
integrity, source evidence, materialization, bounded reads and manifests.
[operations.py](./operations.py) owns mode labels/templates and detection/action
semantics. [replay.py](./replay.py) scores finite trusted callbacks without a model,
optimizer, training loop or subprocess host. [schemas.py](./schemas.py) declares v1
schemas; class/field boundaries are strict, authoring detail objects remain private.

```python
from pathlib import Path
from core import craft_dataset
from craft import MODES, load_dataset
from operations import reference
from replay import evaluate

craft_dataset(
    mode_id="operations", registry=MODES,
   resources=Path("testbeds/datacrafting/mock-resources/packs/operations-v3-accepted"),
    source_root=Path("testbeds/datacrafting"),
    output=Path("testbeds/datacrafting/operations-crafting/runs/new-callable-run"),
)
manifest, public_inputs, private_labels = load_dataset(
    Path("testbeds/datacrafting/operations-crafting/runs/new-callable-run")
)
result = evaluate(public_inputs, private_labels, reference)
```

Set PYTHONPATH as in test commands when importing from repository root. An injected
trusted mode object declares id, version, input_resources and build(bundle); its
string selector is never imported/evaluated. Synthetic injection tests exercise
the same integrity/output pipeline, not another business workflow.

Predictor signature: predict(public_view, EvidenceReader(public_view)). It receives
only already-materialized subsets, not a resource object containing hidden data.
Query(tool, asset_ids=..., case_id=..., start=..., end=..., limit=...) narrows only.
The actual Python method is reader.query. Unknown paths/tools, asset/time/case
widening and row-limit abuse refuse. Both timestamps are filtered. Non-good SCADA
values are withheld; bounded quality metadata distinguishes absence from good zero.
Latest-sample age limit is 300 seconds. Views contain no report hashes/quotes,
scenario/template/split/variant labels, raw pack paths or forensic documents.
Only action views contain validated event_conditions, with opaque notification IDs.
Their subject assets are a nonempty subset of a declared source event's assets;
type and interval must retain that event's identity/precision. Public materialization
does not consult expected labels. An action prediction uses event_time=null and
event_interval, plus structured communication naming notifications, event/assets,
cutoff, verified/unverified/conflicting current state, cause status, evidence and
next steps. Narrative uses public values; narrative quality remains human-reviewed.
Schema v1 is unpublished and tightened in place: legacy action inputs without
notifications refuse with explicit update/regeneration guidance, never backfill.

parameters.stale_after_seconds can narrow the 300-second host freshness bound;
parameters.maximum_detection_latency_seconds supplies the private latency budget.
The integrated pack uses 60 and 120 seconds respectively. Optional version/count/
review annotations, point definitions and native artifact hashes are validated
without requiring them in minimal v1 fixtures. Nested fact/cause/action quotes are
also checked. Generator/review digests lacking an exchange path remain explicitly
unverified provenance declarations. No such field selects code or an expected answer.

This is a data/API boundary for **trusted local callbacks**, not protection against
malicious Python already running in the host process. Do not execute untrusted
callbacks or give an agent the evaluator directory. Filesystem sandboxing, live
authorization and real sensor bindings remain outside this testbed.

## Review And Improvement

Only detection.inputs.jsonl/action.inputs.jsonl are agent-visible; they already
contain their materialized views. Labels, templates, provenance, replay traces,
manifest and REVIEW.md are private evaluation material. Manifest hashes every
included artifact; its own hash is returned separately to avoid recursive hashing.
Output directory creation is exclusive; manifest is written last. Partial output
is preserved on an I/O error, not retried into an existing directory.

Read REVIEW.md, replay/metrics.json, replay/metrics.csv and replay/cases.jsonl.
Inspect source bindings, UTC/AEST precision, evidence cutoffs, expected/produced
structured fields, action prerequisites and exact request/response evidence IDs.
No response narrative is graded by matching prose. Errors/missing outputs stay in
denominators; expected insufficiency can be correct. Wrong assets, future times,
unsupported cause confirmation and forbidden actions fail independently.
Detection P/R, localization, event time and latency count detection cases only.
Action input consistency is receipt consistency, not detection skill. Recommendation
coverage, exact action set, status/gap, prerequisite completeness and communication
are independent measures. Prerequisite completeness requires the expected/alternative
set and supporting evidence, including correct required refusals; separate
action_prerequisite_safety alone can pass for safe but incomplete deferral. No
classification/cause/gap default is inserted from private truth for scoring.

Change only the named data/tool/logic issue and rerun the same focused check.
Review development first. This workflow deliberately compares the full set and
records holdout exposure: **no untouched holdout claim after inspection**. A single
synthetic pass tests plumbing, not learning, generalization or operating readiness.
Keep uncovered physical behavior, real binding/latency and policy gaps explicit.

Recorded 2026-09-16 execution: [local README](./README.md), including test counts,
immutable integrated review paths, repeat-byte evidence and observed limitations.

## Original Documentation

- [Python csv](https://docs.python.org/3.12/library/csv.html)
- [Python json](https://docs.python.org/3.12/library/json.html)
- [Python datetime/timezone](https://docs.python.org/3.12/library/datetime.html)
- [RDFLib parsing and serialization](https://rdflib.readthedocs.io/en/stable/intro_to_parsing.html)
- [jsonschema validation](https://python-jsonschema.readthedocs.io/en/stable/validate/)
- [Native Content Understanding guidance](../../../.github/skills/azure-content-understanding/SKILL.md)