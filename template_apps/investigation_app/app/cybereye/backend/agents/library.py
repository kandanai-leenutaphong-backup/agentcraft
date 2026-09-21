"""Investigation authorization and policy over the public agentconfig authoring store."""

from __future__ import annotations

from pathlib import Path

from agentconfig import (
    AGENT_ID, MAX_INSTRUCTION_BYTES, AgentAssignment, AgentDraft,
    AgentStoreError as LibraryError, AgentVersion, AgentVersionStore, AssignAgent, InstructionFile, SaveAgent,
)

from ..security.principal import Principal


class InvestigatorAssignment(AgentAssignment):
    """Investigator role response schema."""


class AssignInvestigator(AssignAgent):
    """Investigator role request schema."""


def authorize_library(caller: Principal) -> str:
    if (not caller.id or caller.issuer not in {"local-preview", "entra", "signed-dev-access"}
            or caller.kind not in {"user", "service"}):
        raise LibraryError(403, "This caller cannot manage an agent library")
    return caller.id


class AgentLibrary:
    def __init__(self, root: Path, *, builtin_id: str, builtin: AgentDraft,
                 models: tuple[str, ...], tool_ids: frozenset[str],
                 investigator_tools: frozenset[str], storage=None) -> None:
        self.models = models
        self.tool_ids = tool_ids
        self.investigator_tools = investigator_tools
        self._store = AgentVersionStore(root, builtin_id=builtin_id, builtin=builtin,
                                        validate=self.validate, validate_assignment=self.validate_assignment,
                                        storage=storage)

    @property
    def root(self) -> Path:
        return self._store.root

    @property
    def builtin_id(self) -> str:
        return self._store.builtin_id

    @property
    def builtin(self) -> AgentDraft:
        return self._store.builtin

    @builtin.setter
    def builtin(self, value: AgentDraft) -> None:
        self._store.builtin = value

    def versions(self, caller: Principal, agent_id: str) -> list[int]:
        return self._store.versions(authorize_library(caller), agent_id)

    def get(self, caller: Principal, agent_id: str, version: int | None = None) -> AgentVersion:
        return self._store.get(authorize_library(caller), agent_id, version)

    def version_names(self, caller: Principal, agent_id: str) -> dict[int, str]:
        return self._store.version_names(authorize_library(caller), agent_id)

    def list(self, caller: Principal) -> list[dict]:
        return self._store.list(authorize_library(caller))

    def validate(self, draft: AgentDraft) -> None:
        if draft.model not in self.models:
            raise LibraryError(422, "Choose a configured model deployment")
        unknown = set(draft.tool_ids) - self.tool_ids
        if unknown:
            raise LibraryError(422, "Unknown tools: " + ", ".join(sorted(unknown)))

    def validate_assignment(self, version: AgentVersion) -> None:
        missing = self.investigator_tools - set(version.tool_ids)
        if missing:
            raise LibraryError(422, "Investigator requires these tools: " + ", ".join(sorted(missing)))

    def save(self, caller: Principal, draft: SaveAgent, agent_id: str | None = None) -> AgentVersion:
        return self._store.save(authorize_library(caller), draft, agent_id)

    def assignment(self, caller: Principal) -> InvestigatorAssignment:
        assignment = self._store.assignment(authorize_library(caller))
        return InvestigatorAssignment(**assignment.model_dump())

    def assign(self, caller: Principal, request: AssignInvestigator) -> InvestigatorAssignment:
        owner_id = authorize_library(caller)
        try:
            assignment = self._store.assign(owner_id, request)
        except LibraryError as exc:
            if exc.status == 409:
                raise LibraryError(409, "The Investigator assignment changed. Reload before assigning.") from exc
            raise
        return InvestigatorAssignment(**assignment.model_dump())