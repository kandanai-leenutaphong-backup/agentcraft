# Existing-Owner Skill Cull

Status: **complete for the assigned runtime-retirement increment**, 2026-09-16.
Frozen baseline: `015d1bfc683c3b929490ce595f66744a4c8d56fa`. HEAD advanced during
the work; counts use that baseline and frozen path hashes, not current-HEAD diff.

All eleven native skills retain their names and triggers and route to canonical
installed packages. Shipped files: **557 -> 29** (guides, MIT notices and existing
ignore rules). **528 old paths retired**. No independent shipped skill runtime
remains. No obsolete implementation was hidden under documentation.

## Counts And Manifests

| Skill | Old paths retired | Source files retired | Canonical owner / exact manifest |
| --- | ---: | ---: | --- |
| source-code | 4 | 3 | [source-code](../../../source-code/docs/skills/retirement-manifest.json) |
| situation-detector | 7 | 5 | [situation_detector](../../../situation-detector/docs/skills/situation-detector-retirement.json) |
| azure-data-connectors | 97 | 90 | [azdata v4](../../../azure-data-connectors/docs/skills/azure-data-connectors-retirement.json) |
| azure-search | 7 | 6 | [azdata v4 Search](../../../azure-data-connectors/docs/skills/azure-search-retirement.json) |
| azure-llm-connectors | 37 | 30 | [llm_interface](../../../llm-interface/docs/skills/azure-llm-connectors-retirement.json) |
| managed-identity-model-clients | 31 | 23 | [llm_interface](../../../llm-interface/docs/skills/managed-identity-model-clients-retirement.json) |
| resource-explorer | 207 | 174 | [declared-source resource_explorer](../../../resource-explorer/docs/skills/resource-explorer-retirement.json) |
| azure-access-management | 110 | 67 | [entra_auth and native administrative guidance](../../../entra-auth/docs/skills/azure-access-management-retirement.json) |
| content-from-a-store | 1 | 1 | [azdata and host cache guidance](../../../azure-data-connectors/docs/skills/content-from-a-store-retirement.json) |
| signed-dev-access | 27 | 16 | [signed_dev_access](signed-dev-access-retirement.json) |
| event-stream | 0 | 0 | [Parent retirement; notice finish](../../../event-stream/docs/skills/event-stream-retirement.json) |

Gross source removal: **415 files, 100,916 lines, 3,789,922 bytes**.
Canonical signing additions: **5 new files, 1,141 net lines, 47,990 net bytes**.
Net source reduction: **410 files, 99,775 lines, 3,741,932 bytes**.

Source counts include shipped runtime, tests, examples, scripts, CSS, HTML and
Bicep. They exclude ignored state/environments/dependencies, Markdown snippets,
docs, locks, preserved assets and the parent's earlier event-stream removal.
Bytes are logical source bytes, not disk space reclaimed. Exact hashes, imports,
package names and commands: [machine receipt](FINAL_CULL.json).

## Verification

All removal batches received immediate focused checks in a private copy of the
provided Python 3.12 dependency environment, with current canonical source selected.
No shared environment, metadata or lock was changed by these commands.

- Source-code: all three frontend files byte-identical to owner; removal, notice
  and recovery hashes verified. No standalone library selftest exists.
- Situation-detector: 16 tests passed; canonical runtime/tests matched the old copy.
- Azdata v4: 182 tests passed; Search 25 and Storage 12 are included subsets rerun
  immediately after their respective skill removals.
- LLM interface: 48 tests passed after each model skill removal.
- Resource explorer: 69 tests and 28 subtests passed.
- Entra auth: 68 tests passed.
- Signed access: final 130 tests and 48 subtests passed, including 62 new client/
  browser signer cases. Canonical verifier, middleware and replay source unchanged.
- Event-stream: notice bytes and four parent-retired paths verified; parent's
  reported seven tests were not rerun or counted as new evidence.
- Eleven native YAML entries, active local links, exact removals, preserved hashes
  and scoped whitespace checked. Historical provenance links remain historical.

## Retained State And Limits

Verified recovery and isolated interpreter remain outside the repository at
`/tmp/agentcraft-existing-owner-cull-20260916-yUwLnh`. Eleven font/notice/screenshot/
inventory-provenance holdings and five access-history records are preserved in
canonical docs. Every Microsoft MIT notice remains. Private state, environments,
credentials, user data and unrelated work were not deleted. No operational key,
server, cloud/service/model request, grant, write or publication was created.

New signing behavior uses one canonical byte contract, safe private-file reads,
origin-bound requests, redirect refusal, metadata-only CLI and closeable Chromium
CDP interception. Browser tests are synthetic; real Chromium, deployed proxy/auth,
shared Azure Table replay and live identity/provider behavior remain unverified.
Content cache/fallback is host-owned; azdata v4 has no conditional-304 read API.

Next owner: parent integration for portable discovery, package/notice inclusion,
old MCP registrations, application imports and reconciliation of historical root
documentation. No new access package or compatibility runtime is required.