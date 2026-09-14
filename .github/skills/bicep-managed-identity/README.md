# bicep-managed-identity

Provision **access, not credentials**. A user-assigned managed identity and every
grant it holds, declared in one reviewable template: named roles, single resource
scopes, a written reason per grant, idempotent by construction, plus a verifier
that checks the live permission surface afterwards.

Self-contained. Copy this folder anywhere. Deployment needs Azure CLI with Bicep;
the selftest needs only Python 3.10+ and runs offline.

```
bicep-managed-identity/
  README.md            you are here — threat model and design decisions
  SKILL.md             agent-facing: declare, preview, deploy, verify, remove
  CONTRACT.md          exact resource shapes, naming rules, role catalogue
  GOTCHAS.md           thirteen failures, symptom-first, four hit live
  bicep/
    main.bicep           one identity and every grant it holds
    roles.bicep          built-in role ids, named once, compile-time exported
    modules/
      identity.bicep                 the user-assigned identity
      role-assignment-search.bicep   one grant on a search service
      role-assignment-cognitive.bicep one grant on an AI account
  build/
    main.json            the compiled artefact, committed and asserted against
  scripts/
    deploy.sh            what-if, deploy, verify — in that order
    verify.py            live permission surface vs what was declared
  examples/
    deploy.bicepparam    a worked parameter file
  tests/
    selftest.py          62 checks: template invariants + render-and-diff
```

---

## 1. The problem

Access is granted in three places and reviewed in none of them.

| How access usually arrives | Why nobody catches it |
| --- | --- |
| A portal click | No diff, no record of why |
| `az role assignment create` in a script | Random assignment name; not idempotent (G1) |
| A template with literal role GUIDs | The reviewer cannot tell read from owner |
| Resource-group scope "for convenience" | Silently covers resources added later (G5) |
| `listKeys()` into an app setting | A key in deployment history, and a rotation project (G10) |

The result is a permission surface nobody can state, and the failures are
asymmetric: over-granting has no symptom, while under-granting produces a 403
that gets "fixed" by widening the role.

## 2. The approach

**The template is the permission surface.** Reviewing it is reviewing the access,
or it is not doing its job. Three properties make that true:

| Property | How |
| --- | --- |
| Roles are readable | `roleIds.searchIndexDataContributor`, never a GUID (G5) |
| Grants are idempotent | `guid(scope, principalId, roleDefinitionId)` as the name (G1) |
| Grants are narrow | Scoped to one named resource, never a group |
| Grants explain themselves | A `reason` recorded on the assignment, visible in the portal and the verifier |
| Nothing is secret | No `listKeys`, no `@secure()` parameters, no key outputs (G10) |
| Identity outlives compute | User-assigned, so recreating the workload does not orphan its grants (G2) |
| Reality is checked | `verify.py` compares live assignments against the declared list, both directions |

## 3. Failure model

**Prevents:** duplicate or non-idempotent assignments; a grant nobody can
evaluate in review; Owner or User Access Administrator on a workload identity;
secrets read into deployment history; a grant on a resource in the wrong resource
group; an assignment failing because the principal has not replicated.

**Does not prevent:** a grant correct but unnecessary; a role too broad yet
plausible; someone with Owner granting out of band — `verify.py` reports it as an
undeclared grant, which is the finding.

**Does not attempt:** subscription- or management-group-scoped assignments. One
line to add, almost never what was meant.

**The honest limit — acceptance is weaker here than in a code box.** No fake
Azure to substitute, and the artefact *is* the side effect. Acceptance is a
different shape, not a weakened one:
1. **Invariants over the compiled template** — deterministic names, principal
   types, written reasons, no secret-reading functions, no dangerous roles
   granted. Offline, 62 checks.
2. **Render-and-diff** — recompile, compare to the committed `build/main.json`.
   Drift means sources changed without regenerating the reviewed artefact.
3. **Live verification after deployment** — `verify.py`, the only step catching
   G12, where a policy rewrites the resource *after* the control plane returns
   success.

None of it proves a deployment will succeed. That is `deploy.sh` against a real
subscription.

## 4. Why it is portable

No subscription id, tenant, resource name or principal appears in any template —
asserted by the selftest. Everything is a parameter, every grant conditional, so
an absent target is skipped rather than a deployment error.

The seam is the module boundary: a new target type is a five-line copy of
`role-assignment-search.bicep` with the resource type changed. Deliberate
duplication — a role assignment's `scope` must reference an `existing` resource
of a specific type, and Bicep cannot express "a resource of whatever type this id
points at". A generic module taking a resource id **cannot be written**.
## 5. Design decisions worth keeping

- **`guid(scope, principalId, roleDefinitionId)` as the assignment name.**
  Stable, unique per triple, idempotent. `newGuid()` creates a new assignment
  every deployment; a hand-rolled name collides (G1).
- **Roles as an exported variable, not a module with outputs.** A module is a
  nested deployment whose outputs exist only at runtime, so the values cannot be
  used where the compiler needs them. `@export()` costs nothing.
- **`principalType` on every assignment.** Without it, a deployment running
  before the identity replicated fails claiming the principal does not exist
  (G4).
- **User-assigned, not system-assigned.** A system-assigned identity dies with
  its resource and silently orphans every grant, because an assignment holds a
  principal id, not a name (G2).
- **A `reason` on every grant.** Survives into the portal and `verify.py` output,
  so an audit reads the justification instead of inferring it. Also the field a
  `description` parameter would have broken (G8).
- **The compiled artefact is committed.** It is what actually deploys, so it is
  what gets reviewed and diffed. The selftest fails on drift from sources.
- **Two search roles, always.** Control plane and data plane are separate
  permission systems; conflating them is the commonest mistake here (G3).
- **The search service's own identity is a separate parameter.** A different
  principal from the workload identity; treating them as one produces G6's 502.

## 6. Quick start

The client supplies this skill's installed directory. Vendor `bicep/`, `build/`
and `scripts/` together under the project's `deploy/infra/identity/`, preserving
their relative layout. Commands below are what the authorized `deploy/deploy.sh`
calls from that copy; this directory never becomes a second operator entry point.
```bash
./scripts/deploy.sh -g <rg> -n id-my-workload \
    -s <search-service> -a <ai-account> -A <ai-account-rg> -V
```

What-if, a confirmation, the deployment, then verification. Preview only with
`-p`. To check an existing deployment at any time:

```bash
python3 scripts/verify.py -g <rg> -n identity-id-my-workload --strict
```

Prove the templates hold before deploying anything:

```bash
python3 tests/selftest.py        # 62 checks, offline
```

## 7. Removal

```bash
az deployment group delete -g <rg> -n <deployment>     # removes the record only
az role assignment delete --assignee <principalId> --scope <scope> --role "<role>"
az identity delete -n <identity> -g <rg>
```

Deleting the deployment record removes nothing. Grants and identity are resources
and must be deleted explicitly, in that order: deleting the identity first leaves
assignments pointing at a principal that no longer exists, the state described in
G2.

## 8. Provenance

Portable migration copied `core/skills/dep/bicep-managed-identity` without changing
templates, compiled output or verifier. The reviewed `build/main.json` is required
deployment input, not a disposable cache. No cloud operation was part of migration;
source-era live observations below are not a current deployment result.

Built and deployed against a live sandbox subscription: a user-assigned identity
and four role assignments across two resource groups — index management, document
access, model access, plus the search service's own identity for server-side
vectorization. Redeployed to confirm idempotency, verified with
`scripts/verify.py`, which read back every grant with its recorded reason.

**Four of the thirteen gotchas were hit during that work**, not recalled:

- **G1** — the first deployment failed with `RoleAssignmentExists` naming an id
  the template never created. An earlier `az role assignment create` grant had a
  random name; the template computes a deterministic one. Same grant, two
  identities, collision. Deleting the CLI-created assignment and redeploying
  fixed it; every redeployment since is a clean no-op.
- **G8** — a parameter named `description` shadowed the `@description` decorator,
  producing a cascade of `BCP062`/`BCP079` errors on unchanged lines.
- **G11** — `what-if` reported the role assignments as `Unsupported`, their names
  depending on a principal that does not exist until deployment runs. An empty
  what-if does not mean nothing will change, which is why `main.bicep` outputs
  the grant list and `verify.py` exists.
- **G6** — reproduced from the search side: an index carrying a vectorizer was
  accepted with no identity attached and failed queries with a 502 until the
  search service was granted model access. The gotcha's remedy is the one run.

Also corrected during the build: the first least-privilege check searched the
whole compiled template for dangerous role GUIDs and failed, because the role
*catalogue* is compiled into it. Checking "which roles are catalogued" instead of
"which roles are granted" is the difference between a permission review and a
list of roles that exist; the check now resolves `variables('roleIds').<name>`
for assignments only.