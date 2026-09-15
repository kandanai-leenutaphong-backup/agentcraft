import json

import pytest

from deploy.migrate_state import move_state


def fixture(tmp_path, status="ready"):
    source, target = tmp_path / "source", tmp_path / "target"
    record = source / "optimization/experiments/owner/experiment/experiment.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"status": status, "versions": [{"version": 1}]}))
    (source / "copilot-workspaces").mkdir()
    (source / "copilot-workspaces/kept.txt").write_text("private fixture")
    return source, target, record.read_bytes()


def test_moves_both_directories_and_preserves_record_bytes(tmp_path):
    source, target, expected = fixture(tmp_path)
    result = move_state(source, target, source_stopped=True)
    assert result["files_verified"] == {"optimization": 1, "copilot-workspaces": 1}
    assert not (source / "optimization").exists()
    assert not (source / "copilot-workspaces").exists()
    assert (target / "optimization/experiments/owner/experiment/experiment.json").read_bytes() == expected


@pytest.mark.parametrize("status", ["running", "baseline_running"])
def test_refuses_active_state(tmp_path, status):
    source, target, _ = fixture(tmp_path, status)
    with pytest.raises(ValueError, match="active"):
        move_state(source, target, source_stopped=True)
    assert (source / "optimization").exists()
    assert not target.exists()


def test_refuses_existing_destination_and_missing_stop_acknowledgement(tmp_path):
    source, target, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="stop"):
        move_state(source, target, source_stopped=False)
    (target / "optimization").mkdir(parents=True)
    with pytest.raises(ValueError, match="already exists"):
        move_state(source, target, source_stopped=True)
    assert (source / "optimization").exists()