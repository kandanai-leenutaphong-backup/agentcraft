---
name: azure-access-management
description: >
  Use when Azure identity, RBAC or permissions work has to be correct rather
  than merely applied: granting or revoking access for a managed identity,
  service principal, user or group; auditing who can reach a resource; a 403
  or PrincipalNotFound whose cause is unclear; least-privilege migration off a
  subscription-wide Owner or Contributor; a role assignment that "succeeded"
  and is not there; teardown that leaves Cosmos DB, Azure Data Explorer or SQL
  access intact because only Azure RBAC was revoked; deciding whether access is
  exact or inherited; ABAC conditions, PIM, deny assignments and what an
  effective-access answer can honestly claim; Microsoft Graph app role
  assignments and workload identity federation. Plans and reads by default,
  mutates only under an explicit policy and a target-bound confirmation.
---

# Azure access management

**Six verbs — inspect, plan, diff, apply, verify, revoke — over five planes,
read-only until somebody says otherwise, and never claiming an answer is
complete when it is not.**

## Decide

Use this skill when any of these is true:

- a grant has to be made or removed and somebody will later ask exactly what
  changed;
- access is being tightened and "it still works" is not evidence that the wide
  assignment is gone;
- a 403 is being diagnosed and authentication, authorisation, network and
  policy have not been told apart;
- teardown must actually remove access, on every plane the identity was given.

Do **not** use it for:

- creating, moving or deleting Azure *resources* — this is access management,
  and every adapter refuses resource lifecycle by design;
- reading secret, key or certificate *values* — the skill handles Key Vault
  role assignments and never touches a vault's contents;
- bypassing governance. Diagnosing that Azure Policy reverted a write is in
  scope; defeating the policy is not.

If the whole job is "grant one role once, by hand, and never audit it", a single
`az role assignment create` is smaller and honest. The moment a second question
follows — did it land, at what scope, and how do we take it back — this skill is
cheaper.

## Installed Plugin

The `harness-data@harness` bundle supplies five MCP tools: `azaccess_status`, `azaccess_matrix`,
`azaccess_role`, `azaccess_scope`, and `azaccess_inspect`. The first four are offline. Inspection
requires an operator-configured tenant, subscription, allowed scopes and `allow_live_reads`.
Status reports the settings path; tool arguments cannot supply credentials or widen the policy.

MCP inspection covers Azure RBAC only and always preserves the partial/unknown completeness claim.
It is not a five-plane effective-access audit. The matrix describes the wider Python library.
There are no MCP apply, confirm, revoke, group-membership or resource-lifecycle tools. Use the
reviewed Python/CLI workflow below for authorized mutations, outside this MCP adapter.

```bash
uv sync --locked --no-default-groups --no-install-project --extra mcp
.venv/bin/python scripts/mcp_server.py --selftest
```

The SDK check uses a recorded transport and proves out-of-scope refusal before transport.
Disable the server or uninstall the bundle to remove MCP access. Existing role assignments and
ownership ledgers are not changed by plugin installation or removal.

## Standalone Python Install

Copy the folder, then install it. It is standard library only, so the install
adds no dependency to your tree — it just puts `azaccess` on the import path,
which copying alone does not do.

```bash
cp -r azure-access-management /path/to/your/repo/skills/
pip install /path/to/your/repo/skills/azure-access-management
python3 -c "from azaccess import AccessManager; print(AccessManager)"
```

From then on `from azaccess import …` and `python3 -m azaccess.cli` work from
any directory, with no `PYTHONPATH` and no `sys.path` edit. Add `-e` if you
intend to modify the package in place; the default non-editable install copies
it into the environment.

Without installing, everything still runs **from inside the copied folder** —
that is what the `PYTHONPATH=.` lines under [Verify](#verify) are for, and
`scripts/live_check.py` and `tests/selftest.py` add the folder to `sys.path`
themselves so they work either way.

```bash
cd /path/to/your/repo/skills/azure-access-management
python3 tests/selftest.py           # offline; no credential, no network
```

For live use, one of:

- the Azure CLI on `PATH` and `az login --tenant <tenant-id>` — used by
  `AzureCliTransport`, which needs no Python package at all. **Reads only**:
  `az rest` reports no HTTP status, so it cannot distinguish `201 Created` from
  `202 Accepted` or from the `409` that means "already exists", and a mutation
  through it would be a guess;
- any object with `get_token(scope)` (for example `DefaultAzureCredential`) —
  passed to `TokenCredentialTransport`, which reads real statuses and headers
  and is what `apply` and `revoke` require. That library is then the caller's
  dependency, not this skill's — `pip install "…/azure-access-management[live]"`
  is a convenience that pulls `azure-identity`, and nothing here imports it.

Both are bound at construction to one `CloudEndpoints` (public, US Government,
China, or one you build) and one token audience, and refuse any URL outside it
*before* a credential is fetched.

No key, connection string or persisted secret is ever read or accepted.

## Use

The whole surface is one object.

```python
from azaccess import (AccessDeclaration, AccessManager, ArmRbacProvider,
                      AzureCliTransport, OwnershipLedger, bounded_policy,
                      user_assigned_identity)

transport = AzureCliTransport()
policy = bounded_policy(                     # read-only, one tenant, fixed scopes
    tenant_id=TENANT_ID,
    scopes=[f"/subscriptions/{SUB}/resourceGroups/app-rg"],
    max_tier="read",
)
manager = AccessManager(
    {"azure-rbac": ArmRbacProvider(transport, subscription_id=SUB)},
    policy=policy,
)

identity = user_assigned_identity(principal_id=PRINCIPAL_ID, tenant_id=TENANT_ID)
declaration = AccessDeclaration(
    principal=identity,
    role="Storage Blob Data Reader",
    scope=f"{ACCOUNT_ID}/blobServices/default/containers/inbox",
)

print(manager.inspect(PRINCIPAL_ID, ACCOUNT_ID).to_dict())   # 1. what is there
plan = manager.plan([declaration])                           # 2. what would change
print(manager.diff([declaration]).to_dict())                 # 3. desired vs observed
```

Mutating needs three deliberate acts — widening the policy, reviewing the exact
plan, and confirming each exact target:

```python
writable = policy.with_authorized(read_only=False)
manager = AccessManager({"azure-rbac": provider}, policy=writable,
                        ownership_ledger=OwnershipLedger("./.azaccess-ownership"))

plan = manager.plan([declaration])
print(plan.digest())                    # what a reviewer approves
approved = plan.to_dict()["confirmation_required"]   # the exact fingerprints
tokens = manager.confirm(plan, fingerprints=approved)  # single-use, target-bound
report = manager.apply(plan, confirmations=tokens)   # 4. apply, then read back
report.pending           # accepted long-running creates, with their target ids
results = manager.verify([declaration])              # 5. verify at exact scope
teardown = manager.revoke([declaration])             # 6. revoke what it CREATED
```

`revoke` deletes only what this run created. Anything it merely adopted — a
grant that already existed — is reported and left in place; deleting it is a
separate decision, made by passing the id to `authorized_ids`.

From the command line, offline verbs first:

```bash
python3 -m azaccess.cli matrix              # what is supported, on which plane
python3 -m azaccess.cli roles --tier administrative
python3 -m azaccess.cli scope /subscriptions/<sub>/resourceGroups/<name>
python3 -m azaccess.cli plan --live --tenant <t> --subscription <s> \
    --scope /subscriptions/<s>/resourceGroups/<name> \
    --principal <object-id> --declarations declarations.json --save-plan plan.json
```

Then `apply` quotes back what was reviewed — the plan's digest and each
fingerprint. There is no "yes" flag:

```bash
python3 -m azaccess.cli apply --live --write --tenant <t> --subscription <s> \
    --scope <allowlisted-scope> --principal <object-id> \
    --declarations declarations.json \
    --expect-digest <digest from plan.json> \
    --confirm-target <fingerprint> \
    --ownership-ledger ./.azaccess-ownership
```

Exit codes: `0` yes/succeeded, `1` refused/failed/not-present, `2` bad usage.
Without `--live` the estate verbs exit 1 and print the commands that do work.

### The five planes

| plane | what it is | removed by an ARM role-assignment delete? |
| --- | --- | --- |
| `azure-rbac` | `Microsoft.Authorization/roleAssignments` | yes |
| `cosmos-sql-rbac` | Cosmos DB SQL role assignment | **no** |
| `kusto-database` | Data Explorer database principal assignment | **no** |
| `sql-database-user` | contained database user + `GRANT` | **no** |
| `microsoft-graph` | app role assignment in the directory | **no** |

A teardown that walks only the first row leaves the identity reading data.

### Two things the reference goes deeper on

**ABAC conditions.** `container_name_condition("blobs-example-container")` builds
the documented simple-condition form, and it is sent with
`conditionVersion: "2.0"`. A conditional grant is a *different target* from the
unconditional one — different fingerprint, different confirmation token. This
package serialises and compares conditions; it never evaluates one, and says so
in every effective-access answer. Worked example and refusals: CONTRACT §8.1.

**Groups.** Assign the role to a group once and manage people by membership. The
membership calls are built here and sent by the host, because
`DELETE /groups/{g}/members/{id}` **without** the trailing `/$ref` deletes the
user instead of the membership. Permissions, PIM for Groups, transitivity and
the rest: CONTRACT §8.2. Directory permissions are not implied by any Azure RBAC
role, Owner included.

## Verify

```bash
python3 tests/selftest.py                       # offline checks, no framework
python3 tests/transport_offline.py              # both live backends, no socket
PYTHONPATH=. python3 examples/plan_apply_verify_revoke.py    # full lifecycle
PYTHONPATH=. python3 examples/confirmation_lifecycle.py      # how a write is authorised
PYTHONPATH=. python3 examples/least_privilege_migration.py   # inherited != satisfied
PYTHONPATH=. python3 examples/native_planes.py               # the three non-RBAC planes
PYTHONPATH=. python3 examples/abac_condition.py              # a worked ABAC condition
PYTHONPATH=. python3 examples/group_membership.py            # group grants and the /$ref trap
PYTHONPATH=. python3 examples/support_matrix.py              # matrix matches the adapters
python3 -m azaccess.cli matrix
```

Each run prints its own check count; the numbers grow, so they are not quoted
here. Drop the `PYTHONPATH=.` once the package is installed.

Against a real estate, read-only:

```bash
az login --tenant <tenant-id>
python3 scripts/live_check.py --live --tenant <t> --subscription <s> \
    --principal <object-id> --scope /subscriptions/<s>/resourceGroups/<name>
```

What a green run proves: the requests are built correctly, the refusals fire,
and the state machine is right. What it does not prove: that Azure accepted
anything. **No test here has been run against a live tenant** — see
`GOTCHAS.md` G9 and the support matrix's own disclaimer.

## Remove

Uninstall the package and delete the folder, then remove the import:

```bash
pip uninstall azure-access-management
rm -r /path/to/your/repo/skills/azure-access-management
```

Nothing is registered globally, no file is written outside the folder and the
ledger directory you named, and no cloud state is created by installing it.

Cloud state this skill *made* is removed with `manager.revoke(...)` — which
deletes only what its ownership records say this run **created** — or with the
CLI:

```bash
python3 -m azaccess.cli revoke --live --write \
    --tenant <t> --subscription <s> --scope <allowlisted-scope> \
    --principal <object-id> --declarations declarations.json \
    --ownership-ledger ./.azaccess-ownership
```

Assignments this skill did not create — including ones it adopted because they
already existed — are reported and left alone. Removing those is a decision for
whoever made them, with `--authorized-id` or by hand. If a run was interrupted,
`python3 -m azaccess.cli ledger --ownership-ledger ./.azaccess-ownership` prints
the ids it recorded and a manual cleanup command for each; those records are
evidence, never authority for a delete.

## Read next

- [README.md](README.md) — adoption boundary, failure model, limits.
- [CONTRACT.md](CONTRACT.md) — the spec, sufficient to reimplement.
- [GOTCHAS.md](GOTCHAS.md) — symptom-first failures, cited from the code.
