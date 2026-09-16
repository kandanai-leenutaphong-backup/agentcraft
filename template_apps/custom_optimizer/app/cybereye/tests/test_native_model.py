import json

import httpx
import pytest

from llm_interface import LlmError, connect
from app.cybereye.backend.optimization.model import model_predictor


def request_builder(prompt, evidence, model):
    return {"contract": "llm_interface.agent/v1", "model": model, "instructions": prompt,
            "message": json.dumps(evidence), "options": {"max_tokens": 350,
            "response_format": {"type": "json_object"}}}


@pytest.mark.asyncio
async def test_native_prediction_has_one_attempt_and_owner_session_receipt():
    requests = []

    async def handle(request):
        body = json.loads(request.content)
        requests.append(body)
        assert body["store"] is False
        assert body["response_format"] == {"type": "json_object"}
        chunks = [{"id": "fixture", "object": "chat.completion.chunk", "created": 1,
                   "model": "fixture", "choices": [{"index": 0, "delta": delta, "finish_reason": reason}]}
                  for delta, reason in [({"role": "assistant", "content": '{"grade":"TruePositive","rationale":"fixture"}'}, None),
                                        ({}, "stop")]]
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
            content="".join("data: " + json.dumps(chunk) + "\n\n" for chunk in chunks) + "data: [DONE]\n\n")

    async with connect("https://fixture.invalid/v1", "fixture", provider="openai_completions",
                       credential="offline-fixture", allow_model_calls=True,
                       transport=httpx.MockTransport(handle)) as connection:
        predict = model_predictor(connection, request_builder, principal="local:workstation")
        with pytest.raises(LlmError):
            await predict("Classify fixture", {}, "another-model")
        assert requests == []
        answer = await predict("Classify fixture", {}, "fixture")
        assert answer["grade"] == "TruePositive"
        assert answer["llm_interface"]["model_calls"] == 1
        assert answer["llm_interface"]["session_id"]
        assert answer["llm_interface"]["status"] == "completed"
        terminal = answer["llm_interface"]["terminal_event"]
        assert terminal["kind"] == "run.completed"
        assert terminal["run_id"] == answer["llm_interface"]["run_id"]
        assert terminal["sequence"] == answer["llm_interface"]["observed_events"]
        assert len(requests) == 1