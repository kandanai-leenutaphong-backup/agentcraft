"""SDK-independent transport, deployment identity, and permission tests."""

from __future__ import annotations

import asyncio
import hashlib
import json
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_definition import ROOT
from test_packaging import BundleFixture
import httpx
from hostedagents.client import FoundryClient, FoundryError, session_key
from hostedagents.deployment import Deployer, DeployRefused, OperatorPolicy, read_receipt, write_receipt
from hostedagents.grants import Grant, GrantBroker, GrantError, assignment_matches, ROLES

ENDPOINT = "https://example.services.ai.azure.com/api/projects/example"
PRINCIPAL = "11111111-1111-1111-1111-111111111111"
SCOPE = "/subscriptions/00000000-0000-0000-0000-000000000000/resourceGroups/example/providers/Microsoft.CognitiveServices/accounts/example"


class CredentialFixture:
    def get_token(self, _scope):
        return SimpleNamespace(token="offline-transport-fixture", expires_on=time.time() + 3600)


class ClientFixture:
    endpoint = ENDPOINT

    def __init__(self, bundle):
        self.bundle = bundle
        self.agent = None
        self.uploads = 0
        self.events = []
        self.health = {
            "ok": True, "agent": bundle.config["agent_id"],
            "artifact_id": bundle.runtime_sha256,
            "policy": bundle.config["policy"], "model": bundle.config["model"],
        }

    async def get_agent(self, _name):
        return self.agent

    async def upload(self, **_kwargs):
        self.uploads += 1
        self.agent = {"version": str(self.uploads), "instance_identity": {"principal_id": PRINCIPAL}}
        return self.agent

    async def version_status(self, _name, _version):
        return {"status": "active"}

    async def warm(self, *_args, **_kwargs):
        return self.health

    async def delete_agent(self, _name):
        self.events.append("delete")
        self.agent = None


class DeploymentTests(BundleFixture, unittest.TestCase):
    def test_protocol_create_update_and_session_query(self):
        bundle = self.build()
        requests = []

        def handle(request):
            requests.append(request)
            if "/endpoint/" in request.url.path:
                return httpx.Response(200, json={"ok": True})
            return httpx.Response(201, json={"version": "1"})

        async def run():
            client = FoundryClient(ENDPOINT, CredentialFixture(), transport=httpx.MockTransport(handle))
            for update in (False, True):
                await client.upload(name="example", metadata=bundle.metadata, zip_path=bundle.zip_path,
                                    sha256=bundle.sha256, update=update)
            await client.invoke("example", session_key("alice", "example"), {"op": "health"})

        asyncio.run(run())
        self.assertEqual(requests[0].url.path, "/api/projects/example/agents")
        self.assertEqual(requests[0].headers["x-ms-agent-name"], "example")
        self.assertIn(b'name="metadata"', requests[0].content)
        self.assertIn(b'name="code"', requests[0].content)
        self.assertNotIn("x-ms-agent-name", requests[1].headers)
        self.assertEqual(requests[1].headers["x-ms-code-zip-sha256"], bundle.sha256)
        self.assertIn("agent_session_id", requests[2].url.params)
        self.assertNotIn("agent_session_id", requests[2].headers)

    def test_deploy_receipt_is_idempotent_and_verify_checks_identity(self):
        bundle = self.build()
        client = ClientFixture(bundle)
        policy = OperatorPolicy(allowed_agents=("example",), allow_deploy=True)
        deployer = Deployer(client, policy, principal="alice", poll_interval=0)
        path = self.work / "receipt.json"

        async def run():
            first = await deployer.deploy("example", bundle, path)
            second = await deployer.deploy("example", bundle, path)
            self.assertEqual(first["state"], "active")
            self.assertEqual(second["version"], first["version"])
            self.assertEqual(client.uploads, 1)
            client.health["artifact_id"] = "wrong"
            with self.assertRaises(FoundryError):
                await deployer.verify("example", read_receipt(path), bundle)

        asyncio.run(run())

    def test_deploy_denial_existing_agent_and_hosted_process_never_upload(self):
        bundle = self.build()
        client = ClientFixture(bundle)
        path = self.work / "receipt.json"

        async def run():
            denied = Deployer(client, OperatorPolicy(), principal="alice")
            with self.assertRaises(DeployRefused):
                await denied.deploy("example", bundle, path)
            policy = OperatorPolicy(allowed_agents=("example",), allow_deploy=True)
            hosted = Deployer(client, policy, principal="alice", hosted_process=True)
            with self.assertRaises(DeployRefused):
                await hosted.deploy("example", bundle, path)
            client.agent = {"version": "other"}
            with self.assertRaises(DeployRefused):
                await Deployer(client, policy, principal="alice").deploy("example", bundle, path)
            self.assertEqual(client.uploads, 0)

        asyncio.run(run())

    def test_teardown_revokes_before_deleting_and_refuses_changed_version(self):
        bundle = self.build()
        client = ClientFixture(bundle)
        path = self.work / "receipt.json"
        policy = OperatorPolicy(allowed_agents=("example",), allow_deploy=True, allow_delete=True)
        deployer = Deployer(client, policy, principal="alice", poll_interval=0)

        async def run():
            await deployer.deploy("example", bundle, path)
            client.agent["version"] = "other"
            with self.assertRaises(DeployRefused):
                await deployer.teardown("example", path)
            client.agent["version"] = "1"
            receipt = await deployer.teardown("example", path)
            self.assertEqual(receipt["state"], "deleted")
            self.assertIsNone(client.agent)
            self.assertEqual((await deployer.teardown("example", path))["state"], "deleted")

        asyncio.run(run())

    def test_grant_scope_and_identity_readback_are_exact(self):
        grant = Grant(role="Cognitive Services OpenAI User", scope=SCOPE)
        body = {"properties": {"principalId": PRINCIPAL, "scope": SCOPE,
                               "roleDefinitionId": "/roles/" + ROLES[grant.role]}}
        self.assertTrue(assignment_matches(body, grant, PRINCIPAL))
        body["properties"]["scope"] = SCOPE.split("/providers/")[0]
        self.assertFalse(assignment_matches(body, grant, PRINCIPAL))
        with self.assertRaises(ValueError):
            Grant(role="Contributor", scope=SCOPE)
        with self.assertRaises(ValueError):
            Grant(role="Storage Blob Data Reader", scope=SCOPE)

    def test_grant_broker_reads_back_and_revokes_only_owned_assignment(self):
        grant = Grant(role="Cognitive Services OpenAI User", scope=SCOPE)
        state = {}
        requests = []

        def handle(request):
            requests.append(request)
            if request.method == "PUT":
                state.update(json.loads(request.content))
                state["properties"]["scope"] = SCOPE
                return httpx.Response(201, json=state)
            if request.method == "DELETE":
                state.clear()
                return httpx.Response(204)
            return httpx.Response(200, json=state) if state else httpx.Response(404)

        async def run():
            broker = GrantBroker(CredentialFixture(), transport=httpx.MockTransport(handle))
            record = await broker.ensure(grant, PRINCIPAL)
            self.assertTrue(record["created"])
            self.assertEqual(state["properties"]["principalType"], "ServicePrincipal")
            await broker.verify(grant, PRINCIPAL)
            await broker.revoke(record, PRINCIPAL)
            self.assertFalse(state)

        asyncio.run(run())
        self.assertEqual([request.method for request in requests], ["GET", "PUT", "GET", "GET", "GET", "DELETE", "GET"])

    def test_warm_retries_cold_start_and_refuses_auth_failure(self):
        statuses = [409, 200, 403]

        def handle(_request):
            status = statuses.pop(0)
            return httpx.Response(status, json={"ok": status == 200})

        async def run():
            client = FoundryClient(ENDPOINT, CredentialFixture(), transport=httpx.MockTransport(handle))
            self.assertTrue((await client.warm("example", "offline-session", budget=1, interval=0))["ok"])
            with self.assertRaises(FoundryError) as refused:
                await client.warm("example", "offline-session", budget=1, interval=0)
            self.assertEqual(refused.exception.status, 403)

        asyncio.run(run())

    def test_session_namespaces_do_not_collide(self):
        self.assertNotEqual(session_key("alice", "example"), session_key("bob", "example"))
        self.assertNotEqual(session_key("alice", "example"), session_key("alice", "example", purpose="warm"))

    def test_interrupted_upload_is_not_retried_as_an_unapproved_update(self):
        bundle = self.build()
        client = ClientFixture(bundle)
        client.agent = {"version": "1"}
        path = self.work / "receipt.json"
        write_receipt(path, {
            "endpoint": ENDPOINT, "name": "example", "operator": "alice",
            "artifact_id": bundle.artifact_id, "version": "", "state": "uploading",
        })
        policy = OperatorPolicy(allowed_agents=("example",), allow_deploy=True)
        with self.assertRaises(DeployRefused):
            asyncio.run(Deployer(client, policy, principal="alice").deploy("example", bundle, path))
        self.assertEqual(client.uploads, 0)

    def test_failed_grant_readback_keeps_a_durable_cleanup_intent(self):
        bundle = self.build()
        client = ClientFixture(bundle)
        path = self.work / "receipt.json"
        grant = Grant(role="Cognitive Services OpenAI User", scope=SCOPE)
        policy = OperatorPolicy(allowed_agents=("example",), allow_deploy=True,
                                allow_delete=True, allow_role_changes=True, grants=(grant,))

        class BrokerFixture:
            async def ensure(self, selected, principal, *, before_write):
                before_write({"grant": selected.model_dump(), "assignment_id": "fixture", "created": True})
                raise GrantError("read-back failed")

            async def revoke(self, record, principal):
                self_outer.assertTrue(record["created"])
                client.events.append("revoke")

        self_outer = self
        deployer = Deployer(client, policy, principal="alice", broker=BrokerFixture(), poll_interval=0)

        async def run():
            with self.assertRaises(GrantError):
                await deployer.deploy("example", bundle, path)
            receipt = read_receipt(path)
            self.assertEqual(receipt["state"], "failed")
            self.assertTrue(receipt["grants"][0]["pending"])
            await deployer.teardown("example", path)
            self.assertEqual(client.events, ["revoke", "delete"])

        asyncio.run(run())

    def test_version_race_is_refused_before_any_grant(self):
        bundle = self.build()
        client = ClientFixture(bundle)
        path = self.work / "receipt.json"

        async def raced_status(_name, _version):
            client.agent["version"] = "another-version"
            return {"status": "active"}

        client.version_status = raced_status
        policy = OperatorPolicy(allowed_agents=("example",), allow_deploy=True)
        with self.assertRaisesRegex(DeployRefused, "changed while waiting"):
            asyncio.run(Deployer(client, policy, principal="alice", poll_interval=0).deploy("example", bundle, path))
        self.assertEqual(read_receipt(path)["state"], "failed")
        self.assertEqual(read_receipt(path)["grants"], [])


if __name__ == "__main__":
    unittest.main()