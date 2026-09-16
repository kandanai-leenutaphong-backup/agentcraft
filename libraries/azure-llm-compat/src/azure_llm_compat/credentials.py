"""Entra ID identity for Azure endpoints. One credential chain, one place.

No API key is accepted anywhere in this component. The chain resolves on every
call so a process can change identity without a reimport, and so importing the
package costs nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import COGNITIVE_SCOPE

_factory: Callable[[], Any] | None = None


def set_credential_factory(factory: Callable[[], Any] | None) -> Callable[[], Any] | None:
    """Install the factory used when no credential is injected; returns the previous one.

    This is the seam for tests and for a host that supplies its own credential.
    """
    global _factory
    previous = _factory
    _factory = factory
    return previous


def azure_credential() -> Any:
    """A credential that works on a developer machine and under managed identity."""
    if _factory is not None:
        return _factory()
    from azure.identity import AzureCliCredential, DefaultAzureCredential

    # AzureCliCredential avoids a slow IMDS probe locally. Hosted deployments fall
    # through to DefaultAzureCredential, so the same code moves to managed identity.
    if Path.home().joinpath(".azure").exists():
        return AzureCliCredential()
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def bearer_token_provider(scope: str = COGNITIVE_SCOPE, credential: Any | None = None) -> Callable[[], str]:
    """A zero-argument callable returning a fresh bearer token for ``scope``."""
    from azure.identity import get_bearer_token_provider

    return get_bearer_token_provider(credential or azure_credential(), scope)
