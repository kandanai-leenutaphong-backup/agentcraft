"""Public deployment types and limits, without an operator's account inventory."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

ACCOUNT_NAME = ""
RESOURCE_GROUP = ""
SUBSCRIPTION_DISPLAY_NAME = ""
LOCATION = ""

LOCAL_AUTH_DISABLED = True

DEFAULT_ENDPOINT = ""

SECONDARY_ACCOUNT_NAME = ""
SECONDARY_ENDPOINT = ""

# Entra scope for data-plane calls against Azure AI Foundry / Azure OpenAI.
DEFAULT_SCOPE = "https://ai.azure.com/.default"

DEFAULT_DEPLOYMENT = "chat"


@dataclass(frozen=True)
class DeploymentProfile:
    """A caller-supplied deployment profile; empty coordinates identify no account."""

    name: str
    model: str
    model_version: str
    capacity: int
    kind: str  # "chat" or "embedding"
    account: str = ACCOUNT_NAME
    endpoint: str = DEFAULT_ENDPOINT


KNOWN_DEPLOYMENTS: Mapping[str, DeploymentProfile] = MappingProxyType({
    name: DeploymentProfile(name, name, "", 0, "embedding")
    for name in ("text-embedding-3-large", "text-embedding-3-small")
})

HIGHEST_CAPACITY_DEPLOYMENT = ""

# The embedding deployment used when a caller asks for embeddings without
# naming one. Never the chat default: a chat deployment cannot serve
# ``embeddings.create`` and would 404 in a way that reads like a typo.
DEFAULT_EMBEDDING_DEPLOYMENT = "text-embedding-3-large"

# Retained under its 1.0 name; the two are the same string by definition.
EMBEDDING_DEPLOYMENT = DEFAULT_EMBEDDING_DEPLOYMENT

EMBEDDING_DEPLOYMENTS: Mapping[str, DeploymentProfile] = MappingProxyType(
    {name: profile for name, profile in KNOWN_DEPLOYMENTS.items() if profile.kind == "embedding"}
)

# Published Azure OpenAI embedding limits, read 2026-08-31. Only the batch
# size is decidable locally: the token limits need a tokenizer, a character
# count does not prove one, and the service enforces them as a 400.
MAX_EMBEDDING_INPUTS = 2048
MAX_TOKENS_PER_INPUT = 8192
MAX_TOKENS_PER_REQUEST = 300_000


def known_deployment(name: str) -> DeploymentProfile | None:
    """Return the recorded profile for ``name``, or None if it is not known.

    An unknown name is not an error: deployments outlive this file.
    """
    return KNOWN_DEPLOYMENTS.get(name)


def embedding_deployment(name: str) -> DeploymentProfile | None:
    """Return the recorded embedding profile for ``name``, else None.

    Chat deployments are not returned even though they are in
    :data:`KNOWN_DEPLOYMENTS`: the question this answers is "which account do
    I send this embedding request to", and a chat deployment has no answer.
    """
    return EMBEDDING_DEPLOYMENTS.get(name)
