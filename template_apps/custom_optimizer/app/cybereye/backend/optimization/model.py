"""One bounded native model run per authorized local-operator prediction."""

from __future__ import annotations

import json

from llm_interface import Connection, LlmError


def model_predictor(connection: Connection, request_builder, *, principal: str):
    if not principal:
        raise ValueError("prediction_owner_required")

    async def predict(prompt: str, evidence: dict, model: str) -> dict:
        if model != connection.config.model:
            raise LlmError("prediction_model_outside_scope", category="denied")
        request = request_builder(prompt, evidence, model)
        if request.get("contract") != "llm_interface.agent/v1" or request.get("model") != model:
            raise ValueError("prediction_contract_invalid")
        agent = connection.agent(instructions=request["instructions"], name="guide-grader",
                                 tools=(), authorize_tool=lambda call: False)
        session = agent.create_session(principal=principal)
        stream = agent.run(request["message"], session=session, principal=principal,
                           options=request["options"], stream=True)
        event_count = 0
        terminal = None
        async with stream:
            async for event in stream:
                event_count += 1
                if event.kind in {"run.completed", "run.incomplete", "run.refused", "run.failed"}:
                    terminal = {"schema_version": event.schema_version, "kind": event.kind,
                                "run_id": event.run_id, "sequence": event.sequence}
            await stream.get_final_response()
        response = session.result(principal=principal)
        receipt = response.additional_properties["llm_interface"]
        if receipt["status"] != "completed" or terminal is None or terminal["kind"] != "run.completed":
            raise LlmError("prediction_incomplete", category="interrupted")
        answer = json.loads(response.text)
        if not isinstance(answer, dict):
            raise ValueError("prediction_object_required")
        answer["llm_interface"] = {**receipt, "session_id": session.id,
                       "observed_events": event_count, "terminal_event": terminal}
        return answer

    return predict