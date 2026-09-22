"""Run the real framework/SDK paths against synthetic Foundry HTTP, with no network."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from llm_interface import connect, report_progress


class FixtureIdentity:
    async def get_token(self, *scopes, **options):
        return SimpleNamespace(token="synthetic-fixture", expires_on=4_000_000_000)


def response(identifier, output, status="completed"):
    return {"id": identifier, "object": "response", "created_at": 1,
            "model": "fixture-chat", "status": status, "output": output,
            "error": None, "incomplete_details": None, "instructions": None,
            "tools": [], "tool_choice": "auto", "parallel_tool_calls": True,
            "temperature": 1, "top_p": 1, "metadata": {},
            "usage": {"input_tokens": 4, "output_tokens": 3, "total_tokens": 7,
                      "input_tokens_details": {"cached_tokens": 0},
                      "output_tokens_details": {"reasoning_tokens": 0}}}


def message(text):
    return {"id": "msg_fixture", "type": "message", "role": "assistant", "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": [], "logprobs": []}]}


class Fixture:
    def __init__(self):
        self.calls = 0

    async def handle(self, request):
        assert request.url.host == "fixture.invalid"
        self.calls += 1
        body = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"object": "list", "model": "fixture-vectors",
                "data": [{"object": "embedding", "index": index, "embedding": [float(index), 1.0]}
                         for index in reversed(range(len(body["input"])))],
                "usage": {"prompt_tokens": 2, "total_tokens": 2}})
        if not body.get("stream"):
            return httpx.Response(200, json=response("resp_direct", [message("Synthetic standalone answer.")]))
        has_result = any(item.get("type") == "function_call_output" for item in body["input"])
        if not has_result:
            call = {"type": "function_call", "id": "fc_fixture", "call_id": "call_fixture",
                    "name": "lookup", "arguments": '{"record_id":"demo"}', "status": "completed"}
            events = [
                {"type": "response.output_item.added", "output_index": 0,
                 "item": {**call, "arguments": "", "status": "in_progress"}},
                {"type": "response.function_call_arguments.delta", "item_id": "fc_fixture", "output_index": 0,
                 "delta": call["arguments"]},
                {"type": "response.output_item.done", "output_index": 0, "item": call},
                {"type": "response.completed", "response": response("resp_tool", [call])},
            ]
        else:
            events = [
                {"type": "response.output_text.delta", "item_id": "msg_fixture", "output_index": 0,
                 "content_index": 0, "delta": "Synthetic record verified.", "logprobs": []},
                {"type": "response.completed", "response": response("resp_final", [message("Synthetic record verified.")])},
            ]
        wire = "".join("event: " + event["type"] + "\ndata: " + json.dumps({**event, "sequence_number": index}) + "\n\n"
                       for index, event in enumerate(events))
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=wire)


async def lookup(record_id: str) -> dict:
    """Look up a synthetic record in this example, not a real data service."""
    await report_progress({"step": "lookup"})
    return {"record_id": record_id, "source": "synthetic", "verified": True}


async def main():
    fixture = Fixture()
    async with connect("https://fixture.invalid/api/projects/demo", "fixture-chat",
                       credential=FixtureIdentity(), allow_model_calls=True, allowed_tools=("lookup",),
                       embedding_model="fixture-vectors", transport=httpx.MockTransport(fixture.handle)) as model:
        print((await model.chat.get_response("Give a synthetic answer.")).text)
        vectors = await model.embeddings.get_embeddings(["first", "second"])
        assert [item.vector[0] for item in vectors] == [0.0, 1.0]
        agent = model.agent(instructions="Use lookup to inspect the synthetic record.", tools=[lookup])
        session = agent.create_session()
        async with agent.run("Inspect demo.", session=session, stream=True) as stream:
            kinds = []
            async for event in stream:
                kinds.append(event.kind)
                print(event.kind, event.text)
            final = await stream.get_final_response()
        assert final.text == "Synthetic record verified."
        assert session.result().text == final.text
        assert {"tool.call.ready", "tool.started", "tool.progress", "tool.result", "run.completed"} <= set(kinds)
    assert fixture.calls == 4
    print("PASS: standalone response, aligned embeddings, streaming tool loop and final read-back; 4 synthetic model requests.")


if __name__ == "__main__":
    with patch("socket.socket.connect", side_effect=AssertionError("Network forbidden in offline example")):
        asyncio.run(main())