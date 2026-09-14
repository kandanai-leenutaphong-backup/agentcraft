"""Azure SQL Database read connector — TDS, an Entra token, and nothing else.

WHY A PURE-PYTHON DRIVER
------------------------
The deployed consumer of this connector is a Foundry hosted agent built with
``dependency_resolution: remote_build``, which installs from PyPI and has no
package manager, no ``apt``, and no ODBC driver manager. ``pyodbc`` needs
``msodbcsql18`` installed from a Microsoft apt repository, so it cannot travel.
``python-tds`` speaks TDS itself, in Python, and installs from PyPI alone —
which is the whole reason it is the driver here rather than the more familiar
one.

TLS IS NOT OPTIONAL AND IS NOT DEFAULT
----------------------------------------
``python-tds`` encrypts only when it is given a CA bundle: ``connect(cafile=...)``
is what turns TLS on, and without it the login is refused by Azure SQL anyway,
which is the good failure. The bundle is ``certifi``'s, host name validation is
left on, and ``enc_login_only`` is left off so the whole session is encrypted
rather than the handshake alone. All three are stated at the call site because
each one of them silently downgrades the connection if it is left out.

THE TOKEN IS A CALLABLE AND STAYS IN MEMORY
---------------------------------------------
``access_token_callable`` is invoked by the driver at login. The token is never
placed in a connection string, never written to a field of any object this
module returns, and never logged: what a caller can see is a status, a column
list and rows.

WHY EVERY QUERY OPENS ITS OWN CONNECTION
------------------------------------------
A cached connection outlives its token, and the failure mode of a pooled
connection whose login has expired is an error at an unrelated call site. One
login per query costs a TLS handshake and is honest. If that becomes the
bottleneck, the fix is a pool that re-authenticates, not a cache that hopes.

READ-ONLY IS FOUR THINGS, NOT ONE
-----------------------------------
1. the statement is parsed and refused unless it is a bounded ``SELECT``
   (:mod:`azdata.sqldb.guard`);
2. the tables it names are pinned to the binding's own schema and table;
3. the connection is opened with ``autocommit=True`` and the session is set
   read-only at login, so an implicit transaction cannot be left open;
4. the database principal holds ``SELECT`` on one table and nothing else, which
   is the only one of the four that is a security boundary.

DEPENDENCIES
------------
``python-tds``, ``pyOpenSSL`` and ``certifi``, all loaded on first connect.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as _datetime
import decimal
import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Mapping, Sequence

from azdata.core.breaker import ThrottleGate
from azdata.core.envelope import error_envelope
from azdata.core.optional import load
from azdata.sqldb.guard import (
    DEFAULT_TSQL_MAX_ROWS,
    normalize_placeholders,
    validate_tsql_read_only,
)

logger = logging.getLogger(__name__)

#: The Entra scope an Azure SQL token is issued for. Not the ARM scope: a
#: management token is refused at login with a message that does not say so.
SQL_SCOPE = "https://database.windows.net/.default"

#: The public suffix every Azure SQL logical server answers on, and the port
#: TDS uses. Composed rather than discovered, so a binding needs no round trip.
SQL_SUFFIX = "database.windows.net"
SQL_PORT = 1433

#: Login is a TLS handshake plus a TDS login exchange, and Azure SQL serverless
#: may be resuming from paused. Separate from the query timeout because the two
#: fail for unrelated reasons.
DEFAULT_LOGIN_TIMEOUT_SECS = 30.0
DEFAULT_QUERY_TIMEOUT_SECS = 30.0


class SqlUnavailable(RuntimeError):
    """The driver or its TLS dependency is absent, or the login was refused."""


@dataclass(frozen=True, slots=True)
class SqlTarget:
    """One database, and the one table inside it a connector addresses.

    ``server`` is a host name, not a URL: Azure SQL's data plane is TDS on
    1433 and calling it an endpoint with a scheme would invite a caller to
    build an HTTP request out of it.
    """

    server: str
    database: str
    schema: str = "dbo"
    table: str = ""

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.table}" if self.table else self.schema

    @property
    def pinned(self) -> tuple[str, str] | None:
        """The ``(schema, table)`` every statement is held to, when bound."""
        return (self.schema, self.table) if self.schema and self.table else None


def sql_server_host(name: str) -> str:
    """The host name of one logical server, from its resource name."""
    cleaned = str(name or "").strip().lower()
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith(SQL_SUFFIX) else f"{cleaned}.{SQL_SUFFIX}"


def sql_target_from_resource_id(
    resource_id: str, *, schema: str = "", table: str = ""
) -> SqlTarget:
    """Server and database from a ``Microsoft.Sql/servers/databases`` id.

    The id is authority. A connection is never composed from a caller-supplied
    host name or connection string, because a host name is where a read goes
    and a resource id is what an operator granted.
    """
    parts = [part for part in str(resource_id or "").split("/") if part]
    lowered = [part.lower() for part in parts]
    server = database = ""
    for index, part in enumerate(lowered):
        if part == "servers" and index + 1 < len(parts):
            server = parts[index + 1]
        if part == "databases" and index + 1 < len(parts):
            database = parts[index + 1]
    if not (server and database):
        raise SqlUnavailable(
            f"'{str(resource_id)[:120]}' does not name a SQL server and database; "
            "expected .../providers/Microsoft.Sql/servers/<server>/databases/<db>"
        )
    return SqlTarget(
        server=sql_server_host(server), database=database, schema=schema, table=table
    )


def json_safe(value: Any) -> Any:
    """One column value as something ``json.dumps`` accepts, losing nothing silently.

    ``Decimal`` becomes ``float`` rather than a string on purpose: a numeric
    column exists to be summed, and a caller handed ``"120.00"`` has to guess
    that it may be added. Dates become ISO 8601, bytes become base64, and a
    type this function has never seen becomes its ``str`` rather than raising
    inside a serialiser three frames away.
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (_datetime.datetime, _datetime.date, _datetime.time)):
        return value.isoformat()
    if isinstance(value, _datetime.timedelta):
        return value.total_seconds()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode("ascii")
    return str(value)


def open_connection(
    target: SqlTarget,
    *,
    token: Callable[[], str],
    login_timeout_secs: float = DEFAULT_LOGIN_TIMEOUT_SECS,
    query_timeout_secs: float = DEFAULT_QUERY_TIMEOUT_SECS,
    readonly: bool = True,
) -> Any:
    """One authenticated, encrypted TDS connection. Blocking; call off the loop.

    Every TLS argument is passed explicitly. ``cafile`` is what enables
    encryption at all in this driver, ``validate_host`` is what makes the
    certificate mean something, and ``enc_login_only=False`` is what keeps the
    rest of the session encrypted after the login packet.
    """
    pytds = load("pytds", dist="python-tds>=1.16")
    certifi = load("certifi", dist="certifi>=2024.2.2")
    tls = load("pytds.tls", dist="pyOpenSSL>=24")
    if not getattr(tls, "OPENSSL_AVAILABLE", False):
        raise SqlUnavailable(
            "python-tds cannot negotiate TLS without pyOpenSSL, and an "
            "unencrypted login to Azure SQL is refused by the service: "
            "pip install pyOpenSSL"
        )
    if not target.server or not target.database:
        raise SqlUnavailable("no SQL server and database are configured")
    return pytds.connect(
        server=target.server,
        port=SQL_PORT,
        database=target.database,
        access_token_callable=token,
        cafile=certifi.where(),
        validate_host=True,
        enc_login_only=False,
        autocommit=True,
        readonly=readonly,
        login_timeout=login_timeout_secs,
        timeout=query_timeout_secs,
        disable_connect_retry=False,
        appname="azdata-connectors",
    )


class SqlConnector:
    """Bounded, read-only T-SQL against one Azure SQL database.

    Args:
        resolve_target: Called per query, so a per-request binding works
            without rebuilding the connector.
        credential_provider: Returns a ``TokenCredential``.
        gate_provider: Async callable returning the :class:`ThrottleGate` that
            bounds concurrency against this server. Optional: a single-operator
            surface has no capacity to share.
        max_rows: The default ceiling a statement's ``TOP`` is checked against.

    There is no ``write``, no ``execute_non_query`` and no parameter by which a
    caller could ask for one. A read that could become a write by passing an
    argument is not a read-only connector.
    """

    def __init__(
        self,
        *,
        resolve_target: Callable[[], SqlTarget],
        credential_provider: Callable[[], Any],
        gate_provider: Callable[[], Awaitable[ThrottleGate]] | None = None,
        max_rows: int = DEFAULT_TSQL_MAX_ROWS,
        login_timeout_secs: float = DEFAULT_LOGIN_TIMEOUT_SECS,
        connect: Callable[..., Any] | None = None,
    ) -> None:
        self._resolve_target = resolve_target
        self._credential_provider = credential_provider
        self._gate_provider = gate_provider
        self._max_rows = int(max_rows)
        self._login_timeout = float(login_timeout_secs)
        # Injected so the whole read path is exercised with no driver, no
        # network and no credential. Production leaves it None.
        self._connect = connect or open_connection
        self._last_gate: ThrottleGate | None = None

    @property
    def circuit_state(self) -> Any:
        return self._last_gate.state if self._last_gate is not None else None

    def _token(self) -> Callable[[], str]:
        """A callable the driver invokes at login. Never returns to a caller."""

        def issue() -> str:
            credential = self._credential_provider()
            return str(credential.get_token(SQL_SCOPE).token)

        return issue

    async def query(
        self,
        statement: str,
        /,
        *,
        parameters: Mapping[str, Any] | None = None,
        max_rows: int | None = None,
        timeout_secs: float = DEFAULT_QUERY_TIMEOUT_SECS,
    ) -> str:
        """Run one bounded read and return a JSON string.

        ``{"columns": [...], "rows": [...], "truncated": bool}`` on success, an
        error envelope otherwise. Values in ``parameters`` are bound by the
        driver as typed TDS parameters and never enter the statement text.
        """
        target = self._resolve_target()
        if not target.server or not target.database:
            return error_envelope("no SQL database is configured for this connector")

        ceiling = int(max_rows or self._max_rows)
        violation = validate_tsql_read_only(
            statement, max_rows=ceiling, table=target.pinned
        )
        if violation:
            return error_envelope(violation)

        gate = await self._gate_provider() if self._gate_provider else None
        self._last_gate = gate
        was_probe = False
        if gate is not None:
            try:
                was_probe = await gate.acquire()
            except Exception as exc:  # noqa: BLE001 - breaker open, message is safe
                return error_envelope(str(exc))
        try:
            shaped = await asyncio.wait_for(
                asyncio.to_thread(
                    self._run, target, statement, dict(parameters or {}), ceiling,
                    timeout_secs,
                ),
                timeout_secs + self._login_timeout,
            )
            if gate is not None:
                await gate.record_success()
            logger.info("sql.query complete: %d rows", len(shaped["rows"]))
            return json.dumps(shaped, default=str)
        except (asyncio.TimeoutError, TimeoutError):
            if gate is not None:
                await gate.record_server_error()
            return error_envelope(
                f"the query exceeded {timeout_secs}s against {target.database}"
            )
        except Exception as exc:  # noqa: BLE001 - boundary: failure is an envelope
            logger.warning("sql.query failed: %s", type(exc).__name__)
            if gate is not None:
                await self._record(gate, exc)
            return error_envelope(f"SQL query failed: {_safe_detail(exc)}")
        finally:
            if gate is not None:
                gate.release(was_probe=was_probe)

    async def _record(self, gate: ThrottleGate, exc: Exception) -> None:
        text = str(exc).lower()
        if "40501" in text or "throttl" in text or "too many" in text:
            await gate.record_429()
        else:
            await gate.record_server_error()

    def _run(
        self,
        target: SqlTarget,
        statement: str,
        parameters: dict[str, Any],
        max_rows: int,
        timeout_secs: float,
    ) -> dict[str, Any]:
        """The blocking half. Runs on a worker thread, holds no event loop."""
        connection = self._connect(
            target,
            token=self._token(),
            login_timeout_secs=self._login_timeout,
            query_timeout_secs=timeout_secs,
            readonly=True,
        )
        try:
            cursor = connection.cursor()
            try:
                if parameters:
                    cursor.execute(statement, parameters)
                else:
                    cursor.execute(statement)
                columns = [str(column[0]) for column in (cursor.description or ())]
                rows: list[dict[str, Any]] = []
                truncated = False
                for record in cursor:
                    if len(rows) >= max_rows:
                        truncated = True
                        break
                    rows.append(
                        {name: json_safe(value) for name, value in zip(columns, record)}
                    )
            finally:
                close = getattr(cursor, "close", None)
                if close is not None:
                    close()
        finally:
            close = getattr(connection, "close", None)
            if close is not None:
                close()
        return {"columns": columns, "rows": rows, "truncated": truncated}

    async def is_healthy(self) -> bool:
        """True when a trivial bounded read returns without an error envelope."""
        from azdata.core.envelope import is_error

        target = self._resolve_target()
        if not target.server or not target.database:
            return False
        probe = "SELECT TOP (1) 1 AS ready"
        # The health probe names no table, so the binding's table pin would
        # refuse it. It is checked by the guard's other six rules instead.
        payload = await self.query(probe, max_rows=1)
        return not is_error(payload)


def bind_names(names: Sequence[str]) -> dict[str, str]:
    """``{"region": "%(region)s"}`` — the placeholder each bound name renders to.

    ``pytds`` uses DB-API ``pyformat``: the driver rewrites these to ``@P1``,
    ``@P2`` and sends the values as typed TDS parameters, so no value is ever
    part of the statement text. One place writes the syntax so a caller does
    not have to know it.
    """
    return {str(name): f"%({name})s" for name in names}


#: The tables a principal can see, from the database's own catalogue.
#:
#: It passes the read guard on its own terms rather than by exemption: one
#: SELECT, an explicit ``TOP``, a two-part name, no unknown function. Views and
#: system tables are excluded because a connector binds a table, and a bound
#: view would fail the grant rather than the query.
TABLE_LISTING = (
    "SELECT TOP ({max_rows}) TABLE_SCHEMA, TABLE_NAME "
    "FROM INFORMATION_SCHEMA.TABLES "
    "WHERE TABLE_TYPE = 'BASE TABLE' "
    "ORDER BY TABLE_SCHEMA, TABLE_NAME"
)


async def list_tables(
    connector: SqlConnector, *, max_rows: int = 200, timeout_secs: float = 30.0
) -> str:
    """Every base table in the bound database, as a JSON envelope.

    The connector must be built with **no** table in its target: a bound
    connector pins every statement to that one table, which is the correct
    behaviour for a tool and the wrong one for a picker.
    """
    return await connector.query(
        TABLE_LISTING.format(max_rows=int(max_rows)),
        max_rows=max_rows,
        timeout_secs=timeout_secs,
    )


def _safe_detail(exc: Exception) -> str:
    """An SDK failure, without whatever the driver put in the message.

    A TDS login error can echo the server and the database. Neither is secret,
    but a token never appears in one and this makes sure of it by returning the
    exception's class and a truncated message with any bearer-looking run of
    characters removed.
    """
    from azdata.core.envelope import sanitize_detail

    return sanitize_detail(f"{type(exc).__name__}: {str(exc)[:300]}")


__all__ = [
    "DEFAULT_LOGIN_TIMEOUT_SECS",
    "DEFAULT_QUERY_TIMEOUT_SECS",
    "SQL_PORT",
    "SQL_SCOPE",
    "SQL_SUFFIX",
    "TABLE_LISTING",
    "SqlConnector",
    "SqlTarget",
    "SqlUnavailable",
    "bind_names",
    "json_safe",
    "list_tables",
    "open_connection",
    "sql_server_host",
    "sql_target_from_resource_id",
]
