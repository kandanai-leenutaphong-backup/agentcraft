#!/usr/bin/env python3
"""Worked example: the migration that looks finished and is not.

An identity holds ``Contributor`` on the whole resource group. The desired
state is one container-scoped reader assignment. Naive tooling asks "can the
identity read the container?", the answer is yes, and the wide assignment
survives the migration untouched.

This example shows the three outcomes kept apart: ``inherited_only`` (the trap),
``excess`` (the wide assignment, reported and never auto-deleted), and
``missing`` (what still has to be created).

Run it:  python3 examples/least_privilege_migration.py
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
CONTRIBUTOR = "b24988ac-6180-42a0-ab88-20f7382dd24c"


def assignment(name: str, role_id: str, scope: str) -> dict:
    return {
        "id": f"{scope}/providers/Microsoft.Authorization/roleAssignments/{name}",
        "name": name,
        "properties": {
            "principalId": PRINCIPAL,
            "roleDefinitionId": (
                f"/subscriptions/{SUBSCRIPTION}/providers/Microsoft.Authorization"
                f"/roleDefinitions/{role_id}"
            ),
            "scope": scope,
            "principalType": "ServicePrincipal",
        },
    }


def main() -> int:
    wide = assignment("wide", CONTRIBUTOR, RESOURCE_GROUP)
    transport = RecordingTransport()
    transport.default = Response(status=200, body={"value": [wide]})

    manager = AccessManager(
        {"azure-rbac": ArmRbacProvider(transport, subscription_id=SUBSCRIPTION)},
        policy=bounded_policy(tenant_id=TENANT, scopes=[RESOURCE_GROUP],
                              max_tier="read"),
    )
    identity = user_assigned_identity(principal_id=PRINCIPAL, tenant_id=TENANT)
    desired = AccessDeclaration(
        principal=identity, role="Storage Blob Data Reader", scope=CONTAINER,
        justification="least privilege replacement for resource-group Contributor",
    )

    report = manager.diff([desired], include_excess_at=[RESOURCE_GROUP])
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True))

    # The identity can read the container today — and the declaration is still
    # unmet, because the access comes from an assignment somewhere else.
    assert not report.satisfied, report.to_dict()
    assert len(report.missing) == 1
    assert report.missing[0].scope == CONTAINER

    # The wide assignment is reported, and this package will not remove it:
    # nothing here created it, so nothing here owns it.
    assert len(report.excess) == 1
    assert report.excess[0].scope == RESOURCE_GROUP
    assert report.excess[0].role_definition_id.endswith(CONTRIBUTOR)

    # And the answer says what it did not evaluate.
    assert "transitive-group-membership" in report.unevaluated
    assert report.completeness in ("exact", "partial")

    # Read-only policy: planning the fix is allowed, applying it is not.
    plan = manager.plan([desired])
    assert not plan.steps and plan.refusals
    assert plan.refusals[0]["category"] == "authorization"

    print("inherited access did not satisfy the declaration; wide assignment "
          "reported, not deleted; plan refused under a read-only policy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
