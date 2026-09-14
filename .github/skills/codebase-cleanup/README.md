# Codebase Cleanup

Measure filesystem weight, prove unused candidates, preserve recoverable evidence and apply only
an explicitly authorized deletion manifest. The executable tool scans metadata and compares
reports; it never deletes project files or executes a plan. Loading or installing the skill grants
no deletion or cloud authority.

## Use

Python 3.10+ standard library only. No package installation, environment variables, network access
or project imports are required. Resolve `SKILL` to this installed directory. From a harness
checkout, `SKILL="$PWD/core/skills/codebase-cleanup"`; local project installation uses
`$PWD/.github/skills/codebase-cleanup`. A native plugin uses the loaded entry's directory.

```bash
python3 "$SKILL/tests/selftest.py"
python3 "$SKILL/scripts/inventory.py" scan "$PROJECT_ROOT" --group-depth 5 --output "$REPORT_DIR/before.json"
python3 "$SKILL/scripts/inventory.py" scan "$PROJECT_ROOT" --group-depth 5 --output "$REPORT_DIR/after.json"
python3 "$SKILL/scripts/inventory.py" compare "$REPORT_DIR/before.json" "$REPORT_DIR/after.json" --output "$REPORT_DIR/comparison.json"
```

`PROJECT_ROOT` is the confirmed directory being measured. `REPORT_DIR` must exist or be creatable
outside it. Use a new report name for each write; existing files are never overwritten. The two
scans bracket separately authorized work, not cleanup performed by the scanner.

## Contract And Limits

| Surface | Contract |
| --- | --- |
| Owner | `codebase-cleanup`; all implementation, templates and tests remain inside this skill |
| Callers | Operators and agents via `scripts/inventory.py scan` and `compare` |
| Configuration | Explicit root, optional repeated `--exclude`, `--group-depth` from 1 to 8, optional `--output` |
| Inventory | `codebase-cleanup-inventory-v1`: root, scope, totals, groups, measurement time and scan errors |
| Comparison | `codebase-cleanup-comparison-v1`: before/after totals, signed net removals and limits |
| Output | JSON on stdout unless an external, new output file is supplied |
| Exit status | 0 for complete scan/comparison; 2 for partial scans, invalid arguments or refused reports |
| Dependencies | Python standard library; no consuming-application or other capability imports |
| Authorization | Read metadata and write the requested report only; deletion remains a separate operator decision |
| Verification | `python3 "$SKILL/tests/selftest.py"`; isolated temporary fixtures, positive and refusal paths |

The root `.git` is excluded; hidden/ignored files and nested Git metadata otherwise count.
Symlinks are counted but not followed. Hard-linked names count separately. Bytes are logical file
content, not allocated storage or process RSS. A metadata scan is not an atomic snapshot; stop
concurrent writers before interpreting comparisons. Partial scans cannot be compared.

This package adds a measured filesystem-cleanup workflow and reusable scanner. `protocol-lean`
still owns broader repository-weight surveys, including dependency, CI and infrastructure policy;
`protocol-garbage-collect` still owns reachability-led dead-code removal. Neither protocol is
replaced or copied into another implementation.

## Anonymized Example

Native metadata uses `codebase-cleanup`; the catalogue retains `codebase_cleanup` as an alias.
The inventory implementation, tests and unapproved plan template remain independently usable.

The [case study](references/anonymized-cleanup.md) and
[anonymized catalogue](references/anonymized-cleanup.catalogue.json) preserve historical
measurements and retention decisions. Project names, private paths and original receipt
fingerprints are omitted or generalized. These are not synthetic measurements, results reproduced
by this package, recoverable backups or an executable deletion policy. The
[plan template](assets/cleanup-plan.example.json) starts unapproved and unproven.
Full procedure: [SKILL.md](SKILL.md).

## Removal

Removing a standalone copy of this skill removes only its guidance and scanner. Keep external
reports and any independently created recovery archive until their operator approves removal.
For harness-managed copies, use the owning harness's update or uninstall workflow; this skill
does not alter client profiles, dependencies, credentials, cloud resources or application state.