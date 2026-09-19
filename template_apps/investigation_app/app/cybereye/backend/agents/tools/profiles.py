"""Typed native tools; persistence and citation policy belong to SuspectProfiles."""

from typing import Any

from pydantic import ValidationError

from ..profiles import ProfileError, UpdateSuspectProfile
from .base import ToolContext, agent_tool, object_schema


@agent_tool(name="get_suspect_profile", datasource="none", category="suspect_profile",
    description="Read your persisted historical suspect profile and its current revision before updating. "
                "A profile_not_found result means expected_revision 0 for creation.",
    parameters=object_schema({"profile_id": {"type": "string", "minLength": 1, "maxLength": 80}},
                             ["profile_id"]))
def get_suspect_profile(context: ToolContext, *, profile_id: str) -> dict[str, Any]:
    if context.profiles is None or context.caller is None:
        return {"error": "profile_context_unavailable"}
    try:
        return {"profile": context.profiles.get(context.caller, profile_id).model_dump(mode="json")}
    except ProfileError as exc:
        return {"error": exc.code}


@agent_tool(name="update_suspect_profile", datasource="none", category="suspect_profile",
    description="Persist a historical suspect profile for the authenticated caller. Read its revision first. "
                "Replace identity and activity using evidence_ids returned by telemetry tools in THIS turn. "
                "Citations are resolved by the server; unsupported evidence and stale revisions refuse the write. "
                "Use expected_revision 0 only for a new profile. Never claim compromise or live activity.",
    parameters=UpdateSuspectProfile.model_json_schema())
def update_suspect_profile(context: ToolContext, *, profile_id: str, expected_revision: int,
                          identity: dict[str, Any], activity: list[dict[str, Any]]) -> dict[str, Any]:
    if context.profiles is None or context.caller is None or context.ledger is None:
        return {"error": "profile_context_unavailable"}
    try:
        update = UpdateSuspectProfile(profile_id=profile_id, expected_revision=expected_revision,
                                      identity=identity, activity=activity)
        profile = context.profiles.update(context.caller, update, context.ledger)
        return {"kind": "cybereye_tool_result", "category": "suspect_profile",
                "profile": profile.model_dump(mode="json"), "historical_replay": True}
    except ValidationError:
        return {"error": "invalid_profile_update"}
    except ProfileError as exc:
        return {"error": exc.code}