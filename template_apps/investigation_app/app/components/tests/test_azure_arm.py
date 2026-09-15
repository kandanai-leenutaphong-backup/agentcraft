"""`app/components/azure_arm` on its own: no Azure account, no network, no application.

Every call goes through the injected opener, so what is asserted here is the transport's
own behaviour: signing, retry, 404 handling, path encoding, and provisioning waits.
"""

from __future__ import annotations

import json
import os
import unittest
import urllib.request
from typing import Any
from unittest import mock

from app.components.azure_arm import (
    ArmClient,
    ArmConfig,
    ArmConfigError,
    ArmError,
    resource_path,
)


class FakeToken:
    def __init__(self, token: str = "fake-token", expires_on: float = 4_102_444_800.0) -> None:
        self.token = token
        self.expires_on = expires_on


class FakeCredential:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_token(self, scope: str) -> FakeToken:
        self.calls.append(scope)
        return FakeToken()


class FakeArm:
    """Answers a scripted sequence per (method, path), recording every request seen."""

    def __init__(self, script: dict[tuple[str, str], list[tuple[int, Any]]]) -> None:
        self.script = {key: list(value) for key, value in script.items()}
        self.seen: list[tuple[str, str, bytes | None, dict[str, str]]] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
        path = request.full_url.split("management.azure.com", 1)[-1]
        self.seen.append((request.get_method(), path, request.data, dict(request.headers)))
        queue = self.script.get((request.get_method(), path.split("?")[0]))
        if not queue:
            return 404, b'{"error": {"message": "not scripted"}}'
        status, body = queue.pop(0) if len(queue) > 1 else queue[0]
        return status, (b"" if body is None else json.dumps(body).encode("utf-8"))


def client(script: dict[tuple[str, str], list[tuple[int, Any]]], **kwargs: Any) -> tuple[ArmClient, FakeArm]:
    arm = FakeArm(script)
    return ArmClient(credential=FakeCredential(), opener=arm, sleep=lambda _: None,
                     **kwargs), arm


class ConfigResolution(unittest.TestCase):
    def test_defaults_target_the_public_cloud(self) -> None:
        config = ArmConfig()
        self.assertEqual(config.endpoint, "https://management.azure.com")
        self.assertEqual(config.scope, "https://management.azure.com/.default")

    def test_from_env_reads_the_environment_when_called_not_at_import(self) -> None:
        with mock.patch.dict(os.environ, {"ARM_ENDPOINT": "https://management.usgovcloudapi.net/",
                                          "ARM_MAX_ATTEMPTS": "2"}, clear=False):
            config = ArmConfig.from_env()
        self.assertEqual(config.endpoint, "https://management.usgovcloudapi.net")
        self.assertEqual(config.max_attempts, 2)
        self.assertEqual(ArmConfig.from_env().endpoint, "https://management.azure.com")

    def test_explicit_override_beats_the_environment(self) -> None:
        with mock.patch.dict(os.environ, {"ARM_SCOPE": "https://from-env/.default"}, clear=False):
            config = ArmConfig.from_env(scope="https://explicit/.default")
        self.assertEqual(config.scope, "https://explicit/.default")

    def test_a_non_https_endpoint_is_refused(self) -> None:
        with self.assertRaises(ArmConfigError):
            ArmConfig(endpoint="http://management.azure.com")

    def test_describe_carries_no_token(self) -> None:
        described = ArmClient(credential=FakeCredential()).describe()
        self.assertEqual(described["component"], "azure_arm")
        self.assertNotIn("token", json.dumps(described))


class PathBuilding(unittest.TestCase):
    def test_a_provider_path_is_built_from_quoted_parts(self) -> None:
        self.assertEqual(
            resource_path("sub-1", "rg-1", "Microsoft.DocumentDB", "databaseAccounts", "acct"),
            "/subscriptions/sub-1/resourceGroups/rg-1"
            "/providers/Microsoft.DocumentDB/databaseAccounts/acct",
        )

    def test_a_traversal_in_a_name_is_encoded_not_honoured(self) -> None:
        path = resource_path("sub", "rg", "Microsoft.DocumentDB",
                             "databaseAccounts", "../../other")
        self.assertNotIn("../", path)
        self.assertIn("..%2F..%2Fother", path)

    def test_an_unset_part_is_named(self) -> None:
        with self.assertRaises(ArmError) as caught:
            resource_path("", "rg", "Microsoft.DocumentDB")
        self.assertIn("subscription", str(caught.exception))

    def test_an_odd_number_of_segments_is_refused(self) -> None:
        with self.assertRaises(ArmError):
            resource_path("s", "rg", "Microsoft.DocumentDB", "databaseAccounts")


class Signing(unittest.TestCase):
    def test_every_request_carries_a_bearer_token(self) -> None:
        arm_client, arm = client({("GET", "/subscriptions/s"): [(200, {"ok": True})]})
        arm_client.get("/subscriptions/s?api-version=2024-11-15")
        headers = arm.seen[0][3]
        self.assertEqual(headers["Authorization"], "Bearer fake-token")

    def test_the_token_is_fetched_once_and_reused(self) -> None:
        credential = FakeCredential()
        arm = FakeArm({("GET", "/subscriptions/s"): [(200, {})]})
        arm_client = ArmClient(credential=credential, opener=arm, sleep=lambda _: None)
        arm_client.get("/subscriptions/s")
        arm_client.get("/subscriptions/s")
        self.assertEqual(len(credential.calls), 1)

    def test_a_relative_path_is_refused_before_any_request(self) -> None:
        arm_client, arm = client({})
        with self.assertRaises(ArmError):
            arm_client.get("subscriptions/s")
        self.assertEqual(arm.seen, [])

    def test_a_bodyless_post_still_sends_an_empty_payload(self) -> None:
        arm_client, arm = client({("POST", "/subscriptions/s/listKeys"): [(200, {"k": "v"})]})
        arm_client.post("/subscriptions/s/listKeys?api-version=2024-11-15")
        self.assertEqual(arm.seen[0][2], b"")


class Responses(unittest.TestCase):
    def test_an_empty_body_decodes_to_an_empty_mapping(self) -> None:
        arm_client, _ = client({("PUT", "/x"): [(201, None)]})
        self.assertEqual(arm_client.put("/x"), (201, {}))

    def test_a_404_raises_unless_the_caller_allows_absence(self) -> None:
        arm_client, _ = client({("GET", "/x"): [(404, {"error": {"message": "gone"}})]})
        with self.assertRaises(ArmError) as caught:
            arm_client.get("/x")
        self.assertEqual(caught.exception.status, 404)
        self.assertEqual(arm_client.get("/x", absent_ok=True), (404, {}))

    def test_arms_own_message_survives_into_the_error(self) -> None:
        arm_client, _ = client({("GET", "/x"): [(403, {"error": {"message": "Forbidden by policy"}})]})
        with self.assertRaises(ArmError) as caught:
            arm_client.get("/x")
        self.assertIn("Forbidden by policy", str(caught.exception))

    def test_a_non_json_body_is_carried_rather_than_crashing(self) -> None:
        arm_client = ArmClient(credential=FakeCredential(), opener=lambda r, t: (200, b"<html>"),
                               sleep=lambda _: None)
        status, decoded = arm_client.get("/x")
        self.assertEqual(status, 200)
        self.assertEqual(decoded, {"raw": "<html>"})


class Retry(unittest.TestCase):
    def test_a_throttled_call_is_retried_and_then_succeeds(self) -> None:
        arm_client, arm = client({("GET", "/x"): [(429, {"error": {"message": "slow down"}}),
                                                  (200, {"ok": True})]})
        self.assertEqual(arm_client.get("/x"), (200, {"ok": True}))
        self.assertEqual(len(arm.seen), 2)

    def test_a_client_fault_fails_on_the_first_attempt(self) -> None:
        arm_client, arm = client({("GET", "/x"): [(400, {"error": {"message": "bad"}})]})
        with self.assertRaises(ArmError):
            arm_client.get("/x")
        self.assertEqual(len(arm.seen), 1)

    def test_retries_are_bounded_by_max_attempts(self) -> None:
        arm_client, arm = client({("GET", "/x"): [(503, {"error": {"message": "unavailable"}})]},
                                 config=ArmConfig(max_attempts=3))
        with self.assertRaises(ArmError) as caught:
            arm_client.get("/x")
        self.assertEqual(caught.exception.status, 503)
        self.assertEqual(len(arm.seen), 3)


class Provisioning(unittest.TestCase):
    def test_polling_returns_once_the_resource_answers_200(self) -> None:
        arm_client, arm = client({("GET", "/x"): [(404, {}), (404, {}), (200, {"id": "/x"})]})
        arm_client.await_provisioned("/x", interval_seconds=0)
        self.assertEqual(len(arm.seen), 3)

    def test_polling_gives_up_at_the_deadline(self) -> None:
        ticks = iter([0.0, 0.0, 10.0, 20.0])
        arm = FakeArm({("GET", "/x"): [(404, {})]})
        arm_client = ArmClient(credential=FakeCredential(), opener=arm, sleep=lambda _: None,
                               monotonic=lambda: next(ticks))
        with self.assertRaises(ArmError) as caught:
            arm_client.await_provisioned("/x", wait_seconds=5, interval_seconds=0)
        self.assertIn("timed out", str(caught.exception))


class Isolation(unittest.TestCase):
    def test_importing_the_component_needs_no_credential_and_no_network(self) -> None:
        import importlib

        module = importlib.import_module("app.components.azure_arm")
        self.assertTrue(hasattr(module, "ArmClient"))
        self.assertIsNone(ArmClient()._credential)

    def test_the_component_imports_no_pipeline_connector_or_application(self) -> None:
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        for source in (root / "app" / "components" / "azure_arm").glob("*.py"):
            text = source.read_text(encoding="utf-8")
            for forbidden in ("app.data", "app.cybereye"):
                self.assertNotIn(forbidden, text, f"{source.name} imports {forbidden}")


if __name__ == "__main__":
    unittest.main()
