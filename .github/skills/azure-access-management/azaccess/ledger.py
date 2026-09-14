"""A durable, content-addressed record of what a run created — and nothing more.

WHY IT EXISTS
-------------
``AccessManager`` kept ownership in a dict. A process that crashed between
``create`` and ``revoke`` therefore left a real grant with no record of it,
recoverable only by an operator who happened to know the assignment id. That is
an access leak with no changelog, which is the failure this whole skill exists
to prevent, so ownership is now optionally written to a file as it is made.

WHAT IT IS DELIBERATELY NOT
---------------------------
**Not authority.** A record loaded from disk comes back as
``source="ledger-unverified"`` and :meth:`AccessManager.revoke` will not delete
on the strength of it. A file is editable by anyone who can write to the
directory; treating it as proof of ownership would mean an attacker who can
append a line can make this package delete somebody else's assignment. The
ledger's job is to tell a human *where to look*, and to make
``--authorized-id`` a decision rather than an archaeology exercise.

**Not a preexistence oracle.** Absence from the ledger does not mean an
assignment did not exist before, and presence does not mean it did not.

**Not a global store.** One directory, named by the caller, holding one JSON
file per record whose filename is the SHA-256 of its canonical content. Writes
are atomic (temp file plus ``os.replace``); a corrupt or unreadable file is
reported, never skipped silently.

Nothing here writes a credential: the fields are ids, scopes, role names and
timestamps, exactly the fields already printed by ``to_dict``.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from azaccess.errors import CoordinateError
from azaccess.model import OwnershipRecord

LEDGER_VERSION = 1

_ALLOWED_FIELDS = (
    "assignment_id", "plane", "plan_id", "fingerprint", "principal_id",
    "scope", "role", "source", "created_at", "detail",
)


def _canonical(record: OwnershipRecord) -> str:
    payload = {k: getattr(record, k) for k in _ALLOWED_FIELDS}
    payload["ledger_version"] = LEDGER_VERSION
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


@dataclass
class OwnershipLedger:
    """Append-only ownership records under one explicitly named directory."""

    directory: Path

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def append(self, record: OwnershipRecord) -> Path:
        """Write one record. The filename is the digest of its content."""
        body = _canonical(record)
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        path = self.directory / f"{digest}.json"
        handle = tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=self.directory, delete=False
        )
        try:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
        finally:
            handle.close()
        os.replace(handle.name, path)
        return path

    def remove(self, assignment_id: str) -> int:
        """Drop every record naming ``assignment_id``. Returns how many."""
        removed = 0
        for path, record in self._read_files():
            if record.get("assignment_id") == assignment_id:
                path.unlink(missing_ok=True)
                removed += 1
        return removed

    def read_all(self) -> tuple[OwnershipRecord, ...]:
        """Every stored record, marked unverified.

        The ``source`` on disk is preserved in ``detail`` so an operator can
        see whether the original was created or pending, while the loaded
        record itself is never revocable.
        """
        out: list[OwnershipRecord] = []
        for path, payload in self._read_files():
            missing = [f for f in ("assignment_id", "plane", "fingerprint") if not payload.get(f)]
            if missing:
                raise CoordinateError(
                    f"ledger file {path.name} is missing {missing}; refusing to "
                    f"read a partial ownership record"
                )
            out.append(
                OwnershipRecord(
                    assignment_id=str(payload["assignment_id"]),
                    plane=str(payload["plane"]),
                    plan_id=str(payload.get("plan_id") or ""),
                    fingerprint=str(payload["fingerprint"]),
                    principal_id=str(payload.get("principal_id") or ""),
                    scope=str(payload.get("scope") or ""),
                    role=str(payload.get("role") or ""),
                    created_at=str(payload.get("created_at") or ""),
                    source="ledger-unverified",
                    detail=(
                        f"recorded as '{payload.get('source') or 'unknown'}' by plan "
                        f"{payload.get('plan_id') or 'unknown'}; not authority for a delete"
                    ),
                )
            )
        return tuple(sorted(out, key=lambda r: (r.plane, r.assignment_id)))

    def pending(self) -> tuple[OwnershipRecord, ...]:
        """Records whose original source was a long-running create."""
        return tuple(
            r for r in self.read_all() if "'pending'" in r.detail
        )

    def cleanup_report(self) -> dict[str, Any]:
        """What is outstanding, and how a human removes it by hand.

        No command here mutates anything on import or on print. They are the
        exact ids an operator would otherwise have to reconstruct.
        """
        records = self.read_all()
        return {
            "directory": str(self.directory),
            "records": [r.to_dict() for r in records],
            "pending": [r.to_dict() for r in self.pending()],
            "manual_cleanup": [
                _manual_command(r) for r in records
            ],
            "note": (
                "These records are evidence, not authority. Nothing in this "
                "package will delete an assignment because a file says it "
                "should; pass the id to revoke --authorized-id after checking "
                "it yourself."
            ),
        }

    def _read_files(self) -> Iterable[tuple[Path, dict[str, Any]]]:
        for path in sorted(self.directory.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise CoordinateError(
                    f"ledger file {path.name} is unreadable: {exc}"
                ) from None
            if not isinstance(payload, dict):
                raise CoordinateError(f"ledger file {path.name} is not an object")
            yield path, payload


def _manual_command(record: OwnershipRecord) -> str:
    if record.plane == "azure-rbac":
        return f"az role assignment delete --ids {record.assignment_id}"
    if record.plane in ("cosmos-sql-rbac", "kusto-database"):
        return f"az rest --method delete --url 'https://management.azure.com{record.assignment_id}?api-version=<plane api-version>'"
    if record.plane == "microsoft-graph":
        return f"az rest --method delete --url 'https://graph.microsoft.com/v1.0{record.assignment_id}'"
    if record.plane == "sql-database-user":
        return f"-- in the database: DROP USER for {record.assignment_id.rsplit('/users/', 1)[-1]}"
    return f"manual removal required for {record.assignment_id} on {record.plane}"


__all__ = ["LEDGER_VERSION", "OwnershipLedger"]
