# Agent Optimization

One skill entry, two deliberately separate artifacts:

- The portable [Python service and React UI](python/agent_optimization/README.md), installed
	through the existing Python/npm manifests.
- The extractable reference snapshot below, built from those same first-party sources plus a
	synthetic example ledger.

The snapshot is not on the portable package's import path and installs nothing. Use
[SKILL.md](SKILL.md) to choose the appropriate surface.

## Reference Snapshot

Version 2.0.0, rebuilt on 2026-09-14 from this skill's own sources by
[scripts/build_snapshot.py](./scripts/build_snapshot.py). It travels as one unit and holds no
host application, customer configuration, deployment runbook, dataset, credential, cloud target
or third-party component clone. No archive member records an origin path or source revision.

The payload is compressed so adopting projects do not inherit a large file count. Extract it into
a new directory outside the repository when you want to inspect or adopt code offline.

## Entry Points

| Resource | Purpose |
| --- | --- |
| [SKILL.md](./SKILL.md) | Discoverable agent procedure and constraints |
| [Contents map](./references/CONTENTS.md) | Runtime, UI and synthetic example inventory |
| [Integration guide](./references/INTEGRATION.md) | Contracts a different application must implement |
| [Verification guide](./references/VERIFICATION.md) | Reproduce pack checks without a live model |
| [manifest.json](./manifest.json) | Every payload path, byte count, SHA-256 and role |
| [assets/implementation.zip](./assets/implementation.zip) | The source snapshot itself |
| [assets/sources.json](./assets/sources.json) | Explicit first-party selection used to build it |
| [assets/example/](./assets/example/README.md) | Synthetic, hand-authored record shapes |
| [scripts/skillpack.py](./scripts/skillpack.py) | Read-only verification and new-directory extraction |
| [scripts/build_snapshot.py](./scripts/build_snapshot.py) | Explicit rebuild from the first-party sources |

Run from this folder:

```bash
python3 -B scripts/skillpack.py verify
python3 -B scripts/skillpack.py extract --destination /tmp/agent-optimization-reference
```

Expected: `verified`, then `extracted`. Existing destinations, changed hashes, unsafe paths,
links, devices and inconsistent inventories are refused. These commands install no package,
start no app, call no model and change no existing source file.

## Scope And Provenance

The archive has two roots: `runtime/` and `example/`. `runtime/` is a byte copy of the portable
package plus the manifests and the frontend verification recipe. `example/` is hand-authored
illustration of record shape, marked synthetic in every file, produced by no run or measurement.

`situation_detector` and `copilot_terminal` are declared dependencies installed from their own
packages; they are not vendored into this archive. Historical campaign artifacts — configurations,
receipts, proofs, images and outcome ledgers — are not included, and nothing here can reproduce or
rescore them. Aggregate historical results quoted in the [contents map](./references/CONTENTS.md)
are reported history, neither new measurements nor synthetic values.

Per-file hashes identify the archive's working bytes. They establish internal consistency, not
publisher authenticity or redistribution rights; no overall license is asserted or invented here.

## Refresh Deliberately

Adopting the pack and rebuilding its snapshot are separate operations. Do not rebuild during an
active experiment: candidate, skill and implementation pins are part of its contract.

```bash
python3 -B scripts/build_snapshot.py --replace
python3 -B scripts/skillpack.py verify
```

The builder reads the explicit selection and writes only this pack's payload and manifest. It
refuses missing sources, unsafe paths, credential-shaped files and out-of-selection roots, and
defaults its source root to this skill directory. It installs nothing and updates no live import.
