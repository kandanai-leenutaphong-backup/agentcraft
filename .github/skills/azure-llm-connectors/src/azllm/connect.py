"""The two entry points: ``connect`` and ``connect_async``.

WHY THIS EXISTS
---------------
Everything a caller needs to decide — which account, which deployment, which
identity — is decided here, once, at the composition root. Application code
downstream receives a connector and never reads an environment variable or
builds a credential again.

Both functions accept a ``client``, a ``token_provider`` and a
``credential``. That is not generality for its own sake: it is what lets the
whole test suite run with no network, no Azure login and no cloud mutation,
using the same code paths production uses.
"""

from __future__ import annotations

from typing import Any

from azllm import auth
from azllm.aio import AsyncFoundryConnector
from azllm.config import FoundryConfig
from azllm.connector import FoundryConnector


def connect(
    config: FoundryConfig | None = None,
    *,
    credential: Any | None = None,
    token_provider: Any | None = None,
    client: Any | None = None,
) -> FoundryConnector:
    """Build a reusable synchronous connector.

    Args:
        config: Coordinates. Defaults to :meth:`FoundryConfig.from_env`,
            which itself falls back to the verified account defaults.
        credential: A synchronous ``TokenCredential``. Defaults to
            ``DefaultAzureCredential``. A credential passed in is *not*
            closed by :meth:`FoundryConnector.close` — the caller still owns it.
        token_provider: A zero-argument callable returning a bearer token,
            used instead of deriving one from a credential.
        client: A pre-built ``OpenAI``-shaped object. Bypasses credential and
            client construction entirely; this is the test seam.

    Returns:
        A :class:`FoundryConnector`. Build one per process and share it.
    """
    resolved = config or FoundryConfig.from_env()
    return FoundryConnector(
        resolved,
        client=client,
        token_provider=token_provider,
        credential=credential,
        owns_credential=False,
    )


def connect_async(
    config: FoundryConfig | None = None,
    *,
    credential: Any | None = None,
    token_provider: Any | None = None,
    client: Any | None = None,
) -> AsyncFoundryConnector:
    """Build a reusable asyncio connector.

    ``credential`` must be an ``azure.identity.aio`` credential and
    ``token_provider`` must be a coroutine factory: ``AsyncOpenAI`` awaits
    the provider on every request.

    The returned object must be closed with ``await conn.aclose()`` or used
    as an ``async with`` block.
    """
    resolved = config or FoundryConfig.from_env()
    return AsyncFoundryConnector(
        resolved,
        client=client,
        token_provider=token_provider,
        credential=credential,
        owns_credential=False,
    )


def token_provider_for(config: FoundryConfig) -> Any:
    """The sync per-request token callable for ``config``, for direct SDK use.

    Exposed for callers who want to build their own ``OpenAI`` client and
    still get the identity handling right.
    """
    return auth.bearer_token_provider(config, auth.default_credential(config))


def async_token_provider_for(config: FoundryConfig) -> Any:
    """The async per-request token coroutine factory for ``config``."""
    return auth.async_bearer_token_provider(config, auth.default_async_credential(config))
