import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import TestCase

from pydantic import ValidationError

from app.cybereye.backend.agents.library import (
    AgentDraft, AgentLibrary, AssignInvestigator, InstructionFile, LibraryError, SaveAgent,
)
from app.cybereye.backend.security.principal import Principal
from app.cybereye.backend.agents.config import load_agent_spec
from app.cybereye.backend.agents.editor import AgentEditor


class AgentLibraryTests(TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.owner = Principal("local:workstation", issuer="local-preview")
        self.other = Principal("entra:tenant:other", issuer="entra")
        self.options = dict(builtin_id="cyber_defender", builtin=AgentDraft(
            name="CyberDefender", model="llm-one", system_prompt="Historical replay only.",
            tool_ids=["evidence", "diagnosis"],
        ), models=("llm-one", "llm-two"), tool_ids=frozenset({"evidence", "diagnosis", "search"}),
            investigator_tools=frozenset({"evidence", "diagnosis"}))
        self.library = AgentLibrary(self.root, **self.options)

    def draft(self, **values):
        return SaveAgent(name="New analyst", model="llm-two", system_prompt="Use evidence.",
                         tool_ids=["evidence", "diagnosis"], **values)

    def test_new_agent_round_trips_in_its_own_folder_after_restart(self):
        draft = self.draft(instruction_files=[
            InstructionFile(name="first.md", content="# First\nKeep exact text.\n"),
            InstructionFile(name="second.md", content="# Second\nDifferent instructions."),
        ])
        saved = self.library.save(self.owner, draft)
        self.assertEqual(saved.version, 1)
        restarted = AgentLibrary(self.root, **self.options)
        self.assertEqual(restarted.get(self.owner, saved.agent_id, 1), saved)
        paths = list(self.root.glob(f"*/{saved.agent_id}/versions/1.json"))
        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].stat().st_mode & 0o777, 0o600)

    def test_editing_an_old_version_creates_a_new_version_without_overwriting(self):
        first = self.library.save(self.owner, self.draft())
        draft = SaveAgent(**{**first.model_dump(include=set(AgentDraft.model_fields)),
                             "name": "Second", "base_version": 1, "expected_latest_version": 1})
        second = self.library.save(self.owner, draft, first.agent_id)
        third = self.library.save(self.owner, draft.model_copy(update={
            "name": "From version one", "expected_latest_version": 2,
        }), first.agent_id)
        self.assertEqual((second.version, third.version, third.base_version), (2, 3, 1))
        self.assertEqual(self.library.get(self.owner, first.agent_id, 1), first)
        self.assertEqual(self.library.versions(self.owner, first.agent_id), [1, 2, 3])

    def test_builtin_version_is_preserved_before_edit(self):
        original = self.library.get(self.owner, "cyber_defender", 1)
        draft = SaveAgent(**original.model_dump(include=set(AgentDraft.model_fields)),
                          base_version=1, expected_latest_version=1)
        self.assertEqual(self.library.save(self.owner, draft, "cyber_defender").version, 2)
        self.library.builtin = AgentDraft(name="Changed deployment", model="llm-one", system_prompt="New")
        self.assertEqual(self.library.get(self.owner, "cyber_defender", 1), original)

    def test_named_variants_round_trip_without_renaming_the_agent_or_overwriting_history(self):
        first = self.library.save(self.owner, self.draft(version_name="Baseline"))
        original_path = next(self.root.glob(f"*/{first.agent_id}/versions/1.json"))
        original_bytes = original_path.read_bytes()
        self.library.save(self.owner, self.draft(version_name="Focused triage", base_version=1,
                                                expected_latest_version=1), first.agent_id)
        third = self.library.save(self.owner, self.draft(version_name="  Broad investigation  ",
            base_version=1, expected_latest_version=2), first.agent_id)
        restarted = AgentLibrary(self.root, **self.options)
        expected = {1: "Baseline", 2: "Focused triage", 3: "Broad investigation"}
        self.assertEqual(restarted.version_names(self.owner, first.agent_id), expected)
        summary = next(agent for agent in restarted.list(self.owner) if agent["id"] == first.agent_id)
        self.assertEqual(summary["version_names"], expected)
        self.assertEqual(third.name, first.name)
        self.assertEqual(third.base_version, 1)
        self.assertEqual(original_path.read_bytes(), original_bytes)

    def test_unnamed_legacy_versions_read_without_migration_or_rewrite(self):
        first = self.library.save(self.owner, self.draft())
        path = next(self.root.glob(f"*/{first.agent_id}/versions/1.json"))
        legacy = first.model_dump_json(exclude={"version_name"})
        path.write_text(legacy, encoding="utf-8")
        self.assertEqual(self.library.get(self.owner, first.agent_id).version_name, "")
        self.assertEqual(self.library.version_names(self.owner, first.agent_id), {1: ""})
        self.assertEqual(path.read_text(encoding="utf-8"), legacy)

    def test_version_names_are_bounded_single_line_labels(self):
        for name in ("a" * 81, "two\nlines", "bad\x00name", "control\x7f"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                self.draft(version_name=name)

    def test_caller_cannot_read_edit_or_assign_another_callers_agent(self):
        saved = self.library.save(self.owner, self.draft())
        for operation in (
            lambda: self.library.get(self.other, saved.agent_id),
            lambda: self.library.save(self.other, self.draft(), saved.agent_id),
            lambda: self.library.assign(self.other, AssignInvestigator(
                agent_id=saved.agent_id, version=1, expected_revision=0)),
        ):
            with self.assertRaises(LibraryError) as raised:
                operation()
            self.assertEqual(raised.exception.status, 404)
        self.assertEqual([agent["id"] for agent in self.library.list(self.other)], ["cyber_defender"])

    def test_concurrent_stale_saves_cannot_overwrite_a_version(self):
        first = self.library.save(self.owner, self.draft())
        edit = self.draft(base_version=1, expected_latest_version=1)

        def save():
            try:
                return AgentLibrary(self.root, **self.options).save(self.owner, edit, first.agent_id).version
            except LibraryError as error:
                return error.status

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: save(), range(2)))
        self.assertCountEqual(results, [2, 409])
        self.assertEqual(self.library.versions(self.owner, first.agent_id), [1, 2])

    def test_role_assignment_pins_a_saved_version_and_survives_restart(self):
        first = self.library.save(self.owner, self.draft())
        assignment = self.library.assign(self.owner, AssignInvestigator(
            agent_id=first.agent_id, version=1, expected_revision=0))
        self.library.save(self.owner, self.draft(base_version=1, expected_latest_version=1), first.agent_id)
        self.assertEqual(AgentLibrary(self.root, **self.options).assignment(self.owner), assignment)
        self.assertEqual(assignment.version, 1)
        self.assertEqual(self.library.assignment(self.other).agent_id, "cyber_defender")
        with self.assertRaises(LibraryError) as raised:
            self.library.assign(self.owner, AssignInvestigator(
                agent_id="cyber_defender", version=1, expected_revision=0))
        self.assertEqual(raised.exception.status, 409)

    def test_models_tools_and_investigator_requirements_are_validated(self):
        for updates in ({"model": "not-configured"}, {"tool_ids": ["unknown"]}):
            with self.assertRaises(LibraryError) as raised:
                self.library.save(self.owner, self.draft().model_copy(update=updates))
            self.assertEqual(raised.exception.status, 422)
        draft = self.draft().model_copy(update={"tool_ids": []})
        saved = self.library.save(self.owner, draft)
        with self.assertRaisesRegex(LibraryError, "Investigator requires"):
            self.library.assign(self.owner, AssignInvestigator(
                agent_id=saved.agent_id, version=1, expected_revision=0))

    def test_invalid_names_oversized_uploads_and_duplicate_tools_are_refused(self):
        for name in ("../../secret.md", "nested/file.md", "nested\\file.md", "file.txt", "bad\x00.md"):
            with self.subTest(name=name), self.assertRaises(ValidationError):
                InstructionFile(name=name, content="text")
        with self.assertRaises(ValidationError):
            InstructionFile(name="large.md", content="a" * 65_537)
        for updates in ({"name": " "}, {"tool_ids": ["evidence", "evidence"]},
                        {"system_prompt": "", "instruction_files": []}):
            with self.assertRaises(ValidationError):
                SaveAgent(**{**self.draft().model_dump(), **updates})

    def test_untrusted_identity_and_path_traversal_are_refused(self):
        with self.assertRaises(LibraryError) as raised:
            self.library.list(Principal("forged", issuer="header"))
        self.assertEqual(raised.exception.status, 403)
        with self.assertRaises(LibraryError) as raised:
            self.library.get(self.owner, "../other")
        self.assertEqual(raised.exception.status, 404)

    def test_editor_exposes_existing_prompt_files_and_resolves_saved_instruction_contents(self):
        builtin = load_agent_spec()
        editor = AgentEditor(self.root, builtin)
        original = editor.library.get(self.owner, builtin.agent_id)
        self.assertTrue(original.instruction_files)
        self.assertTrue(editor.catalogue(self.owner, {})["foundation_files"])
        self.assertIs(editor.investigator_spec(self.owner), builtin)
        draft = SaveAgent(name="Custom Investigator", model=builtin.model, version_name="Focused triage",
                          system_prompt="Editor runtime instruction marker.",
                          instruction_files=[InstructionFile(name="extra.md", content="Uploaded instruction marker.")],
                          tool_ids=original.tool_ids)
        saved = editor.library.save(self.owner, draft)
        described = editor.describe_version(self.owner, saved)
        self.assertEqual(described["version_name"], "Focused triage")
        self.assertEqual(described["version_names"], {1: "Focused triage"})
        editor.library.assign(self.owner, AssignInvestigator(
            agent_id=saved.agent_id, version=1, expected_revision=0))
        selected = editor.investigator_spec(self.owner)
        self.assertEqual(selected.agent_id, saved.agent_id)
        self.assertEqual(selected.config_version, 1)
        self.assertEqual(selected.name, "Custom Investigator")
        self.assertEqual(editor.catalogue(self.owner, {})["assigned_agent"]["version_name"], "Focused triage")
        self.assertIn("Editor runtime instruction marker.", selected.instructions)
        self.assertIn("Uploaded instruction marker.", selected.instructions)
        for _, content in builtin.foundation_files:
            self.assertIn(content, selected.instructions)
        self.assertIs(editor.investigator_spec(self.other), builtin)