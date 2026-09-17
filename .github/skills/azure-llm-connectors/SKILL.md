---
name: azure-llm-connectors
description: Use when integrating Azure AI Foundry or Azure OpenAI chat,
  embeddings, streaming or structured output with Entra identity; diagnosing
  expired tokens, wrong deployment endpoints, truncated streams or misaligned
  embedding batches; or migrating bounded model calls over MCP to an explicitly
  authorized host. Canonical llm_interface owns the async library, contracts,
  examples and offline safety tests; no skill-local runtime or MCP server.
compatibility: Python 3.11+. Install llm-interface with the needed provider
  extra. Live calls require explicit endpoint, deployment, identity and
  inference authority; offline tests require none of those grants.
---

# Azure LLM Connectors

Use installed `llm-interface`; import `llm_interface`. Read the
[canonical guide](../../../libraries/llm-interface/docs/skills/azure-llm-connectors.md)
for async chat, embeddings, streams, structured results, host identity, errors,
limits and cleanup. `azllm` and its MCP runtime are retired; loading this entry
grants no inference, tool execution, cloud mutation or credential access.

This entry also owns managed-identity model-client guidance. The former
`managed-identity-model-clients` catalogue name resolves here. Retained
[identity and failure notes](../../../libraries/llm-interface/docs/skills/managed-identity-model-clients.md)
cover token refresh, client lifetime and embedding integrity; synchronous/raw Responses
support remains retired.
