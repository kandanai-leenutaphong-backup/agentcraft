# Dataset Preparation — worked example

One public incident report page turned into a labeled, scoreable investigation case. The result is
rendered at `/dataset-prep` on the site; this directory is the authority for it.

## Source of record

| Field | Value |
| --- | --- |
| Publisher | AEMO |
| Title | Trip of Yallourn ‘W’ Power Station unit 3 and unit 4 on 16 October 2025 |
| Document type | Reviewable Operating Incident Report under the National Electricity Rules |
| Published | March 2026 (per the report cover page) |
| URL | https://aemo.com.au/-/media/files/electricity/nem/market_notices_and_events/power_system_incident_reports/2025/trip-of-yallourn-w-power-station-unit-3-and-unit-4.pdf |
| Retrieved | 2026-08-24 |
| Page used | 3 of 7 |
| PDF SHA-256 | `1871bf001bc005134c44cd554dbd36b9e27c61ebe8ebe39d178b8025bd8e6c20` |

This is a public AEMO report. No other provenance metadata is recorded, because none is available
from the document itself.

Only page 3 is used. It carries the summary table (incident classification, 597 MW of generation
lost, no customer load lost, the cooling system common to units 3 and 4), the numbered key events
(the 1334.29 and 1334.32 unit trips, the 1350 direction of Jeeralang A2/A3/B3 to manage system
strength, restoration of unit 3 at 1627 and unit 4 at 0152 the next day), and the confirmed
cooling-water isolating valve actuator cause. No fact from any other page is presented as
page-3-derived.

## Layout

```
source/
  trip-of-yallourn-w-power-station-unit-3-and-unit-4.pdf   byte-for-byte copy of the source
  yallourn-report-page-3.png                               page 3 raster (PyMuPDF, 1.6x)
  yallourn-report-page-3.txt                               page 3 text (PyMuPDF), the verbatim reference
artifacts/
  yallourn-w-2025-10-16.case.json                          source metadata, excerpts, four label objects
scripts/
  validate.mjs                                             invariant + verbatim checks (--self-test)
  sync.mjs                                                 copy into the Vocs tree (--check for drift)
  verify-rendered.mjs                                      browser acceptance against a running site
```

## The artifact

`evidence` is a ledger of excerpts transcribed verbatim from page 3, each with a stable ID
(`P3-EVENT-1`, `P3-CAUSE-2`, …) and a numbered marker. `labels` holds exactly four objects:

- `key_events` — the chronology, one entry per event, each citing its excerpts.
- `expected_signal_detection` — the signals that must be raised, and the requirement to classify the
  two trips as **common-mode** rather than independent.
- `expected_next_action` — manage system strength, direct the fast-start Jeeralang units, and
  investigate the shared cooling dependency; customer load shedding is prohibited.
- `expected_analysis` — required chronology, impact, common-cause and restoration claims, plus the
  two claims that must never be made: customer load loss, and a transmission fault as the cause.

Every derived entry carries at least one `source_refs` ID, and every excerpt is used by at least one
label.

## Regeneration

The page raster and text were derived from the local PDF copy with PyMuPDF 1.28.2.
Run these commands from the repository root:

```python
import pymupdf, pathlib
doc = pymupdf.open('doc_app/dataset_prep/source/trip-of-yallourn-w-power-station-unit-3-and-unit-4.pdf')
page = doc[2]  # page 3, zero-indexed
page.get_pixmap(matrix=pymupdf.Matrix(1.6, 1.6), alpha=False).save('doc_app/dataset_prep/source/yallourn-report-page-3.png')
pathlib.Path('doc_app/dataset_prep/source/yallourn-report-page-3.txt').write_text(page.get_text(), encoding='utf-8')
```

## Validation

```bash
node doc_app/dataset_prep/scripts/validate.mjs             # invariants + verbatim source check
node doc_app/dataset_prep/scripts/validate.mjs --self-test # proves a tampered excerpt and a dangling ref are refused
node doc_app/dataset_prep/scripts/sync.mjs                 # copy artifact and source assets into doc_app/docs
node doc_app/dataset_prep/scripts/sync.mjs --check         # SHA-256 drift gate, no writes
```

`validate.mjs` normalizes whitespace and requires every excerpt to occur in the committed page-3
text, requires every `source_refs` ID to resolve, requires every excerpt to be used, and requires
each label group to survive a `JSON.stringify`/`JSON.parse` round trip. `--self-test` tampers a copy
in memory and fails unless both the non-verbatim excerpt and the dangling reference are refused
while the unmodified artifact still passes.

Browser acceptance runs against a served build. It uses the Playwright package already installed
under `doc_app/demo/app/frontend`; nothing is added to any manifest.
Run the following commands in separate terminals, each starting at the repository root.

```bash
cd doc_app && npm run build && npm run preview
cd doc_app/demo/app/frontend && node ../../../dataset_prep/scripts/verify-rendered.mjs http://127.0.0.1:5179/dataset-prep
```

The verifier parses the visible `textContent` of all four rendered JSON regions, deep-compares each
to its artifact object, resolves every rendered source reference to a rendered excerpt, checks for
horizontal overflow and a working full-report link, checks that keyboard focus is visible, and
writes desktop and mobile screenshots to `/tmp`.

## Boundaries

The PDF, PNG and synchronized JSON are static assets. Unlike the prerendered HTML they receive no
identity-script injection, so access control for them depends entirely on the ingress gate. That is
acceptable for this public AEMO source and is **not** a precedent for confidential material.
