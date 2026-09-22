"""An in-memory fixture, not an Azure connector or a production data store."""

from agentconfig import tool
from toolshape import Param, ToolSpec, integer_range, label, purpose_built

_NOTES = (
    {"title": "Configuration", "text": "An agent is a YAML entry plus prompt files."},
    {"title": "Tools", "text": "Purpose-built tools validate inputs before calling a backend."},
    {"title": "Hosting", "text": "Foundry hosted agents run a portable flat source bundle."},
)


@tool
@purpose_built(ToolSpec(
    name="search_notes",
    purpose="Search the bundled example notes.",
    call_when="Use when the question concerns configuration, tools, or hosting.",
    params=(
        Param("query", "Words to find in a note.", label(max_len=80)),
        Param("limit", "Maximum matching notes.", integer_range(1, 5), required=False, default=3),
    ),
    returns="A table of title and text; empty rows mean no matching example note.",
    dedupe_on=("query", "limit"),
))
def search_notes(query: str, limit: int = 3) -> tuple:
    matches = [note for note in _NOTES if query.casefold() in str(note).casefold()]
    return ["title", "text"], matches[:limit]


@tool
@purpose_built(ToolSpec(
    name="list_topics",
    purpose="List the topics covered by the example notes.",
    call_when="Use before searching when the available topics are unknown.",
    returns="A table with one title per available topic.",
))
async def list_topics() -> tuple:
    return ["title"], [{"title": note["title"]} for note in _NOTES]