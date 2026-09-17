# AgentCraft Framework Mockup

Current scope: a callable [Pipeline](tooling/pipeline/README.md), composing ordinary Python
functions in list order. Pipeline uses the standard library only.

[Azure Foundry call](tooling/functions/llm/azure-foundry/call.py) is one synchronous function:
`call(prompt, *, endpoint, deployment, credential) -> str`. Supply an async Azure
credential; the caller owns its lifetime. Run from synchronous code, not an active
event loop. It imports `respond` from [one framework module](framework/azure_foundry.py).

Install from this directory into a new external environment:

```bash
uv venv /tmp/agentcraft-minimal-foundry-env
uv pip install --python /tmp/agentcraft-minimal-foundry-env/bin/python ./framework
```

Package dependencies: `openai`, `azure-identity`, `httpx`. No `llm-interface`,
Agent Framework, repository-path imports, or other AgentCraft packages.
Select that environment in the editor for import resolution.

Existing deployment, using an already signed-in Azure CLI identity:

```bash
/tmp/agentcraft-minimal-foundry-env/bin/python tooling/functions/llm/azure-foundry/call.py "Reply with OK." \
	--endpoint https://han-primary-foundry-resource.openai.azure.com/openai/v1/ \
	--deployment gpt-5.6-luna \
	--tenant-id c79ab2bb-79cb-47f1-b4da-b6852fe45ff7
```

This sends one model request, capped at 128 output tokens. No credentials are stored.
The framework borrows credentials, disables SDK retries and redirects, requests
`store=False`, and rejects incomplete, refused, or empty responses. Timeout: 120 seconds.
Only Azure public-cloud account endpoints are supported, not Foundry project endpoints.
The caller selects an authorized endpoint and deployment; installation grants no access.

This is a Responses-only extraction of the SDK/authentication path in
[llm_interface.providers](../libraries/llm-interface/src/llm_interface/providers.py),
not a copy of its connection, policy, agent, streaming, or embedding machinery.
The original library and its consumers remain unchanged. This mockup does not provide
that library's shared budgets, byte limits, sanitized errors, or tool authorization.

From this directory, run checks:

```bash
/tmp/agentcraft-minimal-foundry-env/bin/python -I -B -m unittest discover -s framework/tests -v
cd tooling && python3 -B -m unittest pipeline.test_pipeline -v
```

Data adapters, configuration, persistence, triggers, and agent execution are not implemented.

Framework -> The fundamental building blocks used to construct Tooling 

Tooling -> The specific leveraging of building blocks to achieve a target outcome '

Development -> The composition of tooling to build an application
