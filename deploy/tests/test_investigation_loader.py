from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from investigation_loader import graph_properties, graph_upsert, load_package, PACKAGE_SHA256


class LoaderTests(unittest.TestCase):
    def test_bound_edge_writer_does_not_interpolate_payload(self):
        element = {"id": "edge-1", "from_id": "from", "to_id": "to", "label": "REL",
                   "properties": {"partition": "scenario", "source": {"path": "quote'"}, "evidence_refs": ["one", "two"]}}
        query, bindings = graph_upsert(element, edge=True)
        self.assertIn("coalesce(outE(label).hasId(identifier)", query)
        self.assertNotIn("quote", query)
        self.assertEqual(bindings["source"], "from")
        self.assertEqual(bindings["target"], "to")
        self.assertNotIn("partition", [value for key, value in bindings.items() if key.startswith("name")])
        self.assertIn(PACKAGE_SHA256, bindings.values())
        self.assertEqual(graph_properties(element["properties"])["evidence_refs"], '["one","two"]')

    def test_exact_retained_package_hashes_and_counts(self):
        directory = Path(__file__).resolve().parents[2] / "template_apps/investigation_app/deploy/data/public-investigation/packages" / PACKAGE_SHA256
        manifest, documents = load_package(directory)
        self.assertEqual(manifest["counts"]["vertices"], 10)
        self.assertEqual(len(documents["search"]), 3135)


if __name__ == "__main__":
    unittest.main()