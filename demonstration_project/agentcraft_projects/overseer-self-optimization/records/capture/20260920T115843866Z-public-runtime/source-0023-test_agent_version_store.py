import hashlib
import json
import multiprocessing
from pathlib import Path
from unittest.mock import patch

import pytest

from agentconfig import (
    AgentDraft, AgentStoreError, AgentVersionStore, AssignAgent, SaveAgent,
)


def accept(draft):
    pass


def make_store(root):
    return AgentVersionStore(
        Path(root), builtin_id="default_agent",
        builtin=AgentDraft(name="Default", model="host-model", system_prompt="Original instructions."),
        validate=accept, validate_assignment=accept,
    )


def draft(**changes):
    return SaveAgent(**{
        "name": "Analyst", "model": "host-model", "system_prompt": "Exact instructions.\n",
        "tool_ids": ["evidence"], **changes,
    })


def namespace(root, owner="owner"):
    return root / hashlib.sha256(owner.encode("utf-8")).hexdigest()


def concurrent_save(root, agent_id, barrier, results):
    store = make_store(root)
    barrier.wait(timeout=10)
    try:
        result = store.save("owner", draft(base_version=1, expected_latest_version=1), agent_id)
        results.put(result.version)
    except AgentStoreError as exc:
        results.put(exc.status)


def test_round_trip_preserves_layout_bytes_permissions_and_legacy_records(tmp_path):
    store = make_store(tmp_path)
    saved = store.save("owner", draft(version_name="Baseline"))
    path = namespace(tmp_path) / saved.agent_id / "versions/1.json"
    original = path.read_bytes()
    assert original == (saved.model_dump_json(indent=2) + "\n").encode("utf-8")
    assert path.stat().st_mode & 0o777 == 0o600
    assert namespace(tmp_path).stat().st_mode & 0o777 == 0o700
    assert make_store(tmp_path).get("owner", saved.agent_id) == saved
    store.save("owner", draft(base_version=1, expected_latest_version=1), saved.agent_id)
    assert path.read_bytes() == original
    legacy = saved.model_dump_json(exclude={"version_name"})
    path.write_text(legacy, encoding="utf-8")
    assert store.get("owner", saved.agent_id, 1).version_name == ""
    assert store.version_names("owner", saved.agent_id) == {1: "", 2: ""}
    assert path.read_text(encoding="utf-8") == legacy


@pytest.mark.parametrize("action", ["save", "assign"])
def test_builtin_is_persisted_before_edit_or_assignment(tmp_path, action):
    store = make_store(tmp_path)
    original = store.get("owner", "default_agent", 1)
    assert not tmp_path.joinpath(hashlib.sha256(b"owner").hexdigest()).exists()
    if action == "save":
        store.save("owner", draft(base_version=1, expected_latest_version=1), "default_agent")
    else:
        store.assign("owner", AssignAgent(agent_id="default_agent", version=1, expected_revision=0))
    store.builtin = AgentDraft(name="Replacement", model="other", system_prompt="Replacement")
    assert store.get("owner", "default_agent", 1) == original
    assert make_store(tmp_path).get("owner", "default_agent", 1) == original


def test_opaque_owner_ids_are_hashed_without_normalization(tmp_path):
    store = make_store(tmp_path)
    owner = "../../outside/tenant:subject"
    saved = store.save(owner, draft())
    assert saved.owner_id == owner
    assert (namespace(tmp_path, owner) / saved.agent_id / "versions/1.json").is_file()
    assert store.get(owner, saved.agent_id) == saved
    for other in ("owner", owner.upper()):
        with pytest.raises(AgentStoreError) as error:
            store.get(other, saved.agent_id)
        assert error.value.status == 404
        assert [entry["id"] for entry in store.list(other)] == ["default_agent"]


@pytest.mark.parametrize("owner", ["", None, 12])
def test_invalid_owner_is_refused_without_creating_paths(tmp_path, owner):
    with pytest.raises(AgentStoreError) as error:
        make_store(tmp_path).save(owner, draft())
    assert error.value.status == 400
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("agent_id", ["../escape", "/absolute", "nested/agent", "bad\\agent", "bad\x00"])
def test_agent_path_escape_is_refused(tmp_path, agent_id):
    with pytest.raises(AgentStoreError) as error:
        make_store(tmp_path).get("owner", agent_id)
    assert error.value.status == 404
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("change", [
    {"owner_id": "other"}, {"agent_id": "other"}, {"version": 2},
    {"schema_version": 2}, {"unexpected": True}, {"system_prompt": ""},
])
def test_tampered_records_refuse_read_save_and_assignment(tmp_path, change):
    store = make_store(tmp_path)
    saved = store.save("owner", draft())
    path = namespace(tmp_path) / saved.agent_id / "versions/1.json"
    path.write_text(json.dumps({**saved.model_dump(), **change}), encoding="utf-8")
    tampered = path.read_bytes()
    for operation in (
        lambda: store.get("owner", saved.agent_id),
        lambda: store.save("owner", draft(base_version=1, expected_latest_version=1), saved.agent_id),
        lambda: store.assign("owner", AssignAgent(agent_id=saved.agent_id, version=1, expected_revision=0)),
    ):
        with pytest.raises(AgentStoreError) as error:
            operation()
        assert error.value.status == 404
    assert path.read_bytes() == tampered
    assert store.versions("owner", saved.agent_id) == [1]
    assert not (namespace(tmp_path) / "roles.json").exists()


@pytest.mark.parametrize("payload", [b"{", b"\xff"])
def test_unreadable_json_is_a_store_error(tmp_path, payload):
    store = make_store(tmp_path)
    saved = store.save("owner", draft())
    (namespace(tmp_path) / saved.agent_id / "versions/1.json").write_bytes(payload)
    with pytest.raises(AgentStoreError) as error:
        store.get("owner", saved.agent_id)
    assert error.value.status == 404


@pytest.mark.parametrize("location", ["owner", "agent", "versions", "record", "roles", "lock"])
def test_symlink_locations_are_refused_without_touching_target(tmp_path, location):
    root = tmp_path / "store"
    store = make_store(root)
    saved = store.save("owner", draft())
    store.assign("owner", AssignAgent(agent_id=saved.agent_id, version=1, expected_revision=0))
    owner = namespace(root)
    paths = {
        "owner": owner, "agent": owner / saved.agent_id,
        "versions": owner / saved.agent_id / "versions",
        "record": owner / saved.agent_id / "versions/1.json",
        "roles": owner / "roles.json", "lock": owner / ".lock",
    }
    path = paths[location]
    target = tmp_path / "target"
    path.rename(target)
    path.symlink_to(target, target_is_directory=target.is_dir())
    before = {str(item.relative_to(tmp_path)): item.read_bytes()
              for item in (target.rglob("*") if target.is_dir() else [target]) if item.is_file()}
    with pytest.raises(AgentStoreError) as error:
        if location == "roles":
            store.assignment("owner")
        elif location == "lock":
            store.save("owner", draft())
        else:
            store.get("owner", saved.agent_id)
    assert error.value.status in {400, 404}
    after = {str(item.relative_to(tmp_path)): item.read_bytes()
             for item in (target.rglob("*") if target.is_dir() else [target]) if item.is_file()}
    assert after == before


def test_owner_symlink_cannot_alias_another_namespace_inside_root(tmp_path):
    store = make_store(tmp_path)
    store.save("other", draft())
    namespace(tmp_path).symlink_to(namespace(tmp_path, "other"), target_is_directory=True)
    with pytest.raises(AgentStoreError) as error:
        store.list("owner")
    assert error.value.status == 400


def test_stale_cas_and_missing_base_preserve_all_bytes(tmp_path):
    store = make_store(tmp_path)
    saved = store.save("owner", draft())
    for changes in ({"base_version": 1}, {"base_version": 2, "expected_latest_version": 1}):
        with pytest.raises(AgentStoreError) as error:
            store.save("owner", draft(**changes), saved.agent_id)
        assert error.value.status == 409
    assert store.get("owner", saved.agent_id) == saved
    assert store.versions("owner", saved.agent_id) == [1]


def test_separate_process_writers_publish_once(tmp_path):
    store = make_store(tmp_path)
    saved = store.save("owner", draft())
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    results = context.Queue()
    workers = [context.Process(target=concurrent_save, args=(tmp_path, saved.agent_id, barrier, results))
               for _ in range(2)]
    try:
        for worker in workers:
            worker.start()
        assert sorted(results.get(timeout=15) for _ in workers) == [2, 409]
        for worker in workers:
            worker.join(timeout=10)
            assert worker.exitcode == 0
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(timeout=5)
        results.close()
    assert store.versions("owner", saved.agent_id) == [1, 2]
    assert store.get("owner", saved.agent_id, 1) == saved
    assert list(tmp_path.rglob(".writing-*")) == []


def test_assignment_pins_version_and_refuses_stale_foreign_or_corrupt_target(tmp_path):
    store = make_store(tmp_path)
    saved = store.save("owner", draft())
    request = AssignAgent(agent_id=saved.agent_id, version=1, expected_revision=0)
    assigned = store.assign("owner", request)
    store.save("owner", draft(base_version=1, expected_latest_version=1), saved.agent_id)
    assert make_store(tmp_path).assignment("owner") == assigned
    assert assigned.version == 1
    with pytest.raises(AgentStoreError) as error:
        store.assign("owner", request)
    assert error.value.status == 409
    with pytest.raises(AgentStoreError) as error:
        store.assign("other", request)
    assert error.value.status == 404
    foreign = store.save("other", draft())
    roles = namespace(tmp_path) / "roles.json"
    for payload in ("{", json.dumps({**assigned.model_dump(), "agent_id": foreign.agent_id})):
        roles.write_text(payload, encoding="utf-8")
        with pytest.raises(AgentStoreError) as error:
            store.assignment("owner")
        assert error.value.status == 404


def test_policy_callbacks_refuse_before_publication(tmp_path):
    store = make_store(tmp_path)
    with patch.object(store, "validate", side_effect=AgentStoreError(422, "host policy")):
        with pytest.raises(AgentStoreError, match="host policy"):
            store.save("owner", draft())
    assert list(tmp_path.iterdir()) == []
    saved = store.save("owner", draft())
    for callback in ("validate", "validate_assignment"):
        with patch.object(store, callback, side_effect=AgentStoreError(422, "host policy")):
            with pytest.raises(AgentStoreError, match="host policy"):
                store.assign("owner", AssignAgent(agent_id=saved.agent_id, version=1, expected_revision=0))
    assert store.assignment("owner").revision == 0


@pytest.mark.parametrize("operation", ["link", "replace", "fsync"])
def test_failed_publication_cleans_temporary_file_and_preserves_previous_state(tmp_path, operation):
    store = make_store(tmp_path)
    saved = store.save("owner", draft())
    request = AssignAgent(agent_id=saved.agent_id, version=1, expected_revision=0)
    assigned = store.assign("owner", request)
    with patch(f"os.{operation}", side_effect=OSError("disk unavailable")):
        with pytest.raises(OSError, match="disk unavailable"):
            if operation == "replace":
                store.assign("owner", request.model_copy(update={"expected_revision": 1}))
            else:
                store.save("owner", draft(base_version=1, expected_latest_version=1), saved.agent_id)
    assert store.get("owner", saved.agent_id) == saved
    assert store.assignment("owner") == assigned
    assert list(tmp_path.rglob(".writing-*")) == []