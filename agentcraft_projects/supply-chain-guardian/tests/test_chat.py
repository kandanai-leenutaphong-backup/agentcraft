"""Offline regression checks: python3 -m unittest discover -s tests -v."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from agent import app as api


IDS = [
    "scenario-01-clear-disruption",
    "scenario-02-cascading-disruption",
    "scenario-03-no-action-needed",
    "scenario-04-insufficient-evidence",
]


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.cards = {
            sid: SimpleNamespace(
                state="Requires Approval" if i < 2 else "Monitoring",
                confidence=0.8, hypothesis="A delay affects production.",
                execution_result=None,
                to_dict=lambda: {
                    "blast_radius": {"shipment_id": "S102", "material_id": "RM-14"},
                    "foundry_iq_evidence": {"data": [{"id": "POLICY-1"}]},
                    "web_iq_evidence": {"mocked": True, "data": {}},
                    "work_iq_evidence": {"data": None},
                },
            ) for i, sid in enumerate(IDS)
        }
        self.patches = [
            patch.object(api, "_cards", self.cards),
            patch.object(api, "_scenarios_by_id", {sid: {"id": sid} for sid in IDS}),
            patch.object(api, "refresh_evidence"),
            patch.object(api, "simulate_new_disruption"),
            patch.object(api, "apply_decision"),
        ]
        for item in self.patches:
            item.start()
            self.addCleanup(item.stop)

    def test_reference_forms(self):
        for reference, index in [
            ("first one", 0), ("1", 0), ("01", 0), ("1st", 0), ("scenario 2", 1),
            ("scenario-02", 1), ("clear", 0), ("cascading", 1), ("cascad", 1),
            ("insufficient", 3), ("no action", 2), ("no-action", 2),
            ("fourth", 3), (IDS[1], 1),
        ]:
            with self.subTest(reference=reference):
                self.assertEqual(api._match_scenario_id(reference), IDS[index])

    def test_ambiguous_and_unknown_references_never_act(self):
        for reference in [
            "disruption", "1 and 2", "clear cascading", f"{IDS[0]} and {IDS[1]}",
            "99", "scenario 99", "nothing", "1 and 99", "scenario-01-nonexistent",
        ]:
            with self.subTest(reference=reference):
                self.assertIsNone(api._match_scenario_id(reference))
                response = api._handle_chat_command("approve " + reference)
                self.assertFalse(response["action_taken"])
                self.assertIsNone(response["scenario_id"])
                self.assertIn(IDS[0], response["reply"])
        api.apply_decision.assert_not_called()

    def test_response_contract_and_guidance(self):
        for message in ("", "help", "list", "first one", "explain 1", "why cascading", "status 3"):
            with self.subTest(message=message):
                response = api._handle_chat_command(message)
                self.assertEqual(set(response), {"reply", "action_taken", "scenario_id", "suggestions"})
                self.assertGreaterEqual(len(response["suggestions"]), 2)
                self.assertLessEqual(len(response["suggestions"]), 5)
                self.assertFalse(response["action_taken"])
        response = api._handle_chat_command("explain 1")
        self.assertIn(f"approve {IDS[0]}", response["suggestions"])
        self.assertIn(f"reject {IDS[0]}", response["suggestions"])
        self.assertIn("\n\n", response["reply"])
        self.assertIn("\n- Fabric IQ:", response["reply"])
        self.assertIn("fallback scenario evidence", response["reply"])
        self.assertNotIn(f"approve {IDS[2]}", api._handle_chat_command("explain 3")["suggestions"])
        api.refresh_evidence.assert_not_called()
        api.simulate_new_disruption.assert_not_called()
        api.apply_decision.assert_not_called()

    def test_actions_require_explicit_command_and_pending_state(self):
        for message in (
            "don't approve 1", "why approve 1", "disapprove 1", "approve 1 and reject 1",
            "approve 1 not now", "explain 1 simulate", "approve 3", "reject 4",
        ):
            self.assertFalse(api._handle_chat_command(message)["action_taken"], message)
        api.apply_decision.assert_not_called()
        api.simulate_new_disruption.assert_not_called()

        def decision(card, value):
            card.state = "Executed" if value == "approved" else "Rejected"

        api.apply_decision.side_effect = decision
        self.assertTrue(api._handle_chat_command("approve first")["action_taken"])
        api.apply_decision.assert_called_once_with(self.cards[IDS[0]], "approved")
        self.assertFalse(api._handle_chat_command("approve first")["action_taken"])
        self.assertTrue(api._handle_chat_command("reject cascading")["action_taken"])
        self.assertFalse(api._handle_chat_command("reject cascading")["action_taken"])
        self.assertEqual(api.apply_decision.call_count, 2)

    def test_reprobe_and_simulated_incidents(self):
        response = api._handle_chat_command("reprobe 2")
        self.assertTrue(response["action_taken"])
        api.refresh_evidence.assert_called_once_with(self.cards[IDS[1]], {"id": IDS[1]})
        sid = "sim-20260925-port-congestion"
        api.simulate_new_disruption.return_value = {"id": sid}
        with patch.object(api, "build_incident", Mock(return_value=self.cards[IDS[0]])):
            response = api._handle_chat_command("simulate")
        self.assertEqual(response["scenario_id"], sid)
        self.assertTrue(response["action_taken"])
        self.assertEqual(api._match_scenario_id(sid), sid)
        self.assertEqual(api._match_scenario_id("fifth"), sid)
        self.assertEqual(api._match_scenario_id("congestion"), sid)
