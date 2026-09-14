"""F3 — the guard: fail closed, before routing, and unbypassable in Azure."""

from __future__ import annotations

import pytest
from conftest import PRINCIPAL, client, make_settings

from resource_explorer_api.app import create_app
from resource_explorer_api.settings import Settings

PROTECTED = ["/api/tree", "/", "/assets/index-abc123.js", "/no/such/path"]


@pytest.mark.parametrize("path", PROTECTED)
async def test_an_anonymous_request_is_401_with_an_empty_body(path: str) -> None:
    app = create_app(make_settings())
    async with client(app) as http:
        response = await http.get(path)
    assert response.status_code == 401
    assert response.content == b""
    assert response.headers["cache-control"] == "no-store, private"


async def test_an_unknown_path_does_not_confirm_itself_to_an_anonymous_caller() -> None:
    """404 is information. An anonymous prober learns nothing from a 401."""
    app = create_app(make_settings())
    async with client(app) as http:
        anonymous = await http.get("/api/definitely-not-a-route")
        authorized = await http.get("/api/definitely-not-a-route", headers=PRINCIPAL)
    assert anonymous.status_code == 401
    assert authorized.status_code == 404


@pytest.mark.parametrize(
    "header",
    ["X-MS-CLIENT-PRINCIPAL", "X-MS-CLIENT-PRINCIPAL-ID", "x-ms-client-principal-id"],
)
async def test_a_principal_header_passes(header: str) -> None:
    app = create_app(make_settings())
    async with client(app) as http:
        response = await http.get("/api/tree", headers={header: "operator"})
    assert response.status_code == 200


async def test_an_empty_principal_header_does_not_pass() -> None:
    app = create_app(make_settings())
    async with client(app) as http:
        response = await http.get("/api/tree", headers={"X-MS-CLIENT-PRINCIPAL-ID": ""})
    assert response.status_code == 401


async def test_the_dev_bypass_opens_the_door_locally() -> None:
    settings = Settings.from_env(
        {"RESOURCE_EXPLORER_DEV_PRINCIPAL": "1", "RESOURCE_EXPLORER_FAKE_DISCOVERY": "1"}
    )
    assert settings.dev_principal
    async with client(create_app(settings)) as http:
        response = await http.get("/api/tree")
    assert response.status_code == 200


async def test_the_dev_bypass_cannot_exist_in_azure() -> None:
    """The marker variable wins over the flag, in code, not in a script."""
    settings = Settings.from_env(
        {
            "RESOURCE_EXPLORER_DEV_PRINCIPAL": "1",
            "RESOURCE_EXPLORER_FAKE_DISCOVERY": "1",
            "CONTAINER_APP_NAME": "ca-resource-explorer",
        }
    )
    assert settings.running_in_azure
    assert not settings.dev_principal
    async with client(create_app(settings)) as http:
        response = await http.get("/api/tree")
    assert response.status_code == 401


async def test_health_answers_anonymously() -> None:
    app = create_app(make_settings())
    async with client(app) as http:
        live = await http.get("/health/live")
        ready = await http.get("/health/ready")
    assert live.status_code == 200
    assert ready.status_code in (200, 503)
