---
name: managed-identity-model-clients
description: >
  Use when calling Azure OpenAI or Azure AI Foundry models from Python with
  Entra identity instead of API keys, and the call has to survive production.
  Use for token refresh in a long-lived process (401 after an hour), reusing
  one client instead of building one per request, synchronous and asyncio
  access, raw Responses API pass-through, structured output with pydantic,
  streaming that detects in-band error and response.failed events, embeddings
  whose vectors must stay aligned to their inputs, an embedding deployment on a
  different account, bounded timeouts and retries, credential ownership and
  clean shutdown, and errors that must not carry prompts or completions into
  logs. Do not use for creating accounts or deployments, granting roles, agent
  hosting, or evaluation.
---

# Managed-Identity Model Clients

Use installed `llm-interface`; import `llm_interface`, not `modelaccess`. Read the
[canonical guide](../../../libraries/llm-interface/docs/skills/managed-identity-model-clients.md)
for identity refresh, async calls, structured output, streaming, embedding integrity,
errors, limits and cleanup. Synchronous/raw Responses and MCP compatibility are
retired. No local runtime, implicit inference grant or credential discovery remains.
