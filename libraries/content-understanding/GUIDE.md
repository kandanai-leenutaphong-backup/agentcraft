---
name: azure-content-understanding
description: "Use when extracting PDF text, OCR, Markdown, tables, figures and source locations with native Azure Content Understanding in Foundry Tools; use the official async Python SDK, Entra identity, explicit data-processing authorization and a locked uv environment. Includes a portable binary-layout recipe, native evidence, timeout recovery and offline tests; no resource provisioning or access grant is implied."
---

# Azure Content Understanding

**Native first:** use `azure.ai.contentunderstanding.aio.ContentUnderstandingClient`.
This skill packages an executable recipe and verified failure knowledge, not another
service client, job engine or identity framework. [Setup and replay](./README.md),
[contract](./CONTRACT.md), [gotchas](./GOTCHAS.md), [verification](./VERIFICATION.md).

## Choose The Capability

The tested path is GA API `2025-11-01`, analyzer `prebuilt-layout`: PDF text, OCR,
Markdown, structured tables and page/word/cell locations. It requires no language
or embedding model deployment. Figure locations and labels do not prove diagram
topology, breaker state or generated visual descriptions.

Other native analyzers, custom fields, audio/video and generative document search
are different capabilities. Consult [original documentation](./references/README.md),
establish their model dependencies, regions, permissions and charges, then test them
separately. Do not silently substitute an analyzer or enable model capacity.

## Install With uv

Resolve `SKILL_ROOT` to this loaded skill directory; no consuming checkout is needed.
Use Python 3.12 and uv 0.9.30. Dependencies live in
[libraries/pyproject.toml](./libraries/pyproject.toml); exact versions in
[libraries/uv.lock](./libraries/uv.lock).

```bash
uv sync --locked --project "$SKILL_ROOT/libraries"
uv run --locked --project "$SKILL_ROOT/libraries" python -m unittest discover -s "$SKILL_ROOT/tests" -v
uv run --locked --project "$SKILL_ROOT/libraries" python "$SKILL_ROOT/scripts/extract.py" --help
```

Installation/tests perform no Azure call. Never copy credentials into this directory.

## Authorize And Extract

1. Name the approved resource endpoint, tenant/workload identity, source PDF hash,
   processing boundary, byte/time bounds and output location. Paid analysis must be
   explicitly authorized; a CLI login or a loaded skill is not a grant.
2. Use an existing Content Understanding resource with data-plane access. Local
   operators use `AzureCliCredential` with an explicit tenant. Azure workloads use
   `ManagedIdentityCredential`. Do not fetch service keys or embed tokens.
3. Run [scripts/extract.py](./scripts/extract.py) with `--input-sha256`, explicit
   `--processing-location geography|dataZone|global` and `--allow-analysis` only
   after authorization. See the complete command in the README.
4. Read `receipt.json`, verify the input hash and page count, inspect `native.json`
   and `content.md`. The SDK result is also retained as `sdk-result.json`. Presence
   of a successful result is not an accuracy score or evaluation answer key.
5. A failure retains its receipt and available native/operation evidence. Read the
   recorded operation before another submission. Timeout does not cancel remote
   processing or imply zero charges. Never overwrite a previous output directory.

## Hosting And Ownership

An Azure Function may call the native SDK or this recipe with an injected workload
credential. The host owns incoming authentication, tenant/record authorization,
durable jobs, storage, input allowlists and lifecycle; workload identity does not
authenticate callers. Preserve native Entra auth and test anonymous/foreign access
refusal plus persisted read-back. Resource changes stay in the host's documented
`deploy/deploy.sh`, with explicit target-bound authority and exact cleanup ownership.

## Gates

- Offline: real SDK binary POST/poll/serialization with synthetic HTTP transport;
  hash/target/permission/overwrite refusal, empty output, failed provider response,
  bounded timeout and async response-body capture.
- Copy-out: run those checks from a clean copied skill with only declared dependencies.
- Live: verify authorized native extraction and returned source coordinates/structure.
  Do not convert provider confidence into a cross-model quality score.
- Distribution: retain [LICENSE](./LICENSE), manifests, tests and documentation;
  exclude environments, source documents, cloud targets and private operation records.

There is no MCP server, automatic deployment, directory app registration or access
grant. Removing the skill does not delete cloud resources or pending results.