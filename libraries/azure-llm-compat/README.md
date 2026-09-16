# Legacy Azure LLM Compatibility

`azure-llm-compat==0.1.0a1`, public import `azure_llm_compat`.
This preserves the existing raw Responses/streaming/embedding API, not the bounded
`llm_interface` contract. It is migration compatibility, not a new preferred model client.
No raw-option escape hatch is added to `llm_interface`.

This is a separate uv project, explicitly excluded from the shared workspace: its
verified OpenAI 2.x range conflicts with `llm-interface[foundry]`'s OpenAI 3.13 range.
Each application keeps its own lock; do not install both incompatible surfaces together.

Public names: `AzureLlmClient`, `LlmConfig`, `LlmConfigError`, `azure_credential`,
`bearer_token_provider`, `set_credential_factory`, `response_events`, `stream_tool_turn`
and exported constants.
Construction remains lazy; caller configuration and the existing credential injection
remain unchanged. Hosts own inference authority and model/tool budgets.

Consumers: Custom Optimizer's model composition and Investigation's agent adapter import
this package directly. No shared-template bridge or ARM dependency remains.
`stream_tool_turn` receives an event producer, tool executor, schemas, limits and optional
wire metadata. It preserves native response IDs, reasoning-summary frames, tool results
and the terminal iteration refusal. The host still authorizes every tool execution and
owns conversation isolation. This is not the bounded `llm_interface` agent contract.

`AzureLlmClient.close()` closes only owned SDK clients, once; it never closes a borrowed
credential or injected client. Closing an unused client makes no connection. Stream cleanup
closes the event iterator and drains already-started tools; it does not claim tool rollback.

Remove compatibility only when both hosts deliberately migrate raw Responses IDs/events
to `llm_interface` sessions. OpenAI dependency and session/wire differences are real contract
boundaries, not a transport-selection fallback. Live inference remains unverified in this
data-only migration; 30 offline compatibility checks pass.

Source and focused offline tests moved from the shared template at baseline
`00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`. Original behavior is retained, not certified
equivalent to the new model library. No live inference, new deployment or publication was run.
