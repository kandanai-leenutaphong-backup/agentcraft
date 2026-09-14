#!/usr/bin/env python3
"""Exercise the copied capability without pytest, credentials or provider requests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from azllm import ConfigError, FoundryConfig, LlmError, connect, connect_async, embedding_config
from fakes import FakeAsyncClient, FakeClient, error_event, text_delta


def main() -> None:
    with patch("socket.socket.connect", side_effect=AssertionError("selftest attempted network access")):
        try:
            FoundryConfig.from_env(env={})
        except ConfigError:
            print("ok: no implicit account endpoint")
        else:
            raise AssertionError("missing account configuration was accepted")

        config = FoundryConfig(endpoint="https://model.example.invalid", deployment="chat")
        client = FakeClient()
        with connect(config, client=client) as connector:
            answer = connector.ask("fixture question", max_output_tokens=20)
            assert answer.text == "hello"
            assert client.responses.calls[-1]["store"] is False
            print("ok: injected chat request and result round trip")
            embedded = connector.embed(["first", "second"], deployment="embedding", dimensions=3)
            assert embedded.count == 2 and embedded.dimensions == 3
            print("ok: embedding alignment and shape")
            client.responses.stream_events = [text_delta("first"), text_delta(" second")]
            assert "".join(connector.stream_text("fixture stream")) == "first second"
            client.responses.stream_events = [error_event()]
            try:
                list(connector.stream_text("failed fixture"))
            except LlmError:
                print("ok: streaming error is not a successful short answer")
            else:
                raise AssertionError("stream failure was hidden")

        try:
            embedding_config("embedding")
        except ConfigError:
            print("ok: embedding routing requires an explicit endpoint")
        else:
            raise AssertionError("embedding endpoint was guessed")

        async def check_async() -> None:
            async with connect_async(config, client=FakeAsyncClient()) as connector:
                assert (await connector.ask("fixture question")).text == "hello"

        asyncio.run(check_async())
        print("ok: async connector works with an injected client")
    print("azure-llm-connectors selftest: PASS")


if __name__ == "__main__":
    main()