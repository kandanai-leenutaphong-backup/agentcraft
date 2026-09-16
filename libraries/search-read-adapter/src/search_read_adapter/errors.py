"""Status-bearing compatibility errors without provider payload logging."""

from typing import Any


class SearchError(RuntimeError):
    """A failed call with its compatibility status and bounded message."""

    def __init__(self, status: int, message: str, *, body: Any = None) -> None:
        super().__init__(f"{status}: {message}")
        self.status = status
        self.message = message
        self.body = body
