#!/usr/bin/env python3
"""Worked example: the three planes an Azure RBAC teardown does not touch.

Revoke every Azure RBAC assignment an identity holds and it can still read
Cosmos DB, still query an Azure Data Explorer database, and still SELECT from a
SQL table — because none of those grants is an Azure RBAC assignment. This
example makes each one explicitly, shows that Cosmos duplicates rather than
409s, and prints the exact T-SQL the SQL plane would run.

Run it:  python3 examples/native_planes.py
"""

from __future__ import annotations

from azaccess import (
    AccessDeclaration,
    CosmosSqlRbacProvider,
    KustoDatabaseProvider,
    RecordingSqlExecutor,
    RecordingTransport,
    Response,
    SqlDatabaseUserProvider,
    lookup_role,
    sql_grant_statements,
    user_assigned_identity,
)

TENANT = "11111111-1111-1111-1111-111111111111"
SUBSCRIPTION = "22222222-2222-2222-2222-222222222222"
PRINCIPAL = "33333333-3333-3333-3333-333333333333"
RESOURCE_GROUP = f"/subscriptions/{SUBSCRIPTION}/resourceGroups/example-rg"

COSMOS_ACCOUNT = (
    f"{RESOURCE_GROUP}/providers/Microsoft.DocumentDB/databaseAccounts/example-cosmos"
)
COSMOS_SCOPE = f"{COSMOS_ACCOUNT}/dbs/appdb/colls/items"
KUSTO_DATABASE = (
    f"{RESOURCE_GROUP}/providers/Microsoft.Kusto/clusters/example-cluster"
    f"/databases/telemetry"
)
SQL_DATABASE = (
    f"{RESOURCE_GROUP}/providers/Microsoft.Sql/servers/example-server/databases/appdb"
)

identity = user_assigned_identity(
    principal_id=PRINCIPAL, tenant_id=TENANT, display_name="analytics-worker"
)


def main() -> int:
    # Every one of these roles is on a plane of its own. That is the point.
    planes = {
        lookup_role("Cosmos DB Built-in Data Reader").plane,
        lookup_role("Kusto Database Viewer").plane,
        lookup_role("SQL Table Data Reader").plane,
    }
    assert planes == {"cosmos-sql-rbac", "kusto-database", "sql-database-user"}
    assert "azure-rbac" not in planes, (
        "if any of these were Azure RBAC, an ARM teardown would remove it"
    )

    # -- Cosmos: no 409, so a blind PUT would mint a second assignment -----
    cosmos_declaration = AccessDeclaration(
        principal=identity, role="Cosmos DB Built-in Data Reader",
        scope=COSMOS_SCOPE,
    )
    existing = {
        "id": f"{COSMOS_ACCOUNT}/sqlRoleAssignments/already-there",
        "name": "already-there",
        "properties": {
            "principalId": PRINCIPAL,
            "roleDefinitionId": (
                f"{COSMOS_ACCOUNT}/sqlRoleDefinitions/"
                f"00000000-0000-0000-0000-000000000001"
            ),
            "scope": COSMOS_SCOPE,
        },
    }
    transport = RecordingTransport().script(
        "GET", "sqlRoleAssignments", Response(status=200, body={"value": [existing]})
    )
    cosmos = CosmosSqlRbacProvider(transport)
    record = cosmos.create(cosmos_declaration, plan_id="example")
    assert record.source == "adopted", record.to_dict()
    assert not transport.urls("PUT"), "read-before-write is what prevents the duplicate"

    # -- Kusto: role names are words, and the principal type is not ARM's --
    kusto_transport = RecordingTransport()
    kusto_transport.script("GET", "principalAssignments",
                           Response(status=200, body={"value": []}))
    kusto_transport.script(
        "PUT", "principalAssignments/",
        Response(status=200, body={
            "id": f"{KUSTO_DATABASE}/principalAssignments/example",
            "properties": {"principalId": PRINCIPAL, "role": "Viewer"}}),
    )
    kusto = KustoDatabaseProvider(kusto_transport, name_factory=lambda: "example")
    kusto_record = kusto.create(
        AccessDeclaration(principal=identity, role="Kusto Database Viewer",
                          scope=KUSTO_DATABASE),
        plan_id="example",
    )
    body = kusto_transport.bodies("PUT")[0]["properties"]
    assert body["role"] == "Viewer"
    assert body["principalType"] == "App"
    assert kusto_record.assignment_id.endswith("/principalAssignments/example")

    # -- SQL: not an Azure resource; statements, not requests --------------
    sql_declaration = AccessDeclaration(
        principal=identity, role="SQL Table Data Reader", scope=SQL_DATABASE,
        target={"schema": "dbo", "table": "events", "user_name": "analytics-worker"},
    )
    statements = sql_grant_statements(sql_declaration)
    for statement in statements:
        print(statement)
    assert statements == (
        "IF NOT EXISTS (SELECT 1 FROM sys.database_principals "
        "WHERE name = N'analytics-worker') "
        "CREATE USER [analytics-worker] FROM EXTERNAL PROVIDER;",
        "GRANT SELECT ON [dbo].[events] TO [analytics-worker];",
    ), "the CREATE is guarded, so a second apply is not error 15023"

    executor = RecordingSqlExecutor(rows=[{
        "user_name": "analytics-worker", "permission_name": "SELECT",
        "class_desc": "OBJECT_OR_COLUMN", "state_desc": "GRANT",
        "major_id": 1234, "minor_id": 0,
    }])
    sql = SqlDatabaseUserProvider(executor, owned_prefix="analytics-")
    sql_record = sql.create(sql_declaration, plan_id="example")
    assert sql_record.plane == "sql-database-user"
    assert sql_record.source == "adopted", (
        "the permission was already there, so this run did not create it and "
        "may not later drop it"
    )
    assert any("sys.database_permissions" in s for s in executor.statements), (
        "the read-back is bound to the declared object, not to the user alone"
    )

    print("three grants, three planes, none of them visible to an Azure RBAC "
          "assignment list")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
