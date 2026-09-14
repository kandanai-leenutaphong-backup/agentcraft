#!/usr/bin/env python3
"""selftest.py — proves this skill works here, with no test framework installed.

Runs offline. No network, no credential, no Azure account: every plane adapter
is driven against a recorded transport that also captures the requests, so the
assertions are about the *requests this package builds* and the decisions it
makes, not merely that the code survived being called.

    python3 tests/selftest.py

One line per check, non-zero exit on the first failure summary.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from azaccess import (  # noqa: E402
    AccessDeclaration,
    AccessManager,
    AccessProbe,
    ArmRbacProvider,
    AssignmentState,
    AuthorityPolicy,
    AuthorizationRefused,
    AzureCliTransport,
    ConfirmationLedger,
    CoordinateError,
    CosmosSqlRbacProvider,
    GraphAppRoleProvider,
    IdentityRef,
    KustoDatabaseProvider,
    OperationPending,
    Plan,
    PlanStep,
    ProviderConflict,
    RecordingSqlExecutor,
    RecordingTransport,
    Response,
    Scope,
    SqlDatabaseUserProvider,
    TransportError,
    UNEVALUATED_SEMANTICS,
    bounded_policy,
    federated_credential_request,
    lookup_role,
    quote_identifier,
    refuse_embedded_authority,
    render_matrix,
    sanitize_detail,
    sql_grant_statements,
    support_matrix,
    user_assigned_identity,
)
from azaccess.matrix import EVIDENCE, STATUSES  # noqa: E402

# Synthetic coordinates. Not one of them addresses a real estate.
TENANT = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT = "99999999-9999-9999-9999-999999999999"
SUB = "22222222-2222-2222-2222-222222222222"
PRINCIPAL = "33333333-3333-3333-3333-333333333333"
OTHER_PRINCIPAL = "44444444-4444-4444-4444-444444444444"
CLIENT_ID = "55555555-5555-5555-5555-555555555555"

RG = f"/subscriptions/{SUB}/resourceGroups/demo-rg"
ACCOUNT = f"{RG}/providers/Microsoft.Storage/storageAccounts/data-acct"
CONTAINER = f"{ACCOUNT}/blobServices/default/containers/box"
COSMOS = f"{RG}/providers/Microsoft.DocumentDB/databaseAccounts/docs-acct"
COSMOS_SCOPE = f"{COSMOS}/dbs/appdb/colls/items"
KUSTO_DB = f"{RG}/providers/Microsoft.Kusto/clusters/analytics/databases/telemetry"

BLOB_READER = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
OWNER = "8e3af657-a8ff-443c-a75c-2fe8c4bcb635"

_FAILURES: list[str] = []
_CHECKS = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _CHECKS
    _CHECKS += 1
    if condition:
        print(f"ok   {name}")
    else:
        print(f"FAIL {name}{(' — ' + detail) if detail else ''}")
        _FAILURES.append(name)


def refuses(name: str, fn, *expected) -> None:
    """A check that passes only when the call is refused for the right reason."""
    try:
        fn()
    except expected as exc:  # noqa: PERF203 - the message is the evidence
        check(name, True)
        globals().setdefault("_LAST_REFUSAL", "")
        globals()["_LAST_REFUSAL"] = str(exc)
        return
    except Exception as exc:  # wrong error type is still a failure
        check(name, False, f"raised {type(exc).__name__}: {exc}")
        return
    check(name, False, "no refusal raised")


class FakeClock:
    """Time only moves when something sleeps, so budgets are deterministic."""

    def __init__(self) -> None:
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, secs: float) -> None:
        self.slept.append(secs)
        self.now += max(secs, 0.001)


def identity(object_id: str = PRINCIPAL, tenant: str = TENANT) -> IdentityRef:
    return user_assigned_identity(
        principal_id=object_id, client_id=CLIENT_ID, tenant_id=tenant,
        display_name="workload-identity",
    )


def arm_item(assignment_id: str, principal: str, role_id: str, scope: str,
             condition: str = "") -> dict:
    properties = {
        "principalId": principal,
        "roleDefinitionId": (
            f"/subscriptions/{SUB}/providers/Microsoft.Authorization"
            f"/roleDefinitions/{role_id}"
        ),
        "scope": scope,
        "principalType": "ServicePrincipal",
    }
    if condition:
        properties["condition"] = condition
        properties["conditionVersion"] = "2.0"
    return {
        "id": assignment_id,
        "name": assignment_id.rsplit("/", 1)[-1],
        "properties": properties,
    }


def page(items: list, next_link: str = "") -> Response:
    body = {"value": items}
    if next_link:
        body["nextLink"] = next_link
    return Response(status=200, body=body)


def _sql_row(permission: str = "SELECT", *, class_desc: str = "OBJECT_OR_COLUMN",
             state_desc: str = "GRANT", major_id: int = 1234,
             user_name: str = "app-reader") -> dict:
    """One row shaped like ``sys.database_permissions`` actually answers."""
    return {
        "user_name": user_name,
        "permission_name": permission,
        "class_desc": class_desc,
        "state_desc": state_desc,
        "major_id": major_id,
        "minor_id": 0,
    }


def graph_transport() -> RecordingTransport:
    """A recorded transport that claims a Microsoft Graph token audience."""
    from azaccess import AZURE_PUBLIC_CLOUD

    return RecordingTransport(audience=AZURE_PUBLIC_CLOUD.graph_audience)


def blob_declaration(scope: str = CONTAINER, condition: str = "",
                     tenant: str = TENANT) -> AccessDeclaration:
    return AccessDeclaration(
        principal=identity(tenant=tenant),
        role="Storage Blob Data Reader",
        scope=scope,
        condition=condition,
    )


def read_policy(**kwargs) -> AuthorityPolicy:
    policy = bounded_policy(tenant_id=TENANT, scopes=[RG], max_tier="read")
    return policy.with_authorized(**kwargs) if kwargs else policy


def write_policy(max_tier: str = "read", roles=()) -> AuthorityPolicy:
    return bounded_policy(tenant_id=TENANT, scopes=[RG], max_tier=max_tier)\
        .with_authorized(read_only=False, roles=roles)


def arm_manager(transport: RecordingTransport, policy: AuthorityPolicy,
                clock: FakeClock | None = None) -> AccessManager:
    clock = clock or FakeClock()
    provider = ArmRbacProvider(
        transport, subscription_id=SUB, name_factory=lambda: "fixed-assignment-name"
    )
    return AccessManager(
        {
            "azure-rbac": provider,
            "cosmos-sql-rbac": CosmosSqlRbacProvider(
                transport, name_factory=lambda: "fixed-cosmos-name",
                sleeper=lambda s: None),
            "kusto-database": KustoDatabaseProvider(
                transport, name_factory=lambda: "fixed-kusto-name",
                sleeper=lambda s: None),
        },
        policy=policy, clock=clock, sleeper=clock.sleep,
        id_factory=lambda: "plan-0001",
    )


# ---------------------------------------------------------------- coordinates


def test_identity_coordinates() -> None:
    ident = identity()
    check("identity: object id and client id stay distinct",
          ident.object_id == PRINCIPAL and ident.client_id == CLIENT_ID)
    check("identity: managed identity serialises as ServicePrincipal",
          ident.principal_type == "ServicePrincipal")
    refuses("identity: a client id used as the object id is refused",
            lambda: IdentityRef(object_id=CLIENT_ID, kind="managed-identity",
                                client_id=CLIENT_ID), CoordinateError)
    refuses("identity: a non-GUID principal is refused before any request",
            lambda: IdentityRef(object_id="my-identity", kind="user"),
            CoordinateError)
    refuses("identity: an application object is refused as unassignable",
            lambda: IdentityRef(object_id=PRINCIPAL, kind="application"),
            CoordinateError)
    check("identity: describe() carries no client id or credential",
          "client_id" not in ident.describe())


def test_scopes() -> None:
    scope = Scope.parse(CONTAINER)
    ancestors = [a.value for a in scope.ancestors()]
    check("scope: child resource parses as child-resource",
          scope.level == "child-resource")
    check("scope: ancestors walk container -> service -> account -> rg -> sub",
          ancestors == [f"{ACCOUNT}/blobServices/default", ACCOUNT, RG,
                        f"/subscriptions/{SUB}"], str(ancestors))
    check("scope: an ancestor does not equal the exact scope",
          not Scope.parse(RG).is_exact(CONTAINER)
          and Scope.parse(RG).contains(CONTAINER))
    check("scope: management-group ancestry is not invented",
          all("managementGroups" not in a for a in ancestors))
    refuses("scope: a non-ARM string is refused",
            lambda: Scope.parse("demo-rg"), CoordinateError)


# ---------------------------------------------------------------- authority


def test_authority_gates() -> None:
    transport = RecordingTransport().script("GET", "roleAssignments", page([]))
    manager = arm_manager(transport, write_policy())

    plan = manager.plan([blob_declaration(tenant=OTHER_TENANT)])
    check("authority: a tenant outside the allowlist is refused at plan time",
          not plan.steps and plan.refusals
          and plan.refusals[0]["category"] == "authorization",
          json.dumps(plan.to_dict()["refusals"]))

    outside = f"/subscriptions/{SUB}/resourceGroups/other-rg"
    plan = manager.plan([blob_declaration(scope=outside)])
    check("authority: a scope outside the allowlist is refused, whatever was asked",
          not plan.steps and plan.refusals
          and "outside the allowlist" in plan.refusals[0]["reason"])

    owner = AccessDeclaration(principal=identity(), role="Owner", scope=RG)
    plan = manager.plan([owner])
    check("authority: a privileged role above max_tier is refused by tier",
          not plan.steps and "tier" in plan.refusals[0]["reason"])

    named = arm_manager(transport, write_policy(roles=("Owner",)))
    plan = named.plan([owner])
    check("authority: the same role is allowed when named individually",
          len(plan.steps) == 1 and plan.steps[0].action == "create")
    check("authority: a privileged step demands confirmation",
          plan.steps[0].requires_confirmation)

    read_only = arm_manager(transport, read_policy())
    plan = read_only.plan([blob_declaration()])
    check("authority: read-only policy refuses every create",
          not plan.steps and plan.refusals[0]["category"] == "authorization")


def test_no_self_authorisation() -> None:
    refuses("authority: a request carrying 'approved' is refused, not read",
            lambda: refuse_embedded_authority({"approved": True, "scope": RG}),
            AuthorizationRefused)
    refuses("authority: a request carrying 'capability' is refused",
            lambda: refuse_embedded_authority({"capability": "write"}),
            AuthorizationRefused)

    policy = AuthorityPolicy(
        allowed_tenants=frozenset({TENANT}), allowed_scopes=(RG,),
        max_tier="write", read_only=False,
        self_principal_ids=frozenset({PRINCIPAL}),
    )
    transport = RecordingTransport().script("GET", "roleAssignments", page([]))
    manager = arm_manager(transport, policy)
    plan = manager.plan([blob_declaration()])
    check("authority: granting to this process's own principal is refused",
          not plan.steps and "self-grant" in plan.refusals[0]["reason"])


def test_confirmation_tokens() -> None:
    clock = FakeClock()
    ledger = ConfirmationLedger(ttl_secs=60.0, clock=clock)
    token = ledger.mint("plan-0001", "fingerprint-a")
    refuses("confirmation: a token minted for another target is refused",
            lambda: ledger.consume(token, "plan-0001", "fingerprint-b"),
            AuthorizationRefused)
    token2 = ledger.mint("plan-0001", "fingerprint-a")
    ledger.consume(token2, "plan-0001", "fingerprint-a")
    check("confirmation: a valid token is accepted once", True)
    refuses("confirmation: the same token cannot be used twice",
            lambda: ledger.consume(token2, "plan-0001", "fingerprint-a"),
            AuthorizationRefused)
    token3 = ledger.mint("plan-0001", "fingerprint-c")
    clock.now = 3600.0
    refuses("confirmation: an expired token is refused",
            lambda: ledger.consume(token3, "plan-0001", "fingerprint-c"),
            AuthorizationRefused)


# ---------------------------------------------------------------- arm plane


def test_arm_request_serialisation() -> None:
    transport = RecordingTransport()
    transport.script("GET", "roleAssignments?api-version", page([]))
    transport.script(
        "PUT", "roleAssignments/fixed-assignment-name",
        Response(status=201, body=arm_item(
            f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/abc",
            PRINCIPAL, BLOB_READER, CONTAINER)),
    )
    manager = arm_manager(transport, write_policy(max_tier="read"))
    declaration = blob_declaration()
    plan = manager.plan([declaration])
    report = manager.apply(plan, confirmations=manager.confirm(plan),
                           verify_budget_secs=0.0)

    put_bodies = transport.bodies("PUT")
    body = put_bodies[0]["properties"] if put_bodies else {}
    check("arm: role definition id is subscription-qualified",
          body.get("roleDefinitionId", "").endswith(
              f"/Microsoft.Authorization/roleDefinitions/{BLOB_READER}"),
          json.dumps(body))
    check("arm: principalType is sent explicitly",
          body.get("principalType") == "ServicePrincipal")
    check("arm: principalId is the object id, never the client id",
          body.get("principalId") == PRINCIPAL)
    check("arm: the PUT carries the pinned api-version",
          "api-version=2022-04-01" in transport.urls("PUT")[0])
    check("arm: the list filters at scope",
          "$filter=atScope()" in transport.urls("GET")[0])
    check("arm: ownership records the id the service returned",
          len(report.ownership) == 1
          and report.ownership[0].assignment_id.endswith("/roleAssignments/abc")
          and report.ownership[0].source == "created")


def test_inherited_is_not_exact() -> None:
    inherited = arm_item(
        f"{RG}/providers/Microsoft.Authorization/roleAssignments/inherited",
        PRINCIPAL, BLOB_READER, RG)
    transport = RecordingTransport().script(
        "GET", "roleAssignments?api-version", page([inherited]))
    manager = arm_manager(transport, write_policy())
    declaration = blob_declaration()
    plan = manager.plan([declaration])
    check("inherited: an assignment at the resource group does not satisfy the "
          "container declaration",
          len(plan.steps) == 1 and plan.steps[0].action == "create")
    check("inherited: the plan says where the access is coming from instead",
          "inherited from" in plan.steps[0].reason, plan.steps[0].reason)

    report = manager.diff([declaration])
    check("diff: inherited access is reported separately from satisfied",
          len(report.inherited_only) == 1 and not report.satisfied
          and not report.missing)
    check("diff: unevaluated semantics are named, never assumed absent",
          "deny-assignments" in report.unevaluated
          and "pim-eligible-assignments" in report.unevaluated)

    effective = manager.inspect(PRINCIPAL, CONTAINER)
    check("inspect: effective access is never reported as complete",
          effective.completeness == "partial" and len(effective.inherited) == 1
          and not effective.exact)


def test_conditions_are_not_conflated() -> None:
    condition = (
        "@Resource[Microsoft.Storage/storageAccounts/blobServices/containers:name]"
        " StringEquals 'box'"
    )
    conditional = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/cond",
        PRINCIPAL, BLOB_READER, CONTAINER, condition=condition)
    transport = RecordingTransport().script(
        "GET", "roleAssignments?api-version", page([conditional]))
    manager = arm_manager(transport, write_policy())
    plan = manager.plan([blob_declaration()])
    check("conditions: a conditional assignment does not satisfy an "
          "unconditional declaration",
          plan.steps[0].action == "create")
    plan = manager.plan([blob_declaration(condition=condition)])
    check("conditions: the same condition matches exactly",
          plan.steps[0].action == "noop")
    check("conditions: the fingerprint changes with the condition",
          blob_declaration().fingerprint()
          != blob_declaration(condition=condition).fingerprint())


def test_pagination_and_malformed_responses() -> None:
    first = arm_item(f"{CONTAINER}/providers/Microsoft.Authorization"
                     f"/roleAssignments/one", OTHER_PRINCIPAL, BLOB_READER, CONTAINER)
    second = arm_item(f"{CONTAINER}/providers/Microsoft.Authorization"
                      f"/roleAssignments/two", PRINCIPAL, BLOB_READER, CONTAINER)
    next_link = "https://management.azure.com/page-2"
    transport = RecordingTransport()
    transport.script("GET", "roleAssignments?api-version", page([first], next_link))
    transport.script("GET", "page-2", page([second]))
    provider = ArmRbacProvider(transport, subscription_id=SUB)
    found = provider.matches(blob_declaration())
    check("paging: an assignment on page two is found, not reported absent",
          len(found) == 1 and found[0].assignment_id.endswith("/two"))

    for label, body in (
        ("null value array", {"value": None}),
        ("missing value array", {"error": {"code": "InvalidAuthenticationToken"}}),
        ("html error page", {"raw": "<html>proxy error</html>"}),
    ):
        broken = RecordingTransport().script(
            "GET", "roleAssignments", Response(status=200, body=body))
        refuses(f"malformed: {label} is a failure, not 'no assignments'",
                lambda b=broken: ArmRbacProvider(b, subscription_id=SUB)
                .matches(blob_declaration()), TransportError)

    partial = RecordingTransport().script(
        "GET", "roleAssignments", Response(status=503, body={"error": "busy"}))
    refuses("http: a 503 on the read is a failure, not an empty result",
            lambda: ArmRbacProvider(partial, subscription_id=SUB)
            .matches(blob_declaration()), TransportError)


def test_conflict_adoption_preserves_concurrent_writer() -> None:
    concurrent = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/theirs",
        PRINCIPAL, BLOB_READER, CONTAINER)
    transport = RecordingTransport()
    # First read: empty (we decide to create). Then a 409 because another writer
    # got there first. Then the read that finds theirs.
    transport.script("GET", "roleAssignments?api-version", page([]),
                     page([concurrent]), page([concurrent]))
    transport.script("PUT", "roleAssignments/fixed-assignment-name",
                     Response(status=409, body={"error": {
                         "code": "RoleAssignmentExists"}}))
    manager = arm_manager(transport, write_policy())
    declaration = blob_declaration()
    plan = manager.plan([declaration])
    report = manager.apply(plan, confirmations=manager.confirm(plan),
                           verify_budget_secs=0.0)
    check("conflict: a 409 is adopted with the real id, not treated as created",
          len(report.ownership) == 1
          and report.ownership[0].source == "adopted"
          and report.ownership[0].assignment_id.endswith("/theirs"))

    lying = RecordingTransport()
    lying.script("GET", "roleAssignments?api-version", page([]))
    lying.script("PUT", "roleAssignments/", Response(status=409, body={}))
    provider = ArmRbacProvider(lying, subscription_id=SUB,
                               name_factory=lambda: "n")
    refuses("conflict: a 409 with nothing readable is a conflict, not a success",
            lambda: provider.create(declaration, plan_id="p"), ProviderConflict)


def test_policy_revert_and_propagation() -> None:
    created = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/abc",
        PRINCIPAL, BLOB_READER, CONTAINER)
    transport = RecordingTransport()
    transport.script("GET", "roleAssignments?api-version", page([]))
    transport.script("PUT", "roleAssignments/fixed-assignment-name",
                     Response(status=201, body=created))
    clock = FakeClock()
    manager = arm_manager(transport, write_policy(), clock)
    plan = manager.plan([blob_declaration()])
    report = manager.apply(plan, confirmations=manager.confirm(plan),
                           verify_budget_secs=20.0)
    verification = report.verifications[0]
    check("revert: a write that reports 201 and reads back absent is flagged",
          verification.status == "revert-suspected", verification.detail)
    check("revert: the report names policy as a candidate cause",
          "policy" in verification.detail.lower())
    check("revert: the wait is bounded, not infinite",
          verification.waited_secs >= 20.0 and clock.slept)
    check("apply: a run with a failed read-back is not ok", not report.ok)

    # Same shape, but the assignment appears on a later read: propagation.
    # Two reads are consumed by planning (exact, then inherited), so the third
    # is the first read-back and the fourth is when it lands.
    slow = RecordingTransport()
    slow.script("GET", "roleAssignments?api-version", page([]), page([]),
                page([]), page([created]))
    slow.script("PUT", "roleAssignments/fixed-assignment-name",
                Response(status=201, body=created))
    clock2 = FakeClock()
    manager2 = arm_manager(slow, write_policy(), clock2)
    plan2 = manager2.plan([blob_declaration()])
    report2 = manager2.apply(plan2, confirmations=manager2.confirm(plan2),
                             verify_budget_secs=60.0)
    check("propagation: a late assignment verifies present within budget",
          report2.verifications[0].status == "present"
          and report2.verifications[0].waited_secs > 0.0)
    check("propagation: the elapsed wait is reported, not hidden",
          report2.verifications[0].to_dict()["waited_secs"] > 0)

    unreadable = RecordingTransport()
    unreadable.script("GET", "roleAssignments", Response(status=500, body={}))
    manager3 = arm_manager(unreadable, write_policy(), FakeClock())
    result = manager3.verify_one(blob_declaration(), budget_secs=0.0)
    check("verify: a read that fails is 'unknown', never 'absent'",
          result.status == "unknown", result.detail)


def test_revoke_ownership_and_absence() -> None:
    mine = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/abc",
        PRINCIPAL, BLOB_READER, CONTAINER)
    transport = RecordingTransport()
    # planning reads twice (exact, inherited), then apply verifies, then revoke
    # matches, then the final read proves absence.
    transport.script("GET", "roleAssignments?api-version",
                     page([]), page([]), page([mine]), page([mine]), page([]))
    transport.script("PUT", "roleAssignments/fixed-assignment-name",
                     Response(status=201, body=mine))
    transport.script("DELETE", "/roleAssignments/abc", Response(status=204, body={}))
    manager = arm_manager(transport, write_policy(), FakeClock())
    declaration = blob_declaration()
    plan = manager.plan([declaration])
    manager.apply(plan, confirmations=manager.confirm(plan), verify_budget_secs=30.0)
    revoked = manager.revoke([declaration], budget_secs=0.0)
    check("revoke: the assignment this run created is deleted",
          list(revoked.deleted) == [mine["id"]], json.dumps(revoked.to_dict()))
    check("revoke: absence is verified, not assumed",
          revoked.ok and revoked.verifications[0].status == "absent")

    # An assignment this run never made must survive teardown.
    theirs = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/theirs",
        PRINCIPAL, BLOB_READER, CONTAINER)
    other = RecordingTransport().script(
        "GET", "roleAssignments?api-version", page([theirs]))
    manager2 = arm_manager(other, write_policy(), FakeClock())
    report = manager2.revoke([declaration], budget_secs=0.0)
    check("revoke: an unowned assignment is left in place and reported",
          not report.deleted and report.refused
          and report.refused[0]["category"] == "ownership")
    check("revoke: leaving it in place is not silently called success",
          not report.ok and report.verifications[0].status == "present")
    check("revoke: no DELETE was ever issued for the unowned assignment",
          not other.urls("DELETE"))

    explicit = RecordingTransport()
    explicit.script("GET", "roleAssignments?api-version", page([theirs]), page([]))
    explicit.script("DELETE", "/roleAssignments/theirs", Response(status=204, body={}))
    manager3 = arm_manager(explicit, write_policy(), FakeClock())
    report3 = manager3.revoke([declaration], authorized_ids=[theirs["id"]],
                              budget_secs=0.0)
    check("revoke: an explicitly authorised id is deleted and verified absent",
          list(report3.deleted) == [theirs["id"]] and report3.ok)


# ---------------------------------------------------------------- other planes


def test_cosmos_duplicates() -> None:
    declaration = AccessDeclaration(
        principal=identity(), role="Cosmos DB Built-in Data Reader",
        scope=COSMOS_SCOPE,
    )
    existing = {
        "id": f"{COSMOS}/sqlRoleAssignments/one",
        "name": "one",
        "properties": {
            "principalId": PRINCIPAL,
            "roleDefinitionId": f"{COSMOS}/sqlRoleDefinitions/"
                                "00000000-0000-0000-0000-000000000001",
            "scope": COSMOS_SCOPE,
        },
    }
    transport = RecordingTransport().script("GET", "sqlRoleAssignments", page([existing]))
    provider = CosmosSqlRbacProvider(transport, name_factory=lambda: "new")
    record = provider.create(declaration, plan_id="p")
    check("cosmos: an existing assignment is adopted rather than duplicated",
          record.source == "adopted" and not transport.urls("PUT"))

    duplicated = dict(existing, id=f"{COSMOS}/sqlRoleAssignments/two", name="two")
    both = RecordingTransport().script(
        "GET", "sqlRoleAssignments", page([existing, duplicated]))
    provider2 = CosmosSqlRbacProvider(both)
    check("cosmos: duplicates are reported, never mass-deleted",
          provider2.duplicates(declaration) == (duplicated["id"],))

    fresh = RecordingTransport()
    fresh.script("GET", "sqlRoleAssignments", page([]))
    fresh.script("PUT", "sqlRoleAssignments/new",
                 Response(status=201, body=existing))
    provider3 = CosmosSqlRbacProvider(fresh, name_factory=lambda: "new")
    provider3.create(declaration, plan_id="p")
    body = fresh.bodies("PUT")[0]["properties"]
    check("cosmos: the role definition id is account-relative, not ARM-qualified",
          body["roleDefinitionId"].startswith(COSMOS + "/sqlRoleDefinitions/"))
    check("cosmos: the scope is the data-plane path",
          body["scope"] == COSMOS_SCOPE)
    check("cosmos: the api-version is pinned on the write",
          "api-version=" in fresh.urls("PUT")[0])
    refuses("cosmos: a non-Cosmos id is refused for deletion",
            lambda: provider3.delete(
                f"{CONTAINER}/providers/Microsoft.Authorization"
                f"/roleAssignments/abc"), ProviderConflict)

    check("cosmos: a Cosmos grant is invisible to the Azure RBAC plane",
          lookup_role("Cosmos DB Built-in Data Reader").plane == "cosmos-sql-rbac")


def test_kusto_plane() -> None:
    declaration = AccessDeclaration(
        principal=identity(), role="Kusto Database Viewer", scope=KUSTO_DB)
    transport = RecordingTransport()
    transport.script("GET", "principalAssignments", page([]))
    transport.script("PUT", "principalAssignments/fixed",
                     Response(status=200, body={
                         "id": f"{KUSTO_DB}/principalAssignments/fixed",
                         "properties": {"principalId": PRINCIPAL, "role": "Viewer"}}))
    provider = KustoDatabaseProvider(transport, name_factory=lambda: "fixed")
    record = provider.create(declaration, plan_id="p")
    body = transport.bodies("PUT")[0]["properties"]
    check("kusto: the role is a word, not a GUID", body["role"] == "Viewer")
    check("kusto: the principal type is Kusto's own vocabulary",
          body["principalType"] == "App")
    check("kusto: the tenant travels with the assignment",
          body["tenantId"] == TENANT)
    check("kusto: ownership carries the returned id",
          record.assignment_id.endswith("/principalAssignments/fixed"))
    refuses("kusto: a cluster-scope grant is refused; this plane grants at "
            "database scope",
            lambda: provider.create(
                AccessDeclaration(principal=identity(),
                                  role="Kusto Database Viewer",
                                  scope=f"{RG}/providers/Microsoft.Kusto/clusters/"
                                        f"analytics"),
                plan_id="p"), CoordinateError)


def test_sql_plane() -> None:
    declaration = AccessDeclaration(
        principal=identity(), role="SQL Table Data Reader",
        scope=f"{RG}/providers/Microsoft.Sql/servers/server/databases/appdb",
        target={"schema": "dbo", "table": "events", "user_name": "app-reader"},
    )
    statements = sql_grant_statements(declaration)
    check("sql: a contained user is created from the external provider",
          "CREATE USER [app-reader] FROM EXTERNAL PROVIDER;" in statements[0],
          statements[0])
    check("sql: the CREATE USER is guarded, so a second apply is not error 15023",
          statements[0].startswith("IF NOT EXISTS (SELECT 1 FROM "
                                   "sys.database_principals WHERE name = "
                                   "N'app-reader')"),
          statements[0])
    check("sql: a UPN-named principal is accepted, not refused for its '@'",
          "[app@contoso.onmicrosoft.com]" in sql_grant_statements(
              AccessDeclaration(
                  principal=identity(), role="SQL Table Data Reader",
                  scope=declaration.scope,
                  target={"schema": "dbo", "table": "events",
                          "user_name": "app@contoso.onmicrosoft.com"}))[0])
    check("sql: the grant names one table, not a database role",
          statements[1] == "GRANT SELECT ON [dbo].[events] TO [app-reader];",
          statements[1])
    refuses("sql: an identifier with a quote or semicolon is refused, not escaped",
            lambda: sql_grant_statements(AccessDeclaration(
                principal=identity(), role="SQL Table Data Reader",
                scope=declaration.scope,
                target={"schema": "dbo", "table": "events]; DROP TABLE x --",
                        "user_name": "app-reader"})), CoordinateError)

    no_executor = SqlDatabaseUserProvider()
    refuses("sql: with no executor the plane refuses rather than faking HTTP",
            lambda: no_executor.create(declaration, plan_id="p"), ProviderConflict)

    executor = RecordingSqlExecutor(rows=[_sql_row()])
    provider = SqlDatabaseUserProvider(executor, owned_prefix="app-")
    record = provider.create(declaration, plan_id="p")
    check("sql: an already-granted permission is adopted, not re-created",
          record.source == "adopted"
          and any("sys.database_permissions" in s for s in executor.statements))

    granting = RecordingSqlExecutor(rows_for={
        "sys.database_permissions": [],
        "sys.database_principals WHERE name": [],
    })
    fresh = SqlDatabaseUserProvider(granting)
    refuses("sql: a grant whose read-back finds nothing is a conflict, not success",
            lambda: fresh.create(declaration, plan_id="p"), ProviderConflict)

    half_applied = RecordingSqlExecutor(rows=[])
    refuses("sql: a user that exists with no permission is not 'present'",
            lambda: SqlDatabaseUserProvider(half_applied).create(
                declaration, plan_id="p"), ProviderConflict)

    refuses("sql: dropping a user outside the owned prefix is refused",
            lambda: provider.delete(f"{declaration.scope}/users/dba-admin"),
            AuthorizationRefused)


def test_graph_plane() -> None:
    transport = graph_transport().script(
        "POST", "appRoleAssignments", Response(status=201, body={"id": "assignment-1"}))
    provider = GraphAppRoleProvider(transport)
    assignment_id = provider.create_assignment(
        principal_id=PRINCIPAL, resource_id=OTHER_PRINCIPAL, app_role_id=CLIENT_ID)
    check("graph: the assignment id is read from the response",
          assignment_id == "assignment-1")
    check("graph: the three GUIDs are sent under their own names",
          set(transport.bodies("POST")[0]) == {"principalId", "resourceId",
                                               "appRoleId"})
    refuses("graph: a non-GUID app role id is refused before the request",
            lambda: provider.build_assignment_body(
                principal_id=PRINCIPAL, resource_id=OTHER_PRINCIPAL,
                app_role_id="Mail.Read"), CoordinateError)

    body = federated_credential_request(
        name="deploy", issuer="https://token.actions.example.com",
        subject="repo:example/repo:ref:refs/heads/main")
    check("graph: a federated credential carries no secret at all",
          set(body) == {"name", "issuer", "subject", "audiences", "description"}
          and body["audiences"] == ["api://AzureADTokenExchange"])
    refuses("graph: a non-https federated issuer is refused",
            lambda: federated_credential_request(
                name="x", issuer="http://issuer.invalid", subject="s"),
            CoordinateError)


# ---------------------------------------------------------------- discretion


def test_no_credential_material_escapes() -> None:
    leaky = (
        "request failed: Authorization: Bearer "
        "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9.abcdefghijklmnopqrstuvwxyz012345"
        ".signature accountKey=Zm9vYmFyYmF6cXV4 and password: hunter2hunter2"
    )
    cleaned = sanitize_detail(leaky)
    check("discretion: a bearer token never survives into an error string",
          "eyJ0eXAi" not in cleaned and "Bearer <redacted>" in cleaned, cleaned)
    check("discretion: an account key is redacted",
          "Zm9vYmFyYmF6cXV4" not in cleaned, cleaned)

    failing = RecordingTransport().script(
        "GET", "roleAssignments",
        Response(status=403, body={"error": {"message": leaky}}))
    try:
        ArmRbacProvider(failing, subscription_id=SUB).matches(blob_declaration())
        check("discretion: a 403 body is sanitised before it reaches the caller",
              False, "no error raised")
    except TransportError as exc:
        check("discretion: a 403 body is sanitised before it reaches the caller",
              "eyJ0eXAi" not in str(exc) and "403" in str(exc), str(exc))

    policy = read_policy()
    check("discretion: policy.describe() reports counts, never tenant values",
          policy.describe()["tenants"] == 1
          and TENANT not in json.dumps(policy.describe()))


def test_probe_returns_no_data() -> None:
    transport = RecordingTransport().script(
        "GET", "/box", Response(status=200, body={"secretDocument": "value"}))
    probe = AccessProbe(transport, policy=read_policy())
    result = probe.probe(action="read one blob listing", scope=CONTAINER,
                         url="https://management.azure.com/box?comp=list")
    payload = json.dumps(result.to_dict())
    check("probe: the response body never appears in the result",
          "secretDocument" not in payload and "value" not in payload, payload)
    check("probe: the query string is dropped from the recorded url",
          "?" not in result.url and result.allowed)
    refuses("probe: a write method is refused; probes are read-only",
            lambda: probe.probe(action="write", scope=CONTAINER,
                                url="https://management.azure.com/box",
                                method="DELETE"), AuthorizationRefused)
    refuses("probe: an unlabelled probe is refused",
            lambda: probe.probe(action="  ", scope=CONTAINER,
                                url="https://management.azure.com/box"),
            AuthorizationRefused)
    refuses("probe: a target outside the scope allowlist is refused",
            lambda: probe.probe(action="read", scope="/subscriptions/"
                                + OTHER_PRINCIPAL,
                                url="https://management.azure.com/x"),
            AuthorizationRefused)

    denied = RecordingTransport().script("GET", "/box", Response(status=403, body={}))
    outcome = AccessProbe(denied, policy=read_policy()).probe(
        action="read", scope=CONTAINER, url="https://management.azure.com/box")
    check("probe: 403 is categorised as authorization, distinct from 401",
          outcome.category == "authorization" and not outcome.allowed)
    unauth = RecordingTransport().script("GET", "/box", Response(status=401, body={}))
    check("probe: 401 is categorised as authentication, not a missing grant",
          AccessProbe(unauth, policy=read_policy()).probe(
              action="read", scope=CONTAINER,
              url="https://management.azure.com/box").category == "authentication")


# ---------------------------------------------------------------- matrix, cli


def test_support_matrix_comes_from_code() -> None:
    rows = support_matrix()
    check("matrix: every row carries a known status",
          all(r.status in STATUSES for r in rows) and len(rows) > 20)
    check("matrix: the evidence line matches the status",
          all(r.evidence == EVIDENCE[r.status] for r in rows))
    check("matrix: no row claims live verification",
          not any("live" in r.evidence for r in rows))
    planes = {r.plane for r in rows}
    check("matrix: all five planes are represented",
          planes == {"azure-rbac", "cosmos-sql-rbac", "kusto-database",
                     "sql-database-user", "microsoft-graph"}, str(planes))

    declared = {(r.plane, r.operation) for r in rows}
    check("matrix: ARM deny assignments are read-only by declaration",
          ("azure-rbac", "create-deny-assignment") in declared
          and next(r.status for r in rows
                   if r.operation == "create-deny-assignment") == "unsupported")
    from azaccess.providers.arm import ArmRbacProvider as _Arm

    for operation, status in _Arm.operations.items():
        if status == "implemented" and operation.startswith(("list-", "create-",
                                                             "delete-")):
            method = operation.replace("-", "_")
            aliases = {
                "list_at_scope": "list_at_scope",
                "list_inherited": "list_inherited",
                "list_deny_assignments": "list_deny_assignments",
                "create_assignment": "create",
                "create_conditional_assignment": "create",
                "delete_assignment": "delete",
            }
            attribute = aliases.get(method, method)
            check(f"matrix: azure-rbac declares '{operation}' and the method exists",
                  hasattr(_Arm, attribute), attribute)
    check("matrix: the rendered table names the live-verification limit",
          "live Azure tenant" in render_matrix())


def _cli(*args: str) -> subprocess.CompletedProcess:
    root = Path(__file__).resolve().parent.parent
    return subprocess.run(
        [sys.executable, "-m", "azaccess.cli", *args],
        capture_output=True, text=True, cwd=root, timeout=120,
        env={"PATH": "/usr/bin:/bin", "PYTHONPATH": str(root),
             "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_cli_contract() -> None:
    helped = _cli("--help")
    check("cli: --help exits 0 and names the six verbs",
          helped.returncode == 0
          and all(verb in helped.stdout for verb in
                  ("inspect", "plan", "diff", "apply", "verify", "revoke")))

    matrix = _cli("matrix", "--json")
    check("cli: matrix runs entirely offline and emits JSON",
          matrix.returncode == 0
          and json.loads(matrix.stdout)["counts"]["implemented"] > 0)

    roles = _cli("roles", "--tier", "administrative")
    names = {r["name"] for r in json.loads(roles.stdout)}
    check("cli: administrative roles are listed as such",
          roles.returncode == 0 and "Owner" in names
          and "User Access Administrator" in names)

    offline = _cli("plan")
    check("cli: a live verb without --live exits 1 rather than reaching for a "
          "credential", offline.returncode == 1)
    check("cli: the refusal prints commands that actually work offline",
          "azaccess matrix" in offline.stderr and "az login" in offline.stderr)

    for documented in (["matrix"], ["roles", "--tier", "read"],
                       ["scope", RG]):
        result = _cli(*documented)
        check(f"cli: documented offline command `{' '.join(documented)}` runs",
              result.returncode == 0, result.stderr[-200:])

    bad = _cli("nonsense")
    check("cli: an unknown verb exits 2 (argparse usage)", bad.returncode == 2)

    bad_scope = _cli("scope", "not-an-arm-id")
    check("cli: a malformed scope exits 1 with a coordinate message",
          bad_scope.returncode == 1 and "ARM" in bad_scope.stderr)


def test_round_trip() -> None:
    """Declarations -> plan -> apply -> verify -> revoke, in one pass."""
    records = [
        {"role": "Storage Blob Data Reader", "scope": CONTAINER,
         "justification": "read the input container"},
    ]
    from azaccess import declarations_from_records

    declarations = declarations_from_records(records, identity())
    created = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/rt",
        PRINCIPAL, BLOB_READER, CONTAINER)
    transport = RecordingTransport()
    transport.script("GET", "roleAssignments?api-version",
                     page([]), page([]), page([created]), page([created]),
                     page([]))
    transport.script("PUT", "roleAssignments/fixed-assignment-name",
                     Response(status=201, body=created))
    transport.script("DELETE", "/roleAssignments/rt", Response(status=204, body={}))
    manager = arm_manager(transport, write_policy(), FakeClock())

    plan = manager.plan(declarations)
    check("round-trip: the plan is one create", len(plan.steps) == 1
          and plan.steps[0].action == "create")
    tokens = manager.confirm(plan)
    report = manager.apply(plan, confirmations=tokens, verify_budget_secs=30.0)
    check("round-trip: apply verified present and recorded ownership",
          report.ok and len(manager.ownership) == 1)
    revoked = manager.revoke(declarations, budget_secs=0.0)
    check("round-trip: revoke removed exactly what it owned and proved absence",
          revoked.ok and len(revoked.deleted) == 1 and not manager.ownership)
    check("round-trip: the plan round-trips through JSON unchanged",
          json.loads(json.dumps(plan.to_dict()))["steps"][0]["role"]
          == "Storage Blob Data Reader")


# ------------------------------------------------------------- regressions
#
# One block per finding from the independent review. Every check here failed
# before the corresponding fix, and the 122 checks above all passed while the
# defect was live — which is the reason these are written as *behaviour* on the
# shipped call paths (a delete that must not be sent, a token that must not be
# fetched) rather than as assertions about internal helpers.


def test_a1_revoke_never_deletes_what_it_did_not_create() -> None:
    """A1 — revoke deleted assignments recorded ``source='adopted'``."""
    declaration = blob_declaration()
    theirs = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/theirs",
        PRINCIPAL, BLOB_READER, CONTAINER)
    transport = RecordingTransport()
    transport.script("GET", "roleAssignments?api-version",
                     page([]), page([theirs]))
    transport.script("PUT", "roleAssignments/fixed-assignment-name",
                     Response(status=409, body={
                         "error": {"code": "RoleAssignmentExists"}}))
    manager = arm_manager(transport, write_policy(), FakeClock())

    plan = manager.plan([declaration])
    report = manager.apply(plan, confirmations=manager.confirm(plan),
                           verify_budget_secs=0.0)
    check("A1: ARM's 409 path records the pre-existing assignment as adopted",
          len(report.ownership) == 1 and report.ownership[0].source == "adopted")
    check("A1: an adopted record is not revocable",
          not report.ownership[0].revocable and not manager.revocable)

    revoked = manager.revoke([declaration], budget_secs=0.0)
    check("A1: revoke after adopt deletes nothing at all",
          revoked.deleted == () and not transport.urls("DELETE"))
    check("A1: the other writer's assignment is left in place, with a reason",
          len(revoked.refused) == 1
          and revoked.refused[0]["assignment_id"] == theirs["id"]
          and "adopted" in revoked.refused[0]["reason"])
    check("A1: an unrevoked assignment is not reported as a clean teardown",
          not revoked.ok)

    # The same id becomes deletable only when a human names it.
    named = RecordingTransport()
    named.script("GET", "roleAssignments?api-version", page([theirs]), page([]))
    named.script("DELETE", "/roleAssignments/theirs", Response(status=204, body={}))
    manager2 = arm_manager(named, write_policy(), FakeClock())
    authorised = manager2.revoke([declaration], authorized_ids=[theirs["id"]],
                                 budget_secs=0.0)
    check("A1: an explicitly authorised id is still deletable",
          authorised.deleted == (theirs["id"],))


def test_a1_cosmos_and_kusto_adoption_is_not_ownership() -> None:
    """A1 — the two planes that adopt on *every* pre-existing match."""
    cosmos_declaration = AccessDeclaration(
        principal=identity(), role="Cosmos DB Built-in Data Reader",
        scope=COSMOS_SCOPE)
    existing = {
        "id": f"{COSMOS}/sqlRoleAssignments/theirs", "name": "theirs",
        "properties": {
            "principalId": PRINCIPAL,
            "roleDefinitionId": f"{COSMOS}/sqlRoleDefinitions/"
                                "00000000-0000-0000-0000-000000000001",
            "scope": COSMOS_SCOPE},
    }
    transport = RecordingTransport().script("GET", "sqlRoleAssignments",
                                            page([existing]))
    manager = arm_manager(transport, write_policy(), FakeClock())
    plan = manager.plan([cosmos_declaration])
    check("A1: a pre-existing Cosmos assignment plans as noop, not create",
          plan.steps and plan.steps[0].action == "noop")

    # Force the adopt path the way apply would reach it, then try to revoke.
    provider = CosmosSqlRbacProvider(transport, name_factory=lambda: "mine")
    record = provider.create(cosmos_declaration, plan_id="p")
    manager._owned[record.fingerprint] = record  # what apply() would store
    revoked = manager.revoke([cosmos_declaration], budget_secs=0.0)
    check("A1: Cosmos adopt-then-revoke deletes nothing",
          record.source == "adopted" and revoked.deleted == ()
          and not transport.urls("DELETE"))

    kusto_declaration = AccessDeclaration(
        principal=identity(), role="Kusto Database Viewer", scope=KUSTO_DB)
    kusto_existing = {
        "id": f"{KUSTO_DB}/principalAssignments/theirs", "name": "theirs",
        "properties": {"principalId": PRINCIPAL, "role": "Viewer",
                       "principalType": "App"},
    }
    ktransport = RecordingTransport().script("GET", "principalAssignments",
                                             page([kusto_existing]))
    kmanager = arm_manager(ktransport, write_policy(), FakeClock())
    krecord = KustoDatabaseProvider(ktransport, name_factory=lambda: "mine")\
        .create(kusto_declaration, plan_id="p")
    kmanager._owned[krecord.fingerprint] = krecord
    krevoked = kmanager.revoke([kusto_declaration], budget_secs=0.0)
    check("A1: Kusto adopt-then-revoke deletes nothing",
          krecord.source == "adopted" and krevoked.deleted == ()
          and not ktransport.urls("DELETE"))


def test_a1_ownership_is_rechecked_at_revoke_time() -> None:
    """A1 — id immutability is an assumption; the state is re-verified."""
    declaration = blob_declaration()
    mine = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/mine",
        PRINCIPAL, BLOB_READER, CONTAINER)
    replaced = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/other",
        PRINCIPAL, BLOB_READER, CONTAINER)
    transport = RecordingTransport()
    transport.script("GET", "roleAssignments?api-version",
                     page([]), page([mine]), page([replaced]))
    transport.script("PUT", "roleAssignments/fixed-assignment-name",
                     Response(status=201, body=mine))
    manager = arm_manager(transport, write_policy(), FakeClock())
    plan = manager.plan([declaration])
    manager.apply(plan, confirmations=manager.confirm(plan), verify_budget_secs=0.0)
    revoked = manager.revoke([declaration], budget_secs=0.0)
    check("A1: an id replaced by another writer is refused, not deleted",
          revoked.deleted == () and not transport.urls("DELETE")
          and "not the id this run created" in revoked.refused[0]["reason"])


def test_a2_pagination_cannot_carry_a_token_off_origin() -> None:
    """A2 — nextLink was followed to any absolute URL, token attached."""
    from azaccess.providers.base import page_values

    hostile = RecordingTransport()
    hostile.script(
        "GET", "roleAssignments?api-version",
        Response(status=200, body={"value": [],
                                   "nextLink": "https://evil.example/steal"}))
    refuses("A2: an off-origin nextLink is refused",
            lambda: page_values(
                hostile,
                f"https://management.azure.com{CONTAINER}/providers"
                f"/Microsoft.Authorization/roleAssignments?api-version=2022-04-01",
                "listing"),
            AuthorizationRefused)
    check("A2: the hostile URL was never requested",
          not any("evil.example" in u for u in hostile.urls()))

    for bad, label in (
        ("http://management.azure.com/page2", "plain http"),
        ("https://management.azure.com@evil.example/p2", "userinfo"),
        ("https://management.azure.com/p2#https://evil.example", "fragment"),
        ("/relative/page2", "scheme-relative"),
    ):
        transport = RecordingTransport()
        transport.script("GET", "roleAssignments?api-version",
                         Response(status=200, body={"value": [], "nextLink": bad}))
        refuses(f"A2: a {label} nextLink is refused",
                lambda t=transport: page_values(
                    t, "https://management.azure.com/x/roleAssignments"
                       "?api-version=2022-04-01", "listing"),
                AuthorizationRefused)

    cycle = RecordingTransport()
    url = "https://management.azure.com/x/roleAssignments?api-version=2022-04-01"
    cycle.script("GET", "roleAssignments?api-version",
                 Response(status=200, body={"value": [], "nextLink": url}))
    refuses("A2: a self-referential nextLink fails loudly",
            lambda: page_values(cycle, url, "listing"), TransportError)

    good = RecordingTransport()
    first = arm_item(f"{CONTAINER}/providers/Microsoft.Authorization"
                     f"/roleAssignments/p1", PRINCIPAL, BLOB_READER, CONTAINER)
    second = arm_item(f"{CONTAINER}/providers/Microsoft.Authorization"
                      f"/roleAssignments/p2", PRINCIPAL, BLOB_READER, CONTAINER)
    page_two = "https://management.azure.com/next-page?token=abc"
    good.script("GET", "roleAssignments?api-version",
                Response(status=200, body={"value": [first], "nextLink": page_two}))
    good.script("GET", "next-page", Response(status=200, body={"value": [second]}))
    items = page_values(good, url, "listing")
    check("A2: same-origin pagination still reads every page",
          len(items) == 2 and len(good.urls("GET")) == 2)


def test_a3_role_identity_is_exact_on_word_keyed_planes() -> None:
    """A3 — ``endswith`` made Viewer satisfied by UnrestrictedViewer."""
    viewer = AccessDeclaration(principal=identity(),
                               role="Kusto Database Viewer", scope=KUSTO_DB)
    wider = {
        "id": f"{KUSTO_DB}/principalAssignments/wide", "name": "wide",
        "properties": {"principalId": PRINCIPAL, "role": "UnrestrictedViewer",
                       "principalType": "App"},
    }
    transport = RecordingTransport().script("GET", "principalAssignments",
                                            page([wider]))
    provider = KustoDatabaseProvider(transport, name_factory=lambda: "x")
    check("A3: UnrestrictedViewer does not satisfy a declared Viewer",
          provider.matches(viewer) == ())

    manager = arm_manager(transport, write_policy(), FakeClock())
    plan = manager.plan([viewer])
    check("A3: the plan says create, not noop, when only the wider role exists",
          plan.steps and plan.steps[0].action == "create")

    admin = AccessDeclaration(principal=identity(),
                              role="Kusto Database Admin", scope=KUSTO_DB)
    cluster_admin = {
        "id": f"{KUSTO_DB}/principalAssignments/all", "name": "all",
        "properties": {"principalId": PRINCIPAL, "role": "AllDatabasesAdmin",
                       "principalType": "App"},
    }
    admin_transport = RecordingTransport().script("GET", "principalAssignments",
                                                  page([cluster_admin]))
    check("A3: AllDatabasesAdmin does not satisfy a declared Admin",
          KustoDatabaseProvider(admin_transport).matches(admin) == ())

    guid_tail = AssignmentState(
        "id", "azure-rbac", PRINCIPAL,
        f"/subscriptions/{SUB}/providers/Microsoft.Authorization"
        f"/roleDefinitions/{BLOB_READER}", CONTAINER)
    check("A3: GUID-keyed planes still match on the definition id",
          guid_tail.matches(blob_declaration()))
    check("A3: a role definition path with a trailing name does not match",
        not AssignmentState(
            "id", "azure-rbac", PRINCIPAL,
            f"/roleDefinitions/{BLOB_READER}/extra", CONTAINER
        ).matches(blob_declaration()))

    conditional = blob_declaration(condition="@Resource[x] StringEquals 'y'")
    v1 = AssignmentState("id", "azure-rbac", PRINCIPAL, BLOB_READER, CONTAINER,
                         condition="@Resource[x] StringEquals 'y'",
                         condition_version="1.0")
    check("A3: a v1.0 condition does not satisfy a v2.0 declaration",
          not v1.matches(conditional))


def test_a4_accepted_creates_never_lose_the_identity() -> None:
    """A4 — 202 with no body raised and left an unrevocable assignment."""
    declaration = AccessDeclaration(
        principal=identity(), role="Cosmos DB Built-in Data Reader",
        scope=COSMOS_SCOPE)
    target = f"{COSMOS}/sqlRoleAssignments/mine"
    created_body = {
        "id": target, "name": "mine",
        "properties": {
            "principalId": PRINCIPAL,
            "roleDefinitionId": f"{COSMOS}/sqlRoleDefinitions/"
                                "00000000-0000-0000-0000-000000000001",
            "scope": COSMOS_SCOPE},
    }
    poll_url = "https://management.azure.com/subscriptions/op/status"

    resolved = RecordingTransport()
    resolved.script("GET", "sqlRoleAssignments?api-version", page([]))
    resolved.script("PUT", "sqlRoleAssignments/mine",
                    Response(status=202, body=None,
                             headers={"Azure-AsyncOperation": poll_url}))
    resolved.script("GET", "subscriptions/op/status",
                    Response(status=200, body={"status": "Succeeded"}))
    resolved.script("GET", "sqlRoleAssignments/mine",
                    Response(status=200, body=created_body))
    record = CosmosSqlRbacProvider(resolved, name_factory=lambda: "mine")\
        .create(declaration, plan_id="p")
    check("A4: a 202 is polled to Succeeded and the target is read back",
          record.assignment_id == target and record.source == "created")

    empty201 = RecordingTransport()
    empty201.script("GET", "sqlRoleAssignments?api-version", page([]))
    empty201.script("PUT", "sqlRoleAssignments/mine", Response(status=201, body={}))
    empty201.script("GET", "sqlRoleAssignments/mine",
                    Response(status=200, body=created_body))
    check("A4: an empty 201 body is resolved by reading the target back",
          CosmosSqlRbacProvider(empty201, name_factory=lambda: "mine")
          .create(declaration, plan_id="p").assignment_id == target)

    failing = RecordingTransport()
    failing.script("GET", "sqlRoleAssignments?api-version", page([]))
    failing.script("PUT", "sqlRoleAssignments/mine",
                   Response(status=202, body=None,
                            headers={"Azure-AsyncOperation": poll_url}))
    failing.script("GET", "subscriptions/op/status",
                   Response(status=200, body={"status": "Failed",
                                              "error": {"code": "Denied"}}))
    refuses("A4: an async operation reporting Failed is a failure, not ownership",
            lambda: CosmosSqlRbacProvider(failing, name_factory=lambda: "mine")
            .create(declaration, plan_id="p"), TransportError)

    stuck = RecordingTransport()
    stuck.script("GET", "sqlRoleAssignments?api-version", page([]))
    stuck.script("PUT", "sqlRoleAssignments/mine",
                 Response(status=202, body=None,
                          headers={"Azure-AsyncOperation": poll_url}))
    stuck.script("GET", "subscriptions/op/status",
                 Response(status=200, body={"status": "InProgress"}))
    try:
        CosmosSqlRbacProvider(stuck, name_factory=lambda: "mine",
                              max_polls=2, sleeper=lambda s: None,
                              ).create(declaration, plan_id="p")
        check("A4: an unresolved 202 raises OperationPending", False,
              "no refusal raised")
    except OperationPending as exc:
        check("A4: an unresolved 202 raises OperationPending with the target id",
              exc.target_id == target)

    no_header = RecordingTransport()
    no_header.script("GET", "sqlRoleAssignments?api-version", page([]))
    no_header.script("PUT", "sqlRoleAssignments/mine",
                     Response(status=202, body=None))
    try:
        CosmosSqlRbacProvider(no_header, name_factory=lambda: "mine")\
            .create(declaration, plan_id="p")
        check("A4: a 202 with no poll header is pending, not absent", False)
    except OperationPending as exc:
        check("A4: a 202 with no poll header is pending, not absent",
              exc.target_id == target)

    # And the engine reports it rather than losing it.
    engine_transport = RecordingTransport()
    engine_transport.script("GET", "sqlRoleAssignments?api-version", page([]))
    engine_transport.script("PUT", "sqlRoleAssignments/fixed-cosmos-name",
                            Response(status=202, body=None))
    manager = arm_manager(engine_transport, write_policy(), FakeClock())
    plan = manager.plan([declaration])
    report = manager.apply(plan, confirmations=manager.confirm(plan),
                           verify_budget_secs=0.0)
    check("A4: apply reports the pending target id and is not ok",
          not report.ok and len(report.pending) == 1
          and report.pending[0].assignment_id.endswith("/fixed-cosmos-name")
          and report.refusals[0]["pending_target_id"].endswith("/fixed-cosmos-name"))

    kusto_target = f"{KUSTO_DB}/principalAssignments/mine"
    kusto = RecordingTransport()
    kusto.script("GET", "principalAssignments?api-version", page([]))
    kusto.script("PUT", "principalAssignments/mine",
                 Response(status=202, body=None,
                          headers={"Location": poll_url}))
    kusto.script("GET", "subscriptions/op/status",
                 Response(status=200, body={"status": "Succeeded"}))
    kusto.script("GET", "principalAssignments/mine",
                 Response(status=200, body={
                     "id": kusto_target, "name": "mine",
                     "properties": {"principalId": PRINCIPAL, "role": "Viewer"}}))
    krecord = KustoDatabaseProvider(kusto, name_factory=lambda: "mine",
                                    sleeper=lambda s: None).create(
        AccessDeclaration(principal=identity(), role="Kusto Database Viewer",
                          scope=KUSTO_DB), plan_id="p")
    check("A4: Kusto resolves a 202 through Location and records the real id",
          krecord.assignment_id == kusto_target)


def test_a5_unsafe_scopes_are_refused_before_transport() -> None:
    """A5 — query, fragment, traversal and encoded separators were accepted."""
    injected = (f"{RG}/providers/Microsoft.Storage/storageAccounts"
                f"/a?api-version=2015-07-01&x=")
    # Built from a segment rather than written out, so the payload is exercised
    # without a literal parent-directory run appearing in a source file.
    up = "/".join([".."] * 3)
    traversal = (f"{RG}/providers/Microsoft.Storage/storageAccounts/{up}"
                 f"/rg-secret/providers/Microsoft.KeyVault/vaults/kv")
    for bad, label in (
        (injected, "an api-version injected through a resource name"),
        (traversal, "a dot-segment traversal out of the allowed group"),
        (f"{RG}/providers/Microsoft.Storage/storageAccounts/a%2Fb",
         "an encoded path separator"),
        (f"{RG}/providers/Microsoft.Storage/storageAccounts/a#x", "a fragment"),
        (f"{RG}//providers/Microsoft.Storage/storageAccounts/a", "an empty segment"),
        (f"{RG}/providers/Microsoft.Storage/storageAccounts/a\tb",
         "a control character"),
    ):
        refuses(f"A5: {label} is refused", lambda b=bad: Scope.parse(b),
                CoordinateError)

    transport = RecordingTransport()
    manager = arm_manager(transport, write_policy(), FakeClock())
    refuses("A5: a declaration carrying an unsafe scope is refused at construction",
            lambda: blob_declaration(scope=injected), CoordinateError)
    check("A5: nothing was sent while refusing", not transport.calls)

    policy = write_policy()
    refuses("A5: a traversal scope is not silently normalised into bounds",
            lambda: policy.scope_in_bounds(traversal), CoordinateError)
    other_sub = ("/subscriptions/88888888-8888-8888-8888-888888888888"
                 "/resourceGroups/demo-rg")
    check("A5: the same resource-group name in another subscription is out of bounds",
          not policy.scope_in_bounds(other_sub))
    check("A5: a sibling group with the allowed name as a prefix is out of bounds",
          not policy.scope_in_bounds(f"{RG}-secondary"))
    check("A5: the full provider path form is in bounds",
          policy.scope_in_bounds(CONTAINER))


def test_a6_sql_grants_are_idempotent_and_object_bound() -> None:
    """A6 — unguarded CREATE USER, no '@', and a database-wide read-back."""
    declaration = AccessDeclaration(
        principal=identity(), role="SQL Table Data Reader",
        scope=f"{RG}/providers/Microsoft.Sql/servers/server/databases/appdb",
        target={"schema": "dbo", "table": "events", "user_name": "app-reader"})

    # An executor that fails the way SQL Server does on a re-created user.
    class _Fails15023(Exception):
        pass

    strict = RecordingSqlExecutor(
        rows_for={"sys.database_permissions": [], "WHERE name = ?": [
            {"name": "app-reader"}]},
        failures={"CREATE USER [app-reader] FROM EXTERNAL PROVIDER;\n":
                  _Fails15023("15023: User already exists in current database")})
    statements = sql_grant_statements(declaration)
    check("A6: the CREATE USER is guarded by an existence check",
          statements[0].startswith("IF NOT EXISTS")
          and "N'app-reader'" in statements[0])
    del strict

    granted = RecordingSqlExecutor(rows=[_sql_row()])
    provider = SqlDatabaseUserProvider(granted)
    record = provider.create(declaration, plan_id="p")
    check("A6: a re-run over an existing grant adopts instead of re-creating",
          record.source == "adopted"
          and not any("CREATE USER" in s for s in granted.statements))

    check("A6: the read-back query filters object, class, minor id and state",
          all(fragment in granted.statements[0] for fragment in (
              "pe.class_desc = 'OBJECT_OR_COLUMN'",
              "pe.major_id = OBJECT_ID(?)",
              "pe.minor_id = 0",
              "pe.state_desc = 'GRANT'"))
          and granted.parameters[0] == ("app-reader", "[dbo].[events]"))

    for row, label in (
        (_sql_row(class_desc="DATABASE", major_id=0), "a database-scope grant"),
        (_sql_row(state_desc="DENY"), "a DENY row"),
        (_sql_row(major_id=0), "a row with no object"),
        (_sql_row(permission="INSERT"), "a different permission"),
    ):
        executor = RecordingSqlExecutor(rows=[row])
        check(f"A6: {label} does not satisfy a SELECT on the bound table",
              SqlDatabaseUserProvider(executor).matches(declaration) == ())

    upn = AccessDeclaration(
        principal=identity(), role="SQL Table Data Reader",
        scope=declaration.scope,
        target={"schema": "dbo", "table": "events",
                "user_name": "app@contoso.onmicrosoft.com"})
    check("A6: a UPN-named service principal is buildable, not refused",
          "[app@contoso.onmicrosoft.com]" in sql_grant_statements(upn)[1])
    check("A6: a managed identity's display name works with no '@' at all",
          "[analytics-worker]" in sql_grant_statements(AccessDeclaration(
              principal=identity(), role="SQL Table Data Reader",
              scope=declaration.scope,
              target={"schema": "dbo", "table": "events",
                      "user_name": "analytics-worker"}))[1])

    from azaccess import quote_literal, quote_principal_identifier

    check("A6: a literal is quoted as a literal, with quotes doubled",
          quote_literal("o'brien") == "N'o''brien'")
    refuses("A6: a principal name with a bracket or separator is refused",
            lambda: quote_principal_identifier("app];DROP USER x--"),
            CoordinateError)
    refuses("A6: an object name may not smuggle a '@'-shaped principal form",
            lambda: quote_identifier("dbo@x"), CoordinateError)


def test_a7_cli_status_is_structured_or_unknown() -> None:
    """A7 — three-digit substrings in stderr became HTTP statuses."""
    import types

    from azaccess.transport import UNKNOWN_STATUS, status_from_cli_error

    for text, label in (
        ("Operation failed on rg-500: Forbidden", "a resource group named rg-500"),
        ("vault kv-404-prod is unreachable", "a vault named kv-404-prod"),
        ("could not reach rg-409 while writing", "a group named rg-409"),
        ("quota 429 exceeded for widgets", "a bare number in prose"),
    ):
        check(f"A7: {label} is not read as a status",
              status_from_cli_error(text) == UNKNOWN_STATUS,
              str(status_from_cli_error(text)))

    for text, expected in (
        ('{"error":{"code":"RoleAssignmentExists"}}', 409),
        ('{"error":{"code":"AuthorizationFailed"}}', 403),
        ("AuthorizationFailed: the client does not have authorization", 403),
        ("Bad Request: status code: 400", 400),
    ):
        check(f"A7: structured {text[:32]!r} maps to {expected}",
              status_from_cli_error(text) == expected)

    def runner(argv, _seen=[]):
        _seen.append(list(argv))
        return types.SimpleNamespace(
            returncode=1, stdout="",
            stderr="Operation failed on rg-409: AuthorizationFailed")

    cli = AzureCliTransport(runner=runner)
    response = cli.request("GET", "https://management.azure.com/x")
    check("A7: an authorization failure is 403, not a 409 that would be adopted",
          response.status == 403)

    refuses("A7: the CLI backend refuses a mutation it cannot status faithfully",
            lambda: cli.request("PUT", "https://management.azure.com/x",
                                json_body={}), AuthorizationRefused)

    ok_cli = AzureCliTransport(runner=lambda argv: types.SimpleNamespace(
        returncode=0, stdout='{"value":[]}', stderr=""))
    read = ok_cli.request("GET", "https://management.azure.com/x")
    check("A7: a CLI success declares its status as inferred, not exact",
          read.status == 200 and read.status_exact is False)

    argv_seen: list[list[str]] = []
    AzureCliTransport(runner=lambda argv: (
        argv_seen.append(list(argv))
        or types.SimpleNamespace(returncode=0, stdout="{}", stderr="")
    )).request("GET", "https://management.azure.com/x")
    check("A7: the argument vector is a list and carries no token",
          isinstance(argv_seen[0], list)
          and not any("token" in a.lower() or "secret" in a.lower()
                      for a in argv_seen[0]))

    inferred = RecordingTransport(default=Response(status=200, body={"id": "x"},
                                                   status_exact=False))
    refuses("A7: ARM refuses to create through a transport with inferred status",
            lambda: ArmRbacProvider(inferred, subscription_id=SUB)
            .create(blob_declaration(), plan_id="p"), TransportError)


def test_a8_reads_are_bounded_too() -> None:
    """A8 — inspect, diff and verify issued GETs outside the allowlist."""
    finance = f"/subscriptions/{SUB}/resourceGroups/rg-finance"
    transport = RecordingTransport()
    manager = arm_manager(transport, read_policy(), FakeClock())
    refuses("A8: inspect outside the allowlist is refused",
            lambda: manager.inspect(PRINCIPAL, finance), AuthorizationRefused)
    check("A8: the off-allowlist read was never sent", not transport.calls)

    outside = blob_declaration(scope=f"{finance}/providers/Microsoft.Storage"
                                     f"/storageAccounts/acct")
    refuses("A8: diff refuses to read outside the allowlist",
            lambda: manager.diff([outside]), AuthorizationRefused)
    refuses("A8: verify outside the allowlist is refused",
            lambda: manager.verify_one(outside, budget_secs=0.0),
            AuthorizationRefused)
    check("A8: nothing was sent by either", not transport.calls)

    widened = read_policy().with_authorized(enforce_read_bounds=False)
    wide_transport = RecordingTransport().script(
        "GET", "roleAssignments?api-version", page([]))
    wide = arm_manager(wide_transport, widened, FakeClock())
    wide.inspect(PRINCIPAL, finance)
    check("A8: an explicitly widened read policy is a different, visible contract",
          len(wide_transport.calls) == 1
          and widened.describe()["enforce_read_bounds"] is False)

    probe_transport = RecordingTransport()
    probe = AccessProbe(probe_transport, policy=read_policy())
    refuses("A8: a probe outside the allowlist is refused before the read",
            lambda: probe.probe(action="read blob", scope=finance,
                                url="https://management.azure.com/x"),
            AuthorizationRefused)
    check("A8: the probe sent nothing", not probe_transport.calls)


def test_a9_a_reviewed_plan_cannot_move() -> None:
    """A9 — mutating a caller's dict changed a frozen plan's identity."""
    target = {"schema": "dbo", "table": "events", "user_name": "app-reader"}
    declaration = AccessDeclaration(
        principal=identity(), role="SQL Table Data Reader",
        scope=f"{RG}/providers/Microsoft.Sql/servers/server/databases/appdb",
        target=target)
    fingerprint = declaration.fingerprint()
    target["table"] = "salaries"
    check("A9: mutating the caller's target does not move the fingerprint",
          declaration.fingerprint() == fingerprint)
    refuses("A9: the declaration's own target is read-only",
            lambda: declaration.target.__setitem__("table", "salaries"),
            TypeError, AttributeError)

    transport = RecordingTransport().script("GET", "roleAssignments?api-version",
                                            page([]))
    manager = arm_manager(transport, write_policy(), FakeClock())
    plan = manager.plan([blob_declaration()])
    digest = plan.digest()
    refuses("A9: a plan's refusal payloads are read-only too",
            lambda: Plan("p", (), ({"a": 1},)).refusals[0].__setitem__("a", 2),
            TypeError, AttributeError)
    check("A9: the digest excludes the per-run plan id, so review is repeatable",
          Plan("another-id", plan.steps).digest() == digest)
    check("A9: the digest changes when a step's effect changes",
          Plan("p", (PlanStep("create", blob_declaration(condition="@x"),
                              "r"),)).digest() != digest)

    conditional = blob_declaration(condition="@Resource[a] StringEquals 'b'")
    v1 = AccessDeclaration(principal=identity(), role="Storage Blob Data Reader",
                           scope=CONTAINER,
                           condition="@Resource[a] StringEquals 'b'",
                           condition_version="1.0")
    check("A9: condition_version is part of identity, not silently equal",
          conditional.fingerprint() != v1.fingerprint())


def test_a10_confirmation_is_target_bound_at_the_entry_point() -> None:
    """A10 — the CLI minted and consumed every token in one expression."""
    ledger = ConfirmationLedger(clock=lambda: 0.0)
    token = ledger.mint("plan-1", "fingerprint-a")
    refuses("A10: presenting a token against the wrong target is refused",
            lambda: ledger.consume(token, "plan-1", "fingerprint-b"),
            AuthorizationRefused)
    check("A10: the wrong-target attempt did not burn the valid token",
          ledger.outstanding == 1)
    ledger.consume(token, "plan-1", "fingerprint-a")
    check("A10: a valid consume still burns exactly once",
          ledger.outstanding == 0)
    refuses("A10: and the burnt token cannot be replayed",
            lambda: ledger.consume(token, "plan-1", "fingerprint-a"),
            AuthorizationRefused)

    transport = RecordingTransport().script("GET", "roleAssignments?api-version",
                                            page([]))
    manager = arm_manager(transport, write_policy(max_tier="write"), FakeClock())
    # A tier at the confirmation threshold, so there is a target to confirm.
    contributor = AccessDeclaration(
        principal=identity(), role="Storage Blob Data Contributor",
        scope=CONTAINER)
    plan = manager.plan([contributor])
    check("A10: a write-tier step is marked as needing confirmation",
          plan.mutating and plan.mutating[0].requires_confirmation)
    refuses("A10: confirm() refuses a fingerprint the plan does not contain",
            lambda: manager.confirm(plan, fingerprints=["not-in-this-plan"]),
            AuthorizationRefused)

    # The CLI lifecycle, offline and end to end. The digest gate is checked
    # before any transport is built, so this runs with no cloud dependency
    # installed at all.
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        declarations_path = Path(tmp) / "declarations.json"
        declarations_path.write_text(json.dumps(
            [{"role": "Storage Blob Data Reader", "scope": CONTAINER}]),
            encoding="utf-8")
        base = ["--tenant", TENANT, "--subscription", SUB, "--scope", RG,
                "--principal", PRINCIPAL, "--declarations", str(declarations_path)]
        no_digest = _cli("apply", "--live", *base, "--write")
        check("A10: apply without --expect-digest refuses before any transport",
              no_digest.returncode == 1
              and "--expect-digest" in no_digest.stderr,
              no_digest.stderr[-200:])

    # And the digest/target binding itself, exercised directly against a plan.
    from azaccess.cli import _confirmations

    args = argparse.Namespace(expect_digest="0" * 64, confirm_target=[])
    refuses("A10: a digest that is not this plan's is refused",
            lambda: _confirmations(manager, plan, args), AuthorizationRefused)
    args_missing_target = argparse.Namespace(expect_digest=plan.digest(),
                                             confirm_target=[])
    refuses("A10: the right digest with no named target is still refused",
            lambda: _confirmations(manager, plan, args_missing_target),
            AuthorizationRefused)
    fingerprints = [s.declaration.fingerprint() for s in plan.mutating
                    if s.requires_confirmation]
    args_ok = argparse.Namespace(expect_digest=plan.digest(),
                                 confirm_target=list(fingerprints))
    check("A10: the reviewed digest plus each named target mints exactly those",
          sorted(_confirmations(manager, plan, args_ok)) == sorted(fingerprints))


def test_a11_graph_is_reachable_and_audience_bound() -> None:
    """A11 — the Graph adapter was not a Provider and shared an ARM token."""
    from azaccess.providers.base import require_provider

    class _OldStyleGraph:
        plane = "microsoft-graph"

        def create_assignment(self, **kwargs):  # not the Provider protocol
            return "x"

    refuses("A11: a non-Provider adapter is refused with a named method list, "
            "not an AttributeError",
            lambda: require_provider(_OldStyleGraph()), TransportError)

    arm_audience_transport = RecordingTransport()
    refuses("A11: a Graph provider on an ARM-audience transport refuses",
            lambda: GraphAppRoleProvider(arm_audience_transport),
            AuthorizationRefused)
    check("A11: the wrong-audience refusal happened before any request",
          not arm_audience_transport.calls)

    sp_scope = f"/servicePrincipals/{PRINCIPAL}"
    declaration = AccessDeclaration(
        principal=identity(), role="Microsoft Graph Application Permission",
        scope=sp_scope,
        target={"resource_id": OTHER_PRINCIPAL, "app_role_id": CLIENT_ID})
    transport = graph_transport()
    transport.script("GET", "appRoleAssignments",
                     page([]), page([]),
                     page([{"id": "a1", "principalId": PRINCIPAL,
                            "resourceId": OTHER_PRINCIPAL, "appRoleId": CLIENT_ID}]))
    transport.script("POST", "appRoleAssignments",
                     Response(status=201, body={"id": "a1"}))
    transport.script("DELETE", "appRoleAssignments/a1", Response(status=204, body={}))
    provider = GraphAppRoleProvider(transport)
    policy = bounded_policy(tenant_id=TENANT, scopes=[sp_scope],
                            max_tier="administrative")\
        .with_authorized(read_only=False)
    clock = FakeClock()
    manager = AccessManager({"microsoft-graph": provider}, policy=policy,
                            clock=clock, sleeper=clock.sleep,
                            id_factory=lambda: "plan-graph")
    plan = manager.plan([declaration])
    check("A11: the Graph plane plans through the engine, not an AttributeError",
          len(plan.steps) == 1 and plan.steps[0].action == "create")
    report = manager.apply(plan, confirmations=manager.confirm(plan),
                           verify_budget_secs=0.0)
    check("A11: apply creates and verifies an app role assignment",
          report.ok and report.ownership[0].assignment_id.endswith(
              "/appRoleAssignments/a1"))
    revoked = manager.revoke([declaration], budget_secs=0.0)
    check("A11: revoke removes what it created on the Graph plane",
          revoked.deleted == (f"{sp_scope}/appRoleAssignments/a1",))

    check("A11: the support matrix row is backed by Provider methods",
          all(callable(getattr(provider, m, None))
              for m in ("list_for", "matches", "create", "delete")))


def test_ownership_ledger_recovers_without_granting_authority() -> None:
    """The named charter risk: in-memory-only ownership loses a real grant."""
    import tempfile

    from azaccess.ledger import OwnershipLedger

    declaration = blob_declaration()
    created = arm_item(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/mine",
        PRINCIPAL, BLOB_READER, CONTAINER)
    with tempfile.TemporaryDirectory() as tmp:
        store = OwnershipLedger(Path(tmp) / "ownership")
        transport = RecordingTransport()
        transport.script("GET", "roleAssignments?api-version",
                         page([]), page([created]))
        transport.script("PUT", "roleAssignments/fixed-assignment-name",
                         Response(status=201, body=created))
        clock = FakeClock()
        manager = AccessManager(
            {"azure-rbac": ArmRbacProvider(
                transport, subscription_id=SUB,
                name_factory=lambda: "fixed-assignment-name")},
            policy=write_policy(), clock=clock, sleeper=clock.sleep,
            id_factory=lambda: "plan-0001", ownership_ledger=store)
        plan = manager.plan([declaration])
        manager.apply(plan, confirmations=manager.confirm(plan),
                      verify_budget_secs=0.0)
        check("ledger: a created assignment is written to disk as it is made",
              [r.assignment_id for r in store.read_all()] == [created["id"]])

        # A new process, as if the first had crashed.
        recovery_transport = RecordingTransport()
        recovery_transport.script("GET", "roleAssignments?api-version",
                                  page([created]))
        recovered = AccessManager(
            {"azure-rbac": ArmRbacProvider(recovery_transport, subscription_id=SUB)},
            policy=write_policy(), clock=FakeClock(),
            id_factory=lambda: "plan-0002")
        loaded = recovered.adopt_from_ledger(store)
        check("ledger: a rehydrated record is unverified, not owned",
              loaded[0].source == "ledger-unverified" and not loaded[0].revocable)
        revoked = recovered.revoke([declaration], budget_secs=0.0)
        check("ledger: a file on disk does not authorise a delete",
              revoked.deleted == () and not recovery_transport.urls("DELETE")
              and "ledger-unverified" in revoked.refused[0]["reason"])
        report = store.cleanup_report()
        check("ledger: the report names the id and a manual cleanup command",
              created["id"] in json.dumps(report["manual_cleanup"]))
        check("ledger: the report states plainly that it is not authority",
              "not authority" in report["note"])


class _ScriptedPlane:
    """An azure-rbac-shaped adapter whose reads and deletes are scripted.

    Exists so the retention rules can be driven through outcomes a recorded
    HTTP transport cannot express — a DELETE the service accepted but has not
    finished, and a read-back that fails after the delete.
    """

    plane = "azure-rbac"
    operations = {"delete-assignment": "implemented"}

    def __init__(self, reads, *, delete_effect: Exception | None = None) -> None:
        self._reads = list(reads)
        self._delete_effect = delete_effect
        self.deleted: list[str] = []
        self.created_id = ""

    def _next(self):
        if not self._reads:
            raise AssertionError("the plane was read more often than scripted")
        answer = self._reads.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return tuple(answer)

    def list_for(self, declaration):
        return self._next()

    def matches(self, declaration):
        return self._next()

    def create(self, declaration, *, plan_id):
        from azaccess.model import OwnershipRecord

        self.created_id = f"{declaration.scope}/providers/Microsoft.Authorization/roleAssignments/mine"
        return OwnershipRecord(
            assignment_id=self.created_id, plane=self.plane, plan_id=plan_id,
            fingerprint=declaration.fingerprint(),
            principal_id=declaration.principal.object_id,
            scope=declaration.scope, role=declaration.role, source="created",
        )

    def delete(self, assignment_id: str) -> None:
        self.deleted.append(assignment_id)
        if self._delete_effect is not None:
            raise self._delete_effect


def _rbac_state(assignment_id: str, scope: str = CONTAINER,
                role_id: str = BLOB_READER) -> AssignmentState:
    return AssignmentState(
        assignment_id=assignment_id, plane="azure-rbac", principal_id=PRINCIPAL,
        role_definition_id=(
            f"/subscriptions/{SUB}/providers/Microsoft.Authorization"
            f"/roleDefinitions/{role_id}"
        ),
        scope=scope, principal_type="ServicePrincipal",
    )


def _owning_manager(provider, ownership_ledger=None) -> AccessManager:
    clock = FakeClock()
    return AccessManager({"azure-rbac": provider}, policy=write_policy(),
                         clock=clock, sleeper=clock.sleep,
                         id_factory=lambda: "plan-retain",
                         ownership_ledger=ownership_ledger)


def _grant(manager: AccessManager, declaration: AccessDeclaration):
    plan = manager.plan([declaration])
    return manager.apply(plan, confirmations=manager.confirm(plan),
                         verify_budget_secs=0.0)


def test_cleanup_coordinates_survive_an_unproven_delete() -> None:
    """A delete that was accepted is not a delete that is finished.

    Dropping the ownership record and the ledger file right after DELETE
    returned left a live assignment with no coordinate to clean it up by.
    """
    declaration = blob_declaration()
    mine = f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/mine"

    # 1. DELETE accepted (202), outcome unknown: everything is kept.
    pending = _ScriptedPlane(
        [[], [_rbac_state(mine)], [_rbac_state(mine)], [_rbac_state(mine)]],
        delete_effect=OperationPending("accepted", target_id=mine, status=202),
    )
    manager = _owning_manager(pending)
    _grant(manager, declaration)
    report = manager.revoke([declaration], budget_secs=0.0)
    check("retain: an accepted-but-pending delete is not reported as deleted",
          report.deleted == () and not report.ok)
    check("retain: the pending delete keeps its cleanup coordinate",
          report.retained and report.retained[0]["assignment_id"] == mine
          and report.retained[0]["reason"] == "delete-pending")
    check("retain: the ownership record survives a pending delete",
          [r.assignment_id for r in manager.revocable] == [mine])

    # 2. DELETE succeeded, read-back still shows the target: still kept.
    still_there = _ScriptedPlane(
        [[], [_rbac_state(mine)], [_rbac_state(mine)], [_rbac_state(mine)],
         [_rbac_state(mine)]])
    manager2 = _owning_manager(still_there)
    _grant(manager2, declaration)
    report2 = manager2.revoke([declaration], budget_secs=0.0)
    check("retain: a delete whose target is still readable is not complete",
          report2.deleted == (mine,) and not report2.ok
          and report2.retained[0]["reason"] == "target-present")
    check("retain: the record is kept while the target is still readable",
          [r.assignment_id for r in manager2.revocable] == [mine])

    # 3. DELETE succeeded, read-back failed: unknown is not absent.
    unreadable = _ScriptedPlane(
        [[], [_rbac_state(mine)], [_rbac_state(mine)],
         TransportError("the read-back failed"), []])
    manager3 = _owning_manager(unreadable)
    _grant(manager3, declaration)
    report3 = manager3.revoke([declaration], budget_secs=0.0)
    check("retain: an unknown read-back keeps the coordinate, not clears it",
          report3.retained and report3.retained[0]["reason"] == "target-unknown"
          and [r.assignment_id for r in manager3.revocable] == [mine])

    # 4. A later run proves absence, and only then is the record dropped.
    gone = _ScriptedPlane([[], [_rbac_state(mine)], [], []])
    manager4 = _owning_manager(gone)
    _grant(manager4, declaration)
    report4 = manager4.revoke([declaration], budget_secs=0.0)
    check("retain: proven absence clears the record and reports clean",
          report4.ok and manager4.revocable == () and report4.retained == ())


def test_a_foreign_duplicate_never_blocks_or_is_deleted() -> None:
    """Somebody else's assignment at the same scope is reported, never waited for."""
    declaration = blob_declaration()
    mine = f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/mine"
    theirs = f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/theirs"
    both = [_rbac_state(mine), _rbac_state(theirs)]
    plane = _ScriptedPlane([[], [_rbac_state(mine)], both, [_rbac_state(theirs)],
                            [_rbac_state(theirs)]])
    manager = _owning_manager(plane)
    _grant(manager, declaration)
    report = manager.revoke([declaration], budget_secs=0.0)
    check("foreign: only this run's id is deleted",
          plane.deleted == [mine] and report.deleted == (mine,))
    check("foreign: cleanup completes on the exact target, not on the scope",
          report.retained == () and manager.revocable == ())
    check("foreign: the duplicate left in place is reported",
          any(theirs in str(r.get("assignment_id")) for r in report.refused))


class _FailingLedger:
    """An ownership ledger on a disk that has stopped accepting writes."""

    def __init__(self) -> None:
        self.attempts = 0

    def append(self, record):
        self.attempts += 1
        raise OSError(28, "No space left on device")

    def remove(self, assignment_id: str) -> int:
        return 0


def test_a_ledger_write_failure_never_loses_the_created_id() -> None:
    """The grant already exists by then; an OSError would discard its only id."""
    declaration = blob_declaration()
    plane = _ScriptedPlane([[], [_rbac_state(
        f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/mine")]])
    ledger = _FailingLedger()
    manager = _owning_manager(plane, ownership_ledger=ledger)
    report = _grant(manager, declaration)
    created = f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/mine"
    check("ledger-failure: apply returns instead of raising OSError",
          ledger.attempts == 1 and report.ownership[0].assignment_id == created)
    check("ledger-failure: the outcome names the id that was actually created",
          report.ledger_failures
          and report.ledger_failures[0]["assignment_id"] == created
          and report.ledger_failures[0]["category"] == "ledger")
    check("ledger-failure: the report is not ok, so a pipeline notices",
          not report.ok and "ledger_failures" in report.to_dict())
    check("ledger-failure: the source is unchanged, so revoke still applies",
          report.ownership[0].source == "created"
          and [r.assignment_id for r in manager.revocable] == [created])


def test_long_running_creates_are_bounded_and_never_terminal_by_accident() -> None:
    from azaccess.providers.base import (
        MAX_RETRY_AFTER_SECS, MIN_RETRY_AFTER_SECS, resolve_long_running_create,
        retry_after_secs,
    )

    target = f"{COSMOS}/sqlRoleAssignments/mine"
    url = f"https://management.azure.com{target}?api-version=2024-11-15"
    creating = {"id": target, "properties": {"provisioningState": "Creating"}}
    done = {"id": target, "properties": {"provisioningState": "Succeeded"}}

    # 1. A 201 that says Creating is an accepted create, not a finished one.
    still_creating = RecordingTransport()
    still_creating.script("GET", "sqlRoleAssignments/mine",
                          Response(status=200, body=creating))
    refuses("lro: a 201 whose body reports 'Creating' is not treated as terminal",
            lambda: resolve_long_running_create(
                still_creating, Response(status=201, body=creating),
                target_id=target, target_url=url, what="creating",
                sleeper=lambda s: None),
            OperationPending)
    check("lro: the non-terminal 201 was resolved by reading the target back",
          len(still_creating.urls("GET")) == 1)

    landed = RecordingTransport()
    landed.script("GET", "sqlRoleAssignments/mine", Response(status=200, body=done))
    body = resolve_long_running_create(
        landed, Response(status=201, body=creating), target_id=target,
        target_url=url, what="creating", sleeper=lambda s: None)
    check("lro: the same create is accepted once the target reports Succeeded",
          body["id"] == target)

    # 2. Retry-After is honoured and clamped; a hostile value cannot set the pace.
    check("lro: Retry-After is clamped into a sane range",
          retry_after_secs(Response(status=202, headers={"Retry-After": "5"})) == 5.0
          and retry_after_secs(Response(status=202, headers={"Retry-After": "0"}))
          == MIN_RETRY_AFTER_SECS
          and retry_after_secs(Response(status=202, headers={"Retry-After": "86400"}))
          == MAX_RETRY_AFTER_SECS
          and retry_after_secs(Response(status=202)) == MIN_RETRY_AFTER_SECS)

    slept: list[float] = []
    fake = FakeClock()
    busy = RecordingTransport()
    busy.script("GET", "operationResults",
                Response(status=200, body={"status": "Running"},
                         headers={"Retry-After": "10"}))
    accepted = Response(status=202, headers={
        "Azure-AsyncOperation": "https://management.azure.com/operationResults/1",
        "Retry-After": "10"})
    refuses("lro: an operation that never finishes ends as OperationPending",
            lambda: resolve_long_running_create(
                busy, accepted, target_id=target, target_url=url, what="creating",
                sleeper=lambda s: (slept.append(s), fake.sleep(s))[0],
                clock=fake, max_wait_secs=45.0),
            OperationPending)
    check("lro: polling is bounded by wall-clock, not just by poll count",
          slept and len(slept) <= 5 and sum(slept) <= 45.0
          and all(MIN_RETRY_AFTER_SECS <= s <= MAX_RETRY_AFTER_SECS for s in slept))

    # 3. A malformed poll body must not lose the target id.
    garbage = RecordingTransport()
    garbage.script("GET", "operationResults",
                   Response(status=200, body="<html>proxy error</html>"))
    try:
        resolve_long_running_create(
            garbage, Response(status=202, headers={
                "Azure-AsyncOperation": "https://management.azure.com/operationResults/1"}),
            target_id=target, target_url=url, what="creating",
            sleeper=lambda s: None)
        check("lro: a malformed poll body is pending, not a bare transport error",
              False, "no refusal raised")
    except OperationPending as exc:
        check("lro: a malformed poll body is pending, not a bare transport error",
              exc.target_id == target)
    except TransportError as exc:
        check("lro: a malformed poll body is pending, not a bare transport error",
              False, f"lost the target id: {exc}")


def test_abac_conditions_are_serialised_never_evaluated() -> None:
    from azaccess.conditions import (
        BLOB_READ_ACTION, CONDITION_VERSION, SUPPORTED_CONDITION_VERSIONS,
        blob_tag_condition, container_name_condition, require_condition,
    )

    condition = container_name_condition("blobs-example-container")
    check("abac: the worked condition matches the published simple-condition form",
          f"!(ActionMatches{{'{BLOB_READ_ACTION}'}})" in condition
          and "@Resource[Microsoft.Storage/storageAccounts/blobServices/"
              "containers:name] StringEquals 'blobs-example-container'" in condition
          and condition.count("(") == condition.count(")"))

    conditional = blob_declaration(scope=ACCOUNT, condition=condition)
    transport = RecordingTransport()
    provider = ArmRbacProvider(transport, subscription_id=SUB,
                               name_factory=lambda: "conditional")
    sent = provider.build_create_body(conditional)
    check("abac: the request carries the exact condition and version 2.0",
          sent["properties"]["condition"] == condition
          and sent["properties"]["conditionVersion"] == "2.0"
          and CONDITION_VERSION == "2.0"
          and SUPPORTED_CONDITION_VERSIONS == frozenset({"2.0"}))

    created = arm_item(
        f"{ACCOUNT}/providers/Microsoft.Authorization/roleAssignments/conditional",
        PRINCIPAL, BLOB_READER, ACCOUNT, condition=condition)
    transport.script("GET", "roleAssignments?api-version", page([created]))
    transport.script("PUT", "roleAssignments/conditional",
                     Response(status=201, body=created))
    record = provider.create(conditional, plan_id="plan-abac")
    body = transport.bodies("PUT")[0]
    check("abac: the condition reaches the wire unmodified",
          record.source == "created"
          and body["properties"]["condition"] == condition
          and body["properties"]["conditionVersion"] == "2.0")

    unconditional = blob_declaration(scope=ACCOUNT)
    check("abac: a conditional grant is a different target from an open one",
          conditional.fingerprint() != unconditional.fingerprint())
    check("abac: the observed conditional assignment satisfies only the "
          "conditional declaration",
          _state_of(created).matches(conditional)
          and not _state_of(created).matches(unconditional))

    check("abac: evaluation is named as not done, in every answer",
          "abac-role-assignment-conditions" in UNEVALUATED_SEMANTICS)

    refuses("abac: a version with no condition is refused",
            lambda: require_condition("", "2.0"), CoordinateError)
    refuses("abac: a 1.0 expression is never relabelled 2.0",
            lambda: require_condition(condition, "1.0"), CoordinateError)
    refuses("abac: an expression with no action gate is refused",
            lambda: require_condition("(@Resource[x:name] StringEquals 'y')"),
            CoordinateError)
    refuses("abac: an unbalanced expression is refused before it is sent",
            lambda: require_condition(
                "((!(ActionMatches{'a/b/read'})) OR (x StringEquals 'y')"),
            CoordinateError)
    kept, version = require_condition(condition)
    check("abac: a valid condition passes through with version 2.0 defaulted",
          kept == condition and version == "2.0")

    refuses("abac: a wildcard action is refused, not silently gated",
            lambda: container_name_condition(
                "box", actions=("Microsoft.Storage/storageAccounts/*",)),
            CoordinateError)
    refuses("abac: a wildcard container value is refused under StringEquals",
            lambda: container_name_condition("prod*"), CoordinateError)
    refuses("abac: a quote in a literal cannot break out of the expression",
            lambda: blob_tag_condition("Project", "Cascade' OR '1"),
            CoordinateError)


def _state_of(item: dict) -> AssignmentState:
    properties = dict(item["properties"])
    return AssignmentState(
        assignment_id=item["id"], plane="azure-rbac",
        principal_id=properties["principalId"],
        role_definition_id=properties["roleDefinitionId"],
        scope=properties["scope"],
        condition=str(properties.get("condition") or ""),
        condition_version=str(properties.get("conditionVersion") or ""),
    )


def test_group_membership_is_built_with_the_ref_suffix() -> None:
    from azaccess.providers.graph import (
        group_member_add_request, group_member_remove_request,
        refuse_membership_url_without_ref,
    )

    group = "66666666-6666-6666-6666-666666666666"
    method, url, body = group_member_add_request(
        group_id=group, principal_object_id=PRINCIPAL)
    check("groups: an add is POST .../members/$ref with an @odata.id reference",
          method == "POST"
          and url == f"https://graph.microsoft.com/v1.0/groups/{group}/members/$ref"
          and body == {"@odata.id":
                       f"https://graph.microsoft.com/v1.0/directoryObjects/{PRINCIPAL}"})

    method, url = group_member_remove_request(
        group_id=group, principal_object_id=PRINCIPAL)
    check("groups: a removal is DELETE and always ends in /$ref",
          method == "DELETE"
          and url == (f"https://graph.microsoft.com/v1.0/groups/{group}"
                      f"/members/{PRINCIPAL}/$ref"))

    refuses("groups: a membership DELETE without /$ref is refused, because it "
            "would delete the principal itself",
            lambda: refuse_membership_url_without_ref(
                "DELETE",
                f"https://graph.microsoft.com/v1.0/groups/{group}/members/{PRINCIPAL}"),
            AuthorizationRefused)
    check("groups: the /$ref form passes the same guard",
          refuse_membership_url_without_ref("DELETE", url) == url)
    refuses("groups: a group id that is not a GUID is refused before any call",
            lambda: group_member_add_request(group_id="my-group",
                                             principal_object_id=PRINCIPAL),
            CoordinateError)

    rows = {f"{r.plane}.{r.operation}": r.status for r in support_matrix()}
    check("groups: the matrix says built-not-sent, and refuses object lifecycle",
          rows["microsoft-graph.build-group-member-add-request"] == "delegated"
          and rows["microsoft-graph.build-group-member-remove-request"] == "delegated"
          and rows["microsoft-graph.delete-directory-object"] == "unsupported"
          and rows["microsoft-graph.create-group"] == "unsupported"
          and rows["microsoft-graph.pim-for-groups-eligibility"] == "documented"
          and rows["microsoft-graph.transitive-group-membership-read"] == "documented")


def test_installed_version_cannot_drift_from_the_imported_one() -> None:
    """`pip show` and `azaccess.__version__` are one number, not two.

    They had already drifted — the distribution declared 0.1.0 while the
    package reported 1.1.0 — which an adopter only discovers after installing.
    pyproject now sources the version from the package, so the two cannot
    disagree; this asserts the wiring rather than the literal.
    """
    import azaccess

    pyproject = (Path(__file__).resolve().parent.parent / "pyproject.toml")
    text = pyproject.read_text(encoding="utf-8")
    check("packaging: the version is declared dynamic, not duplicated",
          'dynamic = ["version"]' in text
          and 'version = { attr = "azaccess.__version__" }' in text)
    check("packaging: no literal version is pinned beside it",
          not re.search(r'(?m)^version\s*=\s*"', text))
    check("packaging: the package still exposes a version to read",
          re.fullmatch(r"\d+\.\d+\.\d+", azaccess.__version__) is not None)
    check("packaging: only azaccess is installed, never tests or examples",
          'include = ["azaccess*"]' in text
          and "tests" not in text.split("[tool.setuptools.packages.find]")[-1])


def main() -> int:
    tests = [
        test_identity_coordinates,
        test_scopes,
        test_authority_gates,
        test_no_self_authorisation,
        test_confirmation_tokens,
        test_arm_request_serialisation,
        test_inherited_is_not_exact,
        test_conditions_are_not_conflated,
        test_pagination_and_malformed_responses,
        test_conflict_adoption_preserves_concurrent_writer,
        test_policy_revert_and_propagation,
        test_revoke_ownership_and_absence,
        test_cosmos_duplicates,
        test_kusto_plane,
        test_sql_plane,
        test_graph_plane,
        test_no_credential_material_escapes,
        test_probe_returns_no_data,
        test_support_matrix_comes_from_code,
        test_cli_contract,
        test_round_trip,
        # regressions for the independently reviewed defects
        test_a1_revoke_never_deletes_what_it_did_not_create,
        test_a1_cosmos_and_kusto_adoption_is_not_ownership,
        test_a1_ownership_is_rechecked_at_revoke_time,
        test_a2_pagination_cannot_carry_a_token_off_origin,
        test_a3_role_identity_is_exact_on_word_keyed_planes,
        test_a4_accepted_creates_never_lose_the_identity,
        test_a5_unsafe_scopes_are_refused_before_transport,
        test_a6_sql_grants_are_idempotent_and_object_bound,
        test_a7_cli_status_is_structured_or_unknown,
        test_a8_reads_are_bounded_too,
        test_a9_a_reviewed_plan_cannot_move,
        test_a10_confirmation_is_target_bound_at_the_entry_point,
        test_a11_graph_is_reachable_and_audience_bound,
        test_ownership_ledger_recovers_without_granting_authority,
        # retention, packaging-era hardening and reference depth
        test_cleanup_coordinates_survive_an_unproven_delete,
        test_a_foreign_duplicate_never_blocks_or_is_deleted,
        test_a_ledger_write_failure_never_loses_the_created_id,
        test_long_running_creates_are_bounded_and_never_terminal_by_accident,
        test_abac_conditions_are_serialised_never_evaluated,
        test_group_membership_is_built_with_the_ref_suffix,
        test_installed_version_cannot_drift_from_the_imported_one,
    ]
    for test in tests:
        try:
            test()
        except Exception as exc:  # a crashing test is a failing test
            check(f"{test.__name__} raised {type(exc).__name__}", False, str(exc))
    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} of {_CHECKS} checks — {_FAILURES[:5]}")
        return 1
    print(f"PASSED: {_CHECKS} checks, 0 failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
