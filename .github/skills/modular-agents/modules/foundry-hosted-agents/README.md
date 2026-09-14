# Foundry Hosted Agents

The fourth module connects the preserved YAML and tool contracts to a real
source-hosted agent format. It is an adaptation of the source `hcagent` deployment
and runtime protocol, not a copy of its application, canvas store or UI.

The owning [super-skill contract](../../CONTRACT.md) fixes public APIs, policy,
invocation format, deployment receipts, recovery and exclusions. The single
operator sequence is [deploy/README.md](../../deploy/README.md).

| File | Owns |
| --- | --- |
| `hostedagents/definition.py` | YAML composition and typed tool registry |
| `hostedagents/policy.py` | operator-supplied runtime grants and bounds |
| `hostedagents/packaging.py` | flat source zip, explicit package closure, runtime integrity manifest |
| `hostedagents/engine.py` | shared callable service, model/tool loop, cancellation and results |
| `hostedagents/model.py` | official OpenAI SDK adapter and injected identity credential |
| `hostedagents/application.py` | authenticated local and platform-hosted HTTP composition |
| `hostedagents/client.py` | Foundry hosted data-plane transport and session namespaces |
| `hostedagents/grants.py` | exact-scope ARM reader/inference grant lifecycle |
| `hostedagents/deployment.py` | operator policy, durable receipt and read-back verification |
| `hostedagents/runtime/` | packaged entry point and lock-exported dependencies |

Focused checks live in the super-skill's `tests/` directory and use the standard
library runner. No standalone application frontend or MCP registration belongs
to this module.