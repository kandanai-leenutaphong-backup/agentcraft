"""Foundry Responses transport; llm_interface owns the Microsoft Agent Framework loop."""

import json
import os

from composition import ROOT, load_spec
from proof_tools import nonce_digest


async def execute_proof(nonce, endpoint, credential):
    from llm_interface import Limits, connect

    expected = nonce_digest(nonce)
    spec = load_spec()
    events = []
    async with connect(
        endpoint, spec.model, credential=credential, allow_model_calls=True,
        allowed_tools=("nonce_digest",),
        limits=Limits(max_model_calls=2, max_tool_calls=1, max_output_tokens=512,
                      timeout_seconds=90, max_concurrency=1),
    ) as model:
        agent = model.agent(name=spec.name, instructions=spec.instructions, tools=spec.tools)
        async with agent.run(f"Call nonce_digest for nonce {nonce}", stream=True) as stream:
            async for event in stream:
                if event.kind in {"tool.call.ready", "tool.started", "tool.result"}:
                    events.append(event.to_dict())
            final = await stream.get_final_response()
    validate_events(events, expected)
    return {"nonce": nonce, "tool_events": events, "answer": final.text}


def validate_events(events, expected):
    ready = [event["data"] for event in events if event["kind"] == "tool.call.ready"]
    started = [event["data"] for event in events if event["kind"] == "tool.started"]
    results = [event["data"] for event in events if event["kind"] == "tool.result"]
    if len(ready) != 1 or len(started) != 1 or len(results) != 1:
        raise ValueError("exactly one observed tool invocation required")
    call_id = ready[0].get("call_id")
    if (not call_id or ready[0].get("name") != "nonce_digest"
            or ready[0].get("arguments") != {"nonce": expected["nonce"]}
            or started[0].get("name") != "nonce_digest"
            or started[0].get("call_id") != call_id or results[0].get("call_id") != call_id
            or results[0].get("result") != expected):
        raise ValueError("tool evidence does not match nonce, call identity and result")


def create_server(endpoint, manifest, **host_options):
    from azure.ai.agentserver.responses import ResponsesAgentServerHost, TextResponse
    from azure.identity.aio import DefaultAzureCredential

    server = ResponsesAgentServerHost(**host_options)

    @server.response_handler
    async def handler(request, context, _cancellation_signal):
        nonce = (await context.get_input_text() or "").strip()
        nonce_digest(nonce)
        async with DefaultAzureCredential(
            exclude_interactive_browser_credential=True, exclude_shared_token_cache_credential=True,
            exclude_visual_studio_code_credential=True, exclude_cli_credential=True,
            exclude_developer_cli_credential=True, exclude_powershell_credential=True,
        ) as credential:
            result = await execute_proof(nonce, endpoint, credential)
        result.update(source_sha256=manifest["sha256"],
                      config_sha256=manifest["files"]["app/configuration.yaml"],
                      agent_name=os.environ["FOUNDRY_AGENT_NAME"],
                      agent_version=os.environ["FOUNDRY_AGENT_VERSION"])
        return TextResponse(context, request, text=json.dumps(result, sort_keys=True))

    return server


def main():
    create_server(os.environ["FOUNDRY_PROJECT_ENDPOINT"],
                  json.loads((ROOT / "source-manifest.json").read_text())).run()


if __name__ == "__main__":
    main()