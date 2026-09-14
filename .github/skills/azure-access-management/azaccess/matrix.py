"""The support matrix, derived from the adapters rather than written by hand.

WHY DERIVED
-----------
A hand-written support table is a promise nobody checks, and it decays the
first time an adapter changes. This module reads ``operations`` off the
provider classes themselves, so the matrix cannot claim an operation the code
does not carry, and the selftest asserts the table against the classes.

THE FOUR STATUSES, AND WHAT EACH IS ALLOWED TO CLAIM
----------------------------------------------------
``implemented``   a code path builds the request, parses the response, and is
                  exercised offline against a recorded transport.
``delegated``     the request or statement is built and validated here, and
                  executed by something the host supplies (a SQL executor).
``documented``    no code path. A written procedure in CONTRACT.md, because
                  the operation is real and an operator still needs to do it.
``unsupported``   refused in code, on purpose.

WHAT NO STATUS MEANS
--------------------
None of them means "verified against Azure". Nothing in this package has been
run against a live subscription as shipped, and a recorded fake is proof that
a request is *built* correctly, never that a service accepted it. That
distinction is the difference between an honest matrix and a decorative one,
so it is stated in :data:`LIVE_VERIFICATION`, printed with the table, and
asserted by the tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

STATUSES: tuple[str, ...] = ("implemented", "delegated", "documented", "unsupported")

EVIDENCE: dict[str, str] = {
    "implemented": "offline: request and response asserted against a recorded transport",
    "delegated": "offline: statement construction and refusals asserted; execution host-supplied",
    "documented": "none: written procedure only",
    "unsupported": "offline: the refusal itself is asserted",
}

#: Read this before quoting the matrix at anyone.
LIVE_VERIFICATION = (
    "No row in this matrix has been verified against a live Azure tenant by "
    "this package's tests. Recorded-transport evidence proves the request is "
    "serialised correctly, not that a service accepted it."
)


@dataclass(frozen=True)
class MatrixRow:
    plane: str
    operation: str
    status: str
    evidence: str

    def to_dict(self) -> dict[str, str]:
        return {
            "plane": self.plane,
            "operation": self.operation,
            "status": self.status,
            "evidence": self.evidence,
        }


def support_matrix(providers: Iterable[Any] | Mapping[str, Any] | None = None
                   ) -> tuple[MatrixRow, ...]:
    """Every operation every registered adapter declares.

    ``providers`` may be the mapping handed to
    :class:`~azaccess.engine.AccessManager`. With nothing passed, the matrix is
    built from the adapter classes, which is what documentation and the CLI
    want.
    """
    if providers is None:
        from azaccess.providers.arm import ArmRbacProvider
        from azaccess.providers.cosmos import CosmosSqlRbacProvider
        from azaccess.providers.graph import GraphAppRoleProvider
        from azaccess.providers.kusto import KustoDatabaseProvider
        from azaccess.providers.sql import SqlDatabaseUserProvider

        candidates: list[Any] = [
            ArmRbacProvider, CosmosSqlRbacProvider, KustoDatabaseProvider,
            SqlDatabaseUserProvider, GraphAppRoleProvider,
        ]
    elif isinstance(providers, Mapping):
        candidates = list(providers.values())
    else:
        candidates = list(providers)

    rows: list[MatrixRow] = []
    for candidate in candidates:
        plane = getattr(candidate, "plane", "")
        operations = dict(getattr(candidate, "operations", {}) or {})
        for operation, status in sorted(operations.items()):
            if status not in STATUSES:
                raise ValueError(
                    f"{plane}.{operation} declares unknown status '{status}'"
                )
            rows.append(MatrixRow(plane, operation, status, EVIDENCE[status]))
    return tuple(rows)


def render_matrix(rows: Iterable[MatrixRow] | None = None) -> str:
    """A Markdown table, so documentation can be regenerated, not maintained."""
    rows = tuple(rows) if rows is not None else support_matrix()
    width_plane = max([len(r.plane) for r in rows] + [5])
    width_op = max([len(r.operation) for r in rows] + [9])
    lines = [
        f"| {'plane'.ljust(width_plane)} | {'operation'.ljust(width_op)} | status      |",
        f"| {'-' * width_plane} | {'-' * width_op} | ----------- |",
    ]
    for row in rows:
        lines.append(
            f"| {row.plane.ljust(width_plane)} | "
            f"{row.operation.ljust(width_op)} | {row.status.ljust(11)} |"
        )
    lines.append("")
    lines.append(LIVE_VERIFICATION)
    return "\n".join(lines)


def counts(rows: Iterable[MatrixRow] | None = None) -> dict[str, int]:
    rows = tuple(rows) if rows is not None else support_matrix()
    out = {status: 0 for status in STATUSES}
    for row in rows:
        out[row.status] += 1
    return out


__all__ = ["EVIDENCE", "LIVE_VERIFICATION", "MatrixRow", "STATUSES", "counts",
           "render_matrix", "support_matrix"]
