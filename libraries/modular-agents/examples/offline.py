"""Configuration, measured fixture tool, refusal and immutable host bundle, offline."""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

from hostedagents import AgentRuntime, InvocationRefused, RuntimePolicy, build_bundle, load_bundle, load_definition
from toolshape import MemorySink, aggregate, get_sink, set_sink

EXAMPLES = Path(__file__).resolve().parent


async def main() -> None:
    definition = load_definition(EXAMPLES / "control", allowed_prefixes=("agent_tools.",))
    policy = RuntimePolicy(allowed_tools=definition.tools.names)
    runtime = AgentRuntime(definition, policy)
    sink, previous = MemorySink(), get_sink()
    set_sink(sink)
    try:
        result = await runtime.call("search_notes", {"query": "hosting"}, principal="example-owner")
        assert result["rows"][0]["title"] == "Hosting"
        try:
            await runtime.call("unknown", {}, principal="example-owner")
        except InvocationRefused:
            pass
        else:
            raise AssertionError("Unknown tool was admitted")
        assert len(sink.records) == 1
        report = aggregate(sink.records)
        assert report is not None
        with tempfile.TemporaryDirectory(prefix="modular-example-") as temporary:
            bundle = build_bundle(definition, package_sources={"agent_tools": EXAMPLES / "agent_tools"},
                                  output_dir=Path(temporary), policy=policy)
            assert load_bundle(bundle.directory).sha256 == bundle.sha256
        print(json.dumps({"mode": "offline fixture", "agent": definition.spec.agent_id,
                          "tool_calls": len(sink.records), "bundle_readback": True, "model_calls": 0}))
    finally:
        set_sink(previous)
        await runtime.aclose()


if __name__ == "__main__":
    asyncio.run(main())