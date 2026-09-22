# Foundry Hosted Agents Experiment

**Offline checks pass; live hosting blocked by dependencies and registry pull permission.**
No agent deployed, image built, inference performed or access changed.

[Specification and measured results](../../specs/20260922_FOUNDRY_HOSTED_AGENTS_EXPERIMENT.md)
and [deployment sequence](deploy/README.md) own acceptance and operations.

`configuration.yaml` uses the canonical `agentconfig` roster/prompt/`module:function`
contract. `proof_tools.nonce_digest` is deterministic and side-effect-free. `main.py`
composes `llm_interface`'s Microsoft Agent Framework loop with the official Foundry
Responses protocol handler; no second model runner and no optimizer.

Run from repository root, using existing system Python:

```bash
bash testbeds/foundry-hosted-agents/deploy/deploy.sh test
bash testbeds/foundry-hosted-agents/deploy/deploy.sh preflight
```

First command writes a measured offline receipt. Second reads existing Azure metadata
and exits 2 with named gaps. Neither installs packages nor writes Azure resources.
Hosting transport/model loop remain unexecuted until dependencies satisfy owner manifests.