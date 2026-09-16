# Resource Explorer

Use installed `resource-explorer` (`resource_explorer` and
`resource_explorer.content`) and `@agentcraft/resource-explorer`. The target is
host-declared source inventory, not Azure estate discovery. The
[package guide](../../README.md) and public exports own the current API.
Older application-path imports in source contracts/provenance are historical.

The skill-local `resource_explorer_api`, `resource_inventory`, independent estate
engine and vendor `azdata` are retired. Data probes consume public azdata v4;
there is no copied provider runtime or invented discovery package.

## Contract And Host Boundary

Build `InventoryRegistry` from `UseCase`, `InventorySource`, `SourceBinding` and
`SourceType`; construct `InventoryService(registry, probes)`. Public
`SourceProbe.metadata` / `preview` return `ProbeReport` and bounded content values.
Use `tree`, `resource`, `content`, selection contracts and optionally
`build_inventory_router(get_service)`. The host owns lifecycle and authorization.

Router `prefix` and browser client `base` default to `/api/inventory`; set both
explicitly for another host route. No host authentication gate is installed here.
`InventorySource.provenance` is host-supplied. Without it, resource/content payloads
state that provenance is unspecified and freshness unknown. Historical replay or
live monitoring is never inferred; explicit host claims remain unchanged.

Nodes encode use-case/source identity, never endpoint/database coordinates. Every
read resolves those coordinates from the trusted server registry. Undeclared or
cross-use-case identities refuse before probe construction. Registry construction
rejects duplicates, unknown capabilities, connector-less sources and credential-
named coordinates, reporting names rather than secret values. Never put credentials
in a registry, browser payload, node ID, receipt or example.

Optional `resource_explorer.probes.AdxProbe`, `SearchProbe` and `GremlinProbe`
reuse canonical content normalization and azdata. Hosts inject source coordinates,
identity and any allowed graph source factory. A missing factory discovers no
credential or source. Tree enumeration probes nothing. Schema/count/preview failures
retain their states; a forbidden branch is not an empty branch.

`GraphElementSource.sample` returns a sequence or awaitable sequence of mappings.
Async methods and sync wrappers returning awaitables are awaited; synchronous
sample calls run off-loop. `GraphReader` borrows its source. `GremlinProbe` owns
factory-created sources and awaits asynchronous close. Cancellation is not empty
success. Hosts still need blocking callback deadlines: Python cannot terminate
an underlying synchronous worker thread.

Runtime no longer exports `override`, `override_missing` or `clear_overrides`.
Use constructor-injected probes/credentials/transports and scoped import mocks in
tests; no process-global SDK substitution registry remains.

React callers use the public `ResourceExplorer`, `InventoryExplorer` and
`ExplorerLayout`; source previews use separate `@agentcraft/source-code`. The host
provides agent catalogue loading, peers and authenticated HTTP. Metadata previews
never execute code, grant a source, or fetch a URL rendered inside a cell.

## Selection, Errors And Bounds

`X-Inventory-Selection` is a request-local filter, not access control. Missing
means all declared sources; `none` or an empty value means no sources. Explicit
IDs may only narrow the registry. Unknown/repeated/empty IDs, more than 64 IDs or
4,096 characters refuse. Stale browser selection recovers through `none`, retaining
only surviving IDs; it must not reset to `all` or enable newly declared sources.

Construction errors use `InventoryDefinitionError`; malformed nodes/selections
use `InvalidNode` / `InvalidSelection`; disabled reads use `SourceDisabled`.
HTTP errors distinguish invalid node/selection (400), disabled source (409) and
invalid limit (422). Provider failures are 200 responses carrying explicit
status/error, not successful empty inventories. Rejections reflect no submitted
token; `token_digest` is the correlation value.

Every router response, including refusal, carries `Cache-Control: no-store, private`
and selection-aware `Vary`. Preserve status, errors, fixture/provenance markers,
truncation and sample notes in consumers. Inventory fixtures are not a hidden
authentication bypass or live-service evidence.

Preview default is 25 rows, maximum 100; the route rejects invalid values and the
service clamps again. Metadata-only sources refuse preview before a probe. Content
normalization bounds cells, columns and aggregate UTF-8 bytes, reporting omissions;
its documented minimum-row behavior is not a hard transport memory cap. A bounded
sample is not a complete inventory. Tokens never supply a local filesystem path.

The host injects/owns probe lifetime and caller auth. Selection is never stored by
the service. Metadata caching has TTL/single-flight semantics; request scope and
frontend generation checks prevent stale selection results from becoming current.
The existing `cybereye.inventory.selection` storage key is retained for saved
selection compatibility. Neutral routing does not reset a tab to all sources.
This is browser-session state, not server authorization.
Borrowed credentials remain host-owned. No application server, static mount,
forwarded-principal trust, private endpoint change or MCP server is installed here.

## Historical Knowledge And Assets

The retired estate skill's G1-G7 still matter with corrected ownership:
install canonical dependencies instead of vendoring a sibling; build host browser
assets before checking its readiness; node IDs are not authorization; preserve
forbidden/unreachable states; choose search hits by kind rather than position;
trust forwarded principals only behind a proven authenticating/stripping edge;
and display truncation. Subscription/group walking is not the declared inventory
contract. Authorized native Azure administration is a separate host workflow.

Unmodified IBM Plex fonts and OFL license are retained under
[assets/fonts](assets/fonts/LICENSE-OFL-1.1.txt), with the original
[third-party notice](assets/THIRD_PARTY_NOTICES.txt). Its `src/fonts` paths refer
to the retired frontend; the filenames and bytes are unchanged. Five screenshots
under `historical-estate-ui/` preserve old fixture UI evidence, not target acceptance.
The [inventory provenance](history/inventory-provenance.md) is a verbatim historical
record; its old paths/hashes are provenance, not current installation instructions.
No retired implementation source is stored under documentation.

## Retirement And Checks

Exact removal/move manifest (source-or-asset-not-bundled; source reference: `resource-explorer-retirement.json`) records every
path, source hash, preserved asset destination and external recovery copy. The
native skill keeps its name and discovery triggers; runtime is exclusively the
declared-source library. The vendor azdata MIT notice matches its retained owner.

Use installed Python packages (3.12+) and build the source-code peer first.
Installation/examples and `npm run typecheck`, `npm test`, `npm run build`,
`npm pack` belong to the package README. Exports contain built ESM, declarations
and CSS; retained assets and notices ship with the archive.

```bash
python -B -m unittest discover -s libraries/resource-explorer/tests -v
npm --prefix libraries/resource-explorer test
```

Existing tests cover registry/coordinate refusals, node tampering, per-request
selection, disabled sources, no-probe paths, bounded content, async graph samples,
cancellation, neutral provenance/routes and removed test hooks. Frontend tests
exercise compiled client refusals and CSS/declaration artifacts. Synthetic browser
checks are not live inventory, cloud identity or deployed-auth evidence. Parent
owns shared discovery and old MCP registrations.