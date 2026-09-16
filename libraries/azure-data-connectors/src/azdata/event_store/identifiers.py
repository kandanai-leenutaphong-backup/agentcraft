"""Identifier validation and KQL literal rendering.

KQL parameterises *values* but not *identifiers*. Table and column names must
therefore be validated against a strict allowlist before they are interpolated
into a command, and that validation is the connector's injection boundary.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .errors import AdxIdentifierError

# Kusto entity names: letter or underscore, then letters, digits, underscores.
# Deliberately narrower than what the engine tolerates. Anything requiring
# bracket quoting is rejected rather than escaped, because escaping is where
# injection bugs live.
_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")

# Reserved words that would change the meaning of a command if accepted as a name.
_RESERVED = frozenset(
    {
        "and",
        "by",
        "database",
        "datatable",
        "false",
        "in",
        "let",
        "not",
        "null",
        "or",
        "print",
        "project",
        "table",
        "true",
        "where",
    }
)

_SCALAR_TYPES = frozenset(
    {"bool", "datetime", "decimal", "dynamic", "guid", "int", "long", "real", "string", "timespan"}
)


def validate_identifier(name: str, *, kind: str = "identifier") -> str:
    """Return ``name`` if it is a safe bare Kusto identifier, else raise."""
    if not isinstance(name, str) or not _IDENTIFIER.fullmatch(name):
        raise AdxIdentifierError(
            f"unsafe {kind} {name!r}: must match [A-Za-z_][A-Za-z0-9_]{{0,127}}"
        )
    if name.lower() in _RESERVED:
        raise AdxIdentifierError(f"unsafe {kind} {name!r}: reserved KQL word")
    return name


def validate_type(kusto_type: str) -> str:
    """Return ``kusto_type`` if it names a Kusto scalar type, else raise."""
    if kusto_type not in _SCALAR_TYPES:
        raise AdxIdentifierError(f"unknown Kusto scalar type {kusto_type!r}")
    return kusto_type


def quote_string(value: str) -> str:
    """Render a Python string as a KQL string literal.

    Used only where parameters are genuinely unavailable, such as inside a
    ``datatable`` payload for inline ingestion. Prefer query parameters.
    """
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f'"{escaped}"'


def render_datetime(value: datetime) -> str:
    """Render a datetime as a KQL ``datetime()`` literal in UTC."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return f"datetime({value.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')}Z)"
