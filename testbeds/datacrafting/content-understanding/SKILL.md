---
name: content-understanding
description: 'Run native Content Understanding prebuilt-layout on the two authorized PDFs through an Entra-authenticated Azure Function; retain complete provider JSON, Markdown, observed pages and measured timing without generative model deployments.'
---

# Content Understanding Native Layout

Canonical reusable guidance: [azure-content-understanding](../../../.github/skills/azure-content-understanding/SKILL.md).
That skill owns portable native SDK recipes and its bundled uv manifest/lock, not
this experiment's Function implementation or private targets. This document remains
the testbed reference-host recipe. No runtime import or dependency points into the skill.

Callable adapter: [pipeline.py](./pipeline.py). Isolated dependencies: [pyproject.toml](./pyproject.toml).
Deployment and access: [runbook](../deploy/README.md). Output schema: [result contract](../RESULT_CONTRACT.md).
Requires uv, Azure CLI OAuth in the frozen tenant/subscription, and the deployment runbook completed.
The adapter calls only the deployed function; the function uses workload managed identity for CU.

From the repository root:

```bash
uv run --frozen --project testbeds/datacrafting/content-understanding python testbeds/datacrafting/content-understanding/pipeline.py --input testbeds/datacrafting/source_data/trip-of-murray-5b2-330kv-busbar.pdf --output testbeds/datacrafting/content-understanding/results/murray/NEW_UTC
uv run --frozen --project testbeds/datacrafting/content-understanding python testbeds/datacrafting/content-understanding/pipeline.py --input testbeds/datacrafting/source_data/trip-of-yallourn-w-power-station-unit-3-and-unit-4.pdf --output testbeds/datacrafting/content-understanding/results/yallourn/NEW_UTC
```

Use a new UTC-named output directory. Receipt outputs are relative: content.txt, content.md, native.json.
Text and Markdown preserve provider Markdown, not a reconstructed narrative. Complete native JSON is retained.
invocation.json and function.json preserve non-secret job identity, usage where provided, and timings.
Failures exit nonzero; no silent direct-SDK fallback. Read an unconfirmed job before submitting another.

Native API: GA `2025-11-01`, `prebuilt-layout`, `:analyzeBinary`. Official documentation states this analyzer
needs no language or embedding model. `prebuilt-documentSearch` is not used: generated summaries, figure
descriptions, chart reconstruction, generative fields and embeddings are excluded. No model capacity is
deployed. Live support must be established by successful receipts, not by documentation alone.
Service cost is unknown. Resource lifecycle and exact teardown belong to the experiment deployment runbook.

[Selection evidence](./evidence/selection/ASSESSMENT.md) retains the historical
comparison and source renders. Other extraction methods are retired; their raw
outputs are available only through the [external verified recovery archive](./evidence/selection/cleanup.json).
Use `bash testbeds/datacrafting/deploy/deploy.sh verify-results` for the two frozen
CU receipts and source-fact checks without new analysis. `verify` additionally reads
existing live jobs and checks auth, retired routes and completed-job idempotency.

Original documentation:
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/concepts/prebuilt-analyzers
- https://learn.microsoft.com/en-us/rest/api/contentunderstanding/content-analyzers/analyze-binary?view=rest-contentunderstanding-2025-11-01
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/language-region-support