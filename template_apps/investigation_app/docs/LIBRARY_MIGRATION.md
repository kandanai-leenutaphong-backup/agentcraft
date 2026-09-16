# Library Migration

Bounded source migration from baseline `00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`.
Parent-owned connector/model libraries, graph/agent service implementations, root deployment,
browser guards, state, credentials and immutable receipts are protected. No new data,
provisioning, inference, grants, network changes or authentication changes are authorized.

## Current Owners

| Outcome / Decision | Public Owner And Retired Source | Consumers, Contract And Check |
| --- | --- | --- |
| Ordered rule execution / extract | `libraries/situation-detector`, `situation_detector`; removed `shared/src/template_foundations/situation_detector` | Investigation scanner and Custom Optimizer joint evaluation; injected callbacks, deterministic digest, bounded window, failures remain errors; original battery suite moved to library |
| Human token and PKCE primitives / extract | `libraries/entra-auth`, `entra_auth`; removed `app/components/entra_auth` | Host security/sign-in adapters retain authorization, routes and cookies; tenant/expiry/key and session negatives preserved |
| Signed caller verification / extract | `libraries/signed-dev-access`, `signed_dev_access`; removed `app/components/signed_dev_access` | Same host gate; raw-byte signature, replay, tamper, expiry and size refusals preserved; no runtime dependency on Entra |
| Catalogue and bounded previews / extract | `libraries/resource-explorer`, `resource_explorer` and `resource_explorer.content`, `@agentcraft/resource-explorer`; removed `app/components/resource_explorer` and generic content implementation | App inventory/agent editor and injected probes; no duplicate service transport; selection, status and bounded-content contracts unchanged |
| Named event framing / extract | `libraries/event-stream`, `@agentcraft/event-stream`; removed `app/components/event_stream` | App scan/chat stream callers; UTF-8/CRLF framing, JSON failures and reader release preserved; no Python package |
| Read-only source viewer / extract | `libraries/source-code`, `@agentcraft/source-code`; removed shared source viewer | Both frontends and catalogue; original source, token safety, copy/wrap and stale-highlight contract; no Python package |
| Raw model compatibility / keep separate and extract | `libraries/azure-llm-compat`, `azure_llm_compat`; shared retains only a three-symbol parent bridge | Optimizer and parent Investigation model service; preserves raw Responses API, not bounded `llm_interface`; OpenAI 2.x requires an isolated uv project |
| Sync MITRE reads / extract adapter, reuse transport | `libraries/search-read-adapter`, `search_read_adapter`; removed shared `read.py` | Both knowledge callers; `azdata` is the only transport, key/error identities have one owner; policy/lifetime/refusal coverage preserved |

## Evidence

- Detector baseline and relocated installed consumer: 32 passed each. Same battery,
  detector engine and detector configuration assertions; no behavior changes.
- Library and both app dependency resolutions succeed with explicit uv path sources.
- Frozen source/destination hashes and mechanical import list:
  `/tmp/agentcraft-migration.KbnBod/situation-detector-move.json`.
- Recovery for moved tracked source is the baseline commit; existing parent edits remain intact.
- Live checks are recorded per completed batch below. No registry publication or new
  deployment is claimed by source/artifact tests.
- Detector live batch: API 11/11; browser 60/60; graph status 1,308 vertices/2,429 edges;
  MITRE health available with 3,908 documents. Optimizer: 11 passed, 2 existing isolation skips.
- Auth extraction: 253 passed across preserved library tests and application gate/sign-in/
  session/loopback suites. Baseline exposed missing `pytest-asyncio`; declared the prerequisite,
  preserved every test. Move receipt: `/tmp/agentcraft-migration.KbnBod/auth-move.json`.
- Auth live batch: API 11/11, guarded browser 60/60; healthy ADX, graph and MITRE counts unchanged.
- Catalogue backend: 120 passed before/after move. Both frontend typecheck/build commands pass.
  Investigation unit checks: 22 passed after correcting only the test loader's retired alias.
  Frozen source/destination receipt: `/tmp/agentcraft-migration.KbnBod/catalogue-move.json`.
- Catalogue live block: API 11/11, guarded scanner 60/60, unchanged graph/MITRE health.
  Extra no-save catalogue/source check: 25 real MITRE rows, copy/wrap and zero horizontal
  overflow at 1440/900/390 px; screenshots inspected at desktop/mobile. Private evidence:
  `/tmp/agentcraft-migration.KbnBod/catalogue-ui-v2/results.json`.
- Model compatibility: 24 focused tests; 73 with app startup/gate. No inference.
  Search: 85 adapter, knowledge and retained fixture checks. Move receipts:
  `/tmp/agentcraft-migration.KbnBod/model-compat-move.json` and `search-read-move.json`.

## Parent-Owned Follow-Up

- `backend/agents/service.py` still imports the five-line shared bridge. Equivalent public
  import: `from azure_llm_compat import azure_credential, bearer_token_provider, response_events`.
  Parent owns actual `llm_interface` adaptation and the bridge's final removal.
- Raw Search fixture helpers cannot yet be deleted without changing the implementation of
  `app/data/data_pipelines/search/__init__.py`, which eagerly imports publishing helpers for
  the test-only `build_document` consumer. Those non-mechanical app-data edits are outside
  this assignment. Retained raw helpers are explicitly not a live application path.