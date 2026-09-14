"""Query guardrails — read-only enforcement and result-set bounding.

WHY THIS EXISTS
---------------
These connectors exist to let generated queries reach real data. Two things
go wrong immediately.

**Writes.** A query language that can read can usually also delete. RBAC
should be the real boundary — grant a reader role and nothing else — but
RBAC is provisioned somewhere else by someone else, and a text-level guard
costs nothing and fails closed at the point of use. Defence in depth, not
a substitute.

**Unbounded reads.** ``g.V()`` on a populated graph returns everything.
Downstream that is an out-of-memory error, a context-window overflow, or a
bill. Injecting a limit when the query has none is the difference between
a bad answer and an incident.

Neither check parses the language. They are regex guards with known false
negatives (see below and GOTCHAS.md G10). They are a floor, not a sandbox.

KNOWN LIMITS, STATED PLAINLY
----------------------------
* String literals are stripped before keyword matching for the languages
  where that caused false positives, not for the others.
* Comment syntax is not stripped, so a write keyword can be hidden.
* An unrecognised language passes through unchanged.

If the query source is untrusted, use a read-only identity. This module
does not make a hostile query safe.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import re

_CYPHER_WRITE_RE = re.compile(
    r"\b(CREATE|DELETE|SET|MERGE|REMOVE|DETACH|DROP|CALL)\b", re.IGNORECASE
)
_GQL_WRITE_RE = re.compile(
    r"\b(CREATE|DELETE|SET|MERGE|INSERT|REMOVE|DETACH)\b", re.IGNORECASE
)
_SQL_WRITE_RE = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE)\b", re.IGNORECASE
)
# Gremlin mutation steps. ``property`` is included because it is the write
# form; a read uses ``values`` or ``valueMap``.
_GREMLIN_WRITE_RE = re.compile(
    r"\.(addV|addE|drop|property|addVertex|addEdge)\s*\(", re.IGNORECASE
)

_LIMIT_RE = re.compile(r"\bLIMIT\b", re.IGNORECASE)
_KQL_TAKE_RE = re.compile(r"\|\s*(take|limit|top)\s+\d+", re.IGNORECASE)
_GREMLIN_LIMIT_RE = re.compile(r"\.(limit|range|sample)\s*\(", re.IGNORECASE)
_SQL_TOP_RE = re.compile(r"\bTOP\s+\d+", re.IGNORECASE)
_SQL_OFFSET_LIMIT_RE = re.compile(r"\bOFFSET\s+\d+\s+LIMIT\s+\d+", re.IGNORECASE)
_STRING_LITERAL_RE = re.compile(r"'[^']*'|\"[^\"]*\"")

# Aggregations already return one row; appending a limit to ``.count()`` is
# harmless but noisy, and on some steps changes the shape.
_GREMLIN_AGGREGATES = (".count()", ".sum()", ".mean()", ".max()", ".min()")

# Read-only Kusto control commands worth allowing: schema discovery is how a
# generated query learns what to ask for. Everything starting with '.' that
# is not on this list is refused.
_KQL_READONLY_COMMANDS = (".show tables", ".show database", ".show table")

DEFAULT_MAX_ROWS = {
    "cypher": 500,
    "gql": 50,
    "kql": 50,
    "gremlin": 500,
    "sql": 500,
}

# Length caps bound what an unbounded generator can submit. KQL is generous
# because machine-generated scoring queries legitimately run to tens of
# thousands of characters; the read-only check is the real guard.
DEFAULT_MAX_QUERY_LENGTH = {
    "cypher": 2000,
    "gql": 5000,
    "kql": 100000,
    "gremlin": 5000,
    "sql": 5000,
}

LANGUAGES = tuple(DEFAULT_MAX_ROWS)


def validate_read_only(query: str, language: str) -> str | None:
    """Return an explanation when ``query`` may write, else None.

    The return type is deliberately not an exception: connectors turn the
    message into an error envelope for the caller, and a violation is an
    expected outcome rather than an exceptional one.
    """
    max_len = DEFAULT_MAX_QUERY_LENGTH.get(language, 5000)
    if len(query) > max_len:
        return f"Query too long ({len(query)} chars). Maximum: {max_len}."

    if language == "cypher":
        stripped = _STRING_LITERAL_RE.sub("", query)
        match = _CYPHER_WRITE_RE.search(stripped)
        if match:
            return (
                f"Write operations not allowed. Found: '{match.group()}'. "
                "Use read-only queries."
            )

    elif language == "gql":
        stripped = _STRING_LITERAL_RE.sub("", query)
        if _GQL_WRITE_RE.search(stripped):
            return (
                "Write operations (CREATE, DELETE, SET, MERGE, INSERT) "
                "are not permitted."
            )

    elif language == "kql":
        # Split on ';' first: a single statement check would miss
        # "T | take 1; .drop table T".
        for statement in query.split(";"):
            stmt = statement.strip()
            if stmt.startswith("."):
                low = stmt.lower()
                if not any(low.startswith(cmd) for cmd in _KQL_READONLY_COMMANDS):
                    return (
                        "Management commands (.drop, .create, .alter, .set, "
                        ".delete) are not permitted. Use data queries only."
                    )

    elif language == "gremlin":
        match = _GREMLIN_WRITE_RE.search(query)
        if match:
            return (
                f"Write operations not allowed. Found: '.{match.group(1)}()'. "
                "Use read-only traversals."
            )

    elif language == "sql":
        match = _SQL_WRITE_RE.search(query)
        if match:
            return (
                f"Write operations not allowed. Found: '{match.group()}'. "
                "Use SELECT queries only."
            )

    return None


def ensure_limit(query: str, language: str, max_rows: int | None = None) -> str:
    """Append a row cap when the query has none. Idempotent.

    An unrecognised language returns the query unchanged rather than
    guessing at syntax and producing something that will not parse.
    """
    if max_rows is None:
        max_rows = DEFAULT_MAX_ROWS.get(language, 500)

    cleaned = query.rstrip().rstrip(";")

    if language in ("cypher", "gql"):
        if _LIMIT_RE.search(query):
            return query
        return f"{cleaned} LIMIT {max_rows}"

    if language == "kql":
        if _KQL_TAKE_RE.search(query):
            return query
        return f"{cleaned} | take {max_rows}"

    if language == "gremlin":
        if any(agg in query for agg in _GREMLIN_AGGREGATES):
            return query
        if _GREMLIN_LIMIT_RE.search(query):
            return query
        return f"{cleaned}.limit({max_rows})"

    if language == "sql":
        if _SQL_TOP_RE.search(query) or _SQL_OFFSET_LIMIT_RE.search(query):
            return query
        return re.sub(r"(?i)^(SELECT)\s+", rf"\1 TOP {max_rows} ", cleaned, count=1)

    return query


def read_only_validator(language: str):
    """Return a one-argument validator bound to ``language``.

    Connectors accept ``Callable[[str], str | None]``; this adapts the
    two-argument function to that seam.
    """

    def _validate(query: str) -> str | None:
        return validate_read_only(query, language)

    return _validate


def limit_injector(language: str, max_rows: int | None = None):
    """Return a one-argument limit injector bound to ``language``."""

    def _transform(query: str) -> str:
        return ensure_limit(query, language, max_rows)

    return _transform


__all__ = [
    "DEFAULT_MAX_QUERY_LENGTH",
    "DEFAULT_MAX_ROWS",
    "LANGUAGES",
    "ensure_limit",
    "limit_injector",
    "read_only_validator",
    "validate_read_only",
]
