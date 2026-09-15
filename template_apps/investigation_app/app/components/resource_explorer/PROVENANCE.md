# Provenance — `app/components/resource_explorer`

Adopted from the `resource_explorer` component of the `azure-agent-loop` repository, at
revision `b3ba7f485db7961a1f9a36bd32a7ab85808e8724`, source trees
`hillclimber/components/resource_explorer/backend/src/resource_explorer_api/` and
`hillclimber/components/resource_explorer/frontend/src/`.

Adopted **2026-09-05** into `perth_cyber` at baseline `564f627f`.

**This is a copy, not a dependency.** Nothing in this repository imports, links to, or
builds against `azure-agent-loop`. No path, symlink, submodule, `package.json` entry or
requirement points at it, and none may be added.

## The one architectural difference

Upstream roots its tree at an **Azure subscription** and discovers downward: resource
groups, ARM types, resources, data planes. That is right for browsing an estate. It is
wrong here, and adopting it unchanged would have shipped an unrestricted subscription
browser inside an analyst application.

This component roots at a **declared registry of use cases**. Everything it will ever
serve is in that registry, a node id carries only two identifiers, and every coordinate is
looked up server-side. A request cannot name a cluster, a database or a table, because
there is nowhere in the request to put one.

Everything else was adopted because it was already right: the six-status failure
vocabulary, the opaque node codec and its rejection table, the two-`status` wire shape, the
`fixtures` flag, the WAI-ARIA tree keyboard model, the row-sample table, and the discipline
that a discovery failure is data rather than a status code.

## Backend

Upstream paths are relative to
`hillclimber/components/resource_explorer/backend/src/resource_explorer_api/`. The hash is
the full SHA-256 of the upstream file as it stood when this copy was taken.

**No file here is byte-identical to its original.** A file whose docstring was rewritten
is adapted, not verbatim, and is recorded as adapted.

| This repository | Upstream file | Upstream SHA-256 | State |
| --- | --- | --- | --- |
| `backend/cache.py` | `cache.py` | `fdc1879dabb909f797ab5918835c9ac664514af08cb2871cc1161e40c52ac80b` | adapted (docstring only) |
| `backend/contracts.py` | `contracts.py` | `d53403373504687b312164447854862849ec5ae1942f1a3f33fa04ea5a877cfd` | adapted |
| `backend/nodes.py` | `nodes.py` | `e3297bf82b3b589fc228f64e46fb8b567fa6e4fcb5e1e7de6e40b4719739be8b` | adapted |
| `__init__.py` | `__init__.py` | `129bbf0a1012bfdc728721a4a29bd3ded770678cf22aea1f0b3d7cd7e6a335ea` | rewritten |
| `backend/registry.py` | — | — | **new here** |
| `backend/selection.py` | — | — | **new here** |
| `backend/service.py` | — | — | **new here** |
| `backend/router.py` | — (see below) | — | **new here** |
| `backend/__init__.py` | — | — | **new here** |

### What "adapted" means, per file

- **`backend/contracts.py`** — the `Wire` base, the camelCase alias generator, the
  `schemaVersion`/`fixtures`/`observedAt` discipline, the two-`status` design and the
  `NodeStatus` enum are upstream's, retained with their explanatory headers. `NodeKind`
  drops from twenty-one estate kinds to three (`root`, `use_case`, `source`). `ContentKind`
  drops from eight to three: this component reads rows and never bytes, so `image`,
  `binary`, `csv` and `markdown` would name renderings it cannot produce. `SearchHit` and
  `SearchResponse` are dropped with the estate search. `ResourceResponse`,
  `SelectionResponse`, `SelectionSource`, `ConnectorIdentity`, `InvalidLimitError` and
  `SourceDisabledError` are new.
- **`backend/nodes.py`** — the codec is upstream's: base64url of canonical JSON, the same
  `{v,s,l,p,k}` payload, the same rejection rows, `token_digest` for logging. Changed:
  `LEVELS_BY_SERVICE` declares one service with two levels instead of eight services;
  `p[0]` is a use-case id rather than an ARM resource id, which is the change that removes
  a whole class of forgery; `MAX_TOKEN_CHARS` 8192 → 4096 and `MAX_PATH_SEGMENTS` 4 → 2
  because the hierarchy is smaller; `SEGMENTS_BY_LEVEL` is added so a token with the wrong
  arity is refused; an empty path segment is refused. `CONTENT_BY_KIND` becomes
  `CONTENT_KINDS` since one reader answers for every leaf.

### What was deliberately not taken

- **`app.py`** — a whole ASGI application with its own settings, static mount and openapi
  route. This host has all three. `backend/router.py` is an `APIRouter` instead.
- **`security.py`** — `PrincipalGuard`, and with it
  `RESOURCE_EXPLORER_DEV_PRINCIPAL=1`, which skips the principal check. A component that
  brings a second authentication story, and a bypass flag, to a host that already has
  authentication makes the host less safe. CyberEye owns its own edge.
- **`settings.py`** — a second configuration object reading a second set of environment
  variables. Configuration enters this application at its own edge and is passed down.
- **`fixtures.py`** (880 lines) — a fake Azure estate. There is nothing here to fake: the
  registry is small and declared, and a fixture mode would be a second source of numbers.
  The `fixtures` flag is kept on every payload and is always `false`, so a future fixture
  mode cannot be added silently.
- **`facets.py`** — the ARM-type-to-branch table, which only means something under an
  estate root.
- **`tree.py`** (990 lines) and **`discovery.py`** — the subscription hierarchy itself.
  `backend/service.py` composes two declared levels instead.
- **`backend/tests/`** (180 pytest tests) and **`tests/fitness.py`** — written against the
  estate hierarchy and a pytest runner. This repository runs `unittest` and carries its own
  tests for what was adopted, in `app/components/tests/test_resource_explorer.py` and
  `app/cybereye/tests/test_data_inventory.py`.

## Frontend

Upstream paths are relative to `hillclimber/components/resource_explorer/frontend/src/`.

| This repository | Upstream file | Upstream SHA-256 | State |
| --- | --- | --- | --- |
| `frontend/rows.ts` | `api/rows.ts` | `14eabd6545c17980bae7cd534a0e01a444bf40febeb8192456ad37b9e169f45a` | adapted (docstring only) |
| `frontend/keyboard.ts` | `api/keyboard.ts` | `9331d16847f9c46fc98927c56f81201f4983d9f843a7ad034aad5764565c1bbe` | adapted |
| `frontend/status.ts` | `api/status.ts` | `af4986c783b45ae27e81108733c2195c1f89d0b2228701610909a6f55bdae9ea` | adapted |
| `frontend/state.ts` | `api/state.ts` | `40057cecc6aa23448995df5f87763ad3994fda37d5ff5508c0f322a09a809589` | adapted |
| `frontend/wire.ts` | `api/wire.ts` | `6a698f3edb0c39257622d3e8257c76acccd4a81650770565b6961cb64fc253a1` | adapted |
| `frontend/client.ts` | `api/client.ts` | `4d9ef5029db5b68cf7d98802cb08e3216d235cada4740c54813875895c73b089` | adapted |
| `frontend/TreeView.tsx` | `components/TreeView.tsx` | `05adc35e8bd6e627778123357354447032c0cd266d916139136d9dcd22378e85` | adapted |
| `frontend/StatusNote.tsx` | `components/StatusNote.tsx` | `c891258aef32707aa241640ab5f576b51f0524eff7275e298a9cec386726e2b9` | adapted |
| `frontend/DetailPane.tsx` | `components/DetailPane.tsx` | `591484ea28c375fad92d42c1d90211c2589c13d92156990c8b5340659d1f6363` | adapted |
| `frontend/RowsTable.tsx` | `components/content/RowsTable.tsx` | `9e41c83b141f6fdbf4e337c11ad5987cc0f09775cddba4fd4c628725263c7d71` | adapted |
| `frontend/inventory.css` | `index.css` + Tailwind classes | `ce36ff7ca421119073b201cb89dd21daa937f6901d66eb2e6f2a92f0fc2ceff7` | **translated** |
| `frontend/selection.ts` | — | — | **new here** |
| `frontend/InventoryExplorer.tsx` | — | — | **new here** |
| `frontend/ResourceExplorer.tsx` | — | — | **new here**, extracted combined layout and agent/tool viewer |
| `frontend/explorer.css` | — | — | **new here**, shared data/agent navigation styling |
| `frontend/index.ts` | — | — | **new here** |

The combined Explorer accepts a host-owned agent loader and exact inventory dependency IDs.
`InventoryExplorer` and `TreeView` gained optional dependency highlighting and branch reveal;
these are local additions, not claims about upstream behavior. Source enablement is unchanged.

### Tailwind was translated, not adopted

Upstream is React 19 + TypeScript + **Tailwind 3**, and ships Tailwind's preflight reset.
CyberEye is React 19 + TypeScript + hand-written CSS with no framework. Adding Tailwind
would have restyled the whole application, and scoping it away would have meant carrying
`tailwindcss`, `postcss` and `autoprefixer` plus a config file to produce rules that could
be written directly.

So every utility class in the adopted components was replaced by one scoped class defined
in `frontend/inventory.css`, prefixed `inv-`, using the host's own colours. The structure,
the ARIA attributes and the component decomposition are upstream's; only the class strings
changed. `status.ts`'s three Tailwind tone tables (`TONE_BADGE`, `TONE_PANEL`, `TONE_TEXT`)
collapse to one `TONE_CLASS`. **No build-time CSS dependency was added to this repository.**

### What "adapted" means, per file

- **`keyboard.ts`** — the WAI-ARIA move table is upstream's, unchanged. The `/` move is
  dropped (no search box to jump to) and `t` is added, which toggles the focused source.
- **`status.ts`** — the label, meaning, remedy and tone tables are upstream's wording.
  `isRetryable` is new, so retry is offered only where retrying could change the answer.
  `SOURCE_TYPE_LABEL`, `coordinateLabel` and `metricLabel` are new. `CONTENT_KIND_LABEL`
  narrows to the three kinds this component produces. Numbers are locale-formatted.
- **`state.ts`** — the reducer, the `Row` projection, `visibleRows`, `rowIndex`,
  `effectiveActiveId`, `descendantIds` and `pendingLoads` are upstream's. Search, the
  sign-in session and the reveal note are dropped. A `resources` map is added, because a
  source's metadata is a separate read from its preview. A `generation` counter is added:
  every action carries the generation it was issued in and the reducer discards a stale
  one, so a pane cannot repopulate from a source the reader has just switched off. Each
  cached branch records the generation it was read in, so `pendingLoads` refetches what is
  stale rather than only what is absent — which is what lets a selection change keep the
  rows standing instead of clearing them.
- **`wire.ts`** — the defensive-parse discipline is upstream's, including degrading an
  unknown status to `unavailable` rather than throwing inside a render. `maybeCount` is
  added so an absent number stays absent instead of becoming a zero that reads as a
  measurement. `sampleNotes` is added alongside `truncated`.
- **`client.ts`** — the fetch shape and `cache: "no-store"` are upstream's. The
  `401`/session-expiry path is dropped, since the host owns authentication.
  `SourceDisabledError` (409) and `StaleSelectionError` (400) are added, and every call
  carries this tab's selection header and an `AbortSignal`.
- **`TreeView.tsx`** — `role="tree"`, one tabbable row, `aria-level`/`aria-posinset`/
  `aria-setsize` from the same projection the renderer uses, and the focus-restore ref are
  upstream's. The estate icon set is dropped; a per-source switch and `data-*` hooks are
  added. Upstream has no interactive control inside a row, so its key handler acts on
  whatever bubbled to the tree; here Enter and Space are acted on only when they originate
  on the row, and the row's accessible name carries the owning use case.
- **`DetailPane.tsx`** — the pane decomposition and the "status is words, not colour"
  discipline are upstream's. The ARM-properties, blob and image sections are dropped;
  metrics, coordinates, connector identity, capabilities, configuration keys, schema, the
  provenance line and the switched-off state are added. The head is one component shared by
  every branch, so an early return cannot ship a pane that does not say whose source it is.
- **`RowsTable.tsx`** — the sortable table, `aria-sort`, and the absent-last sort are
  upstream's. The sample-scale caption is added, because a page of 25 rows with no scale
  reads as the whole table, and so is the notes list, because a bound that shortened a
  cell has to be legible next to the cell it shortened.

## What was fixed in the adaptation

Three defects found here, none of them upstream's fault and all worth recording because
the traps are general.

**Reconciling a selection against a lazily-expanded tree.** The stored selection was
reconciled against the source ids the *tree* had loaded. The tree is lazily expanded, so
that set is only the sources of whichever use case happens to be open — toggling one
source rewrote the selection down to the three ids of the one expanded branch, silently
switching off everything collapsed. `InventoryExplorer` now takes the authoritative set
from `GET /selection`.

**Healing a rejected selection by widening it.** A stored selection naming one id the
server no longer declares is refused wholesale, and the first repair written here reset it
to `all` — which switches back on every source the reader had deliberately switched off.
The recovery now re-reads the catalogue with a selection that reads nothing and keeps only
the surviving ids; an explicit list with no survivors becomes `none` and says so. Scope
recovery narrows, never widens. Covered in the browser by `verify-inventory.mjs`
sections 10 and 11.

**A composite widget's key handler swallowing its own children.** Upstream's tree has no
interactive control inside a row, so acting on every Enter and Space that reaches the tree
is safe there. Adding a checkbox to each row made it a defect: the handler ran first,
`preventDefault` cancelled the browser's own toggle, and the row then took the focus — so
the switch could be reached by Tab and then did nothing at all, silently. A control inside
a composite owns the keys it uses; the composite owns the rest. Covered by
`verify-inventory.mjs` section 13, which presses real keys rather than clicking.

## Retained notices

The upstream component carries no licence header, no copyright notice and no `LICENSE`
file. Nothing was stripped. Every module docstring that explains *why* a mechanism is
shaped the way it is has been retained, and where a rule was changed the docstring says so
rather than quietly describing the old behaviour.

## Re-checking this record

```bash
UP=/home/hanchoong/azure-agent-loop/hillclimber/components/resource_explorer
sha256sum "$UP"/backend/src/resource_explorer_api/{cache,contracts,nodes,__init__}.py
sha256sum "$UP"/frontend/src/api/{rows,keyboard,status,state,wire,client}.ts \
           "$UP"/frontend/src/components/{TreeView,StatusNote,DetailPane}.tsx \
           "$UP"/frontend/src/components/content/RowsTable.tsx "$UP"/frontend/src/index.css
```

A hash that no longer matches means upstream moved; it does not mean this copy is wrong.
Decide deliberately whether to re-adopt. Nothing in this repository reads that path at
build time, at test time or at run time.
