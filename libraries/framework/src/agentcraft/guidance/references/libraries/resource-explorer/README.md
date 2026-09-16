# Resource Explorer

One owner for the allowlisted inventory service, wire schemas, content/status contracts,
and React explorer. Python imports `resource_explorer` and `resource_explorer.content`;
frontend imports `@agentcraft/resource-explorer`. Hosts inject source registries, probes,
credentials and authorization. Requests cannot widen configured source scope.

Router and browser client default to `/api/inventory`. Hosts can explicitly set
`build_inventory_router(..., prefix=...)` and matching frontend `base`. Missing
source provenance means unknown freshness; only `InventorySource.provenance`
may assert historical replay or live provenance. Selection remains a filter,
never authorization. The [canonical guide](docs/skills/resource-explorer.md) owns
these contracts.

## Build And Install

Python requires 3.12+. From the repository root, build with
`uv build libraries/resource-explorer --wheel`, then install that wheel in the host.
Wheels include `py.typed`; Azure dependencies remain optional.

Build the [source-code peer](../source-code/README.md) first. From this package directory:

```bash
npm install
npm run typecheck
npm test
npm pack
```

`prepack` emits ES2022 ESM, declarations and both unchanged stylesheets in `dist`.
Archives include retained IBM Plex font/license assets. Install the source-code
archive and returned `agentcraft-resource-explorer-0.1.0.tgz` with
`npm install <archive-paths>` in the host. Local `file:` consumers build both
libraries first; compiler/bundler source aliases are not needed. Hosts own peer
lockfiles and releases. TypeScript 5.9, React 19 and Node 20.20.0 were verified.

The main import loads CSS through the host bundler. Explicit `./inventory.css`,
`./explorer.css` and `./assets/*` exports are available. Fonts are optional host
assets; no font loading or layout is changed. Keep one host React instance.
Registry publication and a CSS-unaware Node loader are not claimed.

```tsx
import { InventoryExplorer } from "@agentcraft/resource-explorer";

export function Catalogue({ authenticatedFetch }: { authenticatedFetch: typeof fetch }) {
	return <InventoryExplorer base="/api/inventory" fetchImpl={authenticatedFetch} previewRows={25} />;
}
```

This package owns no ADX/Search/Gremlin transport, provisioning or write connector.
The optional `azure` extra provides `resource_explorer.probes.AdxProbe`, `SearchProbe`
and `GremlinProbe`. ADX/Search probes use public `azdata`; graph probes receive an explicit
source factory and allowed account. Hosts supply credentials and source coordinates.
Counts, schema ordering, missing/forbidden states, preview bounds and connector cleanup
have one implementation here. A missing graph source factory never discovers identity.
Graph previews use the injected `GraphElementSource`.
Samplers may return rows or awaitable rows; sync calls run off-loop. Test-only
global SDK overrides are removed. Tests inject probes, credentials and transports
directly, or scope import mocks to one test.
The source viewer is the separate `@agentcraft/source-code` dependency.

Source and tests originate at baseline `00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4` in
Investigation's `resource_explorer` and `data_connector_library/core` components.
Original contracts and provenance remain beside the source.

Offline checks: package tests, Investigation inventory/authorization tests,
guarded-verifier tests and frontend builds. Real scanner/catalogue runs require
separate authority; historical runs do not prove this revision's live identity
or service behavior.
