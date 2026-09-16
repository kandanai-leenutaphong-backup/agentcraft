from __future__ import annotations

import asyncio
import copy
import threading
import traceback
import unittest
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from situation_detector import (
    ConfigurationError,
    RuleExecutionError,
    configuration_digest,
    normalize_config,
    normalize_window,
    run_battery,
    run_battery_async,
    selected_rules,
    stream_battery,
)


T0 = datetime(2026, 8, 13, 2, 30, tzinfo=timezone.utc)
WINDOW = {"start": T0, "end": T0 + timedelta(hours=1)}


def configuration(**overrides) -> dict:
    base = {
        "version": "test-1",
        "max_window_seconds": 3600,
        "rule_sets": [
            {
                "id": "first", "name": "First set", "enabled": True,
                "rules": [
                    {"id": "alpha", "name": "Alpha", "query": "SOURCE | alpha",
                     "parameters": {"threshold": 2}, "processing": {"kind": "count"}, "enabled": True},
                    {"id": "beta", "name": "Beta", "query": "SOURCE | beta",
                     "parameters": {}, "processing": {}, "enabled": True},
                ],
            },
            {
                "id": "second", "name": "Second set", "enabled": True,
                "rules": [
                    {"id": "gamma", "name": "Gamma", "query": "SOURCE | gamma",
                     "parameters": {}, "processing": {}, "enabled": True},
                ],
            },
        ],
    }
    base.update(overrides)
    return base


def execute(rule, window):
    return {"rows": [{"rule": rule["id"], "start": window["start"]}], "query": rule["query"]}


def process(rule, envelope, window):
    return {"rows": len(envelope["rows"]), "window_start": window["start"], "query": envelope["query"]}


class ConfigurationTests(unittest.TestCase):
    def test_structure_is_validated_and_defaults_are_explicit(self):
        normalized = normalize_config(configuration())
        self.assertEqual(normalized["version"], "test-1")
        self.assertTrue(normalized["rule_sets"][0]["rules"][0]["enabled"])
        lenient = normalize_config({
            "version": "v", "max_window_seconds": 60,
            "rule_sets": [{"id": "s", "name": "s", "rules": [{"id": "r", "name": "R", "query": "Q"}]}],
        })
        rule = lenient["rule_sets"][0]["rules"][0]
        self.assertEqual((rule["enabled"], rule["parameters"], rule["processing"]), (True, {}, {}))

    def test_invalid_configurations_fail_explicitly(self):
        cases = {
            "not an object": [],
            "missing version": {"max_window_seconds": 60, "rule_sets": []},
            "empty version": {"version": " ", "max_window_seconds": 60, "rule_sets": []},
            "bad bound": {"version": "v", "max_window_seconds": 0, "rule_sets": []},
            "bound not numeric": {"version": "v", "max_window_seconds": "60", "rule_sets": []},
            "rule_sets not a list": {"version": "v", "max_window_seconds": 60, "rule_sets": {}},
            "rule missing query": {"version": "v", "max_window_seconds": 60, "rule_sets": [
                {"id": "s", "name": "s", "rules": [{"id": "r", "name": "R"}]}]},
        }
        for label, candidate in cases.items():
            with self.subTest(label):
                with self.assertRaises(ConfigurationError):
                    normalize_config(candidate)

    def test_rule_identifiers_are_globally_unique(self):
        clashing = configuration()
        clashing["rule_sets"][1]["rules"][0]["id"] = "alpha"
        with self.assertRaises(ConfigurationError) as raised:
            normalize_config(clashing)
        self.assertIn("alpha", str(raised.exception))

    def test_additional_fields_are_retained_but_bounded(self):
        extended = configuration(owner="platform")
        extended["rule_sets"][0]["rules"][0]["metadata"] = {"origin": "declared"}
        extended["rule_sets"][0]["notes"] = "kept"
        normalized = normalize_config(extended)
        self.assertEqual(normalized["owner"], "platform")
        self.assertEqual(normalized["rule_sets"][0]["notes"], "kept")
        self.assertEqual(normalized["rule_sets"][0]["rules"][0]["metadata"], {"origin": "declared"})

        unbounded = configuration()
        unbounded["rule_sets"][0]["rules"][0].update({f"extra_{index}": index for index in range(40)})
        with self.assertRaises(ConfigurationError):
            normalize_config(unbounded)

    def test_selection_honours_disabled_sets_and_rules_in_order(self):
        self.assertEqual([(rule["rule_set_id"], rule["id"]) for rule in selected_rules(configuration())],
                         [("first", "alpha"), ("first", "beta"), ("second", "gamma")])
        partial = configuration()
        partial["rule_sets"][0]["rules"][1]["enabled"] = False
        partial["rule_sets"][1]["enabled"] = False
        self.assertEqual([rule["id"] for rule in selected_rules(partial)], ["alpha"])

    def test_digest_is_deterministic_content_identity(self):
        reordered = {"rule_sets": configuration()["rule_sets"], "max_window_seconds": 3600, "version": "test-1"}
        self.assertEqual(configuration_digest(configuration()), configuration_digest(reordered))
        tuned = configuration()
        tuned["rule_sets"][0]["rules"][0]["parameters"]["threshold"] = 3
        self.assertNotEqual(configuration_digest(configuration()), configuration_digest(tuned))
        disabled = configuration()
        disabled["rule_sets"][1]["enabled"] = False
        self.assertNotEqual(configuration_digest(configuration()), configuration_digest(disabled))

    def test_window_bounds_allow_a_zero_width_incident_window(self):
        self.assertEqual(normalize_window({"start": T0, "end": T0}, 60)["end"], T0)
        parsed = normalize_window({"start": "2026-08-13T02:30:00Z", "end": "2026-08-13T02:31:00+00:00"}, 3600)
        self.assertEqual(parsed["start"], T0)
        for label, window, bound in (
            ("reversed", {"start": T0, "end": T0 - timedelta(seconds=1)}, 3600),
            ("over bound", {"start": T0, "end": T0 + timedelta(hours=2)}, 3600),
            ("mixed awareness", {"start": T0, "end": datetime(2026, 8, 13, 3, 30)}, 3600),
            ("unparsable", {"start": "yesterday", "end": T0}, 3600),
        ):
            with self.subTest(label):
                with self.assertRaises(ConfigurationError):
                    normalize_window(window, bound)


class BatteryTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancellation_propagates_without_becoming_a_rule_failure(self):
        async def cancelled(rule, window):
            raise asyncio.CancelledError()

        with self.assertRaises(asyncio.CancelledError):
            await run_battery_async(configuration(), WINDOW, cancelled, process)
        with self.assertRaises(asyncio.CancelledError):
            async for event in stream_battery(configuration(), WINDOW, cancelled, process):
                pass

    async def test_closing_stream_during_start_events_joins_started_tasks(self):
        started = asyncio.Event()
        finished = asyncio.Event()
        running = []

        async def blocked(rule, window):
            running.append(asyncio.current_task())
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                finished.set()

        stream = stream_battery(configuration(), WINDOW, blocked, process)
        try:
            self.assertEqual((await anext(stream))["event"], "rule_started")
            self.assertEqual((await anext(stream))["event"], "rule_started")
            await asyncio.wait_for(started.wait(), 1)
            await stream.aclose()
            self.assertTrue(finished.is_set())
            self.assertTrue(all(task.done() for task in running))
        finally:
            await stream.aclose()
            for task in running:
                task.cancel()
            await asyncio.gather(*running, return_exceptions=True)

    def test_sync_battery_returns_ordered_identified_results(self):
        result = run_battery(configuration(), WINDOW, execute, process)
        self.assertEqual([(entry["rule_set_id"], entry["rule_id"], entry["status"]) for entry in result["rules"]],
                         [("first", "alpha", "completed"), ("first", "beta", "completed"),
                          ("second", "gamma", "completed")])
        self.assertEqual(result["configuration_digest"], configuration_digest(configuration()))
        self.assertEqual(result["window"], {"start": T0.isoformat(), "end": (T0 + timedelta(hours=1)).isoformat()})
        self.assertEqual(result["summary"], {"tests_run": 3, "rule_sets_run": 2, "configuration_version": "test-1"})
        self.assertTrue(all(isinstance(entry["elapsed_ms"], int) for entry in result["rules"]))

    def test_callbacks_receive_the_window_intact(self):
        seen: list[dict] = []

        def record(rule, window):
            seen.append(window)
            return {"rows": []}

        run_battery(configuration(), WINDOW, record, lambda rule, envelope, window: {"window": window})
        self.assertEqual(seen, [WINDOW] * 3)
        self.assertEqual(seen[0]["start"], T0)

    def test_summarize_callback_supplies_the_final_summary(self):
        result = run_battery(configuration(), WINDOW, execute, process,
                             summarize=lambda entries, window: {"observed": sum(e["processed"]["rows"] for e in entries)})
        self.assertEqual(result["summary"], {"observed": 3})
        with self.assertRaises(ConfigurationError):
            run_battery(configuration(), WINDOW, execute, process, summarize=lambda entries, window: ["not an object"])

    def test_configuration_and_window_failures_reach_the_caller(self):
        with self.assertRaises(ConfigurationError):
            run_battery(configuration(), {"start": T0, "end": T0 + timedelta(hours=3)}, execute, process)
        with self.assertRaises(ConfigurationError):
            run_battery(configuration(), WINDOW, "not callable", process)

    def test_a_failure_is_never_an_empty_successful_detection(self):
        def failing(rule, window):
            if rule["id"] == "beta":
                raise TimeoutError("source unavailable")
            return execute(rule, window)

        with self.assertRaises(RuleExecutionError) as raised:
            run_battery(configuration(), WINDOW, failing, process)
        self.assertEqual((raised.exception.rule_set_id, raised.exception.rule_id, raised.exception.stage),
                         ("first", "beta", "execute"))
        self.assertEqual(raised.exception.code, "callback_timeout")
        self.assertNotIn("source unavailable", "".join(traceback.format_exception(raised.exception)))

        with self.assertRaises(RuleExecutionError) as empty:
            run_battery(configuration(), WINDOW, lambda rule, window: None, process)
        self.assertEqual(empty.exception.stage, "execute")

        with self.assertRaises(RuleExecutionError) as bad_processing:
            run_battery(configuration(), WINDOW, execute, lambda rule, envelope, window: ["rows"])
        self.assertEqual((bad_processing.exception.stage, bad_processing.exception.rule_id), ("process", "alpha"))

    async def test_async_battery_is_concurrent_and_order_is_declaration_order(self):
        active = 0
        peak = 0
        delays = {"alpha": 0.05, "beta": 0.01, "gamma": 0.03}

        async def slow(rule, window):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            try:
                await asyncio.sleep(delays[rule["id"]])
                return execute(rule, window)
            finally:
                active -= 1

        result = await run_battery_async(configuration(), WINDOW, slow, process)
        self.assertGreater(peak, 1)
        self.assertEqual([entry["rule_id"] for entry in result["rules"]], ["alpha", "beta", "gamma"])

    async def test_stream_emits_starts_then_completions_then_one_result(self):
        events = [event async for event in stream_battery(configuration(), WINDOW, execute, process)]
        names = [event["event"] for event in events]
        self.assertEqual(names, ["rule_started"] * 3 + ["rule_completed"] * 3 + ["battery_completed"])
        self.assertEqual([event["data"]["rule_id"] for event in events[:3]], ["alpha", "beta", "gamma"])
        direct = await run_battery_async(configuration(), WINDOW, execute, process)
        stable = lambda entries: [{key: value for key, value in entry.items() if key != "elapsed_ms"}
                                  for entry in entries]
        self.assertEqual(stable(events[-1]["data"]["rules"]), stable(direct["rules"]))

    async def test_concurrency_is_bounded_for_native_async_callbacks(self):
        for limit in (1, 2):
            active = 0
            peak = 0

            async def bounded(rule, window):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                try:
                    await asyncio.sleep(0.01)
                    return execute(rule, window)
                finally:
                    active -= 1

            result = await run_battery_async(configuration(), WINDOW, bounded, process, max_concurrency=limit)
            self.assertEqual(peak, limit)
            self.assertEqual([entry["rule_id"] for entry in result["rules"]], ["alpha", "beta", "gamma"])

    async def test_sync_callbacks_use_bounded_threads_including_summary(self):
        loop_thread = threading.get_ident()
        threads = []
        active = 0
        peak = 0
        lock = threading.Lock()

        def bounded(rule, window):
            nonlocal active, peak
            with lock:
                active += 1
                peak = max(peak, active)
                threads.append(threading.get_ident())
            try:
                threading.Event().wait(0.02)
                return execute(rule, window)
            finally:
                with lock:
                    active -= 1

        def observe(rule, envelope, window):
            threads.append(threading.get_ident())
            return process(rule, envelope, window)

        def summarize(entries, window):
            threads.append(threading.get_ident())
            return {"tests_run": len(entries)}

        events = [event async for event in stream_battery(
            configuration(), WINDOW, bounded, observe, summarize=summarize, max_concurrency=2,
        )]
        self.assertEqual(peak, 2)
        self.assertTrue(all(thread != loop_thread for thread in threads))
        self.assertEqual(events[-1]["data"]["summary"], {"tests_run": 3})

    async def test_async_summary_and_callable_objects_are_awaited(self):
        class Fetch:
            async def __call__(self, rule, window):
                return execute(rule, window)

        async def summarize(entries, window):
            await asyncio.sleep(0)
            return {"tests_run": len(entries)}

        result = await run_battery_async(configuration(), WINDOW, Fetch(), process, summarize=summarize)
        self.assertEqual(result["summary"], {"tests_run": 3})

    async def test_invalid_concurrency_refuses_before_callbacks(self):
        called = []
        for limit in (True, False, 0, -1, 1.5, "2", None):
            with self.subTest(limit=limit):
                with self.assertRaises(ConfigurationError):
                    await run_battery_async(configuration(), WINDOW, lambda *args: called.append(args),
                                            process, max_concurrency=limit)
        self.assertEqual(called, [])

    async def test_cancellation_joins_started_synchronous_callback(self):
        started = asyncio.Event()
        release = threading.Event()
        finished = threading.Event()
        loop = asyncio.get_running_loop()

        def blocked(rule, window):
            loop.call_soon_threadsafe(started.set)
            try:
                release.wait(1)
                return execute(rule, window)
            finally:
                finished.set()

        task = asyncio.create_task(run_battery_async(configuration(), WINDOW, blocked, process, max_concurrency=1))
        try:
            await asyncio.wait_for(started.wait(), 1)
            task.cancel()
            await asyncio.sleep(0)
            self.assertFalse(task.done())
        finally:
            release.set()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertTrue(finished.is_set())

    async def test_callback_failures_preserve_identity_without_payload_or_forged_metadata(self):
        payload = "private-query-and-result"

        def fail(rule, *args):
            if rule["id"] == "alpha":
                raise RuleExecutionError("forged-set", "forged-rule", "forged-stage", payload)
            return execute(rule, *args) if len(args) == 1 else process(rule, *args)

        for runner in (run_battery, run_battery_async):
            for stage in ("execute", "process"):
                with self.subTest(runner=runner.__name__, stage=stage):
                    with self.assertRaises(RuleExecutionError) as raised:
                        result = runner(configuration(), WINDOW, fail if stage == "execute" else execute,
                                        fail if stage == "process" else process)
                        if runner is run_battery_async:
                            await result
                    error = raised.exception
                    self.assertEqual((error.rule_set_id, error.rule_id, error.stage), ("first", "alpha", stage))
                    self.assertEqual(error.code, "callback_failed")
                    self.assertNotIn(payload, "".join(traceback.format_exception(error)))
                    self.assertNotIn(payload, repr(vars(error)))
                    self.assertIsNone(error.__cause__)

    def test_sync_cancellation_is_not_wrapped(self):
        def cancelled(*args):
            raise asyncio.CancelledError()

        for execute_callback, process_callback in ((cancelled, process), (execute, cancelled)):
            with self.assertRaises(asyncio.CancelledError):
                run_battery(configuration(), WINDOW, execute_callback, process_callback)

    async def test_observation_mapping_failure_keeps_safe_rule_metadata(self):
        class BrokenObservations(Mapping):
            def __getitem__(self, key):
                raise KeyError(key)

            def __iter__(self):
                raise RuntimeError("private observation payload")

            def __len__(self):
                return 1

        selected = configuration()
        selected["rule_sets"][0]["rules"][1]["enabled"] = False
        selected["rule_sets"][1]["enabled"] = False
        for runner in (run_battery, run_battery_async):
            with self.assertRaises(RuleExecutionError) as raised:
                result = runner(selected, WINDOW, execute, lambda *args: BrokenObservations())
                if runner is run_battery_async:
                    await result
            self.assertEqual((raised.exception.rule_set_id, raised.exception.rule_id, raised.exception.stage),
                             ("first", "alpha", "process"))
            self.assertEqual(raised.exception.code, "callback_failed")
            self.assertNotIn("private observation payload", "".join(traceback.format_exception(raised.exception)))

    async def test_failure_joins_siblings_and_does_not_start_queued_rules(self):
        sibling_started = asyncio.Event()
        sibling_finished = asyncio.Event()
        seen = []

        async def failing(rule, window):
            seen.append(rule["id"])
            if rule["id"] == "alpha":
                await sibling_started.wait()
                raise RuntimeError("private callback failure")
            sibling_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                sibling_finished.set()

        with self.assertRaises(RuleExecutionError):
            await asyncio.wait_for(run_battery_async(configuration(), WINDOW, failing, process,
                                                    max_concurrency=2), 1)
        self.assertTrue(sibling_finished.is_set())
        self.assertEqual(seen, ["alpha", "beta"])

    async def test_stream_raises_rather_than_completing_without_a_failed_rule(self):
        async def failing(rule, window):
            if rule["id"] == "gamma":
                raise RuntimeError("query rejected")
            return execute(rule, window)

        seen: list[str] = []
        with self.assertRaises(RuleExecutionError) as raised:
            async for event in stream_battery(configuration(), WINDOW, failing, process):
                seen.append(event["event"])
        self.assertEqual(raised.exception.rule_id, "gamma")
        self.assertNotIn("battery_completed", seen)


class UnrelatedConsumerTests(unittest.IsolatedAsyncioTestCase):
    """A second, non-security consumer: the component carries no domain of its own."""

    CATALOGUE = {
        "overdue_loans": [{"member": "m-1", "days": 12}, {"member": "m-2", "days": 3}],
        "unshelved_returns": [{"shelf": "A4", "items": 7}],
    }

    def configuration(self) -> dict:
        return {
            "version": "library-checks-2",
            "max_window_seconds": 7 * 24 * 3600,
            "rule_sets": [{
                "id": "circulation", "name": "Circulation checks", "enabled": True,
                "rules": [
                    {"id": "overdue_loans", "name": "Overdue loans", "query": "overdue_loans",
                     "parameters": {"days": 7}, "processing": {"kind": "threshold"}, "enabled": True},
                    {"id": "unshelved_returns", "name": "Unshelved returns", "query": "unshelved_returns",
                     "parameters": {"items": 5}, "processing": {"kind": "threshold"}, "enabled": True},
                    {"id": "lost_media", "name": "Lost media", "query": "lost_media",
                     "parameters": {}, "processing": {}, "enabled": False},
                ],
            }],
        }

    async def test_a_library_battery_runs_on_the_same_public_surface(self):
        def fetch(rule, window):
            return {"records": copy.deepcopy(self.CATALOGUE.get(rule["query"], []))}

        def evaluate(rule, envelope, window):
            threshold = rule["parameters"].get("days") or rule["parameters"].get("items") or 0
            breaches = [record for record in envelope["records"]
                        if max(record.get("days", 0), record.get("items", 0)) >= threshold]
            return {"breaches": len(breaches), "threshold": threshold}

        result = await run_battery_async(
            self.configuration(), {"start": "2026-09-01T00:00:00+00:00", "end": "2026-09-05T00:00:00+00:00"},
            fetch, evaluate,
            summarize=lambda entries, window: {"breaches": sum(e["processed"]["breaches"] for e in entries)},
        )
        self.assertEqual([entry["rule_id"] for entry in result["rules"]], ["overdue_loans", "unshelved_returns"])
        self.assertEqual(result["summary"], {"breaches": 2})
        self.assertEqual(result["window"]["end"], "2026-09-05T00:00:00+00:00")
        self.assertEqual(len(result["configuration_digest"]), 64)


if __name__ == "__main__":
    unittest.main()
