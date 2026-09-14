"""Connection coordinates — one frozen, validated config object.

WHY THIS EXISTS
---------------
The three ways an Azure OpenAI call fails before it ever leaves the process
are a mis-shaped endpoint, a model name that is not a deployment name, and
an API key that the account refuses. All three are decidable at startup.
:class:`FoundryConfig` decides them there: it normalises the endpoint to the
exact ``/openai/v1/`` base URL the OpenAI SDK expects, validates deployment
syntax, and refuses key material outright. The portable copy requires an endpoint.

Frozen, so a request handler cannot mutate the object every other request
handler is sharing. Use :meth:`FoundryConfig.with_overrides` for a variant.

WHY THERE IS NO API KEY FIELD
-----------------------------
The account has ``disableLocalAuth=true``. A key would be rejected at the
service, so accepting one here would only move a 401 later in time and
persuade a caller to put a secret in a config file first. Entra only.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from azllm.deployments import DEFAULT_DEPLOYMENT, DEFAULT_ENDPOINT, DEFAULT_SCOPE
from azllm.errors import ConfigError

# The SDK's own default is 10 minutes, which turns a wedged deployment into a
# wedged worker. A reasoning model can legitimately take a while, so the
# default is generous but finite.
DEFAULT_TIMEOUT_SECS = 120.0

# The SDK retries 408/409/429/5xx with exponential backoff. Two is the SDK
# default and is kept: more retries against a 429 deepens the queue.
DEFAULT_MAX_RETRIES = 2

# Above this, a "retry" strategy is really a queue and belongs in the caller.
_MAX_ALLOWED_RETRIES = 10

# Deployment names are restricted by ARM to this alphabet; enforcing it turns
# an injected value into a config error rather than a strange URL path.
_DEPLOYMENT_ALLOWED = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)
_MAX_DEPLOYMENT_LEN = 64

ENV_PREFIX = "AZURE_LLM_"

# Set by convention for key-based Azure OpenAI access. Their presence means
# somebody expects key auth to work here; it does not, and silently ignoring
# them would leave that person debugging a 401.
_KEY_ENV_SUFFIXES = ("API_KEY", "KEY")
_FOREIGN_KEY_ENV = ("AZURE_OPENAI_API_KEY", "OPENAI_API_KEY")


def normalize_endpoint(raw: str) -> str:
    """Return the exact ``https://host[/path]/openai/v1/`` base URL.

    Accepts every shape a human plausibly pastes: a bare hostname, the
    portal's account endpoint with or without a trailing slash, or a URL that
    already ends in ``/openai`` or ``/openai/v1``. The trailing slash matters:
    ``httpx`` resolves a relative request path against the base URL, and
    without it the last path segment is discarded.

    Raises:
        ConfigError: if the value is empty, is not https, embeds credentials,
            or carries a query string or fragment.
    """
    value = (raw or "").strip()
    if not value:
        raise ConfigError("endpoint is empty; set AZURE_LLM_ENDPOINT or pass endpoint=")
    if any(ch.isspace() for ch in value):
        raise ConfigError("endpoint contains whitespace")

    if "://" not in value:
        value = "https://" + value

    parts = urlsplit(value)
    if parts.scheme != "https":
        raise ConfigError(
            f"endpoint scheme must be https, got {parts.scheme!r}; "
            "an Entra bearer token must never travel in clear text"
        )
    if parts.username or parts.password:
        raise ConfigError("endpoint must not embed credentials")
    if not parts.hostname:
        raise ConfigError("endpoint has no host")
    if parts.query or parts.fragment:
        raise ConfigError(
            "endpoint must not carry a query string or fragment "
            "(an api-key query parameter will not work: local auth is disabled)"
        )

    host = parts.netloc.lower()
    path = parts.path.rstrip("/")
    if ".." in path:
        raise ConfigError("endpoint path must not contain '..'")

    # Idempotent: normalising an already-normalised endpoint is a no-op.
    for suffix in ("/openai/v1", "/openai"):
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break

    return f"https://{host}{path}/openai/v1/"


def _validate_deployment(name: str) -> str:
    value = (name or "").strip()
    if not value:
        raise ConfigError("deployment is empty; on Azure OpenAI 'model' is the deployment name")
    if len(value) > _MAX_DEPLOYMENT_LEN:
        raise ConfigError(f"deployment name is longer than {_MAX_DEPLOYMENT_LEN} characters")
    bad = sorted(set(value) - _DEPLOYMENT_ALLOWED)
    if bad:
        raise ConfigError(
            f"deployment name contains characters not allowed by Azure: {''.join(bad)!r}"
        )
    return value


def _validate_scope(scope: str) -> str:
    value = (scope or "").strip()
    if not value.endswith("/.default"):
        raise ConfigError(
            "credential_scope must be a resource scope ending in '/.default', "
            f"got {value!r}"
        )
    if not value.startswith("https://"):
        raise ConfigError("credential_scope must start with https://")
    return value


@dataclass(frozen=True)
class FoundryConfig:
    """Everything needed to reach one Azure AI Foundry / Azure OpenAI account.

    The endpoint is required. The deployment default is a neutral label,
    not a claim about an account's inventory; pass the deployed name explicitly.

    Attributes:
        endpoint: Account endpoint in any accepted shape. Normalised on
            construction; read :attr:`base_url` for what the SDK is given.
        deployment: Default deployment name, overridable per call.
        credential_scope: Entra scope requested for data-plane tokens.
        timeout_secs: Per-request client-side deadline, in seconds.
        max_retries: SDK-level retries for retryable statuses.
        managed_identity_client_id: Client id of a user-assigned managed
            identity. Required when the host has more than one assigned;
            ``DefaultAzureCredential`` cannot guess which.
        default_max_output_tokens: Optional ceiling applied to convenience
            calls that do not set their own. A cost guard, not a limit on
            the raw pass-through.
    """

    endpoint: str = DEFAULT_ENDPOINT
    deployment: str = DEFAULT_DEPLOYMENT
    credential_scope: str = DEFAULT_SCOPE
    timeout_secs: float = DEFAULT_TIMEOUT_SECS
    max_retries: int = DEFAULT_MAX_RETRIES
    managed_identity_client_id: str | None = None
    default_max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint", normalize_endpoint(self.endpoint))
        object.__setattr__(self, "deployment", _validate_deployment(self.deployment))
        object.__setattr__(self, "credential_scope", _validate_scope(self.credential_scope))

        timeout = self.timeout_secs
        if not isinstance(timeout, (int, float)) or isinstance(timeout, bool):
            raise ConfigError("timeout_secs must be a number")
        if not math.isfinite(float(timeout)) or float(timeout) <= 0:
            raise ConfigError(f"timeout_secs must be a positive finite number, got {timeout!r}")
        object.__setattr__(self, "timeout_secs", float(timeout))

        retries = self.max_retries
        if not isinstance(retries, int) or isinstance(retries, bool):
            raise ConfigError("max_retries must be an int")
        if retries < 0 or retries > _MAX_ALLOWED_RETRIES:
            raise ConfigError(
                f"max_retries must be between 0 and {_MAX_ALLOWED_RETRIES}, got {retries}"
            )

        client_id = self.managed_identity_client_id
        if client_id is not None:
            cleaned = client_id.strip()
            if not cleaned:
                raise ConfigError(
                    "managed_identity_client_id is blank; leave it None to use the ambient identity"
                )
            object.__setattr__(self, "managed_identity_client_id", cleaned)

        cap = self.default_max_output_tokens
        if cap is not None and (not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0):
            raise ConfigError("default_max_output_tokens must be a positive int or None")

    @property
    def base_url(self) -> str:
        """The normalised ``/openai/v1/`` base URL handed to the OpenAI SDK."""
        return self.endpoint

    @property
    def account_host(self) -> str:
        """Hostname only — safe to log, identifies the account, carries no secret."""
        return urlsplit(self.endpoint).netloc

    def with_overrides(self, **changes: object) -> "FoundryConfig":
        """Return a validated copy with ``changes`` applied."""
        unknown = set(changes) - {f for f in FoundryConfig.__dataclass_fields__}
        if unknown:
            raise ConfigError(f"unknown config field(s): {', '.join(sorted(unknown))}")
        return replace(self, **changes)  # type: ignore[arg-type]

    @classmethod
    def from_env(
        cls,
        prefix: str = ENV_PREFIX,
        env: dict[str, str] | None = None,
    ) -> "FoundryConfig":
        """Build a config from environment variables under ``prefix``.

        Reads ``ENDPOINT``, ``DEPLOYMENT``, ``SCOPE``, ``TIMEOUT_SECONDS``,
        ``MAX_RETRIES``, ``CLIENT_ID`` and ``MAX_OUTPUT_TOKENS``. Anything
        unset keeps its neutral default; an unset endpoint is rejected.

        Raises:
            ConfigError: if a value is malformed, or if key-auth environment
                variables are present — the account refuses keys, and quietly
                ignoring them hides the real reason for the later 401.
        """
        source = dict(os.environ if env is None else env)
        prefixed = {
            key: value
            for key, value in source.items()
            if prefix and key.startswith(prefix)
        }
        for key in prefixed:
            tail = key[len(prefix) :]
            if tail in _KEY_ENV_SUFFIXES:
                raise ConfigError(
                    f"{key} is set, but this account has local auth disabled. "
                    "Remove it and use Entra (az login, or a managed identity)."
                )
        for key in _FOREIGN_KEY_ENV:
            if source.get(key):
                raise ConfigError(
                    f"{key} is set, but key auth is refused by the account. "
                    "Unset it so the SDK cannot pick it up implicitly."
                )

        def read(name: str) -> str | None:
            raw = source.get(f"{prefix}{name}")
            if raw is None:
                return None
            value = raw.strip()
            return value or None

        def read_int(name: str) -> int | None:
            value = read(name)
            if value is None:
                return None
            try:
                return int(value)
            except ValueError as exc:
                raise ConfigError(f"{prefix}{name} must be an integer, got {value!r}") from exc

        def read_float(name: str) -> float | None:
            value = read(name)
            if value is None:
                return None
            try:
                return float(value)
            except ValueError as exc:
                raise ConfigError(f"{prefix}{name} must be a number, got {value!r}") from exc

        fields: dict[str, object] = {}
        for field_name, value in (
            ("endpoint", read("ENDPOINT")),
            ("deployment", read("DEPLOYMENT")),
            ("credential_scope", read("SCOPE")),
            ("timeout_secs", read_float("TIMEOUT_SECONDS")),
            ("max_retries", read_int("MAX_RETRIES")),
            ("managed_identity_client_id", read("CLIENT_ID")),
            ("default_max_output_tokens", read_int("MAX_OUTPUT_TOKENS")),
        ):
            if value is not None:
                fields[field_name] = value

        return cls(**fields)  # type: ignore[arg-type]
