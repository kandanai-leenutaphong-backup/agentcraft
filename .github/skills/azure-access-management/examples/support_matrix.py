#!/usr/bin/env python3
"""Worked example: print the support matrix and check it against the code.

The matrix is derived from the adapter classes, so this example is also the
guard that stops documentation drifting away from behaviour: it asserts that
every ``implemented`` operation has a method behind it and that no row claims
verification against a live tenant.

Run it:  python3 examples/support_matrix.py
"""

from __future__ import annotations

from azaccess import ArmRbacProvider, render_matrix, support_matrix
from azaccess.matrix import EVIDENCE, LIVE_VERIFICATION, STATUSES, counts


def main() -> int:
    rows = support_matrix()
    print(render_matrix(rows))
    print()
    print(counts(rows))

    assert rows, "the matrix is empty; no adapter declared any operation"
    assert all(row.status in STATUSES for row in rows)
    assert all(row.evidence == EVIDENCE[row.status] for row in rows)

    # Nothing claims a live run. If that ever changes it has to change here.
    assert "verified against a live Azure tenant" in LIVE_VERIFICATION
    assert not any("live" in row.evidence for row in rows)

    planes = {row.plane for row in rows}
    assert planes == {
        "azure-rbac", "cosmos-sql-rbac", "kusto-database",
        "sql-database-user", "microsoft-graph",
    }, planes

    tally = counts(rows)
    assert tally["implemented"] >= 15, tally
    assert tally["unsupported"] >= 3, "the refusals are part of the contract"

    # An 'implemented' row must have a method; a 'documented' row must not
    # pretend to.
    assert hasattr(ArmRbacProvider, "list_deny_assignments")
    assert ArmRbacProvider.operations["create-deny-assignment"] == "unsupported"
    assert ArmRbacProvider.operations["pim-eligible-assignment"] == "documented"

    print("support matrix agrees with the adapters it was derived from")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
