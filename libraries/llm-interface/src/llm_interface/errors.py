from __future__ import annotations


class LlmError(Exception):
    """Stable, payload-free failure code and a supported next action."""

    def __init__(self, code: str, *, category: str = "invalid", action: str = "Check the caller guide.", field: str | None = None) -> None:
        self.code = code
        self.category = category
        self.action = action
        self.field = field
        super().__init__(f"{category}: {code}. {action}")

    def metadata(self) -> dict[str, str | None]:
        return {"code": self.code, "category": self.category, "field": self.field, "action": self.action}