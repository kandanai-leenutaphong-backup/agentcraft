"""The recorded inventory: documentation that must stay true, not a gate."""

from __future__ import annotations

from azllm import (
    ACCOUNT_NAME,
    DEFAULT_DEPLOYMENT,
    DEFAULT_EMBEDDING_DEPLOYMENT,
    DEFAULT_SCOPE,
    EMBEDDING_DEPLOYMENT,
    EMBEDDING_DEPLOYMENTS,
    HIGHEST_CAPACITY_DEPLOYMENT,
    KNOWN_DEPLOYMENTS,
    MAX_EMBEDDING_INPUTS,
    MAX_TOKENS_PER_INPUT,
    MAX_TOKENS_PER_REQUEST,
    SECONDARY_ACCOUNT_NAME,
    FoundryConfig,
    embedding_deployment,
    known_deployment,
)
from azllm.deployments import LOCAL_AUTH_DISABLED, LOCATION, RESOURCE_GROUP


def test_portable_catalogue_contains_model_types_not_account_inventory() -> None:
    assert set(KNOWN_DEPLOYMENTS) == {
        "text-embedding-3-large",
        "text-embedding-3-small",
    }
    for profile in KNOWN_DEPLOYMENTS.values():
        assert profile.capacity == 0
        assert profile.endpoint == ""
        assert profile.account == ""


def test_account_facts() -> None:
    assert ACCOUNT_NAME == ""
    assert RESOURCE_GROUP == ""
    assert LOCATION == ""
    assert LOCAL_AUTH_DISABLED is True
    assert DEFAULT_SCOPE == "https://ai.azure.com/.default"


def test_portable_names_make_no_capacity_claim() -> None:
    assert DEFAULT_DEPLOYMENT == "chat"
    assert HIGHEST_CAPACITY_DEPLOYMENT == ""
    assert EMBEDDING_DEPLOYMENT in KNOWN_DEPLOYMENTS


def test_the_inventory_is_immutable() -> None:
    try:
        KNOWN_DEPLOYMENTS["new"] = KNOWN_DEPLOYMENTS[DEFAULT_EMBEDDING_DEPLOYMENT]  # type: ignore[index]
    except TypeError:
        return
    raise AssertionError("KNOWN_DEPLOYMENTS must not be mutable")


def test_an_unknown_deployment_is_not_an_error_anywhere() -> None:
    assert known_deployment("gpt-7-preview") is None
    assert FoundryConfig(endpoint="https://example.invalid", deployment="gpt-7-preview").deployment == "gpt-7-preview"


def test_embedding_deployments_record_their_owning_account() -> None:
    assert set(EMBEDDING_DEPLOYMENTS) == {"text-embedding-3-large", "text-embedding-3-small"}

    large = EMBEDDING_DEPLOYMENTS["text-embedding-3-large"]
    assert (large.account, large.capacity) == (ACCOUNT_NAME, 0)
    assert large.endpoint == ""

    small = EMBEDDING_DEPLOYMENTS["text-embedding-3-small"]
    assert (small.account, small.capacity) == (SECONDARY_ACCOUNT_NAME, 0)
    assert small.endpoint == ""

    for profile in EMBEDDING_DEPLOYMENTS.values():
        assert profile.kind == "embedding"
        assert profile.model_version == ""


def test_embedding_deployment_lookup_excludes_chat() -> None:
    assert embedding_deployment("text-embedding-3-small") is not None
    assert embedding_deployment(DEFAULT_DEPLOYMENT) is None
    assert embedding_deployment("nope") is None


def test_embedding_defaults_and_limits() -> None:
    assert DEFAULT_EMBEDDING_DEPLOYMENT == "text-embedding-3-large"
    assert EMBEDDING_DEPLOYMENT == DEFAULT_EMBEDDING_DEPLOYMENT
    assert DEFAULT_EMBEDDING_DEPLOYMENT != DEFAULT_DEPLOYMENT
    assert (MAX_EMBEDDING_INPUTS, MAX_TOKENS_PER_INPUT, MAX_TOKENS_PER_REQUEST) == (
        2048,
        8192,
        300_000,
    )
