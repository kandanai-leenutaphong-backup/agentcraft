import copy
import tempfile
import unittest
from unittest.mock import patch

from core import EvidenceReader, load_bundle, materialize_view
from fixtures import OWNED_ROOT, TinyPack
from operations import OBSERVABLE_CLASSES, power_only, reference
from replay import compare, evaluate


class PredictorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=OWNED_ROOT, prefix=".test-")
        self.addCleanup(self.temp.cleanup)
        self.fixture = TinyPack(self.temp.name)

    def view(self, index=0):
        self.fixture.write()
        bundle = load_bundle(self.fixture.pack, self.fixture.source)
        return materialize_view(bundle, bundle.scenarios[index], "operations", 1)

    def test_reference_detects_generator_busbar_and_restoration(self):
        for index, event_type in enumerate(("generator_trip", "busbar_trip", "restoration")):
            view = self.view(index)
            result = reference(view, EvidenceReader(view))
            self.assertEqual(result["status"], "event")
            self.assertEqual(result["event_type"], event_type)
            self.assertEqual(result["cause_status"], "not_established")
            self.assertTrue(result["evidence_ids"])

    def test_power_only_baseline_misses_busbar_without_mw_loss(self):
        view = self.view(1)
        self.assertEqual(power_only(view, EvidenceReader(view))["status"], "no_event")

    def test_available_alarms_correlate_but_delayed_alarm_does_not_leak(self):
        self.fixture.alarms = [
            {"row_id": "a01", "scenario_id": "s001", "ts": "2025-10-16T03:34:29Z", "available_at": "2025-10-16T03:34:30Z",
             "asset_id": "UNIT_A", "code": "GENERATOR_TRIP", "state": "active", "severity": "critical", "message": "Unit trip indication", "synthetic": "true"},
            {"row_id": "a02", "scenario_id": "s001", "ts": "2025-10-16T03:34:29Z", "available_at": "2025-10-16T03:40:00Z",
             "asset_id": "UNIT_A", "code": "GENERATOR_TRIP", "state": "active", "severity": "critical", "message": "FUTURE SENTINEL", "synthetic": "true"},
        ]
        view = self.view()
        result = reference(view, EvidenceReader(view))
        self.assertIn(view["evidence"]["alarms"][0]["row_id"], result["evidence_ids"])
        self.assertEqual(len(view["evidence"]["alarms"]), 1)

    def test_no_event_controls_and_preexisting_outage(self):
        for value in ("298", "0"):
            for row in self.fixture.scada:
                if row["scenario_id"] == "s001":
                    row["value"] = value if row["point"] == "active_power_mw" else ("1" if row["point"] == "breaker_closed" else "20") if value != "0" else "0"
            view = self.view()
            self.assertEqual(reference(view, EvidenceReader(view))["status"], "no_event")

    def test_all_unavailable_and_bad_latest_are_not_no_event(self):
        view = self.view()
        view["evidence"]["scada"] = []
        view["quality"] = []
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "insufficient_evidence")
        for row in self.fixture.scada:
            if row["scenario_id"] == "s001":
                row["quality"] = "bad"
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "insufficient_evidence")

    def test_stale_and_contradictory_signals_refuse_certainty(self):
        view = self.view()
        view["decision_time"] = "2025-10-16T03:44:31Z"
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "insufficient_evidence")
        for row in self.fixture.scada:
            if row["scenario_id"] == "s001" and row["point"] == "breaker_closed":
                row["value"] = "1"
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "insufficient_evidence")

    def test_actions_require_available_scoped_policy_and_tools(self):
        self.fixture.make_action()
        view = self.view()
        result = reference(view, EvidenceReader(view))
        self.assertEqual(result["action_ids"], self.fixture.knowledge[0]["action_rules"][0]["action_ids"])
        self.assertTrue(all(action["rationale"] and action["evidence_ids"] for action in result["action_evidence"]))
        view["tools"].remove("topology")
        view["evidence"].pop("topology")
        denied = reference(view, EvidenceReader(view))
        self.assertEqual(denied["gap"], "tooling_gap")
        self.assertEqual(denied["action_ids"], ["request_tool_access", "escalate_to_operator"])

    def test_ids_and_names_do_not_select_a_response(self):
        view = self.view()
        original = reference(view, EvidenceReader(view))
        renamed = copy.deepcopy(view)
        renamed["case_id"] = "opaque-other-case"
        renamed["assets"][0]["name"] = "Unseen place"
        self.assertEqual(reference(renamed, EvidenceReader(renamed)), original)

    def test_action_known_event_without_pretransition_succeeds(self):
        scenario = self.fixture.make_action()
        event_start = scenario["event_conditions"][0]["event_interval"]["start"]
        self.fixture.scada = [row for row in self.fixture.scada if row["scenario_id"] != scenario["scenario_id"] or row["ts"] >= event_start]
        view = self.view()
        with patch("operations._observe", side_effect=AssertionError("action must not redetect")):
            result = reference(view, EvidenceReader(view))
        self.assertEqual(result["status"], "event")
        self.assertEqual(result["action_ids"], self.fixture.knowledge[0]["action_rules"][0]["action_ids"])
        self.assertIsNone(result["event_time"])
        self.assertEqual(result["event_interval"], scenario["event_conditions"][0]["event_interval"])
        self.assertEqual(result["communication"]["state"], "verified")
        for detail in ("UNIT_A", event_start, "generator_trip", "breaker_closed", "Cause is not established", "Next steps"):
            self.assertIn(detail, result["message"])
        missing = copy.deepcopy(view)
        missing["evidence"]["scada"] = [row for row in missing["evidence"]["scada"] if row["point"] != "breaker_closed"]
        refused = reference(missing, EvidenceReader(missing))
        self.assertEqual(refused["status"], "insufficient_evidence")
        self.assertEqual(refused["gap"], "data_gap")
        self.assertEqual(refused["action_ids"], ["request_missing_data", "escalate_to_operator"])

    def test_action_known_event_rejects_bad_stale_conflicting_current_state(self):
        self.fixture.make_action()
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "event")
        for failure in ("bad", "stale", "conflicting", "protection"):
            changed = copy.deepcopy(view)
            if failure == "bad":
                changed["quality"][-1]["quality"] = "bad"
            elif failure == "stale":
                changed["decision_time"] = "2025-10-16T03:44:31Z"
            elif failure == "conflicting":
                for row in changed["evidence"]["scada"]:
                    if row["point"] == "breaker_closed":
                        row["value"] = 1
            else:
                changed["evidence"]["alarms"] = [{"row_id": "return01", "asset_id": "UNIT_A", "ts": view["decision_time"],
                                                  "available_at": view["decision_time"], "code": "RETURN_TO_SERVICE", "state": "cleared",
                                                  "severity": "info", "message": "Synthetic return indication", "synthetic": True}]
            with self.subTest(failure=failure):
                result = reference(changed, EvidenceReader(changed))
                self.assertEqual(result["status"], "insufficient_evidence")
                self.assertEqual(result["gap"], "data_gap")
                self.assertEqual(result["action_ids"], ["request_missing_data", "escalate_to_operator"])

    def test_action_known_restoration_uses_current_state_not_old_transition(self):
        scenario = self.fixture.make_action(2)
        event_start = scenario["event_conditions"][0]["event_interval"]["start"]
        self.fixture.scada = [row for row in self.fixture.scada if row["scenario_id"] != scenario["scenario_id"] or row["ts"] >= event_start]
        view = self.view(2)
        self.assertEqual(reference(view, EvidenceReader(view))["action_ids"], self.fixture.knowledge[0]["action_rules"][2]["action_ids"])
        for row in view["evidence"]["scada"]:
            row["value"] = 0
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "insufficient_evidence")

    def test_action_known_multiple_notifications_require_all_assets_and_scopes(self):
        self.fixture.make_action()
        view = self.view()
        second_asset = copy.deepcopy(view["assets"][0])
        second_asset["asset_id"] = "SECOND_UNIT"
        view["assets"].append(second_asset)
        condition = copy.deepcopy(view["event_conditions"][0])
        condition.update({"notification_id": "e-second-notification", "asset_ids": ["SECOND_UNIT"]})
        view["event_conditions"].append(condition)
        for tool in ("scada", "topology"):
            view["evidence"][tool].extend([{**row, "asset_id": "SECOND_UNIT", "row_id": "second-" + row["row_id"]}
                                            for row in list(view["evidence"][tool])])
        view["evidence"]["knowledge"][0]["asset_ids"].append("SECOND_UNIT")
        result = reference(view, EvidenceReader(view))
        self.assertEqual(result["status"], "event")
        self.assertEqual(result["asset_ids"], ["SECOND_UNIT", "UNIT_A"])
        self.assertIsNone(result["gap"])
        unscoped = copy.deepcopy(view)
        unscoped["evidence"]["knowledge"][0]["asset_ids"].remove("SECOND_UNIT")
        self.assertEqual(reference(unscoped, EvidenceReader(unscoped))["gap"], "knowledge_gap")
        view["evidence"]["scada"] = [row for row in view["evidence"]["scada"] if row["asset_id"] != "SECOND_UNIT"]
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "insufficient_evidence")

    def labels(self, view, index=0):
        expected = copy.deepcopy(self.fixture.scenarios[index]["expected"])
        return [{"case_id": view["case_id"], "split": self.fixture.scenarios[index]["split"], "expected": expected,
                 "event_time_tolerance_seconds": 0, "max_detection_latency_seconds": 300,
                 "observable_classification": OBSERVABLE_CLASSES.get(expected["event_type"])}]

    def test_missing_outputs_and_errors_stay_in_denominator(self):
        view = self.view()
        missing = evaluate([view], self.labels(view), lambda public, reader: None)
        self.assertEqual(missing["metrics"]["overall"]["cases"], 1)
        self.assertEqual(missing["metrics"]["overall"]["missing_predictions"], 1)
        self.assertEqual(missing["metrics"]["overall"]["event_recall"], 0)

        def broken(public, reader):
            raise RuntimeError("deliberate fixture error")

        failed = evaluate([view], self.labels(view), broken)
        self.assertEqual(failed["metrics"]["overall"]["errors"], 1)
        self.assertEqual(failed["metrics"]["overall"]["event_recall"], 0)

    def test_missing_action_output_never_gets_empty_action_credit(self):
        self.fixture.make_action()
        view = self.view()
        outcome = evaluate([view], self.labels(view), lambda public, reader: None)
        self.assertEqual(outcome["metrics"]["overall"]["action_exact_match"], 0)
        self.assertEqual(outcome["metrics"]["overall"]["action_prerequisites"], 0)

    def test_planned_transition_is_a_no_event_control(self):
        self.fixture.alarms = [{"row_id": "planned01", "scenario_id": "s001", "ts": "2025-10-16T03:34:00Z",
                                "available_at": "2025-10-16T03:34:00Z", "asset_id": "UNIT_A", "code": "PLANNED_SHUTDOWN",
                                "state": "active", "severity": "info", "message": "Synthetic planned shutdown notice", "synthetic": "true"}]
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "no_event")

    def test_benign_trip_monitor_alarm_is_not_a_new_trip(self):
        for row in self.fixture.scada:
            if row["scenario_id"] == "s001":
                row["value"] = "0"
        self.fixture.alarms = [{"row_id": "monitor01", "scenario_id": "s001", "ts": "2025-10-16T03:34:00Z",
                                "available_at": "2025-10-16T03:34:00Z", "asset_id": "UNIT_A", "code": "TRIP_CIRCUIT_HEALTH",
                                "state": "active", "severity": "info", "message": "Synthetic benign health monitor", "synthetic": "true"}]
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "no_event")

    def test_dispatch_availability_is_not_electrical_state(self):
        self.fixture.scada.append({"row_id": "available01", "scenario_id": "s001", "ts": "2025-10-16T03:34:31Z",
                                   "available_at": "2025-10-16T03:34:31Z", "asset_id": "UNIT_A", "point": "available",
                                   "value": "1", "unit": "1", "quality": "good", "synthetic": "true"})
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "event")

    def test_generator_terminal_excitation_does_not_define_connection(self):
        for row in self.fixture.scada:
            if row["scenario_id"] == "s001" and row["point"] == "voltage_kv":
                row["value"] = "20"
        view = self.view()
        result = reference(view, EvidenceReader(view))
        self.assertEqual((result["status"], result["event_type"]), ("event", "generator_trip"))
        self.assertEqual(result["event_time"], "2025-10-16T03:34:29Z")
        for row in self.fixture.scada:
            if row["scenario_id"] == "s001":
                row["value"] = "20" if row["point"] == "voltage_kv" and row["ts"] >= "2025-10-16T03:34:29Z" else "0"
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "no_event")

    def test_generator_connected_without_terminal_voltage_refuses(self):
        for row in self.fixture.scada:
            if row["scenario_id"] == "s001":
                row["value"] = {"active_power_mw": "298", "breaker_closed": "1", "voltage_kv": "0"}[row["point"]]
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "insufficient_evidence")

    def test_generator_action_allows_residual_voltage_but_requires_quality(self):
        self.fixture.make_action()
        for row in self.fixture.scada:
            if row["scenario_id"] == "s001" and row["point"] == "voltage_kv":
                row["value"] = "20"
        view = self.view()
        result = reference(view, EvidenceReader(view))
        self.assertEqual(result["status"], "event")
        labels = self.labels(view)
        labels[0]["expected"]["action_ids"] = self.fixture.knowledge[0]["action_rules"][0]["action_ids"]
        evaluation = evaluate([view], labels, reference)
        self.assertEqual(evaluation["metrics"]["overall"]["action_prerequisites"], 1)
        for quality in view["quality"]:
            if quality["point"] == "voltage_kv":
                quality["quality"] = "bad"
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "insufficient_evidence")

    def test_latch_snapshot_is_state_not_a_new_trip(self):
        for row in self.fixture.scada:
            if row["scenario_id"] == "s001":
                row["value"] = "0"
        self.fixture.alarms = [{"row_id": "latch01", "scenario_id": "s001", "ts": "2025-10-16T03:34:00Z",
                                "available_at": "2025-10-16T03:34:00Z", "asset_id": "UNIT_A", "code": "UNIT_TRIP_LATCHED",
                                "state": "active", "severity": "critical", "message": "Initial existing latch snapshot", "synthetic": "true"}]
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "no_event")
        self.fixture.make_action()
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["status"], "event")
        self.fixture.make_action(2)
        restored = self.view(2)
        self.assertEqual(reference(restored, EvidenceReader(restored))["status"], "event")
        restored["evidence"]["alarms"].append({
            "row_id": "latch-after-return", "asset_id": restored["assets"][0]["asset_id"],
            "ts": restored["decision_time"], "available_at": restored["decision_time"],
            "code": "UNIT_TRIP_LATCHED", "state": "active", "severity": "critical",
            "message": "Initial existing latch snapshot", "synthetic": True,
        })
        self.assertEqual(reference(restored, EvidenceReader(restored))["status"], "insufficient_evidence")

    def test_knowledge_validity_and_asset_scope_cannot_expand_actions(self):
        self.fixture.make_action()
        self.fixture.knowledge[0]["valid_to"] = "2025-10-16T03:34:30Z"
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["gap"], "knowledge_gap")
        self.fixture.knowledge[0].pop("valid_to")
        self.fixture.knowledge[0]["asset_ids"] = ["BUS_A"]
        view = self.view()
        self.assertEqual(reference(view, EvidenceReader(view))["gap"], "knowledge_gap")

    def test_spurious_asset_confirmed_cause_and_forbidden_action_fail(self):
        view = self.view()
        mutations = ({"asset_ids": ["UNIT_B"]}, {"cause_status": "confirmed"}, {"action_ids": ["operate_switchgear"]})
        for mutation in mutations:
            def predict(public, reader):
                return {**reference(public, reader), **mutation}
            outcome = evaluate([view], self.labels(view), predict)
            self.assertFalse(outcome["cases"][0]["passed"])

    def test_required_classification_cause_and_gap_mismatches_fail(self):
        view = self.view()
        self.assertTrue(evaluate([view], self.labels(view), reference)["cases"][0]["passed"])
        for field, value, failure in (("classification", None, "classification"),
                                      ("classification", "wrong observable class", "classification"),
                                      ("cause_status", "hypothesis", "cause status"),
                                      ("gap", "data_gap", "gap:")):
            with self.subTest(field=field, value=value):
                def predict(public, reader):
                    result = reference(public, reader)
                    if value is None:
                        result.pop(field)
                    else:
                        result[field] = value
                    if field == "cause_status":
                        result["hypotheses"] = ["A simulated possibility, not an established cause."]
                    return result
                case = evaluate([view], self.labels(view), predict)["cases"][0]
                self.assertFalse(case["passed"])
                self.assertIsNone(case["error"])
                self.assertTrue(any(failure in detail for detail in case["failures"]))

    def test_minute_interval_accepts_synthetic_seconds_but_not_next_minute(self):
        view = self.view(1)
        label = self.labels(view, 1)
        for timestamp, expected in (("2026-01-29T00:08:37Z", True), ("2026-01-29T00:09:00Z", False)):
            def predict(public, reader):
                return {**reference(public, reader), "event_time": timestamp}
            outcome = evaluate([view], label, predict)
            self.assertEqual(outcome["cases"][0]["passed"], expected)

    def test_no_event_and_expected_insufficiency_score_correctly(self):
        scenario = self.fixture.scenarios[0]
        scenario["expected"].update({"status": "no_event", "event_type": None, "asset_ids": [], "event_interval": None})
        for row in self.fixture.scada:
            if row["scenario_id"] == "s001":
                row["value"] = {"active_power_mw": "298", "breaker_closed": "1", "voltage_kv": "20"}[row["point"]]
        view = self.view()
        self.assertTrue(evaluate([view], self.labels(view), reference)["cases"][0]["passed"])
        scenario["expected"]["status"] = "insufficient_evidence"
        scenario["expected"]["gap"] = "data_gap"
        view["evidence"]["scada"] = []
        view["quality"] = []
        self.assertTrue(evaluate([view], self.labels(view), reference)["cases"][0]["passed"])

    def test_controlled_ablations_expose_each_gap(self):
        view = self.view()
        runs = compare([view], self.labels(view), baseline=power_only, reference=reference)
        self.assertTrue(runs["reference"]["cases"][0]["passed"])
        for ablation, gap in (("drop_records", "data_gap"), ("deny_scada", "tooling_gap"), ("wrong_rule", "logic_gap"), ("confirm_cause", "unsupported_inference")):
            case = runs[f"reference.{ablation}"]["cases"][0]
            self.assertEqual(case["failure_gap"], gap)
            self.assertTrue(case["trace"])
            self.assertTrue(case["remedy"])

    def test_action_prerequisite_scoring_refuses_ungrounded_action(self):
        self.fixture.make_action()
        self.fixture.scenarios[0]["expected"]["action_ids"] = self.fixture.knowledge[0]["action_rules"][0]["action_ids"].copy()
        view = self.view()
        self.assertTrue(evaluate([view], self.labels(view), reference)["cases"][0]["passed"])

        def no_basis(public, reader):
            result = reference(public, reader)
            result["action_evidence"] = []
            return result

        outcome = evaluate([view], self.labels(view), no_basis)
        self.assertFalse(outcome["cases"][0]["passed"])
        self.assertEqual(outcome["metrics"]["overall"]["action_prerequisites"], 0)

    def test_action_scoring_preserves_intervals_and_requires_communication(self):
        scenario = self.fixture.make_action(1)
        scenario["expected"]["action_ids"] = self.fixture.knowledge[0]["action_rules"][1]["action_ids"].copy()
        view = self.view(1)
        self.assertTrue(evaluate([view], self.labels(view, 1), reference)["cases"][0]["passed"])
        for field, value in (("event_time", "2026-01-29T00:08:30Z"), ("asset_ids", ["UNIT_A"]),
                             ("event_type", "generator_trip"), ("event_interval", {"start": "2026-01-29T00:08:00Z", "end": "2026-01-29T00:08:01Z"}),
                             ("communication", None), ("gap", "knowledge_gap")):
            def predict(public, reader):
                result = reference(public, reader)
                if value is None:
                    result.pop(field)
                else:
                    result[field] = value
                return result
            with self.subTest(field=field):
                case = evaluate([view], self.labels(view, 1), predict)["cases"][0]
                self.assertIsNone(case["error"])
                self.assertFalse(case["passed"])

    def test_action_scoring_requires_queried_current_scada_not_notifications(self):
        scenario = self.fixture.make_action()
        scenario["expected"]["action_ids"] = self.fixture.knowledge[0]["action_rules"][0]["action_ids"].copy()
        view = self.view()
        self.assertTrue(evaluate([view], self.labels(view), reference)["cases"][0]["passed"])

        def only_notification(public, reader):
            result = reference(public, reader)
            result["evidence_ids"] = [public["event_conditions"][0]["notification_id"]]
            result["communication"]["evidence_ids"] = result["evidence_ids"].copy()
            return result

        case = evaluate([view], self.labels(view), only_notification)["cases"][0]
        self.assertFalse(case["passed"])
        self.assertTrue(any("current-state" in failure for failure in case["failures"]))

    def test_action_scoring_requires_latest_applicable_alarm_not_cleared_or_benign(self):
        scenario = self.fixture.make_action()
        rule = self.fixture.knowledge[0]["action_rules"][0]
        rule["required_tools"].append("alarms")
        scenario["expected"]["action_ids"] = rule["action_ids"].copy()
        self.fixture.alarms = [{"row_id": "trip-active", "scenario_id": scenario["scenario_id"], "asset_id": "UNIT_A",
                                "ts": "2025-10-16T03:34:29Z", "available_at": "2025-10-16T03:34:30Z",
                                "code": "GENERATOR_TRIP", "state": "active", "severity": "critical",
                                "message": "Synthetic trip indication", "synthetic": "true"}]
        view = self.view()
        positive = evaluate([view], self.labels(view), reference)["cases"][0]
        self.assertTrue(positive["passed"])
        for failure in ("cleared", "benign"):
            changed = copy.deepcopy(view)
            if failure == "cleared":
                changed["evidence"]["alarms"].append({**changed["evidence"]["alarms"][0], "row_id": "trip-cleared",
                                                      "ts": view["decision_time"], "available_at": view["decision_time"], "state": "cleared"})
            else:
                changed["evidence"]["alarms"][0]["code"] = "TRIP_CIRCUIT_HEALTH"
            self.assertEqual(reference(changed, EvidenceReader(changed))["gap"], "data_gap")

            def stale_recommendation(public, reader):
                for tool in public["tools"]:
                    reader.query(tool)
                return copy.deepcopy(positive["produced"])

            with self.subTest(failure=failure):
                case = evaluate([changed], self.labels(changed), stale_recommendation)["cases"][0]
                self.assertFalse(case["passed"])
                self.assertTrue(any("unmet alarms prerequisite" in detail for detail in case["failures"]))

    def test_action_scoring_keeps_expected_gap_and_missing_error_denominators(self):
        scenario = self.fixture.make_action()
        scenario["expected"].update({"status": "insufficient_evidence", "event_type": None, "asset_ids": [], "event_interval": None,
                                      "gap": "data_gap", "action_ids": ["request_missing_data", "escalate_to_operator"]})
        view = self.view()
        view["evidence"]["scada"] = []
        view["quality"] = []
        self.assertTrue(evaluate([view], self.labels(view), reference)["cases"][0]["passed"])

        def wrong_gap(public, reader):
            return {**reference(public, reader), "gap": None}

        def broken(public, reader):
            raise RuntimeError("deliberate action failure")

        for predictor in (wrong_gap, lambda public, reader: None, broken):
            measured = evaluate([view], self.labels(view), predictor)
            self.assertFalse(measured["cases"][0]["passed"])
            self.assertEqual(measured["metrics"]["action"]["cases"], 1)
            self.assertEqual(measured["metrics"]["action"]["action_gap_accuracy"], 0)
            self.assertIsNone(measured["metrics"]["action"]["event_recall"])

    def test_detection_metrics_unchanged_when_correct_actions_are_appended(self):
        detection = self.view()
        detection_label = self.labels(detection)
        before = evaluate([detection], detection_label, reference)
        scenario = self.fixture.make_action()
        scenario["expected"]["action_ids"] = self.fixture.knowledge[0]["action_rules"][0]["action_ids"].copy()
        action = self.view()
        action["case_id"] += "-action"
        after = evaluate([detection, action], detection_label + self.labels(action), reference)
        self.assertTrue(all(case["passed"] for case in after["cases"]))
        self.assertEqual(before["metrics"]["detection"], after["metrics"]["detection"])
        for metric in ("expected_events", "predicted_events", "event_precision", "event_recall", "false_positives", "false_negatives",
                       "localization_precision", "localization_recall", "exact_localization", "time_accuracy", "observable_classification_accuracy",
                       "detection_latency_budget_accuracy", "no_event_false_positives"):
            self.assertEqual(before["metrics"]["overall"][metric], after["metrics"]["overall"][metric], metric)
        self.assertIsNone(after["metrics"]["action"]["event_precision"])
        self.assertEqual(after["metrics"]["action"]["action_input_consistency"], 1)

        def wrong_detection(public, reader):
            result = reference(public, reader)
            if public["task"] == "detection":
                result.update({"status": "no_event", "event_type": None, "asset_ids": [], "event_time": None, "classification": None})
            return result

        failed = evaluate([detection, action], detection_label + self.labels(action), wrong_detection)
        self.assertEqual(failed["metrics"]["overall"]["event_recall"], 0)
        self.assertEqual(failed["metrics"]["overall"]["false_negatives"], 1)
        self.assertEqual(failed["metrics"]["action"]["passed_cases"], 1)

    def test_defer_baseline_gets_safety_but_not_missing_prerequisite_credit(self):
        scenario = self.fixture.make_action()
        scenario["expected"]["action_ids"] = self.fixture.knowledge[0]["action_rules"][0]["action_ids"].copy()
        view = self.view()
        positive = evaluate([view], self.labels(view), reference)
        self.assertTrue(positive["cases"][0]["passed"])
        self.assertEqual(positive["metrics"]["action"]["action_prerequisites"], 1)
        deferred = evaluate([view], self.labels(view), power_only)
        self.assertFalse(deferred["cases"][0]["passed"])
        self.assertEqual(deferred["metrics"]["action"]["action_prerequisites"], 0)
        self.assertEqual(deferred["metrics"]["action"]["action_prerequisite_safety"], 1)

    def test_detection_rejects_extra_operational_recommendations(self):
        view = self.view()
        self.assertTrue(evaluate([view], self.labels(view), reference)["cases"][0]["passed"])
        for action in ("assess_system_strength", "operate_switchgear", "dispatch_without_authorization"):
            def predict(public, reader):
                return {**reference(public, reader), "action_ids": [action]}
            self.assertFalse(evaluate([view], self.labels(view), predict)["cases"][0]["passed"])


if __name__ == "__main__":
    unittest.main()