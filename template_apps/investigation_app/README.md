# CyberEye Investigation

Local historical-replay analyst app composed from [Agentcraft libraries](../../libraries/README.md).
It is not live monitoring or an autonomous response system. Existing Perth telemetry,
Cosmos graphs and MITRE knowledge are read in place; no dataset or application deployment
was copied or rewritten by this migration.

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