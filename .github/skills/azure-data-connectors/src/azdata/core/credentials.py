"""Credential resolution — one identity, three tiers, cached for the process.

WHY THIS EXISTS
---------------
Connection strings, account keys and SAS tokens are the default in most
Azure sample code and the wrong answer in all of it: they land in config
files, they cannot be scoped, and rotating one is a redeploy. Every
connector in this box authenticates with a ``TokenCredential`` and RBAC
instead, so rotation is a non-event and the permission surface is what the
role assignment says it is.

Three tiers, in order:

1. **Explicit service principal** — only when the caller supplies a
   complete ``(tenant_id, client_id, client_secret)`` triple. This exists
   for genuine cross-tenant access, where managed identity cannot reach.
2. **Managed identity** — whenever the process is running inside Azure.
3. **``az login``** — local development.

Tiers 2 and 3 are the same code path in the application: identical calls,
identical scopes, no environment branching in business logic.

The result is cached at module scope keyed by tenant, because token
acquisition is a network round trip and the credential object refreshes
itself. Never close it: it is a process-lifetime singleton, and a connector
that closes it breaks every other connector in the process (GOTCHAS.md G8).

DOMAIN-BLIND BY CONSTRUCTION
----------------------------
This module never learns which service a credential is for. Callers pass
the triple; nothing here reads a named environment variable.

DEPENDENCIES
------------
Standard library, plus ``azure-identity`` loaded on first call.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from azdata.core.optional import load

logger = logging.getLogger(__name__)

# Set on App Service, Functions, Container Apps and AKS. Presence of any one
# of them means an ambient managed identity should exist.
_AZURE_MARKERS = (
    "WEBSITE_INSTANCE_ID",
    "CONTAINER_APP_NAME",
    "FUNCTIONS_WORKER_RUNTIME",
    "KUBERNETES_SERVICE_HOST",
    "MSI_ENDPOINT",
    "IDENTITY_ENDPOINT",
)

_cached: Any = None
_cached_key: str = "\x00unset"


def running_in_azure(env: dict[str, str] | None = None) -> bool:
    """True when the process appears to be running on Azure compute."""
    src = os.environ if env is None else env
    return any(src.get(marker) for marker in _AZURE_MARKERS)


def default_credential_provider(
    *,
    service_principal: tuple[str, str, str] | None = None,
) -> Any:
    """Return the best available ``TokenCredential`` for this environment.

    Args:
        service_principal: Complete ``(tenant, client_id, secret)`` triple
            for cross-tenant access, or None to use the ambient identity.

    Returns:
        A ``TokenCredential``. Cached per service-principal tenant, so a
        caller that asked for the ambient identity can never be handed a
        service-principal credential from an earlier call, or vice versa.
    """
    global _cached, _cached_key

    key = f"sp={service_principal[0]}" if service_principal else "default"
    if _cached is not None and _cached_key == key:
        return _cached

    identity = load("azure.identity", dist="azure-identity")

    credential = None
    if service_principal:
        tenant_id, client_id, client_secret = service_principal
        if tenant_id and client_id and client_secret:
            logger.debug("azdata.credential: client secret (explicit SP)")
            credential = identity.ClientSecretCredential(
                tenant_id, client_id, client_secret
            )

    if credential is None:
        if running_in_azure():
            logger.info("azdata.credential: managed identity")
            credential = identity.DefaultAzureCredential()
        else:
            logger.info("azdata.credential: azure cli (local dev)")
            credential = identity.AzureCliCredential()

    _cached = credential
    _cached_key = key
    return credential


def reset_credential_cache() -> None:
    """Drop the cached credential. Tests and credential rotation drills only."""
    global _cached, _cached_key
    _cached = None
    _cached_key = "\x00unset"


def credential_provider_for(config: Any) -> Callable[[], Any]:
    """Bind a config's service-principal triple into a zero-arg provider.

    Connectors take ``Callable[[], TokenCredential]`` so they never read
    config themselves; this adapts a config object to that shape.
    """

    def _provider() -> Any:
        return default_credential_provider(
            service_principal=config.service_principal
        )

    return _provider


__all__ = [
    "credential_provider_for",
    "default_credential_provider",
    "reset_credential_cache",
    "running_in_azure",
]
