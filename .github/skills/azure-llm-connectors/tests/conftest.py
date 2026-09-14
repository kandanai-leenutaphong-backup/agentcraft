"""Shared fixtures. The whole suite is offline: no credential, no socket."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from azllm import FoundryConfig, connect, connect_async  # noqa: E402
from fakes import FakeAsyncClient, FakeClient  # noqa: E402

# Not the real account: a test that can only pass against one tenant is not a
# test. The real defaults are asserted separately, in test_config.
TEST_ENDPOINT = "https://acct.openai.azure.com/"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """No ambient Azure or OpenAI environment may reach a test."""
    for key in list(os.environ):
        if key.startswith("AZURE_LLM_") or key in {"OPENAI_API_KEY", "AZURE_OPENAI_API_KEY"}:
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def config() -> FoundryConfig:
    return FoundryConfig(endpoint=TEST_ENDPOINT, deployment="chat")


@pytest.fixture
def fake_client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def fake_async_client() -> FakeAsyncClient:
    return FakeAsyncClient()


@pytest.fixture
def connector(config: FoundryConfig, fake_client: FakeClient):
    conn = connect(config, client=fake_client)
    yield conn
    conn.close()


@pytest.fixture
async def async_connector(config: FoundryConfig, fake_async_client: FakeAsyncClient):
    conn = connect_async(config, client=fake_async_client)
    yield conn
    await conn.aclose()
