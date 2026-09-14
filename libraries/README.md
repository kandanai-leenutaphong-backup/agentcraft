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
| [Azure data connectors](azure-data-connectors/README.md) | `azdata` / `azdata` | uv workspace member; offline contract/integration tests, wheel/sdist build and isolated wheel import verified. Skill/application migration and live acceptance are separate |
| [Azure access management](azure-access-management/README.md) | Distribution name not settled / existing `azaccess` contract | Test-only Azure RBAC SDK comparison passes; no new access runtime package or migrated consumer yet |

Workspace foundation and the first comparison are verified with uv `0.9.30` and Python
`3.11.14`. No release or cloud operation is authorized by this approval. Authentication,
resource provisioning, skill retirement and the separately owned connector implementation
are not part of the access-library increment.

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
  azure-access-management/            add as a member when its package exists
```

The [workspace configuration](pyproject.toml) registers only `azure-data-connectors` and
requires uv `0.9.30`; the [shared lock](uv.lock) records the resolution. Do not enroll
design-only directories, skills or template applications through a wildcard. Existing
build backends are retained; the connector still uses setuptools.

The root `access-comparison` development group depends on the current access skill
package through an explicit local source. This temporary comparison reuses that owner's
public imports without copying it or making it a workspace member. It is not a runtime
dependency of `azdata` or a publishable access package. The local source follows the
checkout; the lock does not freeze its source bytes. Remove this comparison dependency
when canonical access packaging and consumer migration replace it.

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
following workflow passed in the first increment; tests remain offline.

```bash
uv lock --check
uv sync --locked --package azdata --no-default-groups
uv run --locked --package azdata --no-default-groups python -m unittest discover -s azure-data-connectors/tests/contract -v
uv run --locked --package azdata --no-default-groups python -m unittest discover -s azure-data-connectors/tests/integration -v
uv build --no-sources --package azdata --out-dir dist/azdata
```

The access comparison uses a separate environment and only its development group:

```bash
UV_PROJECT_ENVIRONMENT="$PWD/.venv-access-comparison" uv sync --locked --only-group access-comparison
UV_PROJECT_ENVIRONMENT="$PWD/.venv-access-comparison" uv run --locked --only-group access-comparison python -B -m unittest discover -s azure-access-management/tests/comparison -v
```

The [comparison record](azure-access-management/tests/comparison/README.md) names exact
SDK versions, observations and remaining gaps. No `PYTHONPATH` is needed for either group.

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
| 2. Access SDK comparison | Complete for the test-only first slice, not production parity | 11 SDK comparison tests; existing access self-test: 271 checks, 0 failures; no Azure requests |
| 3. Access packaging | Canonical installed package and named migrated consumers | Existing contract behavior, isolated artifacts and no competing maintained implementation |
| 4. Later gaps | Only consumer-justified inspection, reconciliation or prerequisite reports | Separate observable acceptance for each addition |

The approval started increments 1 and 2. Later source retirement, consumer migrations
and new features follow their stated evidence and ownership requirements. Full access SDK
parity, credential integration, dependency lower-bound tests, all Python versions and
registry publication remain unverified. No cloud mutation, automatic authentication change
or external publication is included.

## References

Official uv guidance reviewed 2026-09-14:
[workspaces](https://docs.astral.sh/uv/concepts/projects/workspaces/),
[dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/),
[locking and syncing](https://docs.astral.sh/uv/concepts/projects/sync/), and
[building and publishing](https://docs.astral.sh/uv/guides/package/).
