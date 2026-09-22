# Evaluation Learning Recipe

Live continuation now belongs to the [new evaluation testbed](../../../testbeds/foundry-agent-evaluation/README.md).
Its authorized attempt blocked at pending-upload destination validation before blob
upload; no evaluation run occurred. This packet CLI remains offline and unchanged.

**Offline CLI implemented. Live SDK recipe documented, not executed or wired into CLI.**
Owner entrypoint: this directory's `deploy.sh`; it never deploys or calls Azure.
Run from repository root. Existing Python standard library suffices for offline actions.
No install, environment creation, cloud provisioning, trace setup or agent changes.

## Offline Sequence

```bash
bash specs/20260922_FOUNDRY_HOSTED_AGENT_EVALUATION/deploy/deploy.sh validate
bash specs/20260922_FOUNDRY_HOSTED_AGENT_EVALUATION/deploy/deploy.sh dry-run
```

Expected: `offline_pass`, 3 rows, 1 synthetic positive, 4 rejected synthetic negatives;
dry-run additionally prints submission bounds and `live_implemented: false`.
Nonzero exit means stop and fix packet inputs; no cloud effect. Actions are repeatable.
`dry-run` validates local data and prints plan only; it is not an SDK request preview.

## Live Gate And Operator Inputs

Complete [spec handoff gate](../../20260922_FOUNDRY_HOSTED_AGENT_EVALUATION.md#mandatory-handoff-gate)
first. Preparation request supplies **no live authorization**. Do not execute snippets
below until separate explicit evaluation approval and accepted hosting v2 evidence exist.

Use one operator and one retained private evidence directory for this example. Prepare
a reviewed JSON handoff with these fields, using actual values rather than placeholders:

| Field | Required source |
| --- | --- |
| `endpoint`, `tenant_id` | Accepted target; currently expected project endpoint `https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry`, tenant `c79ab2bb-79cb-47f1-b4da-b6852fe45ff7` |
| `agent_name`, `agent_version` | Final accepted v2 remote readback; never `latest` |
| `image`, `source_sha256`, `config_sha256` | Final accepted immutable image and source manifest |
| `judge_deployment`, `judge_model_version` | Existing authorized chat-completion judge readback, not target-model guess |
| `acceptance_receipt_path`, `acceptance_receipt_sha256` | Hosting owner's final v2 acceptance and linked evidence |
| `authorization_reference` | Explicit dataset/evaluation/inference grant and bounds |

No runtime handoff file is shipped because those facts are not settled. Manual gate
is intentional; automatic receipt ingestion is not implemented. If v2 changes the nonce
contract, stop before upload. Read-only package facts in source notes are not a dependency
lock; operator must confirm current SDK/service compatibility and record versions.

## Exact SDK Lifecycle Recipe

These Python fragments run sequentially in one authorized operator session. They are
reference code, not commands executed by this packet. `handoff` is the reviewed JSON
object above; `evidence` is an operator-selected `pathlib.Path` in approved private storage.
Do not restart the sequence after interruption. Preserve that directory and reconcile
existing resource IDs. A future live CLI must implement these manual gates, reconciliation
and evidence policy before it can claim unattended readiness.

### 1. Establish Session And Write-Ahead Evidence

```python
import hashlib
import json
import time
from pathlib import Path
from azure.ai.projects import AIProjectClient
from azure.identity import AzureCliCredential

packet = Path("specs/20260922_FOUNDRY_HOSTED_AGENT_EVALUATION")
dataset_path = packet / "dataset.jsonl"
dataset_hash = hashlib.sha256(dataset_path.read_bytes()).hexdigest()
assert dataset_hash == "7fa1aa57385f15a1eaead798f022f7cdb62f8b5a484a1b8bee367336118b3357"
assert handoff["agent_version"] and handoff["agent_version"] != "latest"
assert "@sha256:" in handoff["image"]
assert hashlib.sha256(Path(handoff["acceptance_receipt_path"]).read_bytes()).hexdigest() == handoff["acceptance_receipt_sha256"]
assert handoff["authorization_reference"] and handoff["judge_deployment"]
evidence.mkdir(parents=True, exist_ok=True)

def retain(name, value):
    encoded = json.dumps(value, sort_keys=True, indent=2).encode()
    destination = evidence / name
    with destination.open("xb") as output:
        output.write(encoded)
        output.flush()
    assert destination.read_bytes() == encoded

retain("intent.json", {"handoff": handoff, "dataset_sha256": dataset_hash,
                       "max_uploads": 1, "max_definitions": 1, "max_runs": 1})
credential = AzureCliCredential(tenant_id=handoff["tenant_id"], process_timeout=30)
project = AIProjectClient(endpoint=handoff["endpoint"], credential=credential,
                          retry_total=0, connection_timeout=15, read_timeout=60)
client = project.get_openai_client(max_retries=0, timeout=60)
```

`intent.json` uses exclusive creation: repeat execution refuses before requests.
Before each write below, write its intent; if receipt cannot be saved or response is
unknown, stop. Do not delete intent files to retry. SDK internal dataset-storage retries
and transport timeout propagation are not yet verified; operator must resolve before
claiming hard attempt bounds. No raw credential/token/headers in evidence.

### 2. Upload Or Reuse Dataset

Dataset name `hosted-nonce-learning`; version `sha256-` plus full file hash. Same
name/version is never overwritten with different bytes. Use `datasets.get(name, version)`
first. Only an explicit not-found permits first upload; permission/timeouts are unknown.
For an existing version, require retained upload receipt binding its ID to these exact
bytes and remote content verification. Name alone is insufficient; remote byte-download
verification is a manual gap, not implemented here. Do not choose a fresh name to bypass
an unknown upload. For a confirmed absent version, exactly once:

```python
dataset_name = "hosted-nonce-learning"
dataset_version = "sha256-" + dataset_hash
retain("upload-intent.json", {"name": dataset_name, "version": dataset_version,
                              "sha256": dataset_hash})
dataset = project.datasets.upload_file(name=dataset_name, version=dataset_version,
                                       file_path=str(dataset_path))
retain("dataset.json", {"name": dataset_name, "version": dataset_version,
                        "sha256": dataset_hash, "id": dataset.id})
assert project.datasets.get(name=dataset_name, version=dataset_version).id == dataset.id
```

Confirmed reuse assigns `dataset` from that exact `get`, uses original receipt and does
not upload again. An uncertain upload may have created a blob but not registration;
inspect both through the owning service before any deliberate repair. No automatic retry.

### 3. Define One Evaluation And Submit One Pinned Run

```python
definition = {
    "name": "hosted-nonce-learning-" + dataset_hash[:12],
    "data_source_config": {
        "type": "custom",
        "item_schema": {"type": "object", "properties": {"query": {"type": "string"}},
                        "required": ["query"]},
        "include_sample_schema": True,
    },
    "testing_criteria": [{
        "type": "azure_ai_evaluator", "name": "Coherence",
        "evaluator_name": "builtin.coherence",
        "initialization_parameters": {"deployment_name": handoff["judge_deployment"]},
        "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_text}}"},
    }],
}
retain("definition-intent.json", definition)
evaluation = client.evals.create(**definition)
retain("evaluation.json", {"id": evaluation.id})
request = {
    "eval_id": evaluation.id,
    "name": "hosted-nonce-learning-" + dataset_hash[:12],
    "data_source": {
        "type": "azure_ai_target_completions",
        "source": {"type": "file_id", "id": dataset.id},
        "input_messages": {"type": "template", "template": [{
            "type": "message", "role": "user",
            "content": {"type": "input_text", "text": "{{item.query}}"},
        }]},
        "target": {"type": "azure_ai_agent", "name": handoff["agent_name"],
                   "version": handoff["agent_version"]},
    },
}
retain("run-intent.json", request)
run = client.evals.runs.create(**request)
retain("run-id.json", {"eval_id": evaluation.id, "run_id": run.id})
```

Names aid reconciliation, **not service idempotency keys**. If create times out after
delivery, preserve intent, time, request ID if available and exception class/status/code
without token-bearing text. Inspect existing evaluations/runs in Foundry with owner help.
An unknown result is not evidence of absence. Never resubmit, change parameter spelling
or create another run automatically. Known IDs permit read-only continuation.

### 4. Poll And Retrieve Results, Including Failures

```python
deadline = time.monotonic() + 600
terminal = {"completed", "failed", "canceled", "cancelled"}
for attempt in range(30):
    if time.monotonic() >= deadline:
        break
    run = client.evals.runs.retrieve(run_id=run.id, eval_id=evaluation.id)
    retain(f"poll-{attempt:02d}.json", {"run_id": run.id, "status": run.status})
    if run.status in terminal:
        break
    time.sleep(min(10, max(0, deadline - time.monotonic())))
if run.status not in terminal:
    raise RuntimeError("observation deadline: retain IDs; existing remote work may continue")

aggregate = run.model_dump(mode="json")
page = client.evals.runs.output_items.list(run_id=run.id, eval_id=evaluation.id, limit=4)
items = [item.model_dump(mode="json") for item in page.data]
```

Do not raise on failed/canceled status before retrieving available errors/rows. Retain
aggregate fields `id`, `eval_id`, `status`, `result_counts`,
`per_testing_criteria_results`, `per_model_usage`, `error`, `report_url`; include
response/request IDs, actual timestamps and package versions. Record absent fields as
unknown, not zero. Keep all available row statuses, query, response ID, agent/version,
`sample.output_text`, evaluator score/label/threshold/reason/error and item IDs.

**Sanitization gate before `retain`:** review these allowlisted projections. Strip
report URL query/fragment (can contain signed access data), credentials, headers,
storage URLs with SAS, environment dumps, stack locals and private/model reasoning.
Model answer and evaluator explanations remain untrusted text; review for accidental
disclosure, or retain only hashes plus a restricted-storage reference. The example's
nonce/events are synthetic. Do not persist raw `model_dump` wholesale.

Save reviewed projections with `retain("aggregate.json", sanitized_aggregate)` and
`retain("items.json", sanitized_items)`. If `page.has_next_page()` or more than three
items are returned, record incompleteness and stop; do not silently drop the tail.
For this three-row example `limit=4` makes excess detectable. Fewer than three is also
incomplete, even if run says completed. Pagination beyond this bound requires explicit
investigation, not another inference run. Sanitized items must retain original dotted
`datasource_item["sample.output_text"]` and `query` for local scoring; different service
shape requires a reviewed adapter, never a fabricated passing row.

Close `client`, `project` and `credential` in a `finally` block in any implemented
runner. Closing clients does not cancel evaluation or delete datasets. After timeout,
continue reads of existing IDs under renewed read authority; cancellation is a separate
authorized action (`client.evals.runs.cancel(run_id=..., eval_id=...)`) followed by
terminal-state readback. No cleanup/provisioning is included in this learning packet.

### 5. Score Independently And Return

Save `pins.json` in reviewed evidence containing exactly `source_sha256`,
`config_sha256`, `agent_name`, `agent_version`, all nonempty strings from accepted v2.
Then run from repository root, with `EVIDENCE` set to that actual local directory:

```bash
bash specs/20260922_FOUNDRY_HOSTED_AGENT_EVALUATION/deploy/deploy.sh score \
  --items "$EVIDENCE/items.json" --pins "$EVIDENCE/pins.json"
```

Expected successful proof: `proof_passed: 3`, `total: 3`, exit 0. Wrong/missing
evidence fails/nonzero; no retry or submission follows. Return deterministic pass
count separately from coherence scores and row errors; inspect report in authenticated
Foundry portal using retained eval/run IDs. Aggregate success cannot override missing
proof. This is lifecycle learning, not benchmark/optimizer readiness.

## Unimplemented Live Safety Work

Manual recipe still requires final-v2 receipt interpretation, remote readiness/identity
readback, dataset-byte reuse verification, reviewed evidence projections, write-failure
reconciliation and exception/finally handling. No live CLI, live SDK integration test,
service-side attempt cap or automated sanitized evidence collector is claimed.
These are explicit prerequisites for automation, not permission to execute now.