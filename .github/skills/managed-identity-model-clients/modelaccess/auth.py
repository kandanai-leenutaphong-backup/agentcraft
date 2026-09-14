"""Entra token providers — one callable, re-invoked per request.

WHY THIS EXISTS
---------------
The OpenAI SDK accepts ``api_key`` as either a string or a zero-argument
callable, and calls the callable on *every* request. That is the whole reason
identity works cleanly here: hand it the callable that ``azure.identity``
returns and token refresh becomes the credential's problem, forever.

The failure this module exists to prevent is the opposite pattern, which
appears in a lot of sample code::

    token = credential.get_token(SCOPE).token   # frozen at construction
    client = OpenAI(base_url=..., api_key=token)

That process authenticates perfectly for an hour and then serves 401s until
it is restarted. Nothing in this package ever materialises a token string.
See GOTCHAS.md, G4.

SYNC AND ASYNC ARE DIFFERENT CALLABLES
--------------------------------------
``OpenAI`` calls ``provider()`` and expects ``str``. ``AsyncOpenAI`` *awaits*
``provider()`` and expects a coroutine. A sync provider handed to the async
client fails on ``await "eyJ..."``. Hence two functions, and two credential
classes: ``azure.identity`` for one, ``azure.identity.aio`` for the other.
See GOTCHAS.md, G5.

DEPENDENCIES
------------
``azure-identity``, imported on first use so the rest of the package works
without it (an injected token provider or client needs no credential).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable

from modelaccess.config import ModelConfig
from modelaccess.errors import ConfigError

SyncTokenProvider = Callable[[], str]
AsyncTokenProvider = Callable[[], Awaitable[str]]


def _credential_kwargs(config: ModelConfig) -> dict[str, Any]:
    if config.managed_identity_client_id:
        # DefaultAzureCredential cannot choose between several user-assigned
        # identities on the same host; naming one is the only fix.
        return {"managed_identity_client_id": config.managed_identity_client_id}
    return {}


def default_credential(config: ModelConfig) -> Any:
    """Build the synchronous ``DefaultAzureCredential`` for this config.

    Managed identity in Azure, a developer sign-in locally — the same call in
    both places, with no environment branching in application code.
    """
    try:
        from azure.identity import DefaultAzureCredential
    except ImportError as exc:
        raise ConfigError(
            "azure-identity is not installed; pip install azure-identity"
        ) from exc
    return DefaultAzureCredential(**_credential_kwargs(config))


def default_async_credential(config: ModelConfig) -> Any:
    """Build the asynchronous ``DefaultAzureCredential`` for this config.

    Distinct from the sync one: it owns an async transport that must be
    closed, which is why the async client tracks credential ownership.
    """
    try:
        from azure.identity.aio import DefaultAzureCredential

        return DefaultAzureCredential(**_credential_kwargs(config))
    except ImportError as exc:
        raise ConfigError(
            "async identity dependencies are missing; install azure-identity and aiohttp"
        ) from exc


def bearer_token_provider(config: ModelConfig, credential: Any) -> SyncTokenProvider:
    """Return the per-request token callable for a sync credential.

    The returned callable is cached by the credential itself: the identity
    library reuses an unexpired token and only performs a network round trip
    near expiry, so calling it on every request is cheap.
    """
    try:
        from azure.identity import get_bearer_token_provider
    except ImportError as exc:
        raise ConfigError(
            "azure-identity is not installed; pip install azure-identity"
        ) from exc
    return get_bearer_token_provider(credential, config.credential_scope)


def async_bearer_token_provider(config: ModelConfig, credential: Any) -> AsyncTokenProvider:
    """Return the per-request token coroutine factory for an async credential."""
    try:
        from azure.identity.aio import get_bearer_token_provider
    except ImportError as exc:
        raise ConfigError(
            "azure-identity is not installed; pip install azure-identity"
        ) from exc
    return get_bearer_token_provider(credential, config.credential_scope)


__all__ = [
    "AsyncTokenProvider",
    "SyncTokenProvider",
    "async_bearer_token_provider",
    "bearer_token_provider",
    "default_async_credential",
    "default_credential",
]
