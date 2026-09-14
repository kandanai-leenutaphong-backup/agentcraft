"""Config normalisation, rejection and environment reading."""

from __future__ import annotations

import pytest

from azllm import DEFAULT_DEPLOYMENT, DEFAULT_ENDPOINT, DEFAULT_SCOPE, ConfigError, FoundryConfig
from azllm.config import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT_SECS, normalize_endpoint

NORMALIZED = "https://acct.openai.azure.com/openai/v1/"


@pytest.mark.parametrize(
    "raw",
    [
        "acct.openai.azure.com",
        "https://acct.openai.azure.com",
        "https://acct.openai.azure.com/",
        "https://acct.openai.azure.com/openai",
        "https://acct.openai.azure.com/openai/",
        "https://acct.openai.azure.com/openai/v1",
        "https://acct.openai.azure.com/openai/v1/",
        "  https://ACCT.openai.azure.com/openai/v1  ",
    ],
)
def test_every_plausible_endpoint_shape_normalizes_to_one_base_url(raw: str) -> None:
    assert normalize_endpoint(raw) == NORMALIZED


def test_normalization_is_idempotent() -> None:
    once = normalize_endpoint("acct.openai.azure.com")
    assert normalize_endpoint(once) == once


def test_normalized_base_url_keeps_trailing_slash() -> None:
    # httpx resolves relative request paths against the base URL; without the
    # trailing slash the final segment is dropped and every call 404s.
    assert FoundryConfig(endpoint="acct.openai.azure.com").base_url.endswith("/openai/v1/")


def test_path_prefix_is_preserved() -> None:
    assert (
        normalize_endpoint("https://host.services.ai.azure.com/api/projects/p1")
        == "https://host.services.ai.azure.com/api/projects/p1/openai/v1/"
    )


@pytest.mark.parametrize(
    "raw, expected_fragment",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("http://acct.openai.azure.com", "https"),
        ("ftp://acct.openai.azure.com", "https"),
        ("https://user:pw@acct.openai.azure.com", "credentials"),
        ("https://acct.openai.azure.com/?api-key=abc", "query"),
        ("https://acct.openai.azure.com/#frag", "query"),
        ("https://acct.openai.azure.com/openai/../v1", ".."),
        ("https://acct .openai.azure.com", "whitespace"),
        ("https:///openai/v1", "host"),
    ],
)
def test_unsafe_endpoints_are_rejected(raw: str, expected_fragment: str) -> None:
    with pytest.raises(ConfigError) as caught:
        normalize_endpoint(raw)
    assert expected_fragment in str(caught.value)


@pytest.mark.parametrize("name", ["", "   ", "bad name", "bad/name", "a" * 65, "drop;table"])
def test_invalid_deployment_names_are_rejected(name: str) -> None:
    with pytest.raises(ConfigError):
        FoundryConfig(endpoint=NORMALIZED, deployment=name)


def test_unknown_deployment_name_is_allowed() -> None:
    # The inventory is documentation. Deployments outlive this package.
    assert FoundryConfig(endpoint=NORMALIZED, deployment="gpt-9-unreleased").deployment


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), "30", True])
def test_invalid_timeouts_are_rejected(timeout: object) -> None:
    with pytest.raises(ConfigError):
        FoundryConfig(endpoint=NORMALIZED, timeout_secs=timeout)  # type: ignore[arg-type]


@pytest.mark.parametrize("retries", [-1, 11, 2.5, "2", True])
def test_invalid_retry_counts_are_rejected(retries: object) -> None:
    with pytest.raises(ConfigError):
        FoundryConfig(endpoint=NORMALIZED, max_retries=retries)  # type: ignore[arg-type]


@pytest.mark.parametrize("scope", ["", "ai.azure.com/.default", "https://ai.azure.com", "user_impersonation"])
def test_invalid_scopes_are_rejected(scope: str) -> None:
    with pytest.raises(ConfigError):
        FoundryConfig(endpoint=NORMALIZED, credential_scope=scope)


def test_blank_managed_identity_client_id_is_rejected() -> None:
    with pytest.raises(ConfigError):
        FoundryConfig(endpoint=NORMALIZED, managed_identity_client_id="  ")


@pytest.mark.parametrize("cap", [0, -5, 1.5])
def test_invalid_output_cap_is_rejected(cap: object) -> None:
    with pytest.raises(ConfigError):
        FoundryConfig(endpoint=NORMALIZED, default_max_output_tokens=cap)  # type: ignore[arg-type]


def test_config_is_frozen() -> None:
    cfg = FoundryConfig(endpoint=NORMALIZED)
    with pytest.raises(Exception):
        cfg.deployment = "other"  # type: ignore[misc]


def test_with_overrides_revalidates_and_rejects_unknown_fields() -> None:
    cfg = FoundryConfig(endpoint=NORMALIZED)
    assert cfg.with_overrides(deployment="chat-batch").deployment == "chat-batch"
    with pytest.raises(ConfigError):
        cfg.with_overrides(timeout_secs=0)
    with pytest.raises(ConfigError):
        cfg.with_overrides(api_key="nope")


def test_defaults_carry_no_account() -> None:
    with pytest.raises(ConfigError, match="endpoint is empty"):
        FoundryConfig()
    cfg = FoundryConfig(endpoint=NORMALIZED)
    assert cfg.base_url == NORMALIZED
    assert cfg.deployment == DEFAULT_DEPLOYMENT == "chat"
    assert cfg.credential_scope == DEFAULT_SCOPE == "https://ai.azure.com/.default"
    assert cfg.timeout_secs == DEFAULT_TIMEOUT_SECS
    assert cfg.max_retries == DEFAULT_MAX_RETRIES
    assert DEFAULT_ENDPOINT == ""


def test_no_api_key_field_exists() -> None:
    assert not any("key" in field for field in FoundryConfig.__dataclass_fields__)


def test_account_host_is_loggable_and_carries_no_path() -> None:
    assert FoundryConfig(endpoint=NORMALIZED).account_host == "acct.openai.azure.com"


def test_from_env_reads_every_field() -> None:
    env = {
        "AZURE_LLM_ENDPOINT": "other.openai.azure.com",
        "AZURE_LLM_DEPLOYMENT": "chat-alternate",
        "AZURE_LLM_SCOPE": "https://cognitiveservices.azure.com/.default",
        "AZURE_LLM_TIMEOUT_SECONDS": "12.5",
        "AZURE_LLM_MAX_RETRIES": "0",
        "AZURE_LLM_CLIENT_ID": "11111111-2222-3333-4444-555555555555",
        "AZURE_LLM_MAX_OUTPUT_TOKENS": "256",
    }
    cfg = FoundryConfig.from_env(env=env)
    assert cfg.base_url == "https://other.openai.azure.com/openai/v1/"
    assert cfg.deployment == "chat-alternate"
    assert cfg.credential_scope == "https://cognitiveservices.azure.com/.default"
    assert cfg.timeout_secs == 12.5
    assert cfg.max_retries == 0
    assert cfg.managed_identity_client_id == "11111111-2222-3333-4444-555555555555"
    assert cfg.default_max_output_tokens == 256


def test_from_env_with_empty_environment_refuses_to_guess_an_account() -> None:
    with pytest.raises(ConfigError, match="endpoint is empty"):
        FoundryConfig.from_env(env={})


def test_from_env_ignores_blank_values() -> None:
    cfg = FoundryConfig.from_env(env={"AZURE_LLM_ENDPOINT": NORMALIZED, "AZURE_LLM_DEPLOYMENT": "   "})
    assert cfg.deployment == DEFAULT_DEPLOYMENT


def test_from_env_honours_a_custom_prefix() -> None:
    cfg = FoundryConfig.from_env(prefix="MYAPP_", env={"MYAPP_ENDPOINT": NORMALIZED, "MYAPP_DEPLOYMENT": "chat-batch"})
    assert cfg.deployment == "chat-batch"


@pytest.mark.parametrize(
    "env",
    [
        {"AZURE_LLM_API_KEY": "sk-secret"},
        {"AZURE_LLM_KEY": "sk-secret"},
        {"AZURE_OPENAI_API_KEY": "sk-secret"},
        {"OPENAI_API_KEY": "sk-secret"},
    ],
)
def test_from_env_refuses_key_auth_environment(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError) as caught:
        FoundryConfig.from_env(env=env)
    assert "key" in str(caught.value).lower()
    # The refusal names the variable, never its value.
    assert "sk-secret" not in str(caught.value)


@pytest.mark.parametrize(
    "env", [{"AZURE_LLM_MAX_RETRIES": "many"}, {"AZURE_LLM_TIMEOUT_SECONDS": "soon"}]
)
def test_from_env_rejects_unparseable_numbers(env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        FoundryConfig.from_env(env=env)
