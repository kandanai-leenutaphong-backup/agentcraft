"""T-SQL read guard — a parse, an allowlist, and a refusal that names the cause.

WHY THIS IS NOT A REGEX
-----------------------
:mod:`azdata.core.guardrails` guards five languages with regular expressions and
says so: it is a floor, not a sandbox, and it has known false negatives. That
floor is acceptable for a dialect whose values are bound and whose surface is
small. It is **not** acceptable for T-SQL, where the ways to write past a
keyword scan are a documented genre: ``SELECT * INTO``, a batch separated by a
semicolon, a CTE that ends in ``DELETE``, ``OPENROWSET`` reaching a second
server, ``EXEC`` around a string the scanner never sees.

So this module parses. ``sqlglot`` builds the tree, and the decision is made on
node types and function names rather than on the characters that produced them.
A statement that does not parse is refused; there is no fallback that lets
unparseable text through.

FAIL CLOSED, AND SAY WHICH RULE CLOSED
---------------------------------------
Seven rules, each of which is sufficient on its own to refuse:

1. one statement, and it is a ``SELECT``. Not a union, not a batch, not a
   procedure call. ``sqlglot.parse`` returning two roots is a batch.
2. no ``INTO``. ``SELECT * INTO t2 FROM t1`` is a table creation wearing a
   select's clothes, and every keyword scanner in the world passes it.
3. no comment marker and no semicolon **in the text**, before the parse. A
   parser discards comments, so a comment is invisible in the tree; refusing it
   in the text is the only place it can be seen.
4. no unknown function. ``sqlglot`` gives every function it recognises its own
   node type, so anything left as :class:`sqlglot.exp.Anonymous` is a name this
   library has never heard of — which is exactly ``OPENROWSET``, ``OPENQUERY``,
   ``OPENDATASOURCE`` and ``xp_cmdshell``. Refusing the whole class is stronger
   than a denylist that has to be kept current.
5. at most two name parts per table. ``server.database.schema.table`` is a
   linked-server or cross-database read, and both leave the bound database.
6. an explicit row cap. An unbounded ``SELECT`` is refused rather than rewritten:
   ``SELECT DISTINCT`` puts ``TOP`` in a different position and a textual
   rewrite would produce something that does not parse.
7. no ``%``. The driver's parameter binding runs the statement through Python's
   ``%`` formatting to rename placeholders, so a stray percent sign is a
   ``ValueError`` at call time rather than a query.

WHAT THIS IS NOT
----------------
It is not the security boundary. The permissions of the database principal are,
and that principal holds ``SELECT`` on one table. This guard is what stops a
mistake before it costs a round trip, and what makes the refusal legible.

DEPENDENCIES
------------
``sqlglot``, loaded on first call through :mod:`azdata.core.optional`.
"""

from __future__ import annotations

import re

from azdata.core.optional import load

#: The dialect name ``sqlglot`` is asked for. Named once so a caller reading a
#: refusal and a caller reading the parse see the same word.
TSQL_DIALECT = "tsql"

#: The row cap applied when a caller states none. Deliberately the same order
#: as :data:`azdata.core.guardrails.DEFAULT_MAX_ROWS` for ``sql``.
DEFAULT_TSQL_MAX_ROWS = 500

#: Longest statement accepted. A tool template is bounded well below this; the
#: cap exists so a hostile caller cannot make the parser the expensive part.
MAX_TSQL_CHARS = 5_000

#: Text that must not appear before the parse, and why. A parser throws comments
#: away, so this is the only place they are visible.
_FORBIDDEN_TEXT: tuple[tuple[str, str], ...] = (
    ("--", "a line comment"),
    ("/*", "a block comment"),
    ("*/", "a block comment"),
    (";", "a statement separator"),
    ("%", "a character the driver's parameter binding reserves"),
)

#: pytds writes its named parameters as ``%(name)s``. Rewritten to T-SQL's own
#: ``@name`` before the parse so the guard sees the shape the server will,
#: rather than refusing the placeholder it generated itself.
_PYFORMAT = re.compile(r"%\(([A-Za-z_][A-Za-z0-9_]*)\)s")

#: Identifier shape for a schema or table name that may be interpolated into a
#: statement's structure. Not a value: a value is bound, never interpolated.
SQL_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


class TsqlRefused(ValueError):
    """The statement is not a bounded read. Message names the rule that closed."""


def quote_identifier(name: str) -> str:
    """One validated identifier, bracket-quoted, or a refusal.

    Bracket quoting alone is not safety — ``]`` ends the bracket — so the name
    is checked against :data:`SQL_IDENTIFIER` first and the quoting is what
    keeps a legal-but-reserved word working.
    """
    text = str(name or "")
    if not SQL_IDENTIFIER.fullmatch(text):
        raise TsqlRefused(
            f"'{text[:60]}' is not a SQL identifier: a letter or underscore, "
            "then letters, digits and underscores, up to 128 characters"
        )
    return f"[{text}]"


def normalize_placeholders(statement: str) -> str:
    """``%(name)s`` -> ``@name``, so a bound statement can be parsed."""
    return _PYFORMAT.sub(r"@\1", statement or "")


def validate_tsql_read_only(
    statement: str,
    *,
    max_rows: int | None = None,
    table: tuple[str, str] | None = None,
) -> str | None:
    """``None`` when the statement is a bounded read, else why it is not.

    A string return rather than a raise, matching
    :func:`azdata.core.guardrails.validate_read_only`: a refusal is an expected
    outcome that callers turn into an error envelope, not an exceptional one.

    ``max_rows`` bounds the declared ``TOP``; ``table`` — ``(schema, table)`` —
    additionally pins every table in the statement to the bound one, which is
    what stops a tool reading a table its connector never named.
    """
    text = str(statement or "")
    if not text.strip():
        return "the statement is empty"
    if len(text) > MAX_TSQL_CHARS:
        return f"the statement is {len(text)} characters; the maximum is {MAX_TSQL_CHARS}"

    normalized = normalize_placeholders(text)
    for token, what in _FORBIDDEN_TEXT:
        if token in normalized:
            return (
                f"the statement carries {token!r}, {what}. A bounded read is one "
                "SELECT with no comments and no second statement"
            )

    sqlglot = load("sqlglot", dist="sqlglot>=25")
    exp = load("sqlglot.expressions", dist="sqlglot>=25")
    try:
        parsed = sqlglot.parse(normalized, dialect=TSQL_DIALECT)
    except Exception as failure:  # noqa: BLE001 - any parse failure is a refusal
        return f"the statement is not valid T-SQL ({type(failure).__name__})"

    statements = [item for item in parsed if item is not None]
    if len(statements) != 1:
        return (
            f"the text holds {len(statements)} statements; a bounded read is "
            "exactly one SELECT"
        )
    root = statements[0]
    if not isinstance(root, exp.Select):
        return (
            f"the statement is a {type(root).__name__.upper()}, not a SELECT. "
            "This connector reads and cannot be asked to do anything else"
        )

    if root.args.get("into") is not None or list(root.find_all(exp.Into)):
        return (
            "SELECT ... INTO creates a table. It is a write with a SELECT in "
            "front of it, and it is refused"
        )

    unknown = sorted({str(node.name) for node in root.find_all(exp.Anonymous) if node.name})
    if unknown:
        return (
            f"'{unknown[0][:60]}' is not a function this guard recognises. "
            "Unknown functions are refused, because that is the class "
            "OPENROWSET, OPENQUERY and the extended procedures live in"
        )

    wanted = (
        (str(table[0]).lower(), str(table[1]).lower()) if table is not None else None
    )
    for node in root.find_all(exp.Table):
        parts = [part.name for part in node.parts]
        if len(parts) > 2:
            return (
                f"'{'.'.join(parts)[:80]}' names {len(parts)} parts. Two is the "
                "most a bounded read may use: three or four reaches another "
                "database or another server"
            )
        if wanted is None:
            continue
        schema = parts[0].lower() if len(parts) == 2 else ""
        name = parts[-1].lower()
        if (schema, name) != wanted:
            # Named back as the binding spells it, not as it was folded for
            # comparison: a refusal a reader has to re-capitalise is a refusal
            # they have to think about.
            return (
                f"'{'.'.join(parts)[:80]}' is not the table this connector is "
                f"bound to ({table[0]}.{table[1]}). The binding is authority"
            )

    limit = root.args.get("limit")
    declared = _limit_value(limit)
    if declared is None:
        return (
            "the statement declares no row cap. Write 'SELECT TOP (n) ...': an "
            "unbounded read is refused rather than rewritten, because TOP sits "
            "in a different place after DISTINCT"
        )
    ceiling = DEFAULT_TSQL_MAX_ROWS if max_rows is None else int(max_rows)
    if declared > ceiling:
        return f"the statement asks for TOP ({declared}); the maximum is {ceiling}"
    return None


def _limit_value(limit: object) -> int | None:
    if limit is None:
        return None
    expression = getattr(limit, "expression", None)
    raw = getattr(expression, "name", None)
    try:
        return int(str(raw))
    except (TypeError, ValueError):
        return None


def guard_tsql(
    statement: str,
    *,
    max_rows: int | None = None,
    table: tuple[str, str] | None = None,
) -> str:
    """The statement, or :class:`TsqlRefused` naming the rule that closed."""
    violation = validate_tsql_read_only(statement, max_rows=max_rows, table=table)
    if violation:
        raise TsqlRefused(violation)
    return statement


__all__ = [
    "DEFAULT_TSQL_MAX_ROWS",
    "MAX_TSQL_CHARS",
    "SQL_IDENTIFIER",
    "TSQL_DIALECT",
    "TsqlRefused",
    "guard_tsql",
    "normalize_placeholders",
    "quote_identifier",
    "validate_tsql_read_only",
]
