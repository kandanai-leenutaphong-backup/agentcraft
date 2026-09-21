# Official Sources And Reproduction

Observation date: **2026-09-21 UTC**. Publisher: Microsoft. Sources describe
public documentation, not actual account entitlement, live integration or
adoption. The [feature catalogue](FEATURES.md) owns interpretation and proposals.

## Evidence And Availability

- Fresh collection: 83 public official fetches, all HTTP 200, through existing
  `harness-web-resource==1.1.0` public-only, DNS/redirect-guarded, robots-aware,
  rate-limited transport. Three discovery sources plus 80 family/detail references.
- Reused collection: 30 prior records from
  `/tmp/agentcraft-foundry-advisory-20260921`; every original JSON SHA256 matched
  its original catalogue. These were not refetched. Twenty-four are successful
  reference pages, five are official search-discovery responses, one is HTTP 404.
- The historical `/azure/foundry/whats-new` 404 is retained as P01; the current
  `/azure/foundry/whats-new-foundry` route succeeded as F38. A 404/search result
  supports discovery history, not a feature claim.
- Current official TOC has 550 linked navigation entries. TOC/catalogue coverage
  does not prove every linked page or variant was audited. The coverage matrix
  in FEATURES names exclusions and unresolved details.
- Microsoft Learn's public HTML can contain generic sign-in notices even when
  the article body is returned. HTTP 200 is availability of fetched material,
  not proof that an authenticated workflow is usable. No login or bypass occurred.
- Extracts retain headings, links and limited text, not full HTML/SDK/repository
  mirrors. Some passages are truncated or selected by keyword. An absent term in
  an extract does not prove absence from the source. Original payload hashes and
  derivative hashes are distinct; only retained bytes can be rehashed offline.
- Dates are actual fetch times, including original times for prior evidence.
  Exact source commits/revisions are unknown (`null`); page update dates or future
  release claims are not independently tested. Recheck the exact feature/API before
  adopting it. Pricing pages are not customer-specific quotes.
- Third-party source text remains Microsoft's property; internal reference only.
  No customer data, credentials, held-out labels or private material acquired.
  All Foundry integrations in this project remain `not_verified`.

## Machine-Readable Inputs

- [Discovery targets](dataset/discovery-targets.json): current landing, overview, TOC.
- [Feature targets](dataset/feature-targets.json): first 60 references.
- [Detail targets](dataset/detail-targets.json): 20 targeted gap-closing references.
- [Prior refresh targets](dataset/prior-targets.json): 30 original URLs, including
  discovery and historical failure. Refresh never erases the historical result.
- [Source index](dataset/source-index.json): source IDs, titles, URLs, dates,
  availability, evidence paths and derivative SHA256.
- [Reference manifest](dataset/manifest.json): rights, scope and local owners.
- [Research utility](results/20260921-research/evidence/research.py): thin
  project-owned data procedure over the existing `webres.fetch` owner; no service
  client, installation, product runtime or duplicated HTTP transport.

## Repeatable Commands

Run from repository root. No environment creation/activation or install. Existing
runtime used here: `/tmp/agentcraft-release-final/combined/bin/python`, with
`webres` at that runtime's installed site-packages. System `python3` lacks `webres`;
its initial module-help attempt failed with `ModuleNotFoundError`. If the existing
runtime disappears, public acquisition is blocked pending an authorized runtime;
offline verification still uses system Python. Do not silently alter `PYTHONPATH`
or weaken transport/robots rules.

The following invocations were executed successfully. `acquire` and `prior` use
create-only output and refuse collisions. **For a refresh, substitute a new empty
output directory inside this project** and keep previous evidence. No overwrite,
pruning, relocation or deletion is part of the procedure.

```bash
python3 -B .github/skills/agentcraft-process/validate.py demonstration_project/agentcraft_projects/foundry-adoption/constitution/constitution.yaml
python3 -B demonstration_project/agentcraft_projects/foundry-adoption/results/20260921-research/evidence/research.py verify

/tmp/agentcraft-release-final/combined/bin/python -B demonstration_project/agentcraft_projects/foundry-adoption/results/20260921-research/evidence/research.py acquire --targets demonstration_project/agentcraft_projects/foundry-adoption/dataset/discovery-targets.json --out demonstration_project/agentcraft_projects/foundry-adoption/results/20260921-research/discovery
/tmp/agentcraft-release-final/combined/bin/python -B demonstration_project/agentcraft_projects/foundry-adoption/results/20260921-research/evidence/research.py acquire --targets demonstration_project/agentcraft_projects/foundry-adoption/dataset/feature-targets.json --out demonstration_project/agentcraft_projects/foundry-adoption/results/20260921-research/features
/tmp/agentcraft-release-final/combined/bin/python -B demonstration_project/agentcraft_projects/foundry-adoption/results/20260921-research/evidence/research.py acquire --targets demonstration_project/agentcraft_projects/foundry-adoption/dataset/detail-targets.json --out demonstration_project/agentcraft_projects/foundry-adoption/results/20260921-research/details

python3 -B demonstration_project/agentcraft_projects/foundry-adoption/results/20260921-research/evidence/research.py prior --source /tmp/agentcraft-foundry-advisory-20260921 --out demonstration_project/agentcraft_projects/foundry-adoption/results/20260921-research/prior-verified
```

Expected: validator `status: valid`; verifier `status: pass`; acquisition prints
per-source HTTP status/error and writes a hash catalogue. Acquisition retains
failures and continues; process exit alone is not all-sources-success evidence.
Inspect every status. Robots/403/private-address refusal must remain a refusal.
No acquisition command authorizes a model, cloud account or authenticated endpoint.

The `prior` action requires original bytes and matching hashes; it does not invent
missing history. Its first attempt failed after one output because of relative-path
normalization; that partial `prior/P01.json` remains retained and excluded from the
verified source index. Corrected import succeeded in `prior-verified`.

The `index` action was used once to mechanically derive the table below and the
machine source index from verified receipts. It refuses existing generated outputs;
it is not a destructive refresh command. Future source-index replacement requires
an explicitly scoped documentation update, not mutation of retained receipts.

## Local Evidence

Read-only mapping: [documentation router](../../../docs/README.md),
[capability catalogue](../../../libraries/capabilities.json),
[LL README](../../../libraries/llm-interface/README.md),
[MA README](../../../libraries/modular-agents/README.md),
[AO contract](../../../.github/skills/agent-optimization/CONTRACT.md), and
[DATA README](../../../libraries/azure-data-connectors/README.md).
These establish documented local surfaces; no fresh package or live service test
was run. The repository-root architecture overview is absent; docs/README is the
assigned routing authority. No outside-project files changed.

## Source Index

IDs are stable within this research revision. Each evidence link contains source
provenance and a limited extract. Availability is acquisition status, **not maturity**;
feature-specific GA/preview distinctions belong to FEATURES.

<!-- GENERATED SOURCE INDEX -->
| ID | Official title / URL | Observed UTC | Availability / retained evidence |
| --- | --- | --- | --- |
| <a id="f01"></a>F01 | [Microsoft Foundry capability reference - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/capability-reference) | 2026-09-21T11:29:04Z | fresh HTTP 200; [extract](results/20260921-research/features/capability-reference.json) |
| <a id="f02"></a>F02 | [Microsoft Foundry portal general availability overview - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/general-availability) | 2026-09-21T11:29:06Z | fresh HTTP 200; [extract](results/20260921-research/features/general-availability.json) |
| <a id="f03"></a>F03 | [Migrate from the Foundry (classic) portal - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/how-to/navigate-from-classic) | 2026-09-21T11:29:08Z | fresh HTTP 200; [extract](results/20260921-research/features/classic-migration.json) |
| <a id="f04"></a>F04 | [Get started with Microsoft Foundry SDKs and endpoints - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/sdk-overview) | 2026-09-21T11:29:10Z | fresh HTTP 200; [extract](results/20260921-research/features/sdk-overview.json) |
| <a id="f05"></a>F05 | [Microsoft Foundry Models overview - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/foundry-models-overview) | 2026-09-21T11:29:12Z | fresh HTTP 200; [extract](results/20260921-research/features/models-overview.json) |
| <a id="f06"></a>F06 | [Understanding deployment types in Microsoft Foundry Models - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/deployment-types) | 2026-09-21T11:29:14Z | fresh HTTP 200; [extract](results/20260921-research/features/deployment-types.json) |
| <a id="f07"></a>F07 | [Deployment overview for Microsoft Foundry Models - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/deployments-overview) | 2026-09-21T11:29:16Z | fresh HTTP 200; [extract](results/20260921-research/features/deployment-options.json) |
| <a id="f08"></a>F08 | [Model router for Microsoft Foundry concepts - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-router) | 2026-09-21T11:29:18Z | fresh HTTP 200; [extract](results/20260921-research/features/model-router.json) |
| <a id="f09"></a>F09 | [Use the Azure OpenAI Responses API - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/responses) | 2026-09-21T11:29:20Z | fresh HTTP 200; [extract](results/20260921-research/features/responses-api.json) |
| <a id="f10"></a>F10 | [How to use structured outputs with Azure OpenAI in Microsoft Foundry Models - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs) | 2026-09-21T11:29:22Z | fresh HTTP 200; [extract](results/20260921-research/features/structured-outputs.json) |
| <a id="f11"></a>F11 | [Prompt caching with Azure OpenAI in Microsoft Foundry Models - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/prompt-caching) | 2026-09-21T11:29:24Z | fresh HTTP 200; [extract](results/20260921-research/features/prompt-caching.json) |
| <a id="f12"></a>F12 | [What is Memory? - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-memory) | 2026-09-21T11:29:26Z | fresh HTTP 200; [extract](results/20260921-research/features/memory.json) |
| <a id="f13"></a>F13 | [What is Toolbox in Microsoft Foundry? - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/toolbox-overview) | 2026-09-21T11:29:28Z | fresh HTTP 200; [extract](results/20260921-research/features/toolbox.json) |
| <a id="f14"></a>F14 | [Connect agents to MCP server endpoints - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/model-context-protocol) | 2026-09-21T11:29:30Z | fresh HTTP 200; [extract](results/20260921-research/features/mcp.json) |
| <a id="f15"></a>F15 | [Add managed MCP servers powered by connector namespaces (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/connectors) | 2026-09-21T11:29:32Z | fresh HTTP 200; [extract](results/20260921-research/features/managed-connectors.json) |
| <a id="f16"></a>F16 | [Connect to an A2A agent endpoint from Foundry Agent Service - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/agent-to-agent) | 2026-09-21T11:29:34Z | fresh HTTP 200; [extract](results/20260921-research/features/a2a.json) |
| <a id="f17"></a>F17 | [Overview of web grounding capabilities in Foundry - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/web-overview) | 2026-09-21T11:29:36Z | fresh HTTP 200; [extract](results/20260921-research/features/web-tools.json) |
| <a id="f18"></a>F18 | [What is Foundry IQ? - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/what-is-foundry-iq) | 2026-09-21T11:29:38Z | fresh HTTP 200; [extract](results/20260921-research/features/foundry-iq.json) |
| <a id="f19"></a>F19 | [Connect agents to Microsoft Fabric with Fabric IQ (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/fabric-iq) | 2026-09-21T11:29:40Z | fresh HTTP 200; [extract](results/20260921-research/features/fabric-iq.json) |
| <a id="f20"></a>F20 | [File search tool for Microsoft Foundry agents - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/file-search) | 2026-09-21T11:29:42Z | fresh HTTP 200; [extract](results/20260921-research/features/file-search.json) |
| <a id="f21"></a>F21 | [Agentic Retrieval Overview - Azure AI Search &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/search/agentic-retrieval-overview) | 2026-09-21T11:29:44Z | fresh HTTP 200; [extract](results/20260921-research/features/search-retrieval.json) |
| <a id="f22"></a>F22 | [Built-in Evaluators Reference - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/built-in-evaluators) | 2026-09-21T11:29:46Z | fresh HTTP 200; [extract](results/20260921-research/features/evaluators.json) |
| <a id="f23"></a>F23 | [AI Red Teaming Agent - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/ai-red-teaming-agent) | 2026-09-21T11:29:48Z | fresh HTTP 200; [extract](results/20260921-research/features/red-teaming.json) |
| <a id="f24"></a>F24 | [Evaluation datasets in Microsoft Foundry - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-datasets) | 2026-09-21T11:29:50Z | fresh HTTP 200; [extract](results/20260921-research/features/evaluation-datasets.json) |
| <a id="f25"></a>F25 | [Human Evaluation for Microsoft Foundry Agents - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/human-evaluation) | 2026-09-21T11:29:52Z | fresh HTTP 200; [extract](results/20260921-research/features/human-evaluation.json) |
| <a id="f26"></a>F26 | [What is Microsoft Foundry Control Plane? - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/control-plane/overview) | 2026-09-21T11:29:54Z | fresh HTTP 200; [extract](results/20260921-research/features/control-plane.json) |
| <a id="f27"></a>F27 | [Agent tracing overview - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/concepts/trace-agent-concept) | 2026-09-21T11:29:56Z | fresh HTTP 200; [extract](results/20260921-research/features/tracing.json) |
| <a id="f28"></a>F28 | [Configure AI Gateway in your Foundry resources - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/configuration/enable-ai-api-management-gateway-portal) | 2026-09-21T11:29:58Z | fresh HTTP 200; [extract](results/20260921-research/features/ai-gateway.json) |
| <a id="f29"></a>F29 | [Authentication and authorization in Microsoft Foundry - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/authentication-authorization-foundry) | 2026-09-21T11:30:00Z | fresh HTTP 200; [extract](results/20260921-research/features/authentication.json) |
| <a id="f30"></a>F30 | [Guardrails and controls overview in Microsoft Foundry - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/guardrails/guardrails-overview) | 2026-09-21T11:30:02Z | fresh HTTP 200; [extract](results/20260921-research/features/guardrails.json) |
| <a id="f31"></a>F31 | [Data, privacy, and security for Foundry Agent Service - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/agents/data-privacy-security) | 2026-09-21T11:30:04Z | fresh HTTP 200; [extract](results/20260921-research/features/agent-privacy.json) |
| <a id="f32"></a>F32 | [Data, privacy, and security for Foundry Models sold by Azure in Microsoft Foundry - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/responsible-ai/openai/data-privacy) | 2026-09-21T11:30:06Z | fresh HTTP 200; [extract](results/20260921-research/features/model-privacy.json) |
| <a id="f33"></a>F33 | [Customer-Managed Key Encryption in Microsoft Foundry - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/customer-managed-keys) | 2026-09-21T11:30:08Z | fresh HTTP 200; [extract](results/20260921-research/features/customer-managed-keys.json) |
| <a id="f34"></a>F34 | [Networking options for Foundry Agent Service - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/networking-options) | 2026-09-21T11:30:10Z | fresh HTTP 200; [extract](results/20260921-research/features/private-network.json) |
| <a id="f35"></a>F35 | [Plan and Manage Costs - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/manage-costs) | 2026-09-21T11:30:12Z | fresh HTTP 200; [extract](results/20260921-research/features/cost-management.json) |
| <a id="f36"></a>F36 | [Feature availability across cloud regions - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/reference/region-support) | 2026-09-21T11:30:14Z | fresh HTTP 200; [extract](results/20260921-research/features/region-support.json) |
| <a id="f37"></a>F37 | [Foundry Models lifecycle and support policy - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-retirements) | 2026-09-21T11:30:16Z | fresh HTTP 200; [extract](results/20260921-research/features/model-retirements.json) |
| <a id="f38"></a>F38 | [Microsoft Foundry docs: What&#39;s new for August 2026 - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/whats-new-foundry) | 2026-09-21T11:30:18Z | fresh HTTP 200; [extract](results/20260921-research/features/whats-new.json) |
| <a id="f39"></a>F39 | [What is Azure Content Understanding in Foundry Tools? - Foundry Tools &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/content-understanding/overview) | 2026-09-21T11:30:20Z | fresh HTTP 200; [extract](results/20260921-research/features/content-understanding.json) |
| <a id="f40"></a>F40 | [What Is Azure Document Intelligence in Foundry Tools? - Foundry Tools &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/overview) | 2026-09-21T11:30:24Z | fresh HTTP 200; [extract](results/20260921-research/features/document-intelligence.json) |
| <a id="f41"></a>F41 | [What Is Azure Speech? - Foundry Tools &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/overview) | 2026-09-21T11:30:26Z | fresh HTTP 200; [extract](results/20260921-research/features/speech.json) |
| <a id="f42"></a>F42 | [What is Azure Translator in Foundry Tools? - Foundry Tools &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/translator/overview) | 2026-09-21T11:30:28Z | fresh HTTP 200; [extract](results/20260921-research/features/translator.json) |
| <a id="f43"></a>F43 | [What is Azure Vision in Foundry Tools? - Foundry Tools &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/computer-vision/overview) | 2026-09-21T11:30:30Z | fresh HTTP 200; [extract](results/20260921-research/features/vision.json) |
| <a id="f44"></a>F44 | [What is Azure AI Content Safety? - Azure AI services &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/content-safety/overview) | 2026-09-21T11:30:32Z | fresh HTTP 200; [extract](results/20260921-research/features/content-safety.json) |
| <a id="f45"></a>F45 | [What is an autopilot in Microsoft Foundry? - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/autopilot-overview) | 2026-09-21T11:30:34Z | fresh HTTP 200; [extract](results/20260921-research/features/autopilot.json) |
| <a id="f46"></a>F46 | [Add a human-in-the-loop approval step (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/add-human-in-the-loop) | 2026-09-21T11:30:36Z | fresh HTTP 200; [extract](results/20260921-research/features/human-approval.json) |
| <a id="f47"></a>F47 | [Publish agents to Microsoft 365 Copilot and Microsoft Teams - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/publish-copilot) | 2026-09-21T11:30:38Z | fresh HTTP 200; [extract](results/20260921-research/features/publishing.json) |
| <a id="f48"></a>F48 | [Manage hosted agent sessions - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/manage-hosted-sessions) | 2026-09-21T11:30:40Z | fresh HTTP 200; [extract](results/20260921-research/features/sessions.json) |
| <a id="f49"></a>F49 | [Microsoft Agent Framework Overview &#124; Microsoft Learn](https://learn.microsoft.com/en-us/agent-framework/overview/agent-framework-overview) | 2026-09-21T11:30:44Z | fresh HTTP 200; [extract](results/20260921-research/features/agent-framework.json) |
| <a id="f50"></a>F50 | [Connect agents to Microsoft 365 with Work IQ (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/work-iq) | 2026-09-21T11:30:46Z | fresh HTTP 200; [extract](results/20260921-research/features/work-iq.json) |
| <a id="f51"></a>F51 | [Use the computer use tool for agents - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/computer-use) | 2026-09-21T11:30:48Z | fresh HTTP 200; [extract](results/20260921-research/features/computer-use.json) |
| <a id="f52"></a>F52 | [Automate browser tasks with Foundry agents - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/browser-automation) | 2026-09-21T11:30:50Z | fresh HTTP 200; [extract](results/20260921-research/features/browser-automation.json) |
| <a id="f53"></a>F53 | [Use Code Interpreter with Microsoft Foundry agents - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/code-interpreter) | 2026-09-21T11:30:52Z | fresh HTTP 200; [extract](results/20260921-research/features/code-interpreter.json) |
| <a id="f54"></a>F54 | [Govern MCP Tools by Using an AI Gateway - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/governance) | 2026-09-21T11:30:54Z | fresh HTTP 200; [extract](results/20260921-research/features/tool-governance.json) |
| <a id="f55"></a>F55 | [Create a project - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/how-to/create-projects) | 2026-09-21T11:30:56Z | fresh HTTP 200; [extract](results/20260921-research/features/create-projects.json) |
| <a id="f56"></a>F56 | [Agent development with the Azure Developer CLI - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/cli-agent-development) | 2026-09-21T11:30:58Z | fresh HTTP 200; [extract](results/20260921-research/features/cli-lifecycle.json) |
| <a id="f57"></a>F57 | [Microsoft Foundry Toolkit for Visual Studio Code overview - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/how-to/develop/get-started-projects-visual-studio-code) | 2026-09-21T11:31:00Z | fresh HTTP 200; [extract](results/20260921-research/features/toolkit.json) |
| <a id="f58"></a>F58 | [How to use global batch processing with Azure OpenAI in Microsoft Foundry Models - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/batch) | 2026-09-21T11:31:02Z | fresh HTTP 200; [extract](results/20260921-research/features/batch.json) |
| <a id="f59"></a>F59 | [Azure OpenAI in Microsoft Foundry Models Quotas and Limits - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/quotas-limits) | 2026-09-21T11:31:04Z | fresh HTTP 200; [extract](results/20260921-research/features/model-quotas.json) |
| <a id="f60"></a>F60 | [Built-in policies for model deployment - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/how-to/model-deployment-policy) | 2026-09-21T11:31:06Z | fresh HTTP 200; [extract](results/20260921-research/features/security-policy.json) |
| <a id="f61"></a>F61 | [Use the GPT Realtime API for speech and audio with Azure OpenAI - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/realtime-audio) | 2026-09-21T11:33:03Z | fresh HTTP 200; [extract](results/20260921-research/details/realtime-audio.json) |
| <a id="f62"></a>F62 | [How to Use Image Generation Models from OpenAI - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/dall-e) | 2026-09-21T11:33:05Z | fresh HTTP 200; [extract](results/20260921-research/details/image-generation.json) |
| <a id="f63"></a>F63 | [Sora 2 video generation overview (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/video-generation) | 2026-09-21T11:33:07Z | fresh HTTP 200; [extract](results/20260921-research/details/video-generation.json) |
| <a id="f64"></a>F64 | [Quickstart - Get started with Azure OpenAI audio generation - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/audio-completions-quickstart) | 2026-09-21T11:33:09Z | fresh HTTP 200; [extract](results/20260921-research/details/audio-completions.json) |
| <a id="f65"></a>F65 | [Build a workflow in Microsoft Foundry (Preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/workflow) | 2026-09-21T11:33:11Z | fresh HTTP 200; [extract](results/20260921-research/details/workflow.json) |
| <a id="f66"></a>F66 | [Durable state store for Microsoft Foundry hosted agents (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-state-store) | 2026-09-21T11:33:13Z | fresh HTTP 200; [extract](results/20260921-research/details/state-store.json) |
| <a id="f67"></a>F67 | [Connect OpenAPI tools to Microsoft Foundry agents - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/openapi) | 2026-09-21T11:33:15Z | fresh HTTP 200; [extract](results/20260921-research/details/openapi-tool.json) |
| <a id="f68"></a>F68 | [Generate a synthetic evaluation dataset (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-dataset-synthetic) | 2026-09-21T11:33:17Z | fresh HTTP 200; [extract](results/20260921-research/details/synthetic-data.json) |
| <a id="f69"></a>F69 | [Simulate conversations with the Microsoft Foundry SDK - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-simulate-conversations) | 2026-09-21T11:33:19Z | fresh HTTP 200; [extract](results/20260921-research/details/conversation-simulation.json) |
| <a id="f70"></a>F70 | [Azure Language in Foundry Tools - tools and agents - Foundry Tools &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/ai-services/language-service/concepts/foundry-tools-agents) | 2026-09-21T11:33:21Z | fresh HTTP 200; [extract](results/20260921-research/details/language-tools.json) |
| <a id="f71"></a>F71 | [Direct preference optimization - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/fine-tuning-direct-preference-optimization) | 2026-09-21T11:33:23Z | fresh HTTP 200; [extract](results/20260921-research/details/fine-tuning-preferences.json) |
| <a id="f72"></a>F72 | [Reinforcement fine-tuning - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/reinforcement-fine-tuning) | 2026-09-21T11:33:25Z | fresh HTTP 200; [extract](results/20260921-research/details/reinforcement-fine-tuning.json) |
| <a id="f73"></a>F73 | [Enable tool search in a toolbox - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/tool-search) | 2026-09-21T11:33:27Z | fresh HTTP 200; [extract](results/20260921-research/details/tool-search.json) |
| <a id="f74"></a>F74 | [Use skills with Microsoft Foundry agents (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/skills) | 2026-09-21T11:33:29Z | fresh HTTP 200; [extract](results/20260921-research/details/skills.json) |
| <a id="f75"></a>F75 | [Reminder tool for self-scheduling hosted agents - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/reminder-tool) | 2026-09-21T11:33:31Z | fresh HTTP 200; [extract](results/20260921-research/details/reminders.json) |
| <a id="f76"></a>F76 | [Configure a custom code interpreter for agents - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/tools/custom-code-interpreter) | 2026-09-21T11:33:33Z | fresh HTTP 200; [extract](results/20260921-research/details/custom-interpreter.json) |
| <a id="f77"></a>F77 | [Endpoints for Microsoft Foundry Models - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/endpoints) | 2026-09-21T11:33:35Z | fresh HTTP 200; [extract](results/20260921-research/details/model-endpoints.json) |
| <a id="f78"></a>F78 | [Region availability for Foundry Models sold by Azure - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-sold-directly-by-azure-region-availability) | 2026-09-21T11:33:37Z | fresh HTTP 200; [extract](results/20260921-research/details/model-regions.json) |
| <a id="f79"></a>F79 | [Foundry Models from partners and community - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-from-partners) | 2026-09-21T11:33:39Z | fresh HTTP 200; [extract](results/20260921-research/details/model-catalogue-partners.json) |
| <a id="f80"></a>F80 | [Microsoft Foundry product and capability map - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/capabilities) | 2026-09-21T11:33:41Z | fresh HTTP 200; [extract](results/20260921-research/details/capability-map.json) |
| <a id="p01"></a>P01 | [404 - Content not found](https://learn.microsoft.com/en-us/azure/foundry/whats-new) | 2026-09-21T10:55:20+00:00 | prior HTTP 404; hash-verified, not refetched; NOT feature evidence; [extract](results/20260921-research/prior-verified/P01.json) |
| <a id="p02"></a>P02 | [Agent Evaluators for Generative AI - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators) | 2026-09-21T10:51:58+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P02.json) |
| <a id="p03"></a>P03 | [Agent Lightning - Microsoft Research](https://www.microsoft.com/en-us/research/project/agent-lightning/) | 2026-09-21T10:55:44+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P03.json) |
| <a id="p04"></a>P04 | [Quotas and limits for Microsoft Foundry Agent Service - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/limits-quotas-regions) | 2026-09-21T10:53:03+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P04.json) |
| <a id="p05"></a>P05 | [Set up private networking for Foundry Agent Service - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/virtual-networks) | 2026-09-21T10:53:04+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P05.json) |
| <a id="p06"></a>P06 | [Agent optimizer in Foundry Agent Service overview (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-overview) | 2026-09-21T10:50:40+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P06.json) |
| <a id="p07"></a>P07 | [Foundry Agent Service - Pricing &#124; Microsoft Azure](https://azure.microsoft.com/pricing/details/foundry-agent-service/) | 2026-09-21T10:53:05+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P07.json) |
| <a id="p08"></a>P08 | [Monitor agents with the Agent Monitoring Dashboard - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/how-to-monitor-agents-dashboard) | 2026-09-21T10:53:02+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P08.json) |
| <a id="p09"></a>P09 | [Custom Evaluators - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/custom-evaluators) | 2026-09-21T10:53:02+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P09.json) |
| <a id="p10"></a>P10 | [Evaluate conversation datasets with the Microsoft Foundry SDK - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-conversations) | 2026-09-21T10:53:03+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P10.json) |
| <a id="p11"></a>P11 | [Rate limits, region support, and enterprise features for evaluation - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-regions-limits-virtual-network) | 2026-09-21T10:53:02+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P11.json) |
| <a id="p12"></a>P12 | [Use admin-connected models in cloud evaluations - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluate-admin-connected-models) | 2026-09-21T10:56:39+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P12.json) |
| <a id="p13"></a>P13 | [Evaluate models and agents with the Microsoft Foundry SDK - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-targets) | 2026-09-21T10:56:38+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P13.json) |
| <a id="p14"></a>P14 | [Evaluate deployed interactions with the Microsoft Foundry SDK - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-deployed-interactions) | 2026-09-21T10:53:03+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P14.json) |
| <a id="p15"></a>P15 | [Customize a model with fine-tuning - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/fine-tuning) | 2026-09-21T10:56:38+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P15.json) |
| <a id="p16"></a>P16 | [Hosted agents in Foundry Agent Service - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents) | 2026-09-21T10:51:00+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P16.json) |
| <a id="p17"></a>P17 | [https-learn-microsoft-com-api-search-search-22agent-20lightning-22-20-22optimiza](https://learn.microsoft.com/api/search?search=%22Agent%20Lightning%22%20%22optimization%22&locale=en-us&$top=5) | 2026-09-21T10:55:29+00:00 | prior HTTP 200; hash-verified, not refetched; discovery only; [extract](results/20260921-research/prior-verified/P17.json) |
| <a id="p18"></a>P18 | [https-learn-microsoft-com-api-search-search-22foundry-22-20-22evaluation-22-20-2](https://learn.microsoft.com/api/search?search=%22Foundry%22%20%22evaluation%22%20%22billing%22&locale=en-us&$top=6) | 2026-09-21T10:54:16+00:00 | prior HTTP 200; hash-verified, not refetched; discovery only; [extract](results/20260921-research/prior-verified/P18.json) |
| <a id="p19"></a>P19 | [https-learn-microsoft-com-api-search-search-22hosted-20agents-22-20-22ga-22-loca](https://learn.microsoft.com/api/search?search=%22hosted%20agents%22%20%22GA%22&locale=en-us&$top=8) | 2026-09-21T10:55:05+00:00 | prior HTTP 200; hash-verified, not refetched; discovery only; [extract](results/20260921-research/prior-verified/P19.json) |
| <a id="p20"></a>P20 | [https-learn-microsoft-com-api-search-search-foundry-20hosted-20agents-20generall](https://learn.microsoft.com/api/search?search=Foundry%20Hosted%20agents%20generally%20available&locale=en-us&$top=5) | 2026-09-21T10:53:45+00:00 | prior HTTP 200; hash-verified, not refetched; discovery only; [extract](results/20260921-research/prior-verified/P20.json) |
| <a id="p21"></a>P21 | [https-learn-microsoft-com-api-search-search-prompt-20optimizer-locale-en-us-top-](https://learn.microsoft.com/api/search?search=prompt%20optimizer&locale=en-us&$top=5) | 2026-09-21T10:56:11+00:00 | prior HTTP 200; hash-verified, not refetched; discovery only; [extract](results/20260921-research/prior-verified/P21.json) |
| <a id="p22"></a>P22 | [Introduction to cloud evaluation with Microsoft Foundry SDK - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation) | 2026-09-21T10:52:24+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P22.json) |
| <a id="p23"></a>P23 | [Observability in Foundry Control Plane - Pricing &#124; Microsoft Azure](https://azure.microsoft.com/pricing/details/foundryobservability/) | 2026-09-21T10:55:59+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P23.json) |
| <a id="p24"></a>P24 | [Observability in Generative AI - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/concepts/observability) | 2026-09-21T10:54:32+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P24.json) |
| <a id="p25"></a>P25 | [Agent optimizer cost and token usage overview - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/agent-optimizer-costs) | 2026-09-21T10:53:01+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P25.json) |
| <a id="p26"></a>P26 | [Create an evaluation dataset and evaluators for the agent optimizer (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/create-optimizer-dataset) | 2026-09-21T10:53:01+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P26.json) |
| <a id="p27"></a>P27 | [Make your hosted agent optimizer-ready in Foundry Agent Service (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/make-agent-optimizer-ready) | 2026-09-21T10:53:00+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P27.json) |
| <a id="p28"></a>P28 | [Optimize agent instructions, skills, tools, and models in Foundry Agent Service (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/optimize-agent-targets) | 2026-09-21T10:56:38+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P28.json) |
| <a id="p29"></a>P29 | [Optimize agent prompts with Prompt Optimizer (preview) - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/prompt-optimizer) | 2026-09-21T10:56:37+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P29.json) |
| <a id="p30"></a>P30 | [What is Microsoft Foundry Agent Service? - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/agents/overview) | 2026-09-21T10:50:26+00:00 | prior HTTP 200; hash-verified, not refetched; [extract](results/20260921-research/prior-verified/P30.json) |
| <a id="foundry-home"></a>foundry-home | [Microsoft Foundry documentation &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/) | 2026-09-21T11:26:58Z | fresh HTTP 200; [extract](results/20260921-research/discovery/foundry-home.json) |
| <a id="foundry-overview"></a>foundry-overview | [What is Microsoft Foundry? - Microsoft Foundry &#124; Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/what-is-foundry) | 2026-09-21T11:27:00Z | fresh HTTP 200; [extract](results/20260921-research/discovery/foundry-overview.json) |
| <a id="foundry-toc"></a>foundry-toc | [foundry-toc](https://learn.microsoft.com/en-us/azure/foundry/toc.json) | 2026-09-21T11:27:02Z | fresh HTTP 200; navigation, not release proof; [extract](results/20260921-research/discovery/foundry-toc.json) |
