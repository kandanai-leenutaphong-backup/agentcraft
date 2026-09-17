"""Separate loopback composition for a workstation; the container runs ``main:app``."""

from __future__ import annotations

import ipaddress
import json
import os
import sys
import time
from uuid import uuid4
from typing import Any, Mapping
from urllib.parse import urlsplit

from fastapi import Depends
from fastapi.responses import JSONResponse
from agentcraft_core import CallerContext, ExecutionBudget, ExecutionContext

from . import config
from .security import (
    ENTRA_CLIENT_VAR,
    ENTRA_TENANT_VAR,
    KIND_USER,
    PUBLIC_KEY_VAR,
    PUBLIC_ORIGIN_VAR,
    SESSION_TABLE_ENDPOINT_VAR,
    STATE_KEY,
    Principal,
    SecurityComposition,
    current_principal,
    register_principal_resolver,
)
from .security.config import LEDGER_VAR

# Importing ``config`` already loaded ``.env``, which is what makes the names below withholdable.
ENV_FILE = config.APP_ROOT / ".env"

LOCAL_ISSUER = "local-preview"

# One identity shared by every browser on this machine, in a namespace of its own.
LOCAL_PRINCIPAL = Principal(
    id="local:workstation",
    kind=KIND_USER,
    issuer=LOCAL_ISSUER,
    display="Local preview (this workstation)",
)

# Withheld across ``main``'s import: each configures a provider of identity from outside.
WITHHELD_VARS: tuple[str, ...] = (
    PUBLIC_KEY_VAR,
    LEDGER_VAR,
    ENTRA_TENANT_VAR,
    ENTRA_CLIENT_VAR,
    PUBLIC_ORIGIN_VAR,
    SESSION_TABLE_ENDPOINT_VAR,
)

# The one non-numeric name that means this machine; everything else is decided by the address.
_LOOPBACK_NAME = "localhost"


def _is_loopback_host(name: str | None) -> bool:
    if not name:
        return False
    if name == _LOOPBACK_NAME:
        return True
    try:
        return ipaddress.ip_address(name).is_loopback
    except ValueError:
        return False


def _host_of(value: str) -> str | None:
    return urlsplit(value if "//" in value else f"//{value}").hostname


def _headers(scope: Mapping[str, Any]) -> dict[str, str]:
    return {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", ())
    }


async def loopback_principal(scope: Mapping[str, Any]) -> Principal | None:
    """``None`` is not a refusal here; the gate refuses, once, for every mechanism."""
    if scope.get("type") != "http":
        return None
    client = scope.get("client") or ()
    if not client or not _is_loopback_host(str(client[0])):
        return None
    headers = _headers(scope)
    if not _is_loopback_host(_host_of(headers.get("host", ""))):
        return None
    origin = headers.get("origin", "")
    if origin and not _is_loopback_host(_host_of(origin)):
        return None
    return LOCAL_PRINCIPAL


async def whoami(caller: Principal = Depends(current_principal)) -> JSONResponse:
    """Same shape as the deployed sign-in route answers, so no page needs a local special case."""
    return JSONResponse({
        "id": caller.id,
        "kind": caller.kind,
        "issuer": caller.issuer,
        "display": caller.display,
        "tenant_id": caller.tenant_id,
        "scopes": list(caller.scopes),
        "roles": list(caller.roles),
    })


def import_deployed_app() -> tuple[Any, tuple[str, ...]]:
    # Restored immediately and in this process only; ``main`` imported elsewhere reads them.
    withheld = {name: os.environ.pop(name) for name in WITHHELD_VARS if os.environ.get(name)}
    try:
        from . import main
    finally:
        os.environ.update(withheld)
    return main.app, tuple(withheld)


class LocalBudgetMiddleware:
    def __init__(self, app, *, budget: ExecutionBudget):
        self.app = app
        self.budget = budget

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        execution = ExecutionContext(CallerContext(LOCAL_PRINCIPAL.id), self.budget,
                                     time.monotonic() + 600, uuid4().hex)
        with execution.activate():
            await self.app(scope, receive, send)


def install_local_access(app, *, call_limits: dict[str, int] | None = None) -> SecurityComposition:
    register_principal_resolver(app, loopback_principal)
    if call_limits is not None:
        if set(call_limits) != {"model_calls", "data_calls", "tool_calls"}:
            raise ValueError("local call limits require model_calls, data_calls and tool_calls")
        budget = ExecutionBudget(call_limits)
        app.add_middleware(LocalBudgetMiddleware, budget=budget)

        async def budget_status(caller: Principal = Depends(current_principal)):
            return {**budget.snapshot(), "model_calls_enabled": config.settings.allow_model_calls,
                    "scope": "local-process", "billing_ceiling": "not_configured"}

        app.add_api_route("/api/local/budget", budget_status, methods=["GET"])
        app.router.routes.insert(0, app.router.routes.pop())
    app.add_api_route("/api/whoami", whoami, methods=["GET"], name="local_whoami")
    # ``main`` mounts the frontend at ``/`` and Starlette matches in registration order.
    app.router.routes.insert(0, app.router.routes.pop())
    return getattr(app.state, STATE_KEY)


app, _withheld = import_deployed_app()
security = install_local_access(app, call_limits=json.loads(os.environ["CYBEREYE_LOCAL_CALL_LIMITS"])
                                if os.environ.get("CYBEREYE_LOCAL_CALL_LIMITS") else None)

if _withheld:
    print(
        f"local preview: ignoring {', '.join(_withheld)} from {ENV_FILE}. This composition "
        "authenticates the loopback interface, in code, and no provider configures it.",
        file=sys.stderr,
    )

