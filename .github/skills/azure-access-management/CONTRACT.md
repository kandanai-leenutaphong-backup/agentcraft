# Contract

What this skill guarantees, precisely enough to reimplement it in another
language without reading the Python.

## MCP Adapter

The optional stdio adapter is narrower than the six-verb Python API. Installation grants no live
access, and no tool can request mutation or mint confirmation authority.

| Tool | Inputs | Result |
| --- | --- | --- |
| `azaccess_status` | empty object | configuration/grant status, fixture marker, path, `mutations_exposed: false` |
| `azaccess_matrix` | empty object | five-plane library support matrix with offline evidence disclaimer |
| `azaccess_role` | role `name` (1-200 characters) | public `RoleDefinition` fields |
| `azaccess_scope` | ARM `scope` (1-2048 characters) | parsed `Scope` fields; no authorization claim |
| `azaccess_inspect` | principal UUID, ARM scope | existing exact/inherited assignment result with partial/unknown completeness |

Operator JSON: `tenant_id`, `subscription_id`, `scopes` (at most 32, at least one for configured
inspection), `cloud` (`AzureCloud` default), `allow_live_reads` (false), and `timeout_secs`
(30; positive and at most 120 per CLI call). IDs must be UUIDs; allowed scopes must belong to
the configured subscription. Unknown fields, credential values and writable policies are refused.

For live inspection, the adapter first enforces the operator grant and scope bounds, then checks
Azure CLI's record of that subscription against the configured tenant. It does not log in, change
the active subscription, select another cloud, or alter RBAC. Configure the CLI identity/cloud
separately. The underlying read-only transport restricts hosts and continuation URLs; each request
retains its own timeout. This is not an aggregate listing-size or whole-session time budget.

Only the Azure RBAC provider is registered for MCP inspection. The matrix describes the wider
library, not live coverage of all five planes. Group/PIM/ABAC/deny semantics remain unevaluated,
so effective access is never reported complete. Unknown reads remain unknown, not absent.

The SDK validates arguments; adapter failures set `isError` without reflecting provider bodies or
credentials. `--fixtures` injects a recording transport for tests and marks results. The
[MCP smoke check](tests/mcp_smoke.py) proves successful fixture inspection and out-of-scope
refusal before any transport request. Apply, confirm, revoke and directory/resource mutations
remain the explicitly reviewed Python/CLI workflows below, not MCP tools.

## 1. Domain model

### 1.1 Identity coordinates

An identity is `(object_id, kind, tenant_id, display_name, client_id,
resource_id)`.

- `object_id` is the directory object id of the principal and the only
  coordinate that may be sent as `principalId`. For a managed identity it is the
  `principalId`, never the `clientId` and never the identity's ARM resource id.
- `kind` ∈ `user`, `group`, `service-principal`, `managed-identity`,
  `application`.
- `application` is rejected at construction: an application object is not
  assignable; its service principal in the target tenant is.
- A non-GUID `object_id`, `tenant_id` or `client_id` is refused before any
  request is built.
- `client_id == object_id` is refused; it is the commonest cause of
  `PrincipalNotFound`.
- ARM `principalType` is derived from `kind` (`User`, `Group`,
  `ServicePrincipal`) and is always sent explicitly.

`IdentityRef` implements this. `user_assigned_identity(...)` is the named
constructor for the three ids an ARM response hands back.

### 1.2 Scope

`Scope.parse(arm_id)` yields `(value, level, subscription_id, resource_group,
provider_namespace, resource_type, resource_name, management_group)` with
`level` ∈ `management-group`, `subscription`, `resource-group`, `resource`,
`child-resource`.

- Comparison is case-insensitive; storage is verbatim.
- `is_exact` is string equality after normalisation. `contains` is prefix
  containment on a segment boundary.
- `ancestors()` returns only ancestry derivable from the id text: child
  resources up to the top-level resource, then resource group, then
  subscription. **Management-group ancestry is never inferred**, which is one
  reason effective access cannot be closed.

### 1.3 Roles

A role is `(name, definition_id, plane, tier, service, note)`.

- `tier` ∈ `read`, `write`, `privileged`, `administrative`, ordered.
  `administrative` means it can change who else has access.
- `plane` ∈ `azure-rbac`, `cosmos-sql-rbac`, `kusto-database`,
  `sql-database-user`, `microsoft-graph`.
- `definition_id` is a public built-in GUID on the ARM plane, a fixed GUID on
  the Cosmos plane, a word (`Viewer`, `Ingestor`, `Admin`) on the Kusto plane,
  and a T-SQL permission (`SELECT`) on the SQL plane.
- `arm_definition_id(subscription_id)` is only valid on `azure-rbac`; other
  planes refuse it.
- Privileged roles are present on purpose. A catalogue that cannot express
  `Owner` cannot audit one. `register_role` adds custom roles, whose tier is
  stated by a human rather than inferred from a name.

`BUILTIN_ROLES`, `lookup_role`, `register_role`, `roles_at_or_above`,
`READER_ROLE_FOR_SERVICE` and `TIERS` implement this.

### 1.4 Declaration and fingerprint

An `AccessDeclaration` is `(principal, role, scope, target, condition,
condition_version, justification)`. `target` carries plane-specific coordinates
— Cosmos account, Kusto database, SQL schema and table, SQL user name, Graph
resource and app role id.

Construction validates the scope structurally (§1.5) and deep-copies `target`
into a read-only mapping. Every mapping on every value type here is frozen the
same way, so a caller keeping a reference to their own dict cannot change a
plan's identity after it was reviewed.

The **fingerprint** is `sha256(plane | role_definition_id | lowercased scope |
principal object id | condition | effective condition_version | sorted target)`
truncated to 32 hex characters. It excludes `justification` (which a caller may
vary without changing the effect) and includes `condition` **and its version**
(a v1.0 and a v2.0 expression are evaluated by different rules). It is the
target binding for confirmation tokens and the key of the ownership ledger.

`Plan.digest()` is the separate identity of a whole plan's *effects*: SHA-256
over every step's `to_dict()`, excluding the per-run `plan_id`.

### 1.5 Scope validation

A scope is **refused, not repaired**. `normalize_scope` drops trailing slashes
and nothing else; it rejects `?`, `#`, `&`, `%`, `\`, `@`, spaces, control
characters, empty segments (`//`), `.` and `..` segments, and any segment
outside `[A-Za-z0-9._()-]{1,260}`.

Each of those, quietly normalised, names a different target once a server has
parsed it: a resource name containing `?api-version=…` wins over the real
api-version in the built URL, and `…/rg-allowed/…/storageAccounts/../../../rg-secret`
passes a string-prefix allowlist and is then resolved by ARM into the scope the
allowlist existed to forbid.

Containment (`Scope.contains`, `AuthorityPolicy.scope_in_bounds`) is compared
**segment by segment** on validated ids, so `rg-app` does not contain
`rg-application`.

## 2. Authority

Authorisation is a host-constructed object, never a field in a request.

- `refuse_embedded_authority(payload)` raises `AuthorizationRefused` if the
  payload carries any of `approved`, `authorized`, `authorised`, `capability`,
  `elevate`, `bypass_policy`, `force`, `principal_type_override`,
  `confirmation_secret`.
- `AuthorityPolicy` gates, all independent of the requested target:
  1. `read_only` — refuses every `create` and `revoke` step;
  2. tenant allowlist — a principal with no `tenant_id` is refused, because the
     gate cannot be enforced;
  3. scope allowlist — segment-structural containment against scopes fixed at
     construction, applied to **reads as well as writes** unless
     `enforce_read_bounds=False` is set deliberately;
  4. plane allowlist, when non-empty;
  5. tier — a role above `max_tier` is refused unless its exact name is in
     `authorized_roles`;
  6. self-grant — refused when the target principal is in `self_principal_ids`
     and `allow_self_grant` is false.
- `with_authorized(...)` returns a **new** policy. Widening is visible at the
  call site that decided it and does not leak into later steps.
- `bounded_policy(...)` is the intended starting point: read-only, one tenant,
  explicit scopes.
- `describe()` reports counts and settings, never tenant or principal values.

`ConfirmationLedger.mint(plan_id, fingerprint)` returns an opaque token from a
CSPRNG. `consume(token, plan_id, fingerprint)` refuses when the token is
unknown, already used, expired, or bound to a different `(plan_id,
fingerprint)`; comparison is constant-time. **Validation precedes consumption**:
a refused presentation leaves a valid token valid, so one attempt against the
wrong target cannot destroy the approval for the right one. Tokens are minted by
the process, never derived from the request.

## 3. The six verbs

`AccessManager(providers, policy=..., ledger=..., clock=..., sleeper=...,
id_factory=..., ownership_ledger=...)`. Every adapter is checked against the
Provider protocol (`list_for`, `matches`, `create`, `delete`) at construction;
a missing method is a `TransportError` naming it, not an `AttributeError` from
inside `plan`.

| verb | reads | writes | returns |
| --- | --- | --- | --- |
| `inspect(principal_id, scope)` | yes | no | `EffectiveAccess` |
| `plan(declarations, action=)` | yes | no | `Plan` |
| `diff(declarations, include_excess_at=)` | yes | no | `DiffReport` |
| `confirm(plan, fingerprints=)` | no | no | `{fingerprint: token}` |
| `apply(plan, confirmations=, verify_budget_secs=)` | yes | yes | `ApplyReport` |
| `verify(declarations)` / `verify_one(...)` | yes | no | `VerificationResult` |
| `revoke(declarations, authorized_ids=, budget_secs=)` | yes | yes | `RevokeReport` |
| `adopt_from_ledger(ledger)` | no | no | `tuple[OwnershipRecord, ...]` |

**Every read is bounded by the same allowlist as every write.** `inspect`,
`plan`, `diff`, `verify` and the excess scan call `policy.authorize_read(scope)`
before a request is built. Widening is the explicit policy field
`enforce_read_bounds=False`, which `describe()` reports.

### 3.1 inspect

Returns exact assignments, inherited assignments, and `completeness`.
`completeness` is `partial` on success and `unknown` when the read failed. It is
**never** `complete`: `UNEVALUATED_SEMANTICS` lists
`pim-eligible-assignments`, `deny-assignments`, `transitive-group-membership`,
`abac-role-assignment-conditions`, `management-group-ancestry` and
`entra-directory-roles`, and is returned with every answer.

### 3.2 plan

One step per declaration, ordered broad scope first.

- exact match present → `noop`, carrying the existing id;
- nothing present, access inherited from an ancestor → `create`, with a reason
  naming the ancestor;
- nothing present → `create`;
- `action="revoke"` → `revoke` when an exact match exists, else `noop`.

Steps needing a mutation are checked against the policy at plan time, and a
refusal becomes an entry in `plan.refusals` rather than an exception, so one
read-only pass shows the whole picture. `requires_confirmation` is true when the
role's tier is at or above `policy.confirmation_tier`.

### 3.3 diff

Four disjoint outcomes: `satisfied` (exact match), `inherited_only` (present via
an ancestor — **not** satisfied), `missing`, and `excess` (present at a named
scope and undeclared; reported, never deleted). `completeness` is `exact` when
only exact assignments were compared.

### 3.4 apply

For each `create` step, in order: policy check → confirmation token consumed
(if required) → provider create → read-back. A refusal or a provider error
appends to `refusals` and moves on; it never aborts the remaining steps
silently.

A provider that raises `OperationPending` — an accepted long-running create
whose outcome could not be resolved — contributes an `OwnershipRecord` with
`source="pending"` to `ApplyReport.pending`, carrying the **target id this run
PUT**, plus a refusal whose `pending_target_id` repeats it. It is never recorded
as created and never dropped.

`ApplyReport.ok` is true only when there are no refusals, nothing is pending,
nothing is in `ledger_failures`, and every verification is `present`.

An `OwnershipLedger` write that fails **after** the cloud create has succeeded
is not raised. The grant exists by then, so an exception would discard the only
coordinate that could clean it up. The id, plane, scope, role and source are
reported in `ApplyReport.ledger_failures` with `category="ledger"`, the record
stays in memory with `source="created"` so `revoke` still applies to it, and the
report is not `ok`.

`confirm(plan, fingerprints=)` mints one single-use token per named fingerprint.
A fingerprint the plan does not contain as a step needing confirmation is
refused. Omitting `fingerprints` approves every such step and is only
appropriate where the caller has already reviewed `plan.digest()`.

`plan.digest()` is a SHA-256 over the steps' effects, excluding the per-run
`plan_id`, so the same declared state against the same observed state yields the
same digest and a reviewed plan is checkable. The CLI's `apply` refuses unless
`--expect-digest` equals it and `--confirm-target` names exactly the set in
`plan.to_dict()["confirmation_required"]`.

`ConfirmationLedger.consume` validates plan id, fingerprint and expiry **before**
burning the token. A presentation against the wrong target is refused and leaves
the token valid for the target it was minted for.

### 3.5 verify

Polls `matches` at exact scope until the expectation is met or the budget is
spent. Results:

| status | meaning |
| --- | --- |
| `present` | exact match found |
| `absent` | no exact match, and no write claimed success |
| `revert-suspected` | a write reported success and the read-back disagrees after the budget |
| `unknown` | the read itself failed |

`waited_secs` is always reported. The wait is always bounded. `duplicates`
carries any extra ids beyond the first exact match.

### 3.6 revoke

For each declaration: policy check → read exact matches → for each match, delete
only if **all** of these hold, else append a refusal with category `ownership`
and leave it:

1. the match still satisfies the declaration exactly (the plane's own identity
   rule, via `provider.identity_matches` where it defines one);
2. either the id is in `authorized_ids`, or this run holds an `OwnershipRecord`
   for that fingerprint whose `source` is `created`;
3. the id currently readable equals the recorded id.

`source="adopted"`, `"pending"` and `"ledger-unverified"` are **not** revocable.
Adoption records that an assignment already existed so a plan can say `noop`; it
is not a licence to delete another writer's grant. Then verify absence.

**A record is dropped only once the exact id is proved gone.** After a delete
returns, `matches` is polled to the same budget and the check is whether *that
assignment id* is still readable — not whether the declaration still matches
anything. Three outcomes keep the ownership record and its ledger file, and
report them in `RevokeReport.retained` with the reason:

| reason | what happened |
| --- | --- |
| `delete-pending` | the DELETE was accepted (`202`) and has not finished |
| `target-present` | the DELETE succeeded and the id is still readable |
| `target-unknown` | the DELETE succeeded and the read-back failed |
| `ledger-write` | the target is gone and its ledger file could not be removed |

A later `revoke` that reads the scope and does not find the recorded id clears
the record then, on the strength of that read.

A second writer's assignment at the same scope — same role, same principal,
different id — never blocks completion: it is refused with category `ownership`,
left in place, and reported. Waiting for it would hang the teardown, and
deleting it is the defect this whole section exists to prevent.

`RevokeReport.ok` is true only when nothing was retained and every verification
is `absent`.

### 3.7 ownership ledger (optional)

`OwnershipLedger(directory)` writes one content-addressed JSON file per record,
atomically, as each is created, and removes it on a successful delete. It exists
so a process that dies between `create` and `revoke` still leaves recoverable
ids. `read_all()` returns every record with `source="ledger-unverified"`, and
`cleanup_report()` adds a manual cleanup command per record.

A ledger is **evidence, never authority**. Absence from it does not mean an
assignment did not exist; presence does not mean this run created it; and
`revoke` refuses a rehydrated record exactly as it refuses an adopted one. A
file any writer can append to must not be able to direct a deletion. No
credential material is written: the fields are the same ones `to_dict()` prints.

## 4. Plane adapters

Each adapter provides `plane`, `operations`, `list_for`, `matches`, `create`
and `delete`, and may provide `identity_matches(state, declaration)` when its
role identity is not the catalogue definition id. `create` returns an
`OwnershipRecord` whose `assignment_id` is copied from the id the **service
returned**, or from a read-back of the exact target this run PUT under a
freshly minted random name. Ownership is never inferred from a deterministic
name, a description, or a listing difference; a create response with no id and
no readable target is `OperationPending`, not a success.

**Role identity is compared per plane.** GUID-keyed planes (`azure-rbac`,
`cosmos-sql-rbac`) compare the last path segment exactly and require it to be a
GUID. Word-keyed planes (`kusto-database`, `sql-database-user`,
`microsoft-graph`) compare the whole string exactly, case-insensitively. A
suffix comparison is forbidden: `UnrestrictedViewer` ends with `Viewer` and is a
strictly wider grant, and `AllDatabasesAdmin` ends with `Admin`. An ABAC
`conditionVersion` is part of identity too.

### 4.1 azure-rbac — `ArmRbacProvider`

- API version `2022-04-01`. List URL uses `$filter=atScope()`, which includes
  inherited assignments, so every match re-compares `properties.scope`.
- Create is `PUT .../roleAssignments/{new-guid}` with `roleDefinitionId`
  (subscription-qualified), `principalId`, `principalType`, and — when the
  declaration has one — `condition` plus `conditionVersion` (default `2.0`).
- `409` is adoption: the existing assignment is read back and recorded with
  `source="adopted"`. If nothing exact is readable, that is a `ProviderConflict`,
  not a success.
- `delete` accepts `204` and `404`; absence is the desired end state.
- `list_deny_assignments` is read-only. Deny assignments are created only by
  Blueprints and Managed Applications, so creating one is `unsupported`.
- ABAC conditions are built by `azaccess.conditions` and validated before they
  are sent; see §8.1. This package **serialises and compares** a condition. It
  never evaluates one, and `abac-role-assignment-conditions` is named in
  `UNEVALUATED_SEMANTICS` for exactly that reason.

### 4.2 cosmos-sql-rbac — `CosmosSqlRbacProvider`

- API version `2024-11-15`. Assignments hang off the account
  (`.../sqlRoleAssignments`), not off `Microsoft.Authorization`.
- Scope is a data-plane path: `<accountId>/dbs/<db>/colls/<container>`. The
  account id is recovered from the prefix.
- Create is **not idempotent** and there is no `409`, so the adapter reads
  first and adopts. `duplicates()` reports extra matches; they are never deleted
  automatically.
- Create is **long-running**: `201` completes inline, `202 Accepted` carries
  `Azure-AsyncOperation` (or `Location`) and no body. The adapter mints the
  assignment name first, so the target id is known before the PUT, then resolves
  the outcome: poll to `Succeeded` and read the target back, raise on
  `Failed`/`Canceled`, and raise `OperationPending` carrying the target id if it
  runs out of polls, spends its wall-clock budget, loses the poll URL, or the
  poll points off-origin. An empty `200`/`201` body is resolved by the same
  read-back — and so is a `201` whose body reports a non-terminal
  `provisioningState` such as `Creating`, which is an accepted create, not a
  finished one. A read-back that is itself non-terminal is `OperationPending`.
  Waiting is bounded twice, by `MAX_LRO_POLLS` (30) and `MAX_LRO_WAIT_SECS`
  (120s), paced by the server's `Retry-After` clamped to
  `[MIN_RETRY_AFTER_SECS, MAX_RETRY_AFTER_SECS]` (1s–30s); `sleeper` and `clock`
  are injectable, so tests take no wall-clock time. A poll response whose body is
  not a JSON object is `OperationPending` carrying the target id, never a bare
  transport error — losing the id there is how an orphan is made.
- `delete` refuses any id that is not a `sqlRoleAssignments` id.

### 4.3 kusto-database — `KustoDatabaseProvider`

- API version `2023-08-15`. Assignments hang off the database; a cluster-scope
  id is refused.
- Body carries `principalId`, `role` (a word), `principalType` in Kusto's own
  vocabulary (`App`, `User`, `Group`) and `tenantId`.
- Create is long-running on the same contract as Cosmos §4.2, resolved by the
  same protocol.
- Cluster-scoped assignment is `documented`, not implemented.

### 4.4 sql-database-user — `SqlDatabaseUserProvider`

- Not an Azure resource. Statements are built here; execution is delegated to a
  host-supplied `SqlExecutor` (`execute`, `query`). With no executor the adapter
  refuses rather than tunnelling T-SQL through HTTP.
- `sql_grant_statements(declaration)` returns
  `IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'<name>')
  CREATE USER [name] FROM EXTERNAL PROVIDER;` then
  `GRANT <permission> ON [schema].[table] TO [name];`. Permission ∈ `SELECT`,
  `INSERT`, `UPDATE`, `DELETE`. The guard is what makes a second `apply`
  idempotent instead of error 15023.
- Identifiers and literals are quoted by **separate** functions. Object names
  (`quote_identifier`) must match `[A-Za-z0-9_. -]{1,128}`. Principal names
  (`quote_principal_identifier`) additionally allow `@`, because
  `CREATE USER [app@contoso.onmicrosoft.com] FROM EXTERNAL PROVIDER` is the
  standard form for a user or a UPN-named service principal — and a managed
  identity or application is named by display name with no `@` at all, so
  neither form is assumed. Literals (`quote_literal`) are emitted as `N'…'` with
  `'` doubled. DDL cannot be parameterised, so refusal is the boundary.
- The read-back query is bound to the declared object: it filters
  `class_desc = 'OBJECT_OR_COLUMN'`, `major_id = OBJECT_ID(@object)`,
  `minor_id = 0` and `state_desc = 'GRANT'`, and `matches` re-checks each of
  those on the returned row. A permission held at database scope, on another
  object, on a column, or in `DENY` state is not a match. A user that exists
  **without** the permission is not a match either.
- `create` adopts when the permission is already held — this run did not make it
  and may not later drop the user for it.
- `delete` refuses any user name outside the configured `owned_prefix`.

### 4.5 microsoft-graph — `GraphAppRoleProvider`

- Implements the Provider protocol, so the plane is reachable through the same
  six verbs. A declaration is addressed by `scope =
  /servicePrincipals/<sp-object-id>`, `target['resource_id']` (the API's service
  principal) and `target['app_role_id']` (the permission). Role identity is the
  `appRoleId`, compared through `identity_matches`.
- Requires a Graph-audience transport. The transport's declared `audience` is
  checked **at construction**, before any request: an ARM token is rejected by
  Graph with a 401 that reads like a missing permission, so the mismatch is
  refused locally instead. `require_audience=False` opts out deliberately.
- The keyword interface (`create_assignment`, `delete_assignment`,
  `list_assignments`) remains, unchanged in meaning.
- `build_assignment_body` validates three distinct GUIDs: `principalId` (the
  service principal being granted), `resourceId` (the API's service principal in
  the tenant), `appRoleId` (the permission).
- `federated_credential_request(...)` builds a `federatedIdentityCredentials`
  body: `name`, `issuer` (https only), `subject` (the exact `sub` claim),
  `audiences` (default `api://AzureADTokenExchange`), `description`. Nothing in
  it is a credential.
- `group_member_add_request(...)` and `group_member_remove_request(...)` build
  the membership calls and do **not** send them (`delegated`); see §8.2.
  `refuse_membership_url_without_ref` refuses a membership `DELETE` whose URL
  does not end in `/$ref`.
- Admin consent, delegated scope grants and directory-role assignment are
  `documented`, not coded. So are PIM for Groups eligibility and transitive
  membership reads. Creating a group, creating an application and deleting a
  directory object are `unsupported`: this is access management, not object
  lifecycle.

## 5. Transport

`Transport` is `request(method, url, json_body=None) -> Response(status, body,
headers, status_exact)`. It never accepts a command line, a shell string or a
callable from a plan.

Every live transport is bound at construction to one `CloudEndpoints` —
`AZURE_PUBLIC_CLOUD`, `AZURE_US_GOVERNMENT`, `AZURE_CHINA_CLOUD`, or one the
caller builds — and to one token audience. **The URL is validated against that
allowlist before the credential is asked for anything**, on every send. A URL
that is not https, carries userinfo or a fragment, contains control characters,
or names a host outside the configured cloud is refused with no token minted and
no request made.

- `RecordingTransport` — offline. Scripted by `(method, url-fragment)`; a queue
  of several responses is consumed in order, a single response repeats. An
  unscripted call raises rather than returning an empty success. It records every
  `(method, url, body)`, so tests assert the requests that were built. It also
  declares an `audience`, so audience-bound refusals are testable.
- `AzureCliTransport` — shells out to `az rest` with `shell=False`, through an
  injectable `runner`. **`GET` and `HEAD` only.** `az rest` reports no status
  line and no headers, so a success is returned as `200` with
  `status_exact=False` and a mutation is refused outright: `201`, `202` and the
  `409` that means "already exists" would be indistinguishable, and `ArmRbacProvider.create`
  refuses any response with `status_exact=False` for the same reason. A failure's
  status comes from a structured source only — an explicit `HTTP <nnn>` or
  `status code: <nnn>`, or a recognised ARM error `code` — and is
  `UNKNOWN_STATUS` (`0`) otherwise. A three-digit run inside a resource name
  (`rg-409`, `kv-404-prod`) is never a status.
- `TokenCredentialTransport` — any object with `get_token(audience)`, over
  `urllib`, through an injectable `opener`. A 4xx/5xx is data, not an exception;
  a 3xx redirect is refused rather than followed, because urllib would re-send
  the `Authorization` header to the new location. No key fallback exists.
- `sanitize_detail` strips bearer tokens, JWT-shaped strings and key/password
  assignments from anything that reaches an error or a log.

Paging (`page_values`) follows `nextLink`/`@odata.nextLink` **only to the origin
that served the first page**, caps at `MAX_PAGES = 50` and `MAX_ITEMS = 20000`,
refuses a self-referential link, and treats a missing or non-list `value` as a
transport failure — never as "no assignments".

## 6. Access probe

`AccessProbe.probe(action=, url=, scope=, method="GET")` is the only code path
that touches a data plane. It requires a non-empty `action`, allows only `GET`
and `HEAD`, and requires `scope` to be inside the policy allowlist. It returns
`ProbeResult(action, url-without-query, status, allowed, category)` where
`category` separates `authentication` (401), `authorization` (403),
`not-found-or-hidden` (404), `service` and `allowed`. The response body is never
read into the result, logged or stored.

## 7. Support matrix

`support_matrix()` reads `operations` off the adapter classes. Statuses:

| status | claim |
| --- | --- |
| `implemented` | a code path builds the request and parses the response, exercised offline against a recorded transport |
| `delegated` | the request or statement is built and validated here; execution is host-supplied |
| `documented` | no code path; a written procedure below |
| `unsupported` | refused in code, on purpose |

`MatrixRow` carries the evidence line for its status. **No status means
"verified against Azure"**; `LIVE_VERIFICATION` states this and the tests assert
that no row claims otherwise. `render_matrix` regenerates the table so
documentation is derived rather than maintained.

## 8. Documented procedures (no code path)

These are real operations with no adapter. They are here so an operator is not
left guessing.

**Prerequisites, before any of the Microsoft Entra procedures below.** Azure RBAC
and Microsoft Entra are two authorization systems and one does not buy the other.
An identity that is **Owner of the subscription holds nothing in the directory**:
no group management, no consent, no directory-role assignment. Directory writes
need Microsoft Graph permissions on the calling app (application permissions,
admin-consented) *and*, in delegated flows, a supported Entra role on the
signed-in user. Both, not either. Every Graph call also needs a Graph-audience
token; an ARM token is rejected with a `401` that reads exactly like a missing
permission (§4.5 refuses that locally).

### 8.1 ABAC conditions on a role assignment

A condition narrows the assignment it is attached to. It can never grant an
action the role does not carry, and a request the condition does not permit is
simply not allowed *by that assignment*. Conditions are supported on assignments
carrying Azure Blob or Queue Storage data actions — `Storage Blob Data Reader`,
`Storage Blob Data Contributor`, `Storage Blob Data Owner`, and the queue
equivalents.

The form is one targeted action and one expression:

```
(
    (
        !(ActionMatches{'<action>'})
    )
    OR
    (
        <attribute> <operator> <value>
    )
)
```

Read it as: if the request is *not* the targeted action, the condition says
nothing and the assignment applies unchanged; if it *is*, the expression must be
true. Attribute sources are `@Request`, `@Resource`, `@Principal` and
`@Environment`.

Worked case — `Storage Blob Data Reader` at the storage-account scope, narrowed
so that reading a blob is only permitted inside one container:

```
(
 (
  !(ActionMatches{'Microsoft.Storage/storageAccounts/blobServices/containers/blobs/read'})
 )
 OR
 (
  @Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name] StringEquals 'blobs-example-container'
 )
)
```

`container_name_condition("blobs-example-container")` returns exactly that
string. It goes onto the assignment as:

```json
{"properties": {
  "roleDefinitionId": "/subscriptions/<sub>/providers/Microsoft.Authorization/roleDefinitions/2a2b9908-6ea1-4ae2-8e65-a410df84e7d1",
  "principalId": "<object-id>",
  "principalType": "ServicePrincipal",
  "condition": "<the expression above>",
  "conditionVersion": "2.0"}}
```

`conditionVersion` is `"2.0"`. Version 1.0 exists and is evaluated by different
rules, so `require_condition` refuses to relabel one as the other, and the
version is part of `AccessDeclaration.fingerprint()` — a token minted for a
v2.0 target cannot confirm a v1.0 one.

`blob_tag_condition("Project", "Cascade")` builds the blob-index-tag form, whose
attribute name carries the documented key delimiter:
`@Request[Microsoft.Storage/storageAccounts/blobServices/containers/blobs/tags:Project<$key_case_sensitive$>]`.

Refused by the builders, because each looks narrowing and is not:

- a wildcard in a `StringEquals` value (`'prod*'` matches a container literally
  named `prod*`, so the rule never fires and reads as if it does — use an
  explicit `StringLike` expression and say so);
- a wildcard action, which changes *which* requests the expression gates and is
  easy to get backwards;
- a `conditionVersion` with no condition;
- an expression with no `ActionMatches` gate, which applies to every action in
  the role;
- unbalanced parentheses or quotes, which ARM rejects with a character offset
  and nothing else;
- a quote or newline inside a literal.

**Serialising is not evaluating.** This package puts the condition on the
assignment and compares conditions textually when deciding whether an observed
assignment is the declared one. It cannot tell you whether a given request would
be allowed: that is decided by the service handling the data-plane call, using
request, resource, principal and environment attributes this process never sees.
`UNEVALUATED_SEMANTICS` says so in every effective-access answer.

Reference: <https://learn.microsoft.com/azure/role-based-access-control/conditions-format>

### 8.2 Group-based grants and membership lifecycle

The least-privilege pattern: assign the role once to a **group**, then manage
principals by membership. The assignment stops churning and "who has this
access" becomes a directory question.

The grant itself is ordinary — `IdentityRef(kind="group")` serialises
`principalType: "Group"` and every plane treats it as a principal. The
membership calls are Microsoft Graph, are built here and **sent by the host**:

| step | call | success |
| --- | --- | --- |
| add a member | `POST /v1.0/groups/{group-id}/members/$ref` with `{"@odata.id": "https://graph.microsoft.com/v1.0/directoryObjects/{id}"}` | `204 No Content` |
| remove a member | `DELETE /v1.0/groups/{group-id}/members/{directory-object-id}/$ref` | `204 No Content` |
| read members | `GET /v1.0/groups/{group-id}/members` | `200` |
| read nested members | `GET /v1.0/groups/{group-id}/transitiveMembers` | `200` |

**The `/$ref` suffix is the safety property, not a formatting detail.** Graph's
own reference carries the caution: if `/$ref` is not appended and the calling app
may manage the member's object type, *the member object is deleted from Microsoft
Entra ID* — an app holding `GroupMember.ReadWrite.All` and `User.ReadWrite.All`
deletes the user. One missing suffix turns "remove from group" into "delete the
identity". `group_member_remove_request` always appends it and
`refuse_membership_url_without_ref` refuses the unsuffixed form.

Other behaviours worth knowing before wiring this up:

- ids are **directory object ids**, and `/directoryObjects/{id}` is the reference
  form that works for a user, a security group, a device or a service principal
  alike — the caller does not have to know which kind it holds. A client id is
  not an object id (§1.1 refuses the confusion);
- adding a principal that is already a member answers `400`, not `409` and not a
  silent success. Treat "already a member" as an expected outcome;
- a recently created group replicates asynchronously; an add against one can
  answer `400` with "The source resource object … don't exist". Retry after a
  brief delay;
- a member of a **dynamic** group cannot be removed this way at all — membership
  is computed from a rule;
- Microsoft 365 groups take users only; security groups also take security
  groups, devices, service principals and org contacts.

**Permissions.** Least privilege for both calls is `GroupMember.ReadWrite.All`
(application, or delegated). Adding a service principal additionally needs
`Application.ReadWrite.All`; a device needs `Device.ReadWrite.All`. In delegated
flows the signed-in user must also hold a supporting Entra role — Group owner,
Groups Administrator, User Administrator, Directory Writers or Identity
Governance Administrator. A **role-assignable** group is stricter again: the app
needs `RoleManagement.ReadWrite.Directory` and the user needs Privileged Role
Administrator. None of this is implied by any Azure RBAC role.

**Transitivity, and what an answer here may claim.** Azure RBAC honours nested
group membership when it evaluates access; this package does not resolve it.
`transitive-group-membership` is listed in `UNEVALUATED_SEMANTICS`, so
`inspect` reports assignments *to the principal*, never access the principal has
*through a group*. To answer the group question, read
`GET /v1.0/groups/{id}/transitiveMembers`, or ask the directory directly with
`POST /v1.0/directoryObjects/{id}/getMemberGroups`. Treating this package's
answer as complete for a group-granted identity is the mistake the field exists
to prevent.

**PIM for Groups.** Membership (and ownership) of a group can itself be made
*eligible* rather than permanent, so a principal holds nothing until it
activates. Two request collections under
`/v1.0/identityGovernance/privilegedAccess/group`:

- `eligibilityScheduleRequests` — an administrator makes a principal eligible
  (`accessId: "member"`, the group id, `action: "adminAssign"`, a schedule);
- `assignmentScheduleRequests` — the principal activates
  (`action: "selfActivate"`, a justification, a bounded duration), which is what
  actually confers membership.

Eligibility is not access. An effective-access answer that ignores it understates
what the principal can obtain in a minute, and one that counts it as access
overstates what the principal has now; this package reports neither and names
`pim-eligible-assignments` as unevaluated.

References: <https://learn.microsoft.com/graph/api/group-post-members>,
<https://learn.microsoft.com/graph/api/group-delete-members>,
<https://learn.microsoft.com/entra/id-governance/privileged-identity-management/groups-features>

### 8.3 Directory and subscription procedures

**PIM eligible assignment.** `Microsoft.Authorization/roleEligibilitySchedule
Requests` at the target scope, with `requestType: AdminAssign`, a schedule
(`expiration.type`, `duration`), and a justification. Activation is a separate
`roleAssignmentScheduleRequests` call by the eligible principal. Eligibility is
not access: an eligible principal has none until activation, and an
effective-access answer that ignores eligibility understates future access.

**Custom role definition.** `PUT .../providers/Microsoft.Authorization/
roleDefinitions/{guid}` with `roleName`, `permissions[].actions`,
`notActions`, `dataActions`, `notDataActions`, and `assignableScopes`. Register
it with `register_role` so its tier is explicit before anything assigns it.

**Directory role assignment (Entra).** `POST /roleManagement/directory/
roleAssignments` on Graph with `principalId`, `roleDefinitionId` and
`directoryScopeId` (`/` for tenant-wide). Administrative tier by definition;
deliberately not automated here.

**Admin consent / delegated scopes.** `oauth2PermissionGrants` for delegated
scopes; application permissions need an app role assignment plus tenant admin
consent. Consent is a human decision and is not automated here.

**SQL server Entra admin.** Set on the *server*
(`Microsoft.Sql/servers/administrators`), and required before
`CREATE USER ... FROM EXTERNAL PROVIDER` works at all. A workload identity does
not hold it.

**Kusto cluster-scoped assignment.** `.../clusters/{name}/principalAssignments`,
same body shape as the database plane. Wider than database scope; prefer the
database.

**Cosmos custom SQL role definition.** `.../sqlRoleDefinitions/{guid}` with
`permissions[].dataActions` and `assignableScopes`. The two built-ins cover
read and write.

## 9. Public surface

Everything exported from `azaccess`:

| name | what it is |
| --- | --- |
| `AccessManager` | the entry point: the six verbs |
| `AccessDeclaration` | one desired grant |
| `AccessProbe`, `ProbeResult` | the narrow read-only reachability check |
| `AccessError` | base error; `.category` names the plane of failure |
| `AuthenticationError`, `AuthorizationRefused`, `CoordinateError`, `OperationPending`, `ProviderConflict`, `TransportError`, `PolicyRevertSuspected` | the error taxonomy |
| `AuthorityPolicy`, `bounded_policy`, `refuse_embedded_authority` | local authority |
| `ConfirmationLedger` | single-use, target-bound confirmation tokens |
| `OwnershipLedger` | durable, content-addressed record of what a run created; evidence, never authority |
| `CloudEndpoints`, `AZURE_PUBLIC_CLOUD`, `AZURE_US_GOVERNMENT`, `AZURE_CHINA_CLOUD`, `cloud_by_name` | which hosts and audiences a transport may use |
| `IdentityRef`, `user_assigned_identity` | typed identity coordinates |
| `Scope`, `normalize_scope` | ARM scope parsing, validation, exactness and containment |
| `RoleDefinition`, `BUILTIN_ROLES`, `lookup_role`, `register_role`, `role_identity_matches`, `TIERS`, `READER_ROLE_FOR_SERVICE` | the role catalogue and per-plane role identity |
| `Plan`, `PlanStep`, `Planner` | planning |
| `AssignmentState`, `EffectiveAccess`, `DiffReport`, `Completeness`, `UNEVALUATED_SEMANTICS` | observed state and honest completeness |
| `OwnershipRecord`, `ApplyReport`, `RevokeReport`, `VerificationResult` | results |
| `declarations_from_records` | declarations from plain dicts or a config file |
| `ArmRbacProvider`, `CosmosSqlRbacProvider`, `KustoDatabaseProvider`, `SqlDatabaseUserProvider`, `GraphAppRoleProvider` | the plane adapters |
| `sql_grant_statements`, `quote_identifier`, `quote_principal_identifier`, `quote_literal`, `RecordingSqlExecutor` | the SQL seam |
| `federated_credential_request` | secretless workload identity federation |
| `container_name_condition`, `blob_tag_condition`, `require_condition`, `CONDITION_VERSION`, `SUPPORTED_CONDITION_VERSIONS` | ABAC conditions: built and validated here, evaluated by Azure (§8.1) |
| `group_member_add_request`, `group_member_remove_request`, `refuse_membership_url_without_ref` | group membership calls, built and validated here, sent by the host (§8.2) |
| `Response`, `RecordingTransport`, `AzureCliTransport`, `TokenCredentialTransport`, `sanitize_detail`, `status_from_cli_error`, `UNKNOWN_STATUS` | transport |
| `support_matrix`, `render_matrix`, `MatrixRow` | the matrix, derived from code |

## 10. Invariants a reimplementation must keep

1. No credential value is read, written, logged or returned. Ever.
2. Authorisation never comes from the request being authorised.
3. Every mutation is read back at exact scope before it is called success.
4. Inherited access never satisfies an exact declaration.
5. Ownership comes from the service's create response, or from a read-back of
   the exact target this run wrote. Only ids this run **created**, or ids the
   caller explicitly authorised, are deleted; adopted, pending and rehydrated
   records are refused. A record is discarded only when that **exact id** is
   proved absent — never because a delete was accepted, and never because some
   other assignment at the scope disappeared.
6. Effective access is never reported as complete, and what was not evaluated is
   named.
7. Waiting is bounded; `unknown` is a distinct answer from `absent`; and an
   accepted-but-unresolved mutation is `pending`, carrying its target id, rather
   than either of them.
8. A malformed or partial response is a failure, not an empty result.
9. The support matrix is derived from code and claims no live verification.
10. No plane's semantics are simulated by another plane's protocol, and role
    identity is compared by that plane's rule — never by suffix.
11. A URL is authorised against configuration before a credential is obtained,
    on every send, including continuations and redirects. Nothing in a response
    body may widen where a token goes.
12. An HTTP status is read, never inferred from surrounding text; a backend that
    cannot report one says so, and a mutation is refused rather than guessed.
13. Every scope is validated structurally and refused if unsafe; it is never
    rewritten into a different target to make it parse.
14. Reports, plans and declarations are deep-frozen: what was reviewed is what
    runs.
15. A failure to persist an ownership record after a successful cloud write is
    an outcome carrying the created id, never an exception that discards it.
