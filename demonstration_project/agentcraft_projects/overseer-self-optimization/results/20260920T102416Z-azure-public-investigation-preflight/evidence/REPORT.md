# Azure Public Investigation Preflight

Status: **blocked for execution; READ/PLAN checkpoint complete with capture gaps**.
Non-authoritative worker evidence. No deployment or comparative-improvement claim.
Effort requested: max. Effective runtime effort: unverified. Cost: UNKNOWN.
Directory timestamp was observed using `date -u`: `20260920T102416Z`; individual
read timestamps and elapsed time were not captured reliably.

## Pins And Authority

- Workspace: `/home/hanchoong/agentcraft`.
- Project: `demonstration_project/agentcraft_projects/overseer-self-optimization`.
- Constitution revision 7, SHA-256
  `b2b59aebc22e8205f66586ca18d8c0aa8efcd60ab05465816806606ed04487ff`, matched by `sha256sum`.
- Candidate `.github/agents/local-dev-test-subject.agent.md`, observed SHA-256
  `d8b91ecba9338f0a0d9c1b3ec3bcce6ab548bc440c228de1ce7e1d215ec0eef0`.
  Not invoked, no loaded candidate/runtime identity claimed.
- Current assignment permits read/plan and new evidence files only. User's proposed
  deployment is not authority for tenant registration, grants, secret handling,
  public-network changes, policy exemptions, ingestion or model execution now.
- Rev7 explicitly limits mission execution to local discovery. Overseer must revise
  constitution, name cloud/data/model levers and restoration, validate it, and obtain
  archivist pre-change receipt before implementing or executing the new stage.
- No archival checkpoint was supplied for this new stage. Historical rev7 references
  were read, not independently verified or reused as new-cloud authorization.

## Observed Target

| Field | Observed value |
| --- | --- |
| Subscription | `67255afe-8670-4401-a1b8-df6ca63a3516` |
| Tenant | `c79ab2bb-79cb-47f1-b4da-b6852fe45ff7` |
| Cloud / state | `AzureCloud` / `Enabled` |
| Requested RG | `rg-agentcraft-dev` |
| Exact RG ID | `/subscriptions/67255afe-8670-4401-a1b8-df6ca63a3516/resourceGroups/rg-agentcraft-dev` |
| Existence | Marked `az group list` returned `[]` for exact name |
| Contents | Explicit-subscription `az resource list -g rg-agentcraft-dev` returned `ResourceGroupNotFound`, exit 3 |
| Provider status | Microsoft.App, DocumentDB, Search, ContainerRegistry, Storage, ManagedIdentity, CognitiveServices, KeyVault all `Registered` |
| Advertised locations | Relevant account/service/app/environment/registry/storage/identity/vault types all report Australia East and East US 2 |

No existing group to adopt at observation time. Repeat exact-name, ownership and
contents checks immediately before creation; this read is not a reservation.

Recommended region: **australiaeast**, matching app's non-secret isolated planning
configuration. `eastus2` is also advertised and matches root testing-group history.
Neither is proven cheaper, policy-compatible or SKU/quota-admissible. Quotas,
global-name availability, permissions, deny assignments, inherited locks and policy
remain UNKNOWN. Region advertisements are not SKU capacity reservations.

## Proposed Frozen Mutation Set

Proposal only. All names unreserved. `RG` below expands to the exact full RG ID above;
each resource ID is `RG/providers/` plus the suffix. One owner: root `deploy/`.
Initial tags: `managed-by=agentcraft-deploy`, `capability=agentcraft`,
`purpose=public-investigation-dev`, `data-policy=public-approved`,
`lifecycle=explicit-teardown`. Add project and approved expiry through reviewed schema.
Propose 24-hour initial pilot lifetime; this is not an existing user-imposed bound or
automatic expiry guarantee. Explicit cleanup authorization remains separate.

| Proposed suffix / name | SKU and configuration | Purpose |
| --- | --- | --- |
| `Microsoft.DocumentDB/databaseAccounts/cosmos-agentcraft-dev-nosql-67255` | GlobalDocumentDB, EnableServerless, one region, Session consistency, no analytical store | Public telemetry, incidents, alarms and app state |
| `Microsoft.DocumentDB/databaseAccounts/cosmos-agentcraft-dev-gremlin-67255` | GlobalDocumentDB, EnableGremlin + EnableServerless, one region | Graph derived from exactly the same attack records |
| `Microsoft.Search/searchServices/srch-agentcraft-dev-67255` | Basic, one partition, one replica; Entra data auth | MITRE document retrieval |
| `Microsoft.ContainerRegistry/registries/acragentcraftdev67255` | Basic; admin disabled; MI pulls | Versioned application images |
| `Microsoft.App/managedEnvironments/cae-agentcraft-dev` | Consumption workload profile | New dedicated runtime environment |
| `Microsoft.App/containerApps/ca-agentcraft-investigation` | 0.5 vCPU, 1 GiB, min 0/max 1, Single revision, HTTPS; ingress closed until auth verified | Existing Investigation source, production entry point |
| `Microsoft.ManagedIdentity/userAssignedIdentities/id-agentcraft-dev-app` | User-assigned | Pull and app data access |
| `Microsoft.Storage/storageAccounts/stagentcraftdev67255` | StorageV2, Standard_LRS, HTTPS only, shared-key and blob-anonymous access disabled | Azure Tables for session/flow/replay state |
| `Microsoft.KeyVault/vaults/kv-agentcraft-dev-67255` | Standard, RBAC, protected secret references | Gremlin credential delivery, only after explicit approval |

No ADX, new model account/deployment, Log Analytics workspace, public blob content,
second application, VM, premium compute, private endpoint or VNet included. Platform
logging omission needs provider validation; application logs must exclude payloads and
credentials. Networking changes are not silently added if policy rejects this proposal.

Child resources proposed under above parents:

- NoSQL `/sqlDatabases/publiccyber/sqlContainers/{telemetry,incidents,alarms}`,
  partition `/scenario_id`; `/sqlDatabases/publiccyber/sqlContainers/application-state`,
  partition `/owner_id`. Every document has deterministic ID and provenance. Final
  partition/index policy follows bounded public-data profiling, not assumed incident truth.
- Gremlin `/gremlinDatabases/publiccyber/graphs/attackgraph`, partition `/scenario_id`;
  vertex/edge IDs derived from same source revision/scenario/record IDs as NoSQL.
- Search data-plane index `mitre-attack`, lexical BM25 first; no embeddings, semantic
  ranker or model-backed indexer required for initial baseline. Preserve ATT&CK IDs,
  source URL/revision, license/attribution and provenance fields used by existing retrieval.
- Storage `/tableServices/default/tables/browserauth` and
  `/tableServices/default/tables/devauthreplay`.
- Key Vault secret objects `gremlin-readonly` and, only for authorized ingestion,
  `gremlin-ingest`. Secret values never enter this evidence, CLI output, Git or image.
- Scoped role assignments and Cosmos SQL data-role assignments listed below; exact
  assignment GUIDs depend on new principal IDs and frozen target configuration.

Low-idle-cost baseline, **not a retrieved price quote**: serverless Cosmos avoids
fixed provisioned-RU reservations for sparse use, subject to SKU/region approval and
actual workload. If serverless is unavailable, evaluate manual 400 RU/s per account's
single database/container arrangement; do not silently enable autoscale or assume
free-tier eligibility. Shared-throughput/container eligibility must be validated.
Search Free is a cheaper development alternative only if subscription slot is free,
corpus fits 50 MB/three-index constraints, and required features are supported. Those
facts were not established, so Basic is the credible default; one replica gives no HA
claim. Search/ACR/storage retain costs while Container App scales to zero. Quotas,
request units, load volume, transfer, secret operations and model charges are UNKNOWN.
Do not deploy idle services before source and access blockers are resolved.

## Identity And Approval Matrix

Workload identity, analyst identity, deploy operator and signed candidate are distinct.
Proposed grants require explicit target-bound approval; deployment intent is not grant
authority. No broad Contributor/Owner/UAA assignment or tenant-wide consent proposed.

| Principal / exact target | Proposed permission | Approval / remaining evidence |
| --- | --- | --- |
| Existing deploy operator / subscription RG-create scope, then named RG | Resource creation/update for frozen providers, deployment validation/build/release | Operator object ID and effective permissions UNKNOWN; inspect, do not self-grant |
| `id-agentcraft-dev-app` / named ACR | `AcrPull` | Explicit registry-scoped role assignment; read back principal and scope |
| App MI / NoSQL telemetry, incidents | Cosmos SQL Built-in Data Reader at corresponding container scopes | Separate Cosmos data plane, not ordinary ARM Reader; include metadata permission |
| App MI / NoSQL alarms, application-state | Cosmos SQL Built-in Data Contributor at corresponding containers | Needed writes must be mediated by owner-aware application service; candidate gets no direct MI credential |
| Authorized ingest identity, not app analyst / three public NoSQL containers | Cosmos SQL Built-in Data Contributor | Principal UNKNOWN; grant only after acquisition/ingestion plan and source rights approved |
| App MI / named Search service | Search Index Data Reader | Index-specific scope if supported and verified; otherwise isolated single-purpose service scope |
| Approved ingestion identity / named Search | Search Index Data Contributor; Search Service Contributor only for index/schema operations if needed | Keep index management separate from query runtime |
| App MI / each named auth table | Storage Table Data Contributor | Tables created by deployment owner; verify atomic claim, expiry and refusal across restart |
| App MI / `gremlin-readonly` secret | Key Vault Secrets User at approved narrow scope | MI resolves platform Key Vault reference; app receives runtime secret only, never logs it |
| Approved ingestion identity / `gremlin-ingest` secret | Separate Key Vault access | Graph writes need separately authorized credential provisioning; no read-key escalation |
| App MI / approved existing model account | Cognitive Services OpenAI User, if correct for confirmed endpoint | Model resource ID, allowed deployment, principal and reuse approval UNKNOWN |
| Human callers / single-tenant registration | API delegated scope and assigned analyst access | Registration/client/object IDs, approved auth tenant, callback and consent UNKNOWN |
| Candidate / application signed boundary | Existing approved public-key fingerprint and application authorization | Private key stays with signing client; no new key or service-principal admission by default |

Resource tenant above is observed; it does not automatically choose analyst tenant.
Propose same-tenant analyst access subject to confirmation. Do not reuse historical
writeup's corporate tenant or implicit ID-token flow. Current Investigation supports
browser-side code redemption with PKCE, SPA callback `/auth/callback`, validated API
access token and secure opaque server session. It explicitly disallows service
principals in `build_entra_config`; keep that refusal. New registration or changes to
existing callbacks/audiences/scopes/consent require separate directory approval.
Choose exact sign-in contract and assigned callers before exposing ingress.

Preserve unconditional in-process gate, owner checks, tenant/audience/expiry checks,
CSRF, private/no-store, browser flow state and shared Azure Table replay ledger. An
optional platform gate must not obstruct approved signed requests or replace the
application authorization decision. No anonymous analyst API, bypass header,
auth-disabled copy or in-process replay substitute. One replica does not protect
against replay across restarts or revision overlap. Test anonymous assets/unknown
routes as well as APIs, forged principal, wrong tenant, expired/tampered/replayed
signatures, foreign-owner reads/writes, logout and real positive sign-in.

Current Gremlin host binding calls ARM `list_read_only_keys` with borrowed identity.
Do not label it Entra-authenticated traversal. Recommended new deployment replaces
that acquisition with approved Key Vault-reference delivery to the existing explicit
read-only-key provider contract. Provisioning those secrets is a separate protected
operator/platform action, never a secret-fetch shell command. An external scoped
resource-token authority is another design, not an existing implemented grant.
Graph ingestion including edges and idempotent read-back is not demonstrated by the
read-only app binding; extend existing public connector contracts only where needed.

Public service endpoints are proposed for isolated public-data dev only if policy
permits, with service auth required. If policy forces private networking, stop and
rescope network/egress/cost rather than request an automatic exemption. Relevant
historical warning: a Gremlin private endpoint can make public WSS access fail even
with `publicNetworkAccess=Enabled`. A PE is not workstation reachability; verify
from intended Container App network. No PE or policy assertion was reverified here.

## Source Feasibility And Owners

| Finding | Exact existing owner | Consequence |
| --- | --- | --- |
| Root sole dispatcher has RG, live, ADX, retirement; writeup refuses | `deploy/deploy.sh` | Add root `investigation` branch and one root runner/IaC, not second infra owner |
| App cloud runner pins different RG and returns blocked; apply/verify/teardown refuse | `template_apps/investigation_app/deploy/cloud.py` | Do not repurpose old isolated authorization as grant for new RG |
| Production validates ADX endpoint and builds ReadOnlyAdx/Scanner | `template_apps/investigation_app/app/cybereye/backend/{main.py,config.py,data/adx.py}` | NoSQL requires app-owned telemetry queries and detector/tool adaptation, not endpoint swap |
| Shared Cosmos connector exists with explicit partition, Cosmos SQL and conditional writes | `libraries/azure-data-connectors/CONTRACT.md` | Reuse `azdata.connect('cosmos', ...)`; app dependency currently lacks `cosmos` extra |
| Profiles persist local SQLite, owner/revision enforced | `template_apps/investigation_app/app/cybereye/backend/agents/profiles.py` | Implement durable same-owner/version semantics with NoSQL ETag; no naive Blob mirror |
| Agent library delegates filesystem authoring to public AgentVersionStore | `template_apps/investigation_app/app/cybereye/backend/agents/{library.py,editor.py}` and `libraries/modular-agents/` | Extend existing store boundary after exact implementation-owner discovery; preserve immutable versions and assignment CAS |
| Frontend build script `tsc -b && vite build`; local packages referenced | `template_apps/investigation_app/app/cybereye/frontend/package.json` | Build from repository-relative library inputs and npm lock; existing dist is not current-build proof |
| No Dockerfile or .dockerignore found by targeted file search or app/deploy root listings | app and root deployment inputs | Need reviewed root-owned image recipe/context allowlist; no release-ready image proven |
| App architecture manifest omits cloud.py/cloud tests from named exact deployment paths | `template_apps/investigation_app/architecture.json` | Declare actual ownership during integration; root ARCHITECTURE_OVERVIEW.md is missing |

Prefer durable application-state contract backed by the already proposed NoSQL
account over adding a speculative filesystem service. Preserve profile revision
conflicts and owner partition checks; immutable agent-version save plus assignment
compare-and-swap must remain atomic at the appropriate partition boundary. Public
telemetry is not private user state. Keep evaluator-only labels and held-out data
outside candidate-visible containers/indexes/tools. Rewriting storage is routine
authorized-design work after a new assignment, not a request to weaken semantics.

Model configuration lead, read only from allowlisted non-secret fields:
`https://han-primary-foundry-resource.openai.azure.com/openai/v1/`, deployment
`gpt-5.6-luna` in `deploy/env/existing-perth-m1.env`. No successful account/deployment
read-back obtained. This is **not verified availability or approval to reuse**.
No Perth/customer datasets, existing graph/Search content or credentials were read
or copied. Do not source that environment wholesale into the new deployment.

Data preparation must use separately approved public attack/telemetry sources plus
MITRE material with pinned revisions and license notices. No acquisition or ingestion
in this assignment. Derived incidents/alarms must distinguish detector output from
ground truth; network-flow labels do not establish incident narratives. Graph is
derived from the same normalized public records, not copied Perth ontology payloads.

## Root Entry Point And Tests

Future root owner proposal, not implemented commands:

```text
bash deploy/deploy.sh investigation plan --config deploy/env/agentcraft-dev.json
bash deploy/deploy.sh investigation preflight --config deploy/env/agentcraft-dev.json
bash deploy/deploy.sh investigation deploy --config deploy/env/agentcraft-dev.json --confirm <exact-RG-ID>
bash deploy/deploy.sh investigation verify --config deploy/env/agentcraft-dev.json
```

Add `deploy/investigation.py`, `deploy/infra/investigation.bicep`,
`deploy/env/agentcraft-dev.json`, `deploy/Dockerfile.investigation`, a root build-context
allowlist and `deploy/tests/test_investigation.py` only in future authorized work.
Reuse RG ownership checks; do not turn empty-group teardown into recursive deletion.
Keep app-local launcher for local work; app-local cloud planning should route to root
owner or refuse with root command rather than provisioning independently. Retired
writeup runner is a design/test lead, not an authorized live implementation to call.

Existing test anchors: root `deploy/tests/test_resource_group.py` covers wrong target,
permission refusal, owned repeat/no retag and non-empty teardown. Root
`deploy/tests/test_writeup.py` covers protected ingress, callback preservation,
missing-key refusal and closure after failed edge verification. App
`deploy/tests/test_cloud.py` covers zero mutations and target validation; it does
not prove a runnable image or provision services. Tests involving temporary files
were not run because this assignment allows evidence writes only.

Future focused checks: fake CLI wrong-account/collision/grant refusal; frozen
inventory drift; omitted secret/name/callback refusal; private-first ingress;
NoSQL positive read/write plus stale revision/foreign-owner refusal; immutable
authoring and restart durability; graph source-ID parity/read-back; Search source
count/provenance; real SPA sign-in and signed access through edge. Build exact
production `app.cybereye.backend.main:app`, not `local_app`. Build backend locked
dependencies plus frontend; verify all Docker COPY inputs and exclusion of `.env`,
`.local`, datasets, existing artifacts and private source configuration. Container
Apps/ACR server-side builds avoid needing a local Docker daemon but require approval.
Current frontend node_modules/dist exist; installed versions, actual build result,
Docker tooling and production lifespan are UNKNOWN. No environment/install/build run.

## Snapshot Before Implementation

`preflight.py:SNAPSHOTS` names exact existing core paths and can report their current
digests without writing. Additional required files before changing corresponding slice:

```text
template_apps/investigation_app/architecture.json
template_apps/investigation_app/README.md
template_apps/investigation_app/app/cybereye/backend/agents/library.py
template_apps/investigation_app/app/cybereye/backend/agents/tools/base.py
template_apps/investigation_app/app/cybereye/backend/agents/tools/activity.py
template_apps/investigation_app/app/cybereye/backend/agents/tools/evidence.py
template_apps/investigation_app/app/cybereye/backend/agents/tools/scanner.py
template_apps/investigation_app/app/cybereye/backend/api/data_sources.py
template_apps/investigation_app/app/cybereye/backend/api/scanning.py
template_apps/investigation_app/app/cybereye/backend/security/entra.py
template_apps/investigation_app/app/cybereye/backend/security/signin_routes.py
template_apps/investigation_app/app/cybereye/tests/test_suspect_profiles.py
template_apps/investigation_app/app/cybereye/tests/test_agent_library.py
template_apps/investigation_app/app/cybereye/tests/test_agent_editor_api.py
template_apps/investigation_app/app/cybereye/tests/test_detector_engine.py
template_apps/investigation_app/app/cybereye/tests/test_tool_query_binding.py
template_apps/investigation_app/app/cybereye/tests/test_entra_signin.py
template_apps/investigation_app/app/cybereye/tests/test_auth_session_hardening.py
template_apps/investigation_app/app/cybereye/tests/test_authorization_gate.py
template_apps/investigation_app/app/cybereye/tests/test_signed_access_integration.py
template_apps/investigation_app/app/cybereye/tests/test_async_graph.py
template_apps/investigation_app/app/cybereye/tests/test_azdata_migration.py
template_apps/investigation_app/app/cybereye/tests/test_knowledge_search.py
README.md
demonstration_project/README.md
```

Snapshot only sanitized source/config/lockfiles from working tree, not presumed HEAD.
New planned paths need recorded nonexistence before creation. Root `.dockerignore`
existence was not checked; inspect and snapshot before editing. Exact native
AgentVersionStore implementation under modular-agents still needs targeted discovery
before assigning writes there; guessed `libraries/modular-agents/src` did not exist.
Do not snapshot installed environments, state databases, credentials, private datasets
or all library directories. `sha256` is identity, not a backup; archivist must retain
actual approved bytes and receipt, including dirty changes, before implementation.

## Commands, Failures And Capture

Terminal outputs intermittently belonged to unrelated concurrent work. Rejected
outputs included public-source web fetches and a webscrape traceback; they are not
Azure errors, this worker's acquisitions, or useful evidence of command execution.
Calls all requested sync mode with finite command bounds. No asynchronous terminal
handle returned. No poll/sleep or retry of any mutation occurred.

| Attempt | Result trusted for this assignment |
| --- | --- |
| `az account show` first attempt | Capture contaminated by unrelated source grep; outcome UNKNOWN |
| `date -u +%Y%m%dT%H%M%SZ` | `20260920T102416Z` |
| `git status --short --untracked-files=no` | Existing changes: root/demonstration README, constitution, notebook lessons, datasets.sh, explore_data.py, test_datasets.py; untouched |
| `sha256sum <constitution> <candidate>` | Both exact digests above |
| Marked account retry | Expected subscription/tenant/Enabled/AzureCloud |
| `az group show ... rg-agentcraft-dev` | Unrelated web-fetch capture; outcome UNKNOWN |
| Marked exact-name `az group list` | Empty groups array |
| `az resource list ... -g rg-agentcraft-dev` | ResourceGroupNotFound, exit 3 |
| Provider list first attempt | Unrelated webscrape error capture; outcome UNKNOWN |
| Marked provider retry | Eight providers registered; two regions advertised as above |
| Cognitive account list and retry | Both unrelated capture, including retained JSON of another task; model availability UNKNOWN |
| `python3 -B .../preflight.py --help` | Correct argparse help, successful syntax/interface check |
| `timeout 240s python3 -B .../preflight.py --azure`, relative then absolute path | Both returned unrelated web payloads; execution/quotas/package inventory UNKNOWN |
| Editor diagnostics for preflight.py | No errors found |
| Final relative-path evidence `sha256sum` | Both paths not found from terminal working directory; not evidence files absent |
| Absolute-path evidence `sha256sum` | Both files read successfully; script digest `69dbacc953d17c251d59bacb096d6f8e4644b54b3ef069411fda56cf42467b35`; final report digest supplied in return packet |

Source reads used file/search tools. Missing paths: root
`docs/ARCHITECTURE_OVERVIEW.md`, guessed security/browser.py and
libraries/modular-agents/src. Browser owner corrected to security/signin_routes.py
and security/entra.py. No cloud denial or missing credential was established by
the contaminated calls. No recorded build/test success beyond script CLI/diagnostics.

Reproducible metadata-only command, no output file writes:

```bash
timeout 300s python3 -B demonstration_project/agentcraft_projects/overseer-self-optimization/results/20260920T102416Z-azure-public-investigation-preflight/evidence/preflight.py --azure
```

This script enforces rev7 digest and active target before further Azure reads;
further cloud reads refuse if pins differ. `--azure` makes account/group/inventory,
Search/model metadata and candidate quota-API GETs, never provider registrations,
tokens/keys, login/context changes, ingestion or inference. Quota API rejection or
missing pagination is UNKNOWN, not zero quota. Current script queries generic
regional usage, not exhaustive service-specific capacity. It is evidence tooling,
not another deployment owner. Future approved implementation must put operational
preflight into root deployment owner, not depend on this historical evidence path.

## Handoff

- Hard execution/authority blockers: rev7 local-only pin; no new pre-change archive;
  no approved analyst registration/caller set; no approved data/RBAC/graph credential
  grants; no confirmed authorized model target for live loop.
- Concrete technical release blockers: mandatory ADX path, ephemeral SQLite/authoring
  persistence, absent image recipe/release runner, unverified production sign-in and
  Gremlin secure binding/ingestion. These are implementable, not reasons to invent
  new user approvals for routine design after scoped authorization.
- Unknown external facts: quota, current pricing, policy/denies/locks, global names,
  operator principal/effective permissions, model deployment state and entitlement.
  Terminal capture is a tooling blocker, not evidence that Azure is inaccessible.
- Only changed files: this REPORT.md and preflight.py in authorized evidence directory.
  No authority record, constitution, app or deployment source changed by this worker.
- Resource settlement: zero mutations requested by this worker; no owned cloud resource,
  service, key, process server or teardown. Workers: none dispatched. All terminal
  tools returned synchronously; actual completion of contaminated calls remains
  unverified, and no background handle was supplied. Underlying probes are read-only
  and bounded; cannot claim complete process telemetry.
- Capture gaps: full per-read/tool timestamps, aggregate effort/cost and complete raw
  command receipts unavailable. Evidence paths read back by absolute-path hashing. Host transcript is primary
  call record, not independently exported here. No authoritative archive published.
- Next transition: overseer reviews this plan, revises/validates constitution and
  obtains archivist snapshot receipt, resolves exact access/credential approvals,
  then assigns one implementation slice. No automatic experiment or deployment.