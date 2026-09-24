"""Example tool module — text utilities.

Shows two things the notes module does not: a tool with no side effects and no
external dependency, and a tool that is deliberately NOT stamped so it stays
private to the module.
"""

from __future__ import annotations

from agentconfig import tool


@tool
def word_count(text: str) -> dict:
    """Count words and characters in a block of text.

    Use before deciding whether to quote a passage in full or summarise it.

    Args:
        text: The text to measure.
    """
    cleaned = (text or "").strip()
    return {
        "status": "ok",
        "words": len(cleaned.split()),
        "characters": len(cleaned),
    }


@tool(description="Return the first N sentences of a passage.")
def summarise_text(text: str, sentences: int = 2) -> dict:
    """Truncate a passage to its opening sentences.

    The explicit ``description`` above overrides this docstring for the model.
    Prefer relying on the docstring: one text then serves both the reader and
    the model, and cannot drift out of sync with itself.
    """
    parts = [s.strip() for s in (text or "").split(".") if s.strip()]
    kept = parts[: max(0, sentences)]
    return {
        "status": "ok" if kept else "no_results",
        "summary": ". ".join(kept) + ("." if kept else ""),
        "truncated": len(parts) > len(kept),
    }


def _normalise(text: str) -> str:
    """Private helper. No stamp, so it is invisible to the agent layer."""
    return " ".join((text or "").split())
