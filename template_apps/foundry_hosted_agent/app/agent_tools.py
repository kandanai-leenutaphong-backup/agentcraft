"""Example deterministic tool: no network, files, credentials or subprocesses. Replace or extend."""

MAX_TEXT_CHARACTERS = 4096


def count_words(text: str) -> dict[str, int]:
    """Count whitespace-separated words and characters in the supplied text."""
    if not isinstance(text, str) or len(text) > MAX_TEXT_CHARACTERS:
        raise ValueError(f"text must be a string of at most {MAX_TEXT_CHARACTERS} characters")
    return {"words": len(text.split()), "characters": len(text)}
