from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit, urlunsplit

from .errors import LlmError


@dataclass(frozen=True)
class Limits:
    timeout_seconds: float = 120.0
    max_model_calls: int = 8
    max_tool_calls: int = 16
    max_output_tokens: int = 1024
    max_input_bytes: int = 128_000
    max_output_bytes: int = 1_000_000
    max_tool_result_bytes: int = 60_000
    max_concurrency: int = 4
    max_events: int = 10_000

    def __post_init__(self) -> None:
        if (type(self.timeout_seconds) not in (int, float)
                or not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0):
            raise LlmError("invalid_timeout", action="Set a finite positive timeout_seconds.", field="timeout_seconds")
        for name, value in asdict(self).items():
            if name != "timeout_seconds" and (type(value) is not int or value <= 0):
                raise LlmError("invalid_limit", action="Set a positive integer for this execution limit.", field=name)
        if self.max_concurrency > 64:
            raise LlmError("invalid_concurrency", action="Set max_concurrency between 1 and 64.")


@dataclass(frozen=True)
class Policy:
    allow_model_calls: bool = False
    allowed_tools: frozenset[str] = frozenset()
    limits: Limits = Limits()

    def __post_init__(self) -> None:
        if type(self.allow_model_calls) is not bool or not isinstance(self.limits, Limits):
            raise LlmError("invalid_policy")
        if isinstance(self.allowed_tools, (str, bytes)):
            raise LlmError("invalid_tool_grants")
        try:
            tools = frozenset(self.allowed_tools)
        except TypeError:
            raise LlmError("invalid_tool_grants") from None
        if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,63}", name) for name in tools):
            raise LlmError("invalid_tool_grants")
        object.__setattr__(self, "allowed_tools", tools)

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps({"allow_model_calls": self.allow_model_calls,
            "allowed_tools": sorted(self.allowed_tools), "limits": asdict(self.limits)}, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Capabilities:
    chat: bool = True
    streaming: bool = True
    tools: bool = True
    structured_output: bool = True
    embeddings: bool = True
    reasoning: bool = False

    def __post_init__(self) -> None:
        if any(type(value) is not bool for value in asdict(self).values()):
            raise LlmError("invalid_capabilities")


@dataclass(frozen=True)
class ConnectionConfig:
    endpoint: str
    model: str
    provider: str = "auto"
    embedding_model: str | None = None
    allowed_hosts: tuple[str, ...] | None = None
    credential_scope: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.endpoint, str) or any(character.isspace() for character in self.endpoint):
            raise LlmError("invalid_endpoint", category="config", action="Supply an explicit HTTPS model or Foundry project endpoint.")
        try:
            parsed = urlsplit(self.endpoint)
            valid = (parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password
                     and parsed.port in (None, 443) and not parsed.query and not parsed.fragment
                     and not re.search(r"%|\\|(?:^|/)\.{1,2}(?:/|$)", parsed.path))
        except ValueError:
            valid = False
        if not valid:
            raise LlmError("invalid_endpoint", category="config", action="Use an HTTPS endpoint without credentials, query, fragment or relative path segments.")
        host = parsed.hostname.lower()
        hosts = (host,) if self.allowed_hosts is None else self.allowed_hosts
        if isinstance(hosts, str) or not all(isinstance(value, str) and value == value.lower() for value in hosts) or host not in hosts:
            raise LlmError("endpoint_not_allowed", category="denied", action="Ask the operator to configure the approved host.")
        path = parsed.path.rstrip("/")
        provider = self.provider
        if provider == "auto":
            provider = "foundry" if "/api/projects/" in path else "azure_openai"
        if provider not in {"foundry", "azure_openai", "azure_completions", "openai", "openai_completions", "custom"}:
            raise LlmError("unknown_provider", category="unsupported", action="Use a registered provider or from_clients().")
        if provider == "foundry":
            if not re.fullmatch(r"/api/projects/[A-Za-z0-9_.-]+", path):
                raise LlmError("project_endpoint_required", category="config", action="Use the full /api/projects/<project> Foundry endpoint.")
        elif provider != "custom":
            if path not in {"", "/openai", "/openai/v1", "/v1"}:
                raise LlmError("unsupported_endpoint_path", category="config", action="Supply a model account origin or its /openai/v1 endpoint.")
            path = "/v1" if provider.startswith("openai") and path in {"", "/v1"} else "/openai/v1"
        for model in (self.model, self.embedding_model):
            if model is not None and (not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", model)):
                raise LlmError("invalid_model", category="config", action="Supply an explicit model/deployment identifier.")
        if not self.model:
            raise LlmError("model_required", category="config")
        scope = self.credential_scope or ("https://ai.azure.com/.default" if provider == "foundry" else "https://cognitiveservices.azure.com/.default")
        if not isinstance(scope, str) or not re.fullmatch(r"https://[A-Za-z0-9.-]+/\.default", scope):
            raise LlmError("invalid_credential_scope", category="config")
        object.__setattr__(self, "endpoint", urlunsplit(("https", parsed.netloc.lower(), path + "/", "", "")))
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "allowed_hosts", tuple(hosts))
        object.__setattr__(self, "credential_scope", scope)

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()