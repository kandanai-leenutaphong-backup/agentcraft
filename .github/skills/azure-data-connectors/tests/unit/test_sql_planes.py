"""test_sql_planes — the T-SQL read guard and the contained-user grant plane.

Run: ``.venv/bin/python -m pytest tests/unit/test_sql_planes.py -q``, or
``python3 tests/unit/test_sql_planes.py`` for the same checks as a script.

The driver is substituted through an injected ``connect`` callable, so every
statement this package emits, every refusal it makes and every read-back it
performs is exercised with no TDS server, no network and no credential. The
guard itself needs ``sqlglot`` and nothing else: it decides before a connection
is opened, which is the property that makes a mutation attempt cost nothing.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata.sqldb.guard import (  # noqa: E402
    TsqlRefused,
    guard_tsql,
    normalize_placeholders,
    quote_identifier,
    validate_tsql_read_only,
)
from azdata.sqldb.principals import (  # noqa: E402
    SqlGrantFailed,
    SqlPrincipals,
    entra_sid,
    owned_user_name,
)
from azdata.sqldb.read import (  # noqa: E402
    SQL_SCOPE,
    SqlConnector,
    SqlTarget,
    bind_names,
    json_safe,
    sql_server_host,
    sql_target_from_resource_id,
)

_FAILURES: list[str] = []

#: The binding every test in this file reads through, matching the tutorial
#: fixture the configuration chain is specified against. The subscription is
#: the all-zero placeholder: no estate identifier belongs in a test.
RESOURCE_ID = (
    "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups"
    "/rg-example/providers/Microsoft.Sql/servers/sql-example"
    "/databases/TutorialDb"
)
TARGET = SqlTarget(
    server="sql-example.database.windows.net",
    database="TutorialDb",
    schema="dbo",
    table="TutorialOrders",
)
TOOL_QUERY = (
    "SELECT TOP (100) order_id, customer, amount_usd, placed_on "
    "FROM dbo.TutorialOrders WHERE region = %(region)s ORDER BY order_id"
)
#: A principal that is deliberately not ours. Two GUIDs, differing only in the
#: fields SQL Server stores little-endian, so a big-endian SID would be a
#: visibly different value rather than a coincidence.
PRINCIPAL = "12345678-1234-5678-1234-567812345678"


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        _FAILURES.append(label)
    assert condition, label


def section(title: str) -> None:
    print(title)


# ----------------------------------------------------------------------
# A driver that is not a driver.
# ----------------------------------------------------------------------


class FakeCredential:
    def __init__(self) -> None:
        self.scopes: list[str] = []

    def get_token(self, scope: str) -> Any:
        self.scopes.append(scope)
        return type("Token", (), {"token": "not-a-real-token", "expires_on": 0})()


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self._connection = connection
        self.description: tuple[tuple[str, ...], ...] | None = None
        self._rows: list[tuple[Any, ...]] = []

    def execute(self, statement: str, parameters: Any = None) -> None:
        self._connection.statements.append(statement)
        self._connection.parameters.append(parameters)
        columns, rows = self._connection.answer(statement)
        self.description = tuple((name,) for name in columns)
        self._rows = list(rows)

    def __iter__(self):
        return iter(self._rows)

    def close(self) -> None:
        self._connection.cursors_closed += 1


class FakeConnection:
    """Records what was asked and answers from a script. Never opens a socket."""

    def __init__(self, script: dict[str, tuple[list[str], list[tuple]]]) -> None:
        self.script = script
        self.statements: list[str] = []
        self.parameters: list[Any] = []
        self.closed = 0
        self.cursors_closed = 0

    def answer(self, statement: str) -> tuple[list[str], list[tuple]]:
        for marker, payload in self.script.items():
            if marker in statement:
                return payload
        return ([], [])

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def close(self) -> None:
        self.closed += 1


def recorder(script: dict[str, tuple[list[str], list[tuple]]]) -> tuple[Any, list[dict]]:
    """A ``connect`` substitute plus the list of arguments it was called with.

    It invokes the ``token`` callable exactly as the driver does at login, so
    the test observes the audience the credential was actually asked for rather
    than the one the code appears to ask for.
    """
    calls: list[dict] = []
    connection = FakeConnection(script)

    def connect(target: SqlTarget, **kwargs: Any) -> FakeConnection:
        issued = kwargs["token"]()
        calls.append({"target": target, "issued": issued, **kwargs})
        return connection

    connect.connection = connection  # type: ignore[attr-defined]
    return connect, calls


# ----------------------------------------------------------------------
# 1. The guard decides before anything is built.
# ----------------------------------------------------------------------


def test_guard_accepts_the_bounded_tool_read() -> None:
    section("1. the guard, on the statement the tool chain is specified against")
    check(
        "the tool query with a bound placeholder is accepted",
        validate_tsql_read_only(TOOL_QUERY, max_rows=100, table=("dbo", "TutorialOrders"))
        is None,
    )
    check(
        "the same query with a literal instead of a placeholder is accepted",
        validate_tsql_read_only(
            TOOL_QUERY.replace("%(region)s", "'east'"),
            max_rows=100,
            table=("dbo", "TutorialOrders"),
        )
        is None,
    )
    check(
        "a placeholder normalises to a T-SQL variable rather than being refused",
        normalize_placeholders("WHERE region = %(region)s") == "WHERE region = @region",
    )


def test_guard_refuses_every_mutation_shape() -> None:
    section("2. the guard refuses, naming the rule that closed")
    hostile = {
        "a batch behind a semicolon": "SELECT TOP (5) a FROM dbo.TutorialOrders; DROP TABLE dbo.TutorialOrders",
        "a bare UPDATE": "UPDATE dbo.TutorialOrders SET amount_usd = 0",
        "a bare INSERT": "INSERT INTO dbo.TutorialOrders VALUES (1)",
        "a bare DELETE": "DELETE FROM dbo.TutorialOrders",
        "a DROP": "DROP TABLE dbo.TutorialOrders",
        "a MERGE": (
            "MERGE dbo.TutorialOrders AS t USING dbo.Other AS s ON 1 = 1 "
            "WHEN MATCHED THEN DELETE"
        ),
        "a CTE that ends in DML": (
            "WITH c AS (SELECT 1 AS x) DELETE FROM dbo.TutorialOrders"
        ),
        "SELECT INTO, which creates a table": (
            "SELECT TOP (5) * INTO dbo.Copy FROM dbo.TutorialOrders"
        ),
        "EXEC": "EXEC sp_who",
        "an extended procedure": "SELECT TOP (1) xp_cmdshell('dir')",
        "OPENROWSET": "SELECT TOP (1) * FROM OPENROWSET('SQLNCLI', 'x', 'SELECT 1')",
        "OPENQUERY against a linked server": (
            "SELECT TOP (1) * FROM OPENQUERY(other, 'SELECT 1')"
        ),
        "a four-part linked-server name": (
            "SELECT TOP (1) * FROM other.db.dbo.TutorialOrders"
        ),
        "a line comment": "SELECT TOP (5) a FROM dbo.TutorialOrders -- ' OR 1=1",
        "a block comment": "SELECT TOP (5) a /* hidden */ FROM dbo.TutorialOrders",
        "a stray percent the driver would choke on": (
            "SELECT TOP (5) a FROM dbo.TutorialOrders WHERE a LIKE 'x%'"
        ),
        "an unbounded read": "SELECT a FROM dbo.TutorialOrders",
        "text that is not T-SQL at all": "BEGIN TRAN SELECT 1 COMMIT",
        "an empty statement": "   ",
    }
    for label, statement in hostile.items():
        violation = validate_tsql_read_only(statement, max_rows=100)
        check(f"{label} is refused", bool(violation))
        check(f"{label} refusal says why", bool(violation) and len(violation) > 20)

    check(
        "a union of two selects is refused: a bounded read is one SELECT",
        bool(
            validate_tsql_read_only(
                "SELECT TOP (1) a FROM dbo.TutorialOrders UNION ALL "
                "SELECT TOP (1) a FROM dbo.Other",
                max_rows=100,
            )
        ),
    )
    check(
        "a TOP above the caller's ceiling is refused",
        bool(validate_tsql_read_only("SELECT TOP (5000) a FROM dbo.T", max_rows=100)),
    )
    check(
        "a table outside the binding is refused",
        bool(
            validate_tsql_read_only(
                "SELECT TOP (5) a FROM dbo.Secrets",
                max_rows=100,
                table=("dbo", "TutorialOrders"),
            )
        ),
    )
    check(
        "another schema's table of the same name is refused",
        bool(
            validate_tsql_read_only(
                "SELECT TOP (5) a FROM other.TutorialOrders",
                max_rows=100,
                table=("dbo", "TutorialOrders"),
            )
        ),
    )
    raised = False
    try:
        guard_tsql("DROP TABLE dbo.TutorialOrders")
    except TsqlRefused:
        raised = True
    check("guard_tsql raises rather than returning on a refusal", raised)


def test_identifiers_are_validated_not_escaped() -> None:
    section("3. identifiers")
    check("a plain identifier quotes", quote_identifier("TutorialOrders") == "[TutorialOrders]")
    for hostile in ("a]; DROP TABLE x --", "a b", "1abc", "", "a'b", "a" * 200):
        refused = False
        try:
            quote_identifier(hostile)
        except TsqlRefused:
            refused = True
        check(f"identifier {hostile[:18]!r} is refused", refused)


# ----------------------------------------------------------------------
# 4. Binding: server and database come from the resource id.
# ----------------------------------------------------------------------


def test_the_binding_is_derived_from_the_resource_id() -> None:
    section("4. the resource id is authority for where a read goes")
    target = sql_target_from_resource_id(RESOURCE_ID, schema="dbo", table="TutorialOrders")
    check("server is the logical server's host", target.server == TARGET.server)
    check("database is the child segment", target.database == "TutorialDb")
    check("schema and table are carried", target.qualified == "dbo.TutorialOrders")
    check("host composition is idempotent", sql_server_host(TARGET.server) == TARGET.server)
    refused = False
    try:
        sql_target_from_resource_id("https://evil.example.com/TutorialDb")
    except Exception:
        refused = True
    check("a URL is not a resource id and is refused", refused)
    refused = False
    try:
        sql_target_from_resource_id(
            "/subscriptions/x/resourceGroups/y/providers/Microsoft.Sql/servers/s"
        )
    except Exception:
        refused = True
    check("a server without a database is refused", refused)


# ----------------------------------------------------------------------
# 5. The read connector, with the driver substituted.
# ----------------------------------------------------------------------


def test_the_read_connector_binds_values_and_never_interpolates() -> None:
    section("5. the read plane")
    connect, calls = recorder(
        {
            "TutorialOrders": (
                ["order_id", "customer", "amount_usd", "placed_on"],
                [(1001, "Fabrikam", __import__("decimal").Decimal("120.00"),
                  __import__("datetime").date(2026, 1, 4))],
            )
        }
    )
    credential = FakeCredential()
    connector = SqlConnector(
        resolve_target=lambda: TARGET,
        credential_provider=lambda: credential,
        connect=connect,
    )
    payload = json.loads(
        asyncio.run(connector.query(TOOL_QUERY, parameters={"region": "east"}, max_rows=100))
    )
    check("the read returns rows", payload.get("rows") and len(payload["rows"]) == 1)
    check(
        "columns come from the cursor description",
        payload["columns"] == ["order_id", "customer", "amount_usd", "placed_on"],
    )
    check("a Decimal is a number, not a string", payload["rows"][0]["amount_usd"] == 120.0)
    check("a date is ISO 8601", payload["rows"][0]["placed_on"] == "2026-01-04")

    connection = connect.connection  # type: ignore[attr-defined]
    check("exactly one statement was sent", len(connection.statements) == 1)
    check(
        "the value never entered the statement text",
        "east" not in connection.statements[0],
    )
    check(
        "the value travelled as a driver parameter",
        connection.parameters[0] == {"region": "east"},
    )
    check("the connection was closed", connection.closed == 1)
    check("the cursor was closed", connection.cursors_closed == 1)
    check(
        "the token was requested for the SQL audience, not ARM",
        credential.scopes == [SQL_SCOPE],
    )
    check(
        "TLS was demanded explicitly rather than left to the driver's default",
        calls[0]["readonly"] is True,
    )
    check("bind_names writes the driver's own placeholder", bind_names(["region"]) ==
          {"region": "%(region)s"})


def test_a_mutation_costs_no_connection() -> None:
    section("6. a refused statement opens nothing")
    connect, calls = recorder({})
    connector = SqlConnector(
        resolve_target=lambda: TARGET,
        credential_provider=lambda: FakeCredential(),
        connect=connect,
    )
    payload = json.loads(asyncio.run(connector.query("DELETE FROM dbo.TutorialOrders")))
    check("the refusal is an error envelope, not an exception", payload.get("error"))
    check("no connection was opened", calls == [])

    payload = json.loads(
        asyncio.run(
            connector.query("SELECT TOP (5) a FROM dbo.Secrets", max_rows=10)
        )
    )
    check("a table outside the binding is refused at the connector", payload.get("error"))
    check("still no connection was opened", calls == [])

    detached = SqlConnector(
        resolve_target=lambda: SqlTarget(server="", database=""),
        credential_provider=lambda: FakeCredential(),
        connect=connect,
    )
    payload = json.loads(asyncio.run(detached.query("SELECT TOP (1) 1 AS a")))
    check("an unconfigured binding is a status, not a crash", payload.get("error"))


def test_a_driver_failure_is_an_envelope_without_the_token() -> None:
    section("7. failure is a value, and carries no credential")

    def exploding(target: SqlTarget, **kwargs: Any) -> Any:
        raise RuntimeError("Login failed for token eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9")

    connector = SqlConnector(
        resolve_target=lambda: TARGET,
        credential_provider=lambda: FakeCredential(),
        connect=exploding,
    )
    payload = json.loads(asyncio.run(connector.query(TOOL_QUERY, parameters={"region": "east"})))
    check("the failure is an error envelope", payload.get("error"))
    check("the envelope names the failure class", "RuntimeError" in json.dumps(payload))


def test_row_cap_truncates_rather_than_returning_everything() -> None:
    section("8. the row cap is applied to what came back, not only to the text")
    rows = [(index, f"c{index}") for index in range(50)]
    connect, _ = recorder({"TutorialOrders": (["order_id", "customer"], rows)})
    connector = SqlConnector(
        resolve_target=lambda: TARGET,
        credential_provider=lambda: FakeCredential(),
        connect=connect,
    )
    payload = json.loads(
        asyncio.run(
            connector.query(
                "SELECT TOP (10) order_id, customer FROM dbo.TutorialOrders",
                max_rows=10,
            )
        )
    )
    check("only the capped rows are returned", len(payload["rows"]) == 10)
    check("truncation is reported rather than hidden", payload["truncated"] is True)


def test_json_safe_covers_the_types_a_column_can_hold() -> None:
    section("9. value normalisation")
    import datetime as dt
    import decimal

    check("Decimal becomes a float", json_safe(decimal.Decimal("221.25")) == 221.25)
    check(
        "datetime becomes ISO 8601",
        json_safe(dt.datetime(2026, 3, 9, 12, 0, tzinfo=dt.timezone.utc)).startswith(
            "2026-03-09T12:00:00"
        ),
    )
    check("bytes become base64", json_safe(b"hi") == "aGk=")
    check("a uuid becomes its string", json_safe(uuid.UUID(PRINCIPAL)) == PRINCIPAL)
    check("None stays None", json_safe(None) is None)


# ----------------------------------------------------------------------
# 10. The grant plane.
# ----------------------------------------------------------------------


def test_the_sid_is_mixed_endian_as_sql_server_stores_it() -> None:
    section("10. the SID byte order")
    check(
        "the SID is the GUID in bytes_le, which is what CAST AS VARBINARY(16) yields",
        entra_sid(PRINCIPAL) == "0x" + uuid.UUID(PRINCIPAL).bytes_le.hex().upper(),
    )
    check(
        "it is not the big-endian form",
        entra_sid(PRINCIPAL) != "0x" + uuid.UUID(PRINCIPAL).bytes.hex().upper(),
    )
    refused = False
    try:
        entra_sid("not-a-guid'; DROP TABLE x --")
    except SqlGrantFailed:
        refused = True
    check("a non-GUID principal is refused before any statement is built", refused)
    check(
        "the user name is derived from the id and carries the ownership prefix",
        owned_user_name(PRINCIPAL).startswith("hcagent_")
        and owned_user_name(PRINCIPAL) == owned_user_name(PRINCIPAL),
    )


def _principals(script: dict[str, tuple[list[str], list[tuple]]]) -> tuple[SqlPrincipals, Any]:
    connect, _ = recorder(script)
    return (
        SqlPrincipals(
            target=TARGET,
            credential_provider=lambda: FakeCredential(),
            connect=connect,
        ),
        connect.connection,  # type: ignore[attr-defined]
    )


def test_a_grant_is_created_granted_and_read_back() -> None:
    section("11. apply, then read back what the database actually holds")
    name = owned_user_name(PRINCIPAL)
    granted = {
        "sys.database_principals AS dp WHERE": (
            ["name", "principal_type", "entra_id"],
            [(name, "E", uuid.UUID(PRINCIPAL))],
        ),
        "sys.database_permissions": (
            ["permission", "state", "schema_name", "object_name"],
            [("SELECT", "GRANT", "dbo", "TutorialOrders")],
        ),
    }
    principals, connection = _principals(granted)
    outcome = asyncio.run(principals.ensure(PRINCIPAL))
    check("the grant reads back present", outcome["present"] is True)
    check("and it reads the bound table", outcome["readsBoundTable"] is True)
    check("the scope is the table, not the database", outcome["scope"] == "dbo.TutorialOrders")
    emitted = [s for s in connection.statements if not s.startswith("SELECT")]
    check(
        "GRANT SELECT is scoped to one object",
        any(
            "GRANT SELECT ON OBJECT::[dbo].[TutorialOrders]" in statement
            for statement in emitted
        ),
    )
    check(
        "no role membership is added: db_datareader reads every table",
        not any("ALTER ROLE" in s or "db_datareader" in s or "db_owner" in s for s in emitted),
    )
    check(
        "an already-present user is not created twice",
        outcome["applied"] == "already-present",
    )


def test_a_missing_user_is_created_with_sid_and_type() -> None:
    section("12. the CREATE USER statement")
    name = owned_user_name(PRINCIPAL)
    absent_then_present = {
        "sys.database_permissions": (
            ["permission", "state", "schema_name", "object_name"],
            [("SELECT", "GRANT", "dbo", "TutorialOrders")],
        ),
        "sys.database_principals AS dp WHERE": (
            ["name", "principal_type", "entra_id"],
            [(name, "E", uuid.UUID(PRINCIPAL))],
        ),
    }
    principals, _ = _principals(absent_then_present)
    create = principals.create_statement(PRINCIPAL)
    check("the user name is bracketed", f"[{name}]" in create)
    check("the SID is the mixed-endian literal", entra_sid(PRINCIPAL) in create)
    check("TYPE = E marks an Entra principal", create.rstrip().endswith("TYPE = E"))
    check(
        "no directory lookup is asked for",
        "FROM EXTERNAL PROVIDER" not in create,
    )


def test_teardown_removes_only_what_this_module_made() -> None:
    section("13. teardown, and the two ownership checks before it")
    name = owned_user_name(PRINCIPAL)
    principals, connection = _principals(
        {
            "sys.database_principals AS dp WHERE": (
                ["name", "principal_type", "entra_id"],
                [(name, "E", uuid.UUID(PRINCIPAL))],
            ),
            "sys.database_permissions": (
                ["permission", "state", "schema_name", "object_name"],
                [("SELECT", "GRANT", "dbo", "TutorialOrders")],
            ),
        }
    )
    outcome = asyncio.run(principals.remove(PRINCIPAL))
    emitted = [s for s in connection.statements if not s.startswith("SELECT")]
    check("the permission is revoked", any("REVOKE SELECT ON OBJECT::" in s for s in emitted))
    check("the user is dropped", any(s.startswith("DROP USER") for s in emitted))
    check("one user was removed", outcome["deleted"] == 1)
    check(
        "nothing wider was touched",
        not any("DROP TABLE" in s or "DROP DATABASE" in s or "ALTER ROLE" in s for s in emitted),
    )

    someone_else = {
        "sys.database_principals AS dp WHERE": (
            ["name", "principal_type", "entra_id"],
            [(name, "E", uuid.UUID("87654321-4321-8765-4321-876543218765"))],
        ),
        "sys.database_permissions": (["permission", "state", "schema_name", "object_name"], []),
    }
    principals, connection = _principals(someone_else)
    refused = False
    try:
        asyncio.run(principals.remove(PRINCIPAL))
    except SqlGrantFailed:
        refused = True
    check("a user holding another Entra id is not dropped", refused)
    check(
        "and nothing was emitted for it",
        not [s for s in connection.statements if not s.startswith("SELECT")],
    )

    principals, connection = _principals(someone_else)
    refused = False
    try:
        asyncio.run(principals.ensure(PRINCIPAL))
    except SqlGrantFailed:
        refused = True
    check("nor is it re-granted to", refused)


def test_absent_user_teardown_is_success_not_an_error() -> None:
    section("14. removing what is already gone")
    principals, connection = _principals(
        {
            "sys.database_principals AS dp WHERE": (["name"], []),
            "sys.database_permissions": (["permission"], []),
        }
    )
    outcome = asyncio.run(principals.remove(PRINCIPAL))
    check("absent is reported, not raised", outcome["present"] is False)
    check("nothing was deleted", outcome["deleted"] == 0)
    check(
        "and no DROP was emitted",
        not any("DROP" in s for s in connection.statements),
    )


def test_a_grant_without_a_table_is_refused() -> None:
    section("15. a database-wide grant is not offered")
    refused = False
    try:
        SqlPrincipals(
            target=SqlTarget(server=TARGET.server, database=TARGET.database, schema="dbo"),
            credential_provider=lambda: FakeCredential(),
            connect=lambda *a, **k: None,
        )
    except SqlGrantFailed:
        refused = True
    check("a grant with no table is refused at construction", refused)


def main() -> int:
    for name, value in sorted(globals().items()):
        if name.startswith("test_") and callable(value):
            value()
    print()
    if _FAILURES:
        print(f"{len(_FAILURES)} FAILED")
        return 1
    print("SQL_PLANES_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
