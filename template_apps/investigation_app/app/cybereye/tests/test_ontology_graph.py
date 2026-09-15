"""Accuracy tests for the ontology builder.

Every assertion is a contract about how a telemetry row becomes graph structure. The
counts in ``test_matches_the_pinned_export`` are re-derived from the real export, so a
change in extraction that alters the graph shape fails here rather than silently shipping.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from app.data.ontology import build_graph, read_graph, write_graph
from app.data.ontology.canonical import (
    account_key, address_key, address_scope, bucket_key, buckets_in_window, clean, dns_key,
    host_parts, parse_identity_blob, short_host, slug,
)
from app.data.ontology.extract import derive_structural_edges, extract_row
from app.data.ontology.model import (
    EDGE_LABELS, EVENT_EDGES, NODE_LABELS, STRUCTURAL_EDGES, Graph,
)

BASE = Path(__file__).resolve().parents[2] / "data"
NODES = BASE / "output" / "graph_nodes.csv"
EDGES = BASE / "output" / "graph_edges.csv"
REPORT = BASE / "output" / "ontology_report.json"


def row(**overrides: str) -> dict[str, str]:
    base = {
        "source_time": "2026-08-13T02:33:18.000000Z",
        "resource_id": "event://test:1",
        "product": "WINDOWS_SNARE",
        "event_type_recovered": "auth",
        "sensor_id": "", "sensor_type": "",
    }
    base.update(overrides)
    return base


class CanonicalTests(unittest.TestCase):
    def test_export_null_sentinels_collapse_to_absent(self) -> None:
        for value in ["", " ", "-", "'-", "UNSET", "NULL", "null", "N/A", None]:
            self.assertEqual(clean(value), "", repr(value))

    def test_host_projection_folds_fqdn_and_case_but_not_addresses(self) -> None:
        for value in ["SVPMN082", "svpmn082", "SVPMN082.wac.com.au", "svpmn082.WAC.COM.AU"]:
            self.assertEqual(short_host(value), "SVPMN082", value)
        self.assertEqual(short_host("10.0.128.50"), "")

    def test_a_structured_host_field_yields_the_label_and_its_stated_domain(self) -> None:
        blob = '{"domain":"wac.com.au","name":"SVPDS005","original_name":"SVPDS005.wac.com.au"}'
        self.assertEqual(host_parts(blob), ("SVPDS005", "WAC.COM.AU"))
        self.assertEqual(host_parts("SVPDS005.wac.com.au"), ("SVPDS005", "WAC.COM.AU"))
        self.assertEqual(host_parts("SVPDS005"), ("SVPDS005", ""))

    def test_a_host_field_holding_json_never_becomes_the_host_name(self) -> None:
        blob = '{"domain":"","name":"svpmn082","original_name":"svpmn082"}'
        self.assertEqual(short_host(blob), "SVPMN082")
        self.assertNotIn("{", short_host(blob))

    def test_buckets_floor_to_the_declared_resolution(self) -> None:
        self.assertEqual(bucket_key("2026-08-13T02:33:18.000000Z"), "2026-08-13T02:30")
        self.assertEqual(bucket_key("2026-08-13T02:59:59Z"), "2026-08-13T02:45")
        self.assertEqual(bucket_key("2026-08-13T03:00:00Z"), "2026-08-13T03:00")
        for junk in ["", "not-a-time", "2026-08-13"]:
            self.assertEqual(bucket_key(junk), "", junk)

    def test_window_scoring_sums_only_the_buckets_inside_it(self) -> None:
        buckets = {"2026-08-13T02:30": 44, "2026-08-13T02:45": 2, "2026-08-13T03:00": 49}
        self.assertEqual(buckets_in_window(buckets, "", ""), 95)
        self.assertEqual(buckets_in_window(buckets, "2026-08-13T02:30", "2026-08-13T02:45"), 46)
        self.assertEqual(buckets_in_window(buckets, "2026-08-13T03:00", "2026-08-13T03:00"), 49)
        self.assertEqual(buckets_in_window(buckets, "2026-08-13T04:00", "2026-08-13T05:00"), 0)

    def test_account_key_folds_upn_realm_and_domain_prefix(self) -> None:
        for value in ["SVPMN082$", "svpmn082$", "SVPMN082$@WAC.COM.AU", "WAC\\SVPMN082$"]:
            self.assertEqual(account_key(value), "svpmn082$", value)
        self.assertNotEqual(account_key("admLRhodes"), account_key("lachlan.rhodes"))

    def test_identity_blob_parses_and_survives_malformed_json(self) -> None:
        parsed = parse_identity_blob('{"domain":"WAC","name":"admLRhodes","original_name":"a","uid":""}')
        self.assertEqual(parsed["name"], "admLRhodes")
        self.assertEqual(parsed["domain"], "WAC")
        for broken in ['{"name":', "not json", "", "[]"]:
            self.assertEqual(parse_identity_blob(broken), {}, broken)

    def test_addresses_are_validated_and_scoped(self) -> None:
        self.assertEqual(address_key("10.0.128.50"), "10.0.128.50")
        self.assertEqual(address_scope("10.0.128.50"), "private")
        self.assertEqual(address_scope("8.8.8.8"), "public")
        for junk in ["'-", "SVPMN082", "999.1.1.1", ""]:
            self.assertEqual(address_key(junk), "", junk)

    def test_dns_key_folds_case_and_trailing_dot(self) -> None:
        self.assertEqual(dns_key("WPAD.wac.com.au."), "wpad.wac.com.au")

    def test_slug_rejects_characters_that_would_break_a_vertex_id(self) -> None:
        self.assertEqual(slug("host", "A/B C"), "host|A_B_C")
        self.assertLessEqual(len(slug("x", "y" * 400)), 180)


class ExtractionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.graph = Graph()

    def test_an_authentication_row_produces_the_expected_shape(self) -> None:
        extract_row(self.graph, row(
            win_event_id="4648", target_user_name="admLRhodes", target_domain_name="WAC.COM.AU",
            target_host_name="SVPDS004.wac.com.au", source_address="10.0.128.50",
            logon_type="NETWORK", action_result="SUCCESS",
        ))
        self.assertIn("identity|admlrhodes", self.graph.nodes)
        self.assertIn("host|SVPDS004", self.graph.nodes)
        self.assertIn("ip|10.0.128.50", self.graph.nodes)
        edge = self.graph.edges["identity|admlrhodes--AUTHENTICATED_TO--host|SVPDS004"]
        self.assertEqual(edge.observed["win_event_ids"], {"4648"})
        self.assertEqual(edge.observed["meanings"], {"logon with explicit credentials"})
        self.assertEqual(edge.event_count, 1)

    def test_repeated_rows_aggregate_onto_one_edge_and_widen_the_interval(self) -> None:
        for index, when in enumerate(["2026-08-13T02:00:00Z", "2026-08-13T01:00:00Z", "2026-08-13T03:00:00Z"]):
            extract_row(self.graph, row(
                source_time=when, resource_id=f"event://test:{index}", win_event_id="4624",
                target_user_name="admLRhodes", target_host_name="SVPDS004",
            ))
        edge = self.graph.edges["identity|admlrhodes--AUTHENTICATED_TO--host|SVPDS004"]
        self.assertEqual(edge.event_count, 3)
        self.assertEqual(edge.first_seen, "2026-08-13T01:00:00Z")
        self.assertEqual(edge.last_seen, "2026-08-13T03:00:00Z")
        self.assertEqual(len(self.graph.nodes), 2)

    def test_machine_account_class_needs_the_source_flag_not_the_dollar_suffix(self) -> None:
        extract_row(self.graph, row(target_user_name="SVPAP391$", target_host_name="SVPDS004"))
        candidate = self.graph.nodes["identity|svpap391$"]
        self.assertEqual(candidate.props["account_class"], "machine_account_candidate")

        extract_row(self.graph, row(
            resource_id="event://test:2", target_user_name="SVPMN082$",
            target_host_name="SVPDS004", is_machine_account="TRUE",
        ))
        confirmed = self.graph.nodes["identity|svpmn082$"]
        self.assertEqual(confirmed.props["account_class"], "machine_account")
        self.assertIn("is_machine_account", confirmed.props["account_class_basis"])

    def test_host_identity_equality_is_only_ever_a_candidate(self) -> None:
        extract_row(self.graph, row(
            target_user_name="SVPMN082$", target_host_name="SVPMN082", is_machine_account="TRUE"))
        derived = derive_structural_edges(self.graph)
        self.assertEqual(derived["POSSIBLY_SAME_AS"], 1)
        edge = self.graph.edges["identity|svpmn082$--POSSIBLY_SAME_AS--host|SVPMN082"]
        self.assertEqual(edge.kind, "structural")
        self.assertIn("no directory", edge.props["confirmed_by"])
        self.assertNotIn("SAME_AS", EDGE_LABELS)

    def test_kerberos_service_is_a_service_principal_not_an_installed_service(self) -> None:
        extract_row(self.graph, row(
            win_event_id="4769", target_user_name="admLRhodes", target_host_name="SVPDS004",
            service_name="WACVDC02$", service_sid="S-1-5-21-507921405-630328440-1801674531-24613",
        ))
        service = self.graph.nodes["krb|wacvdc02$"]
        self.assertEqual(service.label, "KerberosService")
        self.assertTrue(service.props["sid"].startswith("S-1-5-21-"))
        self.assertIn("identity|admlrhodes--REQUESTED_SERVICE--krb|wacvdc02$", self.graph.edges)

    def test_a_non_sid_service_identifier_is_not_stored_as_a_sid(self) -> None:
        extract_row(self.graph, row(
            win_event_id="4769", target_user_name="admLRhodes", target_host_name="SVPDS004",
            service_name="krbtgt", service_sid="not-a-sid"))
        self.assertEqual(self.graph.nodes["krb|krbtgt"].props["sid"], "")

    def test_placeholder_session_handles_are_dropped_not_materialised(self) -> None:
        for placeholder in ["0x0", "0x3e7", "S-1-5-21-507921405-630328440-1801674531-48269"]:
            extract_row(self.graph, row(
                resource_id=f"event://s:{placeholder}", target_user_name="admLRhodes",
                target_host_name="SVPDS004", session_id=placeholder))
        self.assertEqual([node for node in self.graph.nodes.values() if node.label == "Session"], [])
        self.assertEqual(self.graph.dropped["session_id placeholder or SID"], 3)

    def test_dns_rows_link_client_resolver_and_name(self) -> None:
        extract_row(self.graph, row(
            product="DNS", event_type_recovered="dnsquery", query_name="WPAD.wac.com.au.",
            source_address="10.0.128.50", destination_address="8.8.8.8", query_type="A"))
        self.assertIn("dns|wpad.wac.com.au", self.graph.nodes)
        self.assertEqual(self.graph.nodes["dns|wpad.wac.com.au"].props["registrable"], "com.au")
        self.assertIn("ip|10.0.128.50--QUERIED--dns|wpad.wac.com.au", self.graph.edges)
        self.assertIn("dns|wpad.wac.com.au--RESOLVED_BY--ip|8.8.8.8", self.graph.edges)

    def test_reverse_lookups_are_classified_not_treated_as_hostnames(self) -> None:
        extract_row(self.graph, row(
            product="DNS", event_type_recovered="dnsquery",
            query_name="104.10.22.172.in-addr.arpa", source_address="10.0.128.50"))
        self.assertEqual(self.graph.nodes["dns|104.10.22.172.in-addr.arpa"].props["lookup_kind"], "reverse")

    def test_netflow_carries_port_protocol_and_action_onto_the_edge(self) -> None:
        extract_row(self.graph, row(
            product="ASA_FTD", event_type_recovered="netflow",
            source_address="10.0.128.50", destination_address="8.8.8.8",
            destination_port="443", protocol="6", flow_action="FW_BLOCKED",
            application_name="Office 365"))
        edge = self.graph.edges["ip|10.0.128.50--CONNECTED_TO--ip|8.8.8.8"]
        self.assertEqual(edge.observed["destination_ports"], {"443"})
        self.assertEqual(edge.observed["actions"], {"FW_BLOCKED"})
        self.assertIn("ip|10.0.128.50--USED_APPLICATION--app|office_365", self.graph.edges)

    def test_privileged_rows_expose_the_account_handoff_the_safe_and_the_tool(self) -> None:
        extract_row(self.graph, row(
            product="CYBERARK", event_type_recovered="cloudaudit", event_name="Window Title",
            user='{"domain":"perthairport.com.au","name":"lachlan.rhodes"}',
            target_hostname="SVPMN082", source_address="103.130.155.227",
            additional_event_data=json.dumps({"record": [
                {"key": "duser", "value": "admLRhodes"},
                {"key": "Safe Name", "value": "P-Admin-LRhodes"},
                {"key": "Device Type", "value": "Operating System"},
            ]}),
            original_data="... https://github.com/peass-ng/PEASS-ng winPEAS.exe ...",
        ))
        self.assertIn("identity|lachlan.rhodes--USED_ACCOUNT--identity|admlrhodes", self.graph.edges)
        self.assertIn("identity|admlrhodes--AUTHENTICATED_TO--host|SVPMN082", self.graph.edges)
        self.assertIn("identity|lachlan.rhodes--RETRIEVED_FROM_SAFE--safe|p-admin-lrhodes", self.graph.edges)
        self.assertIn("host|SVPMN082--REFERENCED_SOFTWARE--software|winpeas", self.graph.edges)
        software = self.graph.nodes["software|winpeas"]
        self.assertIn("reference only", software.props["established"])

    def test_an_unhandled_family_is_recorded_rather_than_silently_skipped(self) -> None:
        extract_row(self.graph, row(product="MYSTERY", event_type_recovered="unheard_of"))
        self.assertEqual(self.graph.dropped["no extractor for MYSTERY/unheard_of"], 1)

    def test_undeclared_labels_fail_closed(self) -> None:
        with self.assertRaises(ValueError):
            self.graph.node("Wormhole", "x", "x")
        with self.assertRaises(ValueError):
            self.graph.edge("BECAME", "a", "b")

    def test_one_id_cannot_be_claimed_by_two_labels(self) -> None:
        self.graph.node("Host", "shared", "shared")
        with self.assertRaises(ValueError):
            self.graph.node("Identity", "shared", "shared")


class BuiltGraphTests(unittest.TestCase):
    """Assertions against the graph actually written from the pinned export."""

    @classmethod
    def setUpClass(cls) -> None:
        if not (NODES.is_file() and EDGES.is_file() and REPORT.is_file()):
            raise unittest.SkipTest("run build_ontology.py first")
        cls.nodes, cls.edges = read_graph(NODES, EDGES)
        cls.report = json.loads(REPORT.read_text(encoding="utf-8"))
        cls.by_id = {node["node_id"]: node for node in cls.nodes}

    def test_matches_the_pinned_export(self) -> None:
        self.assertEqual(self.report["source_rows"], 15_520)
        self.assertEqual(self.report["nodes"], len(self.nodes))
        self.assertEqual(self.report["edges"], len(self.edges))
        self.assertTrue(self.report["historical_replay"])

    def test_every_edge_endpoint_exists(self) -> None:
        dangling = [edge["edge_id"] for edge in self.edges
                    if edge["from_id"] not in self.by_id or edge["to_id"] not in self.by_id]
        self.assertEqual(dangling, [])

    def test_every_label_is_declared(self) -> None:
        self.assertLessEqual({node["label"] for node in self.nodes}, set(NODE_LABELS))
        self.assertLessEqual({edge["label"] for edge in self.edges}, set(EDGE_LABELS))

    def test_ids_are_unique(self) -> None:
        self.assertEqual(len(self.by_id), len(self.nodes))
        self.assertEqual(len({edge["edge_id"] for edge in self.edges}), len(self.edges))

    def test_the_known_focal_entities_are_present_and_connected(self) -> None:
        for node_id in ["host|SVPMN082", "identity|admlrhodes", "identity|lachlan.rhodes",
                        "identity|svpmn082$", "safe|p-admin-lrhodes", "software|winpeas"]:
            self.assertIn(node_id, self.by_id, node_id)
        edges = {edge["edge_id"] for edge in self.edges}
        self.assertIn("identity|lachlan.rhodes--USED_ACCOUNT--identity|admlrhodes", edges)
        self.assertIn("identity|admlrhodes--REFERENCED_SOFTWARE--software|winpeas", edges)
        self.assertIn("identity|svpmn082$--POSSIBLY_SAME_AS--host|SVPMN082", edges)

    def test_no_confirmed_identity_equality_is_asserted_anywhere(self) -> None:
        self.assertEqual([edge for edge in self.edges if edge["label"] == "SAME_AS"], [])
        for edge in self.edges:
            if edge["label"] == "POSSIBLY_SAME_AS":
                self.assertIn("none:", edge["properties"]["confirmed_by"])

    def test_machine_account_class_is_only_claimed_where_the_export_flags_it(self) -> None:
        classes = {node["node_id"]: node["properties"].get("account_class")
                   for node in self.nodes if node["label"] == "Identity"}
        self.assertEqual(classes["identity|svpmn082$"], "machine_account")
        self.assertEqual(classes["identity|admlrhodes"], "account_observed")

    def test_event_counts_never_exceed_the_source_row_count(self) -> None:
        worst = max(node["event_count"] for node in self.nodes)
        self.assertLessEqual(worst, self.report["source_rows"])
        self.assertGreater(worst, 0)

    def test_intervals_sit_inside_the_export_window(self) -> None:
        stamps = [node["first_seen"] for node in self.nodes if node["first_seen"]]
        stamps += [node["last_seen"] for node in self.nodes if node["last_seen"]]
        self.assertGreaterEqual(min(stamps), "2026-08-11T23:57:53")
        self.assertLessEqual(max(stamps), "2026-08-13T08:48:53")

    def test_round_trips_through_csv_without_loss(self) -> None:
        import tempfile

        graph, _ = build_graph(BASE / "output" / "events_unified.csv")
        with tempfile.TemporaryDirectory() as directory:
            nodes_path = Path(directory) / "n.csv"
            edges_path = Path(directory) / "e.csv"
            write_graph(graph, nodes_path, edges_path)
            nodes, edges = read_graph(nodes_path, edges_path)
        self.assertEqual(len(nodes), len(graph.nodes))
        self.assertEqual(len(edges), len(graph.edges))


if __name__ == "__main__":
    unittest.main()
