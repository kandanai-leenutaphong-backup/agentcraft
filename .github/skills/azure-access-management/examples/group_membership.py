#!/usr/bin/env python3
"""Group-based grants: one role assignment, membership managed in the directory.

Run it:

    python3 examples/group_membership.py         # after `pip install <skill folder>`
    PYTHONPATH=. python3 examples/group_membership.py   # straight from the folder

The pattern this dramatises is the standard least-privilege one: assign the role
to a **group** once, then add and remove principals from that group. The role
assignment stops churning, and the audit question becomes "who is in the group",
which the directory already answers.

The membership calls are **built here and not sent**. Two reasons, both real:

* one of them, spelled slightly wrong, deletes a user instead of removing a
  membership (see below);
* directory writes need Microsoft Graph permissions that an Azure RBAC Owner
  does not have. Azure RBAC and Microsoft Entra are different authorization
  systems; being Owner of the subscription buys nothing in the directory.

Offline and asserted; no credential, no network, no tenant.
"""

from __future__ import annotations

from azaccess import (AccessDeclaration, IdentityRef, group_member_add_request,
                      group_member_remove_request,
                      refuse_membership_url_without_ref, support_matrix)
from azaccess.errors import AuthorizationRefused, CoordinateError

TENANT = "11111111-1111-1111-1111-111111111111"
SUB = "22222222-2222-2222-2222-222222222222"
GROUP = "66666666-6666-6666-6666-666666666666"
MEMBER = "33333333-3333-3333-3333-333333333333"
CONTAINER = (f"/subscriptions/{SUB}/resourceGroups/demo-rg/providers"
             f"/Microsoft.Storage/storageAccounts/dataacct/blobServices/default"
             f"/containers/inbox")


def main() -> int:
    # 1. The grant is made to the group, exactly like any other principal.
    group_principal = IdentityRef(object_id=GROUP, kind="group", tenant_id=TENANT,
                                  display_name="app-readers")
    declaration = AccessDeclaration(principal=group_principal,
                                    role="Storage Blob Data Reader",
                                    scope=CONTAINER)
    assert declaration.principal.principal_type == "Group"
    print(f"grant: {declaration.role} to group {GROUP} at the container scope")

    # 2. Adding a member: POST .../members/$ref, with the member by reference.
    #    A member that is already in the group answers 400 — not 409, and not a
    #    silent success — so "already a member" is an expected outcome.
    method, url, body = group_member_add_request(group_id=GROUP,
                                                 principal_object_id=MEMBER)
    assert method == "POST"
    assert url == f"https://graph.microsoft.com/v1.0/groups/{GROUP}/members/$ref"
    assert body == {
        "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{MEMBER}"
    }
    print(f"add:    {method} {url}\n        {body}")

    # 3. Removing a member: the URL ends in /$ref, and that suffix is the whole
    #    safety property. Without it, an app that may manage the member's object
    #    type deletes the object — the user, not the membership.
    method, url = group_member_remove_request(group_id=GROUP,
                                              principal_object_id=MEMBER)
    assert method == "DELETE" and url.endswith("/$ref")
    assert url == (f"https://graph.microsoft.com/v1.0/groups/{GROUP}"
                   f"/members/{MEMBER}/$ref")
    print(f"remove: {method} {url}")

    unsafe = f"https://graph.microsoft.com/v1.0/groups/{GROUP}/members/{MEMBER}"
    try:
        refuse_membership_url_without_ref("DELETE", unsafe)
    except AuthorizationRefused as exc:
        print(f"refused: {str(exc)[:96]}…")
    else:  # pragma: no cover - the assertion is the point
        raise AssertionError("the unsuffixed membership DELETE must be refused")
    assert refuse_membership_url_without_ref("DELETE", url) == url

    # 4. Coordinates are validated before anything is built, so a display name
    #    or a client id never reaches a URL where it would address something else.
    try:
        group_member_add_request(group_id="app-readers", principal_object_id=MEMBER)
    except CoordinateError as exc:
        print(f"refused: {str(exc)[:96]}…")
    else:  # pragma: no cover
        raise AssertionError("a non-GUID group id must be refused")

    # 5. What the matrix claims about all of this, read from the adapter itself.
    rows = {f"{r.plane}.{r.operation}": r.status for r in support_matrix()}
    assert rows["microsoft-graph.build-group-member-add-request"] == "delegated"
    assert rows["microsoft-graph.build-group-member-remove-request"] == "delegated"
    assert rows["microsoft-graph.delete-directory-object"] == "unsupported"
    assert rows["microsoft-graph.create-group"] == "unsupported"
    assert rows["microsoft-graph.pim-for-groups-eligibility"] == "documented"
    assert rows["microsoft-graph.transitive-group-membership-read"] == "documented"
    print("\nmatrix: membership requests are built and validated here, sent by "
          "the host with a Graph-scoped token that carries GroupMember."
          "ReadWrite.All")

    print("OK: group grant declared, membership calls built, the delete trap refused.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
