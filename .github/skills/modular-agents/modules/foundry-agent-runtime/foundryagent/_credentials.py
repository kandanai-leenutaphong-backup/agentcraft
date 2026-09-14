"""One credential for the process — the same code path locally and in cloud.

Module role:
    Builds at most one ``DefaultAzureCredential`` and hands the same instance to
    every client. Nothing else in the box constructs a credential.

Why one:
    A credential is a token cache. Building a second one throws away the first
    one's cached tokens and doubles the traffic to the identity endpoint, which
    is itself rate-limited. Under a burst of agent builds that shows up as
    intermittent auth latency nobody can attribute — see GOTCHAS.md G3.

Why DefaultAzureCredential specifically:
    It resolves to a developer's CLI login on a workstation and to the workload
    identity in cloud, with no branch in the code and no key material anywhere.
    Rotation becomes a non-event: there is nothing to rotate.
"""

from __future__ import annotations

import logging
import threading
from typing import Any

from ._optional import load_sdk

logger = logging.getLogger(__name__)

# Cached credential and the lock guarding its creation. Module-level because the
# cache must be process-wide: a per-instance cache is not a cache.
_credential: Any | None = None
_lock = threading.Lock()


def get_credential(factory: Any | None = None) -> Any:
    """Return the process-wide credential, building it on first use.

    Args:
        factory: Zero-arg callable returning a credential. Injected by tests and
            by consumers who need a specific credential type (a user-assigned
            managed identity, say). Ignored once a credential is cached.

    Returns:
        A ``TokenCredential``. The same object on every call.
    """
    global _credential
    if _credential is not None:
        return _credential
    with _lock:
        # Re-check inside the lock: two threads can both pass the check above.
        if _credential is not None:
            return _credential
        if factory is not None:
            _credential = factory()
        else:
            identity = load_sdk("azure.identity")
            _credential = identity.DefaultAzureCredential()
        logger.info(
            "foundry.credential.created: type=%s", type(_credential).__name__
        )
        return _credential


def set_credential(credential: Any) -> None:
    """Install an explicit credential, replacing any cached one.

    The supported way to use a non-default credential: call this once from the
    composition root, before the first agent is built.
    """
    global _credential
    with _lock:
        _credential = credential


def reset_credential() -> None:
    """Drop the cached credential. For tests, and for a deliberate re-auth."""
    global _credential
    with _lock:
        _credential = None


def has_credential() -> bool:
    """True when a credential is already cached. Never builds one."""
    return _credential is not None


__all__ = ["get_credential", "set_credential", "reset_credential", "has_credential"]
