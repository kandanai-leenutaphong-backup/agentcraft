# Harness Guide

Local discovery for the complete skill and protocol package. Python 3.11+, standard library only.
No account, MCP daemon, model call, network access, or client settings change.

From a harness checkout:

```bash
python3 core/skills/harness-guide/scripts/catalogue.py --find "remove dead code" --json
python3 core/skills/harness-guide/scripts/catalogue.py --show protocol-garbage-collect
python3 core/skills/harness-guide/scripts/catalogue.py --list --kind protocol
python3 core/skills/harness-guide/scripts/catalogue.py --check
python3 core/skills/harness-guide/tests/selftest.py
```

In a plugin installation, use the absolute script path beside the loaded skill. The default root
comes from the script's location, never the caller's current directory. A standalone skill copy
can inspect an explicitly supplied package with `--root`; its selftest needs no sibling skills.

The two canonical inputs are the [skill catalogue](../catalogue.json) and
[protocol catalogue](../../protocols/catalogue.json), relative to the supplied package.
Optional module metadata lives in the skill catalogue's
`source_skills` array; those entries are not silently included in plugin skill counts.
Promoted source entries use `superseded_by` and route to their bundled owner without a duplicate
result. The current HyperFrames module is such a compatibility pointer, not an uninstalled option.
Exact `aliases` support requested names such as `ghcp_cli_frontend` while the portable skill remains
`ghcp-cli-frontend`. Both search and `--show` resolve that name without duplicating the capability.
Embedded skill entries live in their parent's `components` array and are discoverable without
being counted as separate plugin installs.
Use `--source-root` only to inspect a deliberately supplied repository containing those modules.

`--list`, `--find QUERY`, `--show NAME`, and `--check` are mutually exclusive. `--kind skill|protocol`
filters listing/search. `--json` returns structured results. `--limit` bounds search results to
1-50. Empty queries, unknown names, invalid catalogues, and escaping paths exit nonzero.
An unmatched nonempty query returns zero matches and an explicit full-list fallback, not a guess.

The Python API is [scripts/catalogue.py](scripts/catalogue.py): `skill_catalogue`,
`protocol_catalogue`, `capability_catalogue`, `search`, `report`, and `print_report`.
The installer calls these same functions. See [CONTRACT.md](CONTRACT.md) for invariants and
[GOTCHAS.md](GOTCHAS.md) for limits.