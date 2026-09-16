# Measured Extraction Comparison

Generated from hash-verified source inputs and retained receipts. Lexical recall is not accuracy.

| Document | Method / output | Narrative probes | Diagram labels | Baseline 5-gram recall | Repeated 5-grams | Native tables | Row relationships | Seconds |
| --- | --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| yallourn | pymupdf / text | 16/16 | 1/1 | 100.0% | 13.6% | 0 | not provided | 2.225 |
| yallourn | pymupdf / markdown | 15/16 | 0/1 | 69.9% | 61.2% | 0 | not provided | 2.225 |
| yallourn | markitdown / text | 16/16 | 1/1 | 90.8% | 13.1% | 0 | not provided | 1.397 |
| yallourn | document-intelligence-read / text | 16/16 | 0/1 | 96.0% | 13.4% | 0 | not provided | 13.786 |
| yallourn | document-intelligence-layout / text | 16/16 | 1/1 | 93.6% | 11.7% | 5 | 3/3 | 14.337 |
| yallourn | content-understanding / text | 16/16 | 1/1 | 93.3% | 12.3% | 5 | 3/3 | 11.077 |
| murray | pymupdf / text | 16/16 | 1/1 | 100.0% | 11.7% | 0 | not provided | 1.773 |
| murray | pymupdf / markdown | 16/16 | 0/1 | 67.3% | 60.2% | 0 | not provided | 1.773 |
| murray | markitdown / text | 16/16 | 1/1 | 86.8% | 11.0% | 0 | not provided | 1.122 |
| murray | document-intelligence-read / text | 16/16 | 0/1 | 89.9% | 11.4% | 0 | not provided | 11.679 |
| murray | document-intelligence-layout / text | 16/16 | 0/1 | 87.7% | 9.8% | 3 | 3/3 | 9.528 |
| murray | content-understanding / text | 16/16 | 0/1 | 83.0% | 10.8% | 3 | 3/3 | 7.998 |

## Missing Probe Phrases

- yallourn / pymupdf / markdown: a2-market-notice (source page 6): ['synchronise Jeeralang unit A2'].
- yallourn / pymupdf / markdown: diagram-labels (source page 5): ['Busbar No. 2'].
- yallourn / document-intelligence-read / text: diagram-labels (source page 5): ['Busbar No. 2'].
- murray / pymupdf / markdown: diagram-labels (source page 5): ['Upper Tumut'].
- murray / document-intelligence-read / text: diagram-labels (source page 5): ['Busbar 5B2'].
- murray / document-intelligence-layout / text: diagram-labels (source page 5): ['Busbar 5B2'].
- murray / content-understanding / text: diagram-labels (source page 5): ['Busbar 5B2'].

See comparison.json for each probe, receipt path, version, hash, warnings and preserved failed attempts.
No aggregate quality score, diagram interpretation, price estimate or statistical latency ranking is claimed.
