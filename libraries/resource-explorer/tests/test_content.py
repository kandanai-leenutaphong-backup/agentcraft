"""The adopted `azdata` subset: bounds, statuses, readers and the SDK seam.

These are this repository's tests, not upstream's. Upstream ships a pytest
suite for the whole package; this covers exactly the surface that was adopted,
including the two behaviours a caller must not be surprised by — that a
`take n` Kusto sample cannot report its own truncation, and that a missing SDK
is a status rather than an exception.

Offline: sources are injected directly and missing imports are scoped mocks.
"""

from __future__ import annotations

import asyncio
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from azdata import ContentValue, ErrorInfo, ItemResult, OperationResult, ResourceAddress
from resource_explorer import GraphInspection, GraphInspectionUnavailable, graph_properties

from resource_explorer.content import (
    ContentBounds,
    ContentPayload,
    DEFAULT_MAX_CELL_CHARS,
    DiscoveryAbsent,
    DiscoveryUnreachable,
    GraphReader,
    GraphTarget,
    MissingDependency,
    bounded_content,
    classify_discovery_failure,
    collected_now,
    content_failure,
    normalize_rows,
    normalize_sample,
    sanitize_detail,
    load,
)


def run(coro: Any) -> Any:
    return asyncio.run(coro)


class BoundsTests(unittest.TestCase):
    def test_bounds_clamp_rather_than_raise(self) -> None:
        """A caller that computed zero gets one row, not an exception."""
        bounds = ContentBounds(max_rows=0, max_bytes=0, timeout_secs=0)
        self.assertEqual(bounds.max_rows, 1)
        self.assertEqual(bounds.max_bytes, 1)
        self.assertGreater(bounds.timeout_secs, 0)


class OptionalImportTests(unittest.TestCase):
    def test_loader_uses_the_real_import_contract(self) -> None:
        import math

        self.assertIs(load("math", dist="stdlib"), math)

    def test_missing_import_reports_distribution_without_a_global_override(self) -> None:
        with patch("resource_explorer.content.optional.importlib.import_module", side_effect=ImportError):
            with self.assertRaises(MissingDependency) as raised:
                load("azure.search.documents", dist="azure-search-documents")
        self.assertEqual(raised.exception.dist, "azure-search-documents>=11.5")

    def test_runtime_exports_no_test_override_hooks(self) -> None:
        import resource_explorer.content as content
        import resource_explorer.content.optional as optional

        for module in (content, optional):
            for name in ("override", "override_missing", "clear_overrides"):
                self.assertFalse(hasattr(module, name))


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


class GraphInspectionTests(unittest.IsolatedAsyncioTestCase):
    @staticmethod
    def result(rows=()):
        return OperationResult("fixture", "query", "gremlin", ResourceAddress({"database": "db", "container": "graph"}),
                               "success", tuple(ItemResult(index, None, "success", ContentValue(row))
                                                for index, row in enumerate(rows)))

    async def test_counts_empty_and_invalid_counts(self):
        connector = SimpleNamespace(query=AsyncMock(return_value=self.result([0])))
        source = GraphInspection(connector)
        self.assertEqual(await source.element_count("vertices"), 0)
        self.assertEqual(connector.query.call_args.args[0].expression, "g.V().count()")
        for rows in ([], [True], [-1], [1.0], ["3"], [1, 2]):
            connector.query.return_value = self.result(rows)
            with self.subTest(rows=rows), self.assertRaisesRegex(GraphInspectionUnavailable, "count_unknown"):
                await source.element_count("edges")
        connector.query.return_value = self.result()
        self.assertEqual(await source.sample("vertices", 1), [])

    async def test_samples_flatten_without_coercing_native_values(self):
        moment = datetime(2026, 9, 17, tzinfo=timezone.utc)
        row = {"id": "vertex", "when": [moment], "many": [1, 2], "empty": [], "flag": [False]}
        connector = SimpleNamespace(query=AsyncMock(return_value=self.result([row])))
        source = GraphInspection(connector)
        self.assertEqual((await source.sample("vertices", 1))[0], graph_properties(row))
        connector.query.return_value = self.result([{"e": row, "from": "a", "to": "b"}])
        self.assertEqual((await source.sample("edges", 1))[0], {**graph_properties(row), "outV": "a", "inV": "b"})
        for rows in ([3], [{"e": 3, "from": "a", "to": "b"}], [{"e": {}}], [{}, {}]):
            connector.query.return_value = self.result(rows)
            with self.subTest(rows=rows), self.assertRaisesRegex(GraphInspectionUnavailable, "sample_invalid"):
                await source.sample("edges", 1)

    async def test_refusals_partial_errors_and_provider_failure_are_not_empty(self):
        successful = self.result([1])
        cases = [replace(successful, status="partial"), replace(successful, truncated=True),
                 replace(successful, status="denied", errors=(ErrorInfo("denied", "denied"),)),
                 replace(successful, errors=(ErrorInfo("provider_error", "failed"),)),
                 replace(successful, items=(ItemResult(0, None, "success"),)),
                 replace(successful, items=(ItemResult(0, None, "failed", error=ErrorInfo("bad_item", "failed")),))]
        connector = SimpleNamespace(query=AsyncMock())
        source = GraphInspection(connector)
        for result in cases:
            connector.query.return_value = result
            with self.subTest(result=result), self.assertRaises(GraphInspectionUnavailable):
                await source.element_count("vertices")
        connector.query.side_effect = OSError("fixture offline")
        with self.assertRaisesRegex(GraphInspectionUnavailable, "graph_query_failed") as raised:
            await source.sample("vertices", 1)
        self.assertIsInstance(raised.exception.__cause__, OSError)
        connector.query.reset_mock()
        for limit in (0, 102, True, 1.5):
            with self.assertRaises(ValueError):
                await source.sample("vertices", limit)
        with self.assertRaises(ValueError):
            await source.element_count("unknown")
        connector.query.assert_not_called()

    async def test_owned_and_borrowed_lifetime(self):
        for owns in (True, False):
            connector = SimpleNamespace(query=AsyncMock(return_value=self.result([1])), aclose=AsyncMock())
            source = GraphInspection(connector, owns_connector=owns)
            self.assertEqual(await source.element_count("vertices"), 1)
            await asyncio.gather(source.aclose(), source.aclose())
            self.assertEqual(connector.aclose.await_count, int(owns))
            with self.assertRaisesRegex(GraphInspectionUnavailable, "closed"):
                await source.element_count("vertices")
            self.assertEqual(connector.query.await_count, 1)
        with self.assertRaisesRegex(GraphInspectionUnavailable, "unconfigured"):
            await GraphInspection(None).sample("vertices", 1)


class GraphReaderTests(unittest.TestCase):
    def test_async_samples_and_sync_wrappers_are_awaited(self) -> None:
        async def check():
            loop_thread = threading.get_ident()
            wrapper_threads = []

            class AsyncSource:
                async def sample(self, element, limit):
                    await asyncio.sleep(0)
                    return [{"id": str(index)} for index in range(limit)]

            class WrappedSource:
                def sample(self, element, limit):
                    wrapper_threads.append(threading.get_ident())
                    return AsyncSource().sample(element, limit)

            for source in (AsyncSource(), WrappedSource()):
                reader = GraphReader(resolve=lambda target: source)
                result = await reader.elements(target=GraphTarget("account", "database", "graph"),
                                               bounds=ContentBounds(max_rows=2))
                self.assertEqual(result.status, "ok")
                self.assertEqual(len(result.payload.rows), 2)
                self.assertTrue(result.truncated)
            self.assertTrue(all(thread != loop_thread for thread in wrapper_threads))

        run(check())

    def test_cancellation_reaches_the_async_source(self) -> None:
        async def check():
            started = asyncio.Event()
            finished = asyncio.Event()

            class Source:
                async def sample(self, element, limit):
                    started.set()
                    try:
                        await asyncio.Event().wait()
                    finally:
                        finished.set()

            reader = GraphReader(resolve=lambda target: Source())
            task = asyncio.create_task(reader.elements(target=GraphTarget("account", "database", "graph")))
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            self.assertTrue(finished.is_set())

        run(check())

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


