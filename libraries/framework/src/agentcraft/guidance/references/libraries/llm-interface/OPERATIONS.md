# Operational Migration Notes

For **`llm-interface` 0.1.0a1**. Start application code with [USAGE.md](USAGE.md);
the [implemented contract](CONTRACT.md) defines supported options and guarantees.
This guide migrates failure knowledge from `azllm`, not its public Python or MCP API.

## Provenance

Source: the original LLM skill's GOTCHAS.md (missing-not-advertised; source reference: `../../.github/skills/azure-llm-connectors/GOTCHAS.md`),
entries G1-G18, at Git revision `5a216df1189708999f6e47bd524092ad2b56a5b1`.
That source names OpenAI 3.6.0 and Azure Identity 1.25.3 as its historical baseline.
The interpretations below were checked against this library's contract/source on
2026-09-15; they do not extend the old baseline to current SDKs or live deployments.

The original documentation remains with the installable legacy package until its
supported callers migrate. The retirement assessment (outside-guidance-not-advertised; source reference: `../CONNECTOR_RETIREMENT.md`)
separates useful knowledge from missing runtime compatibility.

## Findings And Applicability

| Source | Retained Finding | Application To `llm_interface` |
| --- | --- | --- |
| G1 | Azure inference uses the deployment name, not merely the model family. | Supply the operator's actual deployment as `model`. A syntactically valid name is not evidence that the deployment exists. |
| G2 | A token string captured at startup eventually expires. | Supply a credential or supported token callable. Native Azure Identity token providers handle refresh; do not obtain a bearer token once and retain it as a permanent key. |
| G3 | Sync and async token providers have different invocation contracts. | Built-in profiles select the matching native provider. Both credential types are supported; do not copy the old rule requiring every async caller to supply only an async credential. |
| G4 | Endpoint shape and request-path construction can cause persistent 404s. | Pass a supported account origin or Foundry project endpoint. The native provider owns `/openai/v1/` construction; do not concatenate request URLs or assume arbitrary legacy endpoint forms are accepted. |
| G5 | Local-key authentication may be disabled; ambient keys can select the wrong authority. | Azure profiles require explicit identity/token-callable input. Separate explicit OpenAI profiles have a different credential contract. No automatic key or identity fallback is implied. |
| G6 | Management-plane authority does not establish inference permission. | Verify the selected identity, endpoint, token audience and required data-plane role for the actual Foundry/OpenAI profile. No role grant or forced re-login is an installation step. |
| G7 | HTTP 200 and partial text do not prove stream completion. | Explicit failure events refuse; quiet EOF without terminal evidence raises `missing_terminal_event`. Consume the final result and close streams with `async with` or `aclose()`. |
| G8 | Provider error text and exception chains can expose prompts. | Use safe `LlmError.metadata()`. The library does not forward or chain provider messages. Full framework responses, tool events and vectors are payload-bearing, not safe automatic log projections. |
| G9 | Provider-side response chaining depends on retained provider state. | **Incompatible recipe:** `store=True` and `previous_response_id` are not escape hatches here. Use owner-bound in-memory agent sessions under `store=False`; durable history is host-owned and not implemented by this alpha. |
| G10 | Rebuilding clients per request discards connection pools and adds auth work. | Reuse a connection at the composition root **within one event loop**. The old synchronous connector's thread-sharing description is not a guarantee of this async API. |
| G11 | Async clients and credentials require explicit cleanup. | Close connections with async context management; borrowed credentials/transports are closed by their host. Injected-provider resources are borrowed unless explicitly declared owned. |
| G12 | Long timeouts and nested retries can exhaust worker capacity. | `Limits.timeout_seconds` bounds the whole operation/run, including slot waits and backpressure. Built-ins have no automatic retry; do not transfer the legacy default of two retries. |
| G13 | An embedding deployment is reached through the account that owns it. | Different accounts require separate connections. Never guess another endpoint from a model family or fall back to an unconfigured account. |
| G14 | A chat deployment is not an implicit embedding deployment. | Supply `embedding_model` explicitly. Without it, embedding calls refuse; no global embedding deployment name is substituted. |
| G15 | Native embedding array order is not input order. | Validate complete unique integer indices, count, finite nonempty vectors and dimensions before framework normalization; malformed batches return no usable vectors. |
| G16 | Byte/character limits do not establish provider token limits. | Local serialized-byte and batch bounds are not token counts or billing quotas. Check the selected deployment's current limits; historical model-specific token ceilings are not universal defaults. |
| G17 | A copied operator endpoint is not a portable default. | Configure the endpoint/deployment at the composition root. The configured host is pinned; request input cannot change the destination, credentials or grants. |
| G18 | Tool discovery and installation do not authorize model spend. | `Policy.allow_model_calls` defaults to false. **Gap:** this library has no MCP server or equivalent process-wide `azllm` MCP budget. Run-local limits do not replace that adapter's grant, schema and budget checks. |

## Regression And Migration Gates

Current regression owners:

- Configuration tests (source-or-asset-not-bundled; source reference: `tests/test_config.py`): target/profile validation, explicit
  grants and policy snapshots.
- Connection tests (source-or-asset-not-bundled; source reference: `tests/test_connection.py`): no-call refusal, native Foundry
  paths, credential injection and embedding-index validation.
- Safety tests (source-or-asset-not-bundled; source reference: `tests/test_safety.py`): incomplete streams, safe provider errors,
  deadlines, cancellation, request bounds and structured responses.
- Provider tests (source-or-asset-not-bundled; source reference: `tests/test_providers.py`): borrowed dependencies and exactly-once
  closure of explicitly owned resources.
- Agent tests (source-or-asset-not-bundled; source reference: `tests/test_agents.py`) and tool tests (source-or-asset-not-bundled; source reference: `tests/test_tools.py`): shared
  run budgets, owner/binding checks, tool grants and invalid-call refusal.

The registered legacy MCP consumer still requires `azllm_status`, `azllm_ask` and
`azllm_embed`, its explicit non-secret configuration file, per-process attempt
reservations, fixed targets, output caps, fixture markers and SDK client/server
round-trip tests. Preserve these as a thin adapter over the public library before
removing the skill's launch path. Do not add raw provider options or relax
`store=False` to imitate the entire old Python facade.

The synchronous/raw Python contract needs an explicit compatibility or retirement
decision. No library runtime imports the legacy package;
historical comparison tests (missing-not-advertised; source reference: `tests/test_existing_contracts.py`) are optional evidence,
not a supported legacy shim. [VALIDATION.md](VALIDATION.md) owns artifact/live limits.
No model request, cloud grant or external publication was performed for this migration.