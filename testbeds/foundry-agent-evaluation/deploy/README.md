# Reusable Skill: Hosted Evaluation Integration

Use for a bounded three-row Foundry evaluation capability proof against an already
accepted hosted agent. Owner: this testbed. Not a global harness skill, optimizer,
statistical evaluation, native tool evaluator or deployment engine.

**Historical outcome: completed, 2026-09-22.** One registered dataset/version, one
definition and one completed run. Coherence scores 4, 4, 2 at threshold 3;
deterministic oracle 3/3. Eighteen tests pass. No optimization claim.
[Final receipt](records/20260922T075756325970Z-closeout.json), SHA-256
`1d1caa3fd83116ff8476c97c496ee28122bd5092dfac1972e3287590d6964a9f`.

## Migration Canary (Current Procedure)

Fresh `migration-e-final-h-v3` closes the final-host handoff gap: [verification](records/migration-e-final-h-v3/20260922T194842941922Z-verify.json)
proves three complete finite rows, coherence 4/4/4, oracle 3/3, exact accepted H
version 3 and registered dataset byte identity. `builtin.coherence` remains version 12.
Evaluation `eval_3bce450418e240c698ec262828d96c4a`; run
`evalrun_e56c2dc6860e4cd1975d7e92f0a2bd8b`. Source/config/image pins and prior
added-tool acceptance were verified before upload; no H deployment occurred.
Prior [version-1 verification](records/migration-e-v1/20260922T181808468298Z-verify.json)
remains historical collector evidence, not the final-host handoff.
Both series are settled; do not replay writes.
[F09 authoritative acceptance](../../../agentcraft_projects/foundry-official-integration-20260922/records/v2/20260922T200128628556Z-f09-migration-accepted/record.json)
was published 2026-09-22; 26 unchanged-source tests remain the final E evidence.
[Append-only F07 correction](../../../deploy/remediation-evidence/20260922T193935Z-acceptance-gaps/README.md).

The following records the completed sequence, not a new execution grant. For a
separately authorized new series, freeze new names/nonces and exact final accepted
build/deploy/invoke/verify hashes before upload. A deploy receipt alone is insufficient.
`H_DEPLOY` here was `testbeds/foundry-hosted-agents/deploy/records/migration-h-v1/20260922T183120213195Z-deploy.json`.
From repository root:

```bash
E_MANIFEST=testbeds/foundry-agent-evaluation/deploy/env/migration-e-final-h-v3.json
E_SHA=$(sha256sum "$E_MANIFEST" | cut -d ' ' -f1)
E_RUN=(bash testbeds/foundry-agent-evaluation/deploy/deploy.sh)
E_FLAGS=(--manifest "$E_MANIFEST" --manifest-sha256 "$E_SHA")
"${E_RUN[@]}" validate
"${E_RUN[@]}" manifest-check "${E_FLAGS[@]}" --hosted-receipt "$H_DEPLOY" --hosted-sha256 "$(sha256sum "$H_DEPLOY" | cut -d ' ' -f1)"
"${E_RUN[@]}" preflight "${E_FLAGS[@]}"
"${E_RUN[@]}" freeze "${E_FLAGS[@]}"
"${E_RUN[@]}" upload "${E_FLAGS[@]}"
"${E_RUN[@]}" define "${E_FLAGS[@]}"
"${E_RUN[@]}" submit "${E_FLAGS[@]}"
"${E_RUN[@]}" reconcile "${E_FLAGS[@]}"
"${E_RUN[@]}" verify "${E_FLAGS[@]}"
```

Run only with F08 live authority. `freeze` pins a catalogue coherence version and
judge model. `deployment_name` stays unchanged; no unverified switch to `model`.
Definition readback, exact query/row membership, completed statuses, criterion
name/version/metric and finite nonboolean scores are required. `criterion_passed`
is separate from `complete`, `oracle_passed` and integration `accepted`: a genuine
low coherence score is retained, not a transport error or a reason to rerun inference.
O's versioned correct/wrong mapping canary supplies the explicit 1/0 scoring proof.
Both standard and native-field mappings returned 1/0/0 with exact counts. Catalogue
list/get differed only in `created_at`/`modified_at`; only those timestamps are excluded
from executable-contract comparison. Evals adds criterion ID and known null typed
fields; requested name/version/mapping/init fields remain exact. Initial readback
failures were repaired against the same stored run without new inference. Boolean
counts, nonfinite scores and unexpected criterion fields refuse.

All fresh inputs/receipts live under `records/migration-e-final-h-v3/`. Initial H receipt
binding is immutable. Unknown reservation/upload/registration uses `inspect-upload`
with the same flags; unknown Evals submission uses retained IDs and `reconcile`.
Never remove intents or rerun writes. `register-existing` is unavailable.

## Prerequisites

Use existing `/usr/bin/python3` 3.12.3 and Azure CLI identity matching the committed
[authorization](records/approved-decision.json). No venv or implicit installs.
Observed packages: `azure-ai-projects==2.6.1`, `openai==3.13.0`,
`azure-identity==1.26.0b2`, `azure-storage-blob==12.26.0`. Exact import origins and
judge/model/version/capabilities are retained in [selection](records/selection.json).
Editor diagnostics passed; selected editor interpreter was not observed.

Evidence ledger, run manifest, version, sanitization and evaluation read-back checks
come from [`foundry_ops`](../../../libraries/foundry-ops/README.md); `experiment.py`
prepends `libraries/foundry-ops/src` to `sys.path` (no install). Receipts retain its
source digests as `foundry_ops_source`. Storage, dataset, closeout, freeze, define
and submit stay here. New intents carry `recorded_at`; retained intents keep `utc`.

F01 dependency profile is H's [host lock](../../foundry-hosted-agents/deploy/host-requirements.lock),
with complete pinned wheels and canonical library metadata; no E-specific installer.
Use its [uv-only procedure](../../foundry-hosted-agents/deploy/README.md#locked-profiles).
Default uv inventory sees zero packages on this workstation; inventory existing
user/system targets explicitly. Existing shared conflicts are not repaired globally.

Explicit grant covers dataset/evaluation writes and inference, not unrelated
RBAC/policy, secrets, private data or destructive cleanup. Never dispatch an overseer,
directly or indirectly. This experiment dispatched no workers.

## Historical Operator Sequence (Not Executable)

Run from repository root through the single entrypoint:

```bash
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh validate
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh preflight
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh freeze
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh upload
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh define
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh submit
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh reconcile
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh verify
```

**Current checkout is settled: do not rerun the write sequence.** Freeze,
registration, definition and run already exist. `reconcile` and `verify` read the
existing run; `closeout` reads retained verification plus current dataset/host pins.
The sequence above describes a newly authorized experiment, not a second run here.
Each experiment needs its own scoped evidence/identities; do not erase intents.

Every action prints a receipt path/hash, exits nonzero on failure, and preserves
prior evidence. Read its `status`, not merely the printed path. `freeze` and each
write intent use exclusive creation; names are not service idempotency keys.
No upload, definition or run automatically retries. SDK transport retries are zero.
The same existing run can be read with `reconcile` after a local timeout; never
resubmit to obtain results. Each reconciliation is bounded to 30 reads, ten-second
intervals and a 600-second local deadline. Timeout does not cancel server work.

Read-only upload reconciliation:

```bash
bash testbeds/foundry-agent-evaluation/deploy/deploy.sh inspect-upload
```

This command reports named dataset and credential metadata without fetching
arbitrary URLs or retaining credentials. Historical 404s established absent
registration, not absent reservations. Current dataset exists and byte readback passes.

## Public APIs And Evidence

- `AIProjectClient.agents.get_version` checks version, active status, immutable image
  and source/configuration metadata. Existing hosting source archive is hash-checked,
  not copied or inferred from dirty Git HEAD. Accepted host remains unchanged.
- `deployments.list/get` supplies judge capability and model identity. Use typed
  `model_name/model_version` properties: raw `as_dict()` wire keys differ. No extra
  inference probe was needed; the actual run returned three judge scores.
- `datasets.get`, `pending_upload`, Blob `ContainerClient.upload_blob`,
  `datasets.create_or_update`, `get_credentials` implement upload and byte readback.
  Convenience `upload_file` passes Blob retry/timeout kwargs. Explicit public stages
  remain for pre-byte destination validation, returned prefix handling, separate
  reservation/upload/registration intents, and remote byte/hash recovery.
- `client.evals.create/retrieve`, `evals.runs.create/retrieve`,
  `evals.runs.output_items.list` own evaluation lifecycle. No guessed portal status.
  Definition, submission, polling and output retrieval passed against the live service.
- [Packet oracle](../../../specs/20260922_FOUNDRY_HOSTED_AGENT_EVALUATION/deploy/example.py)
  is imported directly. Exactly three distinct queries/output IDs are required;
  pagination or missing/foreign/duplicate rows cannot pass. Prose alone fails.
  `tool_events` are host-generated JSON text, not native function-call records.
  Coherence is instructional; independent SHA-256 proof and loaded pins decide tool
  acceptance. Neither establishes general quality or statistical improvement.

## Correct Contract And Recovery

Inspected installed Projects 2.6.1 public models and implementation before recovery:

| Typed model/property | Wire field | Meaning |
| --- | --- | --- |
| `PendingUploadResponse.blob_reference` | `blobReference` | Container-level read/write/list SAS reference |
| `pending_upload_id`, `version`, `pending_upload_type` | `pendingUploadId`, `version`, `pendingUploadType` | Reservation identity and asset version/type |
| `BlobReference.blob_uri` | `blobUri` | Upload path, documented as `/Container/Path` |
| `storage_account_arm_id` | `storageAccountArmId` | Account identity, possibly provider subscription |
| `BlobReferenceSasCredential.sas_uri`, `type` | `sasUri`, `type` | Container SAS URL and `SAS` discriminator |
| `FileDatasetVersion.data_uri`, `type` | `dataUri`, `type` | Query-free blob URI, `uri_file` |

References: [BlobReference](https://learn.microsoft.com/python/api/azure-ai-projects/azure.ai.projects.models.blobreference?view=azure-python),
[ContainerClient](https://learn.microsoft.com/python/api/azure-storage-blob/azure.storage.blob.containerclient?view=azure-python),
[version-pinned official sample](https://raw.githubusercontent.com/Azure/azure-sdk-for-python/azure-ai-projects_2.6.1/sdk/ai/azure-ai-projects/samples/datasets/sample_datasets.py).
Official sample uses `datasets.upload_file`; installed implementation constructs
`ContainerClient.from_container_url(sas_uri)`, uploads the basename, and registers
query-free `blob_client.url`. This runner separates those steps for provenance,
prefix validation and per-stage recovery; Blob kwargs alone do not establish those
guarantees or bound every service stage. No credential is printed here.

Use `urlsplit`, normalize implicit/explicit HTTPS 443, decode path once, and compare
account plus exact container segment. Credential URI must identify one standard
Azure container; `blobUri` may name that container or a contained upload prefix.
Require containment, never arbitrary host equality or whole-URL equality. SDK
container parser unquotes its last segment; a nested container URL is not a valid
standard Azure container. Pass decoded blob names to SDK; it handles percent encoding.
Reject traversal, encoded traversal, malformed escapes, userinfo, fragments,
foreign hosts, wrong ports and private DNS. Offline model fixtures cover camelCase
wire fields, nested paths, encoded slash/space/percent/container and default ports.
Nested-prefix behavior is offline-tested; live service returned a container root.

Every pending/credential response is captured in an exclusive timestamped receipt
before provenance/destination validation: reservation ID, version/type, account ARM
ID, blob URI, credential type and container URL. Strip query, fragment and userinfo;
never retain SAS or auth headers. Authenticated exact project response establishes
managed-storage provenance, not authority to follow arbitrary URLs. Exact account
ARM/Blob-host correspondence and public DNS are still required.

**Version limit:** registration rejects >50 characters, although pending upload
accepted the old 71-character version. Valid version is
`sha256-7fa1aa57385f15a1eaead798f022f7cd`; full SHA-256 remains the content pin.
Four reservations total: two local refusals, one upload with invalid-version
registration, then valid-version success. Registration-only diagnostic replay
captured the exact HTTP 400 after the old exception handler discarded its message.
`register-existing` is retired from implementation and dispatch. Use read-only
`inspect-upload` for an uncertain new upload; never replay an old reservation.
Recovery checked legacy and new version absence and preserved all old intents.
[Recovery assignment evidence](records/diagnosed-recovery-authority.json) and
[version diagnosis/addendum](records/version-recovery-evidence.json) replace the
historical arbitrary reservation stop gate, not the one registered version/eval/run bounds.
Unknown write outcomes require readback; concrete access/provider incompatibility stops.

**Result shape:** actual `sample.output[].content` contains a JSON-encoded list of
`output_text` blocks. Decode the list, extract text, and cross-check against the
service-generated `datasource_item["sample.output_text"]`. Never confuse judge
`results[].sample` with target output. A premature generic SDK-shape assumption
caused first reconciliation to report false oracle failures; retained real rows
proved the adapter defect. Corrected adapter passes all three unchanged oracle
checks; no new evaluation or inference. Generic OpenAI serialization warns about
Foundry's `azure_ai_target_completions` extension; wire fields remain retained.

## Historical First Two Attempts

First upload stopped at `foreign storage ARM identity`, after `pending_upload`
returned but before blob bytes or final dataset registration. The initial checker
required storage in the caller subscription. That assumption was not established
for Foundry-managed storage. It must not be relaxed to arbitrary endpoints.

Capture gap: returned nonsecret storage identity was not saved before validation;
exact returned identity and reason for mismatch are unknown. SAS was never written
or printed and expired in process memory when the action exited. Named dataset and
credential reads returned 404, so that response cannot currently be recovered through
these APIs. Preserve failure and intent; do not delete them to retry.

The user authorized exactly one additional reservation in
[recovery decision](records/reservation-recovery-decision.json), recorded before action.
Second response supplied storage account `saja5wdacq3zex2` in provider subscription
`d4b89623-911e-42b6-b8b3-067246110cb2`. Its ARM and Blob hostname correspond;
response came from the exact authenticated project endpoint and DNS checks passed.
[Nonsecret metadata](records/pending-upload-metadata.json) was retained before
destination comparison. That comparison failed before any blob write. Blob URI
includes explicit `:443`; credential container path was not retained, so a port-only
cause is **unverified**. Port normalization is now tested; future metadata capture
includes the full nonsecret container URL. Neither change recovered the memory-only SAS.

At that historical checkpoint, dataset and credential GET returned 404 and no
third reservation had been attempted. The current assignment subsequently authorized
diagnosed recovery; see the completed sequence above. Historical receipts stay immutable.

## Managed Storage Rule

Installed `azure-ai-projects==2.6.1` uses service-returned
`blob_reference.credential.sas_uri` with `ContainerClient.from_container_url`.
It does not require the storage account to share the caller subscription.
Retain SDK source path/hash and inspected contract in the result receipt.

1. Pin the project HTTPS endpoint and authenticate through the existing Azure identity.
  Require response request provenance under that exact project's dataset API.
2. Capture ARM ID, Blob URI and credential container URL with query/fragment removed
  **before** destination validation. Never retain SAS or authorization headers.
3. Require exact ARM storage-account correspondence to
  `<account>.blob.core.windows.net`, HTTPS port 443, no userinfo or traversal,
  and exclusively public DNS addresses. Arbitrary URLs/private networks remain refused.
4. Canonicalize explicit/default HTTPS ports, decode once, and require exact
  container containment for the service upload prefix. Do not require whole-URL
  equality or infer containment from hostname alone.
5. Use bounded, no-retry Blob SDK upload and verify exact frozen bytes through
  registered dataset credentials. Registration is not proof of uploaded byte integrity.

SDK `pending_upload` documentation says it **initiates or retrieves** a pending upload.
`get_credentials` applies to a dataset version; it returned 404 for this unregistered
version. No read-only pending-reservation recovery method appears on installed
`DatasetsOperations`. A failed process cannot recover its memory-only SAS locally.
Do not delete an intent or silently issue another potentially creating request.

## Verification And Limits

[Final validation](records/20260922T075746929453Z-validate.json): 18 tests, including
actual retained-row replay. [Live verify](records/20260922T075653771799Z-verify.json):
completed run, exactly three distinct scored outputs, 3/3 deterministic proofs,
no pagination or evaluator errors. Coherence has two passes and one genuine fail;
threshold and rubric unchanged. Closeout rechecked host/judge pins and all 134
dataset bytes. Every linked evidence digest was independently checked locally.

Retained: unchanged hosting and judge, registered dataset/blob, definition, completed
run, one orphan uploaded blob, possible reservations. No cleanup, RBAC change,
new agent, optimization or worker dispatch. No owned background process remains.
Reported judge usage is 5,978 tokens across three invocations; service repeats that
usage under two aggregate groups, so do not sum them. Target token usage, provider
internal retries, reservation retention, total task duration and cost remain unknown.
Per-action durations and failed attempts are in closeout. Full tool transcript stays
host-owned; syntax failures before runner startup lack JSON action receipts.

The following paragraphs preserve historical pre-recovery verification and gaps;
they are superseded by the current evidence above:

Twelve offline tests cover oracle negative controls, exact dataset identity, duplicate
and missing rows, unknown-write refusal, path containment, unsafe storage URLs and
credential/query sanitization, remote version/image/source/config mismatch,
provider-managed provenance, explicit HTTPS ports and private-DNS refusal.
Local guards do not establish live acceptance.
Final metadata-capture edit initially had an indentation error; local validation
refused before cloud activity. Corrected same slice; nine tests then passed.
The earlier packet-root README read failed because that file does not exist;
its deploy README is the packet's operator entrypoint. No source was overwritten.
First closeout failed with `NameError` because its function was accidentally nested.
Receipt verification exposed it; module scope and a callable guard were corrected,
nine tests passed, and read-only closeout succeeded. Initial receipt-link verification
also failed while inspecting that failed receipt; neither failure retried cloud writes.
No remote dataset bytes, three-row scores, oracle verdicts or report URL exist yet.
Definition/submission/reconciliation code remains unexercised against a real run;
result shapes may require a reviewed adapter, never fabricated passing rows.

Receipts retain code digests, measured action duration and available SDK/CLI IDs.
Whole-task duration, tokens, costs and hidden service attempts are unknown. Initial
manual reads/tool calls remain in host history, not a complete local action ledger.
No authoritative optimization record or global skill was published. Existing source
archive and hosting package-inventory evidence remain with the hosting owner.
No pending local process, worker or evaluation run. Storage reservation settlement
is unknown; no cleanup was authorized or attempted.

[Final blocked result](records/20260922T074135995532Z-closeout.json), SHA-256
`7c151582470fc1234d166dd844c14d9dd64eaeec07a0431b9dbb5052a88cedd0`,
retains fresh absent-dataset and active-host readback, three unscored rows,
attempt counts, pins, retained resources, evidence hashes and next decision.
It supersedes the interpretation in the earlier recovery closeout
`20260922T074029199833Z-closeout.json`: explicit port was observed, but port-only
causation was not proven. All prior receipts remain unchanged. Recovery's initial
patch also failed local indentation validation before cloud activity; repaired and
validated. No live E2E acceptance was achieved.