"""Contained database users — the grant plane Azure RBAC cannot reach.

WHY THIS EXISTS AT ALL
----------------------
Every other grant in this system is a role assignment: a ``PUT`` to ARM, or a
Cosmos SQL role assignment, or a Kusto principal assignment. Azure SQL has
none of those for data access. Reading a table is authorised by a **database
principal inside the database**, created with T-SQL, and no amount of
``Contributor`` at subscription scope grants it. An operator who revokes every
Azure role assignment and believes the agent can no longer read the table is
wrong, and this module is why the teardown path knows that.

WHY THE SID IS SPELLED OUT INSTEAD OF LOOKED UP
-------------------------------------------------
``CREATE USER [x] FROM EXTERNAL PROVIDER`` asks the server to resolve the name
in Microsoft Entra, which requires the server's identity to hold the Directory
Readers role — a tenant-level grant this project is not authorised to make and
would not want to. ``CREATE USER [x] WITH SID = 0x..., TYPE = E`` skips the
lookup entirely: the server stores the id it is given and validates nothing.
That is the documented path for exactly this situation, and it is the one taken
here.

THE BYTE ORDER IS THE PART THAT GOES WRONG
--------------------------------------------
A ``uniqueidentifier`` in SQL Server is a GUID in **mixed-endian** layout: the
first three fields little-endian, the last two big-endian. Microsoft's own
recipe is ``CONVERT(VARBINARY(16), CAST(@objectId AS UNIQUEIDENTIFIER))``, and
the Python equivalent of that conversion is ``UUID(value).bytes_le`` — *not*
``.bytes``. Getting it wrong produces a user that is created successfully,
reads back with the wrong id, and silently authorises nobody.

FOR A SERVICE PRINCIPAL THE SID IS THE APPLICATION ID
-------------------------------------------------------
Microsoft's documentation is explicit: for a user or a group the SID is the
Entra **object** id; for an application or a managed identity it is the
**application (client)** id. For a Foundry ``ServiceIdentity`` these are the
same value — a property recorded in ``hcagent.foundry.instance_principal_id``
and true of no user-assigned managed identity — so one field carries it. A
caller holding an identity where they differ must pass the application id.

WHAT THIS MODULE MAY EMIT, AND NOTHING ELSE
---------------------------------------------
Five statements, all of them built here from validated identifiers and a hex
SID derived from a parsed UUID. There is no method that runs caller text. A
grant plane that could run arbitrary DDL would be a management-plane hole with
a data-plane name.

TEARDOWN REMOVES WHAT IT MADE
-----------------------------
:meth:`SqlPrincipals.remove` refuses a user whose name does not carry this
module's prefix, and refuses one whose stored SID is not the principal being
revoked. Both checks exist because the operator credential that runs this is a
database admin, and an admin with a loop is how somebody else's user gets
dropped.

DEPENDENCIES
------------
:mod:`azdata.sqldb.read` for the connection, and its driver.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from azdata.sqldb.guard import TsqlRefused, quote_identifier
from azdata.sqldb.read import (
    DEFAULT_LOGIN_TIMEOUT_SECS,
    DEFAULT_QUERY_TIMEOUT_SECS,
    SQL_SCOPE,
    SqlTarget,
    SqlUnavailable,
    json_safe,
    open_connection,
)

#: The prefix every user this module creates carries. It is the ownership
#: proof teardown checks before it drops anything, so it is not cosmetic.
USER_PREFIX = "hcagent_"

#: ``E`` is a user or service principal, ``X`` is a group. Only the first is
#: emitted: a group grant is somebody else's decision to make.
ENTRA_PRINCIPAL_TYPE = "E"

#: The one permission granted, on one object. Not a role: ``db_datareader``
#: reads every table in the database, and the bound table is one of them.
GRANTED_PERMISSION = "SELECT"

#: Read-backs. Held as constants rather than composed, because a statement a
#: caller can influence is a statement a caller can redirect.
_PRINCIPAL_QUERY = (
    "SELECT TOP (2) dp.name AS name, dp.type AS principal_type, "
    "CAST(CAST(dp.sid AS varbinary(16)) AS uniqueidentifier) AS entra_id "
    "FROM sys.database_principals AS dp WHERE dp.name = %(name)s"
)
_PERMISSION_QUERY = (
    "SELECT TOP (50) perm.permission_name AS permission, "
    "perm.state_desc AS state, sch.name AS schema_name, obj.name AS object_name "
    "FROM sys.database_permissions AS perm "
    "INNER JOIN sys.database_principals AS dp "
    "ON dp.principal_id = perm.grantee_principal_id "
    "LEFT JOIN sys.objects AS obj ON obj.object_id = perm.major_id "
    "LEFT JOIN sys.schemas AS sch ON sch.schema_id = obj.schema_id "
    "WHERE dp.name = %(name)s"
)


class SqlGrantFailed(RuntimeError):
    """A database grant could not be applied, read back or revoked."""


def entra_sid(principal_id: str) -> str:
    """One Entra id as the ``0x`` literal ``CREATE USER ... WITH SID`` wants.

    ``bytes_le`` and not ``bytes``: SQL Server's ``uniqueidentifier`` is
    mixed-endian, and the big-endian form produces a user whose id reads back
    as a different GUID.
    """
    try:
        parsed = uuid.UUID(str(principal_id))
    except (AttributeError, TypeError, ValueError) as failure:
        raise SqlGrantFailed(
            f"'{str(principal_id)[:60]}' is not an Entra object id; a SID can "
            "only be built from a GUID"
        ) from failure
    return "0x" + parsed.bytes_le.hex().upper()


def owned_user_name(principal_id: str, *, prefix: str = USER_PREFIX) -> str:
    """The database user name this module gives one principal.

    Derived from the id rather than from a display name, so it is stable
    across renames, unique per principal, and provably ours by its prefix.
    """
    try:
        parsed = uuid.UUID(str(principal_id))
    except (AttributeError, TypeError, ValueError) as failure:
        raise SqlGrantFailed(
            f"'{str(principal_id)[:60]}' is not an Entra object id"
        ) from failure
    return f"{prefix}{parsed.hex[:16]}"


@dataclass(frozen=True, slots=True)
class SqlGrantState:
    """What the database actually holds for one principal, read back."""

    user: str
    present: bool
    entra_id: str = ""
    permissions: tuple[dict[str, Any], ...] = ()

    @property
    def reads_bound_table(self) -> bool:
        return any(
            str(row.get("permission", "")).upper() == GRANTED_PERMISSION
            and str(row.get("state", "")).upper() == "GRANT"
            for row in self.permissions
        )

    def describe(self) -> dict[str, Any]:
        return {
            "user": self.user,
            "present": self.present,
            "entraId": self.entra_id,
            "permissions": [dict(row) for row in self.permissions],
            "readsBoundTable": self.reads_bound_table,
        }


class SqlPrincipals:
    """Create, read back and remove one contained database user, and its grant.

    The credential is the **operator's own**, and it must be the server's
    Microsoft Entra admin or a principal that admin has given ``ALTER ANY
    USER``. A workload identity does not hold that and must not be given it:
    creating database principals is an administrative act, and the standing
    Azure permissiveness grant does not authorise one from a deployed surface.

    ``connect`` is injected so every statement this class emits, every refusal
    it makes and every read-back it performs is exercised with no driver, no
    network and no database.
    """

    def __init__(
        self,
        *,
        target: SqlTarget,
        credential_provider: Callable[[], Any],
        connect: Callable[..., Any] | None = None,
        user_prefix: str = USER_PREFIX,
        login_timeout_secs: float = DEFAULT_LOGIN_TIMEOUT_SECS,
        query_timeout_secs: float = DEFAULT_QUERY_TIMEOUT_SECS,
    ) -> None:
        if not target.table:
            raise SqlGrantFailed(
                "a SQL grant needs the table it is scoped to; granting the "
                "whole database is wider than any tool needs"
            )
        self._target = target
        self._credentials = credential_provider
        self._connect = connect or open_connection
        self._prefix = user_prefix
        self._login_timeout = float(login_timeout_secs)
        self._query_timeout = float(query_timeout_secs)

    @property
    def target(self) -> SqlTarget:
        return self._target

    def user_for(self, principal_id: str) -> str:
        return owned_user_name(principal_id, prefix=self._prefix)

    # -- the statements, as data ------------------------------------------

    def create_statement(self, principal_id: str) -> str:
        return (
            f"CREATE USER {quote_identifier(self.user_for(principal_id))} "
            f"WITH SID = {entra_sid(principal_id)}, TYPE = {ENTRA_PRINCIPAL_TYPE}"
        )

    def grant_statement(self, principal_id: str) -> str:
        return (
            f"GRANT {GRANTED_PERMISSION} ON OBJECT::"
            f"{quote_identifier(self._target.schema)}."
            f"{quote_identifier(self._target.table)} "
            f"TO {quote_identifier(self.user_for(principal_id))}"
        )

    def revoke_statement(self, principal_id: str) -> str:
        return (
            f"REVOKE {GRANTED_PERMISSION} ON OBJECT::"
            f"{quote_identifier(self._target.schema)}."
            f"{quote_identifier(self._target.table)} "
            f"FROM {quote_identifier(self.user_for(principal_id))}"
        )

    def drop_statement(self, principal_id: str) -> str:
        return f"DROP USER {quote_identifier(self.user_for(principal_id))}"

    # -- the three verbs ---------------------------------------------------

    async def ensure(self, principal_id: str) -> dict[str, Any]:
        """Create the user if absent, grant SELECT, and read both back.

        Idempotent: an existing user with the right SID is success. An existing
        user with the **wrong** SID is a refusal, not a silent re-grant —
        somebody else owns that name.
        """
        name = self.user_for(principal_id)
        before = await self.read_back(principal_id)
        if before.present and before.entra_id and not _same_id(
            before.entra_id, principal_id
        ):
            raise SqlGrantFailed(
                f"a database user named '{name}' already exists with a different "
                "Entra id. It was not created here and will not be changed here"
            )
        statements: list[str] = []
        if not before.present:
            statements.append(self.create_statement(principal_id))
        statements.append(self.grant_statement(principal_id))
        await self._execute(statements)
        after = await self.read_back(principal_id)
        if not after.present or not after.reads_bound_table:
            raise SqlGrantFailed(
                f"'{name}' was applied but did not read back with "
                f"{GRANTED_PERMISSION} on {self._target.qualified}"
            )
        return {
            **after.describe(),
            "applied": "already-present" if before.present else "created",
            "scope": self._target.qualified,
            "database": self._target.database,
        }

    async def read_back(self, principal_id: str) -> SqlGrantState:
        """What the database holds for this principal, right now."""
        name = self.user_for(principal_id)
        rows = await self._select(
            (
                (_PRINCIPAL_QUERY, {"name": name}),
                (_PERMISSION_QUERY, {"name": name}),
            )
        )
        principals, permissions = rows
        if not principals:
            return SqlGrantState(user=name, present=False)
        found = principals[0]
        return SqlGrantState(
            user=name,
            present=True,
            entra_id=str(found.get("entra_id") or ""),
            permissions=tuple(
                row
                for row in permissions
                if str(row.get("schema_name") or "").lower()
                == self._target.schema.lower()
                and str(row.get("object_name") or "").lower()
                == self._target.table.lower()
            ),
        )

    async def remove(self, principal_id: str) -> dict[str, Any]:
        """Revoke and drop **this module's** user, and read back that it is gone.

        Two ownership checks before anything is removed, because the credential
        running this is a database admin: the name must carry this module's
        prefix, and the stored SID must be the principal being revoked. A user
        that fails either is left alone and reported, not dropped.
        """
        name = self.user_for(principal_id)
        if not name.startswith(self._prefix):
            raise SqlGrantFailed(
                f"'{name}' does not carry the '{self._prefix}' prefix, so it was "
                "not created here and will not be dropped here"
            )
        state = await self.read_back(principal_id)
        if not state.present:
            return {
                "user": name,
                "deleted": 0,
                "present": False,
                "scope": self._target.qualified,
            }
        if state.entra_id and not _same_id(state.entra_id, principal_id):
            raise SqlGrantFailed(
                f"'{name}' holds a different Entra id than the principal being "
                "revoked; refusing to drop a user this deployment does not own"
            )
        await self._execute(
            [self.revoke_statement(principal_id), self.drop_statement(principal_id)]
        )
        after = await self.read_back(principal_id)
        return {
            "user": name,
            "deleted": 1,
            "present": after.present,
            "readsBoundTable": after.reads_bound_table,
            "scope": self._target.qualified,
        }

    # -- transport ---------------------------------------------------------

    def _token(self) -> Callable[[], str]:
        def issue() -> str:
            return str(self._credentials().get_token(SQL_SCOPE).token)

        return issue

    def _open(self) -> Any:
        try:
            return self._connect(
                self._target,
                token=self._token(),
                login_timeout_secs=self._login_timeout,
                query_timeout_secs=self._query_timeout,
                # Administrative statements are writes to the database's own
                # catalogue, so this connection is the one place read-only is
                # not asserted. Nothing else in this package opens one.
                readonly=False,
            )
        except (SqlUnavailable, TsqlRefused) as failure:
            raise SqlGrantFailed(str(failure)) from failure

    async def _execute(self, statements: list[str]) -> None:
        def run() -> None:
            connection = self._open()
            try:
                cursor = connection.cursor()
                try:
                    for statement in statements:
                        cursor.execute(statement)
                finally:
                    _close(cursor)
            finally:
                _close(connection)

        try:
            await asyncio.to_thread(run)
        except SqlGrantFailed:
            raise
        except Exception as failure:  # noqa: BLE001 - boundary: a failure is a refusal
            raise SqlGrantFailed(
                f"the grant statement failed: {type(failure).__name__}: "
                f"{str(failure)[:200]}"
            ) from failure

    async def _select(
        self, queries: tuple[tuple[str, dict[str, Any]], ...]
    ) -> list[list[dict[str, Any]]]:
        def run() -> list[list[dict[str, Any]]]:
            connection = self._open()
            collected: list[list[dict[str, Any]]] = []
            try:
                cursor = connection.cursor()
                try:
                    for statement, parameters in queries:
                        cursor.execute(statement, parameters)
                        columns = [
                            str(column[0]) for column in (cursor.description or ())
                        ]
                        collected.append(
                            [
                                {
                                    name: json_safe(value)
                                    for name, value in zip(columns, record)
                                }
                                for record in cursor
                            ]
                        )
                finally:
                    _close(cursor)
            finally:
                _close(connection)
            return collected

        try:
            return await asyncio.to_thread(run)
        except SqlGrantFailed:
            raise
        except Exception as failure:  # noqa: BLE001 - boundary: a failure is a refusal
            raise SqlGrantFailed(
                f"reading the grant back failed: {type(failure).__name__}: "
                f"{str(failure)[:200]}"
            ) from failure


def _same_id(found: str, principal_id: str) -> bool:
    try:
        return uuid.UUID(str(found)) == uuid.UUID(str(principal_id))
    except (AttributeError, TypeError, ValueError):
        return False


def _close(handle: Any) -> None:
    close = getattr(handle, "close", None)
    if close is not None:
        close()


__all__ = [
    "ENTRA_PRINCIPAL_TYPE",
    "GRANTED_PERMISSION",
    "USER_PREFIX",
    "SqlGrantFailed",
    "SqlGrantState",
    "SqlPrincipals",
    "entra_sid",
    "owned_user_name",
]
