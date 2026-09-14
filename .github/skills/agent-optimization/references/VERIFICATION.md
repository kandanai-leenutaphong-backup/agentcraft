# Verify The Independent Copy

Packaging verification needs no live model, cloud login, dataset or source repository. It creates
files only in an explicitly new extraction directory. Runtime sandbox and terminal execution are
Linux-oriented; other platforms are unverified.

## Pack Integrity

From the skillpack directory:

```bash
python3 -B scripts/skillpack.py verify
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B scripts/skillpack.py extract --destination /tmp/agent-optimization-reference
```

Expected: verified payload, nine passing pack/builder tests, then a new extraction. Choose
another destination if it already exists; the extractor never merges into or overwrites an
existing tree. Manifest/payload hashes establish internal consistency, not a publisher signature.

## Python Runtime

The portable package is the same source the archive carries. Run its suite in place, with the
declared shared packages importable:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m pytest python/agent_optimization/tests -q -p no:cacheprovider
```

From an extraction, put `runtime/` on the path instead:

```bash
cd /tmp/agent-optimization-reference/runtime
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$PWD" python3 -m pytest agent_optimization/tests -q -p no:cacheprovider
```

Tests require `pytest` and the declared `situation_detector` and `copilot_terminal` packages in
the chosen Python environment. Install those from their own skill directories when needed;
do not resolve them through an unrelated application checkout. No test calls a hosted model
or imports a host application.

## Frontend Dependency Closure

The archive ships a small dependency manifest for compiling the copied UI, not a publication
manifest and not a lockfile from another project. These commands install into the extraction only,
and need network access. Set `SOURCE_CODE_SKILL` and `TERMINAL_SKILL` to the absolute installed
directories of the `source-code` and `ghcp-cli-frontend` skills. These are declared frontend peers,
not copies inside this archive; no private package registry is required.

```bash
cd /tmp/agent-optimization-reference/runtime
npm install --ignore-scripts --install-links --no-save \
	"${SOURCE_CODE_SKILL:?set the installed source-code directory}" \
	"${TERMINAL_SKILL:?set the installed ghcp-cli-frontend directory}"
./node_modules/.bin/tsc -p frontend-check.tsconfig.json
./node_modules/.bin/vite build --config frontend-check.mjs --logLevel warn
```

The output is an ES-module optimizer library and CSS under `dist-skillpack-check/`. Dependencies
listed in `component-package.json` remain external host dependencies, including the terminal and
source viewer. They are typechecked against their actual packages, not stub declarations, and
are not bundled into the generated library. A complete application shell is not included.

## Observed 2026-09-14

Run offline, from this skill directory:

| Check | Command | Result |
| --- | --- | --- |
| Pack integrity | `python3 -B scripts/skillpack.py verify` | verified, 53 files including license notices |
| Pack/builder tests | `python3 -B -m unittest discover -s tests -p 'test_*.py' -v` | 9 passed |
| Extraction, positive | `scripts/skillpack.py extract --destination <new-directory>` | extracted, 53 files plus the written manifest |
| Extraction, negative | same command repeated | refused: destination already exists, exit 2 |
| Portable optimizer suite | `python3 -m pytest python/agent_optimization/tests -q -p no:cacheprovider` | 63 passed |
| Frontend dependency closure | install the two declared local peers with the command above | passed; actual packages, no type stubs |
| Frontend typecheck/build | `tsc -p frontend-check.tsconfig.json` and `vite build --config frontend-check.mjs` | passed; peer packages remain external |

Not verified here: sandbox execution under Bubblewrap, native CLI sessions, any model call,
and a host application's deployed or browser behavior. No optimization campaign was run.

## Provenance And License

The payload is built from this skill's own sources by `scripts/build_snapshot.py`, which reads
`assets/sources.json`. It carries no host application, customer configuration, deployment runbook,
dataset, credential, cloud target or third-party component clone, and records no source repository
revision. `situation_detector` and `copilot_terminal` are declared dependencies installed from
their own packages rather than vendored here.

`runtime/LICENSE` carries the existing repository MIT notice for its authored sources. External
dependencies retain their own terms and are not relicensed by the pack. Hashes prove archive
consistency, not authorship or rights to a host's data, supplied tools or additional assets.
