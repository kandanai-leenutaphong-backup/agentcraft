"""Contracts for the connected-data-source catalogue.

Adding a source is a documentation and verification act. These tests are what make that
true: a declaration that omits what it holds, what it answers, or where to reach it fails
here rather than shipping as an undiscoverable connection.
"""

from __future__ import annotations

import unittest
from unittest import mock

from app.cybereye.backend.inventory.sources import catalogue, verify


class DeclarationTests(unittest.TestCase):
    def test_every_source_says_what_it_holds_and_what_it_answers(self) -> None:
        for source in catalogue():
            with self.subTest(source.source_id):
                self.assertTrue(source.holds.strip(), "a source must say what it holds")
                self.assertGreaterEqual(len(source.answers), 1, "a source must answer something")
                for answer in source.answers:
                    self.assertTrue(answer.strip())

    def test_every_source_says_where_to_reach_it(self) -> None:
        """A connection nobody can find is not an extension point."""
        for source in catalogue():
            with self.subTest(source.source_id):
                self.assertTrue(source.reached_by.strip())

    def test_every_source_declares_the_settings_that_configure_it(self) -> None:
        for source in catalogue():
            with self.subTest(source.source_id):
                self.assertGreaterEqual(len(source.settings), 1)

    def test_declared_settings_appear_in_the_env_template(self) -> None:
        """The template is how an operator learns a source exists."""
        from app.cybereye.backend.config import APP_ROOT

        template = (APP_ROOT / ".env.example").read_text(encoding="utf-8")
        for source in catalogue():
            for key in source.settings:
                with self.subTest(f"{source.source_id}:{key}"):
                    self.assertIn(key, template)

    def test_source_ids_are_unique(self) -> None:
        ids = [source.source_id for source in catalogue()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_exactly_one_source_is_required(self) -> None:
        """Everything but the telemetry table must be optional, or the app cannot start small."""
        required = [source.source_id for source in catalogue() if source.required]
        self.assertEqual(required, ["telemetry"])


class VerificationTests(unittest.TestCase):
    def test_verify_reports_every_declared_source(self) -> None:
        report = verify()
        self.assertEqual(len(report), len(catalogue()))
        for item in report:
            with self.subTest(item["source_id"]):
                self.assertIn("reachable", item)
                self.assertIn("status", item)
                self.assertIn("holds", item)

    def test_a_probe_that_raises_is_reported_not_propagated(self) -> None:
        """One unreachable source must never take the whole report down."""
        exploding = mock.Mock(health=mock.Mock(side_effect=RuntimeError("cluster asleep")))
        report = verify(adx=exploding)
        telemetry = next(item for item in report if item["source_id"] == "telemetry")
        self.assertFalse(telemetry["reachable"])
        self.assertIn("cluster asleep", telemetry["status"]["detail"])
        self.assertEqual(len(report), len(catalogue()))

    def test_a_live_client_is_used_when_one_is_supplied(self) -> None:
        adx = mock.Mock(health=mock.Mock(return_value={"reachable": True, "database": "X"}))
        telemetry = next(item for item in verify(adx=adx) if item["source_id"] == "telemetry")
        self.assertTrue(telemetry["reachable"])
        adx.health.assert_called_once()

    def test_the_telemetry_declaration_names_the_bound_table(self) -> None:
        from app.cybereye.backend.config import settings

        telemetry = next(source for source in catalogue() if source.source_id == "telemetry")
        self.assertIn(settings.table, telemetry.name)


if __name__ == "__main__":
    unittest.main()
