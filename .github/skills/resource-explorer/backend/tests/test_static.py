"""F7 — static: assets resolve per request, and nothing escapes the directory."""

from __future__ import annotations

from pathlib import Path

from conftest import PRINCIPAL, client, make_settings

from resource_explorer_api.app import PLACEHOLDER_HTML, create_app


def build_dist(root: Path) -> Path:
    dist = root / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>real</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("export const ok = 1;\n", encoding="utf-8")
    (root / "secret.txt").write_text("not servable\n", encoding="utf-8")
    return dist


async def test_an_asset_is_served(tmp_path: Path) -> None:
    app = create_app(make_settings(static_dir=build_dist(tmp_path)))
    async with client(app) as http:
        response = await http.get("/assets/app.js", headers=PRINCIPAL)
    assert response.status_code == 200
    assert "export const ok" in response.text
    assert response.headers["cache-control"] == "no-store, private"


async def test_a_traversal_is_404_and_not_a_file(tmp_path: Path) -> None:
    app = create_app(make_settings(static_dir=build_dist(tmp_path)))
    async with client(app) as http:
        response = await http.get("/assets/../secret.txt", headers=PRINCIPAL)
    assert response.status_code == 404
    assert "not servable" not in response.text


async def test_an_absent_asset_is_404(tmp_path: Path) -> None:
    app = create_app(make_settings(static_dir=build_dist(tmp_path)))
    async with client(app) as http:
        response = await http.get("/assets/missing.js", headers=PRINCIPAL)
    assert response.status_code == 404


async def test_an_asset_built_after_startup_is_still_served(tmp_path: Path) -> None:
    """Per-request resolution: a start-time mount 404s until a restart."""
    dist = build_dist(tmp_path)
    app = create_app(make_settings(static_dir=dist))
    async with client(app) as http:
        before = await http.get("/assets/late.js", headers=PRINCIPAL)
        (dist / "assets" / "late.js").write_text("// built later\n", encoding="utf-8")
        after = await http.get("/assets/late.js", headers=PRINCIPAL)
    assert before.status_code == 404
    assert after.status_code == 200


async def test_the_index_is_a_placeholder_until_the_spa_exists(tmp_path: Path) -> None:
    app = create_app(make_settings(static_dir=tmp_path / "absent"))
    async with client(app) as http:
        response = await http.get("/", headers=PRINCIPAL)
    assert response.status_code == 200
    assert response.text == PLACEHOLDER_HTML


async def test_the_index_is_the_spa_once_it_exists(tmp_path: Path) -> None:
    app = create_app(make_settings(static_dir=build_dist(tmp_path)))
    async with client(app) as http:
        response = await http.get("/", headers=PRINCIPAL)
    assert response.status_code == 200
    assert "real" in response.text
