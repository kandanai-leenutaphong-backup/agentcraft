---
name: azure-access-management
description: "Use for Azure access and identity workflows: Entra API JWT validation and record ownership, browser/session PKCE and Container Apps frontend sign-in, native Easy Auth/MSAL, managed identity and Bicep/AVM, PIM and deployment approvals, RBAC and Cosmos/ADX/SQL/Graph permissions, 401/403 diagnosis, exact-scope verification and owned cleanup. Native workflows first; retained compatibility helpers and read-only MCP inspection. Plans never execute commands or grant authority; cloud mutations need explicit target-bound authorization. Replaces the former separate entra-api-auth, entra-auth-container-apps and bicep-managed-identity entries."
license: MIT
---

# Azure Access And Identity

**One task entry, native workflows first.** Identify the outcome, choose the existing
implementation that fits, then verify exact state and the unauthorized path. This skill
does not create a replacement identity platform or orchestration service.

## Route The Task

| Need | Read | Script Or Retained Surface |
| --- | --- | --- |
| Approval, temporary privileges, declarative ownership or recovery | [Native workflows](./references/native-workflows.md) | PIM, pipeline checks, Terraform/deployment stacks; `scripts/workflow.py plan access` only prepares a plan |
| Entra API JWT, 401/403, scopes/roles or record ownership | [API authentication](./references/api-auth.md) | Supported framework/JWT validation; optional compatibility APIs and token diagnostics |
| Sign in a Container Apps frontend | [Container Apps](./references/container-apps.md) | Native Easy Auth; offline `scripts/workflow.py plan container-apps` |
| Browser PKCE, sessions, or investigation frontend migration | [Frontend sign-in](./references/frontend-signin.md) | MSAL/Easy Auth comparison; strict `entra_auth` helpers retained without changing host routes |
| Workload identity and resource-scoped grants | [Workload identity](./references/workload-identity.md) | Bicep/AVM and retained tested assets, only through host `deploy/deploy.sh` |
| Exact assignment inspection, five-plane helper APIs or owned revoke | [Access workflows](./references/access-workflows.md) | Existing `azaccess` CLI/Python and read-only MCP contracts |

The [complete inventory](./capabilities.json) has native equivalents, retained source,
limits and verification for every capability. Query it without installing dependencies:

```bash
python3 "$SKILL_ROOT/scripts/workflow.py" catalogue
python3 "$SKILL_ROOT/scripts/workflow.py" describe platform-session
python3 "$SKILL_ROOT/scripts/workflow.py" check
python3 "$SKILL_ROOT/scripts/workflow.py" plan container-apps --config <non-secret-target.json>
```

Resolve `SKILL_ROOT` to this loaded directory. Plans return references, prerequisite steps
and read-back argv; they never run commands. Unknown fields, credentials, embedded approval,
unsafe target syntax and unreviewed custom-signature fallbacks refuse. A plan is not access.

## Authority And Safety

1. Distinguish end-user caller, administrative operator and workload managed identity.
   Authentication proves identity; the host separately authorizes the resource/record.
2. Name tenant, subscription, cloud, target, role/permission plane, current owner, mutation
   and verification. Installation, a CLI login or a returned plan authorizes none of them.
3. Prefer an existing lifecycle/approval owner. Never add a competing writer or assume
   native support is absent because an SDK exposes only individual operations.
4. Put deployment mutations in the host's one entry point and runbook. Resource lifecycle
   outside identity integration belongs to `azure-cli-infra-management`; data writes belong
   to the data capability. PIM activation, consent and RBAC grants need their own authority.
5. Keep configured bounds independent of request data. No auth-disabled acceptance, no
   bypass headers, no subscription-wide grant as a shortcut, no secret values in artifacts.
6. Read back exact state, preserve pending/unknown results and test the matching refusal.
   Inheritance is not an exact declaration; an assignment is not proof of data-plane access.
7. Revoke only owned or explicitly authorized exact ids. A local ledger is evidence, not
   permission to delete; a local confirmation is not independent human approval.

## Native Frontend Default

For a new private Container Apps frontend, start with tenant-pinned Easy Auth and
`RequireAuthentication`. Supported provider-token headless calls do not require anonymous
ingress. A custom application-verified signature needs a separate, reviewed routing/gate
decision; loading this skill enables no agent path.

The retained investigation component is not a complete sign-in server. Its host owns
callback routes, cookies, CSRF, session revocation and the common authorization gate.
Native cookie/redirect/expiry parity requires an actual deployed migration test; no app
component is deleted or automatically replaced by this consolidation.

## Optional Compatibility

The retained `azaccess` package remains installable at this skill root with no required
third-party runtime dependencies. Its `live` extra supplies Azure Identity, and `mcp`
supplies only the optional adapter requirements. Neither enables live access.

Two independent auth contracts remain under `compatibility/`: legacy `entraauth` and
strict `entra_auth`. Install only what a named consumer requires; skill discovery does
not install either. **Legacy disabled mode is not a safe deployed default.** Require
enabled configuration; prefer supported native/framework flows for new integrations.

The [SDK comparator](./tests/sdk_comparison/README.md) is offline evidence only. It is
not a public provider, a new package or proof that custom orchestration is necessary.

## Verify

From the skill root, in the documented interpreter/dependency environment:

```bash
python3 scripts/workflow.py check
python3 -m unittest discover -s tests -p test_workflow.py -v
python3 tests/selftest.py
python3 tests/transport_offline.py
python3 scripts/mcp_server.py --selftest
python3 compatibility/api-auth/tests/selftest.py
python3 -m pytest compatibility/browser-auth/tests -q -p no:cacheprovider
python3 assets/managed-identity/tests/selftest.py
```

Dependency/setup details: [README](./README.md). Keep the original positive/refusal tests;
do not obtain a green result by disabling real authentication or removing a retained check.

## MCP And Removal

Preserved tools: `azaccess_status`, `azaccess_matrix`, `azaccess_role`, `azaccess_scope`,
`azaccess_inspect`. The first four are offline. Inspection is Azure RBAC only, requires
operator-configured target/read bounds, and remains partial/unknown. No mutation or
confirmation tool is added. The [contract](./CONTRACT.md) owns exact fields and limits.

Uninstalling the skill or optional packages removes no Azure grants, identities, sessions
or resources. Export required recovery evidence first; cleanup follows its existing
owner and separate authorization. [Consolidation evidence](./references/CONSOLIDATION.md)
records source preservation and current Pending Testing; no live result is implied.
