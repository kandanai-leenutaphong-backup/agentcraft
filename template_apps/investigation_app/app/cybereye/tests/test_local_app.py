"""``dev.sh`` runs ``backend/local_app.py``: open to this machine, and ``main`` still closed.

Both compositions run in child processes, because importing either here would mount middleware
on the application object every other test module shares.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

from app.cybereye.backend.security import (
    SecurityConfigurationError,
    SecuritySettings,
    config as security_config,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
LOCAL_MODULE = "app.cybereye.backend.local_app"
DEPLOYED_MODULE = "app.cybereye.backend.main"

# Answers from the framework alone, so a refusal is observable without an application lifespan.
PROBE_PATH = "/openapi.json"

# Present and empty in every child: `load_dotenv(override=False)` leaves a name alone once it
# exists, so without this a developer's own `.env` would decide what the deployed child mounts.
WITHHELD = {
    security_config.PUBLIC_KEY_VAR: "",
    security_config.LEDGER_VAR: "",
    security_config.ENTRA_TENANT_VAR: "",
    security_config.ENTRA_CLIENT_VAR: "",
}

# The TestClient defaults to peer `testclient` and host `testserver`, neither of which is here.
LOCAL_BASE_URL = "http://127.0.0.1:9000"
LOCAL_PEER = ("127.0.0.1", 51000)

# Cached the way `/api/cyber/scan` caches one. No patterns, so resolving it needs no ADX.
SCAN_FIXTURE = {
    "window_start": "2026-08-13T02:30:00Z",
    "window_end": "2026-08-13T03:40:59Z",
    "situations": [{
        "situation_id": "local-preview-fixture",
        "host": "WORKSTATION",
        "principal": "example",
        "severity": "high",
        "confidence": "high",
        "first_seen": "2026-08-13T02:31:00Z",
        "last_seen": "2026-08-13T03:00:00Z",
        "detector_count": 0,
        "patterns": [],
    }],
    "summary": {"situations": 1, "critical": 0, "high": 1, "evidence_rows": 0, "elapsed_ms": 1},
}
SITUATION_ID = SCAN_FIXTURE["situations"][0]["situation_id"]


def run_child(argv: list[str], **overrides: str) -> subprocess.CompletedProcess:
    env = {**os.environ, **WITHHELD, **overrides, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, *argv], cwd=REPO_ROOT, env=env, capture_output=True, text=True,
    )


def child_result(argv: list[str], **overrides: str) -> dict:
    done = run_child(argv, **overrides)
    if done.returncode != 0:
        raise AssertionError(f"probe failed ({done.returncode}):\n{done.stdout}\n{done.stderr}")
    return json.loads(done.stdout.strip().splitlines()[-1])


def probe_local() -> int:
    """Runs as a child. Every request below is one an ordinary browser on this machine sends."""
    from importlib import import_module

    from fastapi.testclient import TestClient

    local = import_module(LOCAL_MODULE)
    from app.cybereye.backend.models import ScanResponse

    answers: dict[str, object] = {"describe": local.security.describe()}
    with TestClient(local.app, base_url=LOCAL_BASE_URL, client=LOCAL_PEER) as client:
        client.app.state.last_scan.put(
            local.LOCAL_PRINCIPAL.id, ScanResponse.model_validate(SCAN_FIXTURE),
        )
        whoami = client.get("/api/whoami")
        session = client.post("/api/sessions", json={})
        evidence = client.get(f"/api/cyber/evidence/{SITUATION_ID}")
        catalogue = client.get("/api/cyber/agents")
        proxied = client.get("/api/whoami", headers={
            "Host": "localhost:5173", "Origin": "http://localhost:5173",
        })
        foreign_host = client.get("/api/whoami", headers={"Host": "cybereye.example.com"})
        foreign_origin = client.get("/api/whoami", headers={"Origin": "https://evil.example"})
        answers |= {
            "whoami": {"status": whoami.status_code, "body": whoami.json()},
            "session": {"status": session.status_code, "body": session.json()},
            "evidence": {"status": evidence.status_code, "body": evidence.json()},
            "catalogue": {"status": catalogue.status_code, "body": catalogue.json()},
            "proxied": {"status": proxied.status_code},
            "foreign_host": {"status": foreign_host.status_code, "body": foreign_host.text},
            "foreign_origin": {"status": foreign_origin.status_code, "body": foreign_origin.text},
        }

    with TestClient(local.app, base_url=LOCAL_BASE_URL, client=("203.0.113.9", 51234)) as remote:
        refused = remote.get("/api/whoami")
        answers["remote_peer"] = {"status": refused.status_code, "body": refused.text}

    try:
        SecuritySettings.from_env({
            security_config.PUBLIC_KEY_VAR: "abc",
            security_config.LEDGER_VAR: security_config.LEDGER_IN_PROCESS,
        })
    except Exception as error:
        answers["from_env"] = f"{type(error).__name__}: {error}"
    else:
        answers["from_env"] = ""

    print(json.dumps(answers))
    return 0


def probe_deployed() -> int:
    """Compose the container's application in its own process and ask it the same questions."""
    from importlib import import_module

    from fastapi.testclient import TestClient

    deployed = import_module(DEPLOYED_MODULE)
    client = TestClient(deployed.app)
    whoami = client.get("/api/whoami")
    session = client.post("/api/sessions", json={})
    openapi = client.get(PROBE_PATH)
    catalogue = client.get("/api/cyber/agents")

    print(json.dumps({
        "describe": deployed.security.describe(),
        "whoami": {"status": whoami.status_code, "body": whoami.text},
        "session": {"status": session.status_code, "body": session.text},
        "openapi": {"status": openapi.status_code, "body": openapi.text},
        "catalogue": {"status": catalogue.status_code, "body": catalogue.text},
    }))
    return 0


class LocalPreviewTests(unittest.TestCase):
    """One child process, composed exactly as `dev.sh` composes it."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = child_result([__file__, "local"])

    def test_an_ordinary_browser_request_is_answered_without_any_credential(self) -> None:
        self.assertEqual(self.result["whoami"]["status"], 200)

    def test_the_identity_it_reports_is_local_and_says_so(self) -> None:
        body = self.result["whoami"]["body"]
        self.assertEqual(body["issuer"], "local-preview")
        self.assertTrue(body["id"].startswith("local:"), body["id"])
        self.assertNotIn("devkey", body["id"])
        self.assertNotIn("entra", body["id"])
        self.assertEqual(body["tenant_id"], "")

    def test_whoami_is_answered_by_the_route_and_not_by_the_static_mount(self) -> None:
        """`main` mounts the built frontend at `/`, which shadows anything appended after it."""
        self.assertIn("display", self.result["whoami"]["body"])

    def test_local_catalogue_lists_the_loaded_agent_and_real_tool_source(self) -> None:
        response = self.result["catalogue"]
        self.assertEqual(response["status"], 200)
        agent = response["body"]["agents"][0]
        self.assertEqual(agent["id"], "cyber_defender")
        self.assertEqual(len(agent["tools"]), 11)
        self.assertTrue(all(tool["source"]["available"] for tool in agent["tools"]))
        self.assertEqual({tool["datasource"]["kind"] for tool in agent["tools"]},
                         {"adx", "search", "none"})
        tools = {tool["id"]: tool for tool in agent["tools"]}
        self.assertEqual(tools["get_authentication_activity"]["datasource_ids"],
                 ["perth.adx.events_unified"])
        self.assertEqual(tools["search_mitre_attack"]["datasource_ids"],
                 ["cyberkb.search.mitre_attack"])
        self.assertEqual(tools["record_sequence_step"]["datasource_ids"], [])

    def test_an_unsafe_request_with_no_cookie_and_no_signature_creates_a_session(self) -> None:
        self.assertEqual(self.result["session"]["status"], 200)
        self.assertTrue(self.result["session"]["body"]["session_id"])

    def test_the_local_caller_owns_what_it_created(self) -> None:
        """The scan cache is per-principal, so a stable local principal is what makes it usable."""
        self.assertEqual(self.result["evidence"]["status"], 200)
        self.assertEqual(self.result["evidence"]["body"]["situation_id"], SITUATION_ID)

    def test_a_request_proxied_by_vite_keeps_its_loopback_name(self) -> None:
        self.assertEqual(self.result["proxied"]["status"], 200)

    def test_a_foreign_host_header_is_refused(self) -> None:
        self.assertEqual(self.result["foreign_host"]["status"], 401)
        self.assertEqual(self.result["foreign_host"]["body"], "")

    def test_a_foreign_origin_is_refused_so_no_page_can_drive_this_from_a_browser(self) -> None:
        self.assertEqual(self.result["foreign_origin"]["status"], 401)
        self.assertEqual(self.result["foreign_origin"]["body"], "")

    def test_a_caller_that_is_not_on_this_machine_is_refused(self) -> None:
        self.assertEqual(self.result["remote_peer"]["status"], 401)
        self.assertEqual(self.result["remote_peer"]["body"], "")

    def test_the_composition_mounts_one_mechanism_and_no_provider(self) -> None:
        described = self.result["describe"]
        self.assertEqual(described["primary_auth_mechanisms"], 1)
        self.assertFalse(described["signed_access_mounted"])
        self.assertFalse(described["signed_access"])
        self.assertFalse(described["entra_sign_in"])

    def test_that_process_still_cannot_configure_the_per_process_ledger(self) -> None:
        """Read the deployed way, in the very process that admits this machine, nothing relaxed."""
        self.assertIn("SecurityConfigurationError", self.result["from_env"])
        self.assertIn(security_config.LEDGER_AZURE_TABLE, self.result["from_env"])


class DeployedCompositionTests(unittest.TestCase):
    """The container's module, in its own process, with this machine's environment."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.result = child_result([__file__, "deployed"])

    def test_it_refuses_an_unauthenticated_caller_with_a_bare_401(self) -> None:
        for name in ("whoami", "session", "openapi", "catalogue"):
            with self.subTest(request=name):
                self.assertEqual(self.result[name]["status"], 401)
                self.assertEqual(self.result[name]["body"], "")

    def test_no_loopback_resolver_reaches_it(self) -> None:
        """The local composition is a module, not a setting: one import cannot alter the other."""
        self.assertEqual(self.result["describe"]["primary_auth_mechanisms"], 0)


class DeployedConfigurationTests(unittest.TestCase):
    def test_no_spelling_of_the_ledger_variable_selects_the_per_process_one(self) -> None:
        for value in ("in-process", "IN-PROCESS", " in-process ", "InProcess"):
            with self.subTest(value=value), self.assertRaises(SecurityConfigurationError):
                SecuritySettings.from_env({
                    security_config.PUBLIC_KEY_VAR: "abc",
                    security_config.LEDGER_VAR: value,
                })


if __name__ == "__main__":
    _mode = sys.argv[1:2]
    raise SystemExit(
        probe_local() if _mode == ["local"]
        else probe_deployed() if _mode == ["deployed"]
        else 2
    )
