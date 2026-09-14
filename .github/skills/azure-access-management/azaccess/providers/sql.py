"""Azure SQL database users — the plane that is not an Azure resource at all.

WHY IT IS DELEGATED AND NOT IMPLEMENTED
---------------------------------------
A contained database user is created with T-SQL over TDS. There is no ARM
resource, no role assignment, and no HTTP request that will do it. Pretending
otherwise — tunnelling a ``CREATE USER`` through the HTTP transport because
the interface happens to be there — would produce an adapter that cannot
possibly work and a support matrix that lies. So this provider builds and
validates the statements, and executes them only through a host-supplied
:class:`~azaccess.transport.SqlExecutor`. With no executor, it refuses.

WHAT IS STILL PROVEN OFFLINE
----------------------------
Statement construction, identifier quoting, the read-back query, and the
ownership refusals are all exercised against a fake executor. Those are the
parts that are wrong in practice; the network hop is not.

QUOTING IS A SECURITY BOUNDARY
------------------------------
Object names cannot be parameterised in T-SQL DDL, so they are quoted by
doubling ``]`` inside ``[...]`` and refused outright if they contain anything
outside a conservative character set. A display name arriving from a directory
is untrusted input. Identifiers and *literals* are validated and quoted by
separate functions, because they have different escape rules and one function
that does both is a function that will eventually do the wrong one.

A PRINCIPAL NAME IS NOT AN OBJECT NAME
--------------------------------------
The conservative object-identifier set excludes ``@``, which refused
``CREATE USER [app@contoso.onmicrosoft.com] FROM EXTERNAL PROVIDER`` — the
standard form for a user and for a service principal named by UPN. So the
principal name has its own, still-conservative, validator. It is deliberately
not email-only: a managed identity or an application is created by its
*display name*, with no ``@`` anywhere, and both forms are accepted.

GRANT ONE TABLE, NOT A DATABASE ROLE
------------------------------------
``db_datareader`` reads every table in the database. The least-privilege
equivalent is ``GRANT SELECT ON [schema].[table]``, which is what this builds.

THE READ-BACK IS BOUND TO THE OBJECT
------------------------------------
An earlier read-back joined ``sys.database_permissions`` on
``grantee_principal_id`` alone, so ``SELECT`` granted on *any* object — or at
database scope — satisfied a declaration about one table. The query now filters
``class_desc``, ``major_id = OBJECT_ID(@object)``, ``minor_id = 0`` and
``state_desc = 'GRANT'``, and :meth:`SqlDatabaseUserProvider.matches` re-checks
every one of those on the row, so a permissive executor cannot pass the check
by returning a broader row.
"""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from azaccess.errors import AuthorizationRefused, CoordinateError, ProviderConflict
from azaccess.model import AccessDeclaration, AssignmentState, OwnershipRecord
from azaccess.transport import SqlExecutor

#: Conservative: letters, digits, underscore, hyphen, space and dot. Anything
#: else is refused rather than escaped, because escaping cleverness is how
#: injection bugs are written.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_. -]{1,128}$")

#: A database principal name. The object set plus ``@`` for a UPN or service
#: principal name. Still no separator, no bracket, no quote, no control char.
_PRINCIPAL_NAME_RE = re.compile(r"^[A-Za-z0-9_.@ -]{1,128}$")

#: Permissions this plane will grant. An enum, compared exactly.
TABLE_PERMISSIONS: tuple[str, ...] = ("SELECT", "INSERT", "UPDATE", "DELETE")


def quote_identifier(name: str) -> str:
    """``[name]``, with ``]`` doubled, or a refusal. Schema and table names."""
    text = str(name or "").strip()
    if not _SAFE_NAME_RE.match(text):
        raise CoordinateError(
            f"unsafe SQL identifier {text[:40]!r}: expected letters, digits, "
            f"underscore, hyphen, space or dot"
        )
    return "[" + text.replace("]", "]]") + "]"


def quote_principal_identifier(name: str) -> str:
    """``[name]`` for a database principal, which may carry a UPN ``@``."""
    text = str(name or "").strip()
    if not _PRINCIPAL_NAME_RE.match(text):
        raise CoordinateError(
            f"unsafe SQL principal name {text[:40]!r}: expected letters, digits, "
            f"underscore, hyphen, space, dot or '@'"
        )
    return "[" + text.replace("]", "]]") + "]"


def quote_literal(value: str) -> str:
    """``N'value'``, with ``'`` doubled. Values, never identifiers.

    Separate from :func:`quote_identifier` on purpose: a bracket-quoted value
    and a string-quoted identifier are both syntax errors at best and an
    injection at worst.
    """
    text = str(value or "")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in text):
        raise CoordinateError("SQL literal contains control characters")
    if len(text) > 256:
        raise CoordinateError("SQL literal is longer than 256 characters")
    return "N'" + text.replace("'", "''") + "'"


def _object_name(declaration: AccessDeclaration) -> str:
    target = dict(declaration.target)
    return f"{quote_identifier(target.get('schema', ''))}." \
           f"{quote_identifier(target.get('table', ''))}"


def sql_grant_statements(declaration: AccessDeclaration) -> tuple[str, ...]:
    """The statements one SQL declaration expands to, in order.

    Public because reviewing the exact T-SQL before anything runs is the whole
    point of a plan, and because an operator without an executor can copy them
    into a query window and follow the documented procedure by hand.

    The ``CREATE USER`` is guarded. Unguarded, it raised error 15023 on every
    re-run, which made this plane non-idempotent and made a second ``apply``
    fail on work that was already correct.
    """
    name = _user_name(declaration)
    user = quote_principal_identifier(name)
    permission = declaration.role_definition.definition_id
    if permission not in TABLE_PERMISSIONS:
        raise CoordinateError(
            f"'{permission}' is not a table permission this plane will grant"
        )
    return (
        f"IF NOT EXISTS (SELECT 1 FROM sys.database_principals "
        f"WHERE name = {quote_literal(name)}) "
        f"CREATE USER {user} FROM EXTERNAL PROVIDER;",
        f"GRANT {permission} ON {_object_name(declaration)} TO {user};",
    )


def _user_name(declaration: AccessDeclaration) -> str:
    name = str(dict(declaration.target).get("user_name") or "").strip()
    if not name:
        name = declaration.principal.display_name.strip()
    if not name:
        raise CoordinateError(
            "a SQL grant needs the database user name (target['user_name']); a "
            "contained user is created by directory name — the UPN for a user "
            "or a UPN-named service principal, the display name for a managed "
            "identity or application — never by GUID"
        )
    return name


class SqlDatabaseUserProvider:
    """Contained database users, executed by a host-supplied executor."""

    plane = "sql-database-user"

    operations: Mapping[str, str] = {
        "build-grant-statements": "implemented",
        "read-back-permission": "delegated",
        "create-user-and-grant": "delegated",
        "idempotent-re-grant": "delegated",
        "drop-owned-user": "delegated",
        "drop-unowned-user": "unsupported",
        "server-entra-admin-assignment": "documented",
    }

    def __init__(self, executor: SqlExecutor | None = None, *,
                 owned_prefix: str = "") -> None:
        self._executor = executor
        #: Only users whose name starts with this prefix may be dropped. The
        #: credential doing the dropping is a database admin, so "leave other
        #: users alone" has to be enforced, not intended.
        self._owned_prefix = owned_prefix

    def _require_executor(self) -> SqlExecutor:
        if self._executor is None:
            raise ProviderConflict(
                "no SQL executor supplied; this plane speaks T-SQL over TDS and "
                "cannot be driven by the HTTP transport. Supply an executor or "
                "follow the documented manual procedure"
            )
        return self._executor

    def list_for(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        """Permissions this user holds **on the declared object**.

        Every filter here is load-bearing. Without ``class_desc`` and
        ``major_id`` the query answers for permissions on any object or at
        database scope; without ``state_desc`` a ``DENY`` row reads as a grant.
        """
        executor = self._require_executor()
        rows = executor.query(
            "SELECT p.name AS user_name, pe.permission_name, pe.state_desc, "
            "pe.class_desc, pe.major_id, pe.minor_id "
            "FROM sys.database_principals p "
            "JOIN sys.database_permissions pe "
            "  ON pe.grantee_principal_id = p.principal_id "
            "WHERE p.name = ? "
            "  AND pe.class_desc = 'OBJECT_OR_COLUMN' "
            "  AND pe.major_id = OBJECT_ID(?) "
            "  AND pe.minor_id = 0 "
            "  AND pe.state_desc = 'GRANT'",
            (_user_name(declaration), _object_name(declaration)),
        )
        states: list[AssignmentState] = []
        for row in rows:
            states.append(
                AssignmentState(
                    assignment_id=f"{declaration.scope}/users/{row.get('user_name')}",
                    plane=self.plane,
                    principal_id=declaration.principal.object_id,
                    role_definition_id=str(row.get("permission_name") or ""),
                    scope=declaration.scope,
                    raw_name=str(row.get("user_name") or ""),
                    # Carried so ``matches`` can re-check them rather than
                    # trusting that the executor honoured the WHERE clause.
                    principal_type=f"{row.get('class_desc') or ''}|"
                                   f"{row.get('state_desc') or ''}|"
                                   f"{row.get('major_id') if row.get('major_id') is not None else ''}",
                )
            )
        return tuple(states)

    def user_exists(self, declaration: AccessDeclaration) -> bool:
        """Whether the contained user is already there, by name."""
        rows = self._require_executor().query(
            "SELECT name FROM sys.database_principals WHERE name = ?",
            (_user_name(declaration),),
        )
        return bool(rows)

    def matches(self, declaration: AccessDeclaration) -> tuple[AssignmentState, ...]:
        """Present *and* holding the declared permission on the bound object.

        A user that exists with no permission is what a half-applied grant
        leaves behind. Reporting it as present is how a deployment claims
        access it does not have. A row scoped to the database, to another
        object, to a column, or in ``DENY`` state is not this permission either.
        """
        wanted = declaration.role_definition.definition_id.upper()
        out: list[AssignmentState] = []
        for state in self.list_for(declaration):
            if state.role_definition_id.upper() != wanted:
                continue
            class_desc, _, rest = state.principal_type.partition("|")
            state_desc, _, major_id = rest.partition("|")
            if class_desc.upper() != "OBJECT_OR_COLUMN":
                continue
            if state_desc.upper() != "GRANT":
                continue
            if not str(major_id).strip() or str(major_id).strip() in ("0", "None"):
                continue
            out.append(state)
        return tuple(out)

    def identity_matches(self, state: AssignmentState,
                         declaration: AccessDeclaration) -> bool:
        """Whether one observed row is exactly this declaration's grant.

        Supplied to the engine because this plane's identity is a permission
        row on an object, not a role definition id.
        """
        return state.assignment_id in {
            s.assignment_id for s in self.matches(declaration)
        }

    def create(self, declaration: AccessDeclaration, *, plan_id: str) -> OwnershipRecord:
        executor = self._require_executor()
        if self.matches(declaration):
            # Already granted. Adopting is the honest record: this run did not
            # make it, so this run may not drop the user later.
            return OwnershipRecord(
                assignment_id=f"{declaration.scope}/users/{_user_name(declaration)}",
                plane=self.plane, plan_id=plan_id,
                fingerprint=declaration.fingerprint(),
                principal_id=declaration.principal.object_id,
                scope=declaration.scope, role=declaration.role,
                source="adopted",
                detail="the permission was already granted on this object",
            )
        preexisting_user = self.user_exists(declaration)
        for statement in sql_grant_statements(declaration):
            executor.execute(statement)
        if not self.matches(declaration):
            raise ProviderConflict(
                "the grant statements ran and the read-back found no permission "
                "on the bound table"
            )
        return OwnershipRecord(
            assignment_id=f"{declaration.scope}/users/{_user_name(declaration)}",
            plane=self.plane,
            plan_id=plan_id,
            fingerprint=declaration.fingerprint(),
            principal_id=declaration.principal.object_id,
            scope=declaration.scope,
            role=declaration.role,
            source="created",
            detail=(
                "the user already existed; only the permission was granted by "
                "this run" if preexisting_user else "user and permission created"
            ),
        )

    def delete(self, assignment_id: str) -> None:
        executor = self._require_executor()
        name = str(assignment_id).rsplit("/users/", 1)[-1]
        if self._owned_prefix and not name.startswith(self._owned_prefix):
            raise AuthorizationRefused(
                f"refusing to drop database user {name!r}: it does not carry the "
                f"owned prefix {self._owned_prefix!r}"
            )
        executor.execute(f"DROP USER {quote_principal_identifier(name)};")


class RecordingSqlExecutor:
    """An offline executor that records statements and answers scripted rows.

    Ships with the skill because the SQL plane's value is in the statements it
    builds, and a consumer extending this provider needs the same harness the
    selftest uses.

    ``failures`` maps a statement substring to the exception to raise, because
    an executor that never fails is why 119 passing checks missed a plane that
    could not be applied twice. ``rows_for`` answers different queries
    differently, which is what distinguishes "the user exists" from "the user
    holds this permission on this object".
    """

    def __init__(self, rows: Sequence[dict[str, Any]] = (), *,
                 failures: Mapping[str, Exception] | None = None,
                 rows_for: Mapping[str, Sequence[dict[str, Any]]] | None = None) -> None:
        self.statements: list[str] = []
        self.parameters: list[tuple[Any, ...]] = []
        self._rows = list(rows)
        self._failures = dict(failures or {})
        self._rows_for = {k: list(v) for k, v in dict(rows_for or {}).items()}

    def _record(self, statement: str, parameters: Sequence[Any]) -> None:
        self.statements.append(statement)
        self.parameters.append(tuple(parameters))
        for fragment, error in self._failures.items():
            if fragment in statement:
                raise error

    def execute(self, statement: str, parameters: Sequence[Any] = ()) -> None:
        self._record(statement, parameters)

    def query(self, statement: str, parameters: Sequence[Any] = ()) -> list[dict[str, Any]]:
        self._record(statement, parameters)
        for fragment, rows in self._rows_for.items():
            if fragment in statement:
                return list(rows)
        return list(self._rows)


__all__ = [
    "RecordingSqlExecutor",
    "SqlDatabaseUserProvider",
    "TABLE_PERMISSIONS",
    "quote_identifier",
    "quote_literal",
    "quote_principal_identifier",
    "sql_grant_statements",
]
