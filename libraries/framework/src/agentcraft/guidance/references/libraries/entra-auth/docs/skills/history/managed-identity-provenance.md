# Provenance

This skill maintains the identity and role-assignment templates, verification script and
offline acceptance fixtures as one reusable capability. Targets and principals are supplied by
the consuming deployment. No source repository, customer environment or private revision is an
installation prerequisite. The repository's existing MIT notice travels with this skill.

## Adapted for this harness

The deployment templates and compiled `build/main.json` fixture are kept together. The fixture
is a required test input, not disposable build output; the selftest verifies its expected shape.

| File | Change | Why |
| --- | --- | --- |
| `SKILL.md` | `## Install` no longer says `cp -r bicep-managed-identity <your-project>/`; it states where the harness already put the box, and that deployment goes through the project's `deploy/deploy.sh`. `## Use` notes that `-h` is not a help flag. Prose condensed. | The copy instruction is false here — the installer places it — and a skill directory offering its own operator entry point is what `deployment.instructions.md` forbids. |
| `README.md` | `## 6. Quick start` gains the same placement and single-entry-point sentence above the unchanged commands. Prose condensed. | Same reason; the commands themselves are correct and were left alone. |
| `CONTRACT.md` | Prose condensed. No shape, name, GUID or rule changed. | Harness communication register. |
| `GOTCHAS.md` | Prose condensed. Every cause, fix and rule retained. | Harness communication register. |

This record describes the distribution boundary and does not contain private origin receipts.

## Files

SHA-256 truncated to 16 hex characters: enough to detect drift, short enough to
read. `mode` is the mode the file carries here and the mode the installer must
reproduce in a consumer project — `scripts/` is executable because the box's own
documentation tells an operator to run it directly.

| Path | Mode | SHA-256 |
| --- | --- | --- |
| `.gitignore` | 644 | `73acd966a41cef9e` |
| `CONTRACT.md` | 644 | `ac250cd85148ccc9` (adapted) |
| `GOTCHAS.md` | 644 | `911f415e1dcdd167` (adapted) |
| `README.md` | 644 | `caae3f7501881aa7` (adapted) |
| `SKILL.md` | 644 | `15b223a3e5ee1967` (adapted) |
| `bicep/main.bicep` | 644 | `c616d34df470159d` |
| `bicep/modules/identity.bicep` | 644 | `aece7b775bd6d5e5` |
| `bicep/modules/role-assignment-cognitive.bicep` | 644 | `7891adb08d9b9ad0` |
| `bicep/modules/role-assignment-search.bicep` | 644 | `719e4c8f25fde005` |
| `bicep/roles.bicep` | 644 | `1aff5543d53e4006` |
| `build/main.json` | 644 | `707d9d68b83e08a2` |
| `examples/deploy.bicepparam` | 644 | `2c263936a0149ad6` |
| `requirements.txt` | 644 | `8fd429b91faa8593` |
| `scripts/deploy.sh` | 755 | `bcf027614c3628d1` |
| `scripts/verify.py` | 755 | `e5c3d673e534ac91` |
| `tests/selftest.py` | 644 | `f97bc40cf9c6664a` |

Regenerate the table after a re-vendor:

```bash
cd core/skills/bicep-managed-identity
find . -type f -not -name PROVENANCE.md -printf '%P\n' | sort | while read -r f; do
  printf '| `%s` | %s | `%s` |\n' "$f" "$(stat -c '%a' "$f")" "$(sha256sum "$f" | cut -c1-16)"
done
```

## What is deliberately not vendored

Python caches (`__pycache__/`, `*.pyc`) are excluded at copy time and again by
the installer. No credential, key, subscription id or tenant id appears anywhere
in this box; the selftest asserts that and fails on a hardcoded principal.

## Runtime dependencies

`requirements.txt` names no Python package: the selftest is standard library
only. The Azure CLI with the Bicep compiler is needed to *deploy*, never to test,
and the harness installer never installs it.