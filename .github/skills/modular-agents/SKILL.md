---
name: modular-agents
description: "Use when defining YAML agent rosters, composing prompts, validating and measuring typed tools, or building native Foundry hosted bundles. Canonical modular-agents library uses llm_interface for execution; no deployment, inference or grants implied."
---

# Modular Agents

Read the [canonical library guide](../../../libraries/modular-agents/README.md)
and [contract](../../../libraries/modular-agents/CONTRACT.md).
Install `modular-agents`; import `agentconfig`, `toolshape` and `hostedagents`.
`llm_interface` is the sole model/tool-loop owner. `foundryagent` and the raw
OpenAI/administration engines are retired.

Host owns tool-import allowlists, configuration, credentials, caller identity,
execution policy, artifacts and deployment. Empty grants deny model/tool calls.
Run `python tests/selftest.py` from the library after installing declared native
dependencies. Bundles contain host code, not copied library runtimes.

No inference, cloud mutation, grant, teardown or publication follows from installation.
Historical deployment state remains protected. Source-workspace discovery is provided;
portable plugin/catalogue generation remains parent-owned.