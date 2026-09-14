"""The published surface itself: exports, version, and method parity.

A missing name in ``__all__`` or a method that exists on one connector and
not the other is not caught by any behavioural test — both classes are
exercised separately, so both can drift separately.
"""

from __future__ import annotations

import inspect

import azllm


def test_version_is_the_minor_bump() -> None:
    assert azllm.__version__ == "1.1.0"


def test_every_exported_name_exists_and_is_sorted() -> None:
    assert azllm.__all__ == sorted(azllm.__all__)
    assert len(set(azllm.__all__)) == len(azllm.__all__)
    for name in azllm.__all__:
        assert hasattr(azllm, name), name


def test_the_embedding_surface_is_exported() -> None:
    for name in (
        "EmbeddingResult",
        "EMBEDDING_DEPLOYMENTS",
        "DEFAULT_EMBEDDING_DEPLOYMENT",
        "MAX_EMBEDDING_INPUTS",
        "embedding_config",
        "embedding_deployment",
    ):
        assert name in azllm.__all__, name


def test_the_1_0_surface_is_unchanged() -> None:
    for name in (
        "ACCOUNT_NAME",
        "AsyncFoundryConnector",
        "ConfigError",
        "DEFAULT_DEPLOYMENT",
        "DEFAULT_ENDPOINT",
        "DEFAULT_MAX_RETRIES",
        "DEFAULT_SCOPE",
        "DEFAULT_TIMEOUT_SECS",
        "DeploymentProfile",
        "EMBEDDING_DEPLOYMENT",
        "ENV_PREFIX",
        "ErrorCategory",
        "FoundryConfig",
        "FoundryConnector",
        "HIGHEST_CAPACITY_DEPLOYMENT",
        "KNOWN_DEPLOYMENTS",
        "LlmError",
        "LlmResult",
        "ParsedResult",
        "async_token_provider_for",
        "connect",
        "connect_async",
        "known_deployment",
        "normalize_endpoint",
        "token_provider_for",
    ):
        assert name in azllm.__all__, name


def test_both_connectors_expose_the_same_methods() -> None:
    sync_names = {n for n in dir(azllm.FoundryConnector) if not n.startswith("_")}
    async_names = {n for n in dir(azllm.AsyncFoundryConnector) if not n.startswith("_")}

    assert sync_names - {"close"} == async_names - {"aclose"}
    assert {"embed", "embed_raw"} <= sync_names


def test_embed_signatures_match_across_sync_and_async() -> None:
    sync = inspect.signature(azllm.FoundryConnector.embed)
    asyn = inspect.signature(azllm.AsyncFoundryConnector.embed)

    assert list(sync.parameters) == list(asyn.parameters)
    assert sync.parameters["input"].kind is inspect.Parameter.POSITIONAL_ONLY
    assert sync.parameters["deployment"].default is None
    assert sync.parameters["dimensions"].default is None
