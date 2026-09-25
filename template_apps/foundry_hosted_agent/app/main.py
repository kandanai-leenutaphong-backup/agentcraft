"""Foundry Responses protocol host; llm_interface owns the Microsoft Agent Framework loop."""

import asyncio
import json
import logging
import os
import ssl
import sys

import tool_calls
from composition import ROOT, load_optimized_spec, package_manifest, package_root

MAX_INPUT_CHARACTERS = 8192
MAX_METADATA_KEYS = 16
LIMITS = {"max_model_calls": 4, "max_tool_calls": 4, "max_output_tokens": 1024,
          "timeout_seconds": 120, "max_concurrency": 1}
SELF_CHECK_ENDPOINT = "https://self-check.invalid/api/projects/self-check"


def parse_input(text):
    if not isinstance(text, str) or not text.strip() or len(text) > MAX_INPUT_CHARACTERS:
        raise ValueError("bounded non-empty input required")
    return text.strip()


def load_identity(environ, path=ROOT / "source-manifest.json"):
    """Exact build identity returned as response metadata so a stored response proves what served it."""
    manifest = json.loads(path.read_text())
    config_sha256 = manifest.get("config_sha256") or manifest["files"]["app/configuration.yaml"]
    return {"source_sha256": manifest["sha256"], "config_sha256": config_sha256,
            "agent_name": environ["FOUNDRY_AGENT_NAME"], "agent_version": environ["FOUNDRY_AGENT_VERSION"]}


def platform_credential(asynchronous=True):
    """Platform managed identity only; developer and interactive credentials are excluded."""
    if asynchronous:
        from azure.identity.aio import DefaultAzureCredential
    else:
        from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(
        exclude_interactive_browser_credential=True, exclude_shared_token_cache_credential=True,
        exclude_visual_studio_code_credential=True, exclude_cli_credential=True,
        exclude_developer_cli_credential=True, exclude_powershell_credential=True)


async def run_agent(text, endpoint, spec, credential, tls_context, emit):
    """Streams the llm_interface run; emits ("text", delta), ("call", ready data), ("result", tool record)."""
    import httpx
    from llm_interface import Limits, connect

    recorder = tool_calls.ToolCallRecorder(spec.tools)
    # Platform CA trust with CERT_REQUIRED and hostname checks; the default transport failed verification live.
    async with httpx.AsyncHTTPTransport(verify=tls_context, trust_env=False, retries=0) as transport, connect(
        endpoint, spec.model, credential=credential, allow_model_calls=True, transport=transport,
        allowed_tools=tuple(tool.__name__ for tool in spec.tools), limits=Limits(**LIMITS),
    ) as model:
        agent = model.agent(name=spec.name, instructions=spec.instructions, tools=recorder.tools,
                            authorize_tool=recorder.authorize)
        async with agent.run(text, stream=True) as stream:
            async for event in stream:
                if event.kind == "text.delta" and event.text:
                    await emit(("text", event.text))
                elif event.kind == "tool.call.ready":
                    await emit(("call", event.data))
                elif event.kind == "tool.result":
                    await emit(("result", recorder.records[event.data["call_id"]]))
            result = await stream.get_final_response()
    return result.text


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


def _canonical(value):
    return json.dumps(value, sort_keys=True)


async def respond(context, request, identity, produce, cancellation_signal):
    """Native Responses events: text messages, and per tool call a function_call then a function_call_output item."""
    from azure.ai.agentserver.responses import ResponseEventStream

    stream = ResponseEventStream(response_id=context.response_id, request=request)
    stream.response["metadata"] = dict(identity)
    yield stream.emit_created()
    yield stream.emit_in_progress()
    queue = asyncio.Queue()

    async def work():
        try:
            return await run_cancellable(produce(queue.put), cancellation_signal)
        finally:
            queue.put_nowait(None)

    task = asyncio.create_task(work())
    message, emitted_text, results = [], False, 0

    def close_message():
        if not message:
            return []
        builder, content, parts = message
        message.clear()
        return [content.emit_text_done("".join(parts)), content.emit_done(), builder.emit_done()]

    def open_message():
        builder = stream.add_output_item_message()
        content = builder.add_text_content()
        message.extend((builder, content, []))
        return [builder.emit_added(), content.emit_added()]

    try:
        while (event := await queue.get()) is not None:
            kind, data = event
            if kind == "text":
                for item in [] if message else open_message():
                    yield item
                message[2].append(data)
                emitted_text = True
                yield message[1].emit_delta(data)
                continue
            for item in close_message():
                yield item
            if kind == "call":
                for item in stream.output_item_function_call(data["name"], data["call_id"],
                                                             _canonical(data["arguments"])):
                    yield item
            else:
                results += 1
                stream.response["metadata"][tool_calls.METADATA_PREFIX + str(results)] = tool_calls.metadata_entry(data)
                for item in stream.output_item_function_call_output(data["call_id"], _canonical(data["result"])):
                    yield item
        text = await task
        if text and not emitted_text:
            for item in open_message():
                yield item
            message[2].append(text)
            yield message[1].emit_delta(text)
        for item in close_message():
            yield item
        yield stream.emit_completed()
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def create_server(endpoint, spec, identity, **host_options):
    from azure.ai.agentserver.responses import ResponsesAgentServerHost

    if len(identity) + LIMITS["max_tool_calls"] > MAX_METADATA_KEYS:
        raise ValueError("identity plus one metadata key per tool call exceeds 16 response metadata keys")
    server = ResponsesAgentServerHost(**host_options)
    tls_context = ssl.create_default_context()
    metadata = dict(identity)

    @server.response_handler
    async def handler(request, context, cancellation_signal):
        if cancellation_signal.is_set():
            raise asyncio.CancelledError
        text = parse_input(await context.get_input_text())

        async def produce(emit):
            try:
                async with platform_credential() as credential:
                    return await run_agent(text, endpoint, spec, credential, tls_context, emit)
            except asyncio.CancelledError:
                logging.getLogger(__name__).warning("cancellation_settled response_id=%s", context.response_id)
                raise

        return respond(context, request, metadata, produce, cancellation_signal)

    return server


def self_check(environ=os.environ):
    """Image-build smoke over the real SDKs: schemas build, host is ready, invalid input fails. No model call."""
    from agent_framework import tool
    from starlette.testclient import TestClient

    package = package_root(environ)
    spec, optimization = load_optimized_spec(credential=None, package=package)
    schemas = [tool(function).to_json_schema_spec()
               for function in tool_calls.ToolCallRecorder(spec.tools).tools]
    package_sha256 = package_manifest(package)["sha256"]
    identity = {"source_sha256": "self-check", "config_sha256": "self-check", "package_sha256": package_sha256,
                "agent_name": "self-check", "agent_version": "0", **optimization}
    server = create_server(SELF_CHECK_ENDPOINT, spec, identity, configure_observability=None)
    with TestClient(server, raise_server_exceptions=False) as client:
        readiness = client.get("/readiness").status_code
        refused = client.post("/responses", json={"input": " ", "stream": False, "store": False})
    body = refused.json()
    if readiness != 200 or not (refused.status_code >= 400 or body.get("status") == "failed"):
        raise RuntimeError("hosting self-check failed")
    return {"readiness": readiness, "invalid_input_status": refused.status_code,
            "tools": [schema["function"]["name"] for schema in schemas], "package_sha256": package_sha256,
            "optimization": optimization.get("optimization_candidate_id", "none")}


def main(argv=None, environ=os.environ):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--self-check"]:
        print(json.dumps(self_check(environ), sort_keys=True))
        return
    package = package_root(environ)
    with platform_credential(asynchronous=False) as credential:
        spec, optimization = load_optimized_spec(credential, package=package)
    identity = {**load_identity(environ), "package_sha256": package_manifest(package)["sha256"], **optimization}
    create_server(environ["FOUNDRY_PROJECT_ENDPOINT"], spec, identity).run()


if __name__ == "__main__":
    main()
