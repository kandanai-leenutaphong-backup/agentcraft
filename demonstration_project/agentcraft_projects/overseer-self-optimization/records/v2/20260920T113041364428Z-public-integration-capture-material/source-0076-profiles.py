"""Owner-scoped historical profiles shared by HTTP and native agent tools."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from ..security.principal import Principal
from ..security.sessions import OwnedCache
from .tools.diagnosis import EvidenceLedger


Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ProfileId = Annotated[str, StringConstraints(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,79}$")]


class ProfileError(Exception):
    def __init__(self, status: int, code: str) -> None:
        self.status = status
        self.code = code
        super().__init__(code)


class ProfileFields(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SuspectIdentity(ProfileFields):
    account: Text
    display_name: Text


class HistoricalActivity(ProfileFields):
    timestamp: Annotated[str, StringConstraints(min_length=1, max_length=60)]
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
    evidence_ids: list[Text] = Field(min_length=1, max_length=4)

    @field_validator("timestamp")
    @classmethod
    def timestamp_has_offset(cls, value: str) -> str:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("historical timestamp must include a UTC offset")
        return value


class UpdateSuspectProfile(ProfileFields):
    profile_id: ProfileId
    expected_revision: int = Field(ge=0, strict=True)
    identity: SuspectIdentity
    activity: list[HistoricalActivity] = Field(min_length=1, max_length=20)


class Retrieval(ProfileFields):
    retrieval_id: str
    tool: str
    display_name: str
    datasource: str
    query: str
    retrieved_at: str
    row_count: int


class ProfileCitation(ProfileFields):
    evidence_id: Text
    record: dict[str, str | int | float | bool]
    retrieval: Retrieval


class SuspectProfile(ProfileFields):
    profile_id: ProfileId
    revision: int
    identity: SuspectIdentity
    activity: list[HistoricalActivity]
    citations: list[ProfileCitation]
    updated_at: str
    historical_replay: Literal[True] = True


def profile_owner(caller: Principal) -> str:
    if (not caller.id or caller.issuer not in {"local-preview", "entra", "signed-dev-access"}
            or caller.kind not in {"user", "service"}):
        raise ProfileError(403, "profile_forbidden")
    return caller.id


class SuspectProfiles:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._evidence = OwnedCache[tuple[str, EvidenceLedger]]()
        path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as database:
            database.execute("CREATE TABLE IF NOT EXISTS profiles (owner TEXT NOT NULL, "
                             "id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, "
                             "PRIMARY KEY (owner, id))")

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=5)

    def retain_evidence(self, caller: Principal, run_id: str, ledger: EvidenceLedger) -> None:
        self._evidence.put(profile_owner(caller), (run_id, ledger))

    def evidence(self, caller: Principal, run_id: str) -> EvidenceLedger:
        evidence = self._evidence.get(profile_owner(caller))
        if not evidence or evidence[0] != run_id:
            raise ProfileError(422, "profile_evidence_run_unavailable")
        return evidence[1]

    def list(self, caller: Principal) -> list[SuspectProfile]:
        owner = profile_owner(caller)
        with self._connect() as database:
            rows = database.execute("SELECT payload FROM profiles WHERE owner = ? ORDER BY id",
                                    (owner,)).fetchall()
        return [SuspectProfile.model_validate_json(row[0]) for row in rows]

    def get(self, caller: Principal, profile_id: str) -> SuspectProfile:
        owner = profile_owner(caller)
        with self._connect() as database:
            row = database.execute("SELECT payload FROM profiles WHERE owner = ? AND id = ?",
                                   (owner, profile_id)).fetchone()
        if row is None:
            raise ProfileError(404, "profile_not_found")
        return SuspectProfile.model_validate_json(row[0])

    def update(self, caller: Principal, update: UpdateSuspectProfile,
               ledger: EvidenceLedger) -> SuspectProfile:
        owner = profile_owner(caller)
        citations: dict[str, ProfileCitation] = {}
        for activity in update.activity:
            resolved, unsupported = ledger.resolve(activity.evidence_ids)
            if unsupported or not resolved:
                raise ProfileError(422, "unsupported_profile_citations")
            if not any(item["record"].get("resource_id") for item in resolved):
                raise ProfileError(422, "profile_activity_requires_telemetry")
            for item in resolved:
                citations[item["evidence_id"]] = ProfileCitation.model_validate(item)
        with self._connect() as database:
            database.execute("BEGIN IMMEDIATE")
            row = database.execute("SELECT revision FROM profiles WHERE owner = ? AND id = ?",
                                   (owner, update.profile_id)).fetchone()
            revision = row[0] if row else 0
            if revision != update.expected_revision:
                raise ProfileError(409, "stale_profile_revision")
            result = SuspectProfile(profile_id=update.profile_id, revision=revision + 1,
                identity=update.identity, activity=update.activity, citations=list(citations.values()),
                updated_at=datetime.now(timezone.utc).isoformat())
            database.execute("INSERT INTO profiles VALUES (?, ?, ?, ?) ON CONFLICT(owner, id) "
                             "DO UPDATE SET revision=excluded.revision, payload=excluded.payload",
                             (owner, result.profile_id, result.revision, result.model_dump_json()))
        return result