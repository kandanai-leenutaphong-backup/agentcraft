#!/usr/bin/env python3
"""A complete injected-client example; no identity or network is used."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

from azllm import FoundryConfig, connect
from fakes import FakeClient


if __name__ == "__main__":
    config = FoundryConfig(endpoint="https://model.example.invalid", deployment="chat")
    with connect(config, client=FakeClient()) as connector:
        answer = connector.ask("fixture question", max_output_tokens=32)
        print(json.dumps({"fixtures": True, "text": answer.text, **answer.metadata()}))