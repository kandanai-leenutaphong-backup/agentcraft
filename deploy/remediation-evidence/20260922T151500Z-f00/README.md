# F00 Primary Evidence

F00 only. No migration source, dependency or cloud mutation. No constitution established,
scored comparison, holdout access, inference, worker dispatch or authoritative publication.
Full handoff and proposed separate-project authority: [handoff.json](handoff.json).

## Results

- Recovery: 205 allowlisted source files, 2,020,644 bytes; archive SHA-256
  `ec3ba0a346a6589a101d7101d3be761e3112a4c843ebade80071df93335e2076`.
- Isolated recovery bytes verified; 896 historical files stream-hashed without parsing
  raw private data. Accepted H build libraries match all 51 captured library members.
- H/E/O offline owner functions: 21/18/20 passing tests. Shell entrypoints normally write
  outside F00, so their exact offline functions were called with guarded temporary writes.
- Python 3.12.3, uv 0.9.30. Default uv list/check see zero packages. Explicit user-site
  inventory sees 265, system site 97; 350 unique names, ten real base-version conflicts.
- System installation targets nonwritable; existing user-site writable and earlier in
  import order. Build gap: setuptools 68.1.2 versus owning requirement >=77.
- Azure account/project/registry/model/pull-role reads passed. Graph caller-object lookup
  failed `InteractionRequired / TokenCreatedWithOutdatedPolicies`; no retry or login.
- F07 baseline: 144 functions, 19 production files, 3,501 lines; six authenticated custom
  HTTP dispatch sites, five package-install sites, two pip-freeze sites.
- Existing historical H/E/O victories retained; changed-artifact live acceptance not run.

## Reproduction

Run from repository root with existing `/usr/bin/python3`; never create an environment.
Capture is exclusive: never rerun `capture` into this populated evidence directory.

```bash
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deploy/remediation-evidence/20260922T151500Z-f00/capture.py selftest
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deploy/remediation-evidence/20260922T151500Z-f00/probe.py environment
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deploy/remediation-evidence/20260922T151500Z-f00/probe.py sdk
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deploy/remediation-evidence/20260922T151500Z-f00/probe.py inventory
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deploy/remediation-evidence/20260922T151500Z-f00/probe.py baseline-H
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deploy/remediation-evidence/20260922T151500Z-f00/probe.py baseline-E
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deploy/remediation-evidence/20260922T151500Z-f00/probe.py baseline-O
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deploy/remediation-evidence/20260922T151500Z-f00/probe.py supplement
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 deploy/remediation-evidence/20260922T151500Z-f00/probe.py compatibility
```

`probe.py cloud` invokes H deployment owner's read-only preflight and identity GETs;
it performs no installation, upload, inference, context switch or cloud mutation.
It is expected to retain a failed receipt if Graph interaction remains required.
Probes append timestamped receipts when a prior receipt exists.

## Evidence Map

- [capture.json](capture.json): allowlisted bytes, scoped Git diffs/status, historical hashes.
- [source.tar.gz](source.tar.gz): recoverable source, not merely hashes; `recovery/` is isolated.
- [environment.json](environment.json), [supplement.json](supplement.json),
  [compatibility.json](compatibility.json): exact commands, origins, versions and conflicts.
- [sdk-20260922T153054275836Z.json](sdk-20260922T153054275836Z.json): corrected public signatures,
  annotations, unwrapped origins, lines and source hashes; earlier attempts retained.
- [inventory-20260922T153031847646Z.json](inventory-20260922T153031847646Z.json): reproducible
  count scope, imports, HTTP/package sites and removal callers including tests.
- [cloud.json](cloud.json): successful nonsecret target reads and failed Graph lookup.
- [baseline-H-20260922T152714277094Z.json](baseline-H-20260922T152714277094Z.json),
  [baseline-E-20260922T152717068643Z.json](baseline-E-20260922T152717068643Z.json),
  [baseline-O-20260922T152719818253Z.json](baseline-O-20260922T152719818253Z.json): passing owners.

Initial guarded tests failed on read-only platform startup; capture-only fix resolved them.
Unused duplicate capture draft was removed; no existing source was deleted. No historical
receipt overwritten. Archive secret checks are allowlisting plus pattern backstops, not
universal secret detection. Installed wheel rollback and live restore remain unverified.

Overseer owns publication and next assignment. Preserve existing O constitution unchanged.