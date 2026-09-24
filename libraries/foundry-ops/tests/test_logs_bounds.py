import json
import unittest

from foundry_ops.bounds import collect_bounded, poll_until
from foundry_ops.errors import BoundExceededError, VerificationError
from foundry_ops.logs import exception_lines, log_messages

from fakes import Clock


def sse(*messages):
    return b"".join(b"data: " + json.dumps({"message": m}).encode() + b"\n\n" for m in messages)


class LogTests(unittest.TestCase):
    def test_messages_parse_across_chunk_and_utf8_splits(self):
        raw = sse("first", "zweite \u00fc") + b"data: not-json\n\n" + b": comment\n\n"
        chunks = [raw[i:i + 3] for i in range(0, len(raw), 3)]
        self.assertEqual(list(log_messages(chunks)), ["first", "zweite \u00fc"])

    def test_byte_bound_refuses(self):
        with self.assertRaises(BoundExceededError) as caught:
            list(log_messages([sse("x" * 100)], max_bytes=50))
        self.assertEqual(caught.exception.code, "log_bytes")

    def test_event_bound_refuses(self):
        with self.assertRaises(BoundExceededError) as caught:
            list(log_messages([sse("a", "b", "c")], max_events=2))
        self.assertEqual(caught.exception.code, "log_events")

    def test_invalid_utf8_refuses(self):
        with self.assertRaises(UnicodeDecodeError):
            list(log_messages([b"data: \xff\n\n"]))

    def test_exception_lines_filter_redact_and_bound(self):
        chunks = [sse("ok line", "Error Bearer secret-token", "Traceback 1", "failed 2", "Exception 3")]
        excerpt = exception_lines(chunks, max_lines=2)
        self.assertEqual(excerpt["termination"], "bound")
        self.assertEqual(len(excerpt["lines"]), 2)
        self.assertNotIn("secret-token", excerpt["lines"][0])

    def test_exception_lines_record_transport_end(self):
        def stream():
            yield sse("Error once")
            raise TimeoutError("read timeout")

        excerpt = exception_lines(stream())
        self.assertEqual((excerpt["lines"], excerpt["termination"], excerpt["reason"]),
                         (["Error once"], "TimeoutError", None))
        bounded = exception_lines([sse("x" * 10)], max_bytes=5)
        self.assertEqual(bounded["termination"], "BoundExceededError")
        self.assertIn("byte bound", bounded["reason"])


class BoundTests(unittest.TestCase):
    def test_poll_settles(self):
        values = iter(["creating", "creating", "active"])
        clock = Clock()
        result = poll_until(lambda: next(values), lambda v: v == "active", attempts=5, interval=2,
                            sleep=clock.sleep, clock=clock)
        self.assertEqual((result.settled, result.attempts, clock.slept), (True, 3, [2, 2]))

    def test_poll_returns_unsettled_at_attempt_bound(self):
        clock = Clock()
        result = poll_until(lambda: "queued", lambda v: False, attempts=3, interval=1, sleep=clock.sleep, clock=clock)
        self.assertEqual((result.settled, result.attempts, result.value), (False, 3, "queued"))

    def test_poll_deadline_bound(self):
        clock = Clock()
        result = poll_until(lambda: "x", lambda v: False, interval=4, seconds=10, sleep=clock.sleep, clock=clock)
        self.assertFalse(result.settled)
        self.assertLessEqual(sum(clock.slept), 10)

    def test_poll_abort_and_bounds_required(self):
        with self.assertRaises(VerificationError):
            poll_until(lambda: "failed", lambda v: False, attempts=3, interval=0, abort=lambda v: "bad" if v == "failed" else None)
        with self.assertRaises(ValueError):
            poll_until(lambda: 1, lambda v: True, interval=1)

    def test_collect_bounded(self):
        self.assertEqual(collect_bounded(iter(range(3)), max_items=3, seconds=60), [0, 1, 2])
        with self.assertRaises(BoundExceededError):
            collect_bounded(iter(range(4)), max_items=3, seconds=60)
        with self.assertRaises(BoundExceededError):
            collect_bounded(iter(range(3)), max_items=10, seconds=1, clock=Clock(step=1.0))


if __name__ == "__main__":
    unittest.main()
