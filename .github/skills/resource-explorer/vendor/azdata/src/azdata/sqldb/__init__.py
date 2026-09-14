"""Azure SQL Database — one read plane and one grant plane, and no write plane.

Two planes, and the gap between them is the design.

**The read plane parses.** ``SqlConnector`` runs one bounded ``SELECT`` over
TDS with an Entra token, and :mod:`azdata.sqldb.guard` decides what a bounded
``SELECT`` is by parsing the statement rather than scanning it for keywords.
T-SQL has too many ways past a keyword scan — ``SELECT INTO``, a batch, a CTE
ending in ``DELETE``, ``OPENROWSET`` — for the regular-expression floor the
other dialects use to be honest here.

**The grant plane is not Azure RBAC.** Data access to an Azure SQL table is
authorised by a principal *inside the database*, created with T-SQL.
``SqlPrincipals`` creates one from an Entra id with no directory lookup, grants
``SELECT`` on one table, reads both back, and removes only what it made. No
role assignment anywhere in Azure grants or revokes it, which is precisely why
it is here and named.

**There is no write plane, and no ``SqlItems`` will appear beside these two.**
Azure SQL is not one of the four services the Agent Canvas may write to, so an
``INSERT`` path would be a capability nothing is authorised to use.

The pure-Python driver is not an aesthetic choice: the deployed consumer builds
from PyPI with no package manager, so an ODBC driver manager cannot be
installed and ``pyodbc`` cannot travel.
"""

from __future__ import annotations

from azdata.sqldb.guard import (
    DEFAULT_TSQL_MAX_ROWS,
    MAX_TSQL_CHARS,
    SQL_IDENTIFIER,
    TSQL_DIALECT,
    TsqlRefused,
    guard_tsql,
    normalize_placeholders,
    quote_identifier,
    validate_tsql_read_only,
)
from azdata.sqldb.principals import (
    ENTRA_PRINCIPAL_TYPE,
    GRANTED_PERMISSION,
    USER_PREFIX,
    SqlGrantFailed,
    SqlGrantState,
    SqlPrincipals,
    entra_sid,
    owned_user_name,
)
from azdata.sqldb.read import (
    DEFAULT_LOGIN_TIMEOUT_SECS,
    DEFAULT_QUERY_TIMEOUT_SECS,
    SQL_PORT,
    SQL_SCOPE,
    SQL_SUFFIX,
    TABLE_LISTING,
    SqlConnector,
    SqlTarget,
    SqlUnavailable,
    bind_names,
    json_safe,
    list_tables,
    open_connection,
    sql_server_host,
    sql_target_from_resource_id,
)

__all__ = [
    "DEFAULT_LOGIN_TIMEOUT_SECS",
    "DEFAULT_QUERY_TIMEOUT_SECS",
    "DEFAULT_TSQL_MAX_ROWS",
    "ENTRA_PRINCIPAL_TYPE",
    "GRANTED_PERMISSION",
    "MAX_TSQL_CHARS",
    "SQL_IDENTIFIER",
    "SQL_PORT",
    "SQL_SCOPE",
    "SQL_SUFFIX",
    "TABLE_LISTING",
    "TSQL_DIALECT",
    "USER_PREFIX",
    "SqlConnector",
    "SqlGrantFailed",
    "SqlGrantState",
    "SqlPrincipals",
    "SqlTarget",
    "SqlUnavailable",
    "TsqlRefused",
    "bind_names",
    "entra_sid",
    "guard_tsql",
    "json_safe",
    "list_tables",
    "normalize_placeholders",
    "open_connection",
    "owned_user_name",
    "quote_identifier",
    "sql_server_host",
    "sql_target_from_resource_id",
    "validate_tsql_read_only",
]
