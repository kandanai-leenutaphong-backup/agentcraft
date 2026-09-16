# Datacrafting Testbed

**Evidence only. The local Azure Function wrapper and its dependent commands are retired.**
Use the [standalone Content Understanding skill](../../.github/skills/azure-content-understanding/SKILL.md)
for new work. It calls Microsoft's native async SDK with its own uv manifest/lock;
no testbed import, deployment wrapper or local Function host is required.

## Capabilities

| Outcome | Retained Owner |
| --- | --- |
| New extraction and offline recipe tests | [Native SDK skill](../../.github/skills/azure-content-understanding/SKILL.md) |
| Original PDFs and source identity | [Source manifest](source_data/manifest.json) |
| Accepted extraction results and source-based observations | [Evidence index](content-understanding/SKILL.md) |
| Historical cloud ownership and future cleanup prerequisites | [Retired deployment record](deploy/README.md) |

## Inputs And Replay

- [Yallourn PDF](source_data/trip-of-yallourn-w-power-station-unit-3-and-unit-4.pdf):
  7 pages, 586,748 bytes.
- [Murray PDF](source_data/trip-of-murray-5b2-330kv-busbar.pdf): 6 pages, 623,685 bytes.
- [Source manifest](source_data/manifest.json): original user-supplied locations,
  exact hashes and authorization. Copied unchanged; no other documents uploaded.

From the repository root, verify the independent skill without Azure calls:

```bash
uv run --locked --project .github/skills/azure-content-understanding/libraries python -m unittest discover -s .github/skills/azure-content-understanding/tests -q
```

Fourteen tests passed before and after wrapper removal. Follow the skill's setup
and explicit input/target authorization for new analysis. A new extraction is a
billable service call; do not overwrite an existing result directory.

## Verified And Remaining

The two original CU Function receipts and two native-SDK receipts remain unchanged.
Both paths previously passed 32 narrative facts and six table-row checks across
13 pages. The old Function verifier is archived, not runnable in this checkout.
Its [historical receipt schema](RESULT_CONTRACT.md) remains for interpreting results.

Diagrams retain labels/locations, not proven topology or symbol interpretation.
Scanned-document OCR accuracy, large-document/load behavior, generative CU analyzers,
other-user live token tests and precise cost remain unverified. Archived PyMuPDF
materials retain their AGPL/commercial licensing obligations. Source PDFs and
third-party material retain their rights.

This retirement made no Azure calls or changes. Last verified cloud state retained
the Function, hosting resources, CU service and retired DI account. Filesystem
removal does not stop charges or revoke access. The native skill still needs a CU
service. [Cloud cleanup prerequisites](deploy/README.md#teardown) remain documented.

## Portable Native SDK

The registered [skill](../../.github/skills/azure-content-understanding/SKILL.md)
uses Microsoft's `azure-ai-contentunderstanding==1.1.0`. Its own
`libraries/pyproject.toml` and `uv.lock` support independent
copy-out installation. Fourteen native-SDK tests pass; both new live outputs pass
32 narrative facts and six native row-association checks:

- [Yallourn native SDK receipt](content-understanding/results/native-sdk/yallourn/20260916-async-policy/receipt.json): 7 pages, 5 tables, 8.915079 seconds.
- [Murray native SDK receipt](content-understanding/results/native-sdk/murray/20260916-async-policy/receipt.json): 6 pages, 3 tables, 8.789323 seconds.

Those new paid submissions are separate from replay verification of the two frozen
Function outputs. One [earlier SDK capture failure](content-understanding/results/native-sdk/yallourn/20260916-skill-promotion/OUTCOME.md)
has an unknown remote outcome/cost. The async-body capture defect is fixed; the
original failure and successful fresh submissions are retained, not overwritten.

## Removed Wrapper

Removed `azure-extraction`, the Function client/environment, deployment commands,
verifier and derived packages: 8,733 files, 267,535,451 logical bytes. Source PDFs,
CU outputs, the standalone skill and cloud-cleanup evidence were hash-verified
unchanged. [Frozen retirement and recovery record](deploy/records/20260916-function-wrapper-retirement.json).

PyMuPDF, MarkItDown, DI Read/Layout and the comparison executable were retired earlier.
[Historical assessment](content-understanding/evidence/selection/ASSESSMENT.md),
[measurements](content-understanding/evidence/selection/MEASUREMENTS.md), source
renders and [earlier recovery evidence](content-understanding/evidence/selection/cleanup.json) remain.

## Historical Reference

The three imported Hill Climber components now live under ignored `reference/`:
`evaluation_data_crafting`, `evaluation_data_manager`, `evaluation_runner`.
They are protected inspection material, not runtime dependencies of the skill.
Original source revision: `aba1480d78673494aeace9298184a461149437d7`; 198 imported
files originally matched SHA-256 (74 crafting, 88 manager, 36 runner). Their three
contract checks passed on import. Historical cloud/runtime claims were not rerun.
Original repository trees were preserved; library integration remains deferred.

Request and acceptance record:
[timestamped specification](../../specs/20260916T052921Z_AZURE_NATIVE_DATAPROCESSING/README.md).

## Publication Update 2026-09-16

[Last recorded CU-only live acceptance](deploy/records/20260916T083526715583Z-acceptance.json)
passed before local host retirement: three bindings, authenticated persisted result
read-back, retired-route refusal and idempotency. This is historical evidence, not
a fresh liveness check or a reason to retain the wrapper source.