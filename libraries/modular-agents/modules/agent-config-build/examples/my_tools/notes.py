"""Example tool module — note search.

A tool module is an ordinary Python module. It imports the ``tool`` stamp and
nothing else from the agent machinery, so these functions are directly
callable in a unit test with no SDK, no config, and no agent.

The config references these by ``module.path:function_name``, and the import
prefix must be on the allowlist or resolution fails closed.
"""

from __future__ import annotations

from agentconfig import tool

# Stand-in for a real store. A tool's data source is its own business; the
# agent layer only sees the returned envelope.
_NOTES = {
    "onboarding": "New starters get a laptop on day one and a mentor in week one.",
    "release process": "Cut a tag, run the smoke suite, then deploy to staging.",
    "incident review": "Blameless. Written within two working days of resolution.",
}


@tool
def search_notes(query: str, limit: int = 3) -> dict:
    """Search the note store for a phrase and return matching notes.

    Use for any question about internal process or policy. Returns an empty
    ``notes`` list when nothing matches, which means the answer is not in the
    store -- say so rather than answering from memory.

    Args:
        query: Words to look for. Case-insensitive substring match.
        limit: Maximum notes to return.
    """
    # The docstring above is what the model reads. It states when to call the
    # tool and how to interpret an empty result, because a model cannot infer
    # either from a type signature.
    if not query or not query.strip():
        return {"status": "invalid_input", "reason": "query is empty", "notes": []}

    needle = query.strip().lower()
    hits = [
        {"title": title, "body": body}
        for title, body in _NOTES.items()
        if needle in title.lower() or needle in body.lower()
    ]

    # A uniform envelope means the model learns one result shape, not one per
    # tool. Status is an enum the model can dispatch on, never prose.
    return {
        "status": "ok" if hits else "no_results",
        "query": query.strip(),
        "count": len(hits),
        "notes": hits[: max(0, limit)],
    }
