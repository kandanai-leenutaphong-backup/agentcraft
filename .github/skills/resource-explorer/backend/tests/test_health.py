"""F6 — health: local questions only, and neither answer names a resource."""

from __future__ import annotations

from pathlib import Path

from conftest import client, make_settings

from resource_explorer_api import settings as settings_module
from resource_explorer_api.app import create_app


class ExplodingDiscoverer:
    """Registration is free; enumerating is not. Liveness must never enumerate."""

    service = "estate"
    levels = ("resource_group",)

    def child_level(self, level: str) -> str | None:
        return None

    async def discover(self, *args, **kwargs):
        raise AssertionError("liveness reached the discover plane")


class ExplodingRegistry:
    def services(self):
        return ("estate",)

    def get(self, service: str):
        return ExplodingDiscoverer()


class ExplodingReader:
    def __getattr__(self, name: str):
        raise AssertionError("liveness reached the content plane")


class ExplodingAccess:
    discoverers = ExplodingRegistry()
    arm = ExplodingReader()
    properties = ExplodingReader()
    blob = ExplodingReader()
    cosmos = ExplodingReader()
    kusto = ExplodingReader()
    search = ExplodingReader()
    logs = ExplodingReader()


async def test_liveness_makes_no_discovery_call() -> None:
    app = create_app(make_settings(), access=ExplodingAccess())
    async with client(app) as http:
        response = await http.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}


async def test_readiness_is_503_static_until_the_spa_is_built() -> None:
    app = create_app(make_settings(static_dir=Path("/nonexistent-static")))
    async with client(app) as http:
        response = await http.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not-ready", "reason": "static"}


async def test_readiness_is_200_once_the_spa_is_on_disk(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    app = create_app(make_settings(static_dir=tmp_path))
    async with client(app) as http:
        response = await http.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_readiness_is_503_settings_when_the_environment_will_not_parse(
    monkeypatch, tmp_path: Path
) -> None:
    def explode(*args, **kwargs):
        raise ValueError("unparseable environment")

    monkeypatch.setattr(settings_module.Settings, "from_env", classmethod(explode))
    app = create_app()
    async with client(app) as http:
        response = await http.get("/health/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "not-ready", "reason": "settings"}


async def test_neither_health_body_names_a_resource(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    app = create_app(make_settings(static_dir=tmp_path))
    async with client(app) as http:
        bodies = [
            (await http.get("/health/live")).text,
            (await http.get("/health/ready")).text,
        ]
    for body in bodies:
        assert "fixture-subscription" not in body and "rg-fixture" not in body
