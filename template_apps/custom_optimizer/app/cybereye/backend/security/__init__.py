from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

from fastapi import HTTPException, Request


@dataclass(frozen=True, slots=True)
class Principal:
    id: str
    kind: str = "user"
    issuer: str = ""


LOCAL_PRINCIPAL = Principal("local:workstation", issuer="local-preview")


def is_loopback(value: str) -> bool:
    if value == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def local_request(scope) -> bool:
    peer = scope.get("client") or ()
    if not peer or not is_loopback(str(peer[0])):
        return False
    headers = {name.decode("latin-1").lower(): value.decode("latin-1") for name, value in scope.get("headers", ())}
    try:
        host = urlsplit("//" + headers.get("host", "")).hostname or ""
        origin = urlsplit(headers["origin"]) if headers.get("origin") else None
        return is_loopback(host) and (origin is None or (
            origin.scheme in {"http", "https"} and is_loopback(origin.hostname or "")
            and not origin.username and not origin.password))
    except ValueError:
        return False


class LocalGate:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            if not local_request(scope):
                await send({"type": "http.response.start", "status": 401, "headers": [(b"cache-control", b"no-store")]})
                await send({"type": "http.response.body", "body": b""})
                return
            scope.setdefault("state", {})["principal"] = LOCAL_PRINCIPAL
        elif scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await self.app(scope, receive, send)


def current_principal(request: Request) -> Principal:
    principal = getattr(request.state, "principal", None)
    if not isinstance(principal, Principal):
        raise HTTPException(401)
    return principal