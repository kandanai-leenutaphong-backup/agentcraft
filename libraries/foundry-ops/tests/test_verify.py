import unittest

from foundry_ops.errors import ReadbackError, RefusedError, VerificationError
from foundry_ops.verify import (agent_responses_url, anonymous_probe, check_active_version, check_identity,
                                is_not_found, read_stored_response, require_refusal)

from fakes import APIConnectionError, FakeHTTP, FakeOpenAI, HTTPError, Reply, ResourceNotFoundError

IMAGE = "reg.azurecr.io/agent@sha256:" + "a" * 64
DEFINITION = {"kind": "hosted", "cpu": "1", "memory": "2Gi", "container_configuration": {"image": IMAGE},
              "protocol_versions": [{"protocol": "responses", "version": "2.0.0"}]}


class RefusalTests(unittest.TestCase):
    def test_url(self):
        self.assertEqual(agent_responses_url("https://x/api/projects/p/", "agentcraft-migration-a"),
                         "https://x/api/projects/p/agents/agentcraft-migration-a/endpoint/protocols/openai/responses?api-version=v1")
        with self.assertRaises(RefusedError):
            agent_responses_url("https://x", "../other")

    def test_anonymous_probe_sends_no_credentials(self):
        http = FakeHTTP([Reply(401)])
        self.assertEqual(require_refusal(anonymous_probe("https://x/r", http_client=http)), 401)
        method, _, kwargs = http.calls[0]
        self.assertEqual(method, "POST")
        self.assertNotIn("headers", kwargs)

    def test_only_401_403_prove_refusal(self):
        self.assertEqual(require_refusal(403), 403)
        for status in (200, 302, 404, 500):
            with self.assertRaises(VerificationError):
                require_refusal(status)


class IdentityTests(unittest.TestCase):
    def actual(self, **changes):
        value = {"version": "3", "status": "active", "definition": dict(DEFINITION),
                 "metadata": {"source_sha256": "s", "config_sha256": "c", "other": "x"}}
        value.update(changes)
        return value

    def test_active_version_matches(self):
        result = check_active_version(self.actual(), version="3", image=IMAGE,
                                      metadata={"source_sha256": "s"}, definition=DEFINITION)
        self.assertEqual((result["version"], result["status"]), ("3", "active"))

    def test_active_version_refusals_name_fields(self):
        cases = {"status": self.actual(status="creating"), "version": self.actual(version="4"),
                 "image": self.actual(definition=dict(DEFINITION, container_configuration={"image": "other"})),
                 "definition.cpu": self.actual(definition=dict(DEFINITION, cpu="2")),
                 "metadata.source_sha256": self.actual(metadata={"source_sha256": "drift"})}
        for field, actual in cases.items():
            with self.assertRaises(VerificationError) as caught:
                check_active_version(actual, version="3", image=IMAGE, metadata={"source_sha256": "s"}, definition=DEFINITION)
            self.assertIn(field, str(caught.exception))

    def test_check_identity(self):
        check_identity({"a": 1, "b": 2}, {"a": 1})
        with self.assertRaises(VerificationError) as caught:
            check_identity(None, {"agent_version": "3"})
        self.assertIn("agent_version", str(caught.exception))
        self.assertNotIn("'3'", str(caught.exception))


class StoredResponseTests(unittest.TestCase):
    def test_200_returns_body_with_default_query_and_bearer(self):
        http = FakeHTTP([Reply(200, {"id": "resp_1", "status": "completed"})])
        self.assertEqual(read_stored_response(FakeOpenAI(), "resp_1", bearer_token="t", http_client=http)["id"], "resp_1")
        _, url, kwargs = http.calls[0]
        self.assertTrue(url.endswith("/openai/responses/resp_1"))
        self.assertEqual((kwargs["params"], kwargs["headers"]), ({"api-version": "v1"}, {"Authorization": "Bearer t"}))

    def test_json_404_is_absent(self):
        http = FakeHTTP([Reply(404, {"error": {"code": "not_found", "message": "gone"}})])
        self.assertIsNone(read_stored_response(FakeOpenAI(), "resp_1", bearer_token="t", http_client=http))

    def test_unrecognized_404_and_other_status_are_unknown(self):
        for reply in (Reply(404, None, "<html>"), Reply(404, {"detail": "route"}), Reply(500, {"error": {}})):
            with self.assertRaises(ReadbackError):
                read_stored_response(FakeOpenAI(), "resp_1", bearer_token="t", http_client=FakeHTTP([reply]))

    def test_unsafe_response_id_refused(self):
        with self.assertRaises(RefusedError):
            read_stored_response(FakeOpenAI(), "../x", bearer_token="t", http_client=FakeHTTP([]))

    def test_not_found_detection_excludes_connection_errors(self):
        self.assertTrue(is_not_found(HTTPError(404)))
        self.assertTrue(is_not_found(ResourceNotFoundError()))
        self.assertFalse(is_not_found(HTTPError(409)))
        self.assertFalse(is_not_found(APIConnectionError("mapped 404")))


if __name__ == "__main__":
    unittest.main()
