"""Caller-owned agent versions and role assignments stored as atomic local JSON files."""

from __future__ import annotations

import fcntl
import hashlib
import os
import re
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from ..security.principal import Principal

AGENT_ID = re.compile(r"[a-z][a-z0-9_]{0,79}")
MAX_INSTRUCTION_BYTES = 256_000


class LibraryError(ValueError):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status


class InstructionFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    content: str = Field(min_length=1, max_length=65_536)

    @field_validator("name")
    @classmethod
    def markdown_name(cls, value: str) -> str:
        if (not value.lower().endswith(".md") or value != value.strip()
                or any(character in value for character in ("/", "\\", "\x00"))
                or any(ord(character) < 32 for character in value)):
            raise ValueError("Instruction files must have a plain .md filename")
        return value

    @field_validator("content")
    @classmethod
    def nonempty_content(cls, value: str) -> str:
        if not value.strip() or "\x00" in value or len(value.encode("utf-8")) > 65_536:
            raise ValueError("Instruction files must contain text of at most 64 KiB")
        return value


class AgentDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    model: str = Field(min_length=1, max_length=120)
    version_name: str = Field(default="", max_length=80)
    system_prompt: str = Field(default="", max_length=65_536)
    instruction_files: list[InstructionFile] = Field(default_factory=list, max_length=12)
    tool_ids: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("name", "model")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(character) < 32 for character in value):
            raise ValueError("Name and model must be non-empty single-line text")
        return value

    @field_validator("version_name")
    @classmethod
    def single_line_version_name(cls, value: str) -> str:
        if any(ord(character) < 32 or ord(character) == 127 for character in value):
            raise ValueError("Version names must be single-line text")
        return value.strip()

    @model_validator(mode="after")
    def validate_instructions(self) -> AgentDraft:
        if not self.system_prompt.strip() and not self.instruction_files:
            raise ValueError("Add a system instruction or a Markdown instruction file")
        total = len(self.system_prompt.encode("utf-8")) + sum(
            len(item.content.encode("utf-8")) for item in self.instruction_files
        )
        if total > MAX_INSTRUCTION_BYTES or "\x00" in self.system_prompt:
            raise ValueError("Combined instructions must be text of at most 256 KiB")
        names = [item.name.casefold() for item in self.instruction_files]
        if len(names) != len(set(names)):
            raise ValueError("Instruction filenames must be unique")
        if len(self.tool_ids) != len(set(self.tool_ids)):
            raise ValueError("An agent cannot contain a tool more than once")
        return self


class SaveAgent(AgentDraft):
    base_version: int = Field(default=0, ge=0)
    expected_latest_version: int = Field(default=0, ge=0)


class AgentVersion(AgentDraft):
    schema_version: Literal[1] = 1
    agent_id: str
    version: int = Field(ge=1)
    base_version: int = Field(ge=0)
    created_at: str
    owner_id: str


class InvestigatorAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    version: int = Field(ge=1)
    revision: int = Field(ge=0)


class AssignInvestigator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agent_id: str
    version: int = Field(ge=1)
    expected_revision: int = Field(ge=0)


def authorize_library(caller: Principal) -> str:
    if (not caller.id or caller.issuer not in {"local-preview", "entra", "signed-dev-access"}
            or caller.kind not in {"user", "service"}):
        raise LibraryError(403, "This caller cannot manage an agent library")
    return caller.id


class AgentLibrary:
    def __init__(self, root: Path, *, builtin_id: str, builtin: AgentDraft,
                 models: tuple[str, ...], tool_ids: frozenset[str],
                 investigator_tools: frozenset[str]) -> None:
        self.root = root.resolve()
        self.builtin_id = builtin_id
        self.builtin = builtin
        self.models = models
        self.tool_ids = tool_ids
        self.investigator_tools = investigator_tools

    def _owner(self, caller: Principal) -> Path:
        owner = hashlib.sha256(authorize_library(caller).encode("utf-8")).hexdigest()
        directory = self.root / owner
        if not directory.resolve().is_relative_to(self.root):
            raise LibraryError(400, "Invalid library location")
        return directory

    def _agent(self, caller: Principal, agent_id: str) -> Path:
        if not AGENT_ID.fullmatch(agent_id):
            raise LibraryError(404, "Agent not found")
        directory = self._owner(caller) / agent_id
        if not directory.resolve().is_relative_to(self._owner(caller)):
            raise LibraryError(404, "Agent not found")
        return directory

    @contextmanager
    def _locked(self, caller: Principal):
        directory = self._owner(caller)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(directory / ".lock", os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @staticmethod
    def _write(path: Path, value: BaseModel, *, replace: bool = False) -> None:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                             prefix=".writing-", delete=False) as output:
                temporary = Path(output.name)
                output.write(value.model_dump_json(indent=2) + "\n")
                output.flush()
                os.fsync(output.fileno())
            if replace:
                os.replace(temporary, path)
            else:
                os.link(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def _seed(self, caller: Principal) -> AgentVersion:
        return AgentVersion(**self.builtin.model_dump(), agent_id=self.builtin_id, version=1,
                            base_version=0, created_at="", owner_id=authorize_library(caller))

    def versions(self, caller: Principal, agent_id: str) -> list[int]:
        directory = self._agent(caller, agent_id) / "versions"
        found = [int(path.stem) for path in directory.glob("*.json") if path.stem.isdecimal()]
        if agent_id == self.builtin_id:
            found.append(1)
        return sorted(set(found))

    def get(self, caller: Principal, agent_id: str, version: int | None = None) -> AgentVersion:
        versions = self.versions(caller, agent_id)
        if not versions or (version is not None and version not in versions):
            raise LibraryError(404, "Agent version not found")
        number = version if version is not None else versions[-1]
        path = self._agent(caller, agent_id) / "versions" / f"{number}.json"
        if number == 1 and agent_id == self.builtin_id and not path.exists():
            return self._seed(caller)
        try:
            record = AgentVersion.model_validate_json(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise LibraryError(404, "Agent version not found") from exc
        if record.owner_id != authorize_library(caller) or record.agent_id != agent_id or record.version != number:
            raise LibraryError(404, "Agent version not found")
        return record

    def version_names(self, caller: Principal, agent_id: str) -> dict[int, str]:
        return {number: self.get(caller, agent_id, number).version_name
                for number in self.versions(caller, agent_id)}

    def list(self, caller: Principal) -> list[dict]:
        directory = self._owner(caller)
        identifiers = {self.builtin_id}
        if directory.exists():
            identifiers.update(path.name for path in directory.iterdir()
                               if path.is_dir() and AGENT_ID.fullmatch(path.name))
        result = []
        for agent_id in sorted(identifiers):
            versions = self.versions(caller, agent_id)
            if not versions:
                continue
            latest = self.get(caller, agent_id, versions[-1])
            result.append({"id": agent_id, "name": latest.name, "model": latest.model,
                           "latest_version": latest.version, "versions": versions,
                           "version_names": self.version_names(caller, agent_id),
                           "builtin": agent_id == self.builtin_id, "tool_ids": latest.tool_ids})
        return result

    def _validate(self, draft: AgentDraft) -> None:
        if draft.model not in self.models:
            raise LibraryError(422, "Choose a configured model deployment")
        unknown = set(draft.tool_ids) - self.tool_ids
        if unknown:
            raise LibraryError(422, "Unknown tools: " + ", ".join(sorted(unknown)))

    def save(self, caller: Principal, draft: SaveAgent, agent_id: str | None = None) -> AgentVersion:
        authorize_library(caller)
        self._validate(draft)
        creating = agent_id is None
        agent_id = agent_id or "agent_" + uuid.uuid4().hex
        directory = self._agent(caller, agent_id)
        with self._locked(caller):
            versions = self.versions(caller, agent_id)
            latest = versions[-1] if versions else 0
            if not creating and not versions:
                raise LibraryError(404, "Agent not found")
            if draft.expected_latest_version != latest:
                raise LibraryError(409, "A newer version was saved. Reload before saving your changes.")
            if (creating and draft.base_version != 0) or (not creating and draft.base_version not in versions):
                raise LibraryError(409, "The version being edited no longer matches this agent")
            if agent_id == self.builtin_id and not (directory / "versions/1.json").exists():
                self._write(directory / "versions/1.json", self._seed(caller))
            record = AgentVersion(**draft.model_dump(exclude={"expected_latest_version", "base_version"}),
                                  agent_id=agent_id, version=latest + 1,
                                  base_version=draft.base_version,
                                  created_at=datetime.now(timezone.utc).isoformat(), owner_id=caller.id)
            self._write(directory / "versions" / f"{record.version}.json", record)
            return self.get(caller, agent_id, record.version)

    def assignment(self, caller: Principal) -> InvestigatorAssignment:
        path = self._owner(caller) / "roles.json"
        if not path.exists():
            return InvestigatorAssignment(agent_id=self.builtin_id, version=1, revision=0)
        return InvestigatorAssignment.model_validate_json(path.read_text(encoding="utf-8"))

    def assign(self, caller: Principal, request: AssignInvestigator) -> InvestigatorAssignment:
        with self._locked(caller):
            current = self.assignment(caller)
            if request.expected_revision != current.revision:
                raise LibraryError(409, "The Investigator assignment changed. Reload before assigning.")
            version = self.get(caller, request.agent_id, request.version)
            self._validate(version)
            missing = self.investigator_tools - set(version.tool_ids)
            if missing:
                raise LibraryError(422, "Investigator requires these tools: " + ", ".join(sorted(missing)))
            if version.agent_id == self.builtin_id and version.version == 1:
                path = self._agent(caller, self.builtin_id) / "versions/1.json"
                if not path.exists():
                    self._write(path, version)
            assignment = InvestigatorAssignment(agent_id=version.agent_id, version=version.version,
                                                revision=current.revision + 1)
            self._write(self._owner(caller) / "roles.json", assignment, replace=True)
            return self.assignment(caller)