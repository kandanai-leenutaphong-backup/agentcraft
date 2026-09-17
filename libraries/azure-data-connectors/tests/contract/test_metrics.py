import asyncio
import unittest
from types import SimpleNamespace

from azdata import OperationMetrics


class OperationMetricsTests(unittest.IsolatedAsyncioTestCase):
    async def test_known_unknown_predispatch_and_detached_snapshot(self):
        metrics = OperationMetrics(operations=("query", "read"))
        for attempts in (0, 2, None, True, -1, "3"):
            async def call():
                return SimpleNamespace(metrics={"attempts": attempts})
            await metrics.run("query", call, source_id="source")

        async def failing():
            raise OSError("offline")

        with self.assertRaises(OSError):
            await metrics.run("read", failing, source_id="source")
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot, {
            "submitted": 7, "completed": 7, "known_attempts": 2,
            "unknown_attempt_operations": 5, "operations": {"query": 6, "read": 1},
            "sources": {"source": {"known_attempts": 2, "unknown_attempt_operations": 5}},
        })
        snapshot["sources"]["source"]["known_attempts"] = 100
        snapshot["operations"]["read"] = 100
        self.assertEqual(metrics.snapshot()["sources"]["source"]["known_attempts"], 2)
        self.assertEqual(metrics.snapshot()["operations"]["read"], 1)

    async def test_concurrent_reset_and_cancellation(self):
        metrics = OperationMetrics(operations=("query",))
        entered, release = asyncio.Event(), asyncio.Event()

        async def pending():
            entered.set()
            await release.wait()
            return SimpleNamespace(metrics={"attempts": 3})

        first = asyncio.create_task(metrics.run("query", pending, source_id="old"))
        await entered.wait()
        self.assertEqual(metrics.snapshot()["completed"], 0)
        metrics.reset()
        second = asyncio.create_task(metrics.run("query", pending, source_id="new"))
        release.set()
        await asyncio.gather(first, second)
        self.assertEqual(metrics.snapshot()["submitted"], 1)
        self.assertEqual(metrics.snapshot()["completed"], 1)
        self.assertEqual(metrics.snapshot()["known_attempts"], 3)
        self.assertNotIn("old", metrics.snapshot()["sources"])
        entered.clear()
        release.clear()
        cancelled = asyncio.create_task(metrics.run("query", pending))
        await entered.wait()
        cancelled.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await cancelled
        self.assertEqual(metrics.snapshot()["completed"], 2)
        self.assertEqual(metrics.snapshot()["unknown_attempt_operations"], 1)