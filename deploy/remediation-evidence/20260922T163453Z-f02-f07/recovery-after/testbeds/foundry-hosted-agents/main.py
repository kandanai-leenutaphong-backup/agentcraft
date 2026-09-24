"""Foundry Responses transport; llm_interface owns the Microsoft Agent Framework loop."""

import json
import asyncio
import os
import ssl

from composition import ROOT, load_spec
from proof_tools import nonce_digest, nonce_statistics

TOOLS = {"nonce_digest": nonce_digest, "nonce_statistics": nonce_statistics}


def parse_input(text):
    if text.startswith("{"):
        request = json.loads(text)
        if not isinstance(request, dict) or set(request) != {"tool", "nonce"}:
            raise ValueError("expected tool and nonce only")
        tool_name, nonce = request["tool"], request["nonce"]
    else:
        tool_name, nonce = "nonce_digest", text
    if not isinstance(tool_name, str) or tool_name not in TOOLS:
        raise ValueError("unknown tool refused")
    nonce_digest(nonce)
    return tool_name, nonce


async def execute_proof(nonce, endpoint, credential, tls_context, tool_name="nonce_digest"):
    import httpx
    from llm_interface import Limits, connect

    expected = TOOLS[tool_name](nonce)
    spec = load_spec()
    events = []
    async with httpx.AsyncHTTPTransport(verify=tls_context, trust_env=False, retries=0) as transport, connect(
        endpoint, spec.model, credential=credential, allow_model_calls=True,
        transport=transport,
        allowed_tools=tuple(TOOLS),
        limits=Limits(max_model_calls=2, max_tool_calls=1, max_output_tokens=512,
                      timeout_seconds=90, max_concurrency=1),
    ) as model:
        agent = model.agent(name=spec.name, instructions=spec.instructions, tools=spec.tools)
        async with agent.run(f"Call {tool_name} exactly once for nonce {nonce}", stream=True) as stream:
            async for event in stream:
                if event.kind in {"tool.call.ready", "tool.started", "tool.result"}:
                    events.append(event.to_dict())
            final = await stream.get_final_response()
    validate_events(events, expected, tool_name)
    return {"nonce": nonce, "requested_tool": tool_name, "tool_events": events, "answer": final.text}


def validate_events(events, expected, tool_name="nonce_digest"):
    ready = [event["data"] for event in events if event["kind"] == "tool.call.ready"]
    started = [event["data"] for event in events if event["kind"] == "tool.started"]
    results = [event["data"] for event in events if event["kind"] == "tool.result"]
    if len(ready) != 1 or len(started) != 1 or len(results) != 1:
        raise ValueError("exactly one observed tool invocation required")
    call_id = ready[0].get("call_id")
    if (not call_id or ready[0].get("name") != tool_name
            or ready[0].get("arguments") != {"nonce": expected["nonce"]}
            or started[0].get("name") != tool_name
            or started[0].get("call_id") != call_id or results[0].get("call_id") != call_id
            or results[0].get("result") != expected):
        raise ValueError("tool evidence does not match nonce, call identity and result")


async def run_cancellable(operation, signal):
    task = asyncio.create_task(operation)
    waiter = asyncio.create_task(signal.wait())
    try:
        await asyncio.wait((task, waiter), return_when=asyncio.FIRST_COMPLETED)
        if signal.is_set():
            raise asyncio.CancelledError
        return await task
    finally:
        for pending in (task, waiter):
            if not pending.done():
                pending.cancel()
        await asyncio.gather(task, waiter, return_exceptions=True)


def create_server(endpoint, manifest, **host_options):
    from azure.ai.agentserver.responses import ResponsesAgentServerHost, TextResponse
    from azure.identity.aio import DefaultAzureCredential

    server = ResponsesAgentServerHost(**host_options)
    tls_context = ssl.create_default_context()

    @server.response_handler
    async def handler(request, context, cancellation_signal):
        if cancellation_signal.is_set():
            raise asyncio.CancelledError
        tool_name, nonce = parse_input((await context.get_input_text() or "").strip())
        async with DefaultAzureCredential(
            exclude_interactive_browser_credential=True, exclude_shared_token_cache_credential=True,
            exclude_visual_studio_code_credential=True, exclude_cli_credential=True,
            exclude_developer_cli_credential=True, exclude_powershell_credential=True,
        ) as credential:
            result = await run_cancellable(execute_proof(nonce, endpoint, credential, tls_context, tool_name), cancellation_signal)
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