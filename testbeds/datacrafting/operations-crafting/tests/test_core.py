import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rdflib import BNode, Graph, Literal, Namespace, URIRef

from core import EvidenceReader, InvalidInput, QueryDenied, confined_file, craft_dataset, decode_json, json_bytes, load_bundle, materialize_view, select_mode
from fixtures import OWNED_ROOT, TinyPack
import schemas


class SyntheticMode:
    id = "synthetic_test"
    version = 1
    input_resources = frozenset()

    def build(self, bundle):
        return {"test": bundle}


class BoundaryTests(unittest.TestCase):
    def test_v1_manifest_rejects_unknown_fields_and_versions(self):
        manifest = {
            "schema_version": 1, "synthetic": True, "seed": 20260916, "resource_pack_id": "tiny",
            "resources": [{"id": name, "path": name, "sha256": "0" * 64, "description": name} for name in schemas.RESOURCES],
            "authoring": [{"id": name, "path": name, "sha256": "0" * 64, "description": name} for name in ("source_events", "scenarios")],
        }
        schemas.validate(schemas.MANIFEST, manifest, "manifest")
        for field, value in (("schema_version", 2), ("module", "os"), ("synthetic", False)):
            with self.subTest(field=field), self.assertRaises(InvalidInput):
                schemas.validate(schemas.MANIFEST, {**manifest, field: value}, "manifest")

    def test_unknown_and_arbitrary_modes_do_not_touch_files(self):
        with patch.object(Path, "open", side_effect=AssertionError("filesystem access")):
            for mode_id in ("missing", "../operations", "os.system('id')", "https://host", ""):
                with self.subTest(mode_id=mode_id), self.assertRaises(InvalidInput):
                    select_mode(mode_id, {"synthetic_test": SyntheticMode()})

    def test_host_injected_mode_has_explicit_build_interface(self):
        mode = select_mode("synthetic_test", {"synthetic_test": SyntheticMode()})
        self.assertEqual(mode.build("public"), {"test": "public"})

    def test_unknown_mode_crafting_fails_before_any_io(self):
        with patch.object(Path, "exists", side_effect=AssertionError("filesystem access")):
            with self.assertRaisesRegex(InvalidInput, "unknown mode"):
                craft_dataset(mode_id="os.system", registry={}, resources=Path("missing"), source_root=Path("missing"), output=Path("missing"))

    def test_relative_file_and_symlink_confinement(self):
        with tempfile.TemporaryDirectory(dir=OWNED_ROOT, prefix=".test-") as directory:
            root = Path(directory)
            (root / "data.json").write_text("{}", encoding="utf-8")
            (root / "link.json").symlink_to(root / "data.json")
            self.assertEqual(confined_file(root, "data.json"), root / "data.json")
            for relative in ("../data.json", "/etc/passwd", "file:///etc/passwd", "link.json", "./data.json", "a\\b"):
                with self.subTest(relative=relative), self.assertRaises(InvalidInput):
                    confined_file(root, relative)


class IntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=OWNED_ROOT, prefix=".test-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = TinyPack(self.temp.name).write()

    def load(self):
        return load_bundle(self.fixture.pack, self.fixture.source)

    def test_tiny_csv_json_rdf_pack_loads(self):
        bundle = self.load()
        self.assertEqual(len(bundle.scenarios), 3)
        self.assertEqual(set(bundle.nodes), {"UNIT_A", "UNIT_B", "BUS_A"})
        self.assertEqual(bundle.tables["scada"][2]["value"], 298)

    def test_source_hash_and_exact_quote_and_page_forgery(self):
        document = self.fixture.sources["documents"][0]
        original = document["pdf_sha256"]
        document["pdf_sha256"] = "0" * 64
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "SHA-256"):
            self.load()
        document["pdf_sha256"] = original
        reference = self.fixture.sources["events"][0]["source_refs"][0]
        reference["quote"] = "invented quotation"
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "quote/page"):
            self.load()
        reference["quote"] = "At 1334.29 hrs on 16 October 2025 unit A tripped."
        reference["page"] = 2
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "quote/page"):
            self.load()

    def test_fixed_aest_and_minute_precision(self):
        event = self.fixture.sources["events"][0]
        event["event_interval"] = {"start": "2025-10-16T02:34:29Z", "end": "2025-10-16T02:34:30Z"}
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "UTC\\+10"):
            self.load()

    def test_same_incident_variants_stay_together(self):
        self.fixture.add_scenario("s004", "source_a", "2025-10-16T03:34:31Z")["split"] = "holdout"
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "cross splits"):
            self.load()

    def test_ambiguous_alias_and_missing_asset_refuse(self):
        self.fixture.assets[1]["aliases"].append("Unit A")
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "ambiguous asset"):
            self.load()
        self.fixture.assets[1]["aliases"].pop()
        self.fixture.scenarios[0]["asset_ids"] = ["MISSING"]
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "unresolved canonical asset"):
            self.load()

    def test_units_and_quality_are_validated(self):
        self.fixture.scada[2]["unit"] = "kV"
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "units"):
            self.load()

    def test_materialized_view_has_no_source_labels_or_future_data(self):
        current = self.fixture.scada[0].copy()
        self.fixture.scada.extend([
            {**current, "row_id": "future_event", "ts": "2025-10-16T03:40:00Z"},
            {**current, "row_id": "delayed", "available_at": "2025-10-16T03:40:00Z"},
        ])
        self.fixture.assets[0]["attributes"]["expected"] = "PRIVATE LABEL SENTINEL"
        self.fixture.write()
        bundle = self.load()
        view = materialize_view(bundle, bundle.scenarios[0], "operations", 1)
        serialized = str(view)
        for secret in ("source_a", "PRIVATE", "expected", "variant", "template", "split", "source.pdf", "content.md", "2026-08-01"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(len(view["evidence"]["scada"]), 9)
        self.assertNotIn("scenario_id", serialized)
        reader = EvidenceReader(view)
        self.assertFalse(hasattr(reader, "bundle"))

    def test_reader_refuses_tool_asset_scenario_time_and_path_widening(self):
        bundle = self.load()
        reader = EvidenceReader(materialize_view(bundle, bundle.scenarios[0], "operations", 1))
        requests = [
            ("labels", {}), ("../authoring/scenarios.json", {}), ("scada", {"asset_ids": ["BUS_A"]}),
            ("scada", {"case_id": "s002"}), ("scada", {"end": "2026-01-01T00:00:00Z"}),
            ("scada", {"start": "2020-01-01T00:00:00Z"}), ("scada", {"limit": 10001}),
        ]
        for tool, options in requests:
            with self.subTest(tool=tool, options=options), self.assertRaises(QueryDenied):
                reader.query(tool, **options)

    def test_action_conditions_are_public_inputs_not_private_labels(self):
        self.fixture.make_action()
        self.fixture.write()
        bundle = self.load()
        scenario = bundle.scenarios[0]
        view = materialize_view(bundle, scenario, "operations", 1)
        schemas.validate(schemas.PUBLIC_VIEW, view, "public view")
        condition = view["event_conditions"][0]
        self.assertEqual(condition["event_interval"], self.fixture.sources["events"][0]["event_interval"])
        self.assertTrue(condition["notification_id"].startswith("e-"))
        self.assertNotEqual(condition["notification_id"], scenario["event_conditions"][0]["notification_id"])
        scenario["expected"] = {"cause": "PRIVATE LABEL SENTINEL", "asset_ids": ["BUS_A"], "event_type": "restoration"}
        self.assertEqual(materialize_view(bundle, scenario, "operations", 1), view)
        for secret in ("PRIVATE", "expected", "source_a", "source_refs", "quote", "cause", "action_ids", "variant", "split"):
            self.assertNotIn(secret, str(view["event_conditions"]))

    def test_action_conditions_require_explicit_authoring_and_detection_refuses(self):
        scenario = self.fixture.make_action()
        self.fixture.write()
        self.load()
        original = scenario.pop("event_conditions")
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "explicitly update legacy authoring"):
            self.load()
        scenario["event_conditions"] = []
        self.fixture.write()
        with self.assertRaises(InvalidInput):
            self.load()
        scenario["event_conditions"] = original
        scenario["kind"] = "detection"
        self.fixture.write()
        with self.assertRaises(InvalidInput):
            self.load()
        scenario.pop("event_conditions")
        self.fixture.write()
        bundle = self.load()
        self.assertNotIn("event_conditions", materialize_view(bundle, bundle.scenarios[0], "operations", 1))

    def test_action_conditions_reject_labels_future_scope_and_forged_origin(self):
        scenario = self.fixture.make_action()
        original = copy.deepcopy(scenario["event_conditions"][0])
        self.fixture.write()
        self.load()
        mutations = [
            {"asset_ids": ["BUS_A"]}, {"asset_ids": []},
            {"event_interval": {"start": "2025-10-16T03:35:00Z", "end": "2025-10-16T03:35:01Z"}},
            {"event_interval": {"start": "2025-10-16T03:30:00Z", "end": "2025-10-16T03:30:01Z"}},
            {"event_interval": {"start": "2025-10-16T03:34:29Z", "end": "2025-10-16T03:34:29Z"}},
            {"available_at": "2025-10-16T03:40:00Z"}, {"available_at": "2025-10-16T03:34:00Z"},
            {"origin": "source_report"}, {"synthetic": False},
            *[{field: "PRIVATE SENTINEL"} for field in ("expected", "source_refs", "quote", "cause", "action_ids", "classification")],
        ]
        for mutation in mutations:
            scenario["event_conditions"] = [{**copy.deepcopy(original), **mutation}]
            self.fixture.write()
            with self.subTest(mutation=mutation), self.assertRaises(InvalidInput):
                self.load()
        scenario["event_conditions"] = [original, copy.deepcopy(original)]
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "duplicate notification"):
            self.load()

    def test_action_conditions_preserve_minute_uncertainty_at_cutoff(self):
        scenario = self.fixture.make_action(1)
        self.fixture.write()
        bundle = self.load()
        view = materialize_view(bundle, bundle.scenarios[1], "operations", 1)
        self.assertEqual(view["event_conditions"][0]["event_interval"],
                         {"start": "2026-01-29T00:08:00Z", "end": "2026-01-29T00:09:00Z"})
        EvidenceReader(view)
        view["event_conditions"][0]["available_at"] = "2026-01-29T00:09:00Z"
        with self.assertRaisesRegex(InvalidInput, "event/availability"):
            EvidenceReader(view)
        scenario["event_conditions"][0]["event_interval"]["end"] = "2026-01-29T00:08:01Z"
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "interval precision"):
            self.load()

    def test_action_conditions_may_select_source_subjects_without_context_assets(self):
        self.fixture.sources["events"][0]["asset_ids"].append("BUS_A")
        scenario = self.fixture.make_action()
        scenario["asset_ids"].extend(["BUS_A", "UNIT_B"])
        scenario["event_conditions"][0]["asset_ids"] = ["UNIT_A"]
        self.fixture.write()
        bundle = self.load()
        view = materialize_view(bundle, bundle.scenarios[0], "operations", 1)
        self.assertEqual(view["event_conditions"][0]["asset_ids"], ["UNIT_A"])
        self.assertIn("BUS_A", {asset["asset_id"] for asset in view["assets"]})
        scenario["event_conditions"][0]["asset_ids"] = ["UNIT_B"]
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "declared source event"):
            self.load()

    def test_bad_and_stale_values_do_not_enter_evidence(self):
        self.fixture.scada[0]["quality"] = "bad"
        self.fixture.scada[1]["quality"] = "stale"
        self.fixture.write()
        bundle = self.load()
        reader = EvidenceReader(materialize_view(bundle, bundle.scenarios[0], "operations", 1))
        response = reader.query("scada")
        self.assertEqual(len(response["rows"]), 7)
        self.assertTrue(all(row["quality"] == "good" for row in response["rows"]))

    def test_resource_path_escape_and_symlink_refuse_even_with_manifest_entry(self):
        manifest_path = self.fixture.pack / "manifest.json"
        original = decode_json(manifest_path.read_bytes())
        for relative in ("../source/content.md", "https://example.invalid/data", "linked.csv"):
            manifest = decode_json(json_bytes(original))
            entry = next(entry for entry in manifest["resources"] if entry["id"] == "scada")
            entry["path"] = relative
            if relative == "linked.csv":
                (self.fixture.pack / relative).symlink_to(self.fixture.pack / "scada.csv")
            manifest_path.write_bytes(json_bytes(manifest))
            with self.subTest(relative=relative), self.assertRaises(InvalidInput):
                self.load()

    def test_source_path_escape_and_extraction_hash_refuse(self):
        document = self.fixture.sources["documents"][0]
        document["pdf_path"] = "../pack/scada.csv"
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "escapes"):
            self.load()
        document["pdf_path"] = "source.pdf"
        document["extraction_sha256"] = "0" * 64
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "SHA-256"):
            self.load()

    def test_rdf_dangling_uri_and_blank_node_references_refuse(self):
        original = (self.fixture.pack / "topology.rdf").read_bytes()
        for target in (URIRef("urn:mock:absent"), BNode("absent")):
            graph = Graph().parse(data=original, format="xml")
            graph.add((URIRef("urn:mock:UNIT_A"), URIRef("urn:mock:dependency"), target))
            self.fixture.replace_resource("topology", graph.serialize(format="xml", encoding="utf-8"))
            with self.subTest(target=target), self.assertRaisesRegex(InvalidInput, "dangling topology"):
                self.load()

    def test_rdf_entity_and_voltage_disagreement_refuse(self):
        original = (self.fixture.pack / "topology.rdf").read_bytes()
        self.fixture.replace_resource("topology", b'<!DOCTYPE rdf [<!ENTITY bad SYSTEM "file:///etc/passwd">]>' + original)
        with self.assertRaisesRegex(InvalidInput, "entities"):
            self.load()
        graph = Graph().parse(data=original, format="xml")
        cim = Namespace("http://iec.ch/TC57/2013/CIM-schema-cim16#")
        graph.add((URIRef("urn:mock:UNIT_A"), cim["ConductingEquipment.BaseVoltage"], URIRef("urn:mock:base")))
        graph.add((URIRef("urn:mock:base"), cim["BaseVoltage.nominalVoltage"], Literal(330)))
        self.fixture.replace_resource("topology", graph.serialize(format="xml", encoding="utf-8"))
        with self.assertRaisesRegex(InvalidInput, "voltages disagree"):
            self.load()

    def test_source_minute_precision_cannot_claim_seconds(self):
        self.fixture.sources["events"][1]["event_interval"]["end"] = "2026-01-29T00:08:01Z"
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "precision mismatch"):
            self.load()

    def test_optional_native_hash_and_nested_cause_quote_are_verified(self):
        native = b'{"pages": 2}\n'
        (self.fixture.source / "native.json").write_bytes(native)
        document = self.fixture.sources["documents"][0]
        from core import digest
        document.update({"native_path": "native.json", "native_sha256": digest(native), "pages": 2})
        self.fixture.write()
        self.load()
        document["native_sha256"] = "0" * 64
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "SHA-256"):
            self.load()
        document["native_sha256"] = digest(native)
        self.fixture.sources["events"][0]["cause"]["source_refs"] = [{"document_id": "doc", "page": 1, "quote": "forged nested cause"}]
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "quote/page"):
            self.load()

    def test_optional_annotations_do_not_widen_public_knowledge(self):
        manifest_path = self.fixture.pack / "manifest.json"
        manifest = decode_json(manifest_path.read_bytes())
        manifest["synthetic_assumptions"] = [{"id": "test-basis", "basis": "invented", "text": "Synthetic fixture."}]
        manifest["capabilities"] = {tool: tool for tool in schemas.TOOLS}
        manifest_path.write_bytes(json_bytes(manifest))
        self.load()
        self.fixture.knowledge[0]["availability_basis"] = "PRIVATE AUTHORING SENTINEL"
        self.fixture.knowledge[0]["execution"] = "recommendation_only"
        self.fixture.write()
        bundle = self.load()
        view = materialize_view(bundle, bundle.scenarios[0], "operations", 1)
        self.assertNotIn("PRIVATE AUTHORING SENTINEL", str(view))

    def test_authored_freshness_narrows_but_cannot_widen_host_limit(self):
        self.fixture.scenarios[0]["parameters"]["stale_after_seconds"] = 60
        self.fixture.write()
        bundle = self.load()
        self.assertEqual(materialize_view(bundle, bundle.scenarios[0], "operations", 1)["limits"]["max_age_seconds"], 60)
        bundle.scenarios[0]["parameters"]["stale_after_seconds"] = 301
        with self.assertRaisesRegex(InvalidInput, "freshness"):
            materialize_view(bundle, bundle.scenarios[0], "operations", 1)

    def test_rdf_blank_nodes_materialize_identically_across_parses(self):
        graph = Graph().parse(data=(self.fixture.pack / "topology.rdf").read_bytes(), format="xml")
        terminal = BNode()
        graph.add((terminal, URIRef("http://iec.ch/TC57/2013/CIM-schema-cim16#Terminal.ConductingEquipment"), URIRef("urn:mock:UNIT_A")))
        graph.add((terminal, URIRef("urn:mock:synthetic"), Literal(True)))
        self.fixture.replace_resource("topology", graph.serialize(format="xml", encoding="utf-8"))
        first, second = self.load(), self.load()
        self.assertEqual(materialize_view(first, first.scenarios[0], "operations", 1), materialize_view(second, second.scenarios[0], "operations", 1))

    def test_utf16_rdf_document_type_is_refused_before_entity_expansion(self):
        xml = '<?xml version="1.0" encoding="utf-16"?><!DOCTYPE rdf [<!ENTITY secret SYSTEM "file:///etc/passwd">]><rdf>&secret;</rdf>'
        self.fixture.replace_resource("topology", xml.encode("utf-16"))
        with self.assertRaisesRegex(InvalidInput, "entities"):
            self.load()

    def test_unknown_capability_and_executable_rule_fields_refuse(self):
        manifest_path = self.fixture.pack / "manifest.json"
        manifest = decode_json(manifest_path.read_bytes())
        manifest["resources"][0]["id"] = "python"
        manifest_path.write_bytes(json_bytes(manifest))
        with self.assertRaisesRegex(InvalidInput, "capabilities"):
            self.load()
        self.fixture.knowledge[0]["action_rules"][0]["expression"] = "__import__('os')"
        self.fixture.write()
        with self.assertRaisesRegex(InvalidInput, "Additional properties"):
            self.load()


if __name__ == "__main__":
    unittest.main()