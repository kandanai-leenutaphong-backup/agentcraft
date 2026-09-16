# PDF Extraction Assessment

Historical selection narrative, preserved on retirement of competing methods.
Only Content Understanding remains runnable. Original method guides and competing
raw outputs are available only from the [external verified recovery archive](cleanup.json);
[provenance and licensing](PROVENANCE.md) remain local. Relative links below were
relocated; measured claims and the original narrative were not rewritten.

## Decision

**Select Content Understanding `prebuilt-layout` for a Foundry-native prose/table
pipeline on these two reports.** It retains all 32 checked narrative facts, all six
checked native table relationships, all 13 pages, and source coordinates. No language
or embedding model deployment is required for this analyzer.

**Document Intelligence `prebuilt-layout` is an equally credible quality choice.**
It passes the same fact/table checks and preserves more raw-text five-grams in this
sample. A globally more accurate winner is not established. The primary choice
optimizes Foundry-native integration while meeting the measured extraction criteria,
not an invented aggregate accuracy score or a single-run latency advantage.

Use MarkItDown when processing must remain local and page/cell coordinates are not
required. Preserve raw PyMuPDF text and page renders as an independent audit baseline.
Do not use the tested PyMuPDF4LLM Markdown output alone without its coverage fallback.

## Observed Results

All methods ran against the same verified inputs: Yallourn, 7 pages/586,748 bytes;
Murray, 6 pages/623,685 bytes. [Input hashes](../../../source_data/manifest.json).

| Method | Execution | Narrative Facts | Native Row Relationships | Yallourn / Murray Seconds | Recommended Use |
| --- | --- | --- | --- | --- | --- |
| [PyMuPDF](PROVENANCE.md#archived-methods) | local | raw text 32/32 | not provided as table objects | 2.225 / 1.773 | raw text, geometry and source-page audit |
| [MarkItDown](PROVENANCE.md#archived-methods) | local | 32/32 | not provided as table objects | 1.397 / 1.122 | Microsoft local converter; some Markdown tables, no native coordinates |
| [DI Read](PROVENANCE.md#archived-methods) | Azure Function | 32/32 | not provided | 13.786 / 11.679 | OCR text with word/page locations; table relationships not extracted |
| [DI Layout](PROVENANCE.md#archived-methods) | Azure Function | 32/32 | 6/6 | 14.337 / 9.528 | structured document extraction with strong traceability |
| [CU Layout](../../SKILL.md) | Azure Function | 32/32 | 6/6 | 11.077 / 7.998 | native-first Foundry text/table pipeline |

Both layout services emit five native tables for Yallourn and three for Murray.
Those are page-local structures, not a claim that Yallourn contains five distinct
semantic tables. Their native figure regions are retained; figure binaries were
not downloaded. Source-page renders remain available independently.

Complete measurements, variants and exact receipt links are in
[MEASUREMENTS.md](./MEASUREMENTS.md) and
[comparison.json](./comparison.json).

## Source-Based Review

The following source images were viewed, not merely inferred from extracted text:

- [Yallourn page 3](./source-pages/yallourn/page-003.png): 597 MW loss,
  299/298 MW pre-event generation, trips at 1334.29/1334.32, Jeeralang direction at
  1350, synchronisation at 1401/1405, and return times. All narrative probes pass.
- [Yallourn page 4](./source-pages/yallourn/page-004.png): causal and
  security narrative, including 49.91 Hz minimum. Present in every text output.
- [Yallourn page 6](./source-pages/yallourn/page-006.png): the native
  layout tables correctly associate `MN 129720` with `1358 hrs`, `16 October 2025`
  and the Jeeralang A2 direction in one logical row. Both pass all three Yallourn
  row-association probes.
- [Murray page 3](./source-pages/murray/page-003.png): 1008 trip,
  1025 ratings, 1118 restoration, 1120 ratings removal, no generation/load loss,
  and maintenance on the other busbar. All narrative probes pass.
- [Murray page 4](./source-pages/murray/page-004.png): 1370 to 910 MVA,
  two market notices and remedies. Both native layouts retain the correct label
  associations, including spanning rows in DI. All three Murray row probes pass.
- [Yallourn diagram](./source-pages/yallourn/page-005.png) and
  [Murray diagram](./source-pages/murray/page-005.png): labels,
  colored lines and breaker/transformer symbols are visible in the source. The
  extracted words alone do not reconstruct their electrical relationships.

CU often retains a source's logical row as one cell, while DI may split its detail
into several rows with a spanning label. For example, Murray's two main tables
are 11/7 rows in CU and 19/16 in DI. These are different representations, not
evidence that DI invented extra semantic rows. The comparator honors `rowSpan`.

## Quality Gaps

**PyMuPDF4LLM Markdown is unreliable alone on this sample.** Repeated five-grams
are 61.2%/60.2%, versus raw text 13.6%/11.7%. The Yallourn market-notice output
repeats identifiers and dates across columns; one narrative phrase probe fails.
Raw text and unfiltered Markdown were both retained. The local method's own
coverage guard selects the raw fallback for both inputs.

**Lexical misses need adjudication.** The diagram probe expects `Busbar 5B2`;
all three Azure outputs use `Bus bar 5B2`, which is a spacing difference, not a
missing busbar. CU also tokenizes the diagram identifier `652A` as `65 2A`.
`Lower Tumut` and `662A` are present in text/native output for every method.
No lost transmission branch is established by these probes.

**No complete-diagram claim.** Topology, breaker states, line colors and symbols
were not scored. No OCR benchmark for scanned PDFs, model-generated figure
descriptions, arbitrary-document generalization or large-document load test ran.
These two born-digital reports cannot establish such coverage.

**No semantic generation was tested.** CU used GA `2025-11-01/prebuilt-layout`, not
`prebuilt-documentSearch`, custom fields, summaries or embeddings. DI used API
`2024-11-30`. All cloud extraction used managed identity inside actual Azure
Functions; clients did not silently execute the native SDK locally.

## Verification And Cost

- 32 PyMuPDF tests, 16 MarkItDown tests, 32 cloud/deployment offline tests and 17
  comparison tests passed. Failed/partial earlier attempts remain separately recorded.
- Parent integration repeated live authentication/authorization checks, receipt
  integrity, persisted result read-back and idempotency without new extraction jobs:
  [acceptance](../../../deploy/records/20260916T070741387561Z-acceptance.json),
  [access](../../../deploy/records/20260916T070729317256Z-access-verification.json),
  [security state](../../../deploy/records/20260916T070701504318Z-security-readback.json).
- Both source hashes remain unchanged. Results retain Python/package/API versions.
- Actual dollar cost is unknown. CU reports 13 `documentPagesStandard`; DI does
  not return a billing meter in these artifacts. Timings are single observations.
- Dedicated resources remain allocated. Functions/analysis, storage, private
  networking/DNS and logs can charge. [Runbook and exact teardown](../../../deploy/README.md#teardown).
- PyMuPDF/PyMuPDF4LLM have AGPL/commercial licensing implications; no commercial
  entitlement was acquired. MarkItDown is MIT. See each skill's original-source links.

This assessment and the original timestamped spec are the durable experiment record;
no separate notebook installation or duplicate research register was introduced.