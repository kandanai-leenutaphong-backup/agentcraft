# Azure Access And Identity

One consolidated [skill entry](SKILL.md), **68 catalogued capabilities**, and native-first
guidance for API auth, frontend sign-in, workload identity and access administration.
Existing operational products already provide orchestration: this skill helps select and
integrate them. It does not claim those workflows are absent or replace them with a library.

## What Is Included

| Surface | Role |
| --- | --- |
| [Capability catalogue](capabilities.json) | Every source capability family, official equivalent, retained implementation, limit and verification route |
| [Workflow script](scripts/workflow.py) | Offline catalogue, describe, consistency check and non-executing native-first plan |
| [Native workflows](references/native-workflows.md) | PIM, approvals/locks, Terraform, deployment stacks, Easy Auth and supported identity clients |
| [Access helper](references/access-helper.md) | Preserved `azaccess` API, CLI, declarations, policy/evidence, five native planes and their existing limits |
| [API compatibility](compatibility/api-auth/README.md) | Existing `entraauth` imports and optional FastAPI integration, not a new recommended authentication stack |
| [Browser compatibility](compatibility/browser-auth/python/entra_auth/README.md) | Strict `entra_auth`, neutral claims, bounded JWKS staleness, PKCE and expiring stores |
| [Identity assets](assets/managed-identity/README.md) | Retained Bicep source, compiled artifact, scoped verifier and original refusal checks |
| [Frontend guidance](references/frontend-signin.md) | Native alternative and explicit compatibility tests for the investigation application's frontend |
| [SDK comparison](tests/sdk_comparison/README.md) | Preserved real-SDK/synthetic-transport evidence only, not a public provider |

The [source map](references/source-map.json) records every original file disposition;
[consolidation evidence](references/CONSOLIDATION.md) records baseline, recovery and
validation. Original source names may remain as catalogue aliases and historical provenance,
not active directories or additional native skills.

## Usage

Python 3.10+ is enough for routing; strict browser compatibility requires Python 3.11+.
From this skill root:

```bash
python3 scripts/workflow.py catalogue
python3 scripts/workflow.py describe frontend-native-migration
python3 scripts/workflow.py check
python3 scripts/workflow.py plan container-apps --config assets/target.example.json
```

The example target is synthetic. Plans contain references, prerequisites and read-back
argv; they never execute a command. They cannot carry credentials or approve themselves.
For a real change, the host owns operator authority, target configuration, deployment
entry point, independent approval and verification evidence.

## Dependencies

Native SDKs and platforms are reused, not copied. Loading the skill installs nothing.
Preserved packages remain individually installable in a consumer-owned interpreter:

```bash
python3 -m pip install "$SKILL_ROOT"
python3 -m pip install "$SKILL_ROOT/compatibility/api-auth[fastapi]"
python3 -m pip install "$SKILL_ROOT/compatibility/browser-auth[test]"
```

Install only required packages/extras. `azaccess` has no required third-party runtime
dependencies; `live` is an Azure Identity convenience and `mcp` supplies the optional
adapter. Auth packages use maintained PyJWT/cryptography and optional framework/store
dependencies. Their APIs deliberately differ and are not silently merged.

The root `uv.lock` covers access tooling and the `sdk-comparison` development group.
Compatibility packages own their metadata; no dependency on the libraries workspace or
an application checkout is required. For the access/MCP/comparison checks:

```bash
uv sync --locked --extra mcp --group sdk-comparison
uv run --locked --extra mcp --group sdk-comparison python -B tests/selftest.py
uv run --locked --extra mcp --group sdk-comparison python -B tests/transport_offline.py
uv run --locked --extra mcp --group sdk-comparison python -B scripts/mcp_server.py --selftest
uv run --locked --extra mcp --group sdk-comparison python -B -m unittest discover -s tests/sdk_comparison -v
```

The SDK comparator's pinned test versions are not public compatibility claims. Bicep and
OS tooling remain explicit prerequisites, not Python runtime dependencies or installation
side effects.

## Verification

Run the retained tests in an interpreter containing their selected packages:

```bash
python3 scripts/workflow.py check
python3 -m unittest discover -s tests -p test_workflow.py -v
python3 compatibility/api-auth/tests/selftest.py
python3 -m pytest compatibility/browser-auth/tests -q -p no:cacheprovider
python3 assets/managed-identity/tests/selftest.py
```

The package suites preserve positive and refusal behavior. Native frontend sign-in,
credential-reference resolution, real provider authorization, PIM/pipeline/IaC workflows,
replica replay behavior and any actual application migration remain **Pending Testing**.
Compilation and synthetic transports do not prove live results.

## MCP And Safety

Existing registration and tool names remain unchanged: `azaccess_status`, `azaccess_matrix`,
`azaccess_role`, `azaccess_scope`, `azaccess_inspect`. Only inspection can contact Azure,
and only with explicit operator-configured live-read bounds. It covers Azure RBAC, not all
five planes or complete effective access. No new write tool is registered.

The retained [access contract](CONTRACT.md) and [failure guide](GOTCHAS.md) define exact
interfaces. Native workflows take precedence when they meet the host's requirement.
Local confirmations are not independent approval; ledgers are not deletion authority;
absence of a response is not absence of a grant. Authentication does not replace
per-record authorization. The legacy auth disabled branch is never deployed acceptance.

Uninstallation deletes no cloud resource, role, session or credential. Preserve pending
evidence and use its existing owner with separately authorized cleanup. The retained
[MIT notices](LICENSE) travel with redistributed source; dependencies keep their own terms.

