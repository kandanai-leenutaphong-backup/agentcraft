---
name: azure-llm-connectors
description: "Use when integrating Azure AI Foundry or Azure OpenAI chat, embeddings, streaming or structured output with Entra identity; diagnosing expired tokens, wrong deployment endpoints, truncated streams or misaligned embedding batches; or serving bounded model calls over MCP. Includes a Python library, contracts, worked examples, gotchas and offline tests."
compatibility: "Python 3.11+. uv for locked MCP startup. Live calls require an authorized Azure endpoint, deployment and Entra identity; tests do not."
---

# Azure LLM Connectors

Use the `azllm` Python API for application integration or the installed MCP tools for bounded
agent calls. The entire directory is the skill; this file is its discovery entry point.

## Decide

| Need | Surface |
| --- | --- |
| Inspect configuration and grants | `azllm_status`, no network |
| Ask the configured deployment | `azllm_ask`, operator grant required |
| Embed a bounded batch | `azllm_embed`, embedding deployment and grant required |
| Streaming, parsing, raw Responses options | Python API in [CONTRACT.md](CONTRACT.md) |
| Diagnose a failure | Symptom-first [GOTCHAS.md](GOTCHAS.md) |

## Install And Verify

The plugin client owns server startup. Read the `config_file` from `azllm_status`; do not guess
a workspace-relative path. Installation does not grant inference, provision resources, or load secrets.

For a copied standalone skill, run from this directory:

```bash
uv sync --locked --no-default-groups --no-install-project --extra mcp --extra dev
.venv/bin/python tests/selftest.py
.venv/bin/python examples/offline.py
.venv/bin/python -m pytest tests -q
.venv/bin/python scripts/mcp_server.py --selftest
```

The selftest uses injected clients without pytest. The MCP check round-trips an SDK client and
server, including denied calls, malformed inputs, fixture answers and budget exhaustion.

## Use

1. Call `azllm_status` before asking for model work.
2. Require the operator's endpoint, deployment, Entra access and `allow_model_calls` grant.
3. Keep prompts within the configured character limit and output within the token cap.
4. Inspect status and usage; a partial provider result is not a completed answer.
5. Do not restart the server to evade the operator's exhausted budget.

Tool input cannot set endpoints, deployments, credentials, grants, raw SDK options or `store=True`.
Do not call the live probe scripts as installation tests. They invoke models and can incur charges.

Resolve examples and documentation relative to this loaded skill directory. The
[offline example](examples/offline.py) demonstrates the same `connect(config, client=...)`
boundary used in production. [README.md](README.md) covers streaming, embeddings, structured
output, lifecycle and direct Python integration.

## Remove

Disable this MCP server in the client or uninstall the containing `harness-data` plugin. Direct
Python users close connectors and remove the dependency. Neither action revokes Azure roles.