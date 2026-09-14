# Web Resource

Public page fetch, URL probe, embedded-image acquisition, browser screenshot and local provenance
verification. All five scripts, their guides and three reusable target collections travel with
the skill. The library can also be installed into an application environment as `webres`.

Resolve `SKILL_ROOT` from the loaded skill. Core operations need only Python 3.11+:

```bash
python3 "$SKILL_ROOT/tests/selftest.py"
python3 -m unittest discover -s "$SKILL_ROOT/tests" -p 'test_*.py' -v
python3 "$SKILL_ROOT/scripts/fetch-page/fetch_page.py" --url https://example.com \
  --out "$OUTPUT_ROOT" --text
python3 "$SKILL_ROOT/scripts/catalogue/catalogue.py" --catalogue "$OUTPUT_ROOT/manifest.json" --verify
```

`OUTPUT_ROOT` is an explicit operator-selected acquisition directory, outside the installed skill.
Default provenance is saved beside output; plain-text derivatives are separately catalogued.
Verification reads holdings and reports missing/changed/orphan files without rewriting the manifest.
Adoption/pruning are explicit mutations. Material remains subject to its publisher's rights.

Screenshots use the declared optional Python Playwright extra, not a guessed Node package:

```bash
UV_PROJECT_ENVIRONMENT="$RUNTIME_ROOT" uv sync --locked --no-install-project --project "$SKILL_ROOT" --extra browser --group test
PLAYWRIGHT_BROWSERS_PATH="$BROWSER_ROOT" "$RUNTIME_ROOT/bin/python" -m playwright install chromium
PLAYWRIGHT_BROWSERS_PATH="$BROWSER_ROOT" "$RUNTIME_ROOT/bin/python" -B \
  "$SKILL_ROOT/tests/browser_smoke.py" --out "$EVIDENCE_ROOT"
```

Choose external runtime/browser/evidence directories. `--group test` adds Pillow for pixel checks,
not a production dependency. A live screenshot uses the capture script and the same interpreter;
`--browser-executable` optionally names an existing Chromium binary. No script installs a browser
implicitly. Linux browser execution passed; Windows/macOS remain unverified.

No login/cookie session or access-control bypass is supported. Robots absence (404/410) permits;
unreachable/denied robots refuses. A `403` is not retried through another access path. Browser
subresources use guarded public GET/HEAD and may be blocked; capture provenance records the count.
This is a reference-acquisition tool, not a faithful authenticated-app browser or an OS sandbox.

Contracts: [CONTRACT.md](CONTRACT.md). Limits: [GOTCHAS.md](GOTCHAS.md).
Origin: [PROVENANCE.md](PROVENANCE.md). Collection links are starting points, not newly verified holdings.