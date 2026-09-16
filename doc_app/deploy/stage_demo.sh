#!/usr/bin/env bash
# Build the GridIQ kiosk demo and stage it into the site's public tree at /demo/.
#
# It is served as its own full-page route, with a slim site bar injected so a
# visitor can get back to the writeup without a browser Back press.
#
# The demo source is read-only here. Everything the gated site needs that the
# stock kiosk build does not provide — a /demo/ base path, no third-party
# requests — is applied to the built output, not to the source.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEMO_SRC="${DEMO_SRC:-$ROOT/demo/app/frontend}"
STAGE="$ROOT/docs/public/demo"

export PATH="$HOME/.local/node22/bin:$PATH"

[[ -d "$DEMO_SRC" ]] || { echo "demo source not found: $DEMO_SRC" >&2; exit 1; }

echo "==> building kiosk bundle"
( cd "$DEMO_SRC" && VITE_KIOSK_MODE=true VITE_API_URL=/api npx vite build --base=/demo/ >/dev/null )

echo "==> staging into $STAGE"
rm -rf "$STAGE"
mkdir -p "$STAGE"
cp -r "$DEMO_SRC/dist/." "$STAGE/"

python3 - "$STAGE" <<'PY'
import re
import sys
from pathlib import Path

stage = Path(sys.argv[1])
index = stage / 'index.html'
html = index.read_text()
before = len(html)

# Microsoft Clarity: telemetry to a third party from confidential content.
html, clarity = re.subn(r'<script[^>]*clarity\.ms.*?</script>', '', html, flags=re.S)
html = re.sub(r'<script(?![^>]*\bsrc=)[^>]*>(?=[^<]*clarity).*?</script>', '', html, flags=re.S)

# Google Fonts: replaced by the same families, served from this origin.
html, preconnect = re.subn(r'<link[^>]*fonts\.(googleapis|gstatic)\.com[^>]*>', '', html)

local_fonts = """<style>
@font-face{font-family:'IBM Plex Sans';font-style:normal;font-weight:100 700;font-display:swap;src:url('/fonts/ibm-plex-sans-var.woff2') format('woff2')}
@font-face{font-family:'IBM Plex Mono';font-style:normal;font-weight:400;font-display:swap;src:url('/fonts/ibm-plex-mono-400.woff2') format('woff2')}
@font-face{font-family:'IBM Plex Mono';font-style:normal;font-weight:600;font-display:swap;src:url('/fonts/ibm-plex-mono-600.woff2') format('woff2')}
</style>"""
html = html.replace('</head>', local_fonts + '</head>', 1)

# A slim bar in the site's own palette, so the demo reads as part of the site
# rather than a separate application. The kiosk shell sizes itself with
# `h-screen`, so that is reduced by the bar height to avoid a scrollbar.
SITE_BAR_CSS = """<style>
:root{--site-bar:44px}
@font-face{font-family:'IBM Plex Sans';font-style:normal;font-weight:100 700;font-display:swap;src:url('/fonts/ibm-plex-sans-var.woff2') format('woff2')}
body{padding-top:var(--site-bar)}
.h-screen{height:calc(100vh - var(--site-bar))}
.site-bar{position:fixed;top:0;left:0;right:0;height:var(--site-bar);z-index:2147483000;
  display:flex;align-items:center;gap:18px;padding:0 20px;box-sizing:border-box;
  background:#171a1f;border-bottom:1px solid #3a424b;
  font-family:'IBM Plex Sans',Segoe UI,system-ui,sans-serif}
.site-bar__back{display:inline-flex;align-items:center;gap:8px;text-decoration:none;
  color:#e1e4e7;font-size:14px;font-weight:600;padding:6px 12px;
  border:1px solid #3a424b;background:#22272e;line-height:1}
.site-bar__back:hover{border-color:#71a7c4;color:#71a7c4}
.site-bar__arrow{font-size:15px;line-height:1}
.site-bar__title{color:#7d8794;font-size:13px;letter-spacing:.02em}
.site-bar__tag{margin-left:auto;color:#7d8794;font-size:11px;font-weight:700;
  letter-spacing:.14em;text-transform:uppercase}
</style>"""

SITE_BAR = """<div class="site-bar">
<a class="site-bar__back" href="/"><span class="site-bar__arrow">&#8592;</span> Overview</a>
<span class="site-bar__title">Azure-Native Agentic Hillclimbing &middot; GridIQ demo</span>
<span class="site-bar__tag">Bundled data</span>
</div>"""

html = html.replace('</head>', SITE_BAR_CSS + '</head>', 1)
html = html.replace('<body>', '<body>' + SITE_BAR, 1)
if 'site-bar__back' not in html:
    print('    !! site bar was not injected')
    sys.exit(1)

index.write_text(html)
print(f'    index.html {before} -> {len(html)} bytes; '
      f'clarity tags removed: {clarity}; google font links removed: {preconnect}')

leaks = sorted(set(re.findall(r'https?://[a-zA-Z0-9.\-]+', html)))
if leaks:
    print('    !! remaining external hosts in index.html: ' + ', '.join(leaks))
    sys.exit(1)
print('    no external hosts remain in index.html')

# A few asset paths are hardcoded root-absolute in the source rather than built
# from Vite's base, so they 404 once the app is served under /demo/.
ROOT_ABSOLUTE = ('"/favicon.png"', '"/images/')
patched = 0
for bundle in sorted(stage.glob('assets/*.js')):
    text = bundle.read_text()
    original = text
    for literal in ROOT_ABSOLUTE:
        text = text.replace(literal, literal[0] + '/demo' + literal[1:])
    if text != original:
        bundle.write_text(text)
        patched += 1
print(f'    rebased root-absolute asset paths in {patched} bundle(s)')

stray = []
for bundle in sorted(stage.glob('assets/*.js')):
    stray += [m for m in re.findall(r'"/[a-z][^"]{0,40}"', bundle.read_text())
              if not m.startswith('"/demo') and re.match(r'"/(images|assets|favicon|fonts)', m)]
if stray:
    print('    !! unrebased asset paths remain: ' + ', '.join(sorted(set(stray))))
    sys.exit(1)
PY

echo "==> staged $(du -sh "$STAGE" | cut -f1)"
