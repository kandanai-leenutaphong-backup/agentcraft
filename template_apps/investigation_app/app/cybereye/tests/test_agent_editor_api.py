import tempfile
from pathlib import Path
from unittest import TestCase, mock

from fastapi.testclient import TestClient

import _auth_support
from app.cybereye.backend import main
from app.cybereye.backend.agents.config import load_agent_spec
from app.cybereye.backend.agents.editor import AgentEditor
from app.cybereye.backend.agents.service import AgentService
from app.cybereye.backend.security.principal import Principal
from app.cybereye.tests.test_chat_sessions import frames
from app.cybereye.tests.test_situation_diagnosis import GOOD, situation_fixture

PREFIX = "/api/cyber/agent-editor"


class AgentEditorApiTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        _auth_support.install(main.app)
        self.client = self.enterContext(TestClient(main.app))
        self.editor = AgentEditor(self.root, load_agent_spec())
        self.client.app.state.agent_editor = self.editor
        self.owner = _auth_support.DEFAULT
        self.payload = {
            "name": "Editor Investigator", "model": self.editor.builtin.model,
            "system_prompt": "EDITOR-SYSTEM-INSTRUCTION", "instruction_files": [
                {"name": "one.md", "content": "EDITOR-UPLOADED-ONE"},
                {"name": "two.md", "content": "EDITOR-UPLOADED-TWO"},
            ], "tool_ids": list(self.editor.tools), "base_version": 0, "expected_latest_version": 0,
        }

    def create(self):
        response = self.client.post(f"{PREFIX}/agents", json=self.payload)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIn("no-store", response.headers["cache-control"])
        return response.json()

    def test_create_edit_reload_old_version_and_restart_read_back(self):
        response = self.client.get(PREFIX)
        self.assertEqual(response.headers["cache-control"], "no-store, private")
        catalogue = response.json()
        self.assertEqual(len(catalogue["tools"]), 11)
        self.assertTrue(catalogue["foundation_files"])
        builtin = self.client.get(f"{PREFIX}/agents/cyber_defender").json()
        self.assertTrue(builtin["instruction_files"])
        self.assertEqual(builtin["tool_ids"], self.payload["tool_ids"])
        first = self.create()
        self.assertNotIn("owner_id", first)
        endpoint = f"{PREFIX}/agents/{first['agent_id']}"
        edit = {**self.payload, "name": "Version two", "base_version": 1, "expected_latest_version": 1}
        second = self.client.post(endpoint + "/versions", json=edit)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(second.json()["version"], 2)
        stale = self.client.post(endpoint + "/versions", json=edit)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(self.client.get(endpoint, params={"version": 1}).json()["name"], first["name"])
        self.client.app.state.agent_editor = AgentEditor(self.root, load_agent_spec())
        restored = self.client.get(endpoint).json()
        self.assertEqual(restored["version"], 2)
        self.assertEqual(restored["versions"], [1, 2])
        self.assertEqual(restored["instruction_files"], self.payload["instruction_files"])

    def test_anonymous_calls_and_unrecognized_principals_are_refused(self):
        with _auth_support.anonymous():
            for method, url, payload in (
                ("GET", PREFIX, None), ("POST", f"{PREFIX}/agents", self.payload),
                ("GET", f"{PREFIX}/agents/cyber_defender", None),
                ("POST", f"{PREFIX}/agents/cyber_defender/versions", self.payload),
                ("PUT", f"{PREFIX}/roles/investigator", {
                    "agent_id": "cyber_defender", "version": 1, "expected_revision": 0}),
            ):
                response = self.client.request(method, url, json=payload)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.content, b"")
        with _auth_support.as_principal(Principal("unrecognized", issuer="header")):
            self.assertEqual(self.client.get(PREFIX).status_code, 403)

    def test_cross_owner_reads_writes_and_assignment_do_not_disclose_an_agent(self):
        saved = self.create()
        endpoint = f"{PREFIX}/agents/{saved['agent_id']}"
        with _auth_support.as_principal(_auth_support.OTHER):
            self.assertEqual(self.client.get(endpoint).status_code, 404)
            self.assertEqual(self.client.post(endpoint + "/versions", json=self.payload).status_code, 404)
            self.assertEqual(self.client.put(f"{PREFIX}/roles/investigator", json={
                "agent_id": saved["agent_id"], "version": 1, "expected_revision": 0,
            }).status_code, 404)
            self.assertEqual([agent["id"] for agent in self.client.get(PREFIX).json()["agents"]], ["cyber_defender"])

    def test_invalid_upload_tool_model_and_empty_instructions_fail_before_save(self):
        for update in (
            {"instruction_files": [{"name": "../../private.md", "content": "text"}]},
            {"instruction_files": [{"name": "large.md", "content": "x" * 65_537}]},
            {"model": "not-a-configured-model"}, {"tool_ids": ["run_arbitrary_code"]},
            {"system_prompt": "", "instruction_files": []}, {"owner_id": "someone-else"},
        ):
            response = self.client.post(f"{PREFIX}/agents", json={**self.payload, **update})
            self.assertEqual(response.status_code, 422, response.text)
        self.assertEqual(list(self.root.rglob("*.json")), [])

    def test_failed_persistence_does_not_report_a_successful_save(self):
        with mock.patch.object(self.editor.library, "_write", side_effect=OSError("disk unavailable")):
            response = self.client.post(f"{PREFIX}/agents", json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual([agent["id"] for agent in self.client.get(PREFIX).json()["agents"]], ["cyber_defender"])

    def test_assignment_drives_chat_and_diagnosis_and_resets_previous_agent_thread(self):
        calls = []

        async def scripted(agent, message, **arguments):
            calls.append({"spec": agent.spec, **arguments})
            yield "metadata", {"response_id": f"reply-{len(calls)}", "model": agent.spec.model,
                               "agent_id": agent.spec.agent_id, "agent_name": agent.spec.name,
                               "config_version": agent.spec.config_version}
            if arguments.get("instructions"):
                yield "tool_result", {"name": "record_situation_diagnosis", "result": dict(GOOD)}
                yield "tool_result", {"name": "complete_sequence_of_events", "result": {"ordering_note": ""}}
            else:
                yield "token", {"token": "Test response"}
            yield "done", {}

        with mock.patch.object(AgentService, "stream_turn", scripted):
            session = self.client.post("/api/sessions", json={}).json()["session_id"]
            chat = f"/api/chat/{session}"
            self.assertEqual(self.client.post(chat, json={"message": "first"}).status_code, 200)
            self.client.post(chat, json={"message": "continue"})
            self.assertEqual(calls[-1]["previous_response_id"], "reply-1")
            saved = self.create()
            selected = self.client.put(f"{PREFIX}/roles/investigator", json={
                "agent_id": saved["agent_id"], "version": 1, "expected_revision": 0,
            })
            self.assertEqual(selected.status_code, 200, selected.text)
            self.assertEqual(self.client.get(PREFIX).json()["investigator"], selected.json())
            response = self.client.post(chat, json={"message": "new investigator"})
            self.assertIsNone(calls[-1]["previous_response_id"])
            metadata = next(data for event, data in frames(response.text) if event == "metadata")
            self.assertEqual(metadata["agent_id"], saved["agent_id"])
            self.assertEqual(metadata["config_version"], 1)
            self.assertIn("EDITOR-UPLOADED-TWO", calls[-1]["spec"].instructions)
            self.assertEqual([tool.metadata.name for tool in calls[-1]["spec"].tools], self.payload["tool_ids"])
            diagnosed = self.client.post("/api/cyber/situations/diagnose", json=situation_fixture().model_dump(mode="json"))
            self.assertEqual(diagnosed.status_code, 200, diagnosed.text)
            events = frames(diagnosed.text)
            self.assertTrue(any(event == "diagnosis" for event, _ in events))
            self.assertEqual(events[-1][0], "done")
            self.assertEqual(next(data for event, data in events if event == "metadata")["agent_id"], saved["agent_id"])
            self.assertIn("EDITOR-SYSTEM-INSTRUCTION", calls[-1]["instructions"])
            self.assertIn("EDITOR-UPLOADED-ONE", calls[-1]["instructions"])
            self.assertIn("search_mitre_attack", calls[-1]["instructions"])
            self.assertEqual(self.client.get("/api/cyber/agents").json()["agents"][0]["id"], saved["agent_id"])