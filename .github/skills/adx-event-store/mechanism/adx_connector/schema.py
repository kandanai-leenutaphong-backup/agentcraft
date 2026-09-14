"""Schema inference and table DDL.

Infers a Kusto table schema from a CSV header plus a bounded sample of rows, so
a 181-column export becomes a typed table without hand-writing DDL.
"""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

from .identifiers import validate_identifier, validate_type
from .models import ColumnSpec, TableSchema

# Values that mean "absent" across the products in this corpus.
_NULLISH = frozenset({"", "-", "n/a", "null", "none", "unknown"})

_ISO_DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?Z?$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_INTEGER = re.compile(r"^[+-]?\d+$")
_DECIMAL = re.compile(r"^[+-]?(\d+\.\d*|\.\d+|\d+)([eE][+-]?\d+)?$")
_BOOLEAN = frozenset({"true", "false"})

# Kusto's 64-bit integer bounds; anything wider must be carried as a string.
_LONG_MIN, _LONG_MAX = -(2**63), 2**63 - 1


def _classify(value: str) -> str:
    """Narrowest Kusto type that can carry ``value``."""
    text = value.strip()
    if text.lower() in _NULLISH:
        return "null"
    if _ISO_DATETIME.match(text):
        return "datetime"
    if _GUID.match(text):
        return "guid"
    if text.lower() in _BOOLEAN:
        return "bool"
    if _INTEGER.match(text):
        return "long" if _LONG_MIN <= int(text) <= _LONG_MAX else "string"
    if _DECIMAL.match(text):
        return "real"
    if text[:1] in "{[":
        try:
            json.loads(text)
        except ValueError:
            return "string"
        return "dynamic"
    return "string"


# Promotion lattice: when a column shows two types, take their nearest common ancestor.
_PROMOTION: dict[frozenset[str], str] = {
    frozenset({"long", "real"}): "real",
    frozenset({"long", "bool"}): "long",
    frozenset({"long", "datetime"}): "string",
    frozenset({"real", "datetime"}): "string",
    frozenset({"guid", "string"}): "string",
    frozenset({"dynamic", "string"}): "string",
}


def _merge(left: str, right: str) -> str:
    if left == right:
        return left
    if left == "null":
        return right
    if right == "null":
        return left
    return _PROMOTION.get(frozenset({left, right}), "string")


def infer_schema(
    csv_path: Path,
    table_name: str,
    *,
    sample_rows: int = 5_000,
    force_types: dict[str, str] | None = None,
    folder: str = "",
    docstring: str = "",
) -> TableSchema:
    """Infer a :class:`TableSchema` from a CSV file.

    Args:
        sample_rows: Rows to inspect. ``0`` inspects every row, which is exact
            but reads the whole file.
        force_types: Column name to Kusto type, overriding inference. Use when a
            column's meaning is known better than its sample suggests.
    """
    validate_identifier(table_name, kind="table")
    forced = {name: validate_type(kusto_type) for name, kusto_type in (force_types or {}).items()}
    csv.field_size_limit(100_000_000)

    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"{csv_path} is empty") from exc
        for name in header:
            validate_identifier(name, kind="column")

        observed = ["null"] * len(header)
        for index, row in enumerate(reader):
            if sample_rows and index >= sample_rows:
                break
            for position, cell in enumerate(row[: len(header)]):
                observed[position] = _merge(observed[position], _classify(cell))

    columns = tuple(
        ColumnSpec(
            name=name,
            # A column that was null throughout the sample gets `string`: the
            # widest type, so a later non-null value cannot fail ingestion.
            kusto_type=forced.get(name, "string" if kind == "null" else kind),
        )
        for name, kind in zip(header, observed)
    )
    return TableSchema(name=table_name, columns=columns, folder=folder, docstring=docstring)


def create_table_command(schema: TableSchema, *, docstring: str = "") -> str:
    """``.create-merge table`` command for ``schema``.

    Merge rather than create so re-running is idempotent and additive: existing
    columns are left alone and new ones are appended.
    """
    validate_identifier(schema.name, kind="table")
    body = ", ".join(
        f"{validate_identifier(column.name, kind='column')}:{validate_type(column.kusto_type)}"
        for column in schema.columns
    )
    command = f".create-merge table {schema.name} ({body})"
    text = docstring or schema.docstring
    if text:
        command += f" with (docstring = {json.dumps(text)}"
        if schema.folder:
            command += f", folder = {json.dumps(schema.folder)}"
        command += ")"
    elif schema.folder:
        command += f" with (folder = {json.dumps(schema.folder)})"
    return command


def csv_mapping_command(schema: TableSchema, mapping_name: str) -> str:
    """``.create-or-alter ingestion csv mapping`` bound to column ordinals.

    Ordinal mapping rather than name mapping, so a header rename in the source
    file cannot silently shift values into the wrong column.
    """
    validate_identifier(schema.name, kind="table")
    validate_identifier(mapping_name, kind="mapping")
    mapping = [
        {"Column": column.name, "Properties": {"Ordinal": str(index)}}
        for index, column in enumerate(schema.columns)
    ]
    return (
        f".create-or-alter table {schema.name} ingestion csv mapping "
        f"{json.dumps(mapping_name)} {json.dumps(json.dumps(mapping))}"
    )
