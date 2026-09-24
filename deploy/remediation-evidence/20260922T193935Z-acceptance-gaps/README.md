# Acceptance Gap Correction

Assigned gaps closed; **F09 authoritative publication remains pending**. Worker
evidence only. Original F00-F08 receipts, review, H/E history and final H/O artifacts
remain immutable. [Assignment](request.json), [prewrite pins](prewrite-pins.json),
[original independent review](../20260922T174900Z-f08/acceptance-review.json).

## C04 Actual Concurrent Builds

[Owning build receipt](../../../testbeds/foundry-hosted-agents/deploy/records/migration-h-overlap-v1/20260922T194519593953Z-build-overlap.json)
records **43.349496 seconds** of provider execution overlap. Direct CLI returned
IDs, never inventory differences, associate each submitted context/tag with its run.

| Run | Frozen Tag | Provider Start UTC | Provider Finish UTC | Image SHA-256 |
| --- | --- | --- | --- | --- |
| `crm` | `gap-20260922-c04-a` | 19:45:36.786512 | 19:46:26.530980 | `72828ac3023c76ab1811860b1aa9d0e95c959a80444c55a87dbd71ac6f22c2b9` |
| `crn` | `gap-20260922-c04-b` | 19:45:43.181484 | 19:46:29.625145 | `0a73fbea5867c69c23330ac0f6f193abaf54f900dc1bb9f5e0afea7c5dd1544d` |

Both date 2026-09-22, status `Succeeded`. Same existing locked archive:
`5b4b55fb65684a90ce5c75fe9a4eb6c5aab2fde70bd49df89923eedca02fbb95`;
source `5cb22af25af1b384fcafd11490f5bf95fa42b9eea2d781e2cb44f2025def0594`.
Each run's output digest equals its exact-tag readback. Build-only: no agent version,
deployment or serving-image change. Retained images incur unknown storage cost.
Prior actual dropped-result recovery `crf` is reused; no extra unknown write induced.

## Fresh E Final-Host Handoff

[Fresh verification](../../../testbeds/foundry-agent-evaluation/deploy/records/migration-e-final-h-v3/20260922T194842941922Z-verify.json):
three complete finite rows, coherence **4/4/4**, oracle **3/3**, no skipped/error rows.

- Dataset: `migration-e-final-h-v3`, version `sha256-2b026a9dd07b4a5c2b32e6cf6e5b9fba`.
- Full dataset SHA-256: `2b026a9dd07b4a5c2b32e6cf6e5b9fba95ade66827617af60bed883739133f34`.
- Evaluation: `eval_3bce450418e240c698ec262828d96c4a`.
- Run: `evalrun_e56c2dc6860e4cd1975d7e92f0a2bd8b`, `completed`.
- Agent: `agentcraft-migration-tool-proof-v1`, explicit version `3`.
- Config: `e47cedf678a9e29c96926b8008c89059a51180be2d0303b4cd8abea80704cf72`.
- Image: `sha256:2d0b5bbe7a41321ba80e0cd5f663b534be63efb86cf53b3ccda99d0573c26cdd`.
- Source: `5cb22af25af1b384fcafd11490f5bf95fa42b9eea2d781e2cb44f2025def0594`.

Unchanged coherence v12, judge `gpt-5.6-luna` model version `2026-07-09`.
Dataset bytes, stored run/output identities and exact loaded pins verified.
Prior H added-tool/protected/stored-response acceptance checked before upload.
Original E-v1/H receipts unchanged. No statistical or improvement claim.

## F07 Append-Only Correction

[Reproducible measurements](measurement-addendum.json) supersede only the incorrect
mutation-site count and missing baseline bridge, not historical source receipts.

| Same 19 Production Files | Lines | Functions | Install Sites |
| --- | ---: | ---: | ---: |
| F00 | 3501 | 144 | 5, non-uv |
| F01 / F02 prechange | 3523 | 144 | 3, all uv |
| Final at independent review | 4291 | 172 | 3, all uv |
| Current gap closure | 4372 | 173 | 3, all uv |

F01 added 22 lines. Review final minus F00: 790; minus F01: 768. Current adds
81 lines for the bounded build-only owner action. Tests/docs/locks/wheelhouse/data/
evidence excluded; nested functions counted by AST. No net code-reduction or
measured effort-savings claim. Custom authenticated HTTP sites **6 -> 1**;
manual bearer sites **2 -> 0**. Three active dependency mutations are H's installer
and both H/O Dockerfiles. The old matcher missed `uv --no-config pip install`.

## Verification And Scope

H **41** tests pass, including foreign run/tag/digest and unknown-submit refusal.
E **26** and O **46** unchanged-source test receipts reused. Source, procedure/test
hashes, recovery archive and command evidence are bound in [worker handoff](handoff.json).
C09 remains pass with local task/client lifecycle tests and live terminal cancelled
readback; live downstream closure/no-further-dispatch is **not_verified**.
No new optimizer, holdout, cancellation or foreign-credential run; no dependency,
environment, grant, auth, teardown or authoritative-record changes. No agents dispatched.

## Reproduction

From repository root, existing Python only. Read-only evidence checks:

```bash
python3 -B deploy/remediation-evidence/20260922T193935Z-acceptance-gaps/finish.py verify-bindings
python3 -B deploy/remediation-evidence/20260922T193935Z-acceptance-gaps/finish.py verify-final
```

`measure`, `snapshot`, `close` are append-only preparation actions and refuse
existing output names. Do not replay completed cloud writes. H/E runbooks document
their owning deployment entrypoints and immutable manifests/intents.
MAX requested; effective runtime effort, tokens and provider cost unknown.
Blocking commands prevented continuous 60-second clock checks; boundary checks retained.
Original mission deadline 2026-09-22T21:06:18Z unchanged. No notebook entry needed:
this bounded correction retains its own primary evidence; publication belongs to overseer.