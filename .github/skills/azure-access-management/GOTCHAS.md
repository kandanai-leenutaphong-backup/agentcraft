# Gotchas

Every entry is a symptom first, because that is how you arrive: something is
wrong, and the cause has a different name than the thing you observed. Cited
from the code as `GOTCHAS.md, Gn`.

## G1 — The role assignment "succeeded" and it is not there

**Symptom.** A create answered `201 Created`, `provisioningState` says
`Succeeded`, and the read-back at exact scope finds nothing. Repeating the
create produces the same `201` and the same absence.

**Cause.** An Azure Policy `Modify` or `DeployIfNotExists` effect at a
management-group scope reverted the write after ARM accepted it. HTTP 200 means
"ARM accepted this", never "this persisted".

**What this skill does.** `verify_one` polls to a bounded budget and, when a
write reported success and the read-back disagrees, returns status
`revert-suspected` with the elapsed time and policy named as a candidate — not
`absent`, because the two need different next actions.

**What to do.** Look at policy assignments and exemptions at the management
group, not at your own permissions. Re-granting harder will not help.

## G2 — Everything looks granted, and the app still gets 403

**Symptom.** The assignment is present at exact scope, the identity is right,
and the data-plane call is refused.

**Cause.** Four independent things produce a 403 and they are routinely
conflated: authentication (no or wrong token), authorisation (no assignment),
network (a firewall or private endpoint refused the request before authorisation
was evaluated), and service auth mode (an Azure AI Search service in
`apiKeyOnly` mode rejects every Entra token regardless of RBAC).

**What this skill does.** `AccessError.category` separates `authentication`,
`authorization`, `transport` and `policy`, and `AccessProbe` reports 401 as
`authentication` and 403 as `authorization` rather than collapsing them.

**What to do.** Prove which one before changing anything. RBAC is not the lever
for a service auth-mode or firewall problem.

## G3 — PrincipalNotFound on a principal that plainly exists

**Symptom.** A role assignment create fails with `PrincipalNotFound`, and the
portal shows the identity right there.

**Cause.** Usually one of three coordinate mistakes: the application (client)
id was sent where the service principal **object** id was required; the ARM
resource id of a user-assigned managed identity was sent instead of its
`principalId`; or the principal was created seconds ago and the directory
replication ARM does has not caught up — which `principalType` being omitted
turns from a retry into a hard failure.

**What this skill does.** `IdentityRef` refuses a non-GUID, refuses an
`application` kind as unassignable, refuses a `client_id` equal to the
`object_id`, and always sends `principalType` explicitly.

## G4 — Revoking Azure RBAC left the data access in place

**Symptom.** Every role assignment is gone, `az role assignment list` is empty
for the principal, and it still reads Cosmos DB documents, queries a Data
Explorer database, or selects from a SQL table.

**Cause.** Those grants are not Azure RBAC. A Cosmos SQL role assignment is a
child of the account; a Data Explorer principal assignment is a child of the
database; a SQL database user is not an Azure resource at all. None appears in
an ARM assignment list and none is removed by an ARM delete.

**What this skill does.** Every role carries its plane, teardown walks each
plane separately, and the support matrix states which plane each operation is
on.

## G5 — The second run created a duplicate Cosmos assignment

**Symptom.** Two identical Cosmos SQL role assignments for the same principal,
scope and role. Deleting one leaves access intact and looks like a failed
revoke.

**Cause.** Cosmos SQL role assignment creates are not idempotent and there is
no `409`. A fresh GUID name mints a second assignment.

**What this skill does.** `CosmosSqlRbacProvider.create` reads before it
writes and adopts an existing match. `duplicates()` reports extras and never
deletes them: on a shared account the extra may be another team's.

## G6 — "It can already read the container", so the migration was a no-op

**Symptom.** A least-privilege migration reports the desired state satisfied,
and the subscription-wide Contributor assignment is still there.

**Cause.** Effective access was compared instead of exact assignments. The
identity *can* read the container — through an assignment somewhere above it.

**What this skill does.** `diff` reports `satisfied`, `inherited_only` and
`missing` as three separate outcomes, and `inherited_only` is not satisfied. The
plan step says which ancestor the access is coming from.

## G7 — The read-back passed against an assignment nobody made

**Symptom.** Verification is green, but the assignment at the intended scope
does not exist.

**Cause.** ARM's `$filter=atScope()` **includes inherited** assignments. Code
that lists at a scope and checks for a match will match the inherited one.

**What this skill does.** Every match re-compares `properties.scope`
textually. An inherited assignment can never satisfy an exact check.

## G8 — Conditional and unconditional assignments were treated as one

**Symptom.** An ABAC-conditioned assignment satisfied a check for the
unconditional grant, or a teardown deleted a narrow conditional assignment
believing it was the broad one.

**Cause.** Role, principal and scope are equal; the condition is what differs,
and it was not compared.

**What this skill does.** The condition is part of the declaration
fingerprint and part of exact matching.

## G9 — The support matrix was read as a promise about Azure

**Symptom.** "It says `implemented`, so it works against our tenant."

**Cause.** `implemented` means a code path builds the request and parses the
response, exercised against a recorded transport. It is evidence about
serialisation, not about a service accepting anything.

**What this skill does.** Every matrix row carries its evidence line, and
`LIVE_VERIFICATION` states plainly that no row has been verified against a live
tenant by these tests. The tests assert that no row claims otherwise.

## G10 — A 200 with a broken body read as "no assignments"

**Symptom.** A list returns `{"value": null}`, an HTML proxy error, or a first
page only — and the tool decides nothing is assigned, then creates a duplicate
or reports a clean teardown.

**Cause.** Naive parsing of `value`, and not following `nextLink`.

**What this skill does.** `page_values` follows every page, caps at
`MAX_PAGES`, refuses a self-referential `nextLink`, and treats any response
that is not a list of objects as a transport failure rather than an empty
result.

## G11 — The request authorised itself

**Symptom.** A payload arrives carrying `{"approved": true}` or a capability
field, and the code that reads it believes it.

**Cause.** Whoever composes the request composes the flag. Authorisation
carried inside the thing being authorised is decoration.

**What this skill does.** `refuse_embedded_authority` refuses any payload
carrying an authority-shaped field. Authority is an `AuthorityPolicy` object
built by the host at start-up, with a tenant and scope allowlist that does not
follow the request, and confirmation tokens minted by this process, single-use
and bound to one target fingerprint.

## G12 — Teardown removed somebody else's grant

**Symptom.** A shared account loses an assignment another team depended on,
during a routine cleanup.

**Cause.** Deleting "everything that matches", inferring ownership from a
deterministic name, a description string, or a listing difference — or, subtler
and worse, deleting what the run *adopted*. Adoption is what happens when a
grant already existed: ARM answers `409 RoleAssignmentExists`, and the Cosmos,
Kusto, Graph and SQL adapters find a pre-existing match. Recording it lets a
plan say `noop`. Treating that record as ownership makes every teardown delete
the grants it found rather than the grants it made — which this skill did, until
it was audited.

**What this skill does.** `OwnershipRecord.source` is `created` only when this
run wrote it; `revocable` is true only then. `revoke` requires the record to be
`created`, the id currently readable to equal the recorded id, and the
assignment to still match the declaration exactly. Anything else is reported as
refused with category `ownership` and left in place. Deleting an adopted grant
is possible, and it costs an explicit `--authorized-id` naming that exact
assignment.

## G13 — The grant was correct and the check ran too early

**Symptom.** A verification fails, the grant is re-applied, and now there are
two — or a correct grant is investigated for an hour.

**Cause.** Directory and data-plane propagation is slow and asymmetric. Grants
land in minutes; revocations are usually faster; inference endpoints are slower
still. None of them can be inferred from another.

**What this skill does.** Verification polls to an explicit budget and reports
`waited_secs`. It never waits forever, and it never reports `present` because
enough time has probably passed.

## G14 — A probe became a data-exfiltration path

**Symptom.** An "access check" is returning response bodies into logs.

**Cause.** Proving access by reading data, and then keeping the data.

**What this skill does.** `AccessProbe` accepts `GET`/`HEAD` only, requires a
named action and a scope inside the allowlist, and returns the status,
category and whether it was permitted. The body is never read into the result,
never logged, never stored.

## G15 — One list response sent an ARM token to somebody else's server

**Symptom.** Nothing, until the token turns up in someone else's logs.

**Cause.** An ARM or Graph list answers a page plus `nextLink`, and paging code
follows it. `nextLink` is a URL chosen by whoever answered — or by whatever sits
between you and them. Pair that with a transport that attaches
`Authorization: Bearer …` to every request unconditionally and one hostile body
exfiltrates a live credential. urllib makes it worse: it follows redirects by
default and re-sends the header to wherever it is pointed.

**What this skill does.** Every live transport is bound to one `CloudEndpoints`
and one audience, and validates the URL **before** asking the credential for a
token — so a refused URL costs zero tokens, not one that merely was not sent. A
continuation must be same-origin with the page that produced it. Redirects are
refused, not followed. The offline tests assert the credential call count, not
just the refusal.

## G16 — A Kusto `Viewer` grant was reported present, and had never been made

**Symptom.** `plan` says `noop`, `verify` says `present`, and the principal
cannot do the thing. Or worse, `revoke` removes a much wider grant than the one
declared.

**Cause.** Comparing role identity with a suffix test. It is fine for GUIDs,
where the definition id sits at the end of a path. It is silently elevating for
the planes whose roles are *words*: `UnrestrictedViewer` ends with `Viewer`, and
`AllDatabasesAdmin` ends with `Admin`. Both are strictly wider grants.

**What this skill does.** `role_identity_matches` compares GUID-keyed planes by
exact last segment (which must be a GUID) and word-keyed planes by exact whole
string. An ABAC `conditionVersion` is part of identity too, so a v1.0 condition
does not satisfy a v2.0 declaration.

## G17 — The Cosmos grant landed and nothing could revoke it

**Symptom.** A create "fails" with an error about a missing `id`, and the
assignment is there in the portal afterwards.

**Cause.** `PUT .../sqlRoleAssignments/{name}` and the Kusto equivalent are
long-running operations. They answer `202 Accepted` with an
`Azure-AsyncOperation` header and **no body**. Code that reads `id` off that body
raises, records no ownership, and leaves an assignment nobody can attribute.

**What this skill does.** The assignment name is minted before the PUT, so the
target id is known regardless of what comes back. A `202` is polled to a bound
and the target read back; an empty `201` is read back too. If it cannot be
resolved, the outcome is `OperationPending` carrying the target id, surfaced in
`ApplyReport.pending` and in the refusal's `pending_target_id` — because "we do
not know" is a different answer from "it is not there", and conflating them is
how the orphan is made.

## G18 — The scope allowlist was defeated by a resource name

**Symptom.** A read or write lands somewhere the allowlist was supposed to
forbid, or drives an api-version nobody chose.

**Cause.** Normalising a scope instead of refusing it. A resource name
containing `?api-version=2015-07-01&x=` produces a URL whose *first*
api-version wins. A scope containing `../../../rg-secret` passes a string-prefix
allowlist and is then resolved by ARM into the group the allowlist existed to
protect. `%2F` is a `/` after the server decodes it.

**What this skill does.** `normalize_scope` drops trailing slashes and refuses
everything else — `?`, `#`, `&`, `%`, `\`, `@`, spaces, control characters,
`//`, `.` and `..` — at declaration construction, before a plan, an allowlist
check or a request. Containment is compared segment by segment, so `rg-app` does
not contain `rg-application`.

## G19 — `az rest` said 500 because the resource group is called `rg-500`

**Symptom.** A failure is diagnosed as the wrong thing entirely; or a 403
arrives as a 409 and is silently adopted as "already granted".

**Cause.** `az rest` prints a body, not a status line. Grepping any three-digit
run out of stderr turns `rg-500`, `kv-404-prod` and a quota number into HTTP
statuses. The same gap makes every success look like a flat `200`, which hides a
`202` long-running create completely.

**What this skill does.** Only structured sources map to a status — an explicit
`HTTP <nnn>`, a `status code: <nnn>`, or a recognised ARM error `code` — and
anything else is `UNKNOWN_STATUS`, never a guess. Successful CLI reads carry
`status_exact=False`, and `AzureCliTransport` refuses mutations outright:
`apply` and `revoke` need `TokenCredentialTransport`, which reads the real status
and headers off the wire.

## G20 — `--confirm` approved an Owner grant nobody looked at

**Symptom.** A confirmation ledger with target-bound single-use tokens, and an
entry point where typing one flag approves everything in the plan.

**Cause.** `manager.apply(plan, confirmations=manager.confirm(plan))`. Minting
and consuming in one expression means the token proves the process ran, not that
a human reviewed the target. A second failure hid behind it: a ledger that
popped the token *before* validating the binding, so one attempt against the
wrong target destroyed the approval for the right one.

**What this skill does.** `plan --save-plan` prints a digest over the plan's
effects (stable, because it excludes the per-run plan id). `apply` recomputes
the plan, refuses unless `--expect-digest` matches, and mints a token only for
each fingerprint named by `--confirm-target`. `ConfirmationLedger.consume`
validates before it burns, so a misdirected presentation refuses and leaves the
valid token valid.

## G21 — The folder was copied and `from azaccess import …` still fails

**Symptom.** `cp -r azure-access-management <repo>/skills/`, then
`ModuleNotFoundError: No module named 'azaccess'` from anywhere except inside
the copied folder.

**Cause.** The importable package is `azaccess/`, one directory *below* the
skill folder. Copying puts the folder on disk; it does not put the package on
the import path. The `PYTHONPATH=.` in the examples hides this, because it only
works from that one working directory.

**What this skill does.** Ships a `pyproject.toml`, so the copy ends in
`pip install <path-to-copied-folder>` and `from azaccess import …` works from
any directory, in any process, with no `PYTHONPATH` and no `sys.path` edit. The
install declares no runtime dependencies; `[live]` is an optional extra. The
folder still works uninstalled from inside itself, which is what the selftest
and `scripts/live_check.py` rely on.

## G22 — Removing somebody from a group deleted the person

**Symptom.** A cleanup script "removed a member" and a user object is gone from
the tenant. Or, on a less-privileged app, the same call answers `403` and
nobody can say why a removal needed more rights.

**Cause.** `DELETE /groups/{group-id}/members/{id}` without the trailing
`/$ref`. That is not the membership resource. Graph documents it plainly: if
`/$ref` is not appended and the caller may manage the member's object type, the
member object itself is deleted — an app with `GroupMember.ReadWrite.All` and
`User.ReadWrite.All` deletes the user. Otherwise it is a `403`, which is the
lucky outcome.

**What this skill does.** `group_member_remove_request` always emits
`DELETE …/groups/{g}/members/{id}/$ref`, and
`refuse_membership_url_without_ref` refuses any membership `DELETE` whose URL
does not end in `/$ref` before it can be sent. Object lifecycle
(`delete-directory-object`, `create-group`) is `unsupported` in the matrix: this
is access management, not directory administration.

## G23 — Owner of the subscription, and Microsoft Graph answers 403

**Symptom.** An identity with subscription `Owner` cannot add a group member,
grant an app role, or consent to anything. The error says insufficient
privileges and the RBAC assignment is plainly there.

**Cause.** Azure RBAC and Microsoft Entra are two authorization systems. Azure
RBAC governs Azure *resources*; the directory governs users, groups, service
principals and permissions. No Azure role, Owner included, confers a Microsoft
Graph permission. Directory writes need application permissions on the calling
app with admin consent, and in delegated flows a supporting Entra role on the
signed-in user — both, not either.

**What this skill does.** Documents the prerequisite per procedure (CONTRACT
§8) instead of implying a role assignment is enough, refuses a Graph provider
built on an ARM-audience transport at construction, and leaves the directory
writes as built-not-sent so the host supplies a token that actually carries the
permission.

## G24 — The create answered 201 and the assignment was still provisioning

**Symptom.** A Cosmos or Kusto create returns `201`, ownership is recorded, and
the very next read-back finds nothing — or the assignment fails minutes later
and the run has already reported success.

**Cause.** `201` with a body is not automatically a finished create: the body
can carry `provisioningState: "Creating"`. Reading the `id` out of it and
calling it done records ownership of something that may never land.

**What this skill does.** Treats a non-terminal `provisioningState` on a
`200`/`201` as an accepted create and resolves it by reading the target back; a
read-back that is itself non-terminal is `OperationPending` carrying the target
id. Polling is bounded twice — 30 polls and 120 seconds — paced by the server's
`Retry-After` clamped to 1–30 seconds, with `sleeper` and `clock` injectable. A
poll response whose body is not a JSON object is `OperationPending` too, because
losing the target id to a parse error is how an orphan is made.

## G25 — The teardown reported clean and the assignment is still there

**Symptom.** `revoke` printed deletions, the ownership records and ledger files
are gone, and the grant is still readable. Nothing left says which id to remove.

**Cause.** Dropping the ownership record immediately after `DELETE` returned.
A DELETE can be accepted (`202`) and not finished, a read-back can fail, and a
governance policy can put the assignment back. Every one of those looked like
success, and the coordinate needed to clean it up was already deleted.

**What this skill does.** Keeps the record and its ledger file until that
**exact id** is proved absent, and reports why it was kept in
`RevokeReport.retained` (`delete-pending`, `target-present`, `target-unknown`,
`ledger-write`). Proof is per-id, not per-scope: another writer's assignment at
the same scope is reported and left in place, and never becomes a reason to keep
waiting or to delete. A later `revoke` that reads the scope and does not find
the recorded id clears it then.
