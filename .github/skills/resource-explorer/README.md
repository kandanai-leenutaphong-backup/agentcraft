# Resource Explorer

Portable skill: backend, browser source, contracts, fixtures and an internal `azdata` dependency
snapshot. Copy this directory alone; no sibling skill is required. The MCP adapter exposes tree,
content and search through the same `ExplorerService(settings, access)` used by the HTTP application.

A filesystem-grade explorer over an entire Azure subscription. Every resource group, every resource, every resource's own children — and **contents**: blob bytes, Cosmos documents, Kusto rows, Search documents, log rows, registry tags, and the complete ARM property JSON of anything else. Plus one estate-wide search box.

Not a fixed tree over five named services. The root is the subscription, and everything below it is discovered.

Every cloud call is `azdata`'s discover or content plane. This component owns the *hierarchy*: which branches exist, in what order they render, how a resource group's resources are grouped by type, what a node id is, what a byte string is rendered as, and what the wire payload looks like.

**A dark branch is data, never an HTTP error.** `forbidden` is fixed by a role grant; `unreachable` is a network or private-DNS path and a role grant does nothing for it; `unavailable` is the service saying no or an SDK missing; `unconfigured` is a coordinate nobody set; `empty` is a true answer. Collapsing those into "no items" throws away the operator's whole diagnosis.

## Two ideas make it general

**The universal leaf.** Every resource of every type opens into a `Properties (ARM)` leaf holding its complete ARM JSON, read through `GET {resourceId}?api-version={resolved}`. Sixteen of the twenty-six types in a real subscription have no richer data plane; for those, ARM's own document *is* the content. A resource type nobody anticipated is fully browsable the day it appears.

**Generic ARM child collections.** `GET {resourceId}/{collection}` is the same call for container-app revisions, job executions, Cognitive Services deployments, storage queues, Key Vault secret names and subnets. One code path, and adding a type is a row in [`facets.py`](backend/src/resource_explorer_api/facets.py).

On top of those, seven data planes give real contents: blob, Cosmos NoSQL, Cosmos Gremlin, Kusto, Azure AI Search, Log Analytics, and the container registry.

## Layout

```
README.md                  this file
CONTRACT.md                every route, kind, status, payload field and bound
contracts/tree.schema.json machine-readable authority for the wire payloads
backend/                   resource_explorer_api 0.1.0 (FastAPI, ASGI)
frontend/                  resource-explorer-frontend 0.1.0 (React 19, TypeScript, Tailwind)
tests/fitness.py           framework-free architectural fitness
```

There is no `deploy/`. Resource Explorer has no independent runtime lifecycle in this composition, so the app owns deployment — the component contract reserves a component-owned `deploy/` for a capability whose lifecycle is genuinely independent.

The backend serves the frontend. `/` returns `frontend/dist/index.html` and `/assets/{path}` returns its bundle, both resolved per request rather than mounted at startup, because the SPA is built after the image layer that installs the backend and a start-time mount would 404 every asset. `RESOURCE_EXPLORER_STATIC_DIR` moves that directory.

The backend is still deployable *without* a built frontend, and says so rather than crashing: `/` serves a placeholder and `/health/ready` answers `503 {"reason":"static"}` until `frontend/dist/index.html` exists.

## The API

Three endpoints, all of them `200` whenever the process can serve. [`CONTRACT.md`](CONTRACT.md) §1 is the authority; this is the shape.

| Endpoint | Answers |
| --- | --- |
| `GET /api/tree?node=<id>` | one expansion: this node's children, its breadcrumb, its status |
| `GET /api/content?node=<id>` | one node's contents, typed and size-capped, in exactly one of `text`, `dataBase64` or `rows` |
| `GET /api/search?q=<term>&limit=<n>` | one Resource Graph query across the subscription, each hit carrying a `node` the tree accepts |

`/health/live` and `/health/ready` are the only anonymous paths. Everything else needs a principal, and to an anonymous caller an unknown path answers `401` rather than `404`, so a prober learns nothing about which paths exist.

## The frontend

`frontend/` is a React 19 + TypeScript + Tailwind single-page app, built by Vite to `frontend/dist`. It expands the tree lazily — a node is fetched when it is opened, never before — and renders the breadcrumb, the estate search panel, a keyboard-shortcut help dialog, and light and dark themes.

It renders every content kind the contract declares: text, JSON, CSV, markdown, image, binary and rows. A branch's status is rendered as a status note carrying the server's own `error` string, because `forbidden` and `unreachable` need different people to fix them and collapsing both into "failed to load" throws that away.

No Azure SDK, endpoint or subscription GUID appears in browser code; `tests/fitness.py` check 5 fails if one does.

## Local setup

From the skill directory, with Python 3.11+ and uv:

```bash
uv sync --locked --no-default-groups --no-install-project --no-install-package azdata --extra mcp --extra dev
.venv/bin/python tests/selftest.py
.venv/bin/python examples/offline.py
```

The local `azdata` source is bundled, with dependencies resolved by [uv.lock](uv.lock).
The source-layout test and server entry points load it from this skill; the command does not need
to build or install that source into site-packages. A fixture run builds no credentials.

Use `.venv/bin/python -m pip`, not `.venv/bin/pip`: a venv committed to the repository carries the absolute path of the machine that created it in its console-script shebangs, so `pip` can install into a different checkout entirely.

For the optional browser surface, use a supported Node LTS (Node 20.20 was used for this migration):

```bash
cd frontend
npm ci
npm run build          # typechecks, then writes frontend/dist
```

`npm run build` is what makes `/` serve the app instead of the placeholder. Until it has run once, the backend is reachable but the browser sees the placeholder page.

## Tests

From this skill's directory:

```bash
.venv/bin/python tests/selftest.py
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python scripts/mcp_server.py --selftest
python3 tests/fitness.py                                     # 6 checks, each proven discriminating
(cd frontend && npm test)                                    # 85 vitest tests in 4 files
(cd frontend && npx playwright test)                         # 103 e2e tests, 2 skipped
(cd frontend && npm run typecheck && npm run lint && npm run build)
```

The fixture suites do not touch Azure. The browser runner uses explicit fixture settings and
retains the HTTP principal guard. Playwright supplies a fixture principal header to simulate the
trusted edge; the backend suite separately proves anonymous requests are refused. This does not
prove an Entra proxy deployment. No development-auth bypass is needed by these migration checks.

The production build is 260.47 kB, 80.06 kB gzipped.

## Running it locally

Against the fixture subscription, after building the frontend:

```bash
.venv/bin/python scripts/fixture_server.py --port 8099
```

This runner binds loopback, uses only the bundled fixture estate and leaves the principal guard
enabled. The normal browser is therefore unauthorized without a trusted edge. Use the Playwright
walk for an automated preview; its fixture identity is a test input, not real caller authentication.

A real HTTP deployment still needs a trusted authenticated edge that validates users and strips
caller-supplied principal headers. Do not expose the backend directly as an authenticated service.
This migration adds local MCP serving, not a hosted HTTP deployment or an auth bypass.

**`AZDATA_SUBSCRIPTION_ID` is the one variable you cannot omit.** Without it the root answers `200` with `status: "unconfigured"` and `error: "Not configured — set AZDATA_SUBSCRIPTION_ID"`. That is the degradation contract working — a coordinate nobody set is data, not a crash — but it looks like an empty estate if you were not expecting it.

```bash
export AZDATA_RESOURCE_GROUP=<group>   # optional: narrow the root to one group
```

The input application retains its development-principal setting for compatibility, but this
skill's fixture runner and MCP adapter do not enable it. Real identity verification is outside
the inherited header guard; deployment must enforce that boundary.

For frontend work, `npm run dev` serves the SPA on port 5174 with hot reload and proxies `/api` and `/health` to port 8099, so the backend above is still the one answering.

## The fixture estate

`RESOURCE_EXPLORER_FAKE_DISCOVERY=1` serves a complete fake subscription that ships in the package, so a frontend, Playwright, or a human can walk the whole contract with no cloud at all. Every response it produces is stamped `fixtures: true`.

It covers every node kind the contract declares, and one branch per outcome — `ok`, `empty`, `truncated`, `forbidden`, `unreachable`, `unconfigured`, `unavailable` — because a fixture estate where everything works proves only the happy path. Contents cover every rendering: markdown, JSON, CSV, plain text, a real viewable PNG, an undecodable binary, ARM property JSON, and four kinds of row sample.

Three details are deliberate:

- The nested-blob fixture in [backend/src/resource_explorer_api/fixtures.py](backend/src/resource_explorer_api/fixtures.py) has one name containing slashes. The tree synthesises two folders from it; no matching nested file is needed on disk.
- an index named `assets/v1: beta` is the case a delimiter-joined node id cannot survive.
- an index with 501 fields against the 500 clamp makes truncation observable end to end.

## Known limits

- **500 children per expansion, hard.** A larger listing arrives `truncated: true` and the surplus is not reachable through this API. Paging is deliberately deferred: a cursor is a contract, and no observed estate has needed one.
- **A real Log Analytics workspace is permanently truncated.** One declares roughly 690 tables against the 500 clamp, so that branch is always `truncated: true` and the last ~190 tables are not reachable at all. The workspace's own custom tables are ordered first, because those are the ones holding data; the tables lost to the clamp are the tail of the built-in schema.
- **A resource group's `resources` count is not a count of tree nodes.** It comes from a Resource Graph `summarize`, which counts top-level ARM resources only. The tree reaches more than that, because expansion also discovers nested child types — container-app revisions, storage containers, Key Vault secret names — that Resource Graph does not enumerate as resources. Re-observed 2026-08-31: 20 resource groups totalling 213 top-level resources, matching Resource Graph exactly.
- **Contents are capped at one mebibyte or a hundred rows**, declared in `sizeBytes` and `truncated`. This is a browser pane, not a download endpoint.
- **Key Vault is names and metadata only.** Secret, key and certificate *values* are never read.
- **`image/svg+xml` is never rendered as an image.** It is a script-bearing document; it arrives as `binary`.
- **Cosmos and Gremlin databases come from the management plane**, so they list with ARM `Reader` alone and are unaffected by a disabled public data plane. Their *documents* are a data-plane read and are not.
- **A Gremlin graph is read as documents over the SQL endpoint.** Traversal (`g.V()`) needs a key and is not offered; seeing what is in the graph does not.
- **Search index definitions need `Search Service Contributor` grade**, and index *documents* need `Search Index Data Reader`. They are separate grants, and an identity with one and not the other gets `forbidden` on exactly the branch it lacks.
- **The resource-group listing is cached for 30 seconds**, single-flighted, as is each Kusto cluster's query URI. A resource created seconds ago may not appear until the entry expires.
- **Two data planes are verified on one instance each.** Registry tags were read from a single container registry, and Kusto rows from a single cluster. Both code paths are exercised by the fixture estate and by the backend suite, but the live evidence is one instance, not a population — a registry or cluster configured differently may behave differently.
- **No writes, no copy-to-sandbox, no discovery-config persistence.** This component reads.

## Installed MCP Mode

Call `resource_explorer_status` after installing `harness-data@harness`. Its `config_file`
points under `PLUGIN_DATA/resource-explorer`; the environment and cache use the same isolated
namespace. A missing file exposes status but grants no live reads.

For an offline walkthrough, set that file to:

```json
{"fixtures": true}
```

Restart the server, call `resource_explorer_tree`, then pass returned node IDs to tree or content.
Search hits carry IDs accepted by the same tree. Fixture results are always marked.

For live use, the operator must configure `subscription_id`, optional `resource_group`, and
`allow_live_reads: true`, with a separately authenticated Azure identity and the necessary read
roles. Tools cannot widen scope or grant permissions. See [CONTRACT.md](CONTRACT.md) for bounds
and [GOTCHAS.md](GOTCHAS.md) for the failures this packaging and the source checks exposed.

## Removal

Disable this server in the client, or uninstall `harness-data` to remove the bundle. A standalone
consumer removes this copied directory and its own dependency declarations after stopping the
process. Neither path revokes Azure permissions or deletes cloud resources.

## Provenance

Backend, frontend, wire schema and original tests were copied as one component. The dependency
snapshot is `azdata` 3.4.0 from the same source checkout, not the separately installed data skill.
Its [gotchas](vendor/azdata/GOTCHAS.md) retain their original numbering. The master migration guide
records source paths and verification results; no runtime path points back to that checkout.
