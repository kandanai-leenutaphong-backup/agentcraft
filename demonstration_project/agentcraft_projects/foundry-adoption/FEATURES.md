# Foundry Features And AgentCraft Adoption

Research-only inventory, observed **2026-09-21**. Adoption has not begun. Every
Foundry integration in **this project** is `not_verified`; documentation is not
service execution, compatibility, security acceptance, or measured effort reduction.
The scope is wider than evaluation, hosted agents, and Agent Optimizer.

## Read This Catalogue

Rows represent distinct adoption decisions, grouping closely related subfeatures.
They are not a count of SKUs, models, APIs, or every page in a changing product.
The official TOC contains 550 linked navigation entries; many are tutorials,
language variants, or duplicate routes. The official capability reference and
family documents guide the inventory. [Sources and refresh procedure](SOURCES.md).

**Class:** `Native` = Foundry service/platform; `Framework` = SDK/open-source
execution, not a managed service guarantee; `Adjacent` = separately owned Azure
or Microsoft service; `Classic` = legacy portal/API surface. Combined classes
identify real boundaries, not bundled entitlements.

**Maturity:** `GA` = explicit official GA statement for the named scope;
`Preview` = explicit page/catalogue label; `Mixed` = feature/version/region split;
`Unspecified` = documented, no verified release claim. These labels describe
documentation confidence, not AgentCraft runtime readiness. Portal GA does not
make every tool, model, region, SDK, or government-cloud feature GA.

**Recommendations:** `Now pilot` = best next proposal, **not authorized**;
`Later` = after prerequisites; `Conditional` = only with named need/constraints;
`Watch` = changing, preview, or weak current fit; `Not a replacement` = retain
AgentCraft owner. Mechanisms are hypotheses, not savings already measured.

## Existing Owners

Owner abbreviations below identify reuse or extension, not an implemented Foundry
adapter. Source contracts were inspected; their historical tests were not rerun.

| Owner | Verified local surface and boundary |
| --- | --- |
| LL | [llm_interface](../../../libraries/llm-interface/README.md): `connect`, native framework chat/structured output, streaming, text embeddings, local function tools. Multimodal, hosted tools/remote agents, durable sessions and automatic fallback are absent. Extend this owner, do not add another model loop. |
| MA | [modular-agents](../../../libraries/modular-agents/README.md): `agentconfig`, `toolshape`, `hostedagents`, content-addressed local bundles and owner-bound transport. Bundle existence is not Foundry hosting compatibility or cloud verification; build dependency publication remains a prerequisite. |
| AO | [agent_optimization contract](../../../.github/skills/agent-optimization/CONTRACT.md): frozen cohorts, immutable generations, evaluation/replay, evaluator-only labels, bounded tool execution and recoverable completed-output persistence. Not a Foundry evaluation/optimizer client. |
| DATA | [azdata](../../../libraries/azure-data-connectors/README.md): typed bounded Search, Blob, ADX/Eventhouse, databases and Fabric GraphModel operations. New IQ/agentic-retrieval contracts must not hide inside arbitrary provider options. |
| AUTH | [identity owners](../../../docs/README.md#reference): `entra_auth` for human identity; `signed_dev_access` for signed agent requests. Host authorization remains separate from service workload credentials. |
| CORE | [architecture and context](../../../docs/README.md#concepts): caller/execution context, participating budgets, explicit composition/lifetimes; not a distributed billing cap. |
| REC | [recoverable-jobs contract](../../../.github/skills/recoverable-jobs/CONTRACT.md): completed-output recovery and read-back, not computation resumption or scheduler. |
| INV | [resource_explorer](../../../libraries/resource-explorer/README.md): host-declared inventory, not an estate-wide governance control plane. |
| CU | [Content Understanding recipe](../../../.github/skills/azure-content-understanding/README.md): official SDK extraction recipe, not a universal perception adapter. |
| DEP | [deployment owner](../../../deploy/README.md): host-owned explicit deployment entry point and targets. No deployment change is proposed as already implemented. |
| New capability | No adequate public local contract established for this outcome. Placement and authorization remain future decisions; not permission to create a new library. |

## 1. Platform And Developer Surfaces

Foundry evolved from Azure AI Studio/Azure AI Foundry. The Azure resource provider
remains `Microsoft.CognitiveServices/accounts`; new Foundry resources/projects are
not interchangeable with every classic hub/project or standalone service.
[F03](SOURCES.md#f03), [F55](SOURCES.md#f55).

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| PF01 | Foundry resources and child projects; asset/connection scope | Native | Separate future research/dev/production targets; DEP, AUTH | Complement explicit project ownership | Conditional | GA core / mixed types; [F02](SOURCES.md#f02), [F55](SOURCES.md#f55) |
| PF02 | New portal: Discover, Build, Operate; classic navigation | Native / Classic | Operator inspection without a custom admin UI; INV | Replace selected administration screens, not callable contracts | Later | Mixed; [F02](SOURCES.md#f02), [F03](SOURCES.md#f03) |
| PF03 | Model and agent playgrounds; quick comparison | Native | Development-only prompt exploration; AO | Complement repeatable frozen evaluation | Conditional | Mixed; [F01](SOURCES.md#f01), [F02](SOURCES.md#f02) |
| PF04 | Project SDKs: Python, C#, JavaScript, Java | Native SDK | Integrate supported cloud operations; LL, MA | Replace handwritten service transport | Later | Language/API-specific; [F04](SOURCES.md#f04) |
| PF05 | OpenAI-compatible APIs, provider-specific endpoints, REST | Native | Keep model versus project versus management endpoints explicit; LL | Complement one invocation owner | Conditional | Mixed; [F04](SOURCES.md#f04), [F77](SOURCES.md#f77) |
| PF06 | Azure Developer CLI agent extensions: scaffold, run, test, deploy | Native tooling | Reproducible future worker lifecycle; DEP, MA | Replace ad-hoc deployment commands | Later | Unspecified; [F56](SOURCES.md#f56) |
| PF07 | Azure CLI / ARM management; Bicep / Terraform | Native / Adjacent | Declarative resource and deployment management; DEP | Complement existing single deployment entry point | Later | Unspecified; [F01](SOURCES.md#f01), [F55](SOURCES.md#f55) |
| PF08 | Foundry Toolkit for VS Code: project/model/agent development | Native tooling | Local authoring/debugging convenience; MA | Complement canonical source and CLI reproducibility | Conditional | Mixed; [F57](SOURCES.md#f57) |
| PF09 | Foundry Agent Canvas; visual composition/inspection | Native tooling | SME/design discussion of agent shape; MA | Complement source-owned definitions, not independent runtime logic | Watch | Unspecified; [F01](SOURCES.md#f01), [F80](SOURCES.md#f80) |
| PF10 | Templates, samples, coding-agent Foundry Skill | Framework / tooling | Bootstrap a separately approved integration; DEP, MA | Replace boilerplate only after review | Conditional | Mixed; [F01](SOURCES.md#f01), [F56](SOURCES.md#f56) |
| PF11 | Foundry MCP Server for coding agents | Native tooling | Agent-assisted resource development; new capability | Complement operator workflow; discovery grants no execution | Watch | Preview; [F01](SOURCES.md#f01), [F80](SOURCES.md#f80) |
| PF12 | Project connections, shared tools and external resources | Native / Adjacent | Bind existing data/tool targets; DATA, AUTH | Complement explicit endpoint and credential injection | Later | Mixed; [F13](SOURCES.md#f13), [F55](SOURCES.md#f55) |
| PF13 | API lifecycle, SDK migration, agent/model version pins | Native SDK | Reproducible artifacts and exact supported calls; LL, MA, AO | Complement immutable local pins | Now pilot | Mixed; [F03](SOURCES.md#f03), [F04](SOURCES.md#f04), [F37](SOURCES.md#f37) |

## 2. Models, Deployment And Inference

Catalog inclusion is not a license, quota, regional entitlement, common API,
or common privacy policy. Azure-sold, partner/community, and differently hosted
models require separate review. Global/Data Zone/Regional describe processing
placement and capacity, not blanket residency guarantees for tools and logs.
[F05](SOURCES.md#f05), [F06](SOURCES.md#f06), [F32](SOURCES.md#f32),
[F78](SOURCES.md#f78), [F79](SOURCES.md#f79).

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| MD01 | Azure-sold catalog: Microsoft, OpenAI and participating commercial/open-model providers | Native | Compare suitable reasoning, generation and embedding models; LL, AO | Complement frozen model selection | Conditional | Model-specific; [F05](SOURCES.md#f05) |
| MD02 | Partner/community and Hugging Face models; model cards/licenses | Native / ecosystem | Specialist/open-weight model candidates; LL | Complement deployment choices; no automatic license equivalence | Conditional | Mixed; [F05](SOURCES.md#f05), [F79](SOURCES.md#f79) |
| MD03 | Fireworks integration and custom model import | Adjacent integration | Only if required model unavailable through current owner; new capability | Complement catalog, not a new default backend | Watch | Unspecified; [F01](SOURCES.md#f01), [F80](SOURCES.md#f80) |
| MD04 | Model leaderboards, benchmarks and side-by-side comparisons | Native | Shortlist before task-specific testing; AO | Complement domain evaluation, never substitute for it | Now pilot | Unspecified; [F01](SOURCES.md#f01), [F05](SOURCES.md#f05) |
| MD05 | Model Router; cost/quality routing and constrained model choices | Native | Future variable-complexity worker requests; LL, AO | Replace custom model-selection heuristics after controlled tests | Conditional | Model/version-specific; [F08](SOURCES.md#f08) |
| MD06 | Deployment-free instant model access | Native | Low-setup development where approved; LL | Replace explicit deployment setup for supported models only | Watch | Preview; [F01](SOURCES.md#f01), [F07](SOURCES.md#f07) |
| MD07 | Serverless/API deployments and partner access modes | Native / Adjacent | Select supported model delivery contract; LL, DEP | Replace own serving infrastructure where offered | Conditional | Mixed; [F05](SOURCES.md#f05), [F07](SOURCES.md#f07), [F79](SOURCES.md#f79) |
| MD08 | Managed compute for dedicated/custom model hosting | Native | Specialized model not available as shared API; DEP | Replace VM serving operations, not model lifecycle responsibilities | Later | Preview; [F01](SOURCES.md#f01), [F07](SOURCES.md#f07) |
| MD09 | Standard regional deployments | Native | Region-constrained online inference; LL, DEP | Complement capacity/residency policy | Conditional | Model-specific; [F06](SOURCES.md#f06), [F78](SOURCES.md#f78) |
| MD10 | Global Standard and Data Zone Standard | Native | Choose availability and processing geography; LL, DEP | Complement capacity planning; no implicit data approval | Conditional | Model-specific; [F06](SOURCES.md#f06), [F32](SOURCES.md#f32) |
| MD11 | Provisioned throughput: regional/global/data-zone options | Native | Predictable sustained approved workload; DEP | Replace some capacity variability with paid reservation | Later | Model-specific; [F06](SOURCES.md#f06) |
| MD12 | Batch inference; file jobs, asynchronous results/cancellation | Native | Offline development scoring/generation; LL, AO, REC | Complement cheaper asynchronous work, preserve failed/unknown results | Conditional | Model-specific; [F58](SOURCES.md#f58) |
| MD13 | Priority processing / service tiers | Native | Latency-sensitive future interactive workers; LL | Complement latency planning; additional cost tradeoff | Later | Unspecified; [F01](SOURCES.md#f01), [F06](SOURCES.md#f06) |
| MD14 | Chat Completions and Responses; streaming, tools, response state | Native | Existing text inference plus future remote contract; LL | Reuse native SDK; avoid handwritten protocol loops | Now pilot | Mixed; [F04](SOURCES.md#f04), [F09](SOURCES.md#f09) |
| MD15 | Text embeddings; provider/model-specific dimensions and endpoints | Native | Existing retrieval integration; LL, DATA | Reuse LL text embeddings; separate `/models` support remains absent | Conditional | Model-specific; [F05](SOURCES.md#f05), [F77](SOURCES.md#f77) |
| MD16 | Image/PDF input and multimodal reasoning | Native | Analyze authorized diagrams/documents; LL extension, CU | Complement extraction; not implemented by current LL contract | Later | Model-specific; [F09](SOURCES.md#f09) |
| MD17 | Realtime speech/audio via WebRTC, WebSocket and SIP | Native / Adjacent | Voice investigation interface only if needed; new capability | Replace speech orchestration plumbing, not domain policy | Conditional | API/model-specific; [F61](SOURCES.md#f61) |
| MD18 | Audio generation/input, transcription and translation models | Native | Spoken evidence or accessibility; LL extension | Complement dedicated Speech service choices | Conditional | Mixed; [F64](SOURCES.md#f64), [F41](SOURCES.md#f41) |
| MD19 | Image generation and editing | Native | Authorized training/demo imagery; new capability | No fit for core factual investigation; never evidence generation | Conditional | Model-specific; [F62](SOURCES.md#f62) |
| MD20 | Video generation | Native | Optional explanatory media, never observed-event evidence | No fit for current adoption priority | Watch | Preview; [F63](SOURCES.md#f63) |
| MD21 | Structured outputs / JSON Schema and strict function schemas | Native | Machine-readable diagnoses/citations; LL, toolshape | Replace format-repair code; retain semantic validation/refusals | Now pilot | Model/schema-specific; [F10](SOURCES.md#f10) |
| MD22 | Prompt caching, cache keys and model-specific retention policies | Native | Reused instructions/schema prefixes; LL | Complement latency/cost reduction hypothesis; measure hits and writes | Conditional | Model-specific; [F11](SOURCES.md#f11) |
| MD23 | Background Responses, polling/cancellation and stream continuation | Native | Long development jobs; LL extension, REC | Complement durable output recovery; cancellation is not rollback | Later | Feature-specific; [F09](SOURCES.md#f09) |
| MD24 | Model versions, upgrade policy, retirement notifications | Native | Pin and requalify candidates before endpoint changes; LL, AO, DEP | Complement regression gates; no silent model substitution | Now pilot | Mixed; [F37](SOURCES.md#f37), [F03](SOURCES.md#f03) |

## 3. Agents, Runtime, State And Orchestration

Hosted agents provide managed container execution, not automatic migration of
`hostedagents` bundles. Current LL cannot call remote agents/hosted tools.
Responses, Invocations and WebSocket invocation paths differ. A persisted sandbox
session is not the same as conversation history or long-term memory.
[P16](SOURCES.md#p16), [F48](SOURCES.md#f48).

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AG01 | Prompt agents: instructions, model, tools and managed execution | Native | Small constrained information worker; MA, LL extension | Replace a simple hosted tool loop after parity checks | Conditional | Service GA; subfeature-specific; [P04](SOURCES.md#p04), [P30](SOURCES.md#p30) |
| AG02 | Hosted agents: containerized bring-your-code runtime, scaling/isolation | Native | One read-only evidence worker; MA, LL, DEP | Replace container serving operations, not business logic | Now pilot | Mixed: service GA, hosted subfeatures vary; [P04](SOURCES.md#p04), [P16](SOURCES.md#p16) |
| AG03 | Microsoft Agent Framework agents and workflows | Framework | Existing native engine; LL, MA | Reuse framework instead of a second execution loop | Not a replacement | Language/feature-specific; [F49](SOURCES.md#f49) |
| AG04 | LangGraph/LangChain and other bring-your-code agents | Framework / Native hosting | Host existing framework implementation if justified; MA extension | Complement hosting without forcing framework rewrite | Conditional | Framework/protocol-specific; [P16](SOURCES.md#p16), [F01](SOURCES.md#f01) |
| AG05 | Declarative Foundry workflows: branching, sequencing, visual authoring | Native / Classic | Existing-workflow migration only; MA | No fit for new dependency; favor supported framework workflow | Watch | Preview; retirement documented for 2026-12-01; [F65](SOURCES.md#f65) |
| AG06 | Agent definitions, immutable versions and deployment lifecycle | Native | Match local bundle/definition hashes to cloud versions; MA, AO | Complement exact artifact identity | Later | Mixed; [P16](SOURCES.md#p16), [F56](SOURCES.md#f56) |
| AG07 | Responses protocol integration | Native protocol | Remote invocation, platform conversation/evaluation integration; LL extension | Replace custom HTTP adapter where compatible | Later | Protocol-specific; [P16](SOURCES.md#p16), [F48](SOURCES.md#f48) |
| AG08 | Invocations HTTP and WebSocket protocols | Native protocol | Non-Responses/custom or streaming agents; LL extension | Complement flexible serving; platform features differ | Conditional | Protocol-specific; [P16](SOURCES.md#p16) |
| AG09 | Conversation history, response chaining and state read-back | Native | Multi-turn user sessions; LL extension, AUTH | Replace history storage only where ownership/deletion verified | Later | Protocol-specific; [F09](SOURCES.md#f09), [F48](SOURCES.md#f48) |
| AG10 | Hosted sandbox sessions, files, idleness and isolation keys | Native | Reuse worker working files across turns; MA, AUTH | Replace some session compute/storage plumbing | Later | Bounded lifecycle, not archival storage; [F48](SOURCES.md#f48) |
| AG11 | Long-term memory stores, extraction and scoped retrieval | Native | Approved persistent preferences/context; new capability | Complement conversation history; do not contaminate held-out cases | Watch | Preview; [F12](SOURCES.md#f12) |
| AG12 | Durable state store / framework checkpoints | Native / Framework | Resumable authorized worker tasks; MA extension | Complement REC; resuming computation is a different contract | Later | Preview; [F66](SOURCES.md#f66) |
| AG13 | Long-running tasks, reconnectable streaming and task-state handles | Native / Framework | Resilient asynchronous workers; LL, MA extension | Replace custom reconnect plumbing only after failure probes | Later | Preview scope; [F46](SOURCES.md#f46), [F66](SOURCES.md#f66) |
| AG14 | Human approval, pause/resume and framework interrupts | Native / Framework | SME gate before actions; MA, AUTH | Complement explicit authorization; a resumed task is not approval proof | Conditional | Hosted long-running path Preview; [F46](SOURCES.md#f46) |
| AG15 | Multi-agent sequences, parallelism, routing and handoffs | Framework | Bounded specialist work; MA | Reuse framework graph, keep mission authority at AgentCraft | Not a replacement | Framework/version-specific; [F49](SOURCES.md#f49) |
| AG16 | Autopilots, standing roles, agent user identities and event-driven work | Native / Adjacent M365 | Only after unattended operational authority is defined; new capability | Complement proactive workflows; no existing grant | Watch | Unspecified / dependent services; [F45](SOURCES.md#f45) |
| AG17 | Publish to Microsoft 365 Copilot / Teams | Native / Adjacent | SME access through existing collaboration channels; AUTH, DEP | Replace custom channel connector where appropriate | Conditional | Channel/tenant-specific; [F47](SOURCES.md#f47) |
| AG18 | Voice-enabled agents | Native / Adjacent Speech | Optional spoken investigation workflow; new capability | Complement existing text interface | Conditional | Mixed; [F41](SOURCES.md#f41), [F61](SOURCES.md#f61) |
| AG19 | Agent stop, session deletion, image updates and operational cleanup | Native | Explicit settled worker lifecycle; DEP, MA | Complement resource settlement; never equate stop with rollback | Later | Protocol/operation-specific; [F48](SOURCES.md#f48), [F56](SOURCES.md#f56) |

## 4. Tools, Skills And External Actions

Tool discovery and tool authentication do not grant application action authority.
Retain allowlists, bounded arguments, approval policy, audit and read-back.
Side-effecting tools are excluded from initial pilots and optimizer repetition.

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| TL01 | Function calling and typed tool arguments | Native / Framework | Existing local evidence tools; LL, toolshape | Reuse validated tools; no duplicate dispatcher | Not a replacement | Model-specific; [F09](SOURCES.md#f09), [P30](SOURCES.md#p30) |
| TL02 | OpenAPI tools, schema-driven REST integration | Native | Expose approved read-only application APIs; MA, AUTH | Replace simple REST glue, retain host policy | Conditional | Authentication/schema constraints; [F67](SOURCES.md#f67) |
| TL03 | Remote MCP tools, approvals and connection authentication | Native protocol | Connect approved evidence servers; LL extension, AUTH | Replace transport adapters; not trust validation | Conditional | Server/auth-specific; [F14](SOURCES.md#f14) |
| TL04 | Managed MCP servers and enterprise connectors | Native / Adjacent | Approved enterprise reads; DATA, new capability | Replace connector hosting only for supported services | Later | Preview; [F15](SOURCES.md#f15) |
| TL05 | Toolboxes: reusable curated tool collections | Native | Share governed tool sets across workers; MA | Complement local allowlisted tool registry | Later | GA core; [F02](SOURCES.md#f02), [F13](SOURCES.md#f13) |
| TL06 | Private tool catalogs and approved discovery | Native | Organization-only tool exposure; MA, AUTH | Complement per-agent execution allowlists | Later | Mixed; [F13](SOURCES.md#f13), [F54](SOURCES.md#f54) |
| TL07 | Tool search / deferred tool loading | Native | Large catalogs without all schemas in every prompt; MA | Replace manual tool pruning only with recall/refusal checks | Conditional | Unspecified; [F73](SOURCES.md#f73) |
| TL08 | Agent skills and private skill catalogs | Native / Framework | Reusable instructions/assets for approved workers; MA | Complement versioned skill sources; review code/asset trust | Watch | Preview; [F74](SOURCES.md#f74) |
| TL09 | A2A remote agent delegation and authentication | Native protocol / ecosystem | Bounded specialist service calls; LL, MA extension | Replace custom delegation transport, not recursive mission control | Conditional | Protocol-specific; [F16](SOURCES.md#f16) |
| TL10 | Web Search tool | Native / external web | Public reference grounding; new capability | Complement reproducible webres evidence; not source archival | Conditional | Terms/region-specific; [F17](SOURCES.md#f17) |
| TL11 | Grounding with Bing Search | Adjacent integration | Current public knowledge where approved | Replace bespoke search integration; privacy review mandatory | Conditional | Separate terms/billing; [F17](SOURCES.md#f17) |
| TL12 | Grounding with Bing Custom Search / domain constraints | Adjacent integration | Restricted public-document sources | Complement source allowlist; domain filtering is not evidence validation | Conditional | Tool-specific; [F17](SOURCES.md#f17) |
| TL13 | File Search and managed vector stores | Native | Small approved document collections; DATA extension | Replace simple chunk/embed/retrieve pipeline | Conditional | Limits/billing apply; [F20](SOURCES.md#f20) |
| TL14 | Code Interpreter: managed Python sandbox, file analysis | Native | Isolated calculations over approved development data; AO | Complement sandboxed tools; not equivalent to current isolation contract | Conditional | Tool-specific; [F53](SOURCES.md#f53) |
| TL15 | Custom Code Interpreter | Native / Adjacent compute | Controlled packages/runtime for analysis; new capability | Complement managed sandbox; operator owns environment/security | Later | Preview scope; [F76](SOURCES.md#f76) |
| TL16 | Browser Automation | Native / Adjacent browser | Authorized web UI checks; new capability | Replace browser hosting, not deterministic acceptance checks | Conditional | Preview; [F52](SOURCES.md#f52) |
| TL17 | Computer Use | Native model/tool | Only isolated UI experiments with explicit approvals | No fit for initial read-only adoption pilot | Watch | Preview; [F51](SOURCES.md#f51) |
| TL18 | Image generation as agent tool | Native | Optional presentation asset creation | Complement image API; never fabricate operational evidence | Watch | Preview tool versus model-specific API; [F01](SOURCES.md#f01), [F62](SOURCES.md#f62) |
| TL19 | Logic Apps actions and enterprise workflow connectors | Adjacent integration | Future approved ticket/workflow actions; new capability | Replace integration plumbing; actions remain separately authorized | Later | Connector-specific; [F15](SOURCES.md#f15), [P30](SOURCES.md#p30), [F31](SOURCES.md#f31) |
| TL20 | Azure Functions tool integration | Adjacent integration | Thin deployed callable evidence tool; MA, DEP | Complement existing callable owner rather than copy its rule | Conditional | Tool-specific; [P30](SOURCES.md#p30), [F31](SOURCES.md#f31) |
| TL21 | Reminder tool / self-scheduled hosted invocations | Native | Approved periodic development tasks; new capability | Replace simple wake-up plumbing, not portfolio scheduler | Watch | Preview/navigation label; [F75](SOURCES.md#f75) |
| TL22 | Tool guardrails, auth and gateway policy | Native / Adjacent APIM | Consistent restrictions on external tool calls; AUTH, CORE | Complement hard application refusals and audit | Later | Mixed/preview controls; [F54](SOURCES.md#f54), [F30](SOURCES.md#f30) |

## 5. Knowledge And Data Grounding

Foundry IQ is not a new general database. Azure AI Search owns indexing/retrieval;
Fabric IQ and Work IQ own different enterprise knowledge domains. ACL enforcement
depends on source support, ingestion configuration and caller identity; test denied
users and stale permissions, not only successful retrieval.

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| KN01 | Foundry IQ reusable multi-source knowledge bases | Native / Adjacent Search | Shared evidence grounding across workers; DATA extension | Replace per-agent retrieval wiring, not domain evidence meaning | Conditional | API GA subset / portal Preview; [F18](SOURCES.md#f18), [F02](SOURCES.md#f02) |
| KN02 | Knowledge sources: indexed and remote content | Native / Adjacent | Approved Blob, SharePoint, OneLake and other supported sources; DATA | Complement existing bounded data access | Conditional | Source/API-specific; [F18](SOURCES.md#f18) |
| KN03 | Agentic retrieval: query decomposition, parallel retrieval, synthesis | Adjacent Search | Complex multi-part research queries; DATA extension | Replace custom retrieval planning; measure latency and relevance | Conditional | Mixed; LLM planning Preview; [F21](SOURCES.md#f21) |
| KN04 | Keyword, vector and hybrid search | Adjacent Search | Existing searchable evidence; DATA, LL embeddings | Reuse current Search owner; no new duplicate facade | Not a replacement | Feature-specific; [F18](SOURCES.md#f18), [F21](SOURCES.md#f21) |
| KN05 | Semantic ranking/reranking | Adjacent Search | Improve evidence ordering; DATA | Complement retrieval metrics, not correctness guarantee | Conditional | Feature-specific; [F21](SOURCES.md#f21) |
| KN06 | Chunking, embeddings, metadata extraction and incremental indexing | Adjacent Search | Authorized document ingestion pipeline; DATA, CU | Replace repetitive ingestion stages where supported | Later | Source/API-specific; [F18](SOURCES.md#f18) |
| KN07 | ACL synchronization, query-time permissions and sensitivity labels | Native / Adjacent | Enforce user-visible evidence boundaries; AUTH, DATA | Complement record authorization with source-level filtering | Conditional | Source/API-specific; [F18](SOURCES.md#f18) |
| KN08 | Citations, source references and retrieval activity | Native / Adjacent | Trace diagnoses to evidence; DATA, AO | Complement immutable evidence; citation presence is not validity | Now pilot | API-specific; [F18](SOURCES.md#f18), [F21](SOURCES.md#f21) |
| KN09 | Direct Azure AI Search agent tool | Native / Adjacent | Reuse an existing approved index; DATA, MA | Replace thin search-tool wiring, retain query policy | Conditional | Tool-specific; [P30](SOURCES.md#p30), [F13](SOURCES.md#f13) |
| KN10 | Fabric IQ ontology and business-semantic grounding | Adjacent Fabric | Relate evidence to approved business entities; DATA extension | Complement existing GraphModel/Eventhouse queries | Watch | Preview; [F19](SOURCES.md#f19) |
| KN11 | Fabric data agents and Power BI semantic models | Adjacent Fabric | Natural-language analytics over governed data; DATA extension | Replace some query authoring, not deterministic validation | Conditional | Fabric item/tool-specific; [F19](SOURCES.md#f19) |
| KN12 | Work IQ, Microsoft 365 work context via A2A/REST/MCP | Adjacent M365 | Permission-aware SME document/mail context; new capability | Complement domain evidence; separate credits/licensing/consent | Watch | Preview integration; [F50](SOURCES.md#f50) |
| KN13 | SharePoint grounding/connector options | Adjacent M365 / Search | Approved enterprise manuals/runbooks; DATA extension | Replace connector plumbing; compare direct versus IQ ingestion | Conditional | Path-specific; [F18](SOURCES.md#f18), [F31](SOURCES.md#f31), [F50](SOURCES.md#f50) |

## 6. Evaluation, Testing And Feedback

Evaluation can score recorded outputs without moving the application into hosted
agents. Service evaluation may still invoke a paid judge; target-based evaluation
and simulation can execute an agent and its tools. Endpoint, code and prompt
evaluators are different contracts. Freeze data, rubric, judge and controls before
comparison; service score improvement alone is not domain acceptance.
[P09](SOURCES.md#p09), [P13](SOURCES.md#p13), [P22](SOURCES.md#p22).

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| EV01 | Cloud evaluation of recorded query/response datasets | Native | Score approved immutable outputs; AO extension | Replace evaluator execution plumbing, keep local control/records | Now pilot | GA core / evaluator-specific; [F02](SOURCES.md#f02), [P22](SOURCES.md#p22) |
| EV02 | Live model/agent evaluation targets | Native | Separately authorized candidate execution; AO, LL | Complement target invocation; tools can have side effects | Later | Target/protocol-specific; [P13](SOURCES.md#p13) |
| EV03 | General quality: relevance, coherence, fluency and rubric judgments | Native evaluators | Secondary answer-quality signals; AO | Replace generic judge scaffolding, calibrate against SMEs | Now pilot | Evaluator-specific; [F22](SOURCES.md#f22) |
| EV04 | Text similarity and deterministic grading | Native evaluators | Structured expected-answer checks; AO | Complement domain exact-match/semantic policy | Conditional | Evaluator-specific; [F22](SOURCES.md#f22) |
| EV05 | RAG groundedness, retrieval relevance and response completeness | Native evaluators | Grounding quality/citation pilot; AO, DATA | Replace generic RAG checks, retain evidence-validity rules | Now pilot | Evaluator-specific; [F22](SOURCES.md#f22) |
| EV06 | Risk/safety evaluators: harmful content and vulnerable behavior | Native evaluators | Negative-case development suite; AO | Complement hard refusal policy, not probabilistic replacement | Now pilot | Evaluator-specific; [F22](SOURCES.md#f22) |
| EV07 | Agent task completion and tool-use evaluators | Native evaluators | Tool selection, inputs, outputs and task adherence; AO, toolshape | Complement task-specific traces and expected actions | Now pilot | Mixed; task completion/adherence Preview; [P02](SOURCES.md#p02) |
| EV08 | Prompt-based custom evaluators | Native | Encode versioned SME rubric; AO | Replace reusable judge wrapper; rubric remains local authority | Conditional | Preview; [P09](SOURCES.md#p09) |
| EV09 | Custom-code evaluators | Native / caller code | Deterministic task/citation checks; AO | Reuse existing rules through supported contract | Conditional | Preview; packaging/runtime limits; [P09](SOURCES.md#p09) |
| EV10 | Endpoint-backed custom evaluators | Native / external endpoint | Reuse separately secured domain scoring endpoint; AO, AUTH | Complement existing grading service, not arbitrary evaluator access | Conditional | Preview; endpoint/auth-specific; [P09](SOURCES.md#p09) |
| EV11 | Supported judge models, admin-connected judges and OpenAI graders | Native / Adjacent | Compare suitable judge behavior; AO, LL | Complement evaluator calibration; judge/target pins stay separate | Conditional | Mixed; admin-connected support Preview; [P12](SOURCES.md#p12), [F22](SOURCES.md#f22) |
| EV12 | Multi-turn conversation dataset evaluation | Native | Full investigation dialogue quality; AO | Replace per-turn-only aggregation where supported | Now pilot | Evaluator-specific; [P10](SOURCES.md#p10) |
| EV13 | Trace/span-backed evaluation and deployed interactions | Native | Evaluate captured tool trajectories; AO, CORE | Complement immutable semantic events with service traces | Conditional | Trace/target-specific; [P14](SOURCES.md#p14), [F27](SOURCES.md#f27) |
| EV14 | Batch evaluation, datasets, schemas and result analysis | Native | Repeatable development cohorts; AO | Complement local dataset/generation identities | Now pilot | GA core / mixed extras; [F24](SOURCES.md#f24), [P22](SOURCES.md#p22) |
| EV15 | Continuous/sampled production evaluation | Native | Drift detection after authorized rollout; AO extension | Replace generic sampling/judging plumbing, not release acceptance | Later | Monitoring Preview / feature-specific; [P08](SOURCES.md#p08), [F02](SOURCES.md#f02) |
| EV16 | Scheduled evaluation policies and repeated monitoring | Native / operational composition | Periodic approved checks; AO, DEP | Complement scheduler and budgets; exact schedule contract unresolved | Later | Recurring evaluations Preview; [P08](SOURCES.md#p08) |
| EV17 | Synthetic evaluation datasets and trace-to-dataset conversion | Native | Development case expansion; AO | Replace some drafting effort; never manufacture independent held-out proof | Conditional | Preview; [F68](SOURCES.md#f68), [F24](SOURCES.md#f24), [F02](SOURCES.md#f02) |
| EV18 | Multi-turn simulators, personas and synthetic queries | Native / SDK | Exercise development dialogues; AO | Complement real SME cases, not population-representative evidence | Conditional | Conversation simulation Preview; [F69](SOURCES.md#f69) |
| EV19 | AI red teaming, adversarial scans, attack strategies | Native / SDK | Authorized isolated refusal/security probes; AO | Replace attack-generation plumbing; retain threat model and manual review | Conditional | GA overview / method-specific; [F02](SOURCES.md#f02), [F23](SOURCES.md#f23) |
| EV20 | Human evaluation, trace annotation and end-user feedback | Native | SME judgments and disagreements; AO | Complement human decision ownership, not replace it | Now pilot | Feature-specific; [F25](SOURCES.md#f25), [F27](SOURCES.md#f27) |
| EV21 | CI/CD evaluations, benchmark runs and cluster/error analysis | Native / tooling | Gate exact artifacts and inspect failures; AO, DEP | Complement local deterministic tests and frozen acceptance | Later | Mixed; cluster analysis Preview; [F01](SOURCES.md#f01), [F02](SOURCES.md#f02), [F56](SOURCES.md#f56) |

## 7. Optimization And Model Customization

Agent Optimizer searches exposed configuration, **not arbitrary application code
or model weights**. Hosted optimization needs an optimizer-ready configuration
loader and supported Responses integration. Validation feedback is development
evidence; it does not become an untouched final test. Repeated tool use can charge
money or mutate systems. Estimates and optimizer knobs are not hard spend caps.
[P06](SOURCES.md#p06), [P25](SOURCES.md#p25), [P27](SOURCES.md#p27),
[P28](SOURCES.md#p28).

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| OP01 | Agent Optimizer for prompt agents | Native | Development-only instruction/model/tool-description candidates; AO | Replace manual candidate proposal loop, not independent selection | Later | Preview; [P06](SOURCES.md#p06) |
| OP02 | Hosted-agent optimization readiness and config loader | Native / SDK integration | Expose only approved configuration levers; MA, AO | Complement current definitions; application code changes stay outside search | Later | Preview; [P27](SOURCES.md#p27) |
| OP03 | Instructions, skills, tool/parameter descriptions and model selection | Native optimizer | Explicit bounded search space; AO, toolshape | Replace selected configuration trial generation | Later | Preview / agent-type-specific; [P28](SOURCES.md#p28), [P06](SOURCES.md#p06) |
| OP04 | Optimizer datasets, validation, scores and token/cost controls | Native optimizer | Isolated dev cohort, read-only tools and external budget monitoring; AO, CORE | Complement frozen controls; estimated costs are not enforced billing ceilings | Later | Preview; [P25](SOURCES.md#p25), [P26](SOURCES.md#p26) |
| OP05 | Prompt optimizer | Native evaluation tooling | Rewrite one prompt from examples/evaluation feedback; AO | Replace narrow prompt-edit loop, not agent architecture | Conditional | Preview; [P29](SOURCES.md#p29) |
| OP06 | Supervised fine-tuning, vision tuning and deployment of tuned models | Native model customization | Stable repeated task after sufficient approved data; LL, AO | Complement prompting/RAG; training changes weights | Later | GA core / model-specific; [P15](SOURCES.md#p15), [F02](SOURCES.md#f02) |
| OP07 | Direct Preference Optimization (DPO) | Native model customization | Approved preference pairs for behavior/style; AO | Complement SME preference capture; not instruction search | Later | Model-specific; [F71](SOURCES.md#f71) |
| OP08 | Reinforcement Fine-Tuning (RFT) and graders | Native model customization | Verifiable reward task with trustworthy grader; AO | Complement training pipeline; independent final evaluation mandatory | Later | Model-specific; [F72](SOURCES.md#f72) |
| OP09 | Distillation / synthetic teacher outputs for training | Workflow using models/tuning | Smaller approved specialist from vetted teacher examples; AO, LL | Complement training, not a universal standalone Agent Optimizer switch | Conditional | Workflow/model-specific; [P15](SOURCES.md#p15), [F68](SOURCES.md#f68) |
| OP10 | Agent Lightning training/optimization research toolkit | Framework / open-source research | Specialized future learning experiment; new capability | Complement research, not a managed Foundry service replacement | Watch | Research toolkit, no service-GA claim; [P03](SOURCES.md#p03) |
| OP11 | AgentCraft mission strategy, hard refusals, frozen evaluation and recovery | AgentCraft retained control | AO, CORE, AUTH, REC and SMEs | No fit as wholesale Foundry replacement | Not a replacement | Local contract, cloud integrations not_verified; [local contract](../../../.github/skills/agent-optimization/CONTRACT.md) |

## 8. Observability And Governance

Tracing describes what was captured, not hidden reasoning, complete telemetry,
or a tamper-proof record. Application Insights ingestion/retention and evaluation
judges have separate meters. Sensitive prompt/tool content needs deliberate
collection, access and retention policy.
[F27](SOURCES.md#f27), [P23](SOURCES.md#p23).

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| OB01 | OpenTelemetry traces: requests, model/tool spans, correlation | Native / Framework | Correlate existing semantic events with cloud spans; CORE, LL, MA | Replace custom trace transport/viewer plumbing | Now pilot | GA prompt/hosted; external/workflow Preview; [F27](SOURCES.md#f27) |
| OB02 | Application Insights storage/query and telemetry retention | Adjacent Azure Monitor | Durable operational diagnostics; new adapter, CORE | Replace bespoke telemetry backend, not authoritative AO records | Conditional | Service-specific; [F27](SOURCES.md#f27) |
| OB03 | Trace replay, debugging and framework/client instrumentation | Native / Framework | Inspect exact failing trajectories; AO, LL | Complement persisted replay; do not reexecute tools implicitly | Now pilot | Mixed; [F27](SOURCES.md#f27), [F02](SOURCES.md#f02) |
| OB04 | Monitoring dashboard: latency, errors, tokens, run/tool health | Native | Operate an approved pilot; DEP, CORE | Replace generic dashboards, keep task quality separate | Later | Preview; [P08](SOURCES.md#p08), [F02](SOURCES.md#f02) |
| OB05 | End-user feedback, trace annotations and insights | Native | Connect SME feedback to versioned runs; AO | Complement adjudication, not overwrite historical outcomes | Conditional | Feature-specific; [F25](SOURCES.md#f25), [F27](SOURCES.md#f27) |
| OB06 | Control Plane fleet inventory and external-agent registration | Native / Adjacent | View supported deployed agents/models/tools; INV extension | Replace some estate inventory UI, not registry authority | Later | Mixed/preview external registration; [F26](SOURCES.md#f26) |
| OB07 | Fleet performance, compliance posture and cost visibility | Native / Adjacent | Cross-worker operations; new capability | Complement per-project immutable records | Later | Mixed/preview Operate surfaces; [F26](SOURCES.md#f26), [F02](SOURCES.md#f02) |
| OB08 | AI Gateway through API Management | Native integration / Adjacent APIM | Central model/tool endpoint policies; DEP, AUTH | Replace duplicated gateway plumbing | Later | Foundry integration Preview; [F28](SOURCES.md#f28), [F02](SOURCES.md#f02) |
| OB09 | Gateway token limits, quotas and tool policies | Adjacent APIM | Constrain approved consumers; CORE, AUTH | Complement application budgets; shared limits need explicit scope | Conditional | Policy/tier-specific; [F28](SOURCES.md#f28), [F54](SOURCES.md#f54) |
| OB10 | Defender, Purview and Entra governance integrations | Adjacent Microsoft security | Organization security/compliance review; AUTH, new capability | Complement controls; no implicit licenses or policy coverage | Later | Integration-specific; [F26](SOURCES.md#f26) |
| OB11 | Alerts, diagnostic logs, notifications and service health | Native / Adjacent Monitor | Detect failures/quota pressure after deployment; DEP | Replace generic operational alerting, not acceptance tests | Later | Mixed; [F01](SOURCES.md#f01), [F26](SOURCES.md#f26) |

## 9. Security, Privacy And Responsible AI

Neither a managed identity nor an agent identity authenticates the application's
human caller. Neither a successful tool response nor an AI safety classifier
authorizes an action. Keep positive and negative access checks at every boundary.

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| SC01 | Entra ID, managed identity and keyless service access | Native / Adjacent Entra | Explicit workload credentials; AUTH, LL, DATA | Replace secret distribution where supported | Now pilot | Surface-specific; [F29](SOURCES.md#f29) |
| SC02 | Control-plane/data-plane RBAC and project/resource scopes | Native / Adjacent | Least privilege operator versus runtime roles; AUTH, DEP | Complement application authorization | Now pilot | Core GA; [F29](SOURCES.md#f29), [F02](SOURCES.md#f02) |
| SC03 | Agent identity and autopilot agent-user identity | Native / Adjacent Entra | Attribute agent actions separately from people; AUTH extension | Complement signed caller identity, not substitute | Later | Identity/tenant-specific; [F45](SOURCES.md#f45) |
| SC04 | Caller/user versus tool authentication; delegated OAuth and agent credentials | Native / Adjacent | Preserve caller scope through external tools; AUTH | Complement host policy with service identity | Conditional | Connection-specific; [F14](SOURCES.md#f14), [F50](SOURCES.md#f50), [F54](SOURCES.md#f54) |
| SC05 | Private endpoints, VNet integration and network-secured projects | Native / Adjacent networking | Approved private evidence paths; DEP, DATA | Replace public exposure where supported, not tenant authorization | Later | Mixed and topology-specific; [P05](SOURCES.md#p05), [F34](SOURCES.md#f34) |
| SC06 | Outbound/egress controls, tool network isolation | Native / Adjacent | Restrict hosted agent destinations; DEP, AUTH | Complement read-only tool policy; test blocked destinations | Later | Hosted egress controls Preview; [F30](SOURCES.md#f30), [F34](SOURCES.md#f34) |
| SC07 | Secrets/connections and Key Vault integration | Native / Adjacent Key Vault | Resolve approved third-party credentials; DEP, AUTH | Replace embedded keys; retain explicit credential ownership | Conditional | Service-specific; [F01](SOURCES.md#f01), [F29](SOURCES.md#f29) |
| SC08 | Encryption at rest and customer-managed keys | Native / Adjacent Key Vault/HSM | Required encryption/key lifecycle policy; DEP | Complement privacy/security controls, not universal coverage | Conditional | Region/scenario constraints; [F33](SOURCES.md#f33) |
| SC09 | Model content filters, harm categories/severity and blocklists | Native / Adjacent Content Safety | Baseline input/output screening; LL | Complement deterministic refusals and SME risk policy | Conditional | Model guardrails GA / control-specific; [F30](SOURCES.md#f30), [F02](SOURCES.md#f02) |
| SC10 | Prompt Shields: user/document injection detection | Native / Adjacent Content Safety | Untrusted evidence/tool-output defenses; MA, LL | Complement data/instruction separation, not prove immunity | Now pilot | Control-specific; [F30](SOURCES.md#f30), [F44](SOURCES.md#f44) |
| SC11 | Groundedness detection | Native / Adjacent Content Safety | Flag unsupported answer content; AO, LL | Complement citation validation; evaluator/online filter differ | Conditional | Control-specific; [F30](SOURCES.md#f30), [F44](SOURCES.md#f44) |
| SC12 | Protected material detection: text and code | Native / Adjacent Content Safety | Reduce unauthorized reproduction risk; LL | Complement source rights review | Conditional | Control-specific; [F30](SOURCES.md#f30), [F44](SOURCES.md#f44) |
| SC13 | PII/sensitive data leakage controls | Native / Adjacent Language | Minimize sensitive payloads in models/tools/traces; LL, DATA | Complement data classification/redaction, not certify anonymization | Conditional | Control/service-specific; [F30](SOURCES.md#f30), [F70](SOURCES.md#f70) |
| SC14 | Agent task adherence and tool-call/tool-response intervention | Native | Detect tool misuse/exfiltration signals; MA, AUTH | Complement hard allowlists and approvals | Watch | Agent controls Preview; [F30](SOURCES.md#f30) |
| SC15 | Data residency, retention, abuse monitoring and training-use policy | Native / provider terms | Review each model, tool, trace and storage path; AUTH, DEP | Complement data-processing approval, never infer from `store=False` | Now pilot | Provider/feature-specific; [F31](SOURCES.md#f31), [F32](SOURCES.md#f32) |
| SC16 | Audit/diagnostic logs and sensitive trace access | Native / Adjacent Monitor | Incident reconstruction with restricted payload access; CORE, AUTH | Complement authoritative records; telemetry may be incomplete | Conditional | Feature-specific; [F27](SOURCES.md#f27), [F26](SOURCES.md#f26) |
| SC17 | Azure Policy model deployment controls and preview restrictions | Native / Adjacent Policy | Prevent disallowed models/regions/features; DEP | Complement application policy with resource governance | Later | Policy-specific; [F60](SOURCES.md#f60), [F02](SOURCES.md#f02) |
| SC18 | BYO storage/resources and per-service isolation | Native / Adjacent storage | Control permitted state retention and network placement; DATA, DEP | Complement storage authority, not automatic end-to-end isolation | Later | Topology-specific; [F31](SOURCES.md#f31), [F34](SOURCES.md#f34) |

Important exceptions: Bing grounding has separate terms and documented Azure
compliance/Geo-boundary implications; Fabric/Work IQ connections also require
cross-service review. CMK and private networking coverage vary; hosted/private
registry behavior can depend on project creation date. New-portal GA guidance
names an Entra-only set including evaluations, datasets, agents, workflows and
Content Understanding. Recheck the exact API, not merely a key-auth example.
[F17](SOURCES.md#f17), [F19](SOURCES.md#f19), [F50](SOURCES.md#f50),
[F02](SOURCES.md#f02), [F33](SOURCES.md#f33).

## 10. Adjacent Perception And Operational Services

Foundry Tools branding does not merge these services' APIs, costs, regions,
licenses or data-processing terms. Use them for a concrete AgentCraft workflow,
not simply because they appear in the catalog.

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| AX01 | Content Understanding: document/audio/video/image analyzers and structured fields | Adjacent Foundry Tools | Convert approved evidence into structured content; CU | Reuse existing recipe; replace custom extraction stages selectively | Conditional | Capability/API-specific; [F39](SOURCES.md#f39) |
| AX02 | Document Intelligence: OCR, layout/tables, prebuilt/custom extraction/classification | Adjacent Foundry Tools | Forms/manuals where native layout models fit; CU or new adapter | Complement CU; compare extraction/cost before selecting one owner | Conditional | Model/API-specific; [F40](SOURCES.md#f40) |
| AX03 | Speech: transcription, synthesis, translation and custom speech/voice | Adjacent Foundry Tools | Approved spoken evidence/accessibility; new capability | Replace speech pipeline plumbing | Conditional | Feature-specific; [F41](SOURCES.md#f41) |
| AX04 | Voice Live and voice-agent integration | Adjacent Speech / Native agents | Real-time spoken SME interaction; new capability | Complement text workflow; not required for current mission | Later | Feature-specific; [F41](SOURCES.md#f41), [F61](SOURCES.md#f61) |
| AX05 | Translator: text/document/custom translation | Adjacent Foundry Tools | Multilingual evidence/SME review; new capability | Replace generic translation stage, retain source text and provenance | Conditional | Feature-specific; [F42](SOURCES.md#f42) |
| AX06 | Azure Language: PII, language detection, extraction, summarization, CLU/Q&A | Adjacent Foundry Tools | Narrow NLP without a full agent call; new capability | Complement generative inference with specialized operations | Conditional | Feature-specific; [F70](SOURCES.md#f70) |
| AX07 | Azure Vision: OCR and image analysis | Adjacent Foundry Tools | Existing visual-document workloads only after lifecycle review | No default new dependency on retiring analysis variant | Watch | Image Analysis 4.0 deprecated; [F43](SOURCES.md#f43) |
| AX08 | Standalone Content Safety APIs | Adjacent Foundry Tools | Screen non-Foundry ingestion/output paths; LL, DATA extension | Complement Foundry filters without duplicating safety policy | Conditional | Feature-specific; [F44](SOURCES.md#f44) |
| AX09 | Healthcare AI models and domain-specific catalog offerings | Native catalog / specialized models | No current cyber/engineering mission requirement | No fit absent new domain, license and SME authority | Conditional | Model-specific; [F01](SOURCES.md#f01), [F80](SOURCES.md#f80) |
| AX10 | Supporting Search, Storage, Cosmos DB, ACR, Monitor, APIM and networking | Adjacent Azure infrastructure | Operate an approved hosted/knowledge pilot; DATA, DEP | Complement existing owners; not included free with Foundry | Later | Service/tier-specific; [F35](SOURCES.md#f35), [F34](SOURCES.md#f34), [P16](SOURCES.md#p16) |

## 11. Cost, Availability And Lifecycle

No price quote, tenant entitlement or numeric cloud capacity was verified here.
Availability intersects **model + version + API + deployment type + region +
cloud + identity + subscription quota**. A general feature page cannot establish
that intersection for a future target.

| ID | Feature / subfeatures | Class | Concrete AgentCraft use / owner | Simplification mechanism | Recommendation | Maturity; evidence |
| --- | --- | --- | --- | --- | --- | --- |
| LC01 | Model TPM/RPM, concurrency, file/token/job and agent resource limits | Native | Admission planning before pilot; CORE, LL, DEP | Complement local limits with provider limits | Now pilot | Target-specific; [F59](SOURCES.md#f59), [P04](SOURCES.md#p04) |
| LC02 | Evaluation regions, judge support, rate limits and VNet constraints | Native | Select eligible evaluation target; AO, DEP | Complement dataset/judge planning | Now pilot | Feature-specific; [P11](SOURCES.md#p11) |
| LC03 | Region/model feature matrices and sovereign-cloud differences | Native / Azure | Confirm a legal and supported target; DEP | Complement account planning, not automatic global availability | Now pilot | Matrix-specific; [F36](SOURCES.md#f36), [F78](SOURCES.md#f78) |
| LC04 | Model tokens, cache read/write, throughput reservations and batch meters | Native billing | Cost attribution per accepted change; LL, AO | Complement measured usage; avoid one blended token estimate | Now pilot | Model/deployment-specific; [F11](SOURCES.md#f11), [F35](SOURCES.md#f35), [F58](SOURCES.md#f58) |
| LC05 | Hosted compute, tool sessions, storage, search and connector meters | Native / Adjacent billing | Full worker cost estimate; DEP, CORE | Complement model cost; no free-hosting assumption | Now pilot | Service-specific; [P07](SOURCES.md#p07), [F35](SOURCES.md#f35) |
| LC06 | Evaluation/judge, red-team, optimizer and telemetry charges | Native / Adjacent billing | Bound repeated dev work and capture separate meters; AO | Complement external stop controls; estimates are not caps | Now pilot | Service-specific; [P23](SOURCES.md#p23), [P25](SOURCES.md#p25), [F27](SOURCES.md#f27) |
| LC07 | Cost Management budgets, alerts, scope and delayed usage reporting | Adjacent Azure | Detect spend trends after approval; DEP | Complement fail-closed execution budgets; alerts do not stop all work | Later | Billing scope-specific; [F35](SOURCES.md#f35) |
| LC08 | New/classic resource migration, SDK and Assistants lifecycle | Native / Classic | Avoid obsolete dependencies; LL, MA, DEP | Replace retired paths through measured migration, not aliases alone | Now pilot | Dated official migration claims; [F03](SOURCES.md#f03) |
| LC09 | Workflow and model retirement schedules | Native / Classic | Plan regression/replacement before unsupported APIs; MA, LL | Complement version pins with operational lifecycle | Now pilot | Workflow Preview/retiring; [F65](SOURCES.md#f65), [F37](SOURCES.md#f37) |
| LC10 | Known issues, release notes, notifications and SLA boundaries | Native / Azure | Requalify exact candidate against current limitations; DEP | Complement static documentation with dated checks | Now pilot | Mixed; [F38](SOURCES.md#f38), [F02](SOURCES.md#f02) |
| LC11 | CI/CD, private registries, rollout, resiliency and disaster recovery | Native / Adjacent | Exact-artifact deployment and recovery acceptance; DEP, REC | Replace selected hosting work, retain external read-back and restore tests | Later | Topology/feature-specific; [F56](SOURCES.md#f56), [P16](SOURCES.md#p16), [F34](SOURCES.md#f34) |

Observed migration guidance states an August 26, 2026 retirement/sunset for
`azure-ai-inference` and the Assistants API. Workflow documentation states a
December 1, 2026 retirement; Vision documentation states Image Analysis 4.0
retirement on September 25, 2028. These are **publisher claims observed on
2026-09-21**, not live cutoff tests or guarantees about future releases.
Classic Prompt Flow, hub-based projects and Azure ML paths remain migration/adjacent
considerations, not interchangeable names for new Foundry agents.
[F03](SOURCES.md#f03), [F65](SOURCES.md#f65), [F43](SOURCES.md#f43).

## Proposed Phases And Acceptance

**All phases below are proposed, NOT authorized.** No ready constitution, frozen
scenario revision, evaluator, budget, Azure target or SME acceptance exists yet.
Numerical pilot gates below are proposed experiment design, not a changed mission
metric or approved threshold.

| Phase | Small candidate | Proposed measurable acceptance | Prerequisites / refusal |
| --- | --- | --- | --- |
| 0: freeze a pilot | Select one concrete read-only task and named SMEs | Pin dataset/split, judge/rubric, artifact and authority; define effort attribution and accepted-change denominator before execution | New authorized increment; official availability/terms for exact region/model/API; permission to process selected data and incur bounded charges |
| 1: evaluation + tracing | Score already-recorded outputs; instrument one approved worker without hosting migration | Every submitted case has a result or explicit failure; identical case IDs/pins retained; trace/run linkage read back; no evaluator labels enter candidate inputs; matched authorized/denied paths; SME agreement and variance reported against pre-agreed thresholds | AO remains source of frozen controls/records; judge costs and telemetry retention separately authorized; uploaded payload review; external tracing preview considered |
| 2: hosted read-only worker | One MA definition/bundle, one narrowly allowed evidence tool | Exact local/container/service version identity; task/citation parity on frozen cases; cross-owner reads denied; forbidden tool/network action refused; stop/cancel/restart behavior observed; persisted output read back; cleanup settled | LL remote support absent, MA bundle compatibility not_verified; package availability, identity, region, private-network and Responses protocol checks required |
| 3: isolated development optimizer | One prompt or optimizer-ready Responses hosted worker with read-only tools | Approved configuration-only diff; independent untouched control run; retain failures and immutable candidates; report tool/model attempts and actual cost; stop limits verified; no score can offset a hard refusal violation | Preview acceptance; config loader validates allowed fields; dev data only; no arbitrary code/weights or production actions; external limits required where estimates are not caps |
| 4: knowledge / production operations | Only a demonstrated retrieval or operating gap | Relevant-retrieval/citation metrics, denied-user/ACL-change tests, latency and full cost measured; region/retention read-back; SME acceptance and restore test | Choose one retrieval owner; approve ingestion rights, source ACL propagation and adjacent-service costs; no automatic rollout |

Measure human, agent and tool effort separately, including setup, rework, failed
runs and cloud operations. Compare like-for-like accepted changes. With no accepted
changes, effort per accepted change is **undefined**, not zero. This research proves
neither savings nor improved domain quality.

## Coverage And Honest Gaps

| Required family | Coverage / source scan | Remaining action-changing uncertainty |
| --- | --- | --- |
| Project/resources/developer surfaces | PF; official TOC, capability reference/map, migration, SDK/CLI/Toolkit | Exact language/package compatibility and tenant/project availability not tested; classic hub migration details not exhaustively audited |
| Models/deployment/inference | MD; deployment/endpoints/router/modalities/cache/batch/region docs | No exhaustive per-model/version/license matrix, tenant quota or price quote; healthcare, Fireworks and every partner offering not independently piloted |
| Agent types/protocols/state/orchestration | AG; agent overview, hosted, sessions, workflow, state, MAF, approval, publishing/autopilot | Framework-language parity, reconnect/crash behavior and channel/trigger entitlements not tested; no assumption that framework workflows are service-native |
| Tools/connectors | TL; Toolbox, MCP/A2A/OpenAPI, web/files/code/browser/computer, skills/search/reminders | Individual connector catalog is open-ended; every connector/auth method not audited; Azure Functions/Logic Apps listed from official overview, not full API validation |
| Knowledge | KN; Foundry IQ, Search agentic retrieval, Fabric IQ, Work IQ and File Search | Source-specific ACL/sensitivity propagation and GA versus preview REST versions need exact-target check; legacy On Your Data paths not proposed as current default |
| Evaluation/testing | EV; built-ins/custom/targets/recorded conversations/traces/monitoring/datasets/human/red-team/simulation | Exact scheduled-evaluation API/cadence and all evaluator/model combinations unresolved; no judge calibration, runs or domain quality measurement |
| Optimization/tuning | OP; optimizer overview/costs/config/datasets/targets, prompt optimizer, tuning/DPO/RFT, Lightning | Distillation is a workflow candidate, not verified universal managed SKU; no optimizer run, billing cap test, model training or held-out comparison |
| Observability/governance | OB; tracing, monitoring, Control Plane, gateway and pricing | External-agent coverage, log completeness, exact alert rules, gateway tier/policies and licensing unverified |
| Security/privacy | SC; auth/network/CMK/privacy/guardrails/policy | No tenant inspection, negative live auth test, CMK coverage read-back, private routing, key/secret access or legal approval; government-cloud variants not exhaustively read |
| Adjacent services | AX; current official CU/DI/Speech/Translator/Vision/Language/Content Safety overviews | No full service model/API/container/region enumeration; Custom Vision/Face/Video Indexer and unrelated vertical products excluded pending concrete use/rights |
| Cost/quotas/lifecycle | LC; official matrices, limits, costs, migration/release/retirement references | No live capacity, negotiated pricing, subscription eligibility, actual bill, SLA/legal determination or migration execution |

The source set bounds comprehensiveness: official current navigation plus targeted
family references, not a claim to enumerate every future SKU. Navigation links and
search hits are discovery evidence only. A historical 404 remains retained; the
current release-notes route was successfully fetched. Limited excerpts preserve
provenance but do not reproduce entire documents. See [SOURCES.md](SOURCES.md)
for availability and acquisition limitations.

Out of scope: deployment, account inspection, credentials, paid calls, inference,
training, optimizer campaigns, private/held-out data, application/library changes,
irreversible operations and unapproved tenant changes. No dashboard or fabricated
metrics were created. Next decision belongs to overseer/user: approve and freeze
Phase 0/1, or revise the proposed shortlist.