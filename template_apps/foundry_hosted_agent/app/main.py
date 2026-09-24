"""Foundry Responses protocol host; llm_interface owns the Microsoft Agent Framework loop."""

import asyncio
import json
import logging
import os
import ssl
import sys

from composition import ROOT, load_spec

MAX_INPUT_CHARACTERS = 8192
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
    return {"source_sha256": manifest["sha256"], "config_sha256": manifest["files"]["app/configuration.yaml"],
            "agent_name": environ["FOUNDRY_AGENT_NAME"], "agent_version": environ["FOUNDRY_AGENT_VERSION"]}


def platform_credential():
    """Platform managed identity only; developer and interactive credentials are excluded."""
    from azure.identity.aio import DefaultAzureCredential

    return DefaultAzureCredential(
        exclude_interactive_browser_credential=True, exclude_shared_token_cache_credential=True,
        exclude_visual_studio_code_credential=True, exclude_cli_credential=True,
        exclude_developer_cli_credential=True, exclude_powershell_credential=True)


async def run_agent(text, endpoint, spec, credential, tls_context):
    import httpx
    from llm_interface import Limits, connect

    # Platform CA trust with CERT_REQUIRED and hostname checks; the default transport failed verification live.
    async with httpx.AsyncHTTPTransport(verify=tls_context, trust_env=False, retries=0) as transport, connect(
        endpoint, spec.model, credential=credential, allow_model_calls=True, transport=transport,
        allowed_tools=tuple(tool.__name__ for tool in spec.tools), limits=Limits(**LIMITS),
    ) as model:
        agent = model.agent(name=spec.name, instructions=spec.instructions, tools=spec.tools)
        result = await agent.run(text)
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


def create_server(endpoint, spec, identity, **host_options):
    from azure.ai.agentserver.responses import ResponsesAgentServerHost, TextResponse

    server = ResponsesAgentServerHost(**host_options)
    tls_context = ssl.create_default_context()
    metadata = dict(identity)

    @server.response_handler
    async def handler(request, context, cancellation_signal):
        if cancellation_signal.is_set():
            raise asyncio.CancelledError
        text = parse_input(await context.get_input_text())

        async def produce():
            try:
                async with platform_credential() as credential:
                    return await run_cancellable(run_agent(text, endpoint, spec, credential, tls_context),
                                                 cancellation_signal)
            except asyncio.CancelledError:
                logging.getLogger(__name__).warning("cancellation_settled response_id=%s", context.response_id)
                raise

        def configure(response):
            response.metadata = dict(metadata)

        return TextResponse(context, request, text=produce, configure=configure)

    return server


def self_check():
    """Image-build smoke over the real SDKs: schemas build, host is ready, invalid input fails. No model call."""
    from agent_framework import tool
    from starlette.testclient import TestClient

    spec = load_spec()
    schemas = [tool(function).to_json_schema_spec() for function in spec.tools]
    identity = {"source_sha256": "self-check", "config_sha256": "self-check",
                "agent_name": "self-check", "agent_version": "0"}
    server = create_server(SELF_CHECK_ENDPOINT, spec, identity, configure_observability=None)
    with TestClient(server, raise_server_exceptions=False) as client:
        readiness = client.get("/readiness").status_code
        refused = client.post("/responses", json={"input": " ", "stream": False, "store": False})
    body = refused.json()
    if readiness != 200 or not (refused.status_code >= 400 or body.get("status") == "failed"):
        raise RuntimeError("hosting self-check failed")
    return {"readiness": readiness, "invalid_input_status": refused.status_code,
            "tools": [schema["function"]["name"] for schema in schemas]}


def main(argv=None, environ=os.environ):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--self-check"]:
        print(json.dumps(self_check(), sort_keys=True))
        return
    create_server(environ["FOUNDRY_PROJECT_ENDPOINT"], load_spec(), load_identity(environ)).run()


if __name__ == "__main__":
    main()
