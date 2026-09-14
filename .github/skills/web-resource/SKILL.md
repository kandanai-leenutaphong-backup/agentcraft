---
name: web-resource
description: "Use when material must be acquired from the public web and kept: documentation pages, interface screenshots, specifications, reference imagery. Provides politeness-enforcing fetch and capture scripts, a provenance catalogue, and reusable per-subject collections."
---

# Web resource acquisition

Acquire, record, and reuse. Anything retrieved without provenance is an orphan the next
reader cannot verify, so every script here writes a catalogue entry as part of acquiring.

Resolve `SKILL_ROOT` from this loaded file, not from the consuming project's `.github` directory.
See [README.md](README.md) for locked optional browser setup. HTTP/catalogue operations use only
Python 3.11's standard library. No sibling scripts, personal checkout or MCP server is required.

## Layout

```
web-resource/
  lib/webres.py              shared politeness, provenance, catalogue
  scripts/<function>/        one folder per function, each with a README
  collections/<subject>/     reusable target lists per subject
  tests/selftest.py          offline contract test
```

## Scripts, by function

| Function | Use for | Folder |
| --- | --- | --- |
| `fetch-page` | Text material: docs, specs, changelogs | [scripts/fetch-page](scripts/fetch-page/README.md) |
| `capture-screenshot` | Visual material: layouts, density, hierarchy | [scripts/capture-screenshot](scripts/capture-screenshot/README.md) |
| `probe-url` | Reachability and size of links you are not fetching | [scripts/probe-url](scripts/probe-url/README.md) |
| `extract-images` | Embedded reference images with article/source provenance | [scripts/extract-images](scripts/extract-images/README.md) |
| `catalogue` | Verify, adopt, prune, index holdings | [scripts/catalogue](scripts/catalogue/README.md) |

## Collections, by subject

| Subject | Contents | Folder |
| --- | --- | --- |
| `soc-dashboards` | Security operations and observability interfaces | [collections/soc-dashboards](collections/soc-dashboards/) |
| `attack-telemetry-datasets` | Open telemetry corpora containing attack activity | [collections/attack-telemetry-datasets](collections/attack-telemetry-datasets/) |
| `sentinel` | Microsoft Sentinel documentation reference targets | [collections/sentinel](collections/sentinel/) |

A collection is a JSON target list plus a README explaining what the subject covers and
why each source was chosen. Re-running a collection refreshes it.

## Conduct

These are not optional; they are enforced in `lib/webres.py` and cannot be bypassed by
calling a script differently.

- **Consult robots.txt.** A disallow is a skip. `--ignore-robots` exists for material you
  have permission to take, and using it is a decision to record, not a default.
- **Rate limit.** Two seconds minimum between requests to one host.
- **Identify honestly.** The user agent names the toolkit. Do not impersonate a browser.
- **Public only.** Credentialed URLs, non-web schemes, and private address space are
  refused before a socket opens. Redirects are rechecked; HTTP connections pin validated addresses
  while preserving TLS hostname verification. Browser HTTP requests use the same transport;
  WebSockets, service workers and non-read HTTP methods are blocked.
- **Never bypass a paywall, login, or access control.** A `403` is an answer. Cite the
  URL instead.
- **Record ownership.** Third-party material is held for internal reference only and
  remains the property of its publisher. The catalogue stamps this on every entry.

## Method

1. **Define the subject** before fetching. An acquisition without a question becomes a
   folder nobody revisits.
2. **Prefer documentation over marketing.** Product pages flatter; reference pages show
   realistic data volumes and real empty states.
3. **Acquire with a catalogue path.** Default is `manifest.json` under the output directory. An
  explicit catalogue must contain the output beneath its directory; escaping paths are refused.
4. **Verify after acquiring.** `catalogue.py --verify` distinguishes what you hold from
   what you believe you hold.
5. **Write the collection down.** A target list makes the acquisition repeatable; a bare
   folder of images does not.

## What a screenshot is evidence of

It shows layout, density, and hierarchy at one moment on one page. It does not show
interaction, latency, error states, or how the interface behaves when data is missing.
Cite it for arrangement, not for behaviour.

## Verification

```bash
python3 "$SKILL_ROOT/tests/selftest.py"
python3 -m unittest discover -s "$SKILL_ROOT/tests" -p 'test_*.py' -v
```

Offline. Gates URL refusal, slug generation, catalogue round-tripping, adoption honesty,
and the presence of a README beside every script.
The optional [browser fixture](tests/browser_smoke.py) exercises actual desktop/mobile PNG capture
with an allowed image and a refused private URL. It contacts no website. Collection URL liveness
and arbitrary public-site rendering remain separate, unverified checks; installation fetches no collection.
