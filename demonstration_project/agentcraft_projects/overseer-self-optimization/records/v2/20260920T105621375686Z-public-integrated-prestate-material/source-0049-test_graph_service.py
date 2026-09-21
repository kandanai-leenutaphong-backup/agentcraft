"""Contract tests for the read-only Gremlin graph service.

Cosmos is never contacted: the driver client is replaced with scripted fakes so every
connection fault is deterministic.
"""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import Any
from unittest import mock

from fastapi import HTTPException
from azdata import ConnectorConfig, Limits, Policy, ResourceAddress, connect

from app.cybereye.backend.api.graph import graph_node
from app.cybereye.backend.data.graph import (
    CACHE_SECONDS, GraphNotFound, GraphService, GraphUnavailable,
    _apply_window, _edge, _node, _timestamp, _window_count,
)


class FakeClient:
    """Answers a fixed script, optionally failing the first N submits."""

    def __init__(self, rows: list[Any], failures: int = 0, error: str = "Connection was already closed.") -> None:
        self.rows = rows
        self.failures = failures
        self.error = error
        self.submits = 0
        self.closed = False

    def submit(self, script: str, bindings: dict[str, Any] | None = None, **options: Any) -> Any:
        self.submits += 1
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError(self.error)
        return mock.Mock(all=lambda: mock.Mock(result=lambda timeout=None: self.rows))

    def close(self) -> None:
        self.closed = True


def service(clients: list[FakeClient], *, credential: Any = None) -> GraphService:
    queue = list(clients)
    connector = connect("gremlin", ConnectorConfig("wss://fixture.gremlin.cosmos.azure.com",
        ResourceAddress({"database": "db", "container": "graph"}), ("fixture.gremlin.cosmos.azure.com",),
        credential_kind="readonly_key"),
        credential=credential if credential is not None else SimpleNamespace(get_token=mock.Mock()),
        gremlin_readonly_key_provider=mock.AsyncMock(return_value="synthetic-readonly-key"),
        policy=Policy("fixture", {"query"}, limits=Limits(max_items=2500, max_attempts=1)))

    async def query(request):
        client = queue.pop(0) if queue else clients[-1]
        with mock.patch("gremlin_python.driver.client.Client", return_value=client):
            return await connector.query(request)

    return GraphService(account="acct", resource_group="rg",
                        connector=SimpleNamespace(query=query, aclose=connector.aclose))


class FailureTests(unittest.IsolatedAsyncioTestCase):
    async def test_a_query_fault_is_not_retried_by_the_host(self) -> None:
        broken = FakeClient([1], failures=5, error="GraphSyntaxException: bad step")
        graph = service([broken, FakeClient([1])])
        with self.assertRaises(GraphUnavailable):
            await graph._submit("g.V().count()")
        self.assertEqual(broken.submits, 1)
        self.assertTrue(broken.closed)

    async def test_status_reports_unavailable_without_raising_and_does_not_cache_the_failure(self) -> None:
        graph = service([FakeClient([1], failures=9), FakeClient([1], failures=9)])
        report = await graph.status()
        self.assertFalse(report["available"])
        self.assertEqual("gremlin_connection_closed", report["detail"])
        self.assertFalse((await graph.status())["available"], "a failed status must retry")

    async def test_an_unconfigured_service_says_so_instead_of_dialling(self) -> None:
        graph = GraphService()
        graph.account = ""
        self.assertFalse(graph.configured)
        self.assertFalse((await graph.status())["available"])


class MissingNodeTests(unittest.IsolatedAsyncioTestCase):
    async def test_successful_empty_lookup_is_not_an_outage(self) -> None:
        graph = service([FakeClient([])])
        with self.assertRaises(GraphNotFound):
            (await graph.neighbourhood("missing"))
        with self.assertRaises(GraphNotFound):
            await graph.neighbourhood("missing")

    async def test_node_route_maps_absence_to_404(self) -> None:
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph=service([FakeClient([])]))))
        with self.assertRaises(HTTPException) as caught:
            await graph_node(request, "missing")
        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail, "unknown graph node")

    async def test_node_route_keeps_real_outages_at_503(self) -> None:
        graph = service([FakeClient([], failures=9), FakeClient([], failures=9)])
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(graph=graph)))
        with self.assertRaises(HTTPException) as caught:
            await graph_node(request, "missing")
        self.assertEqual(caught.exception.status_code, 503)


class CachingTests(unittest.IsolatedAsyncioTestCase):
    async def test_repeat_calls_inside_the_window_do_not_hit_cosmos(self) -> None:
        client = FakeClient([3])
        graph = service([client])
        self.assertEqual((await graph.status())["vertices"], 3)
        self.assertEqual((await graph.status())["vertices"], 3)
        self.assertEqual(client.submits, 2, "one vertex count and one edge count, then cached")

    def test_the_cache_window_is_bounded(self) -> None:
        self.assertGreater(CACHE_SECONDS, 0)
        self.assertLessEqual(CACHE_SECONDS, 600)


class WindowTests(unittest.IsolatedAsyncioTestCase):
    def slice(self) -> dict:
        return {
            "nodes": [],
            "edges": [
                {"id": "s1", "kind": "structural", "event_count": 0, "buckets": {}},
                {"id": "e1", "kind": "event", "event_count": 95,
                 "buckets": {"2026-08-13T02:30": 44, "2026-08-13T02:45": 2, "2026-08-13T03:00": 49}},
                {"id": "e2", "kind": "event", "event_count": 7,
                 "buckets": {"2026-08-12T12:00": 7}},
            ],
        }

    def test_no_window_shows_the_timeless_layer_alone(self) -> None:
        result = _apply_window(self.slice(), "", "")
        self.assertEqual([edge["id"] for edge in result["edges"]], ["s1"])
        self.assertEqual(result["window"], {"start": "", "end": "", "bucket_minutes": 15})

    def test_a_window_keeps_structure_and_adds_only_edges_that_fired_in_it(self) -> None:
        result = _apply_window(self.slice(), "2026-08-13T02:30", "2026-08-13T03:00")
        self.assertEqual([edge["id"] for edge in result["edges"]], ["s1", "e1"])

    def test_an_event_edge_is_rescored_to_the_window_not_its_lifetime_total(self) -> None:
        result = _apply_window(self.slice(), "2026-08-13T02:30", "2026-08-13T02:45")
        scoped = next(edge for edge in result["edges"] if edge["id"] == "e1")
        self.assertEqual(scoped["event_count"], 46)
        self.assertTrue(scoped["window_scoped"])

    def test_a_structural_edge_is_never_rescored_or_dropped_by_a_window(self) -> None:
        for start, end in [("", ""), ("2026-08-13T02:30", "2026-08-13T03:00"),
                           ("2030-01-01T00:00", "2030-01-02T00:00")]:
            edges = _apply_window(self.slice(), start, end)["edges"]
            structural = [edge for edge in edges if edge["kind"] == "structural"]
            self.assertEqual(len(structural), 1, (start, end))
            self.assertNotIn("window_scoped", structural[0])

    def test_a_window_with_no_activity_shows_structure_only(self) -> None:
        result = _apply_window(self.slice(), "2030-01-01T00:00", "2030-01-02T00:00")
        self.assertEqual([edge["id"] for edge in result["edges"]], ["s1"])

    def test_bucket_counting_is_inclusive_of_both_boundary_buckets(self) -> None:
        buckets = {"2026-08-13T02:30": 1, "2026-08-13T02:45": 2, "2026-08-13T03:00": 4}
        self.assertEqual(_window_count(buckets, "2026-08-13T02:30", "2026-08-13T03:00"), 7)
        self.assertEqual(_window_count(buckets, "2026-08-13T02:45", "2026-08-13T02:45"), 2)
        self.assertEqual(_window_count(buckets, "", ""), 7)


class ExtentTests(unittest.IsolatedAsyncioTestCase):
    def test_the_float_sentinel_from_an_empty_min_never_reaches_the_client(self) -> None:
        for sentinel in [[1.7976931348623157e+308], [-1.7976931348623157e+308], [], [None], [0]]:
            self.assertEqual(_timestamp(sentinel), "", sentinel)

    def test_a_real_timestamp_passes_through(self) -> None:
        self.assertEqual(_timestamp(["2026-08-13T02:33:18Z"]), "2026-08-13T02:33:18Z")


class ShapeTests(unittest.IsolatedAsyncioTestCase):
    def test_valuemap_lists_are_unwrapped_to_scalars(self) -> None:
        node = _node({
            "id": "host|SVPMN082", "label": "Host", "pk": ["perth"],
            "name": ["SVPMN082"], "event_count": [754],
            "first_seen": ["2026-08-11T23:57:53Z"], "last_seen": ["2026-08-13T08:36:06Z"],
            "fqdns": ["a.example", "b.example"],
        })
        self.assertEqual(node["name"], "SVPMN082")
        self.assertEqual(node["event_count"], 754)
        self.assertEqual(node["properties"]["fqdns"], ["a.example", "b.example"])
        self.assertNotIn("pk", node["properties"], "the partition key is plumbing, not evidence")

    def test_edge_endpoints_come_from_the_projection_not_the_property_bag(self) -> None:
        edge = _edge({
            "e": {"id": "a--QUERIED--b", "label": "QUERIED", "kind": "event", "event_count": 647,
                  "buckets": '{"2026-08-13T02:30":647}',
                  "first_seen": "", "last_seen": "", "inV": "b", "outV": "a"},
            "from": "a", "to": "b",
        })
        self.assertEqual((edge["from"], edge["to"], edge["label"]), ("a", "b", "QUERIED"))
        self.assertEqual(edge["event_count"], 647)
        self.assertEqual(edge["kind"], "event")
        self.assertEqual(edge["buckets"], {"2026-08-13T02:30": 647})
        for plumbing in ("inV", "outV", "inVLabel", "outVLabel", "type", "kind", "buckets"):
            self.assertNotIn(plumbing, edge["properties"])

    def test_a_malformed_bucket_payload_degrades_to_empty_rather_than_raising(self) -> None:
        edge = _edge({"e": {"id": "x", "label": "QUERIED", "buckets": "not json"},
                      "from": "a", "to": "b"})
        self.assertEqual(edge["buckets"], {})
        self.assertEqual(edge["kind"], "event")

    def test_a_missing_event_count_does_not_crash_the_projection(self) -> None:
        self.assertEqual(_node({"id": "x", "label": "Host"})["event_count"], 0)
        self.assertEqual(_edge({"e": {"id": "x", "label": "QUERIED"}, "from": "a", "to": "b"})["event_count"], 0)


class BoundsTests(unittest.IsolatedAsyncioTestCase):
    async def test_search_ignores_a_term_too_short_to_be_selective(self) -> None:
        client = FakeClient([])
        graph = service([client])
        for term in ["", " ", "a"]:
            self.assertEqual((await graph.search(term)), [])
        self.assertEqual(client.submits, 0)

    async def test_neighbourhood_limit_is_clamped_to_the_declared_ceiling(self) -> None:
        client = FakeClient([{"id": "host|X", "label": "Host", "name": ["X"]}])
        graph = service([client])
        scripts: list[str] = []
        original = client.submit

        def record(script: str, bindings: dict[str, Any] | None = None, **options: Any) -> Any:
            scripts.append(script)
            return original(script, bindings, **options)

        client.submit = record  # type: ignore[method-assign]
        (await graph.neighbourhood("host|X", limit=100000))
        self.assertTrue(any("limit(220)" in script for script in scripts), scripts)


if __name__ == "__main__":
    unittest.main()


class ScriptedClient:
    """Answers each traversal from a pattern -> rows table, recording what was asked."""

    def __init__(self, table: list[tuple[str, list]]) -> None:
        self.table = table
        self.scripts: list[str] = []
        self.closed = False
        self.failure = ""

    def submit(self, script: str, bindings: dict | None = None, **options: Any) -> Any:
        self.scripts.append(script)
        if self.failure:
            raise RuntimeError(self.failure)
        rows: list = []
        for marker, value in self.table:
            if marker in script:
                rows = value
                break
        return mock.Mock(all=lambda: mock.Mock(result=lambda timeout=None: rows))

    def close(self) -> None:
        self.closed = True


def vertex(node_id: str, label: str = "Host") -> dict:
    return {"id": node_id, "label": label, "name": [node_id.split("|")[-1]], "event_count": [1]}


def edge_row(edge_id: str, source: str, target: str, kind: str = "event") -> dict:
    return {"e": {"id": edge_id, "label": "AUTHENTICATED_TO", "kind": kind, "event_count": 1,
                  "buckets": '{"2026-08-13T02:30":1}'},
            "from": source, "to": target}


def seen_node(node_id: str, label: str = "Host") -> dict:
    """A vertex as the service hands it on, not as Gremlin returns it."""
    from app.cybereye.backend.data.graph import _node

    return _node(vertex(node_id, label))


def seen_edge(edge_id: str, source: str, target: str, kind: str = "event") -> dict:
    from app.cybereye.backend.data.graph import _edge

    return _edge(edge_row(edge_id, source, target, kind))


class DepthTests(unittest.IsolatedAsyncioTestCase):
    def graph_with(self, table: list[tuple[str, list]]) -> tuple[GraphService, ScriptedClient]:
        client = ScriptedClient(table)
        graph = service([client])
        return graph, client

    async def test_depth_is_clamped_to_the_declared_ceiling(self) -> None:
        from app.cybereye.backend.data.graph import MAX_DEPTH

        graph, client = self.graph_with([('g.V("host|A").valueMap', [vertex("host|A")])])
        for requested in (0, -5, 99):
            graph._cache.invalidate()
            (await graph.neighbourhood("host|A", depth=requested))
        hops = [script for script in client.scripts if "times(" in script]
        self.assertTrue(all(f"times({MAX_DEPTH})" in s or "times(1)" in s for s in hops), hops)
        self.assertNotIn("times(0)", " ".join(client.scripts))
        self.assertNotIn("times(99)", " ".join(client.scripts))

    async def test_one_hop_asks_for_direct_neighbours_and_never_repeats(self) -> None:
        graph, client = self.graph_with([
            ('g.V("host|A").valueMap', [vertex("host|A")]),
            ("both().dedup()", [vertex("identity|b", "Identity")]),
            ("bothE()", [edge_row("e1", "host|A", "identity|b", "structural")]),
        ])
        result = (await graph.neighbourhood("host|A", depth=1))
        self.assertEqual(result["depth"], 1)
        self.assertNotIn("repeat(", " ".join(client.scripts))
        self.assertEqual([node["id"] for node in result["nodes"]], ["host|A", "identity|b"])

    async def test_multi_hop_reuses_the_cached_core_edge_set_instead_of_re_traversing(self) -> None:
        graph, client = self.graph_with([
            ('g.V("host|A").valueMap', [vertex("host|A")]),
            ("repeat(", [vertex("identity|b", "Identity"), vertex("host|c")]),
            ('hasLabel("Host","Identity"', [edge_row("core1", "identity|b", "host|c", "structural")]),
            ("bothE()", [edge_row("direct", "host|A", "identity|b", "structural")]),
        ])
        result = (await graph.neighbourhood("host|A", depth=2))
        self.assertEqual(result["depth"], 2)
        self.assertEqual({edge["id"] for edge in result["edges"]}, {"direct", "core1"})
        # The expensive repeat traversal runs once for vertices, never again for edges.
        self.assertEqual(sum("repeat(" in script for script in client.scripts), 1)

    async def test_a_multi_hop_view_still_hides_event_edges_until_a_window_is_chosen(self) -> None:
        table = [
            ('g.V("host|A").valueMap', [vertex("host|A")]),
            ("repeat(", [vertex("identity|b", "Identity"), vertex("host|c")]),
            ('hasLabel("Host","Identity"', [edge_row("core1", "identity|b", "host|c")]),
            ("bothE()", [edge_row("direct", "host|A", "identity|b")]),
        ]
        graph, _ = self.graph_with(table)
        self.assertEqual((await graph.neighbourhood("host|A", depth=2))["edges"], [])
        graph, _ = self.graph_with(table)
        windowed = (await graph.neighbourhood("host|A", depth=2, start="2026-08-13T02:30", end="2026-08-13T02:30"))
        self.assertEqual({edge["id"] for edge in windowed["edges"]}, {"direct", "core1"})

    async def test_the_focus_is_never_listed_twice(self) -> None:
        graph, _ = self.graph_with([
            ('g.V("host|A").valueMap', [vertex("host|A")]),
            ("repeat(", [vertex("host|A"), vertex("identity|b", "Identity")]),
        ])
        ids = [node["id"] for node in (await graph.neighbourhood("host|A", depth=2))["nodes"]]
        self.assertEqual(ids.count("host|A"), 1)

    async def test_an_edge_touching_a_node_outside_the_reach_is_dropped(self) -> None:
        graph, _ = self.graph_with([
            ('g.V("host|A").valueMap', [vertex("host|A")]),
            ("repeat(", [vertex("identity|b", "Identity")]),
            ('hasLabel("Host","Identity"', [edge_row("stray", "identity|b", "host|elsewhere", "structural")]),
            ("bothE()", []),
        ])
        self.assertEqual((await graph.neighbourhood("host|A", depth=2))["edges"], [])

    async def test_an_unknown_focus_is_reported_rather_than_returning_an_empty_graph(self) -> None:
        graph, _ = self.graph_with([("g.V(", [])])
        with self.assertRaises(GraphNotFound) as caught:
            (await graph.neighbourhood("host|nope"))
        self.assertEqual("unknown graph node", str(caught.exception))


class SelectionTests(unittest.IsolatedAsyncioTestCase):
    """Several entities at once: the union of their reaches, and where those reaches meet."""

    def graph_with(self, table: list[tuple[str, list]]) -> GraphService:
        return service([ScriptedClient(table)])

    def meeting_graph(self) -> GraphService:
        """A and B both touch M; each also has a neighbour the other never sees."""
        client = ScriptedClient([])
        graph = service([client])
        reach = {"host|A": [seen_node("host|M"), seen_node("host|onlyA")],
                 "host|B": [seen_node("host|M"), seen_node("host|onlyB")]}
        graph._nodes = mock.AsyncMock(side_effect = lambda script, bindings=None: (  # type: ignore[method-assign]
            [seen_node(bindings["vid"])] if bindings and bindings.get("vid") in reach else []))
        graph._reach = mock.AsyncMock(side_effect = lambda node_id, hops, bounded: reach[node_id])  # type: ignore[method-assign]
        graph._direct_edges = mock.AsyncMock(side_effect = lambda node_id, bounded: [  # type: ignore[method-assign]
            seen_edge(f"{node_id}-M", node_id, "host|M", "structural")])
        graph._edges_between = mock.AsyncMock(side_effect = lambda node_id, others: [])  # type: ignore[method-assign]
        return graph

    async def test_a_node_reached_from_two_selections_is_reported_as_shared(self) -> None:
        result = (await self.meeting_graph().selection(["host|A", "host|B"], depth=1))
        self.assertEqual(result["shared"], ["host|M"])
        self.assertEqual(result["selected"], ["host|A", "host|B"])

    async def test_a_node_only_one_selection_reaches_is_not_shared(self) -> None:
        result = (await self.meeting_graph().selection(["host|A", "host|B"], depth=1, scope="all"))
        self.assertNotIn("host|onlyA", result["shared"])
        self.assertNotIn("host|onlyB", result["shared"])
        self.assertEqual({node["id"] for node in result["nodes"]},
                         {"host|A", "host|B", "host|M", "host|onlyA", "host|onlyB"})

    async def test_a_selection_is_never_shared_with_itself(self) -> None:
        graph = self.meeting_graph()
        graph._reach = mock.AsyncMock(side_effect = lambda node_id, hops, bounded: [  # type: ignore[method-assign]
            seen_node("host|B" if node_id == "host|A" else "host|A")])
        # Each reaches the other, so both are reached twice, yet neither is a meeting point.
        self.assertEqual((await graph.selection(["host|A", "host|B"], depth=1))["shared"], [])

    async def test_one_selection_alone_can_never_produce_a_meeting_point(self) -> None:
        self.assertEqual((await self.meeting_graph().selection(["host|A"], depth=1))["shared"], [])

    async def test_a_repeated_id_is_collapsed_rather_than_faking_a_meeting(self) -> None:
        result = (await self.meeting_graph().selection(["host|A", "host|A", "host|A"], depth=1))
        self.assertEqual(result["selected"], ["host|A"])
        self.assertEqual(result["shared"], [])

    async def test_the_selection_size_is_clamped_to_the_declared_ceiling(self) -> None:
        from app.cybereye.backend.data.graph import MAX_SELECTION

        graph = self.meeting_graph()
        seen: list[str] = []
        graph._reach = mock.AsyncMock(side_effect = lambda node_id, hops, bounded: seen.append(node_id) or [])  # type: ignore[method-assign,func-returns-value]
        graph._nodes = mock.AsyncMock(side_effect = lambda script, bindings=None: [seen_node(bindings["vid"])])  # type: ignore[method-assign]
        (await graph.selection([f"host|{index}" for index in range(MAX_SELECTION + 6)], depth=1))
        self.assertEqual(len(seen), MAX_SELECTION)

    async def test_depth_is_clamped_like_any_other_traversal(self) -> None:
        from app.cybereye.backend.data.graph import MAX_DEPTH

        graph, asked = self.meeting_graph(), []
        graph._reach = mock.AsyncMock(side_effect = lambda node_id, hops, bounded: asked.append(hops) or [])  # type: ignore[method-assign,func-returns-value]
        for requested in (0, -3, 99):
            graph._cache.invalidate()
            (await graph.selection(["host|A"], depth=requested))
        self.assertEqual(asked, [1, 1, MAX_DEPTH])

    async def test_an_empty_selection_is_refused_before_dialling_cosmos(self) -> None:
        client = ScriptedClient([])
        with self.assertRaises(GraphUnavailable):
            (await service([client]).selection(["", "   "]))
        self.assertEqual(client.scripts, [])

    async def test_a_selection_of_entities_that_do_not_exist_is_reported(self) -> None:
        graph = self.graph_with([("g.V(", [])])
        with self.assertRaises(GraphUnavailable) as caught:
            (await graph.selection(["host|nope", "host|alsonope"]))
        self.assertIn("none of the selected", str(caught.exception))

    async def test_event_edges_stay_hidden_until_a_window_is_chosen(self) -> None:
        graph = self.meeting_graph()
        graph._direct_edges = mock.AsyncMock(side_effect = lambda node_id, bounded: [  # type: ignore[method-assign]
            seen_edge(f"{node_id}-M", node_id, "host|M")])
        self.assertEqual((await graph.selection(["host|A", "host|B"], depth=1, scope="all"))["edges"], [])
        graph._cache.invalidate()
        windowed = (await graph.selection(["host|A", "host|B"], depth=1, scope="all",
                                   start="2026-08-13T02:30", end="2026-08-13T02:30"))
        self.assertEqual(len(windowed["edges"]), 2)

    async def test_an_edge_reaching_outside_the_selected_union_is_dropped(self) -> None:
        graph = self.meeting_graph()
        graph._direct_edges = mock.AsyncMock(side_effect = lambda node_id, bounded: [  # type: ignore[method-assign]
            seen_edge(f"{node_id}-stray", node_id, "host|elsewhere", "structural")])
        self.assertEqual((await graph.selection(["host|A", "host|B"], depth=1, scope="all"))["edges"], [])


class ScopeTests(unittest.IsolatedAsyncioTestCase):
    """`scope` decides how much of a selection reaches the canvas."""

    def graph(self) -> GraphService:
        return SelectionTests().meeting_graph()

    async def test_only_shows_the_picks_and_the_relationships_between_them(self) -> None:
        graph = self.graph()
        graph._edges_between = mock.AsyncMock(side_effect = lambda node_id, others: (  # type: ignore[method-assign]
            [seen_edge("A-B", "host|A", "host|B", "structural")] if node_id == "host|A" else []))
        result = (await graph.selection(["host|A", "host|B"], depth=1, scope="only"))
        self.assertEqual({node["id"] for node in result["nodes"]}, {"host|A", "host|B"})
        self.assertEqual([edge["id"] for edge in result["edges"]], ["A-B"])
        self.assertEqual(result["scope"], "only")

    async def test_only_is_the_default_so_a_selection_never_opens_on_the_whole_reach(self) -> None:
        self.assertEqual((await self.graph().selection(["host|A", "host|B"], depth=1))["scope"], "only")

    async def test_shared_adds_the_meeting_points_and_nothing_else(self) -> None:
        graph = self.graph()
        graph._edges_between = mock.AsyncMock(side_effect = lambda node_id, others: (  # type: ignore[method-assign]
            [seen_edge("A-B", "host|A", "host|B", "structural")] if node_id == "host|A" else []))
        result = (await graph.selection(["host|A", "host|B"], depth=1, scope="shared"))
        self.assertEqual({node["id"] for node in result["nodes"]}, {"host|A", "host|B", "host|M"})
        self.assertEqual({edge["id"] for edge in result["edges"]}, {"A-B", "host|A-M", "host|B-M"})

    async def test_all_keeps_the_whole_union(self) -> None:
        result = (await self.graph().selection(["host|A", "host|B"], depth=1, scope="all"))
        self.assertEqual({node["id"] for node in result["nodes"]},
                         {"host|A", "host|B", "host|M", "host|onlyA", "host|onlyB"})

    async def test_an_unrecognised_scope_narrows_rather_than_floods_the_canvas(self) -> None:
        result = (await self.graph().selection(["host|A", "host|B"], depth=1, scope="everything"))
        self.assertEqual(result["scope"], "only")
        self.assertEqual({node["id"] for node in result["nodes"]}, {"host|A", "host|B"})

    async def test_narrowing_does_not_rewrite_what_was_selected_or_shared(self) -> None:
        graph = self.graph()
        narrow = (await graph.selection(["host|A", "host|B"], depth=1, scope="only"))
        graph._cache.invalidate()
        wide = (await graph.selection(["host|A", "host|B"], depth=1, scope="all"))
        self.assertEqual(narrow["selected"], wide["selected"])
        self.assertEqual(narrow["shared"], wide["shared"])
        self.assertEqual(narrow["shared"], ["host|M"])

    async def test_a_pick_to_pick_edge_is_asked_for_directly_not_left_to_the_fan_out_limit(self) -> None:
        """A hub's first `limit` edges need not include the one the analyst selected against."""
        graph, asked = self.graph(), []
        graph._direct_edges = mock.AsyncMock(side_effect = lambda node_id, bounded: [])  # type: ignore[method-assign]
        graph._edges_between = mock.AsyncMock(side_effect = lambda node_id, others: (  # type: ignore[method-assign]
            asked.append((node_id, tuple(others))) or [seen_edge("A-B", "host|A", "host|B", "structural")]))
        result = (await graph.selection(["host|A", "host|B"], depth=1, scope="only"))
        self.assertEqual([edge["id"] for edge in result["edges"]], ["A-B"])
        self.assertEqual(asked, [("host|A", ("host|B",)), ("host|B", ("host|A",))])

    async def test_a_pick_that_does_not_exist_is_never_asked_to_pair_with_the_others(self) -> None:
        graph, asked = self.graph(), []
        graph._edges_between = mock.AsyncMock(side_effect = lambda node_id, others: asked.append(node_id) or [])  # type: ignore[method-assign,func-returns-value]
        (await graph.selection(["host|A", "host|B", "host|ghost"], depth=1, scope="only"))
        self.assertEqual(asked, ["host|A", "host|B"])

    async def test_a_single_pick_asks_for_no_pairing_at_all(self) -> None:
        graph, asked = self.graph(), []
        graph._edges_between = mock.AsyncMock(side_effect = lambda node_id, others: asked.append(others) or [])  # type: ignore[method-assign,func-returns-value]
        (await graph.selection(["host|A"], depth=1, scope="only"))
        self.assertEqual(asked, [[]])


class EntityIndexTests(unittest.IsolatedAsyncioTestCase):
    async def test_entities_expose_only_what_a_mention_needs(self) -> None:
        client = ScriptedClient([('project("id","label","name","event_count")', [
            {"id": "host|SVPMN082", "label": "Host", "name": "SVPMN082", "event_count": 754},
            {"id": "identity|admlrhodes", "label": "Identity", "name": "admLRhodes", "event_count": 554},
            {"id": "host|noname", "label": "Host", "name": "", "event_count": 0},
        ])])
        graph = service([client])
        entities = (await graph.entities())
        self.assertEqual([entity["name"] for entity in entities], ["SVPMN082", "admLRhodes"])
        self.assertEqual(set(entities[0]), {"id", "label", "name", "event_count"})

    def test_the_mention_vocabulary_excludes_the_dns_long_tail(self) -> None:
        from app.cybereye.backend.data.graph import CORE_LABELS, MENTION_LABELS

        self.assertNotIn("DnsName", MENTION_LABELS)
        self.assertNotIn("IpAddress", CORE_LABELS)
        self.assertIn("IpAddress", MENTION_LABELS)
        self.assertLessEqual(set(CORE_LABELS), set(MENTION_LABELS))
