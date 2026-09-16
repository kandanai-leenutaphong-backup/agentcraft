# Historical Selection Evidence

Content Understanding GA `2025-11-01/prebuilt-layout` is the only supported
extraction method. This directory preserves the two-document selection evidence;
it is not a five-method runner or a portable skill implementation.

- [Assessment](ASSESSMENT.md): original narrative retained, with relocated links
  and a retirement notice. Historical alternative recommendations are not current
  runnable methods.
- [Measurements](MEASUREMENTS.md) and [comparison.json](comparison.json): frozen
  final comparison, including original receipt paths, versions, hashes and baseline
  counters. Historical paths inside JSON are archive member identifiers relative
  to the testbed, not current filesystem dependencies.
- [probes.json](probes.json): original source-reviewed facts and row associations.
  The retained CU receipt verifier checks these without competing raw outputs.
- [source-pages](source-pages/): original PNG renders and their source/hash receipts,
  relocated without rerendering. Render metadata paths are historical identifiers.
- [Source manifest](../../../source_data/manifest.json): immutable user-supplied
  PDF provenance. [CU results](../../results/) remain in their original directories.

## Archived Methods

PyMuPDF, MarkItDown, Document Intelligence Read/Layout and the comparison runner
are retired. Their source, guides, tests, raw/failed outputs, locks, environments,
dependency license notices and caches are available only in the external recovery
archive named by [cleanup.json](cleanup.json). No Git restore is assumed: these
testbed files were untracked.

Archive members retain repository-relative names under `testbeds/datacrafting/`.
Restore outside the workspace first and verify against the frozen SHA-256 manifest.
Restoring a pipeline does not authorize a paid analysis, cloud mutation or teardown.
Do not restore archived methods into `reference/` or active discovery paths.

## Licensing And Sources

- PyMuPDF, PyMuPDF4LLM and pymupdf-layout 1.28.2: installed metadata identified
  GNU Affero GPL 3.0 or Artifex commercial licensing. No commercial entitlement
  was obtained. Original notices remain in the recovery archive.
  [Official licensing](https://pymupdf.readthedocs.io/en/latest/about.html),
  [PyMuPDF source](https://github.com/pymupdf/PyMuPDF),
  [PyMuPDF4LLM source](https://github.com/pymupdf/pymupdf4llm).
- MarkItDown 0.1.7 and pdfminer.six: MIT per observed distribution metadata.
  [Microsoft license](https://github.com/microsoft/markitdown/blob/main/LICENSE),
  [PDF converter](https://github.com/microsoft/markitdown/blob/main/packages/markitdown/src/markitdown/converters/_pdf_converter.py),
  [retained read-only acquisition](../../../reference/microsoft-data-tools/pages/markitdown.json).
- Document Intelligence used `2024-11-30/prebuilt-read` and `prebuilt-layout`.
  [Official layout documentation](https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/prebuilt/layout?view=doc-intel-4.0.0)
  and [archived deployment references](../../../deploy/references/) retain
  native API provenance. No DI dependency or endpoint remains in the CU runtime.
- AEMO PDFs and derived renders retain their original rights. Input authorization
  permits this experiment, not an inferred redistribution license.
- Ignored legacy sources and documents under [reference](../../../reference/)
  were neither removed nor copied. Original source revision:
  `aba1480d78673494aeace9298184a461149437d7`.

Filesystem retirement is separate from cloud teardown. The retired DI account and
its existing grant remain allocated; exact ownership and approval requirements live
in the [deployment runbook](../../../deploy/README.md).