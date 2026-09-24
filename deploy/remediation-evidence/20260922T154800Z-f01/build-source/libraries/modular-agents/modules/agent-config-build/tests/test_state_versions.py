from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest

from agentconfig import AgentDraft, AgentStoreError, AgentVersionStore, AssignAgent, SaveAgent


class MemoryCAS:
    def __init__(self):
        self.records = {}
        self.lock = Lock()
        self.barrier = None

    def load(self, owner):
        with self.lock:
            documents, version = self.records.get(owner, ({}, None))
            return dict(documents), version

    def compare_exchange(self, owner, expected, documents):
        if self.barrier:
            self.barrier.wait(timeout=5)
        with self.lock:
            version = self.records.get(owner, ({}, None))[1]
            if expected != version:
                return False
            self.records[owner] = (dict(documents), str(int(version or "0") + 1))
            return True


def store(path, storage):
    return AgentVersionStore(path, builtin_id="builtin",
        builtin=AgentDraft(name="Builtin", model="model", system_prompt="Original"),
        validate=lambda draft: None, validate_assignment=lambda draft: None, storage=storage)


def draft(**changes):
    return SaveAgent(**{"name": "Agent", "model": "model", "system_prompt": "Instructions", **changes})


def test_remote_contract_restart_owner_immutable_and_assignment(tmp_path):
    storage = MemoryCAS()
    first = store(tmp_path, storage)
    saved = first.save("owner", draft())
    other = store(tmp_path, storage)
    assert other.get("owner", saved.agent_id) == saved
    assigned = other.assign("owner", AssignAgent(agent_id=saved.agent_id, version=1, expected_revision=0))
    first.save("owner", draft(base_version=1, expected_latest_version=1), saved.agent_id)
    assert other.get("owner", saved.agent_id, 1) == saved
    assert store(tmp_path, storage).assignment("owner") == assigned
    for operation, status in (
        (lambda: other.get("foreign", saved.agent_id), 404),
        (lambda: other.save("owner", draft(base_version=1, expected_latest_version=1), saved.agent_id), 409),
        (lambda: other.assign("owner", AssignAgent(agent_id=saved.agent_id, version=2, expected_revision=0)), 409),
    ):
        with pytest.raises(AgentStoreError) as error:
            operation()
        assert error.value.status == status
    assert list(tmp_path.iterdir()) == []


def test_concurrent_remote_stores_commit_exactly_once(tmp_path):
    storage = MemoryCAS()
    saved = store(tmp_path, storage).save("owner", draft())
    storage.barrier = Barrier(2)

    def save():
        try:
            return store(tmp_path, storage).save("owner", draft(base_version=1, expected_latest_version=1), saved.agent_id).version
        except AgentStoreError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        attempts = [executor.submit(save) for _ in range(2)]
        assert sorted(attempt.result(timeout=10) for attempt in attempts) == [2, 409]
    assert store(tmp_path, storage).versions("owner", saved.agent_id) == [1, 2]