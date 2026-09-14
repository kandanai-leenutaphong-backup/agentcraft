"""Microsoft Graph — directory-plane grants, which Azure RBAC does not cover.

WHAT LIVES HERE AND WHY IT IS SEPARATE
--------------------------------------
Azure RBAC answers "what may this principal do to Azure resources". It says
nothing about "what may this application do to Microsoft 365 data", which is
an *app role assignment* (application permission) or a delegated scope grant
in the directory, made against Microsoft Graph's own API with Graph-scoped
tokens. A skill that reports RBAC and calls the answer complete has missed an
application that can read every mailbox in the tenant.

CONSENT IS NOT AN API CALL YOU CAN FAKE
---------------------------------------
Delegated permissions require user or admin consent. An application permission
requires admin consent. Granting one is a directory-administrator act; this
module builds and (given a Graph-scoped transport) sends the request, and the
consent decision remains a human one. Directory-role assignment — Global
Administrator and friends — is intentionally *documented* rather than coded:
the tier is administrative, the API is small, and an unattended code path for
it is not something this skill should ship.

FEDERATED CREDENTIALS
---------------------
The workload-identity-federation path (no secret at all) is a
``federatedIdentityCredentials`` object on the application. The request builder
is here because getting the issuer/subject pair wrong is the single most common
federation failure and it is decidable offline.

IT IS A REAL PROVIDER NOW
-------------------------
This adapter used to declare ``plane = "microsoft-graph"`` and a matrix status
of ``implemented`` while exposing ``create_assignment(principal_id=…)`` — not
the :class:`~azaccess.providers.base.Provider` protocol. Registering it in
:class:`~azaccess.engine.AccessManager` raised ``AttributeError`` from inside
``plan``, where nothing catches it. It now implements ``list_for``, ``matches``,
``create`` and ``delete``, so the plane is reachable through the same six verbs
as the others; the keyword form is kept as the direct interface it always was.

A declaration on this plane is addressed as:

* ``scope`` — ``/servicePrincipals/<service-principal-object-id>``, the SP the
  permission is granted **on**;
* ``target['resource_id']`` — the SP of the API being called (Microsoft Graph's
  own service principal in this tenant);
* ``target['app_role_id']`` — the permission's id inside that API.

AUDIENCE IS CHECKED BEFORE THE REQUEST
--------------------------------------
An ARM-audience token is rejected by Graph with a 401 that reads exactly like a
missing permission, and the CLI wired one transport into every plane. So the
transport must declare a Graph audience and the mismatch is refused here,
locally, before anything is sent.
"""

from __future__ import annotations

from typing import Any, Mapping

from azaccess.endpoints import AZURE_PUBLIC_CLOUD, CloudEndpoints
from azaccess.errors import AuthorizationRefused, CoordinateError, ProviderConflict
from azaccess.identity import require_guid
from azaccess.model import AccessDeclaration, AssignmentState, OwnershipRecord
from azaccess.providers.base import created_id, page_values, require_ok
from azaccess.transport import Transport

GRAPH_ENDPOINT = "https://graph.microsoft.com"
GRAPH_VERSION = "v1.0"
GRAPH_SCOPE = "https://graph.microsoft.com/.default"


def service_principal_from_scope(scope: str) -> str:
    """The service principal object id inside a Graph plane scope."""
    text = str(scope or "").rstrip("/")
    marker = "/servicePrincipals/"
    if marker not in text:
        raise CoordinateError(
            f"not a Microsoft Graph scope: {text[:80]!r}; expected "
            f"/servicePrincipals/<service-principal-object-id>"
        )
    return require_guid(text.split(marker, 1)[1].split("/", 1)[0],
                        field="service_principal_id")


class GraphAppRoleProvider:
    """Application-permission (app role) assignments on a service principal."""

    plane = "microsoft-graph"

    operations: Mapping[str, str] = {
        "list-app-role-assignments": "implemented",
        "create-app-role-assignment": "implemented",
        "delete-app-role-assignment": "implemented",
        "build-federated-credential-request": "implemented",
        "build-group-member-add-request": "delegated",
        "build-group-member-remove-request": "delegated",
        "refuse-wrong-token-audience": "implemented",
        "grant-delegated-scope": "documented",
        "admin-consent": "documented",
        "directory-role-assignment": "documented",
        "pim-for-groups-eligibility": "documented",
        "transitive-group-membership-read": "documented",
        "create-application": "unsupported",
        "create-group": "unsupported",
        "delete-directory-object": "unsupported",
    }

    def __init__(self, transport: Transport, *, endpoint: str = GRAPH_ENDPOINT,
                 version: str = GRAPH_VERSION,
                 cloud: CloudEndpoints = AZURE_PUBLIC_CLOUD,
                 require_audience: bool = True) -> None:
        #: A Graph-scoped transport. An ARM-scoped token is refused by Graph
        #: with a 401 that reads exactly like a missing permission, so the
        #: mismatch is caught here instead.
        self._cloud = cloud
        if require_audience:
            _require_graph_audience(transport, cloud)
        self._transport = transport
        self._base = f"{endpoint.rstrip('/')}/{version}"

    # -- Provider protocol ------------------------------------------------

    def list_for(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        sp = service_principal_from_scope(declaration.scope)
        states: list[AssignmentState] = []
        for item in self.list_assignments(sp):
            states.append(
                AssignmentState(
                    assignment_id=f"/servicePrincipals/{sp}/appRoleAssignments/"
                                  f"{item.get('id') or ''}",
                    plane=self.plane,
                    principal_id=str(item.get("principalId") or ""),
                    role_definition_id=str(item.get("appRoleId") or ""),
                    scope=declaration.scope,
                    raw_name=str(item.get("resourceId") or ""),
                )
            )
        return tuple(states)

    def matches(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        """Exact: same principal, same API, same app role.

        Role identity on this plane is the ``appRoleId`` GUID carried in
        ``target``, not the catalogue word, so it is compared here rather than
        through :meth:`AssignmentState.matches`.
        """
        wanted_role = self._app_role_id(declaration)
        wanted_resource = self._resource_id(declaration)
        principal = declaration.principal.object_id.lower()
        return tuple(
            s for s in self.list_for(declaration)
            if s.principal_id.lower() == principal
            and s.role_definition_id.lower() == wanted_role
            and s.raw_name.lower() == wanted_resource
        )

    def identity_matches(self, state: AssignmentState,
                         declaration: AccessDeclaration) -> bool:
        """Whether one observed assignment is exactly this declaration.

        Supplied to the engine because role identity on this plane is the
        ``appRoleId`` GUID in ``target``, not the catalogue definition id, so
        the model's generic comparison would answer no for every Graph grant.
        """
        return (
            state.plane == self.plane
            and state.principal_id.lower() == declaration.principal.object_id.lower()
            and state.role_definition_id.lower() == self._app_role_id(declaration)
            and state.raw_name.lower() == self._resource_id(declaration)
        )

    def create(self, declaration: AccessDeclaration, *, plan_id: str) -> OwnershipRecord:
        existing = self.matches(declaration)
        if existing:
            return OwnershipRecord(
                assignment_id=existing[0].assignment_id, plane=self.plane,
                plan_id=plan_id, fingerprint=declaration.fingerprint(),
                principal_id=declaration.principal.object_id,
                scope=declaration.scope, role=declaration.role,
                source="adopted",
            )
        sp = service_principal_from_scope(declaration.scope)
        assignment_id = self.create_assignment(
            principal_id=declaration.principal.object_id,
            resource_id=self._resource_id(declaration),
            app_role_id=self._app_role_id(declaration),
            service_principal_id=sp,
        )
        return OwnershipRecord(
            assignment_id=f"/servicePrincipals/{sp}/appRoleAssignments/{assignment_id}",
            plane=self.plane, plan_id=plan_id,
            fingerprint=declaration.fingerprint(),
            principal_id=declaration.principal.object_id,
            scope=declaration.scope, role=declaration.role,
            source="created",
        )

    def delete(self, assignment_id: str) -> None:
        text = str(assignment_id or "")
        marker = "/appRoleAssignments/"
        if not text.startswith("/servicePrincipals/") or marker not in text:
            raise ProviderConflict(
                "refusing to delete an id that is not a Graph app role "
                "assignment: expected /servicePrincipals/<sp>/appRoleAssignments/<id>"
            )
        sp, _, name = text.partition(marker)
        self.delete_assignment(sp.rsplit("/", 1)[-1], name)

    def _app_role_id(self, declaration: AccessDeclaration) -> str:
        return require_guid(
            dict(declaration.target).get("app_role_id", ""), field="target['app_role_id']"
        )

    def _resource_id(self, declaration: AccessDeclaration) -> str:
        return require_guid(
            dict(declaration.target).get("resource_id", ""), field="target['resource_id']"
        )

    # -- direct interface -------------------------------------------------

    def list_assignments(self, service_principal_id: str) -> tuple[dict[str, Any], ...]:
        sp = require_guid(service_principal_id, field="service_principal_id")
        url = f"{self._base}/servicePrincipals/{sp}/appRoleAssignments"
        return tuple(page_values(self._transport, url,
                                 "listing app role assignments"))

    def build_assignment_body(self, *, principal_id: str, resource_id: str,
                              app_role_id: str) -> dict[str, str]:
        """The three GUIDs, each validated, none of them interchangeable.

        ``principal_id`` is the service principal being granted, ``resource_id``
        is the service principal of the API being called (Microsoft Graph's own
        service principal in the tenant, not the well-known application id), and
        ``app_role_id`` is the permission's id inside that API.
        """
        return {
            "principalId": require_guid(principal_id, field="principalId"),
            "resourceId": require_guid(resource_id, field="resourceId"),
            "appRoleId": require_guid(app_role_id, field="appRoleId"),
        }

    def create_assignment(self, *, principal_id: str, resource_id: str,
                          app_role_id: str, service_principal_id: str = "") -> str:
        body = self.build_assignment_body(
            principal_id=principal_id, resource_id=resource_id,
            app_role_id=app_role_id,
        )
        sp = (
            require_guid(service_principal_id, field="service_principal_id")
            if service_principal_id else body["principalId"]
        )
        url = f"{self._base}/servicePrincipals/{sp}/appRoleAssignments"
        payload = require_ok(
            self._transport.request("POST", url, json_body=body),
            "creating an app role assignment",
            allowed=(201,),
        )
        return created_id(payload, "creating an app role assignment")

    def delete_assignment(self, service_principal_id: str, assignment_id: str) -> None:
        sp = require_guid(service_principal_id, field="service_principal_id")
        url = (
            f"{self._base}/servicePrincipals/{sp}/appRoleAssignments/{assignment_id}"
        )
        require_ok(self._transport.request("DELETE", url),
                   f"deleting app role assignment {assignment_id}",
                   allowed=(204, 404))


def _require_graph_audience(transport: Transport, cloud: CloudEndpoints) -> None:
    audience = str(getattr(transport, "audience", "") or "")
    if not audience:
        raise AuthorizationRefused(
            "this transport does not declare a token audience, so it cannot be "
            "shown to hold a Microsoft Graph token; construct one bound to "
            f"{cloud.graph_audience} or pass require_audience=False deliberately"
        )

    def base(value: str) -> str:
        return value.rstrip("/").removesuffix("/.default").rstrip("/").lower()

    if base(audience) != base(cloud.graph_audience):
        raise AuthorizationRefused(
            f"Microsoft Graph needs a token for {cloud.graph_audience}; this "
            f"transport holds {audience}. Graph answers 401 for the wrong "
            f"audience and the 401 reads exactly like a missing permission, so "
            f"the request is refused here instead"
        )


def group_member_add_request(
    *, group_id: str, principal_object_id: str, endpoint: str = GRAPH_ENDPOINT,
    version: str = GRAPH_VERSION,
) -> tuple[str, str, dict[str, str]]:
    """``(method, url, body)`` for adding one member to a group.

    Microsoft Graph documents this as
    ``POST /groups/{group-id}/members/$ref`` with a body naming the member by
    reference, answering ``204 No Content``. The reference is built from
    ``/directoryObjects/{id}``, which is the form that works for a user, a
    security group, a device or a service principal alike — the caller does not
    have to know which kind the object id belongs to.

    Group-based grants are the least-privilege pattern this package's role
    assignments are meant to sit on: assign the role to the group once, then
    manage people and workloads by membership. That is why the membership call
    is built here and *not* sent — see :func:`group_member_remove_request` for
    the reason a membership call is worth refusing to fire blindly.

    Adding a member that is already one answers ``400``, not ``409`` and not a
    silent success, so a caller must treat "already a member" as an expected
    outcome rather than an error to retry.
    """
    group = require_guid(group_id, field="group_id")
    member = require_guid(principal_object_id, field="principal_object_id")
    base = f"{endpoint.rstrip('/')}/{version}"
    return (
        "POST",
        f"{base}/groups/{group}/members/$ref",
        {"@odata.id": f"{base}/directoryObjects/{member}"},
    )


def group_member_remove_request(
    *, group_id: str, principal_object_id: str, endpoint: str = GRAPH_ENDPOINT,
    version: str = GRAPH_VERSION,
) -> tuple[str, str]:
    """``(method, url)`` for removing one member from a group.

    The URL **always** ends in ``/$ref``, and that is the whole point.
    Microsoft Graph's own reference carries the caution: if ``/$ref`` is not
    appended and the calling app has permission to manage the member object
    type, *the member object is deleted from Microsoft Entra ID* — an app
    holding ``GroupMember.ReadWrite.All`` and ``User.ReadWrite.All`` deletes the
    user. One missing suffix turns "take this identity out of a group" into
    "delete this identity", so the suffix is appended here rather than left to
    a caller's string concatenation, and
    :func:`refuse_membership_url_without_ref` refuses the unsuffixed form.

    A successful removal answers ``204 No Content``. Membership of a group with
    dynamic membership rules cannot be removed this way at all.
    """
    group = require_guid(group_id, field="group_id")
    member = require_guid(principal_object_id, field="principal_object_id")
    base = f"{endpoint.rstrip('/')}/{version}"
    return "DELETE", f"{base}/groups/{group}/members/{member}/$ref"


def refuse_membership_url_without_ref(method: str, url: str) -> str:
    """Return ``url``, or refuse a membership DELETE that would delete a principal.

    The check is deliberately cheap and deliberately loud: it is the difference
    between removing a membership and removing the identity that held it.
    """
    text = str(url or "")
    if str(method).upper() != "DELETE" or "/members/" not in text:
        return text
    if not text.split("?", 1)[0].rstrip("/").endswith("/$ref"):
        raise AuthorizationRefused(
            "refusing DELETE on a group membership URL that does not end in "
            "'/$ref': without the suffix Microsoft Graph deletes the member "
            "object itself when the caller may manage that object type"
        )
    return text


def federated_credential_request(
    *, name: str, issuer: str, subject: str, audience: str = "api://AzureADTokenExchange",
    description: str = "",
) -> dict[str, Any]:
    """The body for a ``federatedIdentityCredentials`` create.

    Secretless by construction: the trust is issuer plus subject, so nothing
    here is a credential and nothing needs storing. ``subject`` must match the
    token's ``sub`` claim exactly — including case and any ``repo:``/``system:``
    prefix — because the check is a string comparison and a near miss reports
    as an authentication failure with no hint about which half was wrong.
    """
    if not issuer.startswith("https://"):
        raise CoordinateError(f"federated issuer must be https: {issuer[:60]!r}")
    if not subject.strip():
        raise CoordinateError("federated subject must be the exact 'sub' claim")
    return {
        "name": name,
        "issuer": issuer.rstrip("/"),
        "subject": subject,
        "audiences": [audience],
        "description": description,
    }


__all__ = [
    "GRAPH_ENDPOINT",
    "GRAPH_SCOPE",
    "GRAPH_VERSION",
    "GraphAppRoleProvider",
    "federated_credential_request",
    "group_member_add_request",
    "group_member_remove_request",
    "refuse_membership_url_without_ref",
    "service_principal_from_scope",
]
