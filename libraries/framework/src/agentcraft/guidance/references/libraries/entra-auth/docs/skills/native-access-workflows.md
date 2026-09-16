# Native Access Workflows

Administrative guidance only. There is no `azaccess` engine, planner, MCP server,
compatibility provider or new access package. Nothing here executes commands or
grants authority. Runtime application authentication remains with `entra_auth`;
[the host boundary](azure-access-management.md) remains separate.

## Select The Existing Owner

| Outcome | Native owner | Required boundary |
| --- | --- | --- |
| Time-bound privilege activation | [Entra PIM](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-configure) | Eligible assignment, supported resource/licensing, explicit activation, expiry and approval policy |
| Approval outside deployment code | [Azure Pipelines checks](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals?view=azure-devops) | Protected resource/service connection, independent approval and exclusive lock |
| Reviewed infrastructure changes and state | [Terraform plan/apply](https://developer.hashicorp.com/terraform/cli/run) | Reviewed saved plan, protected state, explicit import/adoption ownership |
| Bicep lifecycle | [Deployment stacks](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deployment-stacks) | Explicit delete/detach behavior and one owner per resource/grant |
| Workload identity and scoped grants | [Bicep RBAC](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/scenarios-rbac) and [AVM/native identity resource](https://learn.microsoft.com/en-us/azure/templates/microsoft.managedidentity/userassignedidentities) | Pin supported versions, preview exact scope, read back identity and grants |
| Frontend provider sign-in | [Container Apps Easy Auth](https://learn.microsoft.com/en-us/azure/container-apps/authentication) | Tenant pinning, assets/API gating, cookies/CSRF and matching refusals |
| Client token acquisition | [MSAL](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens) / [Azure Identity](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme) | Explicit selected identity, audience and lifetime; not incoming API validation |

## Authorized Operator Sequence

1. Name tenant, subscription, cloud, principal object ID, exact resource, permission
   plane, role/condition, current owner, proposed change and readback. Do not confuse
   application/client ID, principal object ID, managed-identity `principalId` and ARM ID.
2. Inspect through the native owner. Effective/inherited access is not an exact
   assignment. A CLI login, installed tool, plan or request's `approved: true` is
   not authority. Keep tenant/target allowlists and approval outside request data.
3. Obtain target-bound authorization before any resource, PIM, consent, Graph,
   database or RBAC mutation. Prefer least-privilege resource scope. Keep one
   writer; transfer ownership explicitly when moving from imperative operations
   to IaC. A same-process confirmation is not independent review.
4. Put all deployment actions and recovery in the host's `deploy/deploy.sh` and
   runbook. Preview with the native owner; do not create another ledger/engine.
   Native clients own serialization, paging and long-running operations.
5. Read back exact fields and exact assignment IDs through bounded observations.
   Keep accepted/pending/unknown distinct from absent. Confirm the intended data
   operation separately when authorized; a role listing does not prove it works.
6. Retire only owned or explicitly authorized exact IDs, using the current owner.
   Remove eligible grants before identities. Keep ownership/recovery records until
   exact-ID absence is observed. Never infer authority from names, tags or adoption.

## Permission Planes And Workload Details

Azure RBAC, Cosmos NoSQL SQL-role assignments, ADX database principals, SQL users
and Microsoft Graph permissions are separate systems. Revoking one leaves the
others intact. Subscription Owner confers no Graph administrative permission;
application permissions/admin consent and delegated Entra role requirements must
be checked for the exact directory operation.

Search control-plane and data-plane roles differ; server-side vectorization uses
the Search service's identity, not the caller. Cosmos data permission does not
come from ordinary account RBAC. Cross-group Bicep scope belongs on the module;
an `existing` resource name alone does not set it. Deterministic assignment names
provide repeatability, not ownership. Deleting a deployment record deletes no
resources; stacks' delete/detach and Terraform state have their own semantics.

## Retained Administrative Findings

All twenty-five original findings are retained below as native/operator checks.
Their old implementations are retired. None is newly verified against a tenant.

| Finding | Required interpretation / refusal |
| --- | --- |
| G1 Accepted assignment vanishes | Re-read exact state; governance rewrite is possible. Never re-grant blindly or claim persistence from HTTP success. |
| G2 Assignment exists but operation is 403 | Separate identity, authorization, network and service authentication mode before changing anything. |
| G3 PrincipalNotFound for an existing identity | Check object/client/resource ID confusion and replication; use native principal-type semantics. |
| G4 RBAC removal leaves data access | Verify every separately authorized permission plane; do not infer global revocation. |
| G5 Duplicate Cosmos assignment | Check exact existing assignment before create; duplicate detection is not permission to delete another owner's record. |
| G6 Effective access mistaken for least privilege | Inherited-only is not an exact declaration; report missing/excess grants explicitly. |
| G7 atScope includes inheritance | Compare returned exact scope, not merely a scoped listing's presence. |
| G8 Conditional grant mistaken for unconditional | Include ABAC condition and condition version in exact identity. |
| G9 Offline support matrix read as live promise | SDK serialization or a native command's existence proves no tenant/provider acceptance. |
| G10 Malformed/partial list read as empty | Parse structured pages, bound/follow valid continuations; malformed body or incomplete paging is unknown/failure. |
| G11 Request approves itself | Reject request-supplied authority; approval and allowlists belong to the trusted host/governance owner. |
| G12 Cleanup removes adopted grant | Adoption is not creation/ownership. Require exact authorized ID and unchanged declaration before removal. |
| G13 Propagation mistaken for failure | Bound observation by time/attempts; never create duplicates because state is not visible yet. |
| G14 Access probe leaks content | Use the least revealing authorized operation; retain status/evidence, never response payloads or credentials in diagnostics. |
| G15 Continuation/redirect exports token | Bind audience and origin, refuse foreign continuations/redirects before credential use; never blindly replay a token. |
| G16 Role suffix matches a broader word-role | Compare word roles exactly; GUID role IDs by their exact GUID segment. Viewer is not UnrestrictedViewer. |
| G17 Accepted long-running create loses target ID | Know the target before submission; retain it through bounded polling and unresolved outcomes. |
| G18 Scope normalization escapes allowlist | Refuse ambiguous URI/query/encoded traversal forms; compare resource path segments, not raw prefixes. |
| G19 CLI stderr invents HTTP status | Use structured status/error sources; unknown remains unknown. A resource name containing 500 is not HTTP 500. |
| G20 --confirm approves unreviewed changes | Require review of exact effects/targets, not blanket same-process confirmation. Misdirected approval must not consume valid authority. |
| G21 Copied folder mistaken for installed API | Install canonical packages; there is no installable azaccess replacement or skill source-path import. |
| G22 Removing group member deletes directory object | Delete membership `/$ref`, never the member object URL. Directory-object lifecycle is separate authority. |
| G23 Subscription Owner mistaken for Graph consent | Directory permissions/admin consent are independent of Azure RBAC; verify exact Graph audience and permission. |
| G24 201 body still Creating | Inspect terminal state and read target back; accepted is not completed. Retain target through malformed/unknown polling responses. |
| G25 Ledger erased before deletion confirmed | Preserve recovery/ownership evidence until exact-ID absence; a different assignment at the scope is neither your target nor deletion authority. |

Historical [SDK comparison](history/sdk-comparison.md),
[identity provenance](history/managed-identity-provenance.md) and
[identity failure notes](history/managed-identity-gotchas.md) remain evidence only.
Native API shapes, permissions, rollout/session behavior and cleanup need separately
authorized live verification. No commands from this guide were executed here.