# Extraction Result Contract

The retained CU adapter is callable for one authorized input PDF and one new output directory:

```bash
uv run --frozen --project testbeds/datacrafting/content-understanding python testbeds/datacrafting/content-understanding/pipeline.py --input PDF --output NEW_DIRECTORY
```

Paths are resolved by the CLI, not inferred from the working directory. Pipeline
re-runs use a new directory; do not overwrite earlier evidence. Batch processing
calls this same interface once per document. Cloud CLIs invoke deployed,
authenticated Azure Functions and retrieve the resulting artifacts; they must not
silently fall back to a direct local SDK call and label it an Azure Function run.

## Receipt

Every attempted extraction writes `receipt.json`. Required shape:

```json
{
  "schema_version": 1,
  "method": "content-understanding",
  "execution": "azure-function",
  "status": "succeeded",
  "input": {
    "file": "trip-of-murray-5b2-330kv-busbar.pdf",
    "sha256": "actual-input-sha256",
    "bytes": 623685,
    "pages": 6
  },
  "started_at": "RFC3339 UTC timestamp",
  "elapsed_seconds": 1.0,
  "versions": {"python": "actual", "package": "actual"},
  "provider": {"api_version": "2025-11-01", "model_id": "prebuilt-layout"},
  "outputs": {
    "text": "content.txt",
    "markdown": "content.md",
    "native": "native.json"
  },
  "warnings": [],
  "error": null
}
```

Values above illustrate the format, not measured results. Active execution is
`azure-function`; archived local receipts retain their historical `local` value.
Status is `succeeded`, `failed` or `unavailable`. Pages may be
null when not observed. Native model/API identifiers and installed dependency
versions are recorded, not guessed. An error is a bounded, credential-free object
with `type` and `message`. A failed attempt exits nonzero; it is not an empty success.

`outputs` paths are relative to the receipt directory and must stay inside it.
Unavailable formats are null. A success must contain nonempty extracted text and
native evidence. Retain complete provider response JSON for cloud services. Local
converters preserve their native representation and metadata, rather than inventing
page coordinates or confidence values. Do not send PDF payloads to logs.

Raw text is the provider's content, not a repaired synthesis. Markdown is retained
separately where supported. Additional pages, images, table HTML/CSV, SDK metadata,
timing detail and usage may be kept beside the required files. Embellished figure
descriptions or model-generated summaries must be identified as generated content.

## Historical Comparison

The multi-method executable and competing raw results are retired. Frozen counters,
hashes, narrative and source renders remain in [selection evidence](content-understanding/evidence/selection/PROVENANCE.md).
Current verification checks only the two fixed CU receipts, complete native results,
GA analyzer identity and source facts; it has no baseline runtime dependency.

Only compare receipts whose input hashes match `source_data/manifest.json`.
Measured output size is not accuracy. Report source-based fact probes, omissions,
layout/table behavior, traceability and baseline-normalized coverage independently.
Provider confidence is not a universal calibrated quality score. Any cost not
measured from supported usage/pricing evidence is unknown, not zero.