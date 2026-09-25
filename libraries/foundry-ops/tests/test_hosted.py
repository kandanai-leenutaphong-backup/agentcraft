import json
from pathlib import Path
import tempfile
import unittest

from foundry_ops.core import EvidenceLedger, ReadbackError, RefusedError, UnresolvedIntentError, VerificationError
from foundry_ops.hosting import (HostedTeardown, agent_reference, cancel_response, deploy_version, hosted_definition,
                                 invoke, list_sessions, session_log_excerpt)

from fakes import Clock, Event, FakeHTTP, FakeOpenAI, FakeProject, HTTPError, Reply, ResponseModel

IMAGE = "reg.azurecr.io/agentcraft-migration-a@sha256:" + "a" * 64
AGENT = "agentcraft-migration-a"


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.ledger = EvidenceLedger(self.temp.name)
        self.project = FakeProject()
        self.clock = Clock()

    def tearDown(self):
        self.temp.cleanup()

    def deploy(self, **kwargs):
        kwargs.setdefault("definition", hosted_definition(IMAGE))
        kwargs.setdefault("metadata", {"source_sha256": "s1"})
        kwargs.setdefault("key", "s1")
        return deploy_version(self.project, self.ledger, agent_name=AGENT, sleep=self.clock.sleep,
                              clock=self.clock, **kwargs)


class DeployTests(Base):
    def test_definition_requires_digest_pinned_image(self):
        self.assertEqual(hosted_definition(IMAGE)["container_configuration"]["image"], IMAGE)
        with self.assertRaises(RefusedError):
            hosted_definition("reg.azurecr.io/a:latest")

    def test_fresh_deploy_records_intent_created_active(self):
        result = self.deploy()
        self.assertEqual((result["version"], result["readback"]["status"]), ("1", "active"))
        for name in ("deploy-s1-intent.json", "deploy-s1-created.json", "deploy-s1-active.json"):
            self.assertTrue(self.ledger.exists(name), name)
        order = [name for name, _ in self.project.agents.calls]
        self.assertLess(order.index("get"), order.index("create_version"))
        self.assertEqual(self.deploy(), result)
        self.assertEqual([name for name, _ in self.project.agents.calls].count("create_version"), 1)

    def test_existing_agent_requires_owned_previous_and_distinct_image(self):
        self.deploy()
        with self.assertRaises(RefusedError) as caught:
            self.deploy(key="s2")
        self.assertEqual(caught.exception.code, "agent_exists")
        with self.assertRaises(RefusedError) as caught:
            self.deploy(key="s2", previous_version="7", previous_image="other")
        self.assertEqual(caught.exception.code, "latest_drift")
        with self.assertRaises(RefusedError) as caught:
            self.deploy(key="s2", previous_version="1", previous_image=IMAGE)
        self.assertEqual(caught.exception.code, "image_unchanged")
        second = self.deploy(key="s2", previous_version="1", previous_image="other",
                             definition=hosted_definition(IMAGE.replace("a" * 64, "b" * 64)))
        self.assertEqual(second["version"], "2")

    def test_previous_without_agent_refused(self):
        with self.assertRaises(RefusedError) as caught:
            self.deploy(previous_version="1")
        self.assertEqual(caught.exception.code, "previous_missing")

    def test_dangling_intent_refuses_second_create(self):
        self.ledger.intent("deploy-s1", {"lost": True})
        with self.assertRaises(UnresolvedIntentError):
            self.deploy()
        self.assertNotIn("create_version", [name for name, _ in self.project.agents.calls])

    def test_failed_version_aborts_and_deadline_raises(self):
        self.project.agents.version_status_sequence = ["failed"]
        with self.assertRaises(VerificationError):
            self.deploy()
        self.project = FakeProject()
        self.project.agents.version_status_sequence = ["creating"] * 1000
        with self.assertRaises(ReadbackError) as caught:
            self.deploy(key="s3", seconds=20, interval=5)
        self.assertEqual(caught.exception.code, "readiness_deadline")


class InvokeCancelTests(Base):
    def test_invoke_once_pins_agent_version(self):
        client = FakeOpenAI()
        first = invoke(client, self.ledger, key="n1", agent_name=AGENT, version="1", input="q")
        second = invoke(client, self.ledger, key="n1", agent_name=AGENT, version="1", input="q")
        self.assertEqual(first, second)
        self.assertEqual(first["output_text"], "Iris-setosa")
        creates = [call for call in client.responses.calls if call[0] == "create"]
        self.assertEqual(len(creates), 1)
        self.assertEqual(creates[0][1]["extra_body"], {"agent_reference": agent_reference(AGENT, "1")})

    def test_stream_cancel_at_created_is_proved_by_readback(self):
        client = FakeOpenAI()
        created = ResponseModel(id="resp_c", status="queued", output=[])
        client.responses.store["resp_c"] = created
        client.responses.stream_events = [Event(type="response.created", response=created),
                                          Event(type="response.in_progress")]
        result = cancel_response(client, self.ledger, key="v1", agent_name=AGENT, version="1", input="q",
                                 sleep=self.clock.sleep)
        self.assertEqual((result["response_id"], result["readback"]["status"]), ("resp_c", "cancelled"))
        for name in ("cancel-v1-intent.json", "cancel-v1-accepted.json", "cancel-v1-request-intent.json", "cancel-v1-result.json"):
            self.assertTrue(self.ledger.exists(name), name)
        self.assertEqual([c for c in client.responses.calls if c[0] == "cancel"], [("cancel", "resp_c")])
        again = cancel_response(client, self.ledger, key="v1", agent_name=AGENT, version="1", input="q", sleep=self.clock.sleep)
        self.assertEqual(again["response_id"], "resp_c")
        self.assertEqual(len([c for c in client.responses.calls if c[0] in ("create", "cancel")]), 2)

    def test_completed_output_is_not_cancellation(self):
        client = FakeOpenAI()
        done = ResponseModel(id="resp_d", status="completed", output=[{"type": "message"}])
        client.responses.store["resp_d"] = done
        client.responses.stream_events = [Event(type="response.created", response=done)]
        client.responses.cancel = lambda rid: done
        with self.assertRaises(VerificationError):
            cancel_response(client, self.ledger, key="v2", agent_name=AGENT, version="1", input="q", sleep=self.clock.sleep)

    def test_stream_without_identity_and_bad_event(self):
        client = FakeOpenAI()
        client.responses.stream_events = []
        with self.assertRaises(ReadbackError):
            cancel_response(client, self.ledger, key="v3", agent_name=AGENT, version="1", input="q")
        with self.assertRaises(RefusedError):
            cancel_response(client, self.ledger, key="v4", agent_name=AGENT, version="1", input="q", cancel_on="response.done")


class InspectLogTests(Base):
    def test_list_bound_and_log_version_guard(self):
        self.project.agents.sessions = {(AGENT, f"s{i}"): {"agent_session_id": f"s{i}",
                                                           "version_indicator": {"agent_version": "1"}} for i in range(3)}
        self.assertEqual(len(list_sessions(self.project, AGENT)), 3)
        self.project.agents.log_chunks = [b'data: {"message": "Exception boom token=abc"}\n\n']
        excerpt = session_log_excerpt(self.project, agent_name=AGENT, agent_version="1", session_id="s0")
        self.assertEqual(len(excerpt["lines"]), 1)
        self.assertNotIn("abc", excerpt["lines"][0])
        with self.assertRaises(VerificationError):
            session_log_excerpt(self.project, agent_name=AGENT, agent_version="2", session_id="s0")


class TeardownTests(Base):
    def seed(self):
        self.deploy()
        self.project.agents.sessions = {(AGENT, "s1"): {"agent_session_id": "s1"}}
        self.client = FakeOpenAI()
        self.http = FakeHTTP([Reply(200, {"id": "resp_1", "status": "completed"}),
                              Reply(404, {"error": {"message": "gone"}})])

    def test_order_responses_sessions_versions_enforced(self):
        self.seed()
        teardown = HostedTeardown(self.project, self.ledger, agent_name=AGENT, execute=True, sleep=self.clock.sleep)
        teardown.sessions()
        with self.assertRaises(RefusedError) as caught:
            teardown.responses(self.client, ["resp_1"], bearer_token="t", http_client=self.http)
        self.assertEqual(caught.exception.code, "teardown_order")
        with self.assertRaises(RefusedError):
            HostedTeardown(self.project, self.ledger, agent_name=AGENT).agent_readback()

    def test_full_teardown_reads_back_absence(self):
        self.seed()
        teardown = HostedTeardown(self.project, self.ledger, agent_name=AGENT, execute=True, sleep=self.clock.sleep)
        [response] = teardown.responses(self.client, ["resp_1", "resp_1"], bearer_token="t", http_client=self.http)
        self.assertEqual(response["outcome"], "deleted")
        self.project.agents.session_delete_errors = [HTTPError(409)]
        [session] = teardown.sessions()
        self.assertEqual(session["outcome"], "deleted")
        names = [name for name, _ in self.project.agents.calls]
        self.assertLess(names.index("stop_session"), len(names) - 1 - names[::-1].index("delete_session"))
        [version] = teardown.versions()
        self.assertEqual(version["outcome"], "deleted")
        self.assertEqual(teardown.agent_readback()["outcome"], "absent")
        self.assertTrue(self.ledger.exists(f"teardown-version-{AGENT}-1-intent.json"))
        rerun = HostedTeardown(self.project, self.ledger, agent_name=AGENT, execute=True, sleep=self.clock.sleep)
        self.assertEqual(rerun.versions(["1"])[0], version)

    def test_dry_run_writes_nothing_and_blocked_delete_is_reported(self):
        self.seed()
        dry = HostedTeardown(self.project, self.ledger, agent_name=AGENT, sleep=self.clock.sleep)
        self.assertEqual(dry.versions()[0]["outcome"], "planned")
        self.assertFalse(any(Path(self.temp.name).glob("teardown-*")))
        self.project.agents.delete_version = lambda **kwargs: (_ for _ in ()).throw(HTTPError(409, "deletion-blocking sessions"))
        live = HostedTeardown(self.project, self.ledger, agent_name=AGENT, execute=True, polls=2, sleep=self.clock.sleep)
        record = live.versions(["1"])[0]
        self.assertEqual((record["outcome"], record["delete_error"]["status_code"]), ("delete-failed", 409))
        self.assertEqual(json.loads((Path(self.temp.name) / f"teardown-version-{AGENT}-1-result.json").read_text())["outcome"],
                         "delete-failed")


if __name__ == "__main__":
    unittest.main()
