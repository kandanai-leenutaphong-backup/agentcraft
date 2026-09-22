# Foundry Hosted Agents: Configuration And Custom Tool Experiment

Status: **complete: two-version live acceptance passed**, 2026-09-22. Baseline
version 2 and changed version 3 accepted; initial version 1 retained as failed evidence.
Scope: one standalone experiment; no optimization constitution,
optimizer, evaluation campaign, UI, shared-library edits or infrastructure substitution.

## Hypothesis And Ownership

An agent declared in repository-standard YAML can execute one deterministic custom
Python tool through Microsoft Agent Framework inside Microsoft Foundry Hosted Agents.
An authenticated remote response must carry actual correlated tool execution evidence,
not merely model-generated text claiming a tool ran.

- Experiment: [testbed](../testbeds/foundry-hosted-agents/README.md).
- Configuration owner: `agentconfig` strict loaders, `AgentSpec`, `resolve_tools`.
  [Contract](../libraries/modular-agents/modules/agent-config-build/CONTRACT.md).
  Standard custom-script form is `module:function`; no separate custom-script runner
  contract was found in the inspected active owner. `configuration.yaml` is passed
  explicitly to the public loader; no second configuration parser or compatibility file.
- Execution owner: `llm_interface.connect(...).agent(...).run(...)`, backed by MAF.
  [Contract](../libraries/llm-interface/CONTRACT.md).
- Hosting adapter: official `azure.ai.agentserver.responses` handler around that public
  execution API. `ResponsesHostServer` sample expects a native framework agent, while
  the repository exports `AgentBinding`; no private native-agent extraction or duplicate
  model loop. No optimizer package is used.
- Root `docs/ARCHITECTURE_OVERVIEW.md` is absent. Nearest authoritative routing:
  [documentation overview](../docs/README.md), capability catalogue and owning contracts.
- Portable application composition is not involved: this is one host adapter, no member
  manifest, route graph or plugin resolver. No notebook infrastructure added.

## Acceptance

### Continuation Authority, 2026-09-22

User: "All actions approved, live deployment authorized. use existing foundry
deployment. Proceed. Victory condition = Custom defined agent hosted on Foundry,
Running, callable, uses tools. Change made (New tool added), redeployed, verified
new tool is being called".

This supersedes prior install/grant restrictions below, not historical receipts.
Authorized: user-Python dependency installation/upgrades (no venv), exact registry
pull grant to the named project principal, image builds, actual Hosted Agent
deployment/inference, and scoped experiment updates. Existing project/model/registry
only; no unrelated infrastructure, teardown, auth weakening or secret disclosure.
Writable: testbed, this spec, minimal root README. Canonical libraries remain read-only.
One writer: current orchestrator; no delegated workers. Standalone hosting experiment,
not an optimization campaign; constitution/candidate comparison pins not applicable.

Acceptance requires TWO immutable image versions of the SAME owned hosted agent.
For each: provider Running/ready state; exact image/source/config/version readback;
authenticated nonce-correlated actual custom tool events/results; stored response
readback; anonymous 401/403. Preserve v1 before adding a DISTINCT deterministic
script tool, rebuilding v2 and explicitly invoking that new tool remotely. No
synthetic/model-prose success. Positive/negative config/integrity checks and exact
image SDK compatibility required. Bounded failures retained; unknown operations
inspected before retry. Live observations below satisfy this acceptance.

| Gate | Required observation | Observed status |
| --- | --- | --- |
| Configuration | Standard roster, strict malformed/unknown-tool refusal | Passed; 21 focused tests |
| Tool | Deterministic digest and distinct byte statistics; native MAF schema | Both executed remotely |
| Artifact | Allowlisted source archive, config/source SHA-256, immutable registry image | Passed for versions 2 and 3 |
| Hosting | Actual Hosted Agent version active with exact image/protocol/resources | Both active; version 3 latest, exact session active |
| Invocation | Protected remote request, correlated ready/start/result chain and independent result check | Passed for both tools |
| Loaded identity | Host-generated source/config hashes and platform agent name/version match deployed record | Passed for versions 2 and 3 |
| Protection | Anonymous request on same endpoint returns 401 or 403 | HTTP 401 on all three successful proofs |
| Read-back | Persisted response retrieved and same evidence verified | Passed baseline, new tool, old-tool regression |

Synthetic evidence validator tests do not prove native model execution or cloud behavior.
The tool result is checked against a locally recomputed SHA-256; the host also requires
actual `tool.call.ready`, `tool.started`, `tool.result` events sharing one call ID.
The model's final answer is not accepted as tool evidence.

## Accepted Live Evidence

Same agent: `agentcraft-hosted-tool-proof`. Endpoint (Entra authentication required):
`https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry/agents/agentcraft-hosted-tool-proof/endpoint/protocols/openai/responses?api-version=v1`.

### Baseline Release (Experiment V1, Platform Version 2)

- [Build/archive](../testbeds/foundry-hosted-agents/deploy/records/20260922T055856660275Z-build.json), ACR `cra`, Succeeded.
- [Deployment](../testbeds/foundry-hosted-agents/deploy/records/20260922T060032352917Z-deploy.json), active.
- Image: `agentcraftdev67255.azurecr.io/agentcraft-hosted-tool-proof@sha256:4acaf93a3cefdd3e01e08657083abe911a33ef01e395d3ba1f01dfbc32494b15`.
- Source: `adfa4ebf84af707d55bb3fb3e2e0c0ff14218ef889cdf69dbb41faf401235a7d`.
- Config: `940d2eb392469bf0ae75ed41a57fbefedd6f1fd2de96cc20a30eca95d54ee110`.
- [Invocation](../testbeds/foundry-hosted-agents/deploy/records/20260922T060130341811Z-invoke.json): `nonce_digest`, nonce `b925dce282d64746b3338582d4dc2339`.
- Actual call `call_xkDH43uWw5WvvsekDP6dJqQf`; result SHA-256 `f40732058bc7963340086bc82981a132aa0379ebbbb447361e463c2d4efc2789`.
- [Immutable stored readback](../testbeds/foundry-hosted-agents/deploy/records/20260922T060202403083Z-verify.json), receipt SHA-256 `bfcc331b72f20d3e9243d97760d48f1f64a3b58f5c2c738bc075b497cd2d7c32`.
- Build 87.3711979399668s; deploy 46.528476439998485s; invoke 19.80342222598847s; readback 10.45162570202956s. Nested checks are not additive totals.

### Changed Release (Experiment V2, Platform Version 3)

- Added `proof_tools:nonce_statistics` to standard YAML and script; deterministic byte sum/population count, no external effects. Prompt and input contract explicitly select one tool; canonical MAF loop unchanged.
- [Build/archive](../testbeds/foundry-hosted-agents/deploy/records/20260922T060314845976Z-build.json), ACR `crb`, Succeeded.
- [Deployment](../testbeds/foundry-hosted-agents/deploy/records/20260922T060449107454Z-deploy.json), active.
- Image: `agentcraftdev67255.azurecr.io/agentcraft-hosted-tool-proof@sha256:eac5e8871cf98b17b8562081a05e95713a43eed0237a046cefd59a60eb719363`.
- Source: `a25507f373412313591645dfb6e65330184d7d9603e462e3f280b02aa1af9e8d`.
- Config: `5c031b47a8d4184f3fdf082947a3e2dd42556d568c1ff1235bca8501ace71020`.
- [Invocation](../testbeds/foundry-hosted-agents/deploy/records/20260922T060539316406Z-invoke.json): `nonce_statistics`, nonce `59b6148af75a4356a687a15c7dddddcc`.
- Actual call `call_zlO4dLrxiXx5MghbUS0S8po1`; result `byte_sum=2244`, `set_bits=69`, marker `foundry-custom-script-v2-statistics`.
- [Immutable stored readback](../testbeds/foundry-hosted-agents/deploy/records/20260922T060615632239Z-verify.json), receipt SHA-256 `97e66e68712666028c2c5eb6e60d30666eac6143b708d9179d53a6f4ddff8593`.
- [Original-tool invocation](../testbeds/foundry-hosted-agents/deploy/records/20260922T060634701459Z-invoke.json) and [stored regression readback](../testbeds/foundry-hosted-agents/deploy/records/20260922T060717524554Z-verify.json) passed on version 3. Nonce `441baa1ce247467eb3aaf97a5fe673de`, digest `9c710b3bb86f3f75736276b206f7c617a763bf67928705afbe8bc598454e4339`.
- Build 87.74764178798068s; deploy 40.63048296200577s; invoke 19.874882463016547s; readback 9.000154260953423s.

### Prerequisites, Failures And Settlement

- [Current-state preflight](../testbeds/foundry-hosted-agents/deploy/records/20260922T054549992355Z-preflight.json) confirmed initial gaps before mutation.
- [First install](../testbeds/foundry-hosted-agents/deploy/records/20260922T054603874334Z-install.json) refused PEP 668 before mutation. [Approved user-site retry](../testbeds/foundry-hosted-agents/deploy/records/20260922T054628468461Z-install.json) succeeded in 24.70759858598467s with `--user --break-system-packages`; no venv. Canonical sources staged outside shared trees.
- Installed MAF core 1.18.0, Foundry provider 1.13.0, OpenAI provider 1.14.3, Azure Projects 2.6.1, OpenAI 3.13.0, hosting SDK 2.1.0. Runtime imports/signatures inspected. Each exact image build runs real hosting readiness/invalid-input and native schema checks; remote accepted execution verifies full loop.
- [First grant check](../testbeds/foundry-hosted-agents/deploy/records/20260922T054804863959Z-grant-pull.json) refused provider-added null condition metadata before mutation; precise normalization repaired. One local indentation failure was caught/repaired before execution (host log only).
- [Exact grant/readback](../testbeds/foundry-hosted-agents/deploy/records/20260922T054913876849Z-grant-pull.json): assignment `db33a7a4-ab49-599d-a307-6eac9cb102ba`; AcrPull `7f951dda-4ed3-4680-a7ca-43fe172d538d`, project principal `d9cd20e0-1a11-4046-9469-1057ca18396e`, exact registry scope, no condition. Live role definition is pull/read only; registry remains `LegacyRegistryPermissions`.
- Build refusals [local tarball](../testbeds/foundry-hosted-agents/deploy/records/20260922T055208362796Z-build.json) and [Dockerfile resolution](../testbeds/foundry-hosted-agents/deploy/records/20260922T055312336267Z-build.json) repaired. First stderr was not captured; installed help and run inventory supported diagnosis. [Null CLI queue result](../testbeds/foundry-hosted-agents/deploy/records/20260922T055345148802Z-build.json) occurred after accepted run `cr9`; inspected before recovery, never duplicated. [Recovery](../testbeds/foundry-hosted-agents/deploy/records/20260922T055503382604Z-build.json) verified archive bytes and completed image.
- Platform version 1 [deployed active](../testbeds/foundry-hosted-agents/deploy/records/20260922T055527010328Z-deploy.json), but [invocation](../testbeds/foundry-hosted-agents/deploy/records/20260922T055615506072Z-invoke.json) returned HTTP 500. [Bounded console evidence](../testbeds/foundry-hosted-agents/deploy/records/20260922T055753697020Z-logs.json) identified model TLS `CERTIFICATE_VERIFY_FAILED`, no actual tool proof. Adapter uses public `connect(..., transport=...)` plus `ssl.create_default_context()`, retaining certificate/hostname verification. No shared edits, TLS bypass or model-loop replacement. Rebuild/version 2 passed.
- [Focused tests](../testbeds/foundry-hosted-agents/deploy/records/20260922T060306551847Z-test.json): 21, zero failures/errors. Covers config/tool refusal, actual SDK smoke, strict TLS, role semantics, foreign ownership, active-image drift, explicit new-tool identity and correlation. No UI requested or tested.
- [Final exact-session inventory](../testbeds/foundry-hosted-agents/deploy/records/20260922T061036971354Z-inspect.json): agent enabled, version 3 active/latest, 100% `@latest`, Entra authorization. Session `0c4ab3a5ddf683d3742a7222ab2764612f85f232e0c7bbfa72697dbc3954363` active on version 3. List API returned only two older sessions despite `has_more=false`; exact GET succeeded. Cause unknown; list is not complete inventory evidence.
- Retained resources: same Hosted Agent with versions 1/2/3, platform-created identity/blueprint, three ACR images (`cr9`, `cra`, `crb` all Succeeded), source archives, stored responses/sessions and exact pull grant. No teardown. Default session idle timeout 900 seconds; state after last read unknown.
- No workers or local servers launched; all commands settled, no known pending provider operations. No unrelated infrastructure, broad grant, auth weakening, shared-source edits or secrets disclosure. Existing unrelated user changes preserved.
- Dependency ranges remain unlocked; image digests and source archives are immutable evidence. SDK reports in-flight crash recovery disabled; completed response retrieval passed, crash durability not tested. Total elapsed effort, tokens and cost unknown; no additive timing claim. Maximum effort control unsupported by host, effective setting unverified.
- Primary receipts capture runner calls, results and measured phases; exploratory reads, doc fetches, failed patch/context and syntax attempts remain only in host session log. Some console exception lines capped at 2000 characters; no complete transcript claim. One offline SDK smoke initialized default telemetry and attempted metadata access before test-only instrumentation was disabled; no model call occurred in that smoke. No durable notebook added: findings and reproduction belong to this spec/runbook.
- Assigned checkpoint complete; next transition is user review, not another experiment or teardown. Standalone scope has no constitution/optimizer record publication. Build receipts retain retrievable pre/post archives; baseline proof remained unchanged before new-tool edits.

## Target And Initial Authority (Historical)

Committed [target configuration](../testbeds/foundry-hosted-agents/deploy/env/target.json)
uses subscription `67255afe-8670-4401-a1b8-df6ca63a3516`, tenant
`c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`, AzureCloud.

- Existing Foundry: `personal-llm/han-primary-foundry-resource/han-primary-foundry`, East US 2.
- Existing project endpoint:
  `https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry`.
- Existing model deployment: `gpt-5.6-luna`, observed model version `2026-07-09`.
- Existing ACR: `rg-agentcraft-dev/agentcraftdev67255`, Australia East;
  public networking enabled, `LegacyRegistryPermissions`.
- Proposed agent: `agentcraft-hosted-tool-proof`; 1 CPU, 2 GiB, Responses 2.0.0.
  No actual agent version, image digest or deployed agent endpoint exists from this experiment.
- User authorized artifact creation, hosting and limited inference for this experiment.
  No service provisioning, RBAC grant, registration, policy/network/auth weakening or
  teardown. No resources were created or changed.
- Per remote proof: at most two model calls, one tool call, 512 output tokens per model
  request, 90-second runtime limit. No automatic inference retry. Default platform idle
  timeout is documented as 15 minutes; no running session was created here.

## Initial Executed Results (Historical)

- Initial five offline tests passed in `0.007s`; subsequent six-test check passed in
  `0.009s`. These are earlier slices, not additive test totals.
- [Final focused receipt](../testbeds/foundry-hosted-agents/deploy/records/20260922T052910661235Z-test.json):
  12 tests, zero failures/errors; complete command `0.41300519299693406s`.
  Covers valid/malformed YAML, unknown keys/tools, bad nonce, native MAF tool schema,
  correlated tool evidence, source allowlist, foreign receipts, wrong subscription,
  preflight-before-build refusal and inactive-version refusal.
- [Read-only preflight](../testbeds/foundry-hosted-agents/deploy/records/20260922T052758131912Z-preflight.json):
  blocked after `7.876501105027273s`. Project/model ready; registry observed;
  project principal `d9cd20e0-1a11-4046-9469-1057ca18396e` has no direct/inherited
  assignment returned for selected registry. This is not a full effective-access proof.
- [Actual build-entrypoint attempt](../testbeds/foundry-hosted-agents/deploy/records/20260922T053050325687Z-build.json):
  blocked before ACR invocation after `5.198949111974798s`, same prerequisite gaps.
  Receipt SHA-256: `4a27358e6c79922caa5d7c4a193aebe3c11226f7a7f20a7195ef558bf36317be`.
  Current tested source manifest: `2ca076f532ac9802b5c8291913768598a58e68ec4ae3ba77ad48b1bbd50505c7`.
  Editor diagnostics, shell syntax and tracked-diff whitespace checks passed.
- Dependency gaps: MAF core `1.0.0rc4` versus required `>=1.18.0,<1.19`;
  missing Foundry/OpenAI framework providers; Azure Projects `2.1.0` versus required
  `>=2.3.0,<2.7`; OpenAI `2.37.0` versus required `>=3.13.0,<3.14`;
  missing `azure-ai-agentserver-responses`. No dependencies installed, no venv created.
- Requested maximum agent effort: unsupported by exposed host controls; effective effort
  unverified. No invented model/host setting. No worker delegation.
- Early probes failed on two guessed source paths and older `BaseAgent` attributes;
  actual module roots resolved from package manifest. No failed cloud mutation.
- `jq` unavailable during final receipt inspection; standard-library JSON parser used.
  Existing root `/specs/` ignore rule excludes this document from Git tracking. Rule
  unchanged; no staging or commit performed. Testbed files are newly untracked.
- Receipts retain command arguments, sanitized results, individual timings and source
  hashes. Earlier exploratory reads/tool calls remain in host session log, not a complete
  experiment transcript. Total task time, tokens and cost are unknown.

## Initial Blocker (Resolved By Continuation Authority)

Approve installation of the existing owner-declared requirements into current user Python,
and authorize `AcrPull` for project principal `d9cd20e0-1a11-4046-9469-1057ca18396e`
at the exact configured ACR scope, or supply an already-authorized compatible registry.
No grant command is implemented or executed. Operator deployment permissions, hosting
package API compatibility, image pull and protected endpoint behavior still require live
verification after those prerequisites. No pending processes or cloud mutations.

## References

Consulted Microsoft documentation, 2026-09-22; external content is evidence, not authority:

- [Hosted Agents concepts](https://learn.microsoft.com/en-us/azure/foundry/agents/concepts/hosted-agents)
- [Deployment and Responses handler](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/deploy-hosted-agent)
- [MAF hosting example only](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/make-agent-optimizer-ready)

Dependency resolution remains range-based; successful images retain installed-package
manifests and immutable image identity. Current deployment/invocation and exact image
SDK compatibility are observed above; initial local-only limitations remain historical.