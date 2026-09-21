"""Agent authoring and Investigator resolution over the application's allowed tool registry."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any

from ..security.principal import Principal
from .config import AgentSpec, describe_agent
from .library import AgentDraft, AgentLibrary, AgentVersion, InstructionFile, LibraryError
from .service import AgentService

INVESTIGATOR_TOOLS = frozenset({
    "get_situation_evidence", "search_mitre_attack", "record_situation_diagnosis",
    "record_sequence_step", "complete_sequence_of_events",
})


class AgentEditor:
    def __init__(self, root: Path, builtin: AgentSpec, models: tuple[str, ...] = ()) -> None:
        self.builtin = builtin
        self.tools = {tool.metadata.name: tool for tool in builtin.tools}
        self.investigator_tools = (INVESTIGATOR_TOOLS - {"get_situation_evidence"} | {"get_public_evidence"}
            if "get_public_evidence" in self.tools else INVESTIGATOR_TOOLS)
        self.library = AgentLibrary(
            root, builtin_id=builtin.agent_id,
            builtin=AgentDraft(name=builtin.name, model=builtin.model,
                               system_prompt="" if builtin.instruction_files else builtin.instructions,
                               instruction_files=[InstructionFile(name=name, content=content)
                                                  for name, content in builtin.instruction_files],
                               tool_ids=list(self.tools)),
            models=tuple(dict.fromkeys((builtin.model, *models))),
            tool_ids=frozenset(self.tools), investigator_tools=self.investigator_tools,
        )

    def describe_version(self, caller: Principal, record: AgentVersion) -> dict[str, Any]:
        versions = self.library.versions(caller, record.agent_id)
        return {**record.model_dump(exclude={"owner_id"}), "versions": versions,
            "version_names": self.library.version_names(caller, record.agent_id),
                "latest_version": versions[-1], "builtin": record.agent_id == self.builtin.agent_id}

    def catalogue(self, caller: Principal, datasources: dict[str, dict[str, Any]]) -> dict[str, Any]:
        assignment = self.library.assignment(caller)
        assigned = self.library.get(caller, assignment.agent_id, assignment.version)
        return {
            "agents": self.library.list(caller),
            "models": [{"id": model, "name": model} for model in self.library.models],
            "tools": describe_agent(self.builtin, datasources)["tools"],
            "foundation_files": [{"name": name, "content": content}
                                 for name, content in self.builtin.foundation_files],
            "investigator": assignment.model_dump(),
            "assigned_agent": {"id": assigned.agent_id, "name": assigned.name,
                               "model": assigned.model, "version": assigned.version,
                               "version_name": assigned.version_name},
            "investigator_required_tools": sorted(self.investigator_tools),
        }

    def investigator_spec(self, caller: Principal) -> AgentSpec:
        assignment = self.library.assignment(caller)
        version = self.library.get(caller, assignment.agent_id, assignment.version)
        self.library.validate(version)
        missing = self.investigator_tools - set(version.tool_ids)
        if missing:
            raise LibraryError(422, "The assigned Investigator is missing required tools")
        draft = version.model_dump(include=set(AgentDraft.model_fields))
        if (version.agent_id == self.builtin.agent_id and version.version == 1
                and draft == self.library.builtin.model_dump()):
            return self.builtin
        instructions = [content for _, content in self.builtin.foundation_files]
        if version.system_prompt.strip():
            instructions.append(version.system_prompt.strip())
        instructions.extend(item.content.strip() for item in version.instruction_files)
        fingerprint = hashlib.sha256(version.model_dump_json(exclude={"owner_id"}).encode("utf-8"))
        fingerprint.update("\n\n".join(instructions).encode("utf-8"))
        return replace(
            self.builtin, agent_id=version.agent_id, name=version.name, model=version.model,
            config_id=f"agent:{version.agent_id}", config_version=version.version,
            config_digest=fingerprint.hexdigest()[:12], instructions="\n\n".join(instructions),
            tools=tuple(self.tools[name] for name in version.tool_ids),
            instruction_files=tuple((item.name, item.content) for item in version.instruction_files),
        )

    def investigator(self, caller: Principal, base: AgentService) -> tuple[AgentService, AgentSpec]:
        spec = self.investigator_spec(caller)
        return (base if spec is self.builtin else base.with_spec(spec)), spec