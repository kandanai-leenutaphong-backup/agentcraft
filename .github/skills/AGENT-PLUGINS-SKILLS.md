# Native Guidance Distribution

[libraries/capabilities.json](../../libraries/capabilities.json) is the single metadata authority.
Retained library owners keep substantive guidance, examples, contracts and runtime code.
Moved authoring/tooling bundles and pure procedures remain with their skill/protocol owners. Native catalogues and packaged guidance are
generated views, never another place to edit capability facts.

## Build And Check

Use Python 3.12+ and an isolated environment containing the installed `repository-inspection`
package from a reviewed artifact set. Package names are not claims of registry publication.
Run from the repository root:

```bash
python -B .github/tools/package_native.py
python -B .github/tools/package_native.py --check
```

Default generation writes source-only native views, not packaged guidance or a workspace
portable mirror. Native protocol entries link their authored protocols. The schema-2
[workspace skill catalogue](catalogue.json) has no `reader_root`; pass `--root .github`
explicitly to the repository reader. Parent regeneration follows active-document hash updates.
No generation, tests, builds or installation ran for this documentation update.

The generator refuses
missing or escaping source pointers, stale edited products, unknown aliases/dependencies,
unsupported MCP targets/tools, injected bindings/grants and non-allowlisted host commands.
Implemented targets must match their canonical owners' literal `TOOLS` declarations;
validation parses those declarations without importing adapters or starting clients.
`--check` writes nothing. Source revision, generator digest, document hashes and exclusions are
recorded in generated manifests. Build capability wheels/npm artifacts from their owners,
with build staging and environments outside shared source trees; never bundle runtime source.

## Portable Layout

Export a reviewed standalone plugin explicitly; the output must be an absolute external
directory that is new, empty, or already byte-identical to this generated export:

```bash
python -B .github/tools/package_native.py --plugin-output /tmp/agentcraft-plugin-review/harness-data
python -B .github/tools/package_native.py --plugin-output /tmp/agentcraft-plugin-review/harness-data --check
```

Export does not materialize workspace outputs. Workspace destinations, symlinks, unknown files,
partial exports and changed bytes refuse without repair; use a fresh directory when sources
change. `--check` is non-mutating and reports stale output with exit 1, refusal with exit 2.
Require exit 0 and verify the exported root's `native-manifest.json` hashes before installation.
The old generated workspace mirrors are removed. Historical ownership/hash receipts remain
evidence of that removal, not instructions to recreate those mirrors.

The exported root's native skills, agents and rules reference its contained `guidance/` package.
It needs no sibling `libraries` checkout. Packaged guidance is generated only into the
explicit absolute external output; no retained framework wheel guidance tree is advertised.
No source runtime, executable example, environment, historical receipt or operator state is
copied into GUIDANCE. Relevant notices travel with the documents.

The repository reader accepts the source-only workspace or an exported guidance package:

```bash
repository-catalogue --root .github --list --json
repository-catalogue --root /tmp/agentcraft-plugin-review/harness-data/guidance --show foundry-agent-runtime --json
```

Historical installed CLI examples, requiring separately selected reviewed framework artifacts
and packaged guidance; these are not library-workspace setup commands:

```bash
agentcraft describe
agentcraft describe framework
agentcraft catalogue --find composition
agentcraft catalogue --show portable-app-composition --kind skill
agentcraft catalogue --show capability-modularization --kind protocol
```

`describe [id]` is offline and reports unverified readiness, not service connectivity.
`catalogue --find/--show [--kind skill|protocol]` requires the declared `tooling` extra.
Installed API: `agentcraft.catalogue.load_catalogue()` returns library/task metadata;
`guidance_root()` requires installed packaged guidance; source-only workspace metadata does not supply it;
`report(query="composition")` or `report(name="harness-guide")` delegates search/read to
`repository_inspection.catalogue`. The latter requires the declared tooling dependency.
No API infers a source checkout, changes import paths, starts a server or fetches a package.

Embedded names remain searchable and readable, with parent ownership. Protocol names and native
workflow aliases select one procedural record. `foundry-agent-runtime` selects current native
hosted-bundle guidance, not the retired engine. The historical HyperFrames module is a recorded
alias, not a required source tree.

## Authority And Evidence

All seven obsolete MCP registrations remain removed. Canonical replacement adapters and the
unified host are **implemented**, with bounded **offline-verified** SDK evidence; this does
not make them active. The catalogue's five targets describe 15 supported tool names with
conditional availability. The 27-name legacy map is migration metadata, never runtime aliases.

Shipped MCP registrations stay empty: **DISABLED BY DEFAULT**. With the selected installed
`mcp` extra, an operator may explicitly launch this stdio command from their MCP client:

```bash
agentcraft mcp --offline
```

This opt-in creates only the fixed `composition` binding and its three synthetic/offline
tools. It accepts no configuration factory, endpoint, environment credential or live binding.
No client-specific disabled-registration extension, absolute install path, auto-install
launcher or vendored server runtime is generated. Server lifetime follows the client session;
installation and guidance lookup start no process.

Other targets require a trusted host calling
`agentcraft.mcp.create_server(bindings=..., grants=..., principal=..., context=...)` with
installed public binding values, exact per-binding tool-name grants and matching principal
and execution context. Each offered tool's binding enum contains only granted host bindings.
Native capability grants still apply. Recovery additionally requires its explicit absolute
root and separate stage/inspect/payload-read authority. Nothing selects a live credential,
grants inference, widens a registry or makes staging a remote commit.

The public example is `python -m agentcraft.examples`, with callable
`agentcraft.examples.offline_workflow`; [its owner](harness-guide/framework/README.md)
documents the required extras and real native data -> rules -> model -> recovery flow using
synthetic transports. Source code is not copied into guidance. Final non-editable combined-wheel
execution and installed-client acceptance remain parent-owned and unclaimed here. The
[dated conformance assessment](harness-guide/framework/CONFORMANCE.md) records its own
scope and outstanding gates; implemented discovery is not completed portfolio conformance.

Missing documents, unbundled source/assets and historical references become labelled
non-advertised references, with exact source/target/existence evidence in the external
export's `guidance/provenance.json`. They are not fabricated
replacement documents. Missing canonical catalogue guidance/source pointers refuse generation;
the omission policy applies to ordinary document references, not advertised source records.
Canonical code blocks may describe checkout-only examples; such examples
must be verified through selected release artifacts before claiming installed task completion.
Local link checks do not establish external URL availability, live behavior or client registration.

The repository [MIT notice](../../LICENSE), styling
[asset notices](azure-sky-styling/public/THIRD_PARTY_NOTICES.txt),
[rights record](azure-sky-styling/research/painterly/RIGHTS.md), and explorer
[font notices](../../libraries/resource-explorer/docs/skills/assets/THIRD_PARTY_NOTICES.txt)
retain their owners. An acquisition receipt is not a redistribution grant. No omitted artwork,
private source, customer data or historical evidence gains publication authority from this build.

Installation, native discovery, MCP activation, runtime authorization, Azure grants and
publication are separate actions. Uninstalling guidance never revokes roles, tears down resources,
commits recovery output or authorizes deletion of pending artifacts, notes or user state.