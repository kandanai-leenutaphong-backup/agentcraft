#!/usr/bin/env python3
"""A worked ABAC condition: built, serialised, compared — never evaluated.

Run it:

    python3 examples/abac_condition.py         # after `pip install <skill folder>`
    PYTHONPATH=. python3 examples/abac_condition.py   # straight from the folder

The scenario is the one Azure's own documentation uses: `Storage Blob Data
Reader` at the storage-account scope, narrowed by a condition so that reading a
blob is only permitted inside one container. Everything here is offline and
asserted; no credential, no network, no tenant.
"""

from __future__ import annotations

from azaccess import (AccessDeclaration, ArmRbacProvider, RecordingTransport,
                      Response, container_name_condition, require_condition,
                      user_assigned_identity)
from azaccess.conditions import BLOB_READ_ACTION
from azaccess.errors import CoordinateError
from azaccess.model import AssignmentState, UNEVALUATED_SEMANTICS

TENANT = "11111111-1111-1111-1111-111111111111"
SUB = "22222222-2222-2222-2222-222222222222"
PRINCIPAL = "33333333-3333-3333-3333-333333333333"
ACCOUNT = (f"/subscriptions/{SUB}/resourceGroups/demo-rg/providers"
           f"/Microsoft.Storage/storageAccounts/dataacct")
BLOB_READER = "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1"


def main() -> int:
    condition = container_name_condition("blobs-example-container")
    print(condition)

    # 1. The expression is the published simple-condition form: an action gate,
    #    then the expression that must hold for that action.
    assert f"!(ActionMatches{{'{BLOB_READ_ACTION}'}})" in condition
    assert ("@Resource[Microsoft.Storage/storageAccounts/blobServices/"
            "containers:name] StringEquals 'blobs-example-container'") in condition

    identity = user_assigned_identity(principal_id=PRINCIPAL, tenant_id=TENANT)
    narrow = AccessDeclaration(principal=identity, role="Storage Blob Data Reader",
                               scope=ACCOUNT, condition=condition)
    wide = AccessDeclaration(principal=identity, role="Storage Blob Data Reader",
                             scope=ACCOUNT)

    # 2. A conditional grant is a different target from the open one. The
    #    fingerprint is what a confirmation token is bound to, so conflating the
    #    two would let a token minted for the narrow grant approve the wide one.
    assert narrow.fingerprint() != wide.fingerprint()
    assert narrow.effective_condition_version == "2.0"

    # 3. The request carries the condition and the version, exactly.
    transport = RecordingTransport()
    provider = ArmRbacProvider(transport, subscription_id=SUB,
                               name_factory=lambda: "conditional")
    created = {
        "id": f"{ACCOUNT}/providers/Microsoft.Authorization/roleAssignments/conditional",
        "name": "conditional",
        "properties": {
            "principalId": PRINCIPAL,
            "roleDefinitionId": (f"/subscriptions/{SUB}/providers/Microsoft."
                                 f"Authorization/roleDefinitions/{BLOB_READER}"),
            "scope": ACCOUNT,
            "condition": condition,
            "conditionVersion": "2.0",
        },
    }
    transport.script("PUT", "roleAssignments/conditional",
                     Response(status=201, body=created))
    provider.create(narrow, plan_id="plan-abac")
    sent = transport.bodies("PUT")[0]["properties"]
    assert sent["condition"] == condition
    assert sent["conditionVersion"] == "2.0"

    # 4. Comparison is textual and exact, in both directions. The conditional
    #    assignment observed at the account does not satisfy a declaration that
    #    asked for unconditional read, and vice versa.
    observed = AssignmentState(
        assignment_id=created["id"], plane="azure-rbac", principal_id=PRINCIPAL,
        role_definition_id=created["properties"]["roleDefinitionId"],
        scope=ACCOUNT, condition=condition, condition_version="2.0")
    assert observed.matches(narrow)
    assert not observed.matches(wide)

    # 5. And the honest part: this package serialises and compares conditions.
    #    It does not evaluate them, and says so in every effective-access answer.
    assert "abac-role-assignment-conditions" in UNEVALUATED_SEMANTICS

    # 6. Shapes that would look narrowing and behave otherwise are refused.
    for bad, why in (
        (lambda: container_name_condition("prod*"),
         "a wildcard under StringEquals matches a container literally named 'prod*'"),
        (lambda: container_name_condition(
            "box", actions=("Microsoft.Storage/storageAccounts/*",)),
         "a wildcard action changes which requests the expression gates"),
        (lambda: require_condition(condition, "1.0"),
         "v1.0 and v2.0 are evaluated by different rules"),
        (lambda: require_condition("(@Resource[x:name] StringEquals 'y')"),
         "an expression with no ActionMatches gate applies to every action"),
    ):
        try:
            bad()
        except CoordinateError as exc:
            print(f"refused ({why}): {str(exc)[:70]}…")
        else:  # pragma: no cover - the assertion is the point
            raise AssertionError(f"expected a refusal: {why}")

    print("\nOK: the condition is built, sent and compared; never evaluated here.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
