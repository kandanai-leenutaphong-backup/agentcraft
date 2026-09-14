#!/usr/bin/env python3
"""Worked example: the whole lifecycle, offline, with nothing to clean up.

Plan a container-scoped reader grant, apply it, watch the read-back, revoke it,
and prove absence — against a recorded transport that also captures every
request, so the example asserts the *shape of the calls* and not merely that
nothing crashed.

Run it:  python3 examples/plan_apply_verify_revoke.py
"""

from __future__ import annotations

import json

from azaccess import (
    AccessDeclaration,
    AccessManager,
    ArmRbacProvider,
    RecordingTransport,
    Response,
    bounded_policy,
    user_assigned_identity,
)

TENANT = "11111111-1111-1111-1111-111111111111"
SUBSCRIPTION = "22222222-2222-2222-2222-222222222222"
PRINCIPAL = "33333333-3333-3333-3333-333333333333"

RESOURCE_GROUP = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/example-rg"
CONTAINER = (
    f"{RESOURCE_GROUP}/providers/Microsoft.Storage/storageAccounts/example-account"
    f"/blobServices/default/containers/inbox"
)
ASSIGNMENT = (
    f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/example-id"
)


def empty_page() -> Response:
    return Response(status=200, body={"value": []})


def one_page() -> Response:
    return Response(
        status=200,
        body={
            "value": [
                {
                    "id": ASSIGNMENT,
                    "name": "example-id",
                    "properties": {
                        "principalId": PRINCIPAL,
                        "roleDefinitionId": (
                            f"/subscriptions/{SUBSCRIPTION}/providers"
                            f"/Microsoft.Authorization/roleDefinitions"
                            f"/2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"
                        ),
                        "scope": CONTAINER,
                        "principalType": "ServicePrincipal",
                    },
                }
            ]
        },
    )


class Clock:
    """Time advances only when the manager sleeps, so the run is instant."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, secs: float) -> None:
        self.now += secs


def main() -> int:
    transport = RecordingTransport()
    # plan reads twice (exact, then inherited); apply verifies; revoke matches;
    # the last read proves absence.
    transport.script("GET", "roleAssignments?api-version",
                     empty_page(), empty_page(), one_page(), one_page(),
                     empty_page())
    transport.script("PUT", "roleAssignments/",
                     Response(status=201, body=one_page().body["value"][0]))
    transport.script("DELETE", "roleAssignments/example-id",
                     Response(status=204, body={}))

    clock = Clock()
    # Read-only by default. Widening is one visible call, and it names the
    # tier it is widening to.
    policy = bounded_policy(
        tenant_id=TENANT, scopes=[RESOURCE_GROUP], max_tier="read"
    ).with_authorized(read_only=False)

    manager = AccessManager(
        {"azure-rbac": ArmRbacProvider(transport, subscription_id=SUBSCRIPTION)},
        policy=policy, clock=clock, sleeper=clock.sleep,
    )

    identity = user_assigned_identity(
        principal_id=PRINCIPAL, tenant_id=TENANT, display_name="ingest-worker"
    )
    declaration = AccessDeclaration(
        principal=identity,
        role="Storage Blob Data Reader",
        scope=CONTAINER,
        justification="read the inbox container",
    )

    plan = manager.plan([declaration])
    print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
    assert len(plan.steps) == 1, plan.to_dict()
    assert plan.steps[0].action == "create"
    assert not plan.refusals

    report = manager.apply(plan, confirmations=manager.confirm(plan),
                           verify_budget_secs=30.0)
    assert report.ok, report.to_dict()
    assert report.ownership[0].assignment_id == ASSIGNMENT
    assert report.ownership[0].source == "created"
    assert report.verifications[0].status == "present"

    # The request that was actually built — the part worth asserting.
    body = transport.bodies("PUT")[0]["properties"]
    assert body["principalId"] == PRINCIPAL
    assert body["principalType"] == "ServicePrincipal"
    assert body["roleDefinitionId"].endswith("2a2b9908-6ea1-4ae2-8e65-a410df84e7d1")

    revoked = manager.revoke([declaration], budget_secs=0.0)
    assert revoked.ok, revoked.to_dict()
    assert list(revoked.deleted) == [ASSIGNMENT]
    assert revoked.verifications[0].status == "absent"
    assert not manager.ownership

    print("planned, applied, verified present, revoked, verified absent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
