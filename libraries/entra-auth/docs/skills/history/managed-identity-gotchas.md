# GOTCHAS — bicep-managed-identity

Thirteen ways identity and RBAC templates fail, symptom first. Four were hit building this box
against a live subscription; the rest come from production. Numbers are stable: code cites them.

---

## G1 — Redeployment fails with RoleAssignmentExists, naming an id you never created

**Symptom.**

```
RoleAssignmentExists: The role assignment already exists.
The ID of the existing role assignment is 61b048fcfedc46c3984cf67d821c217f.
```

The template never deployed that id. The grant it describes is already in place.

**Cause.** Two name generators that disagree. A template computes a deterministic
GUID from the identifying triple — `guid(scope, principalId, roleDefinitionId)`.
`az role assignment create` generates a **random** name. Both create the same
grant under different identities, and the second collides.

Same failure with `newGuid()` or any input that changes between runs: every
deployment creates another assignment, or fails.

**Fix.** One owner per grant. If a grant is in a template, remove the
hand-created one first:

```bash
az role assignment delete --assignee <principal> --scope <scope> --role "<role>"
```

Then redeploy. Verified: deployment succeeds, every subsequent redeployment is a
no-op.

**Rule.** A resource whose name you do not control cannot be made idempotent.
Derive the name from the thing's identity, and let one system own it.

---

## G2 — Every grant silently stops working after a resource is recreated

**Symptom.** Access that worked yesterday returns 403. Role assignments still
listed. Nothing changed intentionally.

**Cause.** A role assignment stores a **principal id**, not a name. A
system-assigned identity is a property of its resource, so recreating the
resource yields a new principal id and every assignment points at one that no
longer exists. The assignments stay visible, listing an unknown principal, which
is why nothing looks wrong.

Deleting and recreating a *user-assigned* identity under the same name does the
same: new principal id, orphaned grants.

**Fix.** Use a user-assigned identity, created once, outliving the compute it is
attached to. Treat recreating it as a breaking change — grants must be
redeployed, and `scripts/verify.py` reports them missing.

**Rule.** Identity is a principal id, not a name. Anything changing the id
invalidates every grant, quietly.

---

## G3 — Index management works and document upload returns 403

**Symptom.** The identity creates and deletes indexes, and cannot read or write
documents. Same identity, service, endpoint.

**Cause.** Control plane and data plane are separate permission systems.
`Search Service Contributor` grants management of indexes as *objects*;
`Search Index Data Contributor` grants access to their *contents*. Neither
implies the other, and Owner on the subscription implies neither.

Same split for Storage (`Contributor` versus `Storage Blob Data Contributor`),
Key Vault, Event Hubs.

**Fix.** Grant both, explicitly, named so the review sees both. In `main.bicep`
they are two modules with two written reasons.

**Rule.** "Contributor" on a resource is about managing it, not using it.

---

## G4 — Deployment fails claiming the principal does not exist, and it does

**Symptom.**

```
PrincipalNotFound: Principal <guid> does not exist in the directory
```

The identity was created seconds earlier in the same deployment, and is visible
in the portal.

**Cause.** Directory replication. The role assignment API validates the principal
against a replica that has not seen it.

**Fix.** Set `principalType` on every assignment: the API then need not resolve
the principal to learn its type. Every assignment module declares it and the
selftest asserts it. For a newly created identity, also let the assignment depend
on the identity module — this template does so implicitly by consuming its
output.

---

## G5 — The template grants far more than the review believed

**Symptom.** Nothing. An audit months later finds a workload identity with
Contributor over a resource group.

**Cause.** Two habits. Resource-group scope because it is one line shorter than
two resource-scoped grants — Contributor at group scope covers every resource in
the group, including ones added later by someone else. And a literal role GUID,
which nobody reading the diff can evaluate.

**Fix.** Every grant names a specific resource, and the role is written as
`roleIds.searchIndexDataContributor` rather than a GUID. The selftest asserts no
template outside `roles.bicep` contains a literal role GUID, and that Owner, User
Access Administrator and Contributor are granted nowhere.

**Rule.** If reviewing the template does not tell you what access exists, it is
not the permission surface — it is a script.

---

## G6 — Vector queries return 502 "failed to authenticate", and your credentials are fine

**Symptom.** An index carrying a vectorizer is created without complaint.
Documents load. A text vector query then fails:

```
502  Could not complete vectorization action.
     The service failed to authenticate to the vectorization endpoint.
```

**Cause.** The **search service** calls the model account with its own identity,
not yours. Nothing in the index definition requires that identity to exist, so
the definition is accepted and the failure surfaces at query time as a 502 —
from the service's point of view, its dependency failed.

**Fix.** Give the search service an identity and grant it model access, which is
what `grantSearchServiceModelAccess=true` does. Its principal is a **different
principal** from the workload identity, hence a separate parameter. Verified
live: the same query returned hits about a minute after the assignment landed.

**Rule.** When service A calls service B for you, A's identity is a separate
thing to provision, and B's rejection is reported as A's problem.

---

## G7 — The Cosmos DB grant deploys and the application still cannot read

**Symptom.** A data-plane role appears assigned. Every request is refused.

**Cause.** Cosmos DB's NoSQL data plane does not use Azure RBAC role assignments.
It uses `Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments`, with its own
role definitions scoped inside the account. A
`Microsoft.Authorization/roleAssignments` naming a Cosmos data role deploys
successfully and does nothing.

**Fix.** Use the account's own assignment type. The role catalogue here lists
only the Cosmos **control-plane** role, with a comment saying exactly this, so no
reader is led into the trap by an entry that looks usable.

**Rule.** Not every "role assignment" in Azure is an RBAC role assignment.

---

## G8 — A parameter named `description` breaks every decorator in the file

**Symptom.** A cascade of errors pointing at lines you did not change:

```
BCP062: The referenced declaration with name "description" is not valid.
BCP079: This expression is referencing its own declaration, which is not allowed.
```

**Cause.** `param description string` shadows the `@description()` decorator.
Every decorator in the file resolves to the parameter, and the resource setting
`description:` from it references itself.

**Fix.** Name it anything else. These modules use `reason`, which reads better on
a role assignment: recorded on the assignment, visible in the portal and in
`scripts/verify.py` output.

**Rule.** Where decorators and parameters share a namespace, a parameter can
shadow the language.

---

## G9 — A grant on a resource in another resource group silently targets the wrong one

**Symptom.** `ResourceNotFound` for a resource you can see, or a grant landing on
a same-named resource in the deploying group.

**Cause.** An `existing` reference resolves in the **deployment's** resource
group. Naming a resource in another group does not reach it.

**Fix.** Scope the *module*, not the reference:

```bicep
module modelAccess 'modules/role-assignment-cognitive.bicep' = {
  name: 'model-access'
  scope: resourceGroup(aiAccountResourceGroup)
  params: { ... }
}
```

Verified live across two resource groups in one deployment.

---

## G10 — The template reintroduces the secrets the identity was meant to remove

**Symptom.** None. The deployment works. A key appears in deployment history,
readable by anyone with reader access to the resource group.

**Cause.** `listKeys()`, `listAdminKeys()`, `listConnectionStrings()` and
friends read live secret material into the template, and anything the template
touches lands in the deployment record.

**Fix.** Do not use them. The selftest asserts no source and no compiled artefact
calls one, and no output name ends in `key`, `secret`, `password` or
`connectionString`. This box provisions **access**, never credentials — which is
why rotation is a non-event: there is nothing to rotate.

---

## G11 — what-if shows no changes, and the deployment changes things

**Symptom.** `az deployment group what-if` reports role assignments as
`Unsupported`, explaining that resource ids cannot be calculated, or omits them.
The deployment then creates them.

**Cause.** The assignment name is `guid(scope, principalId, role)` and the
principal does not exist yet — the same deployment creates it. what-if cannot
evaluate the expression, so it cannot identify the resource, so it declines to
analyse it.

**Fix.** Read what-if for what it can analyse; treat the grant list as the
authority for what will change. `main.bicep` outputs `grants` for this reason and
`scripts/verify.py` asserts them afterwards against the live surface.

**Rule.** An empty what-if is not a statement that nothing will change. It can
also mean it could not tell.

---

## G12 — The deployment succeeds and the resource does not match the template

**Symptom.** An ARM write returns HTTP 200. `provisioningState` is `Succeeded`.
Compliance clean. The property is not what the template said, or reverts shortly
after.

**Cause.** An Azure Policy **`Modify`** effect — not `Deny`, which would fail
loudly. It rewrites the request or the resource after the fact, and is frequently
assigned at management-group scope, so it does not appear in
`az policy assignment list` at resource, group or subscription scope, and nothing
in the deployment output mentions it.

**Fix.** Find it in the **Activity Log**, filtering for
`Microsoft.Authorization/policies/modify/action`. Then request an exemption
scoped to the specific resource:

```bash
az policy exemption create --exemption-category Waiver \
    --policy-assignment <assignment-id> \
    --policy-definition-reference-id <reference-id> \
    --scope <resource-id>
```

Requires rights at the scope the assignment lives on. Meanwhile
`scripts/verify.py` turns this from invisible into a failed check.

**Rule.** A successful write is not a durable write. Verify state, not the status
code.

---

## G13 — The workload starts before its access exists

**Symptom.** A pipeline that grants access and immediately runs something gets
403 for the first minute, then works.

**Cause.** Role assignment propagation. The assignment is created immediately;
the authorisation layer takes uncontracted time to see it.

**Fix.** Retry the first authenticated call rather than sleeping a guessed
interval. Do not "fix" it by widening the grant — a broader role propagates no
faster. Where a pipeline must gate on it, poll the operation that needs the
access until it succeeds.
