# Datacrafting Testbed

**CU-only live publication and portable skill verification passed, 2026-09-16.**

Content Understanding GA `2025-11-01/prebuilt-layout` is the sole runnable method.
This retained reference host accepts two immutable AEMO PDFs through an
Entra-authenticated Azure Function and preserves complete native JSON, Markdown,
input hashes, versions and measured timing. No language or embedding model is deployed.

[Canonical portable guidance](../../.github/skills/azure-content-understanding/SKILL.md)
owns native SDK recipes and its bundled uv project/lock. This testbed remains a
separate callable Function host: it imports no skill code and exports no private
cloud targets into that skill.

The existing Function now publishes only CU extraction, status and health.
Retired routes return 404 without creating jobs. The scoped release leaves unrelated
group resources untouched; group-wide provisioning/teardown ownership checks remain
strict. [Live release evidence](deploy/README.md#cu-only-publication-2026-09-16).

## Capabilities

| Outcome | Owner / Public Entry | Dependencies And Authorization | Verification |
| --- | --- | --- | --- |
| Extract either authorized PDF | [CU adapter](content-understanding/SKILL.md), [pipeline.py](content-understanding/pipeline.py) | isolated uv lock; Entra Function caller | `deploy.sh offline`, existing-result `verify` |
| Native CU and durable jobs | [azure-extraction](azure-extraction/README.md) | injected workload MI, CU and private blob store; one caller/target allowlist | provider, input, ownership, replay and refusal tests |
| Local evidence validation | [receipt verifier](deploy/verify_results.py) | frozen CU outputs and source-reviewed probes; no cloud calls | `deploy.sh verify-results` |
| Resource lifecycle | [deploy/deploy.sh](deploy/deploy.sh), [runbook](deploy/README.md) | exact owned target; separate mutation authority | security readback, exact package, live acceptance |

PyMuPDF, MarkItDown, DI Read/Layout and the comparison executable are retired.
[Historical assessment](content-understanding/evidence/selection/ASSESSMENT.md),
[measurements](content-understanding/evidence/selection/MEASUREMENTS.md), source
renders and provenance remain. Competing raw outputs and runnable sources exist
only in the [external verified recovery archive](content-understanding/evidence/selection/cleanup.json).
No alternative method remains a runtime or validation dependency.
[Result contract](RESULT_CONTRACT.md).

## Inputs And Replay

- [Yallourn PDF](source_data/trip-of-yallourn-w-power-station-unit-3-and-unit-4.pdf):
  7 pages, 586,748 bytes.
- [Murray PDF](source_data/trip-of-murray-5b2-330kv-busbar.pdf): 6 pages, 623,685 bytes.
- [Source manifest](source_data/manifest.json): original user-supplied locations,
  exact hashes and authorization. Copied unchanged; no other documents uploaded.

From the repository root, validate retained results without new analysis jobs:

```bash
bash testbeds/datacrafting/deploy/deploy.sh offline
bash testbeds/datacrafting/deploy/deploy.sh verify-results
bash testbeds/datacrafting/deploy/deploy.sh verify
```

The final command needs the authorized CLI login and reads persisted cloud results,
checks auth/retired-route refusal and replays an existing completed job. A fresh
extraction through the [CU adapter](content-understanding/SKILL.md) creates a paid
analysis job; it is not a verification shortcut. Never overwrite an old result.

## Verified And Remaining

The two frozen CU receipts retain 13 pages, 32 source-checked narrative facts,
six native row associations and five/three page-local tables. The verifier pins
Yallourn `20260916T065358185028Z` and Murray `20260916T065409548693Z`, not the latest
successful run. Frozen artifacts and source/probe hashes are checked on every run.
Current test/release evidence belongs to the [deployment runbook](deploy/README.md).

Diagrams retain labels/locations, not proven topology or symbol interpretation.
Scanned-document OCR accuracy, large-document/load behavior, generative CU analyzers,
other-user live token tests and precise cost remain unverified. Archived PyMuPDF
materials retain their AGPL/commercial licensing obligations. Source PDFs and
third-party material retain their rights.

Dedicated group `rg-agentcraft-datacrafting-20260916` remains allocated in East US.
The DI S0 account and its existing grant are retired but still allocated, not
required by CU. No resource, grant or Entra registration was deleted or revoked.
Dollar cost is unknown; Functions, document analysis, storage, private networking
and logs can charge. [Exact owned-resource teardown](deploy/README.md#teardown).
No unrelated deployments were changed by this experiment.

## Portable Native SDK

The registered [skill](../../.github/skills/azure-content-understanding/SKILL.md)
uses Microsoft's `azure-ai-contentunderstanding==1.1.0`, not the reference-host
transport. Its own `libraries/pyproject.toml` and `uv.lock` support independent
copy-out installation. Fourteen native-SDK tests pass; both new live outputs pass
32 narrative facts and six native row-association checks:

- [Yallourn native SDK receipt](content-understanding/results/native-sdk/yallourn/20260916-async-policy/receipt.json): 7 pages, 5 tables, 8.915079 seconds.
- [Murray native SDK receipt](content-understanding/results/native-sdk/murray/20260916-async-policy/receipt.json): 6 pages, 3 tables, 8.789323 seconds.

Those new paid submissions are separate from replay verification of the two frozen
Function outputs. One [earlier SDK capture failure](content-understanding/results/native-sdk/yallourn/20260916-skill-promotion/OUTCOME.md)
has an unknown remote outcome/cost. The async-body capture defect is fixed; the
original failure and successful fresh submissions are retained, not overwritten.

## Historical Reference

The three imported Hill Climber components now live under ignored `reference/`:
`evaluation_data_crafting`, `evaluation_data_manager`, `evaluation_runner`.
They are protected inspection material, not runtime dependencies of the CU host.
Original source revision: `aba1480d78673494aeace9298184a461149437d7`; 198 imported
files originally matched SHA-256 (74 crafting, 88 manager, 36 runner). Their three
contract checks passed on import. Historical cloud/runtime claims were not rerun.
Original repository trees were preserved; library integration remains deferred.

Request and acceptance record:
[timestamped specification](../../specs/20260916T052921Z_AZURE_NATIVE_DATAPROCESSING/README.md).

## Publication Update 2026-09-16

[CU-only live acceptance passed](deploy/records/20260916T081528584957Z-acceptance.json): exactly three
native bindings; original CU outputs unchanged; Entra denials; DI Read/Layout, PyMuPDF and MarkItDown
routes 404 with no jobs; replay 200 and conflict 409. Offline checks passed 19 lifecycle and 52 total tests.
Only Function package `bf404d06-0df2-42a1-bc39-7fbe9f72f588` was published; no new paid analysis.

All 15 allocated resources retain their observed IDs/tags. The release validates 10 exact required
dependencies; DI, endpoint NIC, two NSGs and untagged Event Grid remain untouched outside its authority.
Whole-group apply/teardown still refuses unknown additions. DI S0 remains allocated and its historical
grant was not revoked. No security setting or Entra object changed; cost remains unknown.
[Append-only preservation evidence](content-understanding/evidence/selection/cleanup.json) records 340
unchanged protected files and unchanged recovery archive/manifests. No publication blocker remains.