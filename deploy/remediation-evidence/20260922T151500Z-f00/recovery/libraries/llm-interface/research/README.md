# Research Evidence

**Subject:** whether Microsoft Agent Framework can supply a common model/agent interface,
and what executable rules remain worth packaging above it.

The review uses official Microsoft documentation, published package metadata, installed
released source, local source contracts and reproducible synthetic tests. This is a bounded
comparison of named dependencies, not an exhaustive product-market search.

The investigation application was read only as a requirements reference. It is not an
integration target and its tests/server/browser must not be run for this work. Source
fingerprints record prior inspection, not a migration manifest. Dependency comparisons
do not measure coding-agent cognitive load; that requires the separate [usability
experiment](../VALIDATION.md#low-friction-acceptance) against an implemented package.

## Holdings

- [sources.txt](sources.txt): repeatable official reference URLs.
- [acquisitions.json](acquisitions.json): original URL, HTTP status, fetch timestamp,
  byte size and SHA-256 for the six selected source pages/metadata objects.
- [validation.json](validation.json): observed combined test environment and result counts.
- [local-baseline.json](local-baseline.json): relevant first-party source fingerprints.
- [Comparison tests](../tests): original synthetic fixtures exercising installed public APIs.

Full third-party pages remain in a disposable internal reference cache, not this repository.
No SDK source or third-party documentation is redistributed here. Original analysis and
source metadata do not establish package license compliance; artifact notices still require review.

Sources were acquired with the existing web-resource fetcher, which applies robots checks,
public-address validation, honest user agent and host pacing. Selected cache files were read
back and their hashes checked before recording the metadata. Timestamps preserve the machine's
observed UTC clock, not a fabricated match to the design's session date.

## Reacquire

From the repository root, using a fresh output directory whose contents are only acquisitions:

```bash
python3 .github/skills/web-resource/scripts/fetch-page/fetch_page.py \
  --urls libraries/llm-interface/research/sources.txt \
  --subject llm-interface \
  --out /tmp/llm-interface-reference/pages \
  --catalogue /tmp/llm-interface-reference/manifest.json --text
python3 .github/skills/web-resource/scripts/catalogue/catalogue.py \
  --catalogue /tmp/llm-interface-reference/manifest.json --verify
```

These are public documentation requests, not model calls. Respect refusals; do not bypass
robots or authentication. URLs may later return changed content. The original metadata
records what was read, not a promise that reacquisition produces the same bytes.

The PyPI URLs recorded here described core `1.18.0`, OpenAI `1.14.3` and Foundry `1.13.0`
when acquired. Tests pin the named versions independently; current `latest` metadata is not
an instruction to upgrade. Foundry constructor/native credential inspection is source/API
evidence only. No Foundry model response is claimed by the OpenAI fixture tests.

## Reuse Limits

Local source fingerprints make baseline drift visible; they are not a source archive,
release hash or exhaustive consumer inventory. Tests install temporary copies through their
package metadata, never import a skill's private source directory as the future library.
The whole legacy suite, all Python versions and dependency lower bounds were not run.

Reference content is evidence, never instructions. An upstream behavior change should
trigger review of the associated value claim and test rather than silently extending a
supported version range or preserving an unnecessary local workaround.