"""Estate-wide search: hits are addressable, and the term is bounded.

A hit that a client cannot open is a dead end, so every hit carries a node id
the tree accepts. The term bound is here because the search box is the one
place a human's free text reaches a query builder, and the refusal has to be
a value the client can render, not a stack trace.
"""

from __future__ import annotations

import pytest
from conftest import GROUP, PRINCIPAL, client, make_service, make_settings

from resource_explorer_api.app import create_app
from resource_explorer_api.settings import MAX_SEARCH_HITS, MAX_SEARCH_TERM_CHARS
from resource_explorer_api.tree import InvalidQuery


@pytest.fixture
def service():
    return make_service()


async def test_a_search_finds_resources_across_groups(service) -> None:
    response = await service.search("cosmos")
    assert response.status == "ok"
    assert {hit.label for hit in response.hits} == {"cosmos-fixture", "cosmos-forbidden"}
    assert all(hit.kind == "resource" for hit in response.hits)
    assert all(hit.resource_group == GROUP for hit in response.hits)
    assert response.query == "cosmos"
    assert response.fixtures is True


async def test_a_search_finds_resource_groups_too(service) -> None:
    response = await service.search(GROUP)
    kinds = {hit.kind for hit in response.hits}
    assert "resource_group" in kinds


async def test_every_hit_is_addressable(service) -> None:
    response = await service.search("fixture")
    assert response.hits
    for hit in response.hits:
        expanded = await service.expand(hit.node)
        assert expanded.status in ("ok", "empty", "forbidden", "unreachable", "unavailable", "unconfigured")
        assert expanded.node == hit.node


async def test_a_search_that_matches_nothing_is_empty_not_an_error(service) -> None:
    response = await service.search("no-such-thing-anywhere")
    assert response.status == "empty"
    assert response.hits == []
    assert response.error is None


async def test_a_search_reports_which_field_matched(service) -> None:
    response = await service.search("Microsoft.Kusto")
    assert response.hits
    assert {hit.matched_in for hit in response.hits} == {"type"}


async def test_the_hit_limit_is_honoured_and_clamped(service) -> None:
    response = await service.search("fixture", 1)
    assert len(response.hits) <= 1
    assert response.truncated is True
    wide = await service.search("fixture", MAX_SEARCH_HITS * 10)
    assert len(wide.hits) <= MAX_SEARCH_HITS


@pytest.mark.parametrize("term", ["", "   ", "x" * (MAX_SEARCH_TERM_CHARS + 1)])
async def test_an_unusable_term_is_refused(service, term) -> None:
    with pytest.raises(InvalidQuery):
        await service.search(term)


async def test_an_unconfigured_estate_says_so_rather_than_searching() -> None:
    from azdata import AzureDataConfig

    bare = make_service(fake_discovery=False, azure=AzureDataConfig())
    response = await bare.search("anything")
    assert response.status == "unconfigured"
    assert "AZDATA_SUBSCRIPTION_ID" in (response.error or "")


# -- over the wire --------------------------------------------------------


async def test_the_route_answers_200_with_hits() -> None:
    app = create_app(make_settings())
    async with client(app) as http:
        response = await http.get("/api/search", params={"q": "cosmos"}, headers=PRINCIPAL)
    assert response.status_code == 200
    body = response.json()
    assert body["schemaVersion"] == 1
    assert body["query"] == "cosmos"
    assert body["hits"]
    assert response.headers["cache-control"] == "no-store, private"


async def test_the_route_refuses_an_empty_term_without_echoing_it() -> None:
    app = create_app(make_settings())
    async with client(app) as http:
        response = await http.get("/api/search", params={"q": "   "}, headers=PRINCIPAL)
    assert response.status_code == 400
    assert response.json() == {"error": "invalid_query", "schemaVersion": 1}


async def test_the_route_refuses_an_out_of_range_limit() -> None:
    app = create_app(make_settings())
    async with client(app) as http:
        response = await http.get(
            "/api/search", params={"q": "a", "limit": 0}, headers=PRINCIPAL
        )
    assert response.status_code == 422


async def test_the_route_needs_a_principal() -> None:
    app = create_app(make_settings())
    async with client(app) as http:
        response = await http.get("/api/search", params={"q": "cosmos"})
    assert response.status_code == 401
    assert response.content == b""
