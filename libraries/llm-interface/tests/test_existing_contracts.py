"""Comparison of installed legacy public APIs; no runtime imports from skills."""

from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

import azllm
import modelaccess


class Stream:
    def __init__(self, events):
        self.events = events
        self.closed = False

    def __iter__(self):
        return iter(self.events)

    def close(self):
        self.closed = True


class Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.requests = []
        self.closed = False
        self.responses = self

    def create(self, **options):
        self.requests.append(options)
        if self.error:
            raise self.error
        return self.response

    def close(self):
        self.closed = True


class ExistingContracts(unittest.TestCase):
    def setUp(self):
        blocker = patch("socket.socket.connect", side_effect=AssertionError("Network forbidden"))
        blocker.start()
        self.addCleanup(blocker.stop)
        self.packages = (
            (azllm, azllm.FoundryConfig(endpoint="https://fixture.invalid/", deployment="fixture"), azllm.LlmError),
            (modelaccess, modelaccess.ModelConfig(endpoint="https://fixture.invalid/", deployment="fixture"), modelaccess.ModelError),
        )

    def test_both_existing_packages_validate_embedding_alignment(self):
        invalid = {
            "duplicate": [(0, [1.0]), (0, [2.0])],
            "missing": [(0, [1.0])],
            "out_of_range": [(0, [1.0]), (2, [2.0])],
            "boolean_index": [(False, [1.0]), (1, [2.0])],
            "unequal_width": [(0, [1.0]), (1, [2.0, 3.0])],
            "nonfinite": [(0, [float("inf")]), (1, [2.0])],
            "boolean_component": [(0, [True]), (1, [2.0])],
            "empty_vector": [(0, []), (1, [])],
        }
        for package, config, error_type in self.packages:
            valid = SimpleNamespace(model="fixture", data=[
                SimpleNamespace(index=1, embedding=[2.0]), SimpleNamespace(index=0, embedding=[1.0])])
            self.assertEqual(package.EmbeddingResult.from_response(valid, deployment=config.deployment,
                             expected_count=2).vectors, ((1.0,), (2.0,)))
            for name, entries in invalid.items():
                with self.subTest(package=package.__name__, case=name):
                    response = SimpleNamespace(model="fixture", data=[
                        SimpleNamespace(index=index, embedding=vector) for index, vector in entries])
                    with self.assertRaises(error_type):
                        package.EmbeddingResult.from_response(response, deployment=config.deployment, expected_count=2)

    def test_borrowed_client_ownership_differs(self):
        for package, config, error_type in self.packages:
            native = Client()
            connector = package.connect(config, client=native)
            connector.close()
            connector.close()
            self.assertEqual(native.closed, package is azllm)

    def test_existing_text_streams_close_but_accept_quiet_eof(self):
        for package, config, error_type in self.packages:
            stream = Stream([SimpleNamespace(type="response.output_text.delta", delta="unfinished")])
            connector = package.connect(config, client=Client(stream))
            with connector:
                self.assertEqual(list(connector.stream_text("fixture")), ["unfinished"])
            self.assertTrue(stream.closed)

    def test_existing_text_streams_refuse_explicit_failure(self):
        for package, config, error_type in self.packages:
            stream = Stream([SimpleNamespace(type="response.failed", response=SimpleNamespace(
                error=SimpleNamespace(code="fixture_failure")))])
            with package.connect(config, client=Client(stream)) as connector:
                with self.assertRaises(error_type) as refusal:
                    list(connector.stream_text("fixture"))
                self.assertEqual(refusal.exception.category, "stream")
            self.assertTrue(stream.closed)

    def test_safe_error_projection_does_not_make_traceback_safe(self):
        for package, config, error_type in self.packages:
            native = Client(error=RuntimeError("fixture-private-payload"))
            with package.connect(config, client=native) as connector:
                with self.assertRaises(error_type) as failure:
                    connector.ask("synthetic input")
            self.assertNotIn("fixture-private-payload", str(failure.exception))
            self.assertIn("fixture-private-payload", str(failure.exception.__cause__))

    def test_modelaccess_allowlist_refuses_foreign_chat_or_embedding_host(self):
        with self.assertRaises(modelaccess.ConfigError):
            modelaccess.ModelConfig(endpoint="https://foreign.invalid/", deployment="fixture",
                                    allowed_hosts=("fixture.invalid",))
        with self.assertRaises(modelaccess.ConfigError):
            modelaccess.ModelConfig(endpoint="https://fixture.invalid/", deployment="fixture",
                                    embedding_endpoint="https://foreign.invalid/", embedding_deployment="vectors",
                                    allowed_hosts=("fixture.invalid",))


if __name__ == "__main__":
    unittest.main()