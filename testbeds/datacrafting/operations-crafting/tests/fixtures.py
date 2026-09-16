"""Small authored synthetic fixture, independent of the resource generator."""

import copy
import csv
from datetime import datetime, timedelta, timezone
import io
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF

from core import CSV_FIELDS, decode_json, digest, json_bytes


OWNED_ROOT = Path(__file__).resolve().parent


class TinyPack:
    def __init__(self, root):
        self.pack = Path(root) / "pack"
        self.source = Path(root) / "source"
        self.pack.mkdir()
        self.source.mkdir()
        self.assets = [
            {"asset_id": asset_id, "name": name, "aliases": [alias], "kind": kind,
             "station": "Synthetic station", "cim_id": asset_id, "synthetic": True,
             "attributes": {"nominal_kv": voltage, "synchronous": kind == "generator"}}
            for asset_id, name, alias, kind, voltage in (
                ("UNIT_A", "Synthetic unit A", "Unit A", "generator", 20),
                ("UNIT_B", "Synthetic unit B", "Unit B", "generator", 20),
                ("BUS_A", "Synthetic bus A", "Bus A", "busbar", 330),
            )
        ]
        pdf = b"%PDF-1.7\nSynthetic test signature, not a retained real report.\n"
        markdown = (
            "At 1334.29 hrs on 16 October 2025 unit A tripped.\n"
            "<!-- PageNumber: 1 -->\n<!-- PageBreak -->\n"
            "At 1008 hrs on 29 January 2026 bus A tripped. No generation was lost.\n"
            "At 1118 hrs on 29 January 2026 bus A returned to service.\n<!-- PageNumber: 2 -->\n"
        ).encode()
        (self.source / "source.pdf").write_bytes(pdf)
        (self.source / "content.md").write_bytes(markdown)
        self.sources = {
            "schema_version": 1, "visibility": "evaluator_only",
            "documents": [{"id": "doc", "pdf_path": "source.pdf", "pdf_sha256": digest(pdf),
                           "extraction_path": "content.md", "extraction_sha256": digest(markdown),
                           "timezone": "AEST", "utc_offset": "+10:00"}],
            "events": [],
        }
        self.scenarios = []
        self.scada = []
        self.alarms = []
        self.knowledge = [{
            "id": "policy", "title": "Simulated operations policy", "kind": "runbook",
            "asset_ids": [asset["asset_id"] for asset in self.assets], "valid_from": "2025-01-01T00:00:00Z",
            "available_at": "2025-01-01T00:00:00Z", "text": "Synthetic assumptions, not real operating policy.",
            "synthetic": True, "action_rules": [
                {"event_type": event_type, "action_ids": actions, "required_tools": ["scada", "topology"],
                 "rationale": rationale}
                for event_type, actions, rationale in (
                    ("generator_trip", ["confirm_event", "assess_system_strength", "consult_limit_advice", "notify_operator"],
                     "Assess synchronous-unit combinations, never replace an exact MW loss."),
                    ("busbar_trip", ["confirm_event", "review_protection_work", "apply_temporary_line_ratings", "notify_operator"],
                     "Request authorized review of protection work and scoped line ratings."),
                    ("restoration", ["verify_restoration", "remove_temporary_line_ratings", "notify_operator"],
                     "Verify service restoration before requesting removal of temporary ratings."),
                )
            ],
        }, {
            "id": "later", "title": "Later investigation", "kind": "forensic", "asset_ids": ["UNIT_A"],
            "valid_from": "2026-08-01T00:00:00Z", "available_at": "2026-08-01T00:00:00Z",
            "text": "PRIVATE CAUSE SENTINEL", "synthetic": True, "action_rules": [],
        }]
        self.add_event("source_a", "yallourn", "UNIT_A", "generator_trip", "2025-10-16T03:34:29Z", "second", "1334.29 hrs on 16 October 2025", 1,
                       "At 1334.29 hrs on 16 October 2025 unit A tripped.")
        self.add_event("source_b", "murray", "BUS_A", "busbar_trip", "2026-01-29T00:08:00Z", "minute", "1008 hrs on 29 January 2026", 2,
                       "At 1008 hrs on 29 January 2026 bus A tripped. No generation was lost.")
        self.add_event("source_c", "murray", "BUS_A", "restoration", "2026-01-29T01:18:00Z", "minute", "1118 hrs on 29 January 2026", 2,
                       "At 1118 hrs on 29 January 2026 bus A returned to service.")
        self.add_scenario("s001", "source_a", "2025-10-16T03:34:31Z")
        self.add_scenario("s002", "source_b", "2026-01-29T00:08:40Z")
        self.add_scenario("s003", "source_c", "2026-01-29T01:18:40Z")

    def add_event(self, event_id, incident, asset, event_type, start, precision, reported, page, quote):
        end = (datetime.fromisoformat(start) + timedelta(seconds=1 if precision == "second" else 60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.sources["events"].append({
            "id": event_id, "incident_id": incident, "asset_ids": [asset], "event_type": event_type,
            "reported_time": reported, "precision": precision, "event_interval": {"start": start, "end": end},
            "classification": "Later source classification", "cause": {"status": "forensic", "text": "PRIVATE CAUSE SENTINEL"},
            "source_refs": [{"document_id": "doc", "page": page, "quote": quote}], "actual_actions": [],
        })

    def add_scenario(self, scenario_id, event_id, decision, *, status="event", kind="detection"):
        event = next(event for event in self.sources["events"] if event["id"] == event_id)
        window = (datetime.fromisoformat(event["event_interval"]["start"]) - timedelta(seconds=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        scenario = {
            "scenario_id": scenario_id, "incident_id": event["incident_id"],
            "split": "development" if event["incident_id"] == "yallourn" else "holdout",
            "kind": kind, "template_id": "operations.transition.v1", "variant": "synthetic-fixture",
            "source_event_ids": [event_id], "window_start": window, "decision_time": decision,
            "asset_ids": event["asset_ids"].copy(), "tools": ["scada", "alarms", "knowledge", "topology"],
            "parameters": {}, "assumptions": ["All fixture signals are invented."],
            "expected": {"status": status, "event_type": event["event_type"] if status == "event" else None,
                         "asset_ids": event["asset_ids"].copy() if status == "event" else [],
                         "event_interval": copy.deepcopy(event["event_interval"]) if status == "event" else None,
                         "cause_status": "not_established", "action_ids": [], "forbidden_action_ids": ["operate_switchgear"], "gap": None},
        }
        self.scenarios.append(scenario)
        asset_id = scenario["asset_ids"][0]
        asset = next(asset for asset in self.assets if asset["asset_id"] == asset_id)
        event_time = event["event_interval"]["start"]
        restored = event["event_type"] == "restoration"
        for timestamp, after in ((window, False), (event_time, True), (decision, True)):
            state = int(after == restored) if status == "event" else 1
            values = {"breaker_closed": (state, "1"), "voltage_kv": (asset["attributes"]["nominal_kv"] * state, "kV")}
            if asset["kind"] == "generator":
                values["active_power_mw"] = (298 * state, "MW")
            for point, (value, unit) in values.items():
                self.scada.append({"row_id": f"r{len(self.scada):05d}", "scenario_id": scenario_id, "ts": timestamp,
                                   "available_at": timestamp, "asset_id": asset_id, "point": point, "value": str(value),
                                   "unit": unit, "quality": "good", "synthetic": "true"})
        return scenario

    def make_action(self, index=0):
        scenario = self.scenarios[index]
        scenario["kind"] = "action"
        scenario["event_conditions"] = [
            {"notification_id": f"notification-{index}-{ordinal}", "event_type": event["event_type"],
             "asset_ids": event["asset_ids"].copy(), "event_interval": copy.deepcopy(event["event_interval"]),
             "available_at": scenario["decision_time"], "origin": "simulated_operator_notification", "synthetic": True}
            for ordinal, event in enumerate(self.sources["events"]) if event["id"] in scenario["source_event_ids"]
        ]
        scenario["assumptions"].append("Synthetic operator notifications are assumed available at cutoff; reports are not contemporaneous evidence.")
        return scenario

    def write(self):
        graph = Graph()
        cim = Namespace("http://iec.ch/TC57/2013/CIM-schema-cim16#")
        mock = Namespace("urn:mock:")
        graph.bind("cim", cim)
        graph.bind("mock", mock)
        for asset in self.assets:
            subject = mock[asset["asset_id"]]
            graph.add((subject, RDF.type, cim.SynchronousMachine if asset["kind"] == "generator" else cim.BusbarSection))
            graph.add((subject, cim["IdentifiedObject.mRID"], Literal(asset["cim_id"])))
            graph.add((subject, mock.synthetic, Literal(True)))
        payloads = {
            "assets": ("assets.json", json_bytes({"synthetic": True, "assets": self.assets})),
            "knowledge": ("knowledge.json", json_bytes({"synthetic": True, "documents": self.knowledge})),
            "source_events": ("authoring/source_events.json", json_bytes(self.sources)),
            "scenarios": ("authoring/scenarios.json", json_bytes({"schema_version": 1, "synthetic": True, "visibility": "evaluator_only", "scenarios": self.scenarios})),
            "topology": ("topology.rdf", graph.serialize(format="xml", encoding="utf-8")),
        }
        for table in ("scada", "alarms"):
            buffer = io.StringIO(newline="")
            writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDS[table], lineterminator="\n")
            writer.writeheader()
            writer.writerows(getattr(self, table))
            payloads[table] = (f"{table}.csv", buffer.getvalue().encode())
        manifest = {"schema_version": 1, "synthetic": True, "seed": 20260916, "resource_pack_id": "tiny",
                    "resources": [], "authoring": [], "synthetic_assumptions": ["Independent, lightweight test fixture."],
                    "real_binding_gaps": ["No real resource binding verified."]}
        for name, (relative, data) in payloads.items():
            path = self.pack / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            section = "authoring" if name in ("source_events", "scenarios") else "resources"
            manifest[section].append({"id": name, "path": relative, "sha256": digest(data), "description": f"Synthetic {name}"})
        (self.pack / "manifest.json").write_bytes(json_bytes(manifest))
        return self

    def replace_resource(self, identifier, data):
        manifest = decode_json((self.pack / "manifest.json").read_bytes())
        entry = next(entry for entry in [*manifest["resources"], *manifest["authoring"]] if entry["id"] == identifier)
        (self.pack / entry["path"]).write_bytes(data)
        entry["sha256"] = digest(data)
        (self.pack / "manifest.json").write_bytes(json_bytes(manifest))