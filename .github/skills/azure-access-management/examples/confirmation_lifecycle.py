#!/usr/bin/env python3
"""confirmation_lifecycle.py — how a mutation gets authorised, offline.

    PYTHONPATH=. python3 examples/confirmation_lifecycle.py

The point of this file is that a confirmation is **target-bound**, and that
being an operator at a terminal is not, by itself, an authorisation. The
shipped CLI used to take ``--confirm`` and then mint and consume a token for
every step in the same expression as ``apply`` — a boolean wearing a security
control's clothes.

What replaces it, and what this script demonstrates end to end against a
recorded transport:

1. ``plan`` produces a ``digest`` over the *effects* — stable across runs,
   because it excludes the per-run ``plan_id``;
2. a human reads the plan and decides;
3. ``apply`` re-plans, refuses unless the freshly computed digest equals the
   one that was reviewed, and mints one token per *named* fingerprint;
4. presenting a token against the wrong target refuses **and leaves the right
   token valid**, so a mistake is not a denial of the approval path.

The equivalent command line is printed at the end.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from azaccess import (  # noqa: E402
    AccessDeclaration,
    AccessManager,
    ArmRbacProvider,
    AuthorizationRefused,
    OwnershipLedger,
    RecordingTransport,
    Response,
    bounded_policy,
    user_assigned_identity,
)

TENANT = "11111111-1111-1111-1111-111111111111"
SUB = "22222222-2222-2222-2222-222222222222"
PRINCIPAL = "33333333-3333-3333-3333-333333333333"
RG = f"/subscriptions/{SUB}/resourceGroups/demo-rg"
CONTAINER = (f"{RG}/providers/Microsoft.Storage/storageAccounts/data-acct"
             f"/blobServices/default/containers/box")
BLOB_WRITER = "ba92f5b4-2d11-453d-a403-e96b0029c9fe"


def main() -> int:
    identity = user_assigned_identity(principal_id=PRINCIPAL, tenant_id=TENANT)
    declaration = AccessDeclaration(
        principal=identity, role="Storage Blob Data Contributor",
        scope=CONTAINER, justification="the canvas writes blobs here",
    )

    created = {
        "id": f"{CONTAINER}/providers/Microsoft.Authorization/roleAssignments/new",
        "name": "new",
        "properties": {
            "principalId": PRINCIPAL,
            "roleDefinitionId": f"/subscriptions/{SUB}/providers"
                                f"/Microsoft.Authorization/roleDefinitions/{BLOB_WRITER}",
            "scope": CONTAINER,
            "principalType": "ServicePrincipal",
        },
    }
    transport = RecordingTransport()
    # Each plan reads twice on this plane: once at the exact scope, once for
    # inherited access. The last scripted page is what the read-back sees.
    empty = Response(status=200, body={"value": []})
    transport.script("GET", "roleAssignments?api-version",
                     empty, empty, empty, empty,
                     Response(status=200, body={"value": [created]}))
    transport.script("PUT", "roleAssignments/new", Response(status=201, body=created))

    # write=True is one visible call, made because a human decided it.
    policy = bounded_policy(tenant_id=TENANT, scopes=[RG], max_tier="write")\
        .with_authorized(read_only=False)

    with tempfile.TemporaryDirectory() as tmp:
        store = OwnershipLedger(Path(tmp) / "ownership")
        manager = AccessManager(
            {"azure-rbac": ArmRbacProvider(transport, subscription_id=SUB,
                                           name_factory=lambda: "new")},
            policy=policy, clock=lambda: 0.0, sleeper=lambda s: None,
            id_factory=lambda: "plan-demo", ownership_ledger=store,
        )

        # 1. plan, and print what a reviewer would read.
        plan = manager.plan([declaration])
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        digest = plan.digest()
        needs_confirmation = plan.to_dict()["confirmation_required"]
        print(f"\ndigest to review: {digest}")
        print(f"targets needing confirmation: {needs_confirmation}\n")

        # 2. the digest is stable, so the thing reviewed is the thing applied.
        assert manager.plan([declaration]).digest() == digest

        # 3. approving nothing is a refusal, not a default.
        try:
            manager.apply(plan, confirmations={}, verify_budget_secs=0.0)
        except AuthorizationRefused:  # pragma: no cover - defensive
            raise SystemExit("apply must not raise; refusals are reported as data")
        unapproved = manager.apply(plan, confirmations={}, verify_budget_secs=0.0)
        assert not unapproved.ok and unapproved.refusals, (
            "a mutating step with no token is refused"
        )
        assert not transport.urls("PUT"), "and nothing was sent"
        print("no token -> refused, nothing sent")

        # 4. a token minted for the wrong target does not confirm this one, and
        #    does not burn the right one either.
        other = AccessDeclaration(principal=identity, role="Storage Blob Data Reader",
                                  scope=CONTAINER)
        tokens = manager.confirm(plan, fingerprints=needs_confirmation)
        wrong = {other.fingerprint(): list(tokens.values())[0]}
        misdirected = manager.apply(plan, confirmations=wrong, verify_budget_secs=0.0)
        assert not misdirected.ok, "a token under the wrong key is not a confirmation"
        print("token bound to a different target -> refused")

        # 5. the right token, named explicitly, applies exactly one step.
        report = manager.apply(plan, confirmations=tokens, verify_budget_secs=0.0)
        assert report.ok, report.to_dict()
        print(f"approved and applied: {report.ownership[0].assignment_id}")
        print(f"ownership recorded on disk: "
              f"{[r.assignment_id for r in store.read_all()]}")

    print(
        "\nthe same thing on the command line:\n"
        "  azaccess plan --live --tenant <tenant> --subscription <sub> \\\n"
        "      --scope <resource-group-id> --principal <object-id> \\\n"
        "      --declarations declarations.json --save-plan plan.json\n"
        "  # read plan.json, then quote its digest and each fingerprint back:\n"
        "  azaccess apply --live --tenant <tenant> --subscription <sub> \\\n"
        "      --scope <resource-group-id> --principal <object-id> \\\n"
        "      --declarations declarations.json --write \\\n"
        "      --expect-digest <digest from plan.json> \\\n"
        "      --confirm-target <fingerprint> \\\n"
        "      --ownership-ledger ./.azaccess-ownership\n"
        "  # if it crashes, the ids are still recoverable:\n"
        "  azaccess ledger --ownership-ledger ./.azaccess-ownership"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
