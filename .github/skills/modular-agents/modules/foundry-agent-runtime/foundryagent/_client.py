"""The Foundry client factory, and the per-agent client pool around it.

Module role:
    Turns a :class:`FoundryConfig` into a zero-arg callable that builds an Agent
    Framework client bound to the project endpoint, the model deployment and the
    process credential. Then pools those clients **one per agent id**.

Why a factory rather than a client:
    Because the pool needs to build more than one. Handing out a single shared
    client instance is the shape that causes GOTCHAS.md G2 — SDK clients carry
    per-agent state, and sharing one across a roster lets one agent's thread and
    tool set surface inside another's turn.

Why the pool lives here:
    It is the only correct way to consume the factory, so shipping the factory
    without it would be shipping the trap.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

from ._config import FoundryConfig
from ._credentials import get_credential
from ._optional import load_sdk

logger = logging.getLogger(__name__)


def foundry_agent_client(
    config: FoundryConfig,
    *,
    credential: Any | None = None,
) -> Callable[[], Any]:
    """Build a zero-arg factory producing Foundry-backed agent clients.

    Args:
        config: Endpoint, deployment and API version.
        credential: Explicit credential. ``None`` uses the process-wide cached
            one, built on first call — the same code path on a workstation
            (CLI login) and in cloud (workload identity), with no key material.

    Returns:
        ``() -> AzureAIAgentClient``. A **fresh** client per call, by design:
        the caller (normally :class:`ClientPool`) decides the sharing policy.

    Raises:
        SdkUnavailable: From the returned factory, not from here. Building the
            factory must stay free of SDK imports so a composition root can wire
            Foundry conditionally without installing it.
    """

    def _factory() -> Any:
        azure_bindings = load_sdk("agent_framework.azure")
        cred = credential if credential is not None else get_credential()

        kwargs: dict[str, Any] = {
            "project_endpoint": config.project_endpoint,
            "model_deployment_name": config.model_deployment,
            "credential": cred,
        }
        # Omitted rather than passed as None: some SDK versions treat an explicit
        # None as "use this version" and fail the request rather than defaulting.
        if config.api_version is not None:
            kwargs["api_version"] = config.api_version

        client = azure_bindings.AzureAIAgentClient(**kwargs)
        logger.info("foundry.client.built: %s", config.redacted())
        return client

    return _factory


class ClientPool:
    """One client per agent id, built on demand and cached for the process.

    The isolation unit is the agent, not the request: building a client per
    request adds a construction and an auth handshake to every turn, while
    sharing one across agents bleeds state between them. Per agent id is the
    only point that is both correct and affordable.

    Thread-safe. Agent construction happens concurrently at startup in most
    hosts, and two threads racing to build the first client for the same agent
    would otherwise produce two clients and cache the loser's.
    """

    def __init__(self, factory: Callable[[], Any]) -> None:
        """Args: factory: zero-arg client builder, normally from
        :func:`foundry_agent_client`."""
        self._factory = factory
        self._clients: dict[str, Any] = {}
        self._lock = threading.Lock()

    def client_for(self, agent_id: str) -> Any:
        """Return this agent's dedicated client, building it on first request."""
        existing = self._clients.get(agent_id)
        if existing is not None:
            return existing
        with self._lock:
            existing = self._clients.get(agent_id)
            if existing is not None:
                return existing
            client = self._factory()
            self._clients[agent_id] = client
            logger.info("foundry.client.pooled: agent_id=%s", agent_id)
            return client

    def agent_ids(self) -> list[str]:
        """Agent ids that currently hold a client. For diagnostics."""
        return sorted(self._clients)

    def clear(self) -> None:
        """Drop every cached client.

        Call after a config change that must take effect without a restart.
        Clients already handed to a running turn keep working — this only stops
        them being handed out again.
        """
        with self._lock:
            self._clients.clear()


__all__ = ["foundry_agent_client", "ClientPool"]
