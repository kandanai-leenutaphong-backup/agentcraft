# Legacy Azure LLM Compatibility

`azure-llm-compat==0.1.0a1`, public import `azure_llm_compat`.
This preserves the existing raw Responses/streaming/embedding API, not the bounded
`llm_interface` contract. It is migration compatibility, not a new preferred model client.
No raw-option escape hatch is added to `llm_interface`.

This is a separate uv project, explicitly excluded from the shared workspace: its
verified OpenAI 2.x range conflicts with `llm-interface[foundry]`'s OpenAI 3.13 range.
Each application keeps its own lock; do not install both incompatible surfaces together.

Public names: `AzureLlmClient`, `LlmConfig`, `LlmConfigError`, `azure_credential`,
`bearer_token_provider`, `set_credential_factory`, `response_events` and exported constants.
Construction remains lazy; caller configuration and the existing credential injection
remain unchanged. Hosts own inference authority and model/tool budgets.

Consumers: Custom Optimizer's model composition; Investigation's parent-owned agent service
through a temporary `template_foundations.azure_llm` re-export; existing ARM identity setup.
Removal owner: parent agent adapting `backend/agents/service.py` to `llm_interface`, then
the optimizer host. Remove compatibility only after raw response/event/session parity is proved.

Source and focused offline tests moved from the shared template at baseline
`00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`. Original behavior is retained, not certified
equivalent to the new model library. No live inference, new deployment or publication was run.
