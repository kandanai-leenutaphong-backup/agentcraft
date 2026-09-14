"""The two entry points: ``connect`` and ``connect_async``.

WHY THIS EXISTS
---------------
Everything a caller needs to decide — which account, which deployment, which
identity — is decided here, once, at the composition root. Application code
downstream receives a client and never reads an environment variable or
builds a credential again.

Both functions accept a ``client``, a ``token_provider`` and a
``credential``. That is not generality for its own sake: it is what lets the
whole test suite run with no network, no cloud sign-in and no cloud mutation,
using the same code paths production uses.

DEPENDENCIES
------------
Standard library; the identity and SDK imports happen further down, and only
when nothing was injected.
"""

from __future__ import annotations

from typing import Any

from modelaccess import auth
from modelaccess.aio import AsyncModelClient
from modelaccess.client import ModelClient
from modelaccess.config import ModelConfig


def connect(
    config: ModelConfig | None = None,
    *,
    credential: Any | None = None,
    token_provider: Any | None = None,
    client: Any | None = None,
    owns_client: bool | None = None,
) -> ModelClient:
    """Build a reusable synchronous client.

    Args:
        config: Coordinates. Defaults to :meth:`ModelConfig.from_env`, which
            refuses with an actionable message when the endpoint or the
            deployment is unset.
        credential: A synchronous ``TokenCredential``. Defaults to
            ``DefaultAzureCredential``. A credential passed in is *not* closed
            by :meth:`ModelClient.close` — the caller still owns it.
        token_provider: A zero-argument callable returning a bearer token,
            used instead of deriving one from a credential.
        client: A pre-built ``OpenAI``-shaped object. Bypasses credential and
            client construction entirely; this is the test seam, and also the
            seam for sharing one HTTP client across several connectors.
        owns_client: Whether ``close()`` closes ``client``. Defaults to True
            only for a client built here, so a shared injected client is not
            closed out from under its other users. Pass True to hand this
            object the lifecycle deliberately.

    Returns:
        A :class:`~modelaccess.client.ModelClient`. Build one per process and
        share it.
    """
    resolved = config or ModelConfig.from_env()
    return ModelClient(
        resolved,
        client=client,
        token_provider=token_provider,
        credential=credential,
        owns_credential=False,
        owns_client=owns_client,
    )


def connect_async(
    config: ModelConfig | None = None,
    *,
    credential: Any | None = None,
    token_provider: Any | None = None,
    client: Any | None = None,
    owns_client: bool | None = None,
) -> AsyncModelClient:
    """Build a reusable asyncio client.

    ``credential`` must be an asyncio credential and ``token_provider`` must
    be a coroutine factory: ``AsyncOpenAI`` awaits the provider on every
    request.

    ``owns_client`` follows the same rule as :func:`connect`: an injected
    client is left open unless ownership is transferred explicitly.

    The returned object must be closed with ``await client.aclose()`` or used
    as an ``async with`` block.
    """
    resolved = config or ModelConfig.from_env()
    return AsyncModelClient(
        resolved,
        client=client,
        token_provider=token_provider,
        credential=credential,
        owns_credential=False,
        owns_client=owns_client,
    )


def token_provider_for(config: ModelConfig) -> Any:
    """The sync per-request token callable for ``config``, for direct SDK use.

    Exposed for callers who want to build their own ``OpenAI`` client and
    still get the identity handling right. The credential it builds is owned
    by the returned closure, not by this package.
    """
    return auth.bearer_token_provider(config, auth.default_credential(config))


def async_token_provider_for(config: ModelConfig) -> Any:
    """The async per-request token coroutine factory for ``config``."""
    return auth.async_bearer_token_provider(config, auth.default_async_credential(config))


__all__ = ["async_token_provider_for", "connect", "connect_async", "token_provider_for"]
