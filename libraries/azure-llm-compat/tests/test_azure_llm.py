"""Azure LLM connector: configuration resolves at call time, auth carries no key."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest import mock

from azure_llm_compat import AzureLlmClient, LlmConfig, LlmConfigError
from azure_llm_compat.config import COGNITIVE_SCOPE


class FakeResponses:
    def __init__(self, output_text: str = "ok") -> None:
        self.calls: list[dict] = []
        self.output_text = output_text

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=self.output_text)


class FakeEmbeddings:
    def __init__(self, vectors: list[list[float]]) -> None:
        self.calls: list[dict] = []
        self.vectors = vectors

    def create(self, **kwargs):
        self.calls.append(kwargs)
        # Deliberately out of order: the service orders by an explicit index field.
        data = [SimpleNamespace(index=i, embedding=v) for i, v in enumerate(self.vectors)]
        return SimpleNamespace(data=list(reversed(data)))


class FakeOpenAI:
    def __init__(self, output_text: str = "ok", vectors: list[list[float]] | None = None) -> None:
        self.responses = FakeResponses(output_text)
        self.embeddings = FakeEmbeddings(vectors or [])


class ConfigTests(unittest.TestCase):
    def test_endpoint_must_be_https(self):
        with self.assertRaises(LlmConfigError):
            LlmConfig(endpoint="http://example.invalid/openai/v1/")

    def test_from_env_reads_at_call_time_not_import_time(self):
        with mock.patch.dict(os.environ, {"AZURE_LLM_ENDPOINT": "https://a.invalid/openai/v1/"}, clear=False):
            first = LlmConfig.from_env()
        with mock.patch.dict(os.environ, {"AZURE_LLM_ENDPOINT": "https://b.invalid/openai/v1/"}, clear=False):
            second = LlmConfig.from_env()
        self.assertEqual(first.endpoint, "https://a.invalid/openai/v1/")
        self.assertEqual(second.endpoint, "https://b.invalid/openai/v1/")

    def test_from_env_requires_endpoint(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(LlmConfigError):
                LlmConfig.from_env()

    def test_from_env_honours_prefix_and_overrides(self):
        env = {"OTHER_ENDPOINT": "https://c.invalid/openai/v1/", "OTHER_MAX_RETRIES": "5"}
        with mock.patch.dict(os.environ, env, clear=True):
            config = LlmConfig.from_env("OTHER_", model="gpt-x")
        self.assertEqual(config.model, "gpt-x")
        self.assertEqual(config.max_retries, 5)

    def test_default_scope_is_cognitive_services(self):
        self.assertEqual(LlmConfig(endpoint="https://a.invalid/").scope, COGNITIVE_SCOPE)

    def test_embeddings_fall_back_to_the_main_endpoint(self):
        config = LlmConfig(endpoint="https://a.invalid/openai/v1/")
        self.assertEqual(config.embeddings_base_url, config.endpoint)


class ClientTests(unittest.TestCase):
    def client(self, **kwargs) -> tuple[AzureLlmClient, FakeOpenAI]:
        fake = FakeOpenAI(**kwargs)
        config = LlmConfig(
            endpoint="https://a.invalid/openai/v1/",
            model="gpt-test",
            embedding_deployment="text-embedding-3-small",
        )
        return AzureLlmClient(config, client=fake), fake

    def test_construction_makes_no_request_and_needs_no_credential(self):
        client, fake = self.client()
        self.assertEqual(fake.responses.calls, [])
        self.assertEqual(client.describe()["auth"], "entra-id-bearer-token")

    def test_describe_exposes_no_secret(self):
        client, _ = self.client()
        self.assertNotIn("api_key", client.describe())
        self.assertNotIn("key", " ".join(client.describe()))

    def test_respond_builds_a_minimal_request(self):
        client, fake = self.client()
        client.respond(input="hello")
        self.assertEqual(fake.responses.calls[0], {"model": "gpt-test", "input": "hello"})

    def test_respond_includes_only_the_options_given(self):
        client, fake = self.client()
        client.respond(input="hi", instructions="be brief", max_output_tokens=64, reasoning_effort="low")
        call = fake.responses.calls[0]
        self.assertEqual(call["instructions"], "be brief")
        self.assertEqual(call["max_output_tokens"], 64)
        self.assertEqual(call["reasoning"], {"effort": "low"})

    def test_respond_text_strips(self):
        client, _ = self.client(output_text="  spaced  ")
        self.assertEqual(client.respond_text(input="x"), "spaced")

    def test_explicit_model_overrides_the_default(self):
        client, fake = self.client()
        client.respond(input="x", model="other")
        self.assertEqual(fake.responses.calls[0]["model"], "other")

    def test_missing_model_is_named(self):
        client = AzureLlmClient(LlmConfig(endpoint="https://a.invalid/"), client=FakeOpenAI())
        with self.assertRaises(LlmConfigError):
            client.respond(input="x")

    def test_stream_sets_the_stream_flag(self):
        client, fake = self.client()
        client.stream(input="x")
        self.assertTrue(fake.responses.calls[0]["stream"])

    def test_embed_returns_vectors_in_the_order_sent(self):
        client, _ = self.client(vectors=[[1.0, 0.0], [0.0, 1.0]])
        self.assertEqual(client.embed(["a", "b"]), [[1.0, 0.0], [0.0, 1.0]])

    def test_embed_of_nothing_makes_no_call(self):
        client, fake = self.client(vectors=[])
        self.assertEqual(client.embed([]), [])
        self.assertEqual(fake.embeddings.calls, [])

    def test_embed_without_a_deployment_is_named(self):
        client = AzureLlmClient(LlmConfig(endpoint="https://a.invalid/"), client=FakeOpenAI())
        with self.assertRaises(LlmConfigError):
            client.embed(["a"])


if __name__ == "__main__":
    unittest.main()
