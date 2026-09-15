# Capability Libraries

**Approved direction, 2026-09-14: uv-managed Python development with independently
installable, versioned and publishable capability packages.** A workspace is not one
code-bearing distribution, and installing a library grants no Azure access.

This README owns the dependency-management and execution sequence. The
[portfolio design](DESIGN.md) records the wider consolidation proposal; this approved
sequence supersedes its earlier design-only Python-packaging guidance.

## Current State

| Capability | Distribution / Import | State |
| --- | --- | --- |
| [Azure data connectors](azure-data-connectors/README.md) | `azdata` / `azdata` | Ten standardized service profiles in `4.0.0a3`; 126 source tests. Local CyberEye ADX adoption started; [verification record](azure-data-connectors/VERIFICATION.md) separates current source, earlier artifacts and live gaps. |
| [LLM interface](llm-interface/README.md) | `llm-interface` / `llm_interface` | Implemented `0.1.0a1`: few-line Foundry calls, embeddings and streaming agents; [validation record](llm-interface/VALIDATION.md) owns offline/artifact evidence and pending live/usability testing. |

The access-library proposal is retired as of 2026-09-15. Its useful evidence and functionality
belong to the consolidated [Azure access skill](../.github/skills/azure-access-management/SKILL.md),
not a workspace package. The workspace foundation was verified with uv `0.9.30` and Python
`3.11.14`; current library checks and pending live acceptance remain capability-owned.

## Workspace Model

```text
libraries/
  README.md
  DESIGN.md
  pyproject.toml                      non-package workspace root
  uv.lock                             committed shared resolution
  .venv/                              ignored development environment
  azure-data-connectors/
    pyproject.toml                    member metadata and owned dependencies
    src/azdata/
  llm-interface/
    pyproject.toml                    independently versioned model/agent package
    src/llm_interface/
```

The [workspace configuration](pyproject.toml) registers `azure-data-connectors` and `llm-interface` and
requires uv `0.9.30`; the [shared lock](uv.lock) records the resolution. Do not enroll
design-only directories, skills or template applications through a wildcard. Existing
build backends are retained; both implemented members use setuptools.

No workspace dependency or development source points into the access skill. Its retained
SDK evidence uses that skill's own optional development group and lockfile.

One writer coordinates the root configuration and lockfile. Member owners still own
their source, version and dependency declarations. Concurrent jobs/agents use separate
environments or worktrees, not simultaneous `uv sync` calls against one `.venv`.

Workspace members resolve together, including extras and dependency groups, and share the
intersection of their `requires-python` ranges. If members need incompatible resolutions,
use separate uv projects. Do not raise a package's published Python minimum merely to fit
the workspace. Python import isolation still requires independent artifact tests.

## Dependency Ownership

| Metadata | Purpose | Published To Consumers |
| --- | --- | --- |
| `project.dependencies` | Required runtime imports | Yes, as standard versioned requirements |
| `project.optional-dependencies` | Implemented provider/integration extras | Yes, installed when selected |
| `dependency-groups` | Test, lint and other development tools | No runtime requirement |
| `build-system.requires` | Build backend and build-time requirements | Used to build the package |
| `tool.uv.sources` | Explicit local development sources | Not a replacement for standard published requirements |
| `uv.lock` | Exact development resolution | Not imposed on package consumers |

- Declare each dependency in the member that imports it, including directly used SDK
  support packages. Another member's transitive dependency is not an API contract.
- Use tested minimum versions and evidence-based compatibility limits in package metadata.
  Keep exact development resolutions in the lockfile, not a blanket set of published pins.
- Use optional SDK extras so a policy-only consumer does not install every Azure client.
  Installation is not proof of provider support or permission to perform operations.
- For a real inter-library dependency, declare a normal distribution/version requirement
  plus `{ workspace = true }` in `tool.uv.sources` for local development. Do not introduce
  an access-to-data dependency just because the packages share this directory.
- MSAL/framework auth, frontend dependencies, Azure CLI, Bicep and OS database drivers
  remain with their consuming applications/toolchains. uv manages Python packages only.
- Do not install both legacy and new distributions exporting the same import namespace
  into one environment and mistake import order for compatibility.

## Development Commands

Run from `libraries/`. `--package` takes the distribution name, not its folder. The
connector workflow now selects its implemented provider extras; tests remain offline.

```bash
uv lock --check
uv sync --locked --package azdata --all-extras --no-default-groups
uv run --locked --package azdata --all-extras --no-default-groups python -B -m unittest discover -s azure-data-connectors/tests -t azure-data-connectors -v
uv build --no-sources --package azdata --out-dir dist/azdata
```

The LLM interface uses a separate environment, with no model inference in these checks:

```bash
UV_PROJECT_ENVIRONMENT="$PWD/.venv-llm-interface" uv run --locked --package llm-interface --extra foundry --no-default-groups python -B -m unittest discover -s llm-interface/tests -v
UV_PROJECT_ENVIRONMENT="$PWD/.venv-llm-interface" uv run --locked --package llm-interface --extra foundry --no-default-groups python -B llm-interface/examples/offline.py
uv build --no-sources --package llm-interface --out-dir dist/llm-interface
```

Legacy comparison tests skip when their separate packages are absent; the LLM runtime
does not depend on those skills. Its [caller guide](llm-interface/USAGE.md) starts with
the actual few-line interface. LLM application adoption remains deferred. The separate
[CyberEye template](../template_apps/README.md) is now an ADX consumer with its own uv project
and an explicit path dependency; it is not enrolled in this library workspace.

The retired experiment's [comparison record](../.github/skills/azure-access-management/tests/sdk_comparison/README.md)
now lives with the consolidated skill and is not part of library test discovery.

For an intentional dependency change, use `uv add --package <member> --optional <extra>
<dependency>` or `uv add --package <member> --group <group> <tool>`, review metadata and
lock changes, then run affected checks. `uv lock` creates/updates the resolution;
routine CI uses `--locked` and checks freshness rather than modifying it. `--frozen`
skips freshness validation and is not equivalent evidence. Select extras/groups explicitly.

Use the required uv tool version in CI; no CI workflow is installed by this increment.
An explicit `UV_PROJECT_ENVIRONMENT` can isolate a
concurrent job's environment; it does not create a private dependency lock. Ordinary
resolution/tests must not authenticate to Azure, provision resources or invoke live tests.

## Release Contract

1. Each capability owns its distribution name, version, Python support, public imports,
   README/license metadata and third-party notices. Local names do not reserve PyPI names.
2. Build wheel and sdist with `uv build --no-sources`. Inspect their contents, rebuild from
   the sdist and check imports/behavior outside this checkout. No skill-path imports,
   editable siblings, `PYTHONPATH`, datasets or credentials may hide a missing dependency.
3. Test the base installation, implemented extras, supported Python versions and dependency
   lower bounds. A passing workspace lock does not prove all supported combinations or
   lock the isolated build backend. Record the limits of actual tests.
4. Resolve inter-library dependencies through released artifacts or a controlled staging
   wheel set/index. Publish dependencies before consumers; never ship local-path requirements.
5. Publication is a separate authorized action. Upload only reviewed artifact paths, using
   protected release jobs and PyPI Trusted Publishing/OIDC when PyPI is selected. Private
   indexes need deliberate routing/authentication; do not commit tokens or credentialed URLs.
6. Verify installation from the chosen registry and retain artifact hashes and test evidence.
   Consumers may use pip; neither uv nor this lockfile is a runtime requirement.

A later metapackage can provide one install command through extras pointing to released
capability packages. It owns no copied code or unified import API. The illustrative name
`agentcraft-libraries[access,data]` is not reserved or published. A single code-bearing
distribution would require a separate decision about shared versions and release cadence.

## Execution Sequence

| Increment | Deliverable | Completion Evidence |
| --- | --- | --- |
| 1. Workspace foundation | Complete: explicit connector member, shared lock, ignore rules and runnable commands | Lock freshness; 32 contract tests and 1 integration test; wheel/sdist build and isolated wheel import |
| 2. Access proposal | Retired in favor of one consolidated skill | Useful helpers and comparison evidence preserved under their skill owner; no access workspace package |
| 3. Library adoption and releases | Capability-specific next increments | Current consumer, artifact, dependency and separately authorized live checks |

Library consumer migrations and releases follow their stated evidence and ownership
requirements. Credential integration, dependency lower-bound tests, all Python versions
and registry publication remain separate verification gates. Source consolidation grants
no cloud mutation, automatic authentication change or external publication authority.

## References

Official uv guidance reviewed 2026-09-14:
[workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/),
[dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/),
[locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/), and
[building and publishing](https://docs.astral.sh/uv/guides/package/).
