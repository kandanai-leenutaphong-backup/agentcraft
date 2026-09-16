"""Explicit failures. A failure is never an empty successful detection."""

from __future__ import annotations


class ConfigurationError(ValueError):
    """A configuration, window or callback contract was violated."""


class RuleExecutionError(RuntimeError):
    """A rule's query or processing stage failed, or returned nothing usable."""

    def __init__(
        self, rule_set_id: str, rule_id: str, stage: str, message: str,
        *, code: str = "rule_execution_failed",
    ) -> None:
        super().__init__(f"[{rule_set_id}/{rule_id}] {stage}: {message}")
        self.rule_set_id = rule_set_id
        self.rule_id = rule_id
        self.stage = stage
        self.code = code


__all__ = ["ConfigurationError", "RuleExecutionError"]
