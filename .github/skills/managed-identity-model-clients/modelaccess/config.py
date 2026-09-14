"""Connection coordinates — one frozen, validated config object.

WHY THIS EXISTS
---------------
The three ways an Azure OpenAI call fails before it ever leaves the process
are a mis-shaped endpoint, a model name that is not a deployment name, and
an API key that an Entra-only account refuses. All three are decidable at
startup. :class:`ModelConfig` decides them there: it normalises the endpoint
to the exact ``/openai/v1/`` base URL the OpenAI SDK expects, requires a
deployment name rather than guessing one, and refuses key material outright.

WHY THERE ARE NO DEFAULTS FOR ENDPOINT AND DEPLOYMENT
-----------------------------------------------------
A built-in default endpoint is one environment's address compiled into every
copy of the code. It survives a copy-paste into a new repository, points at
an account the new owner cannot reach, and produces a 401 or a 404 that reads
like a permissions problem. Both fields are required and the refusal names
the environment variable to set. See GOTCHAS.md, G1.

WHY EMBEDDINGS HAVE THEIR OWN FIELDS
------------------------------------
A deployment is reachable **only through the endpoint of the account that
owns it**, and an embedding deployment frequently lives on a different
account from the chat deployment. Assuming otherwise produces a 404 that
reads exactly like a misspelled deployment name. So the embedding deployment
is configured explicitly and never inferred. See GOTCHAS.md, G6.

Frozen, so a request handler cannot mutate the object every other request
handler is sharing. Use :meth:`ModelConfig.with_overrides` for a variant.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from modelaccess.errors import ConfigError

# The SDK's own default is 10 minutes, which turns a wedged deployment into a
# wedged worker. A reasoning model can legitimately take a while, so the
# default is generous but finite.
DEFAULT_TIMEOUT_SECS = 120.0

# The SDK retries 408/409/429/5xx with exponential backoff. Two is the SDK
# default and is kept: more retries against a 429 deepens the queue.
DEFAULT_MAX_RETRIES = 2

# Above this, a "retry" strategy is really a queue and belongs in the caller.
_MAX_ALLOWED_RETRIES = 10

# The documented public Entra scope for Azure AI Services data-plane calls.
# It is a service constant, not one environment's value, and every config can
# override it — some accounts are fronted by a different resource audience.
DEFAULT_SCOPE = "https://cognitiveservices.azure.com/.default"

# Deployment names are restricted by ARM to this alphabet; enforcing it turns
# an injected value into a config error rather than a strange URL path.
_DEPLOYMENT_ALLOWED = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_."
)
_MAX_DEPLOYMENT_LEN = 64

ENV_PREFIX = "MODEL_"

# Set by convention for key-based Azure OpenAI access. Their presence means
# somebody expects key auth to work here; this package never sends a key, and
# silently ignoring them would leave that person debugging a 401.
_KEY_ENV_SUFFIXES = ("API_KEY", "KEY")
_FOREIGN_KEY_ENV = ("AZURE_OPENAI_API_KEY", "OPENAI_API_KEY")


def normalize_endpoint(raw: str) -> str:
    """Return the exact ``https://host[/path]/openai/v1/`` base URL.

    Accepts every shape a human plausibly pastes: a bare hostname, the
    portal's account endpoint with or without a trailing slash, or a URL that
    already ends in ``/openai`` or ``/openai/v1``. The trailing slash matters:
    ``httpx`` resolves a relative request path against the base URL, and
    without it the last path segment is discarded. See GOTCHAS.md, G2.

    **This is shape validation, not a security control.** Every syntactically
    valid https URL is accepted, and an Entra bearer token for
    :data:`DEFAULT_SCOPE` is then sent to whatever host it names. The endpoint
    is trusted operator configuration; see :attr:`ModelConfig.allowed_hosts`
    and GOTCHAS.md, G15.

    Raises:
        ConfigError: if the value is empty, is not https, embeds credentials,
            or carries a query string or fragment.
    """
    value = (raw or "").strip()
    if not value:
        raise ConfigError(
            f"endpoint is empty; set {ENV_PREFIX}ENDPOINT or pass endpoint="
        )
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
            "(a key query parameter will not work on an Entra-only account)"
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


def _validate_deployment(name: str, *, field: str) -> str:
    value = (name or "").strip()
    if not value:
        raise ConfigError(
            f"{field} is empty; on Azure OpenAI 'model' is the deployment name — "
            f"set {ENV_PREFIX}{field.upper()} or pass {field}="
        )
    if len(value) > _MAX_DEPLOYMENT_LEN:
        raise ConfigError(f"{field} is longer than {_MAX_DEPLOYMENT_LEN} characters")
    bad = sorted(set(value) - _DEPLOYMENT_ALLOWED)
    if bad:
        raise ConfigError(
            f"{field} contains characters not allowed by Azure: {''.join(bad)!r}"
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
class ModelConfig:
    """Everything needed to reach one Azure AI Foundry / Azure OpenAI account.

    ``endpoint`` and ``deployment`` are required and have no defaults: this
    package ships no account catalogue and guesses nothing.

    Attributes:
        endpoint: Account endpoint in any accepted shape. Normalised on
            construction; read :attr:`base_url` for what the SDK is given.
        deployment: Default chat/responses deployment name, overridable per
            call.
        embedding_deployment: Deployment that serves ``embeddings.create``.
            None until configured, and :meth:`embed` refuses rather than
            sending an embedding request to a chat deployment.
        embedding_endpoint: Account endpoint that owns
            ``embedding_deployment`` when it is not the same account. None
            means "the same account as :attr:`endpoint`".
        credential_scope: Entra scope requested for data-plane tokens.
        timeout_secs: Per-request client-side deadline, in seconds.
        max_retries: SDK-level retries for retryable statuses.
        managed_identity_client_id: Client id of a user-assigned managed
            identity. Required when the host has more than one assigned;
            ``DefaultAzureCredential`` cannot guess which.
        default_max_output_tokens: Optional ceiling applied to convenience
            calls that do not set their own. A cost guard, not a limit on
            the raw pass-through.
        allowed_hosts: Optional tuple of hostnames this config may point at.
            None (the default) accepts any https host, which is correct when
            the endpoint is operator configuration and wrong when it is not:
            a config built from a tenant record, a request field or a
            user-editable settings row sends a bearer token wherever that
            value says. Set this from something the untrusted source cannot
            edit. Comparison is on the hostname, case-insensitive, port
            included when one is present. See GOTCHAS.md, G15.
    """

    endpoint: str
    deployment: str
    embedding_deployment: str | None = None
    embedding_endpoint: str | None = None
    credential_scope: str = DEFAULT_SCOPE
    timeout_secs: float = DEFAULT_TIMEOUT_SECS
    max_retries: int = DEFAULT_MAX_RETRIES
    managed_identity_client_id: str | None = None
    default_max_output_tokens: int | None = None
    allowed_hosts: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "endpoint", normalize_endpoint(self.endpoint))
        object.__setattr__(
            self, "deployment", _validate_deployment(self.deployment, field="deployment")
        )
        if self.embedding_deployment is not None:
            object.__setattr__(
                self,
                "embedding_deployment",
                _validate_deployment(
                    self.embedding_deployment, field="embedding_deployment"
                ),
            )
        if self.embedding_endpoint is not None:
            object.__setattr__(
                self, "embedding_endpoint", normalize_endpoint(self.embedding_endpoint)
            )
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
                    "managed_identity_client_id is blank; leave it None to use the "
                    "ambient identity"
                )
            object.__setattr__(self, "managed_identity_client_id", cleaned)

        cap = self.default_max_output_tokens
        if cap is not None and (not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0):
            raise ConfigError("default_max_output_tokens must be a positive int or None")

        allowed = self.allowed_hosts
        if allowed is not None:
            if isinstance(allowed, str) or not isinstance(allowed, (tuple, list)):
                raise ConfigError("allowed_hosts must be a tuple of hostnames, or None")
            hosts = tuple(str(host).strip().lower() for host in allowed)
            if not hosts or any(not host for host in hosts):
                raise ConfigError(
                    "allowed_hosts must not be empty or contain a blank entry; "
                    "pass None to allow any https host"
                )
            object.__setattr__(self, "allowed_hosts", hosts)
            for field_name in ("endpoint", "embedding_endpoint"):
                value = getattr(self, field_name)
                if value is None:
                    continue
                host = urlsplit(value).netloc.lower()
                if host not in hosts:
                    raise ConfigError(
                        f"{field_name} host {host!r} is not in allowed_hosts "
                        f"{hosts!r}; an Entra token would otherwise be sent there"
                    )

    @property
    def base_url(self) -> str:
        """The normalised ``/openai/v1/`` base URL handed to the OpenAI SDK."""
        return self.endpoint

    @property
    def account_host(self) -> str:
        """Hostname only — safe to log, identifies the account, carries no secret."""
        return urlsplit(self.endpoint).netloc

    @property
    def embeddings_are_local(self) -> bool:
        """True when the embedding deployment lives on :attr:`endpoint`'s account."""
        return self.embedding_endpoint is None or self.embedding_endpoint == self.endpoint

    def with_overrides(self, **changes: object) -> "ModelConfig":
        """Return a validated copy with ``changes`` applied."""
        unknown = set(changes) - {f for f in ModelConfig.__dataclass_fields__}
        if unknown:
            raise ConfigError(f"unknown config field(s): {', '.join(sorted(unknown))}")
        return replace(self, **changes)  # type: ignore[arg-type]

    @classmethod
    def from_env(
        cls,
        prefix: str = ENV_PREFIX,
        env: dict[str, str] | None = None,
    ) -> "ModelConfig":
        """Build a config from environment variables under ``prefix``.

        Reads ``ENDPOINT``, ``DEPLOYMENT``, ``EMBEDDING_DEPLOYMENT``,
        ``EMBEDDING_ENDPOINT``, ``SCOPE``, ``TIMEOUT_SECONDS``,
        ``MAX_RETRIES``, ``CLIENT_ID`` and ``MAX_OUTPUT_TOKENS``.

        Raises:
            ConfigError: if ``ENDPOINT`` or ``DEPLOYMENT`` is unset, if a
                value is malformed, or if key-auth environment variables are
                present — this package never sends a key, and quietly
                ignoring them hides the real reason for the later 401.
        """
        source = dict(os.environ if env is None else env)
        prefixed = [key for key in source if prefix and key.startswith(prefix)]
        for key in prefixed:
            tail = key[len(prefix) :]
            if tail in _KEY_ENV_SUFFIXES:
                raise ConfigError(
                    f"{key} is set, but this package authenticates with Entra only. "
                    "Remove it and sign in, or attach a managed identity."
                )
        for key in _FOREIGN_KEY_ENV:
            if source.get(key):
                raise ConfigError(
                    f"{key} is set, but this package never sends a key. "
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

        endpoint = read("ENDPOINT")
        if endpoint is None:
            raise ConfigError(
                f"{prefix}ENDPOINT is not set. This package ships no default account: "
                "set it to the endpoint of the account you are entitled to use."
            )
        deployment = read("DEPLOYMENT")
        if deployment is None:
            raise ConfigError(
                f"{prefix}DEPLOYMENT is not set. On Azure OpenAI this is the "
                "deployment name from the account, not the model family name."
            )

        fields: dict[str, object] = {"endpoint": endpoint, "deployment": deployment}
        for field_name, value in (
            ("embedding_deployment", read("EMBEDDING_DEPLOYMENT")),
            ("embedding_endpoint", read("EMBEDDING_ENDPOINT")),
            ("credential_scope", read("SCOPE")),
            ("timeout_secs", read_float("TIMEOUT_SECONDS")),
            ("max_retries", read_int("MAX_RETRIES")),
            ("managed_identity_client_id", read("CLIENT_ID")),
            ("default_max_output_tokens", read_int("MAX_OUTPUT_TOKENS")),
        ):
            if value is not None:
                fields[field_name] = value

        return cls(**fields)  # type: ignore[arg-type]


def embedding_config(
    config: ModelConfig,
    *,
    deployment: str | None = None,
    endpoint: str | None = None,
    **overrides: object,
) -> ModelConfig:
    """Return a config whose ``endpoint`` is the account owning the embeddings.

    A client is bound to one base URL. When the embedding deployment lives on
    a different account, one client cannot serve both, so this returns the
    second config to build the second client from::

        embeddings = connect(embedding_config(config))

    Args:
        config: The config to start from, so timeouts, retries and a managed
            identity client id survive.
        deployment: Embedding deployment name. Defaults to
            ``config.embedding_deployment``.
        endpoint: Account endpoint hosting it. Defaults to
            ``config.embedding_endpoint``, then to ``config.endpoint``.
        **overrides: Any other :class:`ModelConfig` field.

    Raises:
        ConfigError: when no embedding deployment is configured or passed.
            Guessing one is how a 404 gets misread as a typo.
    """
    target = deployment or config.embedding_deployment
    if not target:
        raise ConfigError(
            "no embedding deployment is configured; set "
            f"{ENV_PREFIX}EMBEDDING_DEPLOYMENT, pass embedding_deployment= to "
            "ModelConfig, or name one here. A chat deployment cannot serve "
            "embeddings and answers 404, which reads like a typo."
        )
    host = endpoint or config.embedding_endpoint or config.endpoint
    return config.with_overrides(
        endpoint=host,
        deployment=target,
        embedding_deployment=target,
        embedding_endpoint=host,
        **overrides,
    )


__all__ = [
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_SCOPE",
    "DEFAULT_TIMEOUT_SECS",
    "ENV_PREFIX",
    "ModelConfig",
    "embedding_config",
    "normalize_endpoint",
]
