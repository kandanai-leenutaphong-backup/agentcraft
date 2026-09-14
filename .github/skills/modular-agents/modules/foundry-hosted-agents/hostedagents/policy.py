"""Operator-owned hosting policy; no tool or agent YAML can widen its grants."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator


class RuntimePolicy(BaseModel):
    """All effectful operations default to denied; bounds apply to every caller."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    allowed_tools: tuple[str, ...] = ()
    allow_model: StrictBool = False
    max_message_bytes: StrictInt = Field(default=16_000, ge=1, le=100_000)
    max_output_tokens: StrictInt = Field(default=2_000, ge=1, le=16_000)
    max_tool_rounds: StrictInt = Field(default=4, ge=1, le=8)
    max_tool_calls: StrictInt = Field(default=16, ge=1, le=64)
    max_result_bytes: StrictInt = Field(default=60_000, ge=256, le=1_000_000)
    turn_timeout_seconds: StrictInt = Field(default=120, ge=1, le=240)
    max_concurrent_turns: StrictInt = Field(default=4, ge=1, le=32)

    @field_validator("allowed_tools")
    @classmethod
    def validate_tools(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value) or any(
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name) for name in value
        ):
            raise ValueError("allowed_tools must contain unique exact tool names")
        return value


class RuntimeTarget(BaseModel):
    """Non-secret model target; accepted only at the composition edge."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    model_endpoint: str = ""

    @field_validator("model_endpoint")
    @classmethod
    def validate_endpoint(cls, value: str) -> str:
        if not value:
            return ""
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.username or parsed.password or parsed.port not in (None, 443)
            or parsed.query or parsed.fragment
            or not re.fullmatch(
                r"[a-z0-9-]+\.(?:openai|services\.ai|cognitiveservices)\.azure\.com",
                parsed.hostname or "",
            )
            or parsed.path.rstrip("/") != "/openai/v1"
        ):
            raise ValueError("model_endpoint must be an Azure public-cloud HTTPS /openai/v1 endpoint")
        return value.rstrip("/")