"""The role vocabulary: public definition ids, plane, and privilege tier.

WHY A CATALOGUE AT ALL
----------------------
A role definition id is a GUID with no meaning at the call site, so code that
inlines one cannot be reviewed and cannot be tiered. The catalogue exists so
that (a) a plan names a role in words, (b) the authority policy can refuse a
tier rather than a spelling, and (c) a reader can see which *plane* a role is
assigned on — which is the distinction that makes revocation correct.

Every GUID here is a public, documented built-in role definition id, identical
in every tenant. None of them is an environment coordinate.

FOUR PLANES, ONE OF THEM AZURE RBAC
-----------------------------------
A Cosmos SQL role assignment is not Azure RBAC: it does not appear in an ARM
role-assignment list and an ARM delete will never remove it. A Kusto database
principal assignment is the same. A SQL database user is further still — not
an Azure resource at all, created with T-SQL inside the database. Revoking
Azure RBAC alone therefore leaves data access intact on three planes, which is
why every role carries its plane and teardown walks all of them.

TIERS ARE INTENTIONAL, NOT PROHIBITED
-------------------------------------
``privileged`` and ``administrative`` roles are in the catalogue on purpose: a
management skill that cannot express ``Owner`` cannot audit one. What the
catalogue does is make the tier explicit so authorisation is a decision
somebody made, not a spelling that slipped through.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from azaccess.errors import CoordinateError

_GUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)

#: Planes whose role identity is a GUID carried at the end of a definition
#: path, and planes whose role identity is a word. The two need different
#: comparisons and sharing one is how ``Viewer`` came to match
#: ``UnrestrictedViewer``.
GUID_KEYED_PLANES: tuple[str, ...] = ("azure-rbac", "cosmos-sql-rbac")
WORD_KEYED_PLANES: tuple[str, ...] = (
    "kusto-database",
    "sql-database-user",
    "microsoft-graph",
)

#: Ordered least to most privileged. ``read`` and ``write`` are data or
#: control-plane grades; ``privileged`` can change resources broadly;
#: ``administrative`` can change *who else* has access, which is the tier that
#: makes every other control moot.
TIERS: tuple[str, ...] = ("read", "write", "privileged", "administrative")

#: The assignment planes. ``azure-rbac`` is the only one ARM role-assignment
#: APIs cover.
PLANES: tuple[str, ...] = (
    "azure-rbac",
    "cosmos-sql-rbac",
    "kusto-database",
    "sql-database-user",
    "microsoft-graph",
)


@dataclass(frozen=True)
class RoleDefinition:
    """One assignable role, on one plane, at one privilege tier."""

    name: str
    definition_id: str
    plane: str
    tier: str
    service: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.tier not in TIERS:
            raise CoordinateError(f"'{self.tier}' is not a privilege tier")
        if self.plane not in PLANES:
            raise CoordinateError(f"'{self.plane}' is not an assignment plane")

    @property
    def is_privileged(self) -> bool:
        return self.tier in ("privileged", "administrative")

    def arm_definition_id(self, subscription_id: str) -> str:
        """The subscription-qualified id ARM requires in an assignment body."""
        if self.plane != "azure-rbac":
            raise CoordinateError(
                f"{self.name} is assigned on the {self.plane} plane and has no "
                f"ARM role definition id"
            )
        return (
            f"/subscriptions/{subscription_id}/providers/Microsoft.Authorization"
            f"/roleDefinitions/{self.definition_id}"
        )


def _role(name: str, definition_id: str, plane: str, tier: str, service: str = "",
          note: str = "") -> RoleDefinition:
    return RoleDefinition(name, definition_id, plane, tier, service, note)


#: Built-in roles this skill can plan, read back and revoke. Extend it with
#: :func:`register_role`; nothing here is a restriction on Azure, only on what
#: this package will build a request for without being told the id explicitly.
BUILTIN_ROLES: dict[str, RoleDefinition] = {
    r.name: r
    for r in (
        # -- control plane, general ------------------------------------
        _role("Reader", "acdd72a7-3385-48ef-bd42-f606fba81ae7", "azure-rbac", "read"),
        _role("Contributor", "b24988ac-6180-42a0-ab88-20f7382dd24c", "azure-rbac",
              "privileged", note="every resource action except access management"),
        _role("Owner", "8e3af657-a8ff-443c-a75c-2fe8c4bcb635", "azure-rbac",
              "administrative", note="includes granting access to others"),
        _role("User Access Administrator", "18d7d88d-da9d-4a06-b2f8-d1ff5b25a1b6",
              "azure-rbac", "administrative"),
        _role("Role Based Access Control Administrator",
              "f58310d9-a9f6-439a-9e8d-f62e7b41a168", "azure-rbac", "administrative"),
        # -- storage ---------------------------------------------------
        _role("Storage Blob Data Reader", "2a2b9908-6ea1-4ae2-8e65-a410df84e7d1",
              "azure-rbac", "read", "storage"),
        _role("Storage Blob Data Contributor", "ba92f5b4-2d11-453d-a403-e96b0029c9fe",
              "azure-rbac", "write", "storage",
              note="no built-in role separates blob writes from container lifecycle"),
        _role("Storage Blob Data Owner", "b7e6dc6d-f1e8-4753-8033-0f276bb0955b",
              "azure-rbac", "privileged", "storage"),
        _role("Storage Queue Data Reader", "19e7f393-937e-4f77-808e-94535e297925",
              "azure-rbac", "read", "storage"),
        _role("Storage Table Data Reader", "76199698-9eea-4c19-bc75-cec21354c6b6",
              "azure-rbac", "read", "storage"),
        # -- search ----------------------------------------------------
        _role("Search Index Data Reader", "1407120a-92aa-4202-b7e9-c0e197c71c8f",
              "azure-rbac", "read", "search"),
        _role("Search Index Data Contributor", "8ebe5a00-799e-43f5-93ac-243d3dce84a7",
              "azure-rbac", "write", "search"),
        _role("Search Service Contributor", "7ca78c08-252a-4471-8644-bb5ff32d4ba0",
              "azure-rbac", "privileged", "search",
              note="index lifecycle; not a data-plane grant"),
        # -- key vault -------------------------------------------------
        _role("Key Vault Secrets User", "4633458b-17de-408a-b874-0445c86b69e6",
              "azure-rbac", "read", "keyvault",
              note="reads secret VALUES; treat as credential access"),
        _role("Key Vault Reader", "21090545-7ca7-4776-b22c-e363652d74d2",
              "azure-rbac", "read", "keyvault", note="metadata only, not values"),
        # -- monitoring ------------------------------------------------
        _role("Monitoring Reader", "43d0d8ad-25c7-4714-9337-8ba259a9fe05",
              "azure-rbac", "read", "monitor"),
        _role("Log Analytics Reader", "73c42c96-874c-492b-b04d-ab87d138a893",
              "azure-rbac", "read", "monitor"),
        # -- inference -------------------------------------------------
        _role("Cognitive Services OpenAI User", "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd",
              "azure-rbac", "read", "inference"),
        _role("Cognitive Services OpenAI Contributor",
              "a001fd3d-188f-4b5d-821b-7da978bf7442", "azure-rbac", "write",
              "inference"),
        # -- native planes ---------------------------------------------
        _role("Cosmos DB Built-in Data Reader",
              "00000000-0000-0000-0000-000000000001", "cosmos-sql-rbac", "read",
              "cosmos", note="not Azure RBAC; invisible to ARM assignment lists"),
        _role("Cosmos DB Built-in Data Contributor",
              "00000000-0000-0000-0000-000000000002", "cosmos-sql-rbac", "write",
              "cosmos", note="not Azure RBAC; create is NOT idempotent"),
        _role("Kusto Database Viewer", "Viewer", "kusto-database", "read", "kusto"),
        _role("Kusto Database Unrestricted Viewer", "UnrestrictedViewer",
              "kusto-database", "privileged", "kusto",
              note="reads restricted-view tables; a strict superset of Viewer"),
        _role("Kusto Database Ingestor", "Ingestor", "kusto-database", "write", "kusto"),
        _role("Kusto Database Monitor", "Monitor", "kusto-database", "read", "kusto"),
        _role("Kusto Database User", "User", "kusto-database", "read", "kusto"),
        _role("Kusto Database Admin", "Admin", "kusto-database", "administrative",
              "kusto"),
        _role("Kusto All Databases Admin", "AllDatabasesAdmin", "kusto-database",
              "administrative", "kusto",
              note="cluster-wide; the name ends in 'Admin' and it is not Admin"),
        _role("SQL Table Data Reader", "SELECT", "sql-database-user", "read", "sql",
              note="a T-SQL GRANT on one table, not a database role membership"),
        # -- directory plane -------------------------------------------
        _role("Microsoft Graph Application Permission", "AppRoleAssignment",
              "microsoft-graph", "administrative", "graph",
              note="the exact permission is target['app_role_id']; admin consent "
                   "is a human act and this only records the assignment"),
    )
}

#: A conservative default: the narrowest role that satisfies a read journey per
#: service. Documentation, not a restriction.
READER_ROLE_FOR_SERVICE: dict[str, str] = {
    "storage": "Storage Blob Data Reader",
    "search": "Search Index Data Reader",
    "cosmos": "Cosmos DB Built-in Data Reader",
    "kusto": "Kusto Database Viewer",
    "sql": "SQL Table Data Reader",
    "inference": "Cognitive Services OpenAI User",
    "monitor": "Log Analytics Reader",
}


def lookup_role(name: str) -> RoleDefinition:
    """The catalogue entry for ``name``, or a refusal naming near matches."""
    key = str(name or "").strip()
    if key in BUILTIN_ROLES:
        return BUILTIN_ROLES[key]
    lowered = key.lower()
    for candidate, role in BUILTIN_ROLES.items():
        if candidate.lower() == lowered:
            return role
    near = sorted(n for n in BUILTIN_ROLES if lowered and lowered.split()[0].lower() in n.lower())
    raise CoordinateError(
        f"'{key}' is not in the role catalogue"
        + (f"; did you mean {near[:3]}?" if near else "")
    )


def register_role(role: RoleDefinition) -> RoleDefinition:
    """Add a custom role definition to the catalogue for this process.

    Custom roles are the normal case in a mature estate. Registering one is a
    deliberate act so that its tier is stated by a human rather than inferred
    from a name.
    """
    BUILTIN_ROLES[role.name] = role
    return role


def role_identity_matches(observed_role_id: str, role: RoleDefinition) -> bool:
    """True only when the observed role is *this* role, on ``role.plane``.

    Two comparisons, because the planes carry two kinds of identity:

    * GUID-keyed planes (Azure RBAC, Cosmos SQL) report a *path* ending in the
      definition GUID. The last segment is compared exactly, and it has to be
      a GUID — so a definition path with a trailing name never matches.
    * Word-keyed planes (Kusto, SQL, Graph) report a word. The whole string is
      compared exactly, case-insensitively, against the catalogue enum.

    A suffix test — which is what this package used to do on every plane — is
    correct for GUIDs and silently elevating for words: a declared Kusto
    ``Viewer`` matched a live ``UnrestrictedViewer`` and a declared ``Admin``
    matched ``AllDatabasesAdmin``, so ``plan`` reported ``noop`` for a grant
    that was never made and ``revoke`` targeted the broader role.
    """
    observed = str(observed_role_id or "").strip()
    wanted = role.definition_id.strip()
    if not observed or not wanted:
        return False
    if role.plane in GUID_KEYED_PLANES:
        tail = observed.rsplit("/", 1)[-1]
        if not _GUID_RE.match(tail) or not _GUID_RE.match(wanted):
            return False
        return tail.lower() == wanted.lower()
    return observed.lower() == wanted.lower()


def roles_at_or_above(tier: str) -> tuple[str, ...]:
    """Catalogue names at ``tier`` or more privileged. Used by audits."""
    if tier not in TIERS:
        raise CoordinateError(f"'{tier}' is not a privilege tier")
    floor = TIERS.index(tier)
    return tuple(
        sorted(r.name for r in BUILTIN_ROLES.values() if TIERS.index(r.tier) >= floor)
    )


__all__ = [
    "BUILTIN_ROLES",
    "GUID_KEYED_PLANES",
    "PLANES",
    "READER_ROLE_FOR_SERVICE",
    "RoleDefinition",
    "TIERS",
    "WORD_KEYED_PLANES",
    "lookup_role",
    "register_role",
    "role_identity_matches",
    "roles_at_or_above",
]
