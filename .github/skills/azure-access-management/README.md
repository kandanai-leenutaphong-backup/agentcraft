# azure-access-management

Azure identity and permission management that can be reviewed before it runs,
proved after it runs, and taken back afterwards. Standard library only.

## Why this exists

Access work has three failure modes that ordinary tooling does not catch,
because none of them looks like an error:

1. **A write that reported success and did not persist.** Governance policies
   revert settings after ARM returns `201`. A tool that trusts the status code
   reports a grant that is not there.
2. **An answer that was true and incomplete.** "The identity can read the
   container" is compatible with a subscription-wide Contributor assignment
   nobody intended to keep. Effective access and exact assignments are different
   questions, and conflating them makes a least-privilege migration a no-op.
3. **A teardown that removed the visible plane only.** Cosmos DB, Azure Data
   Explorer and Azure SQL grants are not Azure RBAC. `az role assignment delete`
   never touches them, so an identity that has been "fully revoked" is still
   reading data.

Every design decision here comes from one of those three.

## Adoption boundary

For an installed agent plugin, start with the MCP section below. For a Python application,
keep the original package-adoption boundary:

Copy the folder, install it, one import, one call site:

```bash
cp -r azure-access-management <your-repo>/skills/
pip install <your-repo>/skills/azure-access-management
```

```python
from azaccess import AccessManager, bounded_policy

manager = AccessManager(providers, policy=bounded_policy(
    tenant_id=TENANT_ID, scopes=[ALLOWED_SCOPE], max_tier="read"))
```

The install is what puts `azaccess` on the import path; copying alone leaves it
one directory down, where nothing finds it. It declares **no runtime
dependencies** — `pip install "…[live]"` is an optional convenience that pulls
`azure-identity` for hosts that want a ready-made credential, and no module here
imports it. Everything also runs uninstalled from inside the folder with
`PYTHONPATH=.`.

`AccessManager` is the single public entry point. It exposes the whole
interface — `inspect`, `plan`, `diff`, `confirm`, `apply`, `verify`,
`verify_one`, `revoke` — and owns the authority policy, the plane adapters and
the ownership ledger. Everything else the package exports is a value type you
pass to it, an adapter you register with it, or an error it raises.

Constructing it grants nothing: the default policy is read-only, so `apply`
refuses until the host widens the policy deliberately and supplies a
target-bound confirmation token. Nothing is registered globally, no module is
monkey-patched, and no file is written outside this folder.

## Failure model

- **Refusal is a normal outcome.** Anything outside the tenant or scope
  allowlist, above the authorised tier, or missing a confirmation token is
  refused locally and recorded as data on the plan (`plan.refusals`,
  `report.refusals`). The CLI exits `1`; nothing is sent.
- **Every write is read back at exact scope.** A create whose read-back
  disagrees is `revert-suspected`, never success.
- **Waiting is bounded and honest.** Verification polls to a budget and reports
  `present`, `absent`, `unknown` or `revert-suspected` with `waited_secs`.
  `unknown` means the read failed — a different fact from "not there".
- **Errors carry a category** — `coordinate`, `authentication`, `authorization`,
  `transport`, `conflict`, `policy` — because the four causes of a 403 need four
  different responses.
- **Response detail is sanitised** before it reaches an error, a log or a
  result. No token, key, connection string or password shape survives.
- **Ownership gates deletion, and adoption is not ownership.** `revoke` removes
  only ids this run **created** — read from the service's own create response,
  or from a read-back of the exact target it PUT — or ids the caller explicitly
  authorised with `--authorized-id`. An assignment this run merely *adopted*
  (ARM's `409 RoleAssignmentExists`, or a pre-existing Cosmos, Kusto, Graph or
  SQL match) belongs to somebody else and is refused. Before any delete, the
  assignment currently readable at that scope must still be the recorded id and
  still match the declaration exactly.
- **A cleanup coordinate outlives an unproven delete.** The ownership record and
  its ledger file are dropped only when that exact id is proved gone. An
  accepted `202`, a read-back that still shows the target, or a read-back that
  failed keeps them and reports the reason in `RevokeReport.retained`. Another
  writer's assignment at the same scope is reported and left alone; it never
  blocks completion and is never deleted.
- **A ledger write that fails after a successful grant is an outcome, not an
  exception.** The created id is reported in `ApplyReport.ledger_failures`,
  because raising there would discard the only thing that could clean it up.
- **Reads are bounded too.** `inspect`, `plan`, `diff` and `verify` are checked
  against the same scope allowlist as mutations, because a read is a disclosure
  and it carries a token. Widening is the explicit
  `AuthorityPolicy(enforce_read_bounds=False)`, and `describe()` says so.
- **A token only goes where configuration says.** Every live transport is bound
  to one `CloudEndpoints` and one audience, and validates the URL *before*
  asking the credential for anything. Pagination follows `nextLink` only
  same-origin; redirects are refused, not followed.
- **An accepted long-running create is `pending`, not lost.** A Cosmos or Kusto
  `202` is polled to a bound and the target read back. If it cannot be resolved,
  `ApplyReport.pending` carries the target id so it can be cleaned up.

## MCP Plugin

The `harness-data@harness` bundle adds five tools while leaving the Python API's mutation
workflow intact. `azaccess_status`, `azaccess_matrix`, `azaccess_role` and `azaccess_scope` are
offline. `azaccess_inspect` is the only live operation, and it only lists Azure RBAC assignments.
No MCP confirmation, mutation, secret-value read, resource lifecycle or executable configuration exists.

Status locates `${PLUGIN_DATA}/azure-access-management/config.json`. To authorize inspection,
the operator configures `tenant_id`, `subscription_id`, `scopes` and `allow_live_reads: true`.
Every configured scope must be inside that subscription. Tool input carries only a principal ID
and an in-policy scope; the existing `AccessManager` still enforces read bounds.

`cloud` defaults to `AzureCloud` and accepts the library's documented cloud names; `timeout_secs`
defaults to 30 (maximum 120) per CLI request. Live inspection requires Azure CLI sign-in and
checks that its subscription record matches the configured tenant before inspection. Installation
does not sign in, change the active subscription, create an identity, or grant a role.

The output preserves `partial` or `unknown` completeness. The support matrix describes all
five Python-library planes, not five implemented MCP inspection planes. Fixture transport
tests prove serialization and authorization logic, not a live tenant's behavior.

```bash
uv sync --locked --no-default-groups --no-install-project --extra mcp
.venv/bin/python scripts/mcp_server.py --selftest
```

The optional SDK runtime and cache are isolated from the other plugin servers. Base `azaccess`
still has no third-party dependency. Disabling the server or uninstalling the plugin changes no
role assignment, principal, resource or ownership record.

## Limits — what it does not do

- **No resource lifecycle.** It never creates, deletes or reconfigures an Azure
  resource, a policy assignment, a network rule or a firewall. Diagnosing that a
  policy reverted a write is in scope; bypassing the policy is not.
- **No secret values.** Key Vault *role assignments* are in the catalogue;
  secret, key and certificate contents are never read.
- **Effective access is never complete.** PIM eligibility, deny-assignment
  evaluation, transitive group membership, ABAC condition evaluation,
  management-group ancestry and Entra directory roles are not evaluated. They
  are named in every answer (`UNEVALUATED_SEMANTICS`) instead of being silently
  omitted. A condition is *serialised and compared*, never evaluated; a
  group-granted identity's access is not resolved through its groups.
- **Directory writes are built, not sent.** Group membership calls and federated
  credential bodies are constructed and validated here; the host sends them with
  a Graph-scoped token. No Azure RBAC role — Owner included — grants Microsoft
  Graph permissions, so the prerequisites are documented rather than assumed
  (CONTRACT §8.2).
- **Some operations are documented, not coded** — PIM eligible assignments,
  admin consent, delegated scope grants, directory-role assignment, custom role
  definition lifecycle. The support matrix says which, and
  `python3 -m azaccess.cli matrix` prints it from the code.
- **SQL is delegated.** T-SQL is not HTTP. Statements are built and validated
  here; execution needs a host-supplied executor.
- **The Azure CLI backend reads only.** `az rest` reports no HTTP status and no
  headers, so it cannot tell `201 Created` from `202 Accepted` or from the
  `409` that should be adopted. `AzureCliTransport` refuses mutating methods;
  `apply` and `revoke` need `TokenCredentialTransport`, which reads the real
  status off the wire.
- **Nothing here has been run against a live Azure tenant.** Every test uses a
  recorded transport, an injected subprocess runner or an injected URL opener.
  That proves requests are serialised correctly and refusals happen before a
  credential is fetched; it does not prove a service accepted them.

## Removal

Uninstall the package (`pip uninstall azure-access-management`), delete the
folder, and remove the import. There is no global registration, no generated
file, no background process and no cloud state created by installing it.

To roll back cloud state this skill made, call `manager.revoke(declarations)` or
run the CLI `revoke` verb before deleting the folder.

Ownership lives in the manager instance, so the simplest path is to revoke in
the same process. For anything longer-lived, pass an `OwnershipLedger` (CLI:
`--ownership-ledger DIR`) and each created assignment is written to a file as it
is made, so a crash between `create` and `revoke` still leaves the ids
recoverable:

```bash
python3 -m azaccess.cli ledger --ownership-ledger ./.azaccess-ownership
```

That prints every recorded id and a manual cleanup command for each. It is
**evidence, not authority**: records read back from disk arrive as
`ledger-unverified` and `revoke` still refuses them, because a file anyone can
append to must not be able to direct a deletion. Pass an id to
`--authorized-id` once you have checked it yourself.

## Layout

| path | what it is |
| --- | --- |
| [SKILL.md](SKILL.md) | agent-facing: decide, install, use, verify, remove |
| [CONTRACT.md](CONTRACT.md) | the spec, sufficient to reimplement without this code |
| [GOTCHAS.md](GOTCHAS.md) | symptom-first failures, cited from the code |
| `azaccess/` | the mechanism |
| `azaccess/providers/` | one adapter per assignment plane |
| [examples/plan_apply_verify_revoke.py](examples/plan_apply_verify_revoke.py) | full lifecycle, offline |
| [examples/confirmation_lifecycle.py](examples/confirmation_lifecycle.py) | how a mutation is authorised: plan digest, named targets, ledger |
| [examples/least_privilege_migration.py](examples/least_privilege_migration.py) | inherited is not satisfied |
| [examples/native_planes.py](examples/native_planes.py) | the three planes RBAC teardown misses |
| [examples/abac_condition.py](examples/abac_condition.py) | a worked ABAC condition: built, sent, compared, never evaluated |
| [examples/group_membership.py](examples/group_membership.py) | group grants, the membership calls, and the `/$ref` delete trap |
| [examples/support_matrix.py](examples/support_matrix.py) | matrix asserted against the adapters |
| [scripts/live_check.py](scripts/live_check.py) | operator-triggered Azure probe, read-only, `--live` required |
| [tests/selftest.py](tests/selftest.py) | offline checks, no test framework needed |
| [tests/transport_offline.py](tests/transport_offline.py) | both live backends driven through injected seams |
| [pyproject.toml](pyproject.toml) | packaging: `azaccess`, no runtime dependencies, optional `live` extra |

## Verify it here

```bash
python3 tests/selftest.py            # offline; prints its own check count
python3 tests/transport_offline.py   # no socket opened
PYTHONPATH=. python3 examples/plan_apply_verify_revoke.py
PYTHONPATH=. python3 examples/confirmation_lifecycle.py
PYTHONPATH=. python3 examples/abac_condition.py
PYTHONPATH=. python3 examples/group_membership.py
python3 -m azaccess.cli matrix
```
