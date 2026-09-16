# Agentcraft Workspace

This page owns installation and package development. Start with the
[documentation entry](../docs/README.md) for tasks, shared concepts and references.
The canonical catalogue (outside-guidance-not-advertised; source reference: `capabilities.json`) owns capability names, APIs, dependencies
and checks; generated discovery views are projections, not another knowledge source.

## Current State

The uv workspace (outside-guidance-not-advertised; source reference: `pyproject.toml`) has **16 explicit Python members**, including
`agentcraft` and `agentcraft-core`, with a refreshed shared lock (outside-guidance-not-advertised; source reference: `uv.lock`).
`agentcraft` supplies composition, discovery and optional adapters over independently
installable libraries. It is not a second data, model or tool-execution engine.

Native async `azdata` and `llm_interface` are current. Investigation's
owner map (outside-guidance-not-advertised; source reference: `../template_apps/investigation_app/docs/ARCHITECTURE_OVERVIEW.md`) records
its public-library composition. The
raw model compatibility (outside-guidance-not-advertised; source reference: `azure-llm-compat/README.md`) and
synchronous Search adapter (outside-guidance-not-advertised; source reference: `search-read-adapter/README.md`) are retirement notices,
not install options. Skill entries carry guidance and discovery, not capability runtimes
or a retained source snapshot. Source migration does not establish live acceptance.

[Content Understanding](content-understanding/README.md) is a library-owned official-SDK
recipe with a separate locked uv project, not a seventeenth workspace distribution.
Frontend packages retain their npm metadata. The [reference index](../docs/README.md#reference)
links these owners without repeating the catalogue here.

## Installation

Run from the repository root. Requirements: Python 3.12+, uv **0.9.30**, reviewed
dependencies and a caller-owned environment. Replace the path below with a new absolute
environment path outside the checkout; do not reuse another application's environment.
Dependency installation may need a package source. It grants no service access and
performs no model inference.

```bash
export UV_PROJECT_ENVIRONMENT=/absolute/path/to/a/new/agentcraft-env
uv sync --locked --project libraries --package agentcraft --extra data --extra models --extra recovery --extra optimization --extra tooling --no-default-groups
"$UV_PROJECT_ENVIRONMENT/bin/agentcraft" describe
```

Expect a JSON capability description with `readiness: unverified`, not a connection
test. `agentcraft describe [capability]` selects an id from that output. No binding,
credential or grant is created. Next: run the
[composed offline workflow](../docs/README.md#offline-data-rules-and-recovery).

Framework metadata (source-or-asset-not-bundled; source reference: `framework/pyproject.toml`) defines extras. This profile selects
`data`, `models`, `recovery`, `optimization` and `tooling`; `optimization` supplies
`situation-detector` explicitly. There is no `rules` extra. `data` selects
Kusto/Search/Gremlin/identity, not every data provider; `models` selects
`llm-interface[openai]`, not `[foundry]`. Provider-specific dependencies remain in
data metadata (source-or-asset-not-bundled; source reference: `azure-data-connectors/pyproject.toml`) and
model metadata (source-or-asset-not-bundled; source reference: `llm-interface/pyproject.toml`).

These are workspace-source commands, separate from artifact installation. Do not
substitute `--frozen` or drop `--locked` on a mismatch: have the lock owner reconcile
metadata, then repeat setup. The recorded isolated install (source-or-asset-not-bundled; source reference: `framework/distribution/independent-reader.json`)
used reviewed wheels; this source setup is not a new artifact pass. This sweep checks
lock freshness without synchronization. Dependency installation was not repeated.

Unknown capability: `describe` exits 2; select an id from the successful unfiltered
description and retry. Description/discovery creates no service or persistent application
state. Keep the selected environment for repeated calls; remove only that owned environment
when no longer needed, never user recovery output, datasets or shared caches.

## Discovery And MCP

The `tooling` extra enables installed guidance lookup:

```bash
"$UV_PROJECT_ENVIRONMENT/bin/agentcraft" catalogue --find "recovery"
"$UV_PROJECT_ENVIRONMENT/bin/agentcraft" catalogue --show recoverable-jobs --kind skill
```

`agentcraft catalogue --find/--show [--kind skill|protocol]` reads generated guidance;
it does not execute it. The [framework guide](framework/README.md) owns the CLI and
composition APIs. Source protocol entries link authored
[protocol guidance](../../README.md). Installed readers use
`agentcraft.catalogue.guidance_root()`, backed by the retained
[wheel guidance tree](../../README.md).
There is no in-checkout portable plugin mirror.

Maintainers can export a self-contained native plugin to a new absolute external directory:

```bash
"$UV_PROJECT_ENVIRONMENT/bin/python" -B .github/tools/package_native.py --plugin-output /absolute/external/agentcraft-plugin
"$UV_PROJECT_ENVIRONMENT/bin/python" -B .github/tools/package_native.py --plugin-output /absolute/external/agentcraft-plugin --check
```

Run generation only after documentation is settled. Check exit 0 means current bytes;
1 means stale and 2 means refused input or protected edits. Never install a nonzero-check
or changed-hash export. [Native installation and cleanup](../harness/skills/AGENT-PLUGINS-SKILLS.md)
owns the client sequence. Deduplication evidence (source-or-asset-not-bundled; source reference: `framework/distribution/guidance-dedup.json`)
records the external-export, installed-reader and 37-skill CLI checks. These commands are
source-verified here, not rerun; generated products are read-only during this sweep.

MCP is an explicit opt-in: add `--extra mcp` to the locked setup above, then run:

```bash
"$UV_PROJECT_ENVIRONMENT/bin/agentcraft" mcp --offline
```

This starts the offline stdio host; closing the client ends the session. Live hosts use
`create_server` with explicit bindings, grants, principal and execution context.
The [native SDK client example](framework/README.md#offline-mcp-client) covers discovery,
validation refusal/recovery and child cleanup without editor activation.
The [conformance record](framework/CONFORMANCE.md) distinguishes SDK, native-client and
live-provider evidence.
Editor MCP configuration (outside-guidance-not-advertised; source reference: `../.github/mcp.json`) is intentionally empty; server activation
requires explicit operator action. Installing an extra or loading guidance enables no
server or grant.

## Dependency Ownership

Each importing member declares normal versioned runtime dependencies and its optional
extras. Development groups and the shared lock are not published runtime requirements;
`tool.uv.sources` supplies workspace development locations, not consumer dependencies.
Do not mask missing requirements with `PYTHONPATH`, skill directories or editable siblings.
uv manages Python only; application, frontend, native driver and deployment prerequisites
stay with their owners.

Package metadata owns workspace dependencies and lock changes. From the repository root,
`uv lock --check --project libraries` checks freshness; capability-specific test commands
live in the catalogue and owning guides. Select extras explicitly and keep offline tests
separate from authorized service/model checks. This documentation sweep installs and
builds nothing.

## Release Contract

Build wheels and sdists with `uv build --no-sources`; inspect contents, rebuild from
sdists and verify imports and behavior outside the checkout with reviewed dependency
artifacts. A workspace pass does not prove every extra, Python version, lower bound or
combined profile. Retain notices and hashes; no local-path dependency may escape into
published metadata. Publication and registry read-back require separate authorization.

The release-candidate receipt (source-or-asset-not-bundled; source reference: `framework/distribution/release-candidate.json`) owns
its dated artifact hashes and build/rebuild/install results. Later runtime and documentation
changes require new artifact identities; that receipt does not certify current source.
[Conformance](framework/CONFORMANCE.md) records every retained package's F1-F8 result;
the execution ledger (outside-guidance-not-advertised; source reference: `../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/EXECUTION.md`)
preserves intermediate observations, including failures superseded by later repairs.

Historical skill and generated-mirror reductions retain their separate denominators in
the release and deduplication receipts. Source movement alone proves neither disk/RAM
savings nor runtime improvement.

## Design And History

Core objectives (outside-guidance-not-advertised; source reference: `../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/0_CORE_OBJECTIVE.md`)
and Chapter 05 (outside-guidance-not-advertised; source reference: `../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/05_DOCUMENTATION_AND_DEVELOPER_EXPERIENCE.md`)
state acceptance requirements, not completed execution. The
portfolio design (outside-guidance-not-advertised; source reference: `DESIGN.md`) and connector assessment (outside-guidance-not-advertised; source reference: `CONNECTOR_RETIREMENT.md`)
are historical inputs; use current contracts and the execution ledger for present state.
Locally retained specs may be absent from a distributed checkout. No cloud, publication,
authentication change or deletion of operator data follows from this source migration.
