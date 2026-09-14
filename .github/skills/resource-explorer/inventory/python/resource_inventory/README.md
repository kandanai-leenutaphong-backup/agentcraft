# `resource_explorer` — data, agents and tools

Portable Python import: `resource_inventory`; React package: `@harness/resource-inventory`.
Use the [portable entry](../../SKILL.md) for current setup; no source application directory is
required.

A reusable three-column Explorer: datasources, agents/tools, and one shared viewer. The data
inventory is declared by the host's registry; the agent catalogue arrives through a host-supplied
loader. Source metadata, bounded previews and syntax-highlighted tool code remain read-only.

The inventory view reuses the resource explorer distributed in this skill;
[`PROVENANCE.md`](PROVENANCE.md) records the shared source and adaptation decisions.
This file is the contract.

## Public surface

Python imports from `resource_inventory`; React imports from `@harness/resource-inventory`.
The consuming application owns its composition and any architecture-checker configuration.

```python
registry = InventoryRegistry([UseCase(...)])            # the allowlist
service  = InventoryService(registry, {"adx": probe})   # one probe per connector
app.include_router(build_inventory_router(lambda request: request.app.state.inventory))
```

```tsx
import { ResourceExplorer } from "@harness/resource-inventory";
<ResourceExplorer loadAgents={loadAgents} active={active} previewRows={25} />
```

`loadAgents(signal)` returns `Promise<{ agents: AgentCatalogueEntry[] }>`; the component imports
no application API or configuration. `active` defaults to true. The exported agent/tool types
carry metadata, source previews and `datasource_ids`, an array of exact inventory IDs. Selecting
a tool reveals and outlines all matching source rows in green. Unknown IDs are ignored; an empty
array clears the outlines. Highlighting never enables a source or reads its contents.

Tool metadata may include a `datasources` array; the original `datasource` object remains a
compatible fallback. Both navigation columns share styles in `explorer.css`. Tool code uses
the public `source_code/frontend` component. The host supplies React, lucide-react and Shiki.

`InventoryExplorer` is still exported for hosts needing only the two-column datasource view.
Optional `renderLayout({ navigation, detail })` arranges the existing panes in a host-owned
layout; selection, fetching, bounds and cancellation remain owned by `InventoryExplorer`.
`onSelect()` notifies the host when a tree row is activated. `selectionActive={false}` suppresses
the selected-row highlight without clearing the selection, for a shared viewer showing another pane.
Omitting these props retains the standalone two-column layout.
`highlightedSourceIds` reveals and outlines the declared dependencies independently of selection.

`ExplorerLayout` exports a two- or three-pane shell: `agents`, `heading`, viewer `children`, and
optional `navigation`, `subtitle`, `viewerRef`, `testId` are supplied by the host. Omitting
`navigation` removes the source column entirely and places Agents beside the viewer.
`AgentToolDetail` renders a tool given `tool` and an agent's `name`/`model`. A host's
**Data & Tools Catalogue** supplies navigation from `InventoryExplorer`; an **Agent Editor**
surface uses the two-pane layout without mounting inventory. Persistence, versioning, role
assignment and authorization remain entirely in the application, never in this component.

| Piece | Owns |
| --- | --- |
| `registry.py` | The allowlist. Duplicate ids, a source filed under the wrong use case, an unknown capability, a connector-less source and a credential-named coordinate are all refused at build |
| `nodes.py` | The opaque node codec and every rejection row |
| `selection.py` | One request's scope, parsed from `X-Inventory-Selection`. Never stored |
| `service.py` | `tree`, `resource`, `content`, and the `SourceProbe` seam |
| `router.py` | Four `GET` routes |
| `cache.py` | TTL plus single flight for metadata reads |
| `frontend/` | `ResourceExplorer`, its reusable `InventoryExplorer`, agent/tool types and scoped CSS |

## Routes

| Route | Answers | Non-200 |
| --- | --- | --- |
| `GET /tree?node=` | Root, or one use case's sources. Never probes | 400 `invalid_node`, 400 `invalid_selection` |
| `GET /resource?node=` | One source's metadata, read now | 400, 409 `source_disabled` |
| `GET /content?node=&limit=` | One source's bounded preview | 400, 409, 422 `invalid_limit` |
| `GET /selection` | Every selectable source and whether this request has it on | 400 |

Every response, including every rejection, carries `Cache-Control: no-store, private` and
`Vary: X-Inventory-Selection`. A rejection body echoes nothing the client submitted;
`token_digest` exists so a rejected token can be correlated in a log without the endpoint
becoming a reflection surface.

A read failure is a **200 carrying its status**. Only a malformed request and a scope
conflict are non-200, because a dark branch still has to render.

## The registry is the security control

A node id decodes to `(use_case_id, source_id)` and nothing else. Every endpoint,
database, table, graph and index name is looked up server-side. A forged token can name a
source that does not exist — which is refused before any client is built — but it has
nowhere to put a cluster.

**A declaration may not contain a credential.** Coordinates are the things you would read
off a portal blade, and they are served to the browser in the detail pane. A coordinate
whose *name* is a credential name — `key`, `secret`, `password`, `token`, `sas`, `sig`,
`credential`, `auth`, `connection_string`, and their camelCase forms — is refused at
registry build, naming the coordinate and never its value. Coordinate *shapes* are the
composing application's to validate at its own edge, because only it knows which
coordinates its readers take; the host declares its own manifest module for that.

Authentication never travels this path. A probe gets its identity from the host.

## Selection

`X-Inventory-Selection` takes `all`, `none`, or a comma-separated list of source ids.

| Value | Means |
| --- | --- |
| absent header | `all` — the default |
| `all` | Every declared source |
| `none`, or an empty value | No source. "Everything off" is never read as "not chosen yet" |
| `a,b,c` | Exactly those; an explicit list covering everything collapses to `all` |

Refused with 400 `invalid_selection`: an unknown id, a repeated id, an empty id in a list,
more than 64 ids, more than 4096 characters. Unknown and repeated ids are refused rather
than dropped — either means the client has lost track of its own selection, and silently
repairing it leaves a switch that does nothing.

**It is not an access control.** The client declares it, so a client can declare anything.
It narrows what this request reads and says so in `SELECTION_SCOPE`; the allowlist decides
what may be read at all.

**Scope recovery narrows, never widens.** The browser half stores its selection in
`sessionStorage` and sends it per request. When the server refuses it as stale, the client
re-reads `/selection` with `none` — costing no source read — and keeps only the surviving
ids. An explicit list with no survivors becomes `none` with an explanation. Resetting to
`all` would switch back on every source the reader had switched off, which is the one
thing the switch exists to prevent.

The set of sources comes from `/selection`, never from the tree. The tree is lazily
expanded, so its ids are only those of whichever branches happen to be open.

**Changing the selection does not rebuild the tree.** The reducer's `invalidate` carries the
new selection, drops every metadata and preview response — those described a different scope
— bumps the generation so answers already in flight are discarded, and flips the switches on
the rows already on screen. The branches are then re-read at the new generation. Clearing the
tree instead blanked it for the length of a round trip and threw away the focus of whoever
had just operated a switch.

## Keyboard and naming

The tree is the WAI-ARIA tree pattern: one tabbable row, Up/Down over what is visible,
Right to open then descend, Left to collapse then ascend, Home/End to jump, Enter or Space
to select the focused row, and `t` to toggle the focused source.

**A key pressed on a control inside a row belongs to that control.** `TreeView` acts on
Enter and Space only when the event originates on the row itself. Handling them wherever
they bubbled from meant `preventDefault` cancelled the native activation of a focused
checkbox, so the switch could be tabbed to and then not operated at all. Navigation keys
still reach the tree from inside a row, because no control in a row uses the arrow keys.
Space on the switch is the browser's own toggle; Enter is handled explicitly, because a
checkbox has no native Enter behaviour and a reader who has just tabbed to it expects both.

Two use cases may declare a slot with the same label — both declare `Retrieval index`. The
row renders the declared label and the *accessible* name carries the owner:
`Retrieval index, AIT, enabled`, with the switch named `Use Retrieval index, AIT in this
session`. The detail pane is a region named the same way and states its use case, in every
state including switched-off, unconfigured and still-loading, where there is no metadata to
infer it from.

Interactive targets are at least 24×24 CSS pixels (WCAG 2.2 SC 2.5.8): the twisty is 24×24
and the switch label 48×26. Both are measured in the browser by `verify-inventory.mjs`
section 14, not asserted from the stylesheet.

## Preview bounds

`SourceType` includes `local_table` alongside `adx_table`, `gremlin_graph` and `search_index`.
This is a wire kind, not a filesystem reader: the host supplies an authorized local probe
and its root. Nothing in a node token or preview request becomes a filesystem path.

Only sources declaring the `preview` capability offer row previews. Metadata-only sources
have `hasContent: false`, no preview action in the viewer, and a direct content request
returns `status: "forbidden"` with no rows before calling a probe. The host may further
restrict preview rows, such as development-only evidence and evaluator-only labels.

`DEFAULT_PREVIEW_ROWS` is 25 and `MAX_PREVIEW_ROWS` is 100; the route rejects anything
outside 1–100 with 422 and the service clamps again. Byte, column and cell bounds belong
to the bundled [content-envelope contract](_content/content.py). Hosts must honor those bounds.

`ContentResponse` reports the sample honestly: `sizeBytes` is the row count returned,
`rowLimit` the bound applied, `sampleOf` the population when a probe knows it, `truncated`
whether anything was left out, and `sampleNotes` which bound left it out. `RowsTable`
renders the notes beside the scale line. Every cell renders as text; nothing in a row is
treated as markup, a link, or something to fetch.

## Injection seams

`SourceProbe` — `async metadata(source) -> ProbeReport` and
`async preview(source, *, limit) -> ContentResult`, registered per connector name. Neither
may raise: a source whose connector has no probe is reported `unavailable` naming the
connector. `build_inventory_router(get_service)` resolves the service per request, so the
host keeps lifespan and configuration.

## What this component does not know

Any use case, source, cluster, table, graph or index. It has no settings object, no
principal guard, no static mount, no development authentication bypass and no fixture
mode. `fixtures` is on every payload and is always `false`, so a fixture mode cannot be
added silently.

## Tests

```bash
python3 -m unittest discover -s "$SKILL_ROOT/tests" -q
```

The portable integration gate exercises the composed browser surface with synthetic, locally
authorized data. The original application's browser journey is not an installation dependency.
