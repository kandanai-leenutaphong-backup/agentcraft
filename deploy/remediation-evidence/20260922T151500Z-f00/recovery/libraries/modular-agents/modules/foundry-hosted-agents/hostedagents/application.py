"""Authenticated local HTTP and Foundry invocations adapters for AgentRuntime."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import importlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Callable, Mapping

import agentconfig
from pydantic import BaseModel, ConfigDict, Field, StrictBool, ValidationError
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, PlainTextResponse, StreamingResponse
from starlette.routing import Route

from .definition import Definition
from .engine import AgentRuntime, InvocationRefused
from .model import connect_model
from .policy import RuntimePolicy, RuntimeTarget


class _Invocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    op: str = "health"
    tool: str = ""
    arguments: dict[str, Any] = Field(default_factory=dict)
    message: str = ""
    turn_id: str = ""
    stream: StrictBool = True


def local_authorizer(token: str) -> Callable[[Request], str]:
    if len(token) < 32:
        raise ValueError("local serving requires an operator token of at least 32 characters")
    principal = "local:" + hashlib.sha256(token.encode()).hexdigest()

    def authorize(request: Request) -> str:
        supplied = request.headers.get("authorization", "")
        return principal if hmac.compare_digest(supplied, f"Bearer {token}") else ""

    return authorize


def create_app(runtime: AgentRuntime, *, authorize: Callable[[Request], str]) -> Starlette:
    async def readiness(_: Request) -> PlainTextResponse:
        return PlainTextResponse("ready")

    async def invoke(request: Request):
        principal = authorize(request)
        if not principal:
            return JSONResponse({"error": "authentication required"}, status_code=401)
        payload = bytearray()
        async for chunk in request.stream():
            payload.extend(chunk)
            if len(payload) > 128_000:
                return JSONResponse({"error": "request body too large"}, status_code=413)
        try:
            body = _Invocation.model_validate_json(bytes(payload))
        except ValidationError:
            return JSONResponse({"error": "invalid invocation shape"}, status_code=400)
        try:
            if body.op == "health":
                return JSONResponse(runtime.status())
            if body.op == "tools":
                return JSONResponse({"tools": runtime.tools.schemas})
            if body.op == "call":
                return JSONResponse(await runtime.call(body.tool, body.arguments, principal=principal))
            if body.op == "result":
                return JSONResponse(runtime.result(body.turn_id, principal=principal))
            if body.op == "abort":
                return JSONResponse(runtime.abort(body.turn_id, principal=principal))
            if body.op == "chat":
                prepared = runtime.prepare_chat(body.message, principal=principal, turn_id=body.turn_id)
                events = runtime.chat_events(body.message, principal=principal, prepared=prepared)
                if not body.stream:
                    async for _event, _payload in events:
                        pass
                    return JSONResponse(runtime.result(prepared[0], principal=principal))

                async def frames():
                    async for event, value in events:
                        yield f"event: {event}\ndata: {json.dumps(value)}\n\n".encode()

                return StreamingResponse(frames(), media_type="text/event-stream")
            return JSONResponse({"error": "unknown operation"}, status_code=400)
        except InvocationRefused as failure:
            return JSONResponse({"error": str(failure)}, status_code=failure.status)
        except TimeoutError:
            return JSONResponse({"error": "operation timeout"}, status_code=504)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            await runtime.aclose()

    app = Starlette(lifespan=lifespan, routes=[
        Route("/readiness", readiness, methods=["GET"]),
        Route("/invocations", invoke, methods=["POST"]),
    ])

    async def guard(request: Request, call_next):
        if request.url.path != "/readiness" and not authorize(request):
            return JSONResponse({"error": "authentication required"}, status_code=401,
                                headers={"Cache-Control": "no-store, private"})
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store, private"
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=guard)
    return app


def load_runtime(root: Path, *, connection=None, owns_connection: bool = False) -> AgentRuntime:
    identity = (root / "runtime_manifest.json").read_bytes()
    for name, digest in json.loads(identity).items():
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()) or path.is_symlink():
            raise ValueError("runtime manifest contains a nonlocal file")
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("runtime source differs from its build manifest")
    raw = (root / "agent_config.json").read_bytes()
    config = json.loads(raw)
    functions = []
    for reference in config["tools"]:
        module, name = reference.split(":", 1)
        functions.append(getattr(importlib.import_module(module), name))
    spec = agentconfig.AgentSpec(
        agent_id=config["agent_id"], name=config["name"], description=config["description"],
        model=config["model"], instructions=config["instructions"], tools=tuple(functions),
    )
    definition = Definition.from_spec(spec)
    schemas = json.loads((root / "tool_schemas.json").read_bytes())
    if schemas != definition.tools.schemas:
        raise ValueError("packaged tool schemas differ from the imported functions")
    return AgentRuntime(
        definition, RuntimePolicy.model_validate(config["policy"]), connection=connection,
        owns_connection=owns_connection,
        artifact_id=hashlib.sha256(identity).hexdigest(),
    )


def serve(root: Path, *, environment: Mapping[str, str] | None = None) -> None:
    import uvicorn

    environment = dict(os.environ if environment is None else environment)
    config = json.loads((root / "agent_config.json").read_bytes())
    policy = RuntimePolicy.model_validate(config["policy"])
    target = RuntimeTarget.model_validate(config["target"])
    session = environment.get("FOUNDRY_AGENT_SESSION_ID", "")
    version = environment.get("FOUNDRY_AGENT_VERSION", "")
    hosted = bool(session and version)
    if bool(session) != bool(version):
        raise ValueError("Foundry session and version must both be present")
    if hosted:
        principal = "foundry-session:" + hashlib.sha256(session.encode()).hexdigest()
        authorize = lambda _request: principal
    else:
        authorize = local_authorizer(environment.get("MODULAR_AGENTS_LOCAL_TOKEN", ""))
    connection = None
    credential = None
    try:
        if policy.allow_model:
            from azure.identity import AzureCliCredential, ManagedIdentityCredential

            credential = ManagedIdentityCredential() if hosted else AzureCliCredential()
            connection = connect_model(target, policy, model=config["model"], credential=credential)
        runtime = load_runtime(root, connection=connection, owns_connection=connection is not None)
        uvicorn.run(
            create_app(runtime, authorize=authorize),
            host="0.0.0.0" if hosted else "127.0.0.1",
            port=int(environment.get("PORT", "8088")),
            log_level="warning",
        )
    finally:
        if connection is not None:
            asyncio.run(connection.aclose())
        if credential is not None:
            credential.close()