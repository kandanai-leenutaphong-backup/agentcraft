# Webscraper

URL-to-HTML scripts: fast HTTP first, real Playwright Chromium when rendering is needed.
No model account, API key, remote browser service, or server process required.
Canonical source: `core/tools/webscraper`. Reuse the CLI or the `data_collection` Python API;
no demo application is required.

## Run

Requires Linux, Bash, [uv](https://docs.astral.sh/uv/getting-started/installation/),
Python 3.11+ and Chromium's system libraries. From this directory:

```bash
./setup.sh
./scrape.sh https://example.com
./scrape.sh https://quotes.toscrape.com/js/ --wait-for .quote --screenshot
```

[setup.sh](setup.sh) installs the locked Python environment and Playwright's Chromium build.
If Chromium reports missing Linux libraries, an administrator can install them with
`source ./runtime.sh && uv run --locked python -m playwright install-deps chromium`, then rerun setup.
No script requests elevated privileges, configures credentials, or changes browser profiles.

Launch scripts resolve their own directory and can be called from any working directory.
[runtime.sh](runtime.sh) keeps generated files outside the checkout by default:

- Environment: `${XDG_CACHE_HOME:-$HOME/.cache}/harness/webscraper/venv`.
- Saved pages and receipts: `${XDG_STATE_HOME:-$HOME/.local/state}/harness/webscraper/output`.
- Browser test evidence: the same state directory under `webscraper-tests/`.

Override `UV_PROJECT_ENVIRONMENT` for the Python environment, `WEBSCRAPER_STATE_HOME` for
state, or `--out` for one acquisition's output. The old demo environment and captures remain
outside the repository; this tool neither imports nor depends on that old directory.

Each URL prints one JSON receipt with status, method, timings, output paths, errors and
verification result. Exit codes: `0` all acquisitions succeeded, `1` acquisition or
persistence failed, `2` invalid input, `130` interrupted. `--help` lists every option.

```bash
./scrape.sh https://example.com --raw > page.html
./scrape.sh --input urls.txt --out output --concurrency 4
./scrape.sh --input urls.json --mode http
./scrape.sh https://quotes.toscrape.com/js/ --mode browser --wait-for .quote
./scrape.sh https://quotes.toscrape.com/js/ --click '.next > a' --wait-for .quote --screenshot
```

Text input: one URL per line; blank lines and `#` comments are skipped. JSON input:
an array of URL strings. Batch results stream in completion order; duplicate inputs are
preserved. `--raw` accepts one URL and sends its JSON receipt to stderr, HTML only to stdout;
the verified output directory is still written.

## Retrieval strategy

1. Fetch through the shared [web-resource transport](../../skills/web-resource/README.md).
   Decode bounded gzip/deflate bodies and legacy HTML encodings; inspect with Selectolax.
2. Return usable source HTML without launching Chromium. Retry transient transport/server
   failures with jitter and respect `Retry-After` within the active time budget.
3. In `auto`, render script shells, missing readiness selectors, explicit browser actions,
   screenshots and retryable HTTP failures. `http` never launches a browser; `browser` always does.
4. Reuse Chromium across the batch but create a fresh isolated context per URL. Reuse the
   initial HTTP document instead of downloading it twice. Block unnecessary media; images/fonts
   are loaded when a screenshot is requested.
5. Wait for readiness, run requested actions, allow a bounded DOM quiet period, then capture
   the rendered DOM. Save artifacts and read back their hashes before reporting persistence success.

`--wait-for` is a CSS presence check, not a promise that all future requests have finished.
In auto mode an existing selector can satisfy the HTTP path. Use `--mode browser` to require
browser-side waiting. Repeated matches are accepted; readiness waits for the first match.

## Browser actions

`--click CSS` is repeatable. `--actions` accepts a JSON file containing ordered actions:

```json
[
  {"kind": "click", "selector": ".next > a"},
  {"kind": "wait", "selector": ".quote"},
  {"kind": "scroll", "pixels": 720}
]
```

File actions run first, followed by `--click` actions, readiness, and DOM settling.
Clicks require one unambiguous element; wait actions require the first match to be visible.
At most 30 actions; each scroll is between -5000 and 5000 pixels, excluding zero.
Actions are explicit, not LLM-generated; there is no automatic form filling or arbitrary script API.
`--headed` shows Chromium when a graphical display is available. Headed operation is not
verified in the current headless environment. `--browser-executable` selects an existing Chromium.

## Output and verification

Each acquisition has a unique directory under the configured output root; repeated runs
never overwrite it. The shell launcher defaults to the external state directory above;
invoking `collect-html` directly instead defaults to `./output` unless `--out` is provided.

- `page.html`: successful HTML snapshot, UTF-8 with BOM for legacy-encoding compatibility.
- `source.html`: decoded initial HTTP source, when a successful HTTP fetch needed rendering.
- `screenshot.png`: optional 1440x1000 viewport capture, not a full-page screenshot.
- `result.json`: outcome, original/final URL, timestamp, title, request attempts, options and warnings.
- `manifest.json`: completion marker, provenance and SHA-256 hashes; published after artifact writes.

A failed acquisition writes its receipt, not a success HTML file. An interrupted write may
leave an incomplete directory; absence of the final manifest makes verification fail.
`verified: true` means saved artifacts match their manifest, not that acquisition succeeded.
Check `ok`, `warnings` and `blocked_requests` too. A manifest proves integrity relative to its
recorded hashes, not publisher authenticity or protection from deliberate rewriting.

```bash
./scrape.sh --verify /absolute/path/from/receipt
```

Use the actual `directory` from a receipt. Verification is offline and reports both `ok`
(artifact integrity) and `acquisition_ok` (the recorded retrieval outcome).

## Python API

From this directory, use the same external environment as the launch scripts:

```bash
source ./runtime.sh
uv run --locked python
```

The existing package name `harness-data-collection`, `data_collection` imports and
`collect-html` command remain unchanged. Keep the sibling `core/skills/web-resource`
package available when reusing this source checkout; the dependency is declared in
[pyproject.toml](pyproject.toml), not copied into the scraper.

```python
import asyncio
from os import environ
from pathlib import Path
from data_collection import ScrapeOptions, Scraper
from data_collection.storage import save_result

output_root = Path(environ["WEBSCRAPER_STATE_HOME"]) / "output"

async def main():
    options = ScrapeOptions(wait_selector=".quote")
    async with Scraper(options) as scraper:
        result = await scraper.fetch("https://quotes.toscrape.com/js/")
        if not result.ok:
            raise RuntimeError(f"{result.error_code}: {result.error}")
        directory = await asyncio.to_thread(save_result, result, output_root, options)
        print(directory)

asyncio.run(main())
```

`fetch()` returns HTML in memory. `fetch_many(urls)` is a bounded async iterator; saving is
explicit in the Python API. The CLI calls the same service and saves every result automatically.

## Large documentation collections

[corpus.sh](corpus.sh) composes the same scraper with pinned public Git source acquisition,
optional Git LFS expansion, file hashes, SQLite full-text search and feature-family reports.
No downloaded code or notebooks are executed. The collection root belongs to the caller and
should be ignored by Git before acquisition; the Foundry collection uses `docs/msft_foundry_kb`.

From the harness repository root:

```bash
./core/tools/webscraper/corpus.sh repositories --root docs/msft_foundry_kb
./core/tools/webscraper/corpus.sh discover --root docs/msft_foundry_kb
./core/tools/webscraper/corpus.sh pages --root docs/msft_foundry_kb
./core/tools/webscraper/corpus.sh index --root docs/msft_foundry_kb
./core/tools/webscraper/corpus.sh features --root docs/msft_foundry_kb
./core/tools/webscraper/corpus.sh search --root docs/msft_foundry_kb --query '"Foundry IQ"'
./core/tools/webscraper/corpus.sh verify --root docs/msft_foundry_kb
```

`collection.json` at the root declares schema version 1, official repository names, page URLs,
families and optional feature queries. `--plan` selects another plan. Repository resume keeps
the existing commit and refuses mismatched origins or edited source; page resume verifies saved
artifacts, skips recorded failures unless `--retry-failed`, and reacquires corrupted captures.
Skipped failures keep the command's failure status; corrupt extracted text is regenerated from
verified HTML. `discover` adds a finite Microsoft Learn frontier from named source prefixes,
excluding includes and media and deduplicating existing URLs. It never recursively follows the web.
Text indexing is limited to UTF-8 files up to 2 MiB; larger/binary files remain retained and hashed.
LFS pointers and unexpanded submodules are explicit classifications, not completed downloads.
For optional LFS expansion, `corpus.sh lfs --root ROOT --lfs-executable /path/to/git-lfs`
uses a caller-supplied client with local-only filters and verifies declared object hashes.
LFS index differences are accepted only when every changed file matches its pinned HEAD
pointer's SHA-256 and size; genuine edits, deletions and origin mismatches remain failures.
Run `index`, `features` and `verify` after acquisition changes. Feature queries prove retained
evidence, not product availability. Full source commits and acquisition receipts carry provenance.

## Limits and access

- Public, unauthenticated HTTP(S) only. Credentialed URLs, private/mixed-address DNS answers,
  unsafe redirects, robots disallows, access denials and recognized challenge pages are refused.
  No CAPTCHA solver, stealth identity, login/paywall bypass or proxy rotation.
- Robots rules use Protego. Per-host requests keep a two-second minimum spacing and respect
  crawl delay. Concurrency improves multi-host throughput, not permission to overload one host.
- Default bounds: 90 active seconds per URL, 20-second socket timeout, two extra retries,
  four acquisitions, eight HTTP workers, two browser contexts, 80 transport attempts,
  16 MiB per response/DOM and 64 MiB aggregate decoded responses. Limits never silently truncate HTML.
  URL queue time is outside the active budget; transport cleanup may outlast that budget.
- Browser HTTP requests use the guarded transport. WebSockets, service workers, popups and
  non-read HTTP methods are blocked. No authentication cookies are replayed. Apps requiring
  those facilities may not render; blocked requests remain visible in the receipt.
- Redirected subresources are served at their requested URL, with a warning because relative
  imports may behave differently. HTML is a snapshot, not an offline mirror; external assets,
  iframe documents and closed shadow DOM are not bundled into the result.
- Automatic readiness is heuristic. Use site-specific selectors/actions for delayed content.
  No benchmark establishes "fastest" and no scraper can guarantee every site's availability.
- Routing guards are not an OS sandbox. Run untrusted pages with least privilege and suitable
  host/container isolation. Full input URLs are recorded: never put secrets in query strings.

## Ownership and evidence

The acquisition capability is owned by [src/data_collection](src/data_collection), called by
[cli.py](src/data_collection/cli.py) and Python consumers through `Scraper`, `ScrapeOptions`,
`BrowserAction` and the storage API. Configuration enters through `ScrapeOptions`; permission is
the local operator's public-read invocation, not a hosted or multi-user authorization service.
It composes canonical `harness-web-resource`, Playwright, Protego, Selectolax and w3lib;
no copied shared transport, cloud deployment or global client installation.

```bash
./test.sh
```

Verified from `core/tools/webscraper` on Linux, 2026-09-13: 52 acquisition/corpus tests and
nine shared-network tests pass using the external environment,
including real Chromium clicks, scrolling, redirects, isolation, repeated selector matches,
private/write refusals, retries, decoding bounds, CLI output and corruption detection.
Before relocation, live `https://quotes.toscrape.com/js/` acquired through Chromium with a screenshot in 12,737 ms,
seven transport requests, no blocked requests; saved artifacts verified. This is one observed
run, not a throughput benchmark. Tests use local fixtures; live-site checks are separate.