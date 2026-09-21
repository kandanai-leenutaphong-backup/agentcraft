"""Synthetic structural fixtures, not malicious labels or copied upstream telemetry."""

import copy
import hashlib
import json
import unittest

from app.data.ontology import normalize_windows, resolve_event, validate_package
from app.data.ontology.public_windows import qualified_id
from deploy.public_data import project_mitre


def fixture(*, domain="LAB", host="host.lab.test", process="11111111-1111-1111-1111-111111111111", pid="7"):
    return ("<Event xmlns='http://schemas.microsoft.com/win/2004/08/events/event'><System>"
            "<Provider Name='Microsoft-Windows-Sysmon'/><EventID>1</EventID>"
            "<TimeCreated SystemTime='2025-07-29T09:42:00Z'/><EventRecordID>1</EventRecordID>"
            f"<Computer>{host}</Computer></System><EventData>"
            f"<Data Name='User'>{domain}\\test</Data><Data Name='ProcessGuid'>{process}</Data>"
            f"<Data Name='ProcessId'>{pid}</Data><Data Name='ParentProcessGuid'>22222222-2222-2222-2222-222222222222</Data>"
            "<Data Name='Image'>C:\\Windows\\System32\\rundll32.exe</Data>"
            "<Data Name='CommandLine'>rundll32.exe C:\\Temp\\sample.dll</Data>"
            "</EventData></Event>\n").encode()


def source(payload, scenario="synthetic", source_id="synthetic-owner"):
    return {"source_id": source_id, "scenario_id": scenario, "commit": "a" * 40,
            "source_path": "synthetic.log", "source_url": "https://example.org/synthetic.log",
            "sha256": hashlib.sha256(payload).hexdigest()}


class PublicWindowsTests(unittest.TestCase):
    def test_deterministic_chain_and_raw_membership(self):
        payload = fixture()
        result = normalize_windows(payload, source(payload))
        self.assertEqual(result, normalize_windows(payload, source(payload)))
        incident, alarm, event = result["cosmos"]
        self.assertTrue(alarm["derived"])
        self.assertEqual(incident["ground_truth_kind"], "emulation_scenario")
        self.assertEqual(alarm["event_refs"], [event["resource_id"]])
        self.assertEqual(event["label_status"], "unlabelled")
        self.assertEqual(event["source"]["raw_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(resolve_event(result, event["resource_id"], partition=result["partition"]), event)
        self.assertEqual(result["observations"]["omissions"]["parent_creation_not_in_export"], 1)

    def test_collisions_domain_host_pid_and_source(self):
        payload = fixture() + fixture(domain="OTHER", process="33333333-3333-3333-3333-333333333333") + fixture(host="host.other.test")
        result = normalize_windows(payload, source(payload))
        events = [item for item in result["cosmos"] if item["kind"] == "event"]
        self.assertNotEqual(events[0]["entity_refs"]["user"], events[1]["entity_refs"]["user"])
        self.assertNotEqual(events[0]["entity_refs"]["process"], events[1]["entity_refs"]["process"])
        self.assertNotEqual(events[0]["entity_refs"]["host"], events[2]["entity_refs"]["host"])
        self.assertNotEqual(events[0]["entity_refs"]["process"], events[2]["entity_refs"]["process"])
        for changed in (source(payload, scenario="other"), source(payload, source_id="other")):
            alternative = normalize_windows(payload, changed)
            self.assertTrue({item["id"] for item in result["gremlin"]["vertices"]}.isdisjoint(
                item["id"] for item in alternative["gremlin"]["vertices"]))
        self.assertNotEqual(qualified_id("host", "scope", "host.lab"), qualified_id("host", "scope", "host.other"))

    def test_missing_guid_never_joins_pid(self):
        payload = fixture(process="")
        result = normalize_windows(payload, source(payload))
        event = result["cosmos"][-1]
        self.assertNotIn("process", event["entity_refs"])
        self.assertEqual(result["observations"]["omissions"]["missing_process_guid_no_pid_join"], 1)

    def test_refusals(self):
        payload = fixture()
        result = normalize_windows(payload, source(payload))
        with self.assertRaises(ValueError):
            normalize_windows(payload + b" ", source(payload))
        for identity, partition in (("event://unknown", result["partition"]), (result["cosmos"][-1]["resource_id"], "foreign")):
            with self.assertRaises(ValueError):
                resolve_event(result, identity, partition=partition)
        for kind in ("source", "event", "edge"):
            broken = copy.deepcopy(result)
            if kind == "source":
                broken["cosmos"][-1]["source"]["commit"] = "b" * 40
            elif kind == "event":
                broken["cosmos"][1]["event_refs"].append("event://foreign")
            else:
                broken["gremlin"]["edges"][0]["properties"]["evidence_refs"] = ["event://foreign"]
            with self.assertRaises(ValueError):
                validate_package(broken)
        xml = b'<!DOCTYPE x [<!ENTITY unsafe "expanded">]>' + payload
        with self.assertRaises(ValueError):
            normalize_windows(xml, source(xml))

    def test_rule_negative_preserves_unlabelled_event(self):
        payload = fixture().replace(b"rundll32.exe C:\\Temp\\sample.dll", b"rundll32.exe C:\\Windows\\sample.dll")
        result = normalize_windows(payload, source(payload))
        self.assertEqual(result["observations"]["alarms"], 0)
        self.assertEqual(result["cosmos"][-1]["label_status"], "unlabelled")


class MitreProjectionTests(unittest.TestCase):
    def project(self, objects):
        payload = json.dumps({"type": "bundle", "id": "bundle--synthetic", "objects": objects}).encode()
        pin = {"source_path": "synthetic.json", "commit": "a" * 40, "release": "synthetic", "license": "synthetic-only", "license_sha256": "b" * 64}
        return project_mitre(payload, pin, {"retrieved_at": "2026-09-20T00:00:00Z"})

    def item(self, kind="attack-pattern", identity="technique", external_id="T1001", **extra):
        return {"type": kind, "id": identity, "spec_version": "2.1", "name": "Synthetic", "modified": "2025-01-01T00:00:00Z",
                "external_references": [{"source_name": "mitre-attack", "external_id": external_id, "url": "https://attack.mitre.org/techniques/T1001/"}], **extra}

    def test_keys_provenance_and_revocation(self):
        docs, report = self.project([self.item(), self.item(identity="revoked", external_id="T9999", revoked=True)])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]["id"], "situation_type_T1001-adaac2e0")
        self.assertEqual(docs[0]["native_id"], "technique")
        self.assertTrue(docs[0]["advisory_only"])
        self.assertEqual(docs[0]["license"], "synthetic-only")
        self.assertEqual(report["excluded_revoked_or_deprecated"], 1)

    def test_explicit_detection_links_only(self):
        strategy = self.item("x-mitre-detection-strategy", "strategy", "DET0001", x_mitre_analytic_refs=["analytic"])
        analytic = self.item("x-mitre-analytic", "analytic", "AN0001")
        relation = {"type": "relationship", "id": "relation", "spec_version": "2.1", "relationship_type": "detects", "source_ref": "strategy", "target_ref": "technique"}
        docs, _ = self.project([self.item(), strategy, analytic, relation])
        self.assertTrue(all(doc["technique_ids"] == ["T1001"] for doc in docs))
        docs, _ = self.project([self.item(), strategy, analytic])
        self.assertTrue(all(doc["technique_ids"] == [] for doc in docs if doc["doc_kind"] == "analytic"))

    def test_duplicate_version_and_external_url_refusals(self):
        for objects in ([self.item(), self.item()], [self.item(spec_version="2.0")],
                        [self.item(external_references=[{"source_name": "mitre-attack", "external_id": "T1001", "url": "https://external.example/"}])],
                        [self.item(), self.item(identity="different-same-key")]):
            with self.assertRaises(ValueError):
                self.project(objects)


if __name__ == "__main__":
    unittest.main()