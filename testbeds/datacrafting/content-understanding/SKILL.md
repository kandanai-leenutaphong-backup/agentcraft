---
name: content-understanding
description: 'Inspect preserved Content Understanding extraction evidence; use the canonical azure-content-understanding skill for new native SDK runs. The former Function-testbed wrapper is retired.'
---

# Content Understanding Evidence

Canonical reusable guidance: [azure-content-understanding](../../../.github/skills/azure-content-understanding/SKILL.md).
Its bundled uv manifest/lock, native SDK recipe and tests are the only supported
execution path. This folder retains results; its Function client, project environment
and deployment wrapper were removed. No new forwarding script replaces them.

## Preserved Results

- [Yallourn native SDK receipt](./results/native-sdk/yallourn/20260916-async-policy/receipt.json): seven pages, five native tables.
- [Murray native SDK receipt](./results/native-sdk/murray/20260916-async-policy/receipt.json): six pages, three native tables.
- [Original Yallourn Function receipt](./results/yallourn/20260916T065358185028Z/receipt.json).
- [Original Murray Function receipt](./results/murray/20260916T065409548693Z/receipt.json).
- [Initial SDK failure and unknown remote outcome](./results/native-sdk/yallourn/20260916-skill-promotion/OUTCOME.md).

Native API: GA `2025-11-01`, `prebuilt-layout`. All retained outputs distinguish
SDK execution from historical Function execution. No result, source hash or
operation record was rewritten during wrapper removal. Native Markdown/tables
do not establish circuit-diagram topology or a trustworthy evaluation answer key.

[Selection evidence](./evidence/selection/ASSESSMENT.md) retains the historical
comparison and source renders. Other extraction methods are retired; their raw
outputs are available only through the [external verified recovery archive](./evidence/selection/cleanup.json).

The [wrapper retirement record](../deploy/records/20260916-function-wrapper-retirement.json)
identifies its separate archive. [Cloud ownership records](../deploy/README.md)
remain local; no Azure teardown occurred. New analysis requires the canonical
skill's explicit input/target authorization and a fresh output directory.

Original documentation:
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/concepts/prebuilt-analyzers
- https://learn.microsoft.com/en-us/rest/api/contentunderstanding/content-analyzers/analyze-binary?view=rest-contentunderstanding-2025-11-01
- https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/language-region-support