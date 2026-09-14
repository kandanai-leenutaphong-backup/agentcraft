"""Routing an embedding call to the account that owns the deployment.

WHY THIS EXISTS
---------------
A deployment is reachable only through the endpoint of the account that
hosts it. Different embedding deployments may belong to different accounts.
The portable catalogue records model types but no account coordinates, so
``endpoint=`` is required. The helper preserves the caller's other settings
without guessing which account owns a deployment.

WHY IT IS A SEPARATE MODULE
---------------------------
:mod:`azllm.deployments` is deliberately dependency-free and is imported by
:mod:`azllm.config`. Putting a function that *returns* a ``FoundryConfig``
there would make that a cycle. Here, the direction is one-way:
``deployments`` -> ``config`` -> ``embeddings``.

DEPENDENCIES
------------
Standard library only.
"""

from __future__ import annotations

from azllm.config import FoundryConfig
from azllm.deployments import (
    DEFAULT_EMBEDDING_DEPLOYMENT,
    EMBEDDING_DEPLOYMENTS,
    embedding_deployment,
)
from azllm.errors import ConfigError


def embedding_config(
    deployment: str = DEFAULT_EMBEDDING_DEPLOYMENT,
    *,
    endpoint: str | None = None,
    base: FoundryConfig | None = None,
    **overrides: object,
) -> FoundryConfig:
    """Return a :class:`FoundryConfig` pointed at ``deployment``'s own account.

        from azllm import connect, embedding_config

        with connect(embedding_config("text-embedding-3-small", endpoint=account_endpoint)) as llm:
            result = llm.embed("hello")

    Args:
        deployment: An embedding deployment name. Defaults to
            :data:`~azllm.deployments.DEFAULT_EMBEDDING_DEPLOYMENT`.
        endpoint: Required in the portable package, whose profiles contain
            no private account endpoints.
        base: A config to start from, so timeouts, retries and a managed
            identity client id survive. Its endpoint and deployment are
            replaced.
        **overrides: Any other :class:`FoundryConfig` field.

    Raises:
        ConfigError: when ``deployment`` is unknown and no ``endpoint`` is
            given. Guessing the account is how a 404 gets misread as a typo.
    """
    profile = embedding_deployment(deployment)
    if profile is None and endpoint is None:
        known = ", ".join(sorted(EMBEDDING_DEPLOYMENTS))
        raise ConfigError(
            f"{deployment!r} is not a known embedding deployment (known: {known}); "
            "pass endpoint= with the account that hosts it — a deployment is only "
            "reachable through its own account's endpoint"
        )

    target = endpoint if endpoint is not None else profile.endpoint  # type: ignore[union-attr]
    start = base if base is not None else FoundryConfig(endpoint=target, deployment=deployment)
    return start.with_overrides(endpoint=target, deployment=deployment, **overrides)
