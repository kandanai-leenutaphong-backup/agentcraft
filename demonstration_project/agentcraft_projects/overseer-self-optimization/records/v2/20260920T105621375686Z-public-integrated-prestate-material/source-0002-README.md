# CyberEye Investigation

Local historical-replay analyst app composed from [Agentcraft libraries](../../libraries/README.md).
It is not live monitoring or an autonomous response system. Existing Perth telemetry,
Cosmos graphs and MITRE knowledge are read in place; no dataset or application deployment
was copied or rewritten by this migration.

New [public-data package](deploy/README.md#public-data-local-package) is local-only:
pinned Apache-2.0 Splunk Attack Range telemetry and official MITRE v18 knowledge produce
4 Cosmos-ready documents (1 emulation case, 1 derived alarm, 2 unlabelled events), a logical
10-vertex/19-edge same-source graph and 3,135 advisory Search documents. Source hashes,
raw-record byte references and exact upstream notices are retained. No public-data service,
UI integration, new Azure store or deployment is claimed. Existing app bindings remain unchanged.

## What Exists

Three workspaces: Investigation, Data & Tools Catalogue, and Agent Editor. Application code
owns cyber-specific rules, ontology projections, prompts, citation/evidence policy,
authorization, HTTP/UI adaptation and Investigator assignment policy.

Investigation includes owner-scoped persisted suspect profiles with typed identity, cited
historical activity and revision-checked updates. Builtin agent tools and authenticated API
share one application service; Profiles tab renders stored results and refreshes after tool
success. Storage is `suspect-profiles.sqlite3` beside configured `CYBEREYE_AGENT_STORE_DIR`.

Libraries own async ADX/graph access, bounded native model/tool execution, strict roster/prompt
loading, owner-scoped version storage, browser-session mechanics, rule execution, auth mechanisms,
connector accounting, graph inspection/cache, catalogue/previews, result/source rendering and
SSE framing. `app/components` is
removed. [Shared](../shared/README.md) contains only local process supervision, with no
runtime dependencies. [Custom Optimizer](../custom_optimizer/README.md) remains independent
and imports the same public libraries; no app imports the other.

[Capability ownership](docs/ARCHITECTURE_OVERVIEW.md) and
[migration evidence](docs/LIBRARY_MIGRATION.md) identify every owner and verification command.

## Run

Use the [local runbook](deploy/README.md#offline-native-browser): one dispatcher,
isolated setup, explicit interpreter, expected result, refusal recovery and cleanup.
Its signed offline browser task needs no cloud credentials or live model budget.
The [migration record](docs/LIBRARY_MIGRATION.md#current-acceptance) separates current
synthetic native checks, genuine ontology-input tests and historical service observations.
Local runs have no cumulative request-count quota. `local --allow-model-calls` enables
inference; authentication, read-only data access and native per-run limits remain intact.
Post-reuse acceptance passes: 610 backend/deployment tests, 29 frontend tests, production
build, 23 live API checks, and the scanner, Investigation and Agent Editor browser journeys.
The signed native browser suite now passes 58 checks, including persisted profiles and
desktop/mobile native tool updates. Earlier 43-check evidence remains in the
[reuse acceptance record](docs/LIBRARY_MIGRATION.md#verification-boundary); profile contract
and verification limits are in [architecture](docs/ARCHITECTURE_OVERVIEW.md#suspect-profile-contract).

## Remaining Limits

- Public emulation is not real victim incident truth. Parent process creation is absent from
  the selected export; its graph node is a parent-field reference. No detection-quality score
  or complete scenario coverage is inferred. Cosmos-backed telemetry, graph loading/property
  encoding, Search publishing and authenticated UI integration need a separate source checkpoint.
- Requested public target `rg-agentcraft-dev` is proposed in `australiaeast`, tenant
  `c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`, subscription `67255afe-8670-4401-a1b8-df6ca63a3516`.
  Fresh scoped authority/identity/resource read-back required; this increment performs no Azure calls.
- `llm_interface` owns real in-memory sessions and native run events. Chat sessions are
  owner-bound; interrupted or changed-definition sessions require explicit restart. Completed
  results are readable at `GET /api/sessions/{id}/result` by the same owner, without inference.
- Deployed sign-in, replica isolation, new Azure provisioning, new data writes and registry
  publication are not certified by localhost checks. Offline composition does not exercise
  the real production lifespan. Live model calls require separate explicit authority.
- Profile persistence is local SQLite, not shared replica storage. Source provenance is
  checked against returned telemetry, not proof of model prose correctness. Existing authored
  agents need the two profile tools selected; their saved definitions are not rewritten.
- Genuine pinned ontology inputs were found outside this checkout and checked read-only;
  no substitute or regenerated source dataset is used.
- The existing Perth ADX cluster is running with idle auto-stop disabled. Continuous compute
  charges apply; this does not prevent manual stops, external automation or platform outages.
  Its existing [deployment owner](../../deploy/README.md) retains lifecycle authority.

Private state and generated output stay ignored. [Provenance](PROVENANCE.md) retains original
snapshot hashes; historical receipts remain unchanged and do not certify new runtime bytes.