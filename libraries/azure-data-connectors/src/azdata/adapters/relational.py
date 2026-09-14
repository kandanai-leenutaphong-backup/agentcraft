from __future__ import annotations

import asyncio
import math
import re
import time
from collections.abc import Mapping
from types import SimpleNamespace
from urllib.parse import urlsplit

from .base import AdapterResult, RecordAdapter
from ..contracts import Caveat, ConfigurationError, ContentValue, ItemResult, OperationCapability, RecordKey, VerificationResult, plain
from ..transport import OperationFault


def database_fault(error, mutation):
    state = getattr(error, "sqlstate", None)
    if state == "23505" or type(error).__name__ == "IntegrityError":
        return OperationFault("conflict", "database_constraint_conflict")
    if state in {"42501", "28000", "28P01"}:
        return OperationFault("denied", "database_access_denied")
    return OperationFault("unknown" if mutation else "failed", "database_operation_failed")


class RelationalAdapter(RecordAdapter):
    content_kinds = ("json", "row")
    scalar_keys = True
    caveats = (Caveat("key_constraint_required", "Configured key fields must have a database unique constraint; no schema or roles are created automatically."),
               Caveat("merge_not_replace", "Writes change supplied columns. Full row replacement and implicit row-version strategies are not supplied."),
               Caveat("driver_result_buffer", "Driver and server enforce row/time bounds; output byte limits apply after native value decoding."))

    def __init__(self, config):
        super().__init__(config)
        if (set(config.target.coordinates) != {"database", "schema", "table"}
                or any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", value) for value in config.target.coordinates.values())
                or config.partition_key_field is not None):
            raise ConfigurationError("Relational targets require database, schema and table identifiers, without a partition field")
        if self.service == "postgresql" and config.database_user is None:
            raise ConfigurationError("PostgreSQL requires the configured Entra database role name")
        for operation in ("create", "read", "update", "upsert", "delete"):
            evidence = ("none", "presence") if operation == "read" else ("none", "acknowledgment", "absence") if operation == "delete" else ("none", "acknowledgment", "presence", "content")
            self.capabilities[operation] = OperationCapability("supported", modes=("merge",) if operation in {"update", "upsert"} else (),
                guarantees=("create_if_absent",) if operation == "create" else (), verification=evidence, reason="")
        self.capabilities["query"] = OperationCapability("supported", dialects=(self.dialect,), reason="")
        self.capabilities["schema"] = OperationCapability("supported", actions=("read",), verification=("none", "schema"), reason="")

    def create_client(self, session, kind):
        import sqlglot

        if session._transport._injected is not None:
            raise OperationFault("unsupported", "http_transport_not_native_driver")
        if self.service == "postgresql":
            import psycopg
        else:
            import mssql_python
        return self

    async def close(self):
        return None

    def validate(self, operation, request, evidence):
        for record in getattr(request, "records", ()):
            if record.expected_version is not None:
                raise OperationFault("unsupported", "row_version_not_configured")
            if any(not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in record.content.data):
                raise OperationFault("invalid", "invalid_column_name")
            if any(isinstance(value, (Mapping, tuple, list)) for value in record.content.data.values()):
                raise OperationFault("unsupported", "structured_column_type_unsupported")
            if operation == "update" and not set(record.content.data) - set(self.key_fields):
                raise OperationFault("invalid", "update_columns_required")
        if any(version is not None for version in getattr(request, "expected_versions", ())):
            raise OperationFault("unsupported", "row_version_not_configured")
        if operation == "query":
            if request.continuation or request.projection:
                raise OperationFault("unsupported", "native_projection_without_continuation")
            self._query(request, 1)
        if operation == "schema" and (request.definition is not None or request.expected_version is not None):
            raise OperationFault("invalid", "schema_read_has_no_definition")
        if evidence == "content" and operation == "create":
            raise OperationFault("unsupported", "server_defaults_prevent_exact_content")

    def identifier(self, name):
        from sqlglot import exp

        return exp.to_identifier(name, quoted=True).sql(dialect=self.parser_dialect)

    @property
    def table(self):
        return ".".join(self.identifier(self.config.target.coordinates[name]) for name in ("schema", "table"))

    @property
    def marker(self):
        return "%s" if self.service == "postgresql" else "?"

    def predicate(self, key):
        return " AND ".join(f"{self.identifier(name)} = {self.marker}" for name in self.key_fields), tuple(key.parts[name] for name in self.key_fields)

    def _query(self, request, limit):
        try:
            import sqlglot
            from sqlglot import exp
            from sqlglot.errors import ParseError
        except ImportError:
            raise OperationFault("failed", f"missing_dependency_{self.service}") from None
        try:
            statements = sqlglot.parse(request.expression, read=self.parser_dialect)
            if len(statements) != 1 or not isinstance(statements[0], exp.Select):
                raise OperationFault("denied", "read_query_required")
            query = statements[0]
            if any(query.find(kind) is not None for kind in (exp.Insert, exp.Update, exp.Delete, exp.Into, exp.Lock, exp.Command)):
                raise OperationFault("denied", "query_mutation_refused")
            safe_functions = {"COUNT", "SUM", "AVG", "MIN", "MAX", "COALESCE", "LOWER", "UPPER", "LENGTH", "CAST", "TRY_CAST"}
            if any(function.sql_name() not in safe_functions for function in query.find_all(exp.Func)):
                raise OperationFault("unsupported", "query_function_unsupported")
            for table in query.find_all(exp.Table):
                if (not isinstance(table.this, exp.Identifier) or table.name != self.config.target.coordinates["table"]
                        or table.catalog or table.db not in {"", self.config.target.coordinates["schema"]}):
                    raise OperationFault("denied", "query_table_outside_scope")
                table.set("db", exp.to_identifier(self.config.target.coordinates["schema"], quoted=True))
            parameters = []
            names = set()
            for placeholder in list(query.find_all(exp.Placeholder)):
                name = placeholder.name
                if name not in request.parameters:
                    raise OperationFault("invalid", "query_parameter_missing")
                parameters.append(request.parameters[name])
                names.add(name)
                placeholder.replace(exp.Var(this=self.marker))
            if names != set(request.parameters) or query.find(exp.Parameter):
                raise OperationFault("invalid", "query_parameter_mismatch")
            if query.args.get("limit") is not None:
                existing = query.args["limit"].expression
                if not isinstance(existing, exp.Literal) or not existing.is_int or int(existing.this) < 0:
                    raise OperationFault("invalid", "literal_query_limit_required")
                limit = min(limit, int(existing.this))
            query.limit(limit, copy=False)
            return query.sql(dialect=self.parser_dialect, identify=True), tuple(parameters)
        except ParseError:
            raise OperationFault("invalid", "invalid_query_syntax") from None

    async def _run(self, statement, parameters, context, *, mutation=False, fetch=False, readonly=False):
        context.session.client("driver")
        async def invoke():
            token = await context.session.credential.get_token(self.scope)
            context.attempts += 1
            if self.service == "postgresql":
                return await self._postgres(statement, parameters, context, token, mutation, fetch, readonly)
            task = asyncio.create_task(asyncio.to_thread(self._sql, statement, parameters, context, token, mutation, fetch))
            try:
                return await asyncio.shield(task)
            except asyncio.CancelledError:
                try:
                    await asyncio.shield(task)
                except Exception:
                    pass
                raise
        return await context.invoke(invoke, mutation=mutation)

    async def _postgres(self, statement, parameters, context, token, mutation, fetch, readonly):
        import psycopg
        from psycopg.rows import dict_row

        connection = None
        try:
            endpoint = urlsplit(self.config.endpoint)
            connection = await psycopg.AsyncConnection.connect(host=endpoint.hostname, port=endpoint.port or 5432,
                dbname=self.config.target.coordinates["database"], user=self.config.database_user, password=token.token,
                sslmode="verify-full", connect_timeout=max(1, math.ceil(context.deadline - time.monotonic())), row_factory=dict_row)
            async with connection.transaction():
                async with connection.cursor() as cursor:
                    if readonly:
                        await cursor.execute("SET TRANSACTION READ ONLY")
                    timeout = max(1, math.ceil((context.deadline - time.monotonic()) * 1000))
                    await cursor.execute("SELECT set_config('statement_timeout', %s, true)", (str(timeout),))
                    context.submitted = True
                    await cursor.execute(statement, parameters)
                    rows = await cursor.fetchmany(context.limits.max_items + 1) if fetch else []
                    count = cursor.rowcount
                return rows, count
        except psycopg.Error as error:
            raise database_fault(error, mutation and context.submitted) from None
        finally:
            if connection is not None:
                await connection.close()

    def _sql(self, statement, parameters, context, token, mutation, fetch):
        import mssql_python

        connection = None
        try:
            endpoint = urlsplit(self.config.endpoint)
            configuration = (f"Server=tcp:{endpoint.hostname},{endpoint.port or 1433};Database={self.config.target.coordinates['database']};"
                             "Encrypt=yes;TrustServerCertificate=no;ConnectRetryCount=0")
            provider = SimpleNamespace(get_token=lambda *args: token)
            timeout = max(1, math.ceil(context.deadline - time.monotonic()))
            connection = mssql_python.connect(configuration, token_provider=provider, timeout=timeout, autocommit=False)
            connection.timeout = timeout
            cursor = connection.cursor()
            try:
                context.submitted = True
                cursor.execute(statement, parameters)
                if mutation:
                    while cursor.description is None and cursor.nextset():
                        pass
                    count = cursor.fetchone()[0] if cursor.description else cursor.rowcount
                    rows = []
                    connection.commit()
                else:
                    names = [column[0] for column in cursor.description]
                    if len(set(names)) != len(names):
                        raise OperationFault("failed", "duplicate_result_columns")
                    rows = [dict(zip(names, row)) for row in cursor.fetchmany(context.limits.max_items + 1)] if fetch else []
                    count = cursor.rowcount
                    connection.rollback()
                return rows, count
            finally:
                cursor.close()
        except mssql_python.Error as error:
            raise database_fault(error, mutation and context.submitted) from None
        finally:
            if connection is not None:
                connection.close()

    async def read_record(self, key, context):
        where, parameters = self.predicate(key)
        statement = f"SELECT * FROM {self.table} WHERE {where}"
        statement = statement + " LIMIT 2" if self.service == "postgresql" else statement.replace("SELECT *", "SELECT TOP (2) *", 1)
        rows, count = await self._run(statement, parameters, context, fetch=True, readonly=True)
        if not rows:
            raise OperationFault("not_found", "record_not_found")
        if len(rows) != 1 or any(rows[0].get(name) != value for name, value in key.parts.items()):
            raise OperationFault("unknown", "nonunique_or_mismatched_key")
        return ContentValue(rows[0], kind="row"), None

    async def write_record(self, operation, key, record, version, request, context):
        where, key_values = self.predicate(key)
        values = {**plain(record.content.data), **plain(key.parts)} if record else {}
        changes = [name for name in values if name not in self.key_fields]
        insert = (f"INSERT INTO {self.table} ({', '.join(self.identifier(name) for name in values)}) "
                  f"VALUES ({', '.join(self.marker for name in values)})")
        assignments = ", ".join(f"{self.identifier(name)} = {self.marker}" for name in changes)
        if operation == "create":
            statement, parameters = insert, tuple(values.values())
        elif operation == "delete":
            statement, parameters = f"DELETE FROM {self.table} WHERE {where}", key_values
        elif operation == "update":
            statement, parameters = f"UPDATE {self.table} SET {assignments} WHERE {where}", tuple(values[name] for name in changes) + key_values
        elif self.service == "postgresql":
            conflict = ", ".join(self.identifier(name) for name in self.key_fields)
            update = ", ".join(f"{self.identifier(name)} = EXCLUDED.{self.identifier(name)}" for name in changes)
            statement = insert + f" ON CONFLICT ({conflict}) " + (f"DO UPDATE SET {update}" if changes else "DO NOTHING")
            parameters = tuple(values.values())
        else:
            locked = self.table + " WITH (UPDLOCK, HOLDLOCK)"
            if changes:
                statement = (f"DECLARE @azdata_count int; UPDATE {locked} SET {assignments} WHERE {where}; "
                    f"SET @azdata_count = @@ROWCOUNT; IF @azdata_count = 0 BEGIN {insert}; SET @azdata_count = @@ROWCOUNT; END; "
                    "SELECT @azdata_count AS azdata_affected")
                parameters = tuple(values[name] for name in changes) + key_values + tuple(values.values())
            else:
                statement = (f"IF NOT EXISTS (SELECT 1 FROM {locked} WHERE {where}) BEGIN {insert}; END; SELECT 1 AS azdata_affected")
                parameters = key_values + tuple(values.values())
        if self.service == "sql" and operation != "upsert":
            statement += "; SELECT @@ROWCOUNT AS azdata_affected"
        rows, count = await self._run(statement, parameters, context, mutation=True)
        if count == 0 and operation in {"update", "delete"}:
            raise OperationFault("not_found", "record_not_found")
        if count not in (0, 1):
            raise OperationFault("unknown", "unexpected_affected_rows")
        return None

    async def execute(self, operation, request, context, evidence, cursor):
        if operation == "query":
            statement, parameters = self._query(request, context.limits.max_items + 1)
            rows, count = await self._run(statement, parameters, context, fetch=True, readonly=True)
            items = tuple(ItemResult(index, None, "success", ContentValue(row, kind="row")) for index, row in enumerate(rows[:context.limits.max_items]))
            return AdapterResult(items, truncated=len(rows) > context.limits.max_items)
        if operation == "schema":
            statement = (f"SELECT column_name, data_type, is_nullable FROM information_schema.columns "
                         f"WHERE table_schema = {self.marker} AND table_name = {self.marker} ORDER BY ordinal_position")
            rows, count = await self._run(statement, (self.config.target.coordinates["schema"], self.config.target.coordinates["table"]), context, fetch=True, readonly=True)
            if not rows:
                raise OperationFault("not_found", "schema_not_found")
            if len(rows) > context.limits.max_items:
                raise OperationFault("failed", "schema_item_limit")
            report = VerificationResult(evidence, "schema", "satisfied", 1) if evidence == "schema" else VerificationResult()
            return AdapterResult((ItemResult(0, None, "success", ContentValue({"columns": rows}, kind="row"), verification=report),))
        return await super().execute(operation, request, context, evidence, cursor)


class SQLAdapter(RelationalAdapter):
    service = "sql"
    scope = "https://database.windows.net/.default"
    schemes = ("mssql",)
    dialect = "tsql"
    parser_dialect = "tsql"


class PostgreSQLAdapter(RelationalAdapter):
    service = "postgresql"
    scope = "https://ossrdbms-aad.database.windows.net/.default"
    schemes = ("postgresql",)
    dialect = "postgresql"
    parser_dialect = "postgres"