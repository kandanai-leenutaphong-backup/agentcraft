"""Where ARM lives and what audience it accepts, resolved when asked, never at import."""

from __future__ import annotations

import os
from dataclasses import dataclass

#: Azure public cloud. Sovereign clouds differ, so both are overridable per call.
DEFAULT_ARM_ENDPOINT = "https://management.azure.com"
DEFAULT_ARM_SCOPE = "https://management.azure.com/.default"
DEFAULT_ENV_PREFIX = "ARM_"


class ArmConfigError(RuntimeError):
    """Configuration is missing or malformed."""


@dataclass(frozen=True, slots=True)
class ArmConfig:
    endpoint: str = DEFAULT_ARM_ENDPOINT
    scope: str = DEFAULT_ARM_SCOPE
    timeout_seconds: float = 120.0
    max_attempts: int = 4

    def __post_init__(self) -> None:
        if not self.endpoint.startswith("https://"):
            raise ArmConfigError(f"ARM endpoint must be https: {self.endpoint!r}")
        if self.max_attempts < 1:
            raise ArmConfigError("max_attempts must be at least 1")

    @classmethod
    def from_env(cls, prefix: str = DEFAULT_ENV_PREFIX, **overrides: object) -> ArmConfig:
        """Read the environment now, not at import. Explicit keywords beat both."""
        def read(key: str, fallback: str) -> str:
            return (os.environ.get(f"{prefix}{key}") or "").strip() or fallback

        values: dict[str, object] = {
            "endpoint": read("ENDPOINT", DEFAULT_ARM_ENDPOINT).rstrip("/"),
            "scope": read("SCOPE", DEFAULT_ARM_SCOPE),
            "timeout_seconds": float(read("TIMEOUT_SECONDS", "120")),
            "max_attempts": int(read("MAX_ATTEMPTS", "4")),
        }
        values.update({name: value for name, value in overrides.items() if value is not None})
        return cls(**values)  # type: ignore[arg-type]

    def describe(self) -> dict[str, object]:
        """Non-secret configuration. Makes no request and never carries a token."""
        return {
            "endpoint": self.endpoint,
            "scope": self.scope,
            "timeout_seconds": self.timeout_seconds,
            "max_attempts": self.max_attempts,
        }


__all__ = [
    "ArmConfig",
    "ArmConfigError",
    "DEFAULT_ARM_ENDPOINT",
    "DEFAULT_ARM_SCOPE",
    "DEFAULT_ENV_PREFIX",
]
