"""Result and schema value objects.

Deliberately free of pandas so the connector has no dependency beyond the
official Azure SDKs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterator, Sequence


@dataclass(frozen=True, slots=True)
class ColumnSpec:
    """One column of a Kusto table."""

    name: str
    kusto_type: str
    docstring: str = ""

    def as_schema_fragment(self) -> str:
        return f"{self.name}:{self.kusto_type}"


@dataclass(frozen=True, slots=True)
class TableSchema:
    """A Kusto table definition."""

    name: str
    columns: tuple[ColumnSpec, ...]
    folder: str = ""
    docstring: str = ""

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    def column(self, name: str) -> ColumnSpec:
        for candidate in self.columns:
            if candidate.name == name:
                return candidate
        raise KeyError(f"{self.name} has no column {name!r}")


@dataclass(frozen=True, slots=True)
class QueryResult:
    """A single result table returned by a query or control command."""

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]
    client_request_id: str = ""
    elapsed_seconds: float = 0.0

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self.to_dicts())

    @property
    def is_empty(self) -> bool:
        return not self.rows

    def to_dicts(self) -> list[dict[str, Any]]:
        """Rows as dictionaries keyed by column name."""
        return [dict(zip(self.columns, row)) for row in self.rows]

    def scalar(self, default: Any = None) -> Any:
        """First cell of the first row, or ``default`` when the result is empty."""
        if self.is_empty or not self.columns:
            return default
        return self.rows[0][0]

    def column_values(self, name: str) -> list[Any]:
        """All values of one column, in row order."""
        try:
            index = self.columns.index(name)
        except ValueError as exc:
            raise KeyError(f"result has no column {name!r}; has {self.columns}") from exc
        return [row[index] for row in self.rows]

    def first(self) -> dict[str, Any] | None:
        """First row as a dictionary, or ``None`` when the result is empty."""
        dicts = self.to_dicts()
        return dicts[0] if dicts else None


@dataclass(frozen=True, slots=True)
class BatteryCase:
    """One query in the standardised test battery."""

    name: str
    description: str
    kql: str
    parameters: dict[str, Any] = field(default_factory=dict)
    expect_rows: int | None = None
    expect_min_rows: int | None = None
    expect_scalar: Any = None
    expect_columns: Sequence[str] = ()
