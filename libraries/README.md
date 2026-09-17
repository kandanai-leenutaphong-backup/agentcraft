# Agentcraft Workspace

This page owns installation and package development. Start with the
[documentation entry](../docs/README.md) for tasks, shared concepts and references.
The [canonical catalogue](capabilities.json) owns capability names, APIs, dependencies
and checks; generated discovery views are projections, not another knowledge source.

## Current State

The [uv workspace](pyproject.toml) has **8 explicit Python members** and a
[shared lock](uv.lock). Ten Investigation-used library directories remain:
`azure-data-connectors`, `llm-interface`, `situation-detector`, `resource-explorer`,
`modular-agents`, `event-stream`, `source-code`, `framework-core`, `entra-auth` and
`signed-dev-access`. Four npm packages remain across these owners.
`framework` and `app-composition` are no longer Python workspace members.

Native async `azdata` and `llm_interface` are current. Investigation's
[owner map](../template_apps/investigation_app/docs/ARCHITECTURE_OVERVIEW.md) records
its public-library composition. The
[raw model compatibility](../.github/skills/azure-llm-compat/README.md) and
[synchronous Search adapter](../.github/skills/search-read-adapter/README.md) are retirement notices,
not install options. Application runtimes have library owners; authoring-only scripts
and assets belong to skills. Source migration does not establish live acceptance.

[Content Understanding](../.github/skills/azure-content-understanding/SKILL.md) is a skill-owned official-SDK
recipe with a separate locked uv project, not a library workspace distribution.
Frontend packages retain their npm metadata. The [reference index](../docs/README.md#reference)
links these owners without repeating the catalogue here.

## Library Scope

Agentcraft exists to simplify construction of end-to-end agentic applications.
Admit a library for a named application/framework consumer or an approved application
requirement, with a public contract, declared dependencies and a focused check.
Self-tests, a package manifest or a skill entry alone do not establish runtime relevance.
Reuse an existing owner before introducing another package.

[Azure Sky](../.github/skills/azure-sky-styling/SKILL.md) and
[HyperFrames](../.github/skills/hyperframes-motion/SKILL.md) are skill-owned authoring
bundles, excluded from runtime capability registration. Their source, assets, tests,
locks and notices remain with those skills; package names and exports are unchanged.

Eleven unused library owners moved into skills: [agent optimization](../.github/skills/agent-optimization/SKILL.md),
[app composition](../.github/skills/portable-app-composition/SKILL.md),
[Content Understanding](../.github/skills/azure-content-understanding/SKILL.md),
[Copilot terminal](../.github/skills/ghcp-cli-frontend/SKILL.md),
[notebook tooling](../.github/skills/investigation-notebook/SKILL.md),
[recovery](../.github/skills/recoverable-jobs/SKILL.md),
[web acquisition](../.github/skills/web-resource/SKILL.md),
[repository inspection](../.github/skills/harness-guide/repository-inspection/README.md),
[framework](../.github/skills/harness-guide/framework/README.md), and the two retirement
notices above. Moved source is retained, not deleted. Twelve duplicate skill directories
are removed; retained libraries own their substantive guidance under `docs/skills/`.

## Installation

Run from the repository root. Requirements: Python 3.12+, uv **0.9.30**, reviewed
dependencies and a caller-owned environment. Replace the path below with a new absolute
environment path outside the checkout; do not reuse another application's environment.
Dependency installation may need a package source. It grants no service access and
performs no model inference.

```bash
export UV_PROJECT_ENVIRONMENT=/absolute/path/to/a/new/agentcraft-env
uv sync --locked --project libraries --package agentcraft-core --no-default-groups
```

This selects the retained core distribution, not the moved `agentcraft` framework.
Choose another retained distribution and its extras from its owning metadata as needed.
No binding, credential or grant is created. The skill-owned
[framework guide](../.github/skills/harness-guide/framework/README.md) owns its separate
composition setup; the library workspace no longer installs that profile.
Provider-specific dependencies remain in
[data metadata](azure-data-connectors/pyproject.toml) and
[model metadata](llm-interface/pyproject.toml).

These are workspace-source commands, separate from artifact installation. Do not
substitute `--frozen` or drop `--locked` on a mismatch: have the lock owner reconcile
metadata, then repeat setup. The historical [recorded isolated install](../.github/skills/harness-guide/framework/distribution/independent-reader.json)
used reviewed wheels; it does not certify the split. No lock check or installation was
run for this documentation update. Keep the selected environment for repeated calls; remove only that owned environment
when no longer needed, never user recovery output, datasets or shared caches.

## Discovery And MCP

With the repository reader available, source-only workspace guidance lookup uses:

```bash
repository-catalogue --root .github --find "recovery" --json
repository-catalogue --root .github --show recoverable-jobs --json
```

The schema-2 [workspace skill catalogue](../.github/skills/catalogue.json) has no
`reader_root`; pass `.github` explicitly. Lookup reads guidance, not execution authority.
Source protocol entries link authored [protocol guidance](../.github/protocols/README.md).
Packaged guidance is generated only into an explicit external export, not a retained
wheel guidance tree or in-checkout portable plugin mirror.

Maintainers can export a self-contained native plugin to a new absolute external directory:

```bash
"$UV_PROJECT_ENVIRONMENT/bin/python" -B .github/tools/package_native.py --plugin-output /absolute/external/agentcraft-plugin
"$UV_PROJECT_ENVIRONMENT/bin/python" -B .github/tools/package_native.py --plugin-output /absolute/external/agentcraft-plugin --check
```

Run generation only after documentation is settled. Check exit 0 means current bytes;
1 means stale and 2 means refused input or protected edits. Never install a nonzero-check
or changed-hash export. [Native installation and cleanup](../.github/skills/AGENT-PLUGINS-SKILLS.md)
owns the client sequence. Historical [deduplication evidence](../.github/skills/harness-guide/framework/distribution/guidance-dedup.json)
records earlier external-export and installed-reader checks, not this split.
Regenerate after changing source hashes; generated products remain read-only here.

MCP remains an explicit opt-in through the skill-owned framework's separate setup.
Live hosts use `create_server` with explicit bindings, grants, principal and execution context.
The [native SDK client example](../.github/skills/harness-guide/framework/README.md#offline-mcp-client) covers discovery,
validation refusal/recovery and child cleanup without editor activation.
The historical [conformance record](../.github/skills/harness-guide/framework/CONFORMANCE.md) distinguishes SDK, native-client and
live-provider evidence.
[Editor MCP configuration](../.github/mcp.json) is intentionally empty; server activation
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

The historical [release-candidate receipt](../.github/skills/harness-guide/framework/distribution/release-candidate.json) owns
its dated artifact hashes and build/rebuild/install results. Later runtime and documentation
changes require new artifact identities; that receipt does not certify current source.
[Conformance](../.github/skills/harness-guide/framework/CONFORMANCE.md) records its dated package results;
the [execution ledger](../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/EXECUTION.md)
preserves intermediate observations, including failures superseded by later repairs.

Historical skill and generated-mirror reductions retain their separate denominators in
the release and deduplication receipts. Source movement alone proves neither disk/RAM
savings nor runtime improvement.

## Design And History

[Core objectives](../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/0_CORE_OBJECTIVE.md)
and [Chapter 05](../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/05_DOCUMENTATION_AND_DEVELOPER_EXPERIENCE.md)
state acceptance requirements, not completed execution. The
portfolio design (`DESIGN.md`) and connector assessment (`CONNECTOR_RETIREMENT.md`)
are historical inputs absent from this checkout; use current contracts and the execution ledger for present state.
Locally retained specs may be absent from a distributed checkout. No cloud, publication,
authentication change or deletion of operator data follows from this source migration.
