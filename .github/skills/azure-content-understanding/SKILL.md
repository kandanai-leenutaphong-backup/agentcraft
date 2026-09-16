---
name: azure-content-understanding
description: "Use when extracting PDF text, OCR, Markdown, tables, figures and source locations with native Azure Content Understanding in Foundry Tools; use the official async Python SDK, Entra identity, explicit data-processing authorization and a locked uv environment. Includes a portable binary-layout recipe, native evidence, timeout recovery and offline tests; no resource provisioning or access grant is implied."
---

# Azure Content Understanding

Read the [canonical native SDK recipe](../../../libraries/content-understanding/GUIDE.md)
and [setup, failure recovery and read-back](../../../libraries/content-understanding/README.md).
The library owner retains implementation, tests, dependency lock, evidence and notices.
Use its explicit Python 3.12/uv environment; no skill-local runtime is installed.

Analysis requires separate endpoint, identity, input-hash, processing-boundary and budget
authority. No resource creation, model deployment, credential grant or live processing
is implied by loading this entry. Preserve pending results after timeout.