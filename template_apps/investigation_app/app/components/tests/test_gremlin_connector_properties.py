"""What a producer hands the Gremlin connector decides whether the value survives Cosmos.

This is the connector's half of the bucket round-trip contract. It is tested here because
the encoder and its cap are the connector's, and a caller cannot see either from outside.

The cap is not hypothetical: a serialised bucket map fell through to it once and was chopped
mid-token, which silently truncated the 34 busiest edges in the ontology graph
(note-20260902T050858Z-8014ad95). The three properties below are what stops that recurring.

Moved here with the connector, and now exercised through the library's public barrel, which
is the surface every consumer will import.
"""

from __future__ import annotations

import json
import unittest

from app.components.data_connector_library import PROPERTY_TEXT_LIMIT, encode_properties


def busy_relationship() -> dict[str, int]:
    """A relationship active across a whole three-day export: 288 quarter-hour buckets."""
    return {f"2026-08-{day:02d}T{hour:02d}:{minute:02d}": 3
            for day in (11, 12, 13) for hour in range(24) for minute in (0, 15, 30, 45)}


class GremlinPropertyEncodingTests(unittest.TestCase):
    def test_a_mapping_survives_whole_however_busy_the_relationship(self) -> None:
        stored = encode_properties({"buckets": busy_relationship()})["buckets"]
        self.assertGreater(len(stored), PROPERTY_TEXT_LIMIT)
        self.assertEqual(json.loads(stored), busy_relationship())

    def test_the_same_map_handed_over_as_text_is_chopped(self) -> None:
        """The defect mechanism, pinned. Free text has no exemption for looking like JSON."""
        pre_serialised = json.dumps(busy_relationship())
        stored = encode_properties({"buckets": pre_serialised})["buckets"]
        self.assertEqual(len(stored), PROPERTY_TEXT_LIMIT)
        with self.assertRaises(json.JSONDecodeError):
            json.loads(stored)

    def test_free_text_is_still_capped(self) -> None:
        self.assertEqual(len(encode_properties({"note": "x" * 5000})["note"]), PROPERTY_TEXT_LIMIT)

    def test_a_relationship_that_never_fired_stores_no_bucket_property_at_all(self) -> None:
        self.assertNotIn("buckets", encode_properties({"buckets": {}}))


class GremlinBindingTests(unittest.TestCase):
    """Every value crosses as a binding; only the property name is interpolated."""

    def _graph(self) -> object:
        from app.components.data_connector_library import GremlinGraph, GremlinSettings

        settings = GremlinSettings(account="a", database="d", graph="g", partition_key="pk",
                                   partition_value="perth", resource_group="", subscription_id="")
        # __init__ opens a websocket; the script builders need only the settings.
        graph = GremlinGraph.__new__(GremlinGraph)
        graph.settings = settings
        return graph

    def test_no_caller_value_reaches_the_traversal_text(self) -> None:
        graph = self._graph()
        script, bindings = graph._vertex_script([
            {"id": "g.V().drop()", "label": "Host", "properties": {"name": "'; drop"}},
        ])
        self.assertNotIn("g.V().drop()", script)
        self.assertNotIn("'; drop", script)
        self.assertIn("g.V().drop()", bindings.values())
        self.assertIn("'; drop", bindings.values())

    def test_an_unsafe_property_name_is_refused_rather_than_escaped(self) -> None:
        from app.components.data_connector_library import GremlinError

        graph = self._graph()
        with self.assertRaises(GremlinError):
            graph._vertex_script([{"id": "v1", "label": "Host", "properties": {"!!": "x"}}])


if __name__ == "__main__":
    unittest.main()
