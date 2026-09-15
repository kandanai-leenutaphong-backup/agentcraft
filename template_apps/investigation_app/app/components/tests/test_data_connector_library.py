"""The adopted `azdata` subset: bounds, statuses, readers and the SDK seam.

These are this repository's tests, not upstream's. Upstream ships a pytest
suite for the whole package; this covers exactly the surface that was adopted,
including the two behaviours a caller must not be surprised by — that a
`take n` Kusto sample cannot report its own truncation, and that a missing SDK
is a status rather than an exception.

Offline: every SDK is substituted through the `optional` seam.
"""

from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from typing import Any

from app.components.data_connector_library import (
    ContentBounds,
    ContentPayload,
    DEFAULT_MAX_CELL_CHARS,
    DiscoveryAbsent,
    DiscoveryUnreachable,
    GraphReader,
    GraphTarget,
    KustoReader,
    KustoTableInspector,
    MissingDependency,
    SearchReader,
    bounded_content,
    classify_discovery_failure,
    clear_overrides,
    collected_now,
    content_failure,
    normalize_rows,
    normalize_sample,
    override,
    override_missing,
    sanitize_detail,
    shape_kusto_response,
)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class Column:
    def __init__(self, name: str, kind: str = "string") -> None:
        self.column_name = name
        self.column_type = kind


class Primary:
    def __init__(self, columns: list[Column], rows: list[dict[str, Any]]) -> None:
        self.columns = columns
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


def kusto_response(columns: list[Column], rows: list[dict[str, Any]]) -> Any:
    return SimpleNamespace(primary_results=[Primary(columns, rows)])


class FakeKustoClient:
    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.calls: list[tuple[str, str]] = []

    def execute(self, database: str, query: str) -> Any:
        self.calls.append((database, query))
        for fragment, answer in self.answers.items():
            if fragment in query:
                return answer
        raise AssertionError(f"unexpected query: {query}")


def kusto_sdk(client: FakeKustoClient) -> Any:
    builder = SimpleNamespace(with_azure_token_credential=lambda uri, credential: uri)
    return SimpleNamespace(
        KustoConnectionStringBuilder=builder, KustoClient=lambda _builder: client
    )


class BoundsTests(unittest.TestCase):
    def test_bounds_clamp_rather_than_raise(self) -> None:
        """A caller that computed zero gets one row, not an exception."""
        bounds = ContentBounds(max_rows=0, max_bytes=0, timeout_secs=0)
        self.assertEqual(bounds.max_rows, 1)
        self.assertEqual(bounds.max_bytes, 1)
        self.assertGreater(bounds.timeout_secs, 0)


class ClassificationTests(unittest.TestCase):
    def test_forbidden_and_unreachable_are_distinguished(self) -> None:
        """A role grant fixes one and does nothing at all for the other."""
        forbidden = SimpleNamespace(status_code=403)
        self.assertEqual(
            classify_discovery_failure(RuntimeError("no"))[0], "unavailable"
        )
        exc = RuntimeError("denied")
        exc.status_code = 403  # type: ignore[attr-defined]
        self.assertEqual(classify_discovery_failure(exc)[0], "forbidden")
        self.assertEqual(
            classify_discovery_failure(DiscoveryUnreachable("network rule"))[0],
            "unreachable",
        )
        self.assertEqual(
            classify_discovery_failure(DiscoveryAbsent("gone"))[0], "unavailable"
        )
        self.assertEqual(
            classify_discovery_failure(MissingDependency("x", "y"))[0], "unavailable"
        )
        del forbidden

    def test_socket_failure_is_unreachable(self) -> None:
        self.assertEqual(classify_discovery_failure(OSError("refused"))[0], "unreachable")


class SanitizeTests(unittest.TestCase):
    def test_urls_are_stripped_from_free_text(self) -> None:
        text = sanitize_detail("failed against https://secret.kusto.windows.net/db")
        self.assertNotIn("secret.kusto", text)
        self.assertIn("<redacted-url>", text)

    def test_detail_is_capped(self) -> None:
        self.assertEqual(len(sanitize_detail("x" * 5000)), 500)


class NormalizeRowsTests(unittest.TestCase):
    def test_column_order_is_first_appearance(self) -> None:
        rows, columns, truncated = normalize_rows(
            [{"b": 1, "a": 2}, {"c": 3}], max_rows=10
        )
        self.assertEqual(columns, ("b", "a", "c"))
        self.assertFalse(truncated)
        self.assertEqual(len(rows), 2)

    def test_over_the_bound_is_truncated(self) -> None:
        rows, _, truncated = normalize_rows([{"a": i} for i in range(5)], max_rows=2)
        self.assertEqual(len(rows), 2)
        self.assertTrue(truncated)

    def test_long_cells_are_capped_and_bytes_are_described(self) -> None:
        rows, _, _ = normalize_rows(
            [{"long": "y" * 9000, "raw": b"\x00\x01"}], max_rows=1
        )
        cell = str(rows[0]["long"])
        self.assertTrue(cell.startswith("y" * DEFAULT_MAX_CELL_CHARS))
        self.assertIn("more characters not shown", cell)
        self.assertEqual(rows[0]["raw"], "<2 bytes>")


class ContentFidelityTests(unittest.TestCase):
    """Data is returned as the source holds it; only a bound may change it.

    `sanitize_detail` is an *error* formatter — it strips URL-shaped tokens and
    cuts at 500 characters. It was being applied to rows, so a preview of a
    proxy log answered `GET <redacted-url> HTTP/1.1` and reported
    `truncated: false`. Rewriting evidence and calling it original is worse
    than refusing to show it.
    """

    def test_a_url_in_a_row_is_not_redacted(self) -> None:
        original = "GET https://example.invalid/evidence HTTP/1.1"
        sample = normalize_sample([{"raw": original}], max_rows=1)
        self.assertEqual(sample.rows[0]["raw"], original)
        self.assertNotIn("redacted", str(sample.rows[0]["raw"]))
        # The error formatter still does redact, which is why it must not run here.
        self.assertIn("<redacted-url>", sanitize_detail(original))

    def test_a_value_under_the_cell_bound_is_untouched(self) -> None:
        """600 characters used to come back as 500, with truncated false."""
        sample = normalize_sample([{"long": "x" * 600}], max_rows=1)
        self.assertEqual(sample.rows[0]["long"], "x" * 600)
        self.assertFalse(sample.truncated)
        self.assertEqual(sample.notes, ())

    def test_a_shortened_cell_carries_its_own_marker(self) -> None:
        sample = normalize_sample([{"long": "z" * 5000}], max_rows=1)
        cell = str(sample.rows[0]["long"])
        self.assertIn("[1000 more characters not shown]", cell)
        self.assertTrue(sample.truncated)
        self.assertTrue(any("shortened" in note for note in sample.notes))

    def test_a_nested_value_renders_as_json_not_as_a_repr(self) -> None:
        sample = normalize_sample(
            [{"props": {"label": "Host", "tags": [1, 2]}}], max_rows=1
        )
        self.assertEqual(
            sample.rows[0]["props"], '{"label": "Host", "tags": [1, 2]}'
        )

    def test_the_byte_budget_bounds_a_sample_a_row_bound_cannot(self) -> None:
        """A hundred rows of a hundred wide columns is not bounded by rows."""
        wide = [{f"c{index}": "v" * 1000 for index in range(100)} for _ in range(100)]
        sample = normalize_sample(wide, max_rows=100, max_bytes=250_000)
        self.assertLess(len(sample.rows), 100)
        self.assertGreaterEqual(len(sample.rows), 1)
        self.assertLessEqual(sample.size_bytes, 250_000)
        self.assertTrue(sample.truncated)
        self.assertTrue(any("bytes" in note for note in sample.notes))

    def test_the_budget_is_counted_in_utf8_bytes_not_characters(self) -> None:
        """Three bytes per character: a character budget would keep three rows."""
        rows = [{"text": "\u4e2d" * 100} for _ in range(3)]
        sample = normalize_sample(rows, max_rows=3, max_bytes=400)
        self.assertEqual(len(sample.rows), 1)
        self.assertEqual(sample.rows[0]["text"], "\u4e2d" * 100)
        self.assertTrue(sample.truncated)

    def test_one_row_is_returned_even_when_it_alone_exceeds_the_budget(self) -> None:
        sample = normalize_sample([{"a": "x" * 3000}], max_rows=5, max_bytes=10)
        self.assertEqual(len(sample.rows), 1)

    def test_columns_beyond_the_bound_are_dropped_and_reported(self) -> None:
        row = {f"c{index}": index for index in range(20)}
        sample = normalize_sample([row], max_rows=1, max_columns=5)
        self.assertEqual(len(sample.columns), 5)
        self.assertEqual(len(sample.rows[0]), 5)
        self.assertTrue(sample.truncated)
        self.assertTrue(any("column" in note for note in sample.notes))

    def test_a_dropped_column_stays_dropped_on_later_rows(self) -> None:
        rows = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        sample = normalize_sample(rows, max_rows=2, max_columns=1)
        self.assertEqual(sample.columns, ("a",))
        self.assertEqual([set(row) for row in sample.rows], [{"a"}, {"a"}])

    def test_normalize_rows_is_normalize_sample_without_the_notes(self) -> None:
        rows, columns, truncated = normalize_rows([{"a": 1}], max_rows=1)
        sample = normalize_sample([{"a": 1}], max_rows=1)
        self.assertEqual((rows, columns, truncated), (sample.rows, sample.columns, sample.truncated))


class BoundedContentTests(unittest.TestCase):
    def test_a_raised_exception_becomes_a_status(self) -> None:
        def boom() -> tuple[ContentPayload, bool]:
            raise RuntimeError("nope")

        result = run(
            bounded_content(
                service="s", kind="k", bounds=ContentBounds(), fetch=boom
            )
        )
        self.assertEqual(result.status, "unavailable")
        self.assertIn("nope", result.detail)

    def test_an_empty_payload_is_empty_not_ok(self) -> None:
        result = run(
            bounded_content(
                service="s",
                kind="k",
                bounds=ContentBounds(),
                fetch=lambda: (ContentPayload(), False),
            )
        )
        self.assertEqual(result.status, "empty")

    def test_content_failure_carries_a_timestamp(self) -> None:
        failure = content_failure(
            service="s", kind="k", status="forbidden", detail="denied"
        )
        self.assertTrue(failure.collected_at.endswith("Z"))
        self.assertTrue(collected_now().endswith("Z"))


class KustoReaderTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_overrides()

    def test_missing_coordinates_are_unconfigured_without_an_sdk(self) -> None:
        override_missing("azure.kusto.data")
        reader = KustoReader(credential_provider=lambda: object())
        result = run(reader.rows(query_uri="", database="", table=""))
        self.assertEqual(result.status, "unconfigured")

    def test_a_table_name_outside_the_kusto_alphabet_is_refused(self) -> None:
        """Refused, not escaped: the client is never built."""
        override_missing("azure.kusto.data")
        reader = KustoReader(credential_provider=lambda: object())
        result = run(
            reader.rows(
                query_uri="https://c", database="d", table='x"] | .drop table y //'
            )
        )
        self.assertEqual(result.status, "unavailable")
        self.assertIn("not a Kusto identifier", result.detail)

    def test_a_missing_sdk_is_a_status(self) -> None:
        override_missing("azure.kusto.data")
        reader = KustoReader(credential_provider=lambda: object())
        result = run(reader.rows(query_uri="https://c", database="d", table="T"))
        self.assertEqual(result.status, "unavailable")
        self.assertIn("azure-kusto-data", result.detail)

    def test_rows_come_back_shaped_and_bounded(self) -> None:
        client = FakeKustoClient(
            {
                "take": kusto_response(
                    [Column("a"), Column("b", "int")],
                    [{"a": "one", "b": 1}, {"a": "two", "b": 2}],
                )
            }
        )
        override("azure.kusto.data", kusto_sdk(client))
        reader = KustoReader(credential_provider=lambda: object())
        result = run(
            reader.rows(
                query_uri="https://c",
                database="d",
                table="Events",
                bounds=ContentBounds(max_rows=5),
            )
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.payload.columns, ("a", "b"))
        self.assertEqual(len(result.payload.rows), 2)
        self.assertEqual(client.calls[0][1], '["Events"] | take 5')

    def test_take_n_cannot_report_its_own_truncation(self) -> None:
        """Recorded because a caller must not read `truncated: false` as "all of it".

        Upstream issues `take n`, so a full page looks identical to a table with
        exactly n rows. The inventory service compares the sample against the
        row count instead; this test pins the reader's half of that contract.
        """
        client = FakeKustoClient(
            {"take": kusto_response([Column("a")], [{"a": i} for i in range(3)])}
        )
        override("azure.kusto.data", kusto_sdk(client))
        reader = KustoReader(credential_provider=lambda: object())
        result = run(
            reader.rows(
                query_uri="https://c",
                database="d",
                table="T",
                bounds=ContentBounds(max_rows=3),
            )
        )
        self.assertFalse(result.truncated)
        self.assertEqual(len(result.payload.rows), 3)


class KustoInspectorTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_overrides()

    def test_count_and_schema_are_read_from_composed_queries(self) -> None:
        client = FakeKustoClient(
            {
                "count": kusto_response([Column("Count", "long")], [{"Count": 15520}]),
                "getschema": kusto_response(
                    [Column("ColumnName"), Column("ColumnType")],
                    [
                        {"ColumnName": "TimeGenerated", "ColumnType": "datetime"},
                        {"ColumnName": "Host", "ColumnType": "string"},
                    ],
                ),
            }
        )
        override("azure.kusto.data", kusto_sdk(client))
        inspector = KustoTableInspector(credential_provider=lambda: object())
        result, facts = run(
            inspector.facts(query_uri="https://c", database="d", table="EventsUnified")
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(facts.row_count, 15520)
        self.assertEqual(len(facts.columns), 2)
        self.assertEqual(facts.columns[0]["name"], "TimeGenerated")
        for _, query in client.calls:
            self.assertTrue(query.startswith('["EventsUnified"]'))

    def test_a_bad_table_name_is_refused_before_any_client(self) -> None:
        override_missing("azure.kusto.data")
        inspector = KustoTableInspector(credential_provider=lambda: object())
        result, facts = run(
            inspector.facts(query_uri="https://c", database="d", table="a;b")
        )
        self.assertEqual(result.status, "unavailable")
        self.assertIsNone(facts.row_count)


class SearchReaderTests(unittest.TestCase):
    def tearDown(self) -> None:
        clear_overrides()

    def test_unconfigured_before_a_client_exists(self) -> None:
        override_missing("azure.search.documents")
        reader = SearchReader(credential_provider=lambda: object())
        result = run(reader.documents(endpoint="", index=""))
        self.assertEqual(result.status, "unconfigured")
        self.assertIn("endpoint and index", result.detail)

    def test_documents_are_read_with_the_documented_match_all(self) -> None:
        captured: dict[str, Any] = {}

        class FakeSearchClient:
            def __init__(self, **kwargs: Any) -> None:
                captured["client"] = kwargs

            def search(self, **kwargs: Any) -> list[dict[str, Any]]:
                captured["search"] = kwargs
                return [{"id": "1", "@search.score": 1.0}, {"id": "2"}]

        override(
            "azure.search.documents", SimpleNamespace(SearchClient=FakeSearchClient)
        )
        reader = SearchReader(credential_provider=lambda: object())
        result = run(
            reader.documents(
                endpoint="https://s", index="i", bounds=ContentBounds(max_rows=10)
            )
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(captured["search"]["search_text"], "*")
        self.assertEqual(captured["search"]["top"], 11)
        self.assertEqual(captured["client"]["index_name"], "i")
        self.assertIn("@search.score", result.payload.columns)


class GraphReaderTests(unittest.TestCase):
    def test_an_incomplete_target_is_unconfigured_and_resolves_nothing(self) -> None:
        resolved: list[GraphTarget] = []

        def resolve(target: GraphTarget):
            resolved.append(target)
            return None

        reader = GraphReader(resolve=resolve)
        result = run(reader.elements(target=GraphTarget(account="a")))
        self.assertEqual(result.status, "unconfigured")
        self.assertEqual(resolved, [])

    def test_an_unresolvable_target_is_unconfigured(self) -> None:
        reader = GraphReader(resolve=lambda _target: None)
        result = run(
            reader.elements(target=GraphTarget(account="a", database="d", graph="g"))
        )
        self.assertEqual(result.status, "unconfigured")

    def test_elements_come_back_flat_and_report_truncation(self) -> None:
        class Source:
            def __init__(self) -> None:
                self.calls: list[tuple[str, int]] = []

            def sample(self, element: str, limit: int) -> list[dict[str, Any]]:
                self.calls.append((element, limit))
                return [{"id": str(i), "label": "Host"} for i in range(limit)]

        source = Source()
        reader = GraphReader(resolve=lambda _target: source)
        result = run(
            reader.elements(
                target=GraphTarget(account="a", database="d", graph="g"),
                element="vertices",
                bounds=ContentBounds(max_rows=4),
            )
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(len(result.payload.rows), 4)
        self.assertTrue(result.truncated)
        self.assertTrue(result.payload.notes)
        # One more than asked for, so truncation is observed and not guessed.
        self.assertEqual(source.calls, [("vertices", 5)])

    def test_a_target_is_identified_by_all_three_coordinates(self) -> None:
        """Two accounts holding the same database and graph name are not one graph."""
        one = GraphTarget(account="account-one", database="db", graph="g")
        two = GraphTarget(account="account-two", database="db", graph="g")
        self.assertNotEqual(one, two)
        self.assertTrue(one.is_complete and two.is_complete)

    def test_an_unknown_element_is_refused(self) -> None:
        reader = GraphReader(resolve=lambda _target: None)
        result = run(
            reader.elements(
                target=GraphTarget(account="a", database="d", graph="g"),
                element="everything",  # type: ignore[arg-type]
            )
        )
        self.assertEqual(result.status, "unavailable")


class ShapeTests(unittest.TestCase):
    def test_an_empty_response_shapes_to_empty_lists(self) -> None:
        shaped = shape_kusto_response(SimpleNamespace(primary_results=[]))
        self.assertEqual(shaped, {"columns": [], "rows": []})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
