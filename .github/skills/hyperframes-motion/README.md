# HyperFrames Motion

Portable, bounded local rendering over HyperFrames 0.8.12. Preserves the source authoring/evidence
guidance and adds an explicit-root runner, a dependency lock, safe ZIP extraction helper, parser
tests and a reproducible two-render fixture. No origin checkout or project-specific runner needed.

Resolve `SKILL_ROOT` from the loaded skill. Choose two separate external directories,
`RUNTIME_ROOT` for dependencies/caches and `WORK_ROOT` for compositions/output. Keep both outside
the installed skill. Setup downloads packages/browser binaries, so run it deliberately:

```bash
mkdir -p "$RUNTIME_ROOT" "$WORK_ROOT"
cp "$SKILL_ROOT/package.json" "$SKILL_ROOT/package-lock.json" "$RUNTIME_ROOT/"
HYPERFRAMES_SKIP_SKILLS=1 HYPERFRAMES_NO_TELEMETRY=1 npm ci --prefix "$RUNTIME_ROOT"
NODE="$RUNTIME_ROOT/node_modules/node/bin/node"
python3 "$SKILL_ROOT/tests/selftest.py" --runtime "$RUNTIME_ROOT"
"$NODE" "$SKILL_ROOT/scripts/hf.mjs" --root "$WORK_ROOT" --runtime "$RUNTIME_ROOT" \
  --allow-browser-install -- browser ensure
"$NODE" "$SKILL_ROOT/tests/render_smoke.mjs" --root "$WORK_ROOT" --runtime "$RUNTIME_ROOT"
```

Use Node 22+ for normal operation. The lock includes a Node 22 executable; installation under an
older npm host can emit engine warnings, but the runner refuses to execute HyperFrames under it.
The setup above creates no MCP server or client instructions. The render smoke test intentionally
produces two local MP4s in a scratch work root; it must not target existing user output.

The test runs actual lint/check, verifies 640x360 at 30fps for two seconds, proves sampled frames
are nonblank and moving, and compares decoded RGB bytes across both renders. It retains logs,
sampled PNGs, media metadata and hashes under the work root's `evidence/`. These fixed-format
composition dimensions are not a responsive application UI.

For authoring, use the same command prefix followed by the allowed shapes in
[references/gates-and-evidence.md](references/gates-and-evidence.md). Read the brief and author its
beat map before markup. Use existing local assets and inspect retained frames; successful lint is
not sufficient visual proof. Runtime setup is not authorization for cloud publishing or arbitrary
upstream CLI commands.

[CONTRACT.md](CONTRACT.md) defines boundaries. [GOTCHAS.md](GOTCHAS.md) records the unresolved
upstream dependency advisory. Linux was exercised; Windows and macOS were not.