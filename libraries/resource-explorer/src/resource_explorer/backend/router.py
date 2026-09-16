"""The HTTP surface — four read-only routes over one inventory service.

NEW IN THIS COMPONENT. Route table and headers: `README.md`.

An ``APIRouter`` a host mounts, not an application: no settings object, no
principal guard, no static mount, no development authentication bypass. A
component that brings a second auth story to a host that has one has made the
host less safe. There is no write verb, no query parameter that reaches a
service, and no endpoint that changes server state.

Parameters are validated inside the handlers rather than by ``Query(...)``
constraints. The framework's own validation answers before any of this code
runs, so it carries none of the headers below, and its body echoes the
submitted value — which would turn the one endpoint that accepts client input
into a reflection surface.

Every response is ``no-store, private``: the payloads name the stores this
deployment reads and can carry rows out of them. ``Vary`` names the selection
header because two requests differing only in it are different answers.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .contracts import (
    ContentResponse,
    InvalidLimitError,
    InvalidNodeError,
    InvalidSelectionError,
    ResourceResponse,
    SelectionResponse,
    SourceDisabledError,
    TreeResponse,
)
from .nodes import InvalidNode, MAX_TOKEN_CHARS
from .selection import (
    SELECTION_HEADER,
    InvalidSelection,
    Selection,
    parse_selection,
)
from .service import (
    DEFAULT_PREVIEW_ROWS,
    MAX_PREVIEW_ROWS,
    InventoryService,
    SourceDisabled,
)

#: Applied to every response this router produces, success or failure.
NO_STORE = {
    "Cache-Control": "no-store, private",
    "Vary": SELECTION_HEADER,
}

ServiceProvider = Callable[[Request], InventoryService]


def _reject(model: BaseModel, status_code: int) -> JSONResponse:
    """A rejection body that echoes nothing the client submitted."""
    return JSONResponse(
        status_code=status_code,
        content=model.model_dump(by_alias=True),
        headers=NO_STORE,
    )


def _bound(raw: str) -> int:
    """The row bound, or a raise. Never a silent clamp: that hides the caller's bug."""
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("limit is not an integer") from exc
    if value < 1 or value > MAX_PREVIEW_ROWS:
        raise ValueError("limit out of range")
    return value


def build_inventory_router(
    get_service: ServiceProvider,
    *,
    prefix: str = "/api/inventory",
    tags: list[str] | None = None,
) -> APIRouter:
    """Build the router. The service is resolved per request, never captured.

    Args:
        get_service: Reads the composed service off the request, so the host
            keeps ownership of lifespan and configuration.
        prefix: Where the host mounts these routes.
        tags: OpenAPI tags.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["data-inventory"])

    def _selection(request: Request, service: InventoryService) -> Selection:
        return parse_selection(
            request.headers.get(SELECTION_HEADER),
            allowed=service.registry.source_ids(),
        )

    def _token(node: str) -> str:
        # Length is checked before decoding, so a megabyte of base64 never
        # reaches the codec.
        if len(node) > MAX_TOKEN_CHARS:
            raise InvalidNode("token length")
        return node

    @router.get("/selection", response_model=SelectionResponse)
    async def selection(request: Request, response: Response):
        """Every selectable source, and whether this request has it switched on."""
        response.headers.update(NO_STORE)
        service = get_service(request)
        try:
            chosen = _selection(request, service)
        except InvalidSelection:
            return _reject(InvalidSelectionError(), 400)
        return service.selection_report(chosen)

    @router.get("/tree", response_model=TreeResponse)
    async def tree(request: Request, response: Response, node: str = ""):
        """Expand the root, or one use case. Never probes a source."""
        response.headers.update(NO_STORE)
        service = get_service(request)
        try:
            chosen = _selection(request, service)
        except InvalidSelection:
            return _reject(InvalidSelectionError(), 400)
        try:
            return await service.tree(_token(node), chosen)
        except InvalidNode:
            return _reject(InvalidNodeError(), 400)

    @router.get("/resource", response_model=ResourceResponse)
    async def resource(request: Request, response: Response, node: str = ""):
        """One source's metadata, read now."""
        response.headers.update(NO_STORE)
        service = get_service(request)
        try:
            chosen = _selection(request, service)
        except InvalidSelection:
            return _reject(InvalidSelectionError(), 400)
        try:
            return await service.resource(_token(node), chosen)
        except InvalidNode:
            return _reject(InvalidNodeError(), 400)
        except SourceDisabled:
            return _reject(SourceDisabledError(), 409)

    @router.get("/content", response_model=ContentResponse)
    async def content(
        request: Request,
        response: Response,
        node: str = "",
        limit: str = str(DEFAULT_PREVIEW_ROWS),
    ):
        """One source's bounded preview, read now."""
        response.headers.update(NO_STORE)
        service = get_service(request)
        try:
            chosen = _selection(request, service)
        except InvalidSelection:
            return _reject(InvalidSelectionError(), 400)
        try:
            bound = _bound(limit)
        except ValueError:
            return _reject(InvalidLimitError(minimum=1, maximum=MAX_PREVIEW_ROWS), 422)
        try:
            return await service.content(_token(node), chosen, limit=bound)
        except InvalidNode:
            return _reject(InvalidNodeError(), 400)
        except SourceDisabled:
            return _reject(SourceDisabledError(), 409)

    return router


__all__ = ["NO_STORE", "ServiceProvider", "build_inventory_router"]
