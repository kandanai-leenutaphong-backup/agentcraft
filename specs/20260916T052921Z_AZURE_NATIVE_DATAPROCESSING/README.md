# Azure-Native Data Processing Experiment

Requested: 2026-09-16. Historical comparison completed: five methods, ten successful
extractions. Subsequent user decision selected Content Understanding, retired the
four alternatives and promoted [the portable skill](../../.github/skills/azure-content-understanding/SKILL.md).
This document preserves the original experiment scope and marks its superseded state.

## User Request

Use uv for dependency management. Find and test the most effective and most
Azure/Foundry-native method for processing and extracting both supplied PDFs:

- `C:\Users\hchoong\Downloads\trip-of-yallourn-w-power-station-unit-3-and-unit-4 (1).pdf`
- `C:\Users\hchoong\Downloads\trip-of-murray-5b2-330kv-busbar.pdf`

Copy inputs into source data. Build a range of methods in separate folders under
`testbeds/datacrafting/`. Each folder contains an extraction pipeline, local or
cloud-based as an Azure Function, a results folder, and a replicable `SKILL.md`
linking original documentation. Compare extracted outputs for relative
completeness and quality. Document this request here before executing autonomously.

The user authorizes implementation decisions, required cloud resource deployment
and cloud execution. This is not permission to modify unrelated deployments,
disclose credentials, disable authentication, or delete pre-existing resources.

## Scope And Initial Hypothesis

Local Markdown conversion provides a low-cost baseline; Azure Document Intelligence
may better preserve tables and source locations, while Content Understanding may
add semantic extraction. These are hypotheses, not measured results.

Start with these independently reproducible candidates:

| Method Folder | Intended Role | Execution |
| --- | --- | --- |
| `pymupdf/` | Existing-family raw-text and Markdown baseline | Local |
| `markitdown/` | Microsoft's multi-format converter | Local |
| `document-intelligence-read/` | Native OCR/text extraction | Azure Function |
| `document-intelligence-layout/` | Native structure, tables and Markdown | Azure Function |
| `content-understanding/` | Foundry-native document analysis | Azure Function |

If a service/API/region cannot be exercised, retain the exact refusal evidence and
distinguish unsupported or blocked from successful. Do not name an unrun method the
winner. Substitution requires the same objective and a recorded reason.

## Layout And Ownership

- `testbeds/datacrafting/source_data/`: the two unchanged source PDFs, SHA-256,
  original locations and provenance. Do not upload other local files.
- Each method: uv project/lock, callable pipeline, `SKILL.md`, and `results/`.
- Root comparison: one common result contract, bounded source-based probes,
  assessment and reproducible commands. No application frontend is required.
- `testbeds/datacrafting/deploy/`: sole lifecycle owner for experiment resources,
  `deploy.sh` entry point, non-secret targets, runbook and read-back receipts.
- Existing ignored `reference/`: historical implementations and acquired external
  documentation; never silently promoted into production dependencies.
- The original Hill Climber repository and unrelated worktree changes are untouched.

## Acceptance

1. Both copied PDFs match source hashes. Inputs are immutable across methods.
2. Dependencies are resolved and executed with uv; locked versions are recorded.
3. Each method exposes explicit source and output paths, preserves provider-native
   output plus comparable extracted text, and records tool/API/model versions,
   source hash, measured duration, status and errors without credentials.
4. Cloud functions require authentication and explicit application authorization;
   workload access uses managed identity. Verify positive invocation and anonymous
   refusal. No cloud success claim based only on a deployment status.
5. Run each available method on both PDFs and retain results separately. A failed
   extraction never becomes an empty success or silently replaces earlier evidence.
6. Compare text coverage, named facts/numbers, ordering, tables, source locations,
   omissions, duplication and usability. Raw PDF text is a baseline, not ground
   truth. Visually inspect source pages that support decisive quality claims.
7. Prefer first-party APIs where they perform adequately. Report effectiveness,
   Azure nativeness, runtime and cost knowledge separately; no unmeasured score or
   inferred service bill. Generated text is not source truth.
8. Every `SKILL.md` provides prerequisites, exact replay commands, output contract,
   limitations and original documentation links. Report cloud resources left
   running and their exact cleanup command; do not delete unrelated resources.

## Execution Boundaries

Cloud targets will be frozen from observed subscription/tenant state before writes.
Use a dedicated, tagged experiment resource group and explicit subscription flags.
Record service SKUs, region, owned identity/grants, lifetime and cost controls before
deployment. Do not silently switch the shared Azure CLI account or fetch secret
values. Restrict model/document processing to these two user-authorized inputs.

Local fixtures and contract tests precede cloud rollout. The comparison checks the
integrated artifacts, not only component reports. Cloud-only gaps remain explicit.

## Initial Evidence

- Input files observed through `/mnt/c/Users/hchoong/Downloads/`.
- Yallourn: 586,748 bytes. Murray: 623,685 bytes.
- `uv` and `az` are installed. No cloud mutation performed at spec creation.
- Initial evidence preceded cloud creation. Final results and remaining limits follow.

## Frozen Cloud Scope

- Observed subscription: `67255afe-8670-4401-a1b8-df6ca63a3516`.
- Observed tenant: `c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`; cloud: `AzureCloud`.
- Dedicated resource group: `rg-agentcraft-datacrafting-20260916`.
- Authorized experiment-owned service set: Azure Functions and required hosting
   storage/identity, Document Intelligence and a Foundry/AI Services resource.
   Prefer consumption hosting and pay-per-use analysis; avoid provisioned throughput.
- Role assignments must be limited to owned resources and the execution identities
   that need them. Do not grant subscription-wide roles or mutate shared Entra apps.
- Service location/SKU support must be checked before creation, then recorded in
   `testbeds/datacrafting/deploy/env/` together with exact resource names.
- Initial lifetime: this experiment and replay inspection. Document ongoing charges
   and an exact owned-resource teardown command; deletion is not automatic.

## Historical Acceptance

| Requirement | Observation / Evidence |
| --- | --- |
| Immutable source data | Both copies match original SHA-256; [manifest](../../testbeds/datacrafting/source_data/manifest.json). Yallourn 7 pages, Murray 6. |
| uv dependency management | Each method has its own project and frozen lock. Shared Azure implementation and offline comparison have separately locked environments. |
| Per-method pipelines/results/skills | Originally five callable CLIs/skills; [current retained capabilities](../../testbeds/datacrafting/README.md#capabilities). Alternatives are now archived outside the workspace. |
| Actual local/cloud execution | Four successful local runs, six successful Azure Function runs; failed earlier attempts retained. |
| Common output and integrity | [Result contract](../../testbeds/datacrafting/RESULT_CONTRACT.md), ten hash-verified receipts and complete native output. |
| Relative quality | 32 narrative probes per method's text output; six source-row probes for each Azure layout method; visual page inspection and lexical/duplication evidence in [retained historical assessment](../../testbeds/datacrafting/content-understanding/evidence/selection/ASSESSMENT.md). |
| Runtime | Measured single-run times, versions and provider identifiers retained; no statistical latency claim. |
| Authentication and persistence | Parent live [acceptance](../../testbeds/datacrafting/deploy/records/20260916T070741387561Z-acceptance.json) verifies exact inputs, native read-back, denials and idempotency. |
| Tests | 32 PyMuPDF + 16 MarkItDown + 32 cloud/deployment + 17 comparison tests passed. |
| Resource ownership | Dedicated East US group, Functions, private/keyless storage, managed identity, two S0 cognitive accounts and scoped grants; [runbook](../../testbeds/datacrafting/deploy/README.md). |
| Reproducibility and cleanup | Each skill links original docs and exact uv commands. Deployment runbook owns guarded replay/teardown; no deletion executed. |

## Decision And Limits

Select CU GA `2025-11-01/prebuilt-layout` for a Foundry-native prose/table pipeline;
DI `2024-11-30/prebuilt-layout` passes the same fact/row checks. No global accuracy
winner is established. MarkItDown is the local Microsoft option; PyMuPDF raw text
and geometry remain useful independent evidence. PyMuPDF4LLM Markdown alone shows
substantial cell repetition and triggers fallback on both reports.

The CU method deliberately uses non-generative native layout, not
`prebuilt-documentSearch` or custom-field extraction. It requires no language or
embedding model deployment. Thus the initial possibility of semantic extraction
was not tested. No diagram topology, scanned-PDF accuracy, arbitrary-corpus quality,
load/scaling benchmark, other-user live sign-in or measured dollar cost is claimed.

A dedicated, secret-free Entra API registration/service principal was created for
caller authentication; no shared registration was edited. Private networking and
capped logs support the owned Function. Exact identities, grants, cost-bearing
resources and cleanup are recorded by the deployment owner, not duplicated here.
Resources remain allocated for inspection; ongoing monetary cost is unknown.

## Skill Promotion And Retirement

The user subsequently selected CU, authorized removal of the competing methods,
and requested a native skill plus a documented uv manifest convention.

- [azure-content-understanding](../../.github/skills/azure-content-understanding/SKILL.md)
   is registered in the native catalogue, with portable SDK recipe, contract,
   gotchas, original references, license and isolated `libraries/pyproject.toml`/lock.
- The [skill catalogue guide](../../.github/skills/README.md#uv-dependency-management)
   now requires the per-skill uv manifest and lock for Python recipes; the existing
   repository library workspace remains a separate owner and was not rewritten.
- PyMuPDF, MarkItDown, DI Read/Layout and the old comparison runner were removed.
   [Frozen cleanup/recovery evidence](../../testbeds/datacrafting/content-understanding/evidence/selection/cleanup.json)
   retains measured scope, external byte-verified archive, source hashes and selection evidence.
- The reference Function was narrowed and published CU-only; its 52 offline checks,
   live auth/readback and retired-route refusal pass. No resource/role deletion occurred.
- The portable async SDK recipe passes 14 offline tests and two fresh live PDF runs,
   retaining 13 pages, eight native tables, 32 narrative facts and six row associations.
   One earlier response-capture failure has unknown remote status/cost and remains recorded.
- Skill copy-out passes with only bundled uv dependencies. Customer PDFs, endpoints,
   identities and operation payloads remain in the testbed, not the skill distribution.

Retired DI infrastructure remains allocated; deletion/revocation was not part of
filesystem retirement. Current hosted evidence and resource lifecycle belong to
the [deployment runbook](../../testbeds/datacrafting/deploy/README.md).