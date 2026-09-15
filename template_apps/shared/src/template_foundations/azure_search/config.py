"""Which search service to reach, resolved at call time rather than at import."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlparse

#: Entra ID audience covering both the management and the data plane of AI Search.
SEARCH_SCOPE = "https://search.azure.com/.default"

DEFAULT_SEARCH_API_VERSION = "2024-07-01"
DEFAULT_ENV_PREFIX = "SEARCH_"

#: The service rejects capitals and underscores; a name that looks fine returns 400.
_INDEX_NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class SearchConfigError(RuntimeError):
    """Configuration is missing or malformed."""


def valid_index_name(name: str) -> bool:
    """True when the service will accept ``name``: lowercase, digits, single dashes."""
    return bool(name) and len(name) <= 128 and bool(_INDEX_NAME.fullmatch(name))


@dataclass(frozen=True, slots=True)
class SearchConfig:
    """Endpoint, API version, and identity audience for one search service.

    Attributes:
        endpoint: ``https://<service>.search.windows.net``.
        api_version: Pinned data-plane API version.
        scope: Token audience.
        timeout_seconds: Per-request deadline. Without one the first call can hang forever.
        max_attempts: Total attempts for a retryable status.
    """

    endpoint: str
    api_version: str = DEFAULT_SEARCH_API_VERSION
    scope: str = SEARCH_SCOPE
    timeout_seconds: float = 60.0
    max_attempts: int = 4

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        if parsed.scheme != "https" or not parsed.netloc:
            raise SearchConfigError(f"endpoint must be an https URL, got {self.endpoint!r}")
        if self.timeout_seconds <= 0:
            raise SearchConfigError("timeout_seconds must be positive")
        if self.max_attempts < 1:
            raise SearchConfigError("max_attempts must be at least 1")

    @property
    def base_url(self) -> str:
        return self.endpoint.rstrip("/")

    def url(self, path: str) -> str:
        """Absolute URL for a data-plane path, with the pinned API version applied."""
        separator = "&" if "?" in path else "?"
        return f"{self.base_url}/{path.lstrip('/')}{separator}api-version={self.api_version}"

    @classmethod
    def from_env(cls, prefix: str = DEFAULT_ENV_PREFIX, **overrides: object) -> "SearchConfig":
        """Build from ``<prefix>*`` environment variables, read now, with overrides.

        Recognised keys: ``ENDPOINT`` (required), ``API_VERSION``, ``SCOPE``,
        ``TIMEOUT_SECONDS``, ``MAX_ATTEMPTS``.
        """
        def env(name: str) -> str | None:
            return os.environ.get(prefix + name)

        endpoint = overrides.pop("endpoint", None) or env("ENDPOINT")
        if not endpoint:
            raise SearchConfigError(f"{prefix}ENDPOINT is required when endpoint is not passed explicitly")

        values: dict[str, object] = {"endpoint": str(endpoint)}
        for key, caster in (
            ("API_VERSION", str),
            ("SCOPE", str),
            ("TIMEOUT_SECONDS", float),
            ("MAX_ATTEMPTS", int),
        ):
            raw = env(key)
            if raw is not None and raw != "":
                values[key.lower()] = caster(raw)
        values.update(overrides)
        try:
            return cls(**values)  # type: ignore[arg-type]
        except TypeError as exc:
            raise SearchConfigError(str(exc)) from exc
