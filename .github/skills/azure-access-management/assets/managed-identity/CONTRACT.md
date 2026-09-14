# CONTRACT — bicep-managed-identity

Everything needed to reimplement this box in another IaC language against the
same platform. Exact resource shapes, naming rules, role catalogue.

---

## 1. Resources

### 1.1 User-assigned managed identity

```
type:       Microsoft.ManagedIdentity/userAssignedIdentities
apiVersion: 2023-01-31
name:       <identityName>
location:   <resource group location>
```

Outputs consumed downstream:

| Output | Use |
| --- | --- |
| `id` | attaching the identity to a workload |
| `principalId` | the subject of every role assignment |
| `clientId` | selecting this identity at runtime when several are attached |

`principalId` changes if the identity is recreated, even under the same name.
Every existing assignment then references a principal that no longer exists (G2).

### 1.2 Role assignment

```
type:       Microsoft.Authorization/roleAssignments
apiVersion: 2022-04-01
name:       guid(<scopeResourceId>, <principalId>, <roleDefinitionId>)
scope:      the target resource
properties:
  roleDefinitionId: subscriptionResourceId(
                      'Microsoft.Authorization/roleDefinitions', <guid>)
  principalId:      <principal object id>
  principalType:    ServicePrincipal | User | Group | ForeignGroup | Device
  description:      <why this access exists>
```

**Naming is the contract.** `guid(scope, principal, role)` is:

- deterministic — redeploying produces the same name, so the operation is a
  no-op rather than a duplicate or a conflict;
- unique per triple — two different grants cannot collide;
- independent of anything that changes between runs.

`newGuid()`, a hand-written name, or a timestamp-derived name each break one of
those (G1). `az role assignment create` generates a **random** name, so a grant
made by CLI and the same grant made by template are two different resources
describing one permission.

`principalType` must be set. Without it the API resolves the principal to
discover its type, which fails for an identity that has not replicated (G4).

---

## 2. Scoping rules

| Intent | How |
| --- | --- |
| Grant on a resource in this group | `scope:` the `existing` resource |
| Grant on a resource in another group | `scope:` the **module** to that group |
| Grant across subscriptions | separate deployment; out of scope here |

An `existing` reference resolves in the deployment's own resource group. Naming a
resource in another group does not reach it (G9).

One module per target resource type, because a role assignment's scope must
reference an `existing` resource of a specific type; a generic module taking an
arbitrary resource id cannot be expressed.

---

## 3. Role catalogue

Built-in role definition GUIDs are stable across every tenant and cloud, so they
are literals rather than lookups. Named once, in `roles.bicep`, exported at
compile time.

| Name | GUID |
| --- | --- |
| Owner | `8e3af657-a8ff-443c-a75c-2fe8c4bcb635` |
| Contributor | `b24988ac-6180-42a0-ab88-20f7382dd24c` |
| Reader | `acdd72a7-3385-48ef-bd42-f606fba81ae7` |
| User Access Administrator | `18d7d88d-d35e-4fb5-a5c3-7773c20a72d9` |
| Search Service Contributor | `7ca78c08-252a-4471-8644-bb5ff32d4ba0` |
| Search Index Data Contributor | `8ebe5a00-799e-43f5-93ac-243d3dce84a7` |
| Search Index Data Reader | `1407120a-92aa-4202-b7e9-c0e197c71c8f` |
| Cognitive Services User | `a97b65f3-24c7-4388-baec-2e87135dc908` |
| Cognitive Services OpenAI User | `5e0bd9bd-7b93-4f28-af87-19fc36ad61bd` |
| Cognitive Services OpenAI Contributor | `a001fd3d-188f-4b5d-821b-7da978bf7442` |
| Azure AI Developer | `64702f94-c441-49e6-a78b-ef80e0188fee` |
| Storage Blob Data Reader | `2a2b9908-6ea1-4ae2-8e65-a410df84e7d1` |
| Storage Blob Data Contributor | `ba92f5b4-2d11-453d-a403-e96b0029c9fe` |
| Storage Queue Data Contributor | `974c5e8b-45b9-4653-ba55-5f855dd0fb88` |
| Key Vault Secrets User | `4633458b-17de-408a-b874-0445c86b69e6` |
| Key Vault Secrets Officer | `b86a8fe4-44ce-4948-aee5-eccb2c155cd7` |
| Cosmos DB Account Reader | `fbdf93bf-df7d-467e-a4d2-9458aa1360c8` |
| Monitoring Metrics Publisher | `3913510d-42f4-4e42-8a64-420c390055eb` |

### 3.1 Control plane versus data plane

Routinely conflated pairs. Holding the first grants nothing of the second (G3):
| Manage the resource | Use its contents |
| --- | --- |
| Search Service Contributor | Search Index Data Contributor / Reader |
| Contributor (storage) | Storage Blob Data Contributor / Reader |
| Contributor (key vault) | Key Vault Secrets User / Officer |

### 3.2 Not RBAC at all

Cosmos DB's NoSQL data plane uses
`Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments`, with its own role
definitions scoped inside the account. A `Microsoft.Authorization/roleAssignments`
naming a Cosmos data role deploys successfully and grants nothing (G7).

---

## 4. Template outputs

```
identityId   string   resource id of the identity
principalId  string   object id — the subject of every grant
clientId     string   for runtime identity selection
grants       array    [{scopeType, scopeName, principalId, roleDefinitionId, role}]
```

`grants` exists because `what-if` cannot analyse assignments whose name depends
on a principal created by the same deployment (G11). It is the declared
permission surface, and what the verifier asserts against.

No output may name a credential. The selftest rejects any output whose name ends
in `key`, `secret`, `password` or `connectionString`, and any use of `listKeys`,
`listSecrets`, `listAdminKeys`, `listConnectionStrings`, `listAccountSas` or
`listServiceSas` anywhere in the box (G10).

---

## 5. Verification

Three levels, increasing cost and increasing truth.

**Level 1 — invariants over the compiled template.** Offline. Deterministic
names, `principalType` present, non-empty reason, role ids via
`subscriptionResourceId`, no literal role GUIDs outside the catalogue, no
hardcoded subscription or tenant, no secret-reading functions, Owner / User
Access Administrator / Contributor never actually granted.

"Granted" means reaching an assignment. The role *catalogue* is compiled into the
template, so a text search for a dangerous GUID reports the catalogue entry;
resolve `variables('roleIds').<name>` for assignment parameters only.

**Level 2 — render-and-diff.** Recompile the sources, compare to the committed
artefact, ignoring the compiler's `metadata._generator` stamp — otherwise every
compiler upgrade looks like a template change.

**Level 3 — live verification.** After deployment, compare live assignments
against `grants`, both directions:

| Finding | Meaning |
| --- | --- |
| declared, not present | removed or rewritten after a successful deploy (G12) |
| present, not declared | granted out of band, or a leftover |
| Owner / User Access Administrator | never correct for a workload identity |

Level 3 is the only one that can detect an Azure Policy `Modify` effect, which
returns HTTP 200, leaves `provisioningState: Succeeded`, and changes the
resource anyway.
