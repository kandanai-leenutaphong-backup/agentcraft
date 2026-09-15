from __future__ import annotations

import asyncio
import copy
import threading
import time
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.cybereye.backend.investigation.detector import (
    DetectorEngine,
    default_configuration,
    registry,
)
from app.cybereye.backend.models import ScanRequest


T0 = datetime(2026, 8, 13, 2, 30, tzinfo=timezone.utc)


class FakeAdx:
    def __init__(self, rows=None, delay=0.0, queries=None, fails=()):
        self.rows = rows or {}
        self.delay = delay
        self.queries = {rule.query: rule.rule_id for rule in registry()} | dict(queries or {})
        self.fails = set(fails)
        self.active = 0
        self.max_active = 0
        self.executed: list[str] = []
        self.lock = threading.Lock()

    def parameterized(self, query, params, max_rows=100):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        try:
            time.sleep(self.delay)
            rule_id = self.queries[query]
            with self.lock:
                self.executed.append(rule_id)
            if rule_id in self.fails:
                raise TimeoutError("ADX unavailable")
            rows = self.rows.get(rule_id, [])
            columns = list(rows[0]) if rows else []
            return SimpleNamespace(columns=columns, rows=[[row[column] for column in columns] for row in rows])
        finally:
            with self.lock:
                self.active -= 1


def row(count=5, minute=0, host="host1", principal="user1", ids=None):
    first = T0 + timedelta(minutes=minute)
    return {"host": host, "principal": principal, "event_count": count,
            "first_seen": first, "last_seen": first + timedelta(seconds=5),
            "evidence_ids": ids or [f"rid-{minute}"]}


class DetectorEngineTests(unittest.IsolatedAsyncioTestCase):
    def request(self, hours=1):
        return ScanRequest(start=T0, end=T0 + timedelta(hours=hours))

    def test_registry_identity_is_unique_and_stable(self):
        identities = [(rule.rule_id, rule.version) for rule in registry()]
        self.assertEqual(identities, [
            ("explicit_credential_burst", "1.0.0"),
            ("tool_url_in_session_title", "1.0.0"),
            ("directory_enumeration_alert", "1.0.0"),
            ("event_volume_excursion", "1.0.0"),
            ("fixed_interval_dns", "1.0.0"),
        ])
        self.assertEqual(len(identities), len(set(identities)))
        self.assertTrue(all(rule.query.startswith("EventsUnified") for rule in registry()))

    async def test_rules_execute_concurrently_and_lifecycle_has_one_terminal(self):
        adx = FakeAdx(delay=0.03)
        events = [event async for event in DetectorEngine(adx).stream_scan(self.request())]
        self.assertGreater(adx.max_active, 1)
        names = [event["event"] for event in events]
        self.assertEqual(names[:5], ["rule_started"] * 5)
        self.assertEqual(names.count("rule_completed"), 5)
        self.assertEqual(names[-1], "done")
        self.assertEqual(sum(name in {"done", "error"} for name in names), 1)

    async def test_miss_creates_no_factor_and_hit_has_causal_evidence(self):
        adx = FakeAdx({
            "explicit_credential_burst": [row(count=4)],
            "tool_url_in_session_title": [row(count=1, ids=["tool-id"])],
        })
        result = await DetectorEngine(adx).scan(self.request())
        self.assertEqual(len(result.situations), 1)
        factors = result.situations[0].patterns
        self.assertEqual([factor.rule_id for factor in factors], ["tool_url_in_session_title"])
        self.assertEqual(factors[0].evidence_ids, ["tool-id"])
        self.assertIn("tool-title predicate", factors[0].evidence_semantics)
        self.assertEqual(factors[0].role, "anchor")

    async def test_volume_only_correlates_to_same_entity_near_tool_hit(self):
        adx = FakeAdx({
            "tool_url_in_session_title": [row(count=1)],
            "event_volume_excursion": [
                row(count=50, minute=3),
                row(count=90, minute=2, host="other"),
                row(count=100, minute=10),
            ],
        })
        result = await DetectorEngine(adx).scan(self.request())
        factors = result.situations[0].patterns
        self.assertEqual({factor.rule_id for factor in factors}, {"tool_url_in_session_title", "event_volume_excursion"})
        self.assertEqual(result.situations[0].severity, "high")
        self.assertEqual(next(f.count for f in factors if f.rule_id == "event_volume_excursion"), 50)

    async def test_stream_evidence_only_names_matched_rules(self):
        adx = FakeAdx({"fixed_interval_dns": [row(count=20, ids=["dns-id"]) ]})
        events = [event async for event in DetectorEngine(adx).stream_scan(self.request())]
        evidence = [event for event in events if event["event"] == "evidence_completed"]
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["data"], {
            "situation_id": next(e["data"]["situation_id"] for e in events if e["event"] == "situation"),
            "rule_id": "fixed_interval_dns", "evidence_count": 1,
        })

    async def test_window_guards_are_terminal_errors(self):
        for request in (ScanRequest(start=T0, end=T0), self.request(hours=49)):
            events = [event async for event in DetectorEngine(FakeAdx()).stream_scan(request)]
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event"], "error")


def without(configuration, rule_id):
    configuration = copy.deepcopy(configuration)
    rules = configuration["rule_sets"][0]["rules"]
    configuration["rule_sets"][0]["rules"] = [rule for rule in rules if rule["id"] != rule_id]
    return configuration


def find(configuration, rule_id):
    return next(rule for rule in configuration["rule_sets"][0]["rules"] if rule["id"] == rule_id)


class DetectorCompositionTests(unittest.IsolatedAsyncioTestCase):
    """Rule sets compose through configuration; the default scan is unaffected."""

    def request(self, hours=1):
        return ScanRequest(start=T0, end=T0 + timedelta(hours=hours))

    def test_default_configuration_declares_the_registry_and_is_stable(self):
        first, second = default_configuration(), default_configuration()
        declared = [rule["id"] for rule in first["rule_sets"][0]["rules"]]
        self.assertEqual(declared, [rule.rule_id for rule in registry()])
        self.assertEqual(first, second)
        self.assertEqual(DetectorEngine(FakeAdx()).rules, registry())

    async def test_a_disabled_rule_is_never_executed_or_streamed(self):
        configuration = default_configuration()
        find(configuration, "explicit_credential_burst")["enabled"] = False
        adx = FakeAdx({"explicit_credential_burst": [row(count=9)], "tool_url_in_session_title": [row(count=1)]})
        events = [event async for event in DetectorEngine(adx, configuration).stream_scan(self.request())]
        started = [event["data"]["rule_id"] for event in events if event["event"] == "rule_started"]
        self.assertNotIn("explicit_credential_burst", started)
        self.assertNotIn("explicit_credential_burst", adx.executed)
        self.assertEqual(len(started), 4)
        situation = next(event for event in events if event["event"] == "situation")
        self.assertEqual([pattern["rule_id"] for pattern in situation["data"]["patterns"]],
                         ["tool_url_in_session_title"])

    async def test_removing_the_volume_rule_leaves_synthesis_intact(self):
        configuration = without(default_configuration(), "event_volume_excursion")
        adx = FakeAdx({"tool_url_in_session_title": [row(count=1)], "event_volume_excursion": [row(count=90, minute=2)]})
        result = await DetectorEngine(adx, configuration).scan(self.request())
        self.assertEqual(len(result.situations), 1)
        self.assertEqual({pattern.rule_id for pattern in result.situations[0].patterns},
                         {"tool_url_in_session_title"})
        self.assertEqual(len(result.rule_executions), 4)
        self.assertNotIn("event_volume_excursion", adx.executed)

    async def test_a_tuned_threshold_changes_qualification_only(self):
        configuration = default_configuration()
        find(configuration, "explicit_credential_burst")["parameters"]["threshold"] = 50
        adx = FakeAdx({"explicit_credential_burst": [row(count=9)]})
        result = await DetectorEngine(adx, configuration).scan(self.request())
        self.assertEqual(result.situations, [])
        execution = next(item for item in result.rule_executions if item.rule_id == "explicit_credential_burst")
        self.assertEqual((execution.hit_count, execution.observation["groups_returned"]), (0, 1))
        self.assertEqual(execution.observation["threshold_expression"], "event_count >= 50")

    async def test_an_added_rule_set_contributes_its_own_patterns(self):
        configuration = default_configuration()
        configuration["rule_sets"].append({
            "id": "synthetic", "name": "Synthetic trial set", "enabled": True,
            "rules": [{
                "id": "synthetic_probe", "name": "Synthetic probe",
                "query": "SyntheticFixture | project host, principal, event_count, first_seen, last_seen, evidence_ids",
                "enabled": True,
                "parameters": {"version": "0.1.0", "description": "Synthetic trial rule over a fixture table.",
                               "threshold": 2, "score": 10, "confidence": "low", "role": "contextual",
                               "evidence_semantics": "Synthetic fixture rows; not observed telemetry.",
                               "behaviour_class": "volume_anomaly"},
                "processing": {"kind": "entity_groups", "max_rows": 10},
            }],
        })
        adx = FakeAdx(
            {"tool_url_in_session_title": [row(count=1)], "synthetic_probe": [row(count=4, ids=["syn-1"])]},
            queries={find(configuration, "tool_url_in_session_title")["query"]: "tool_url_in_session_title",
                     configuration["rule_sets"][1]["rules"][0]["query"]: "synthetic_probe"},
        )
        result = await DetectorEngine(adx, configuration).scan(self.request())
        self.assertEqual(len(result.rule_executions), 6)
        patterns = {pattern.rule_id: pattern for pattern in result.situations[0].patterns}
        self.assertIn("synthetic_probe", patterns)
        self.assertEqual(patterns["synthetic_probe"].evidence_ids, ["syn-1"])
        self.assertEqual(patterns["synthetic_probe"].rule_version, "0.1.0")

    async def test_a_rule_execution_failure_names_the_rule_and_is_terminal(self):
        adx = FakeAdx({"tool_url_in_session_title": [row(count=1)]}, fails={"fixed_interval_dns"})
        events = [event async for event in DetectorEngine(adx).stream_scan(self.request())]
        error = events[-1]
        self.assertEqual(error["event"], "error")
        self.assertEqual(error["data"]["error_code"], "RuleExecutionError")
        self.assertIn("fixed_interval_dns", error["data"]["message"])
        self.assertNotIn("done", [event["event"] for event in events])
        with self.assertRaises(Exception):
            await DetectorEngine(adx).scan(self.request())

    async def test_an_invalid_configuration_is_refused_at_construction(self):
        broken = default_configuration()
        find(broken, "fixed_interval_dns")["query"] = ""
        with self.assertRaises(ValueError):
            DetectorEngine(FakeAdx(), broken)


if __name__ == "__main__":
    unittest.main()
