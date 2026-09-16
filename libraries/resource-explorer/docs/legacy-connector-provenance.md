# Provenance — `app/components/data_connector_library`

Adopted from `azdata` version **3.4.0**, the package published by the
`data_connector_library` component of the `azure-agent-loop` repository, at revision
`b3ba7f485db7961a1f9a36bd32a7ab85808e8724`, source tree
`hillclimber/components/data_connector_library/src/azdata/`.

Adopted **2026-09-05** into `perth_cyber` at baseline `564f627f`.

**This is a copy, not a dependency.** Nothing in this repository imports, links to, or
builds against `azure-agent-loop`. There is no path, symlink, submodule or requirement
entry pointing at it, and none may be added: the origin tree is read-only reference
material that this repository does not control.

## What was taken

This section covers the **read plane only** — the subset adopted from `azdata`. The CRUD
plane came from elsewhere in this repository and is recorded separately below.

Upstream paths are relative to
`hillclimber/components/data_connector_library/src/azdata/` in that repository, at the
revision above. The hash is the full SHA-256 of the upstream file as it stood when this
copy was taken, so a silent upstream edit is detectable.

**Only `core/envelope.py` is byte-identical to its original.** Everything else differs —
in most cases only by an import path or a docstring, but a file whose docstring was
rewritten is adapted, not verbatim, and is recorded as adapted.

| This repository | Upstream file | Upstream SHA-256 | State |
| --- | --- | --- | --- |
| `core/envelope.py` | `core/envelope.py` | `7674627d8625793cf343e5ab5a99f4d5805fafe8591c0492d215ef30135b1a23` | **verbatim** |
| `core/optional.py` | `core/optional.py` | `d51a56c01431038712420d6daa06a35e15f364c96c0c2a1daa2d98009eb7bd3d` | adapted |
| `core/discover.py` | `core/discover.py` | `35b8a646425e77187b97faa3fdacdf04c70aa16a2fa9cf369dbd9a82ed4dc60e` | adapted |
| `core/content.py` | `core/content.py` | `0afa21ec3bcc4ad94170b65d42c314d2a7d5e10ac11c8e002fad11c0ffd5fc7a` | adapted |
| `kusto/read.py` | `kusto/read.py` | `656241d1bf7f8f896b3190a4f72bf2c16006cc21563ba64f8fc314353aa80703` | **partial** |
| `kusto/content.py` | `kusto/content.py` | `86183651e0dc1825af15b285daa6ef8975fd2f150a209b1b04bda75a26e0a460` | adapted |
| `search/content.py` | `search/content.py` | `9b2e426a427043e96be6749d7c4927a8a41ee3866a23a1a0d64a665bb1ba4602` | adapted |
| `__init__.py` | `__init__.py` | `5e84776cdfbf07a2fd38d549b0e71a3618478941fa56e03fdfcc6e00ad3759fc` | rewritten for the subset |
| `kusto/metadata.py` | — | — | **new here** |
| `graph/content.py` | — | — | **new here** |
| `core/__init__.py`, `kusto/__init__.py`, `search/__init__.py`, `graph/__init__.py` | — | — | **new here** (one-line barrels) |

## What "adapted" means, per file

Nothing below changes behaviour except where stated.

- **`core/optional.py`** — `KNOWN_DISTRIBUTIONS` reduced from sixteen entries to the
  three modules this subset can actually reach (`azure.core.exceptions`,
  `azure.kusto.data`, `azure.search.documents`). Retaining thirteen entries for SDKs no
  copied module loads would advertise a surface that does not exist. Docstring reference
  to the upstream selftest path removed. Logic untouched.
- **`core/discover.py`** — absolute `azdata.core.*` imports rewritten as relative.
  `build_discovery_registry` **removed**: it imports five service discoverers
  (`arm`, `cosmos`, `gremlin`, `kusto`, `search`) that were not adopted, so a copy would
  not import. Omitted rather than stubbed — a factory that can build nothing is worse
  than an absent one. `Discoverer`, `DiscovererRegistry` and every other export kept.
  Two docstring lines referencing upstream invariant numbering reworded.
- **`core/content.py`** — imports rewritten as relative; the blob-centric wording in the
  module header generalised. **Behaviour changed here, deliberately** — see "The sample
  bounds are this repository's" below.
- **`kusto/read.py`** — **partial copy.** Only `shape_kusto_response` is kept.
  `KqlConnector` and `KqlTarget` are omitted because CyberEye already owns its ADX query
  path (`kusto/connector.py` here, `app/cybereye/backend/adx_service.py`)
  and a second gated connector would be a second place for the read-only gate to drift.
  Omitting them also drops the transitive need for `core/breaker.py`, `core/config.py`
  and `core/guardrails.py` — about 1,070 lines with no caller here.
- **`kusto/content.py`** — imports rewritten as relative. One method added: `close()`,
  which closes the cached `KustoClient` objects. Upstream leaves them open for the
  process lifetime; this application closes its readers on shutdown alongside the
  existing `ReadOnlyAdx.close()`. `rows()` now calls `normalize_sample` and reports its
  notes; the `take {max_rows}` query is unchanged — see the truncation note below.
- **`search/content.py`** — imports rewritten as relative; `documents()` calls
  `normalize_sample` and reports its notes. Otherwise identical.
- **`kusto/read.py`** — one docstring line repointed in 2026-09-07 when the ADX query path
  moved into this package. Code untouched.

## The CRUD plane is this repository's, not upstream's

Added **2026-09-07**. None of it came from `azdata`; upstream's write and deploy planes were
deliberately not taken, and still are not — see "What was deliberately not taken".

These files were moved here from `app/data/data_connectors/`, where they were written for
this repository's two data pipelines. They arrived **byte-for-byte identical** to the modules
they were moved from, because the move was a change of ownership rather than of behaviour.
That origin directory was deleted on 2026-09-07 once every consumer import had moved, so the
surviving guard is an API contract, not a diff:
`app/components/tests/test_connector_library_contract.py` freezes the public signatures and
the exported names the old barrels carried.

| This repository | Moved from | State |
| --- | --- | --- |
| `kusto/client.py` | `app/data/data_connectors/adx_connector/client.py` | verbatim |
| `kusto/config.py` | `…/adx_connector/config.py` | verbatim |
| `kusto/connector.py` | `…/adx_connector/connector.py` | verbatim |
| `kusto/crud.py` | `…/adx_connector/crud.py` | verbatim |
| `kusto/errors.py` | `…/adx_connector/errors.py` | verbatim |
| `kusto/identifiers.py` | `…/adx_connector/identifiers.py` | verbatim |
| `kusto/ingest.py` | `…/adx_connector/ingest.py` | verbatim |
| `kusto/models.py` | `…/adx_connector/models.py` | verbatim |
| `kusto/provision.py` | `…/adx_connector/provision.py` | verbatim |
| `kusto/retry.py` | `…/adx_connector/retry.py` | verbatim |
| `kusto/schema.py` | `…/adx_connector/schema.py` | verbatim |
| `graph/connector.py` | `…/gremlin_connector/connector.py` | verbatim |

Azure AI Search CRUD was **not copied at all**. `SearchIndexClient` and its values are
re-exported from `app/components/azure_search`, which keeps the single implementation, its
contract and its own `PROVENANCE.md`. `app/components/tests/test_connector_library_surface.py`
asserts object identity and that no second write path was defined here.

`__init__.py` was rewritten again to carry both planes. Its lazy export map exists so that the
read plane's promise — that importing this package costs the standard library and nothing
else — survives the arrival of modules that import `azure-kusto-data` at module scope.

`graph/control.py` was consolidated here on 2026-09-08 from the two identical pipeline
`arm.py` implementations. Cosmos request shapes and public pipeline imports are retained;
transport, path encoding and bounded polling now reuse `app.components.azure_arm`.
Both pipeline modules are compatibility exports, not independent copies. Offline tests cover
create/existing paths and matching failures; no provisioning was performed during maintenance.

## The sample bounds are this repository's

Upstream's `normalize_rows` ran every cell through `sanitize_detail` — the *error*
formatter, which strips URL-shaped tokens and cuts at 500 characters. Applied to data it
rewrites evidence: a preview of a proxy log answered `GET <redacted-url> HTTP/1.1`, and a
600-character value came back as 500 with `truncated: false`. Content that has been
rewritten and reported as original is worse than content that was refused.

What is here instead:

- `_cell` coerces and may **shorten**, and nothing else. A shortened cell carries
  `… [N more characters not shown]` so a copied value cannot be mistaken for the whole
  one. `sanitize_detail` still formats `detail` and `error`, which are exception text.
- `ContentBounds.max_bytes` is now enforced. Upstream declared 1 MiB and never applied it
  to rows, so a row bound of 100 did not bound 100 rows of 1,000 wide columns.
  `normalize_sample` measures the serialized UTF-8 size of each normalized row and stops
  when the budget is spent — always returning at least one row, so a fat row previews
  rather than disappearing.
- `max_columns` (512) bounds width, which a row bound cannot.
- `RowSample.notes` and `ContentPayload.notes` carry, in a reader's words, every bound
  that made the sample lossy. They surface on the wire as `ContentResponse.sampleNotes`.

`normalize_rows` is kept as the three-value form of `normalize_sample` so a caller that
only wants rows, columns and a boolean is unaffected.

## What is new

`graph/content.py` and `kusto/metadata.py` are written here and adopted from nothing.

Upstream's Gremlin read plane authenticates with an Entra token; that path is
**unverified in this tenant**. The only Cosmos DB for Gremlin access this repository has
proved is an ARM `readonlykeys` lookup performed at runtime with the ambient identity,
which `app/cybereye/backend/graph_service.py` already implements. `GraphReader` therefore
adopts the *shape* — `ContentBounds` in, `ContentResult` and the six statuses out — and
takes its transport by injection, so the proven auth path stays where it is proved.

`kusto/metadata.py` exists because the content plane samples rows and cannot say how many
the table holds: a preview that cannot say "25 of 15,520" is a page with no scale.

## Truncation, honestly

`KustoReader.rows()` issues `take n`, so a table with more than `n` rows returns exactly
`n` and `ContentResult.truncated` is `False`. That is upstream behaviour and it is kept
verbatim. The inventory service that calls it compares the sample size against the row
count it read separately and reports truncation from that comparison, which is strictly
more informative than a boolean. `SearchReader.documents()` and `GraphReader.elements()`
both request `n + 1` and so report truncation directly.

## What was deliberately not taken

The write plane (`SearchDocuments`, `CosmosItems`, `GremlinElements`, `BlobObjects`),
the deploy plane (every `*Provisioner`), the observe and verify planes, the estate and
ARM browsing planes, the `live` topology module, and the blob, cosmos, logs, registry
and `fabric_graph` connectors. This repository's inventory is read-only over three named
coordinates; a mutation surface no caller may use is a liability, not a spare part.

Upstream's own tests were not copied either. They are written for `pytest` with
`asyncio_mode = auto` against the full package; this repository runs `unittest` and
carries its own tests for the subset in `app/components/tests/test_data_connector_library.py`.

None of this changed when the CRUD plane arrived. The ADX and Gremlin connectors here are
this repository's own code and share no line with upstream's write plane.

## Retained notices

The upstream package carries no licence header, no copyright notice and no `LICENSE`
file in the component directory. Nothing was stripped. Every module docstring — the part
that explains *why* each mechanism is shaped the way it is — is retained, which is the
material worth keeping.

## Re-checking this record

```bash
UP=/home/hanchoong/azure-agent-loop/hillclimber/components/data_connector_library/src/azdata
sha256sum "$UP"/core/{envelope,optional,discover,content}.py \
           "$UP"/kusto/{read,content}.py "$UP"/search/content.py "$UP"/__init__.py
```

A hash that no longer matches means upstream moved; it does not mean this copy is wrong.
Decide deliberately whether to re-adopt. Nothing in this repository reads that path at
build time, at test time or at run time.
