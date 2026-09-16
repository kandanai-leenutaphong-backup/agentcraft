import json

import pytest

from agent_optimization import GradeEvaluator, RunSaveError, measure_run, run_recovery, write_json
from agent_optimization import persistence
from test_agent_optimization import FakeDataset, NEUTRAL_PROFILE


def test_completed_manifest_is_read_back_before_staging_is_removed(tmp_path):
    jobs = run_recovery(tmp_path, "run-1")
    outcome = jobs.commit("run-1", {"id": "run-1", "status": "completed"})
    assert outcome.saved and outcome.verified
    assert json.loads((tmp_path / "run.json").read_text()) == {"id": "run-1", "status": "completed"}
    assert list(jobs.pending()) == []


def test_failed_save_preserves_manifest_and_recommit_does_not_rerun_work(tmp_path, monkeypatch):
    jobs = run_recovery(tmp_path, "run-1")
    original_write = persistence._write

    def fail(*args, **kwargs):
        raise OSError("fixture storage failure")

    monkeypatch.setattr(persistence, "_write", fail)
    outcome = jobs.commit("run-1", {"id": "run-1", "result": [1, 2, 3]})
    assert not outcome.saved and outcome.recoverable
    assert outcome.artifact.path.is_file()
    monkeypatch.setattr(persistence, "_write", original_write)
    restarted = run_recovery(tmp_path, "run-1")
    restored = restarted.recommit(restarted.read("run-1"))
    assert restored.saved and restored.verified
    assert json.loads((tmp_path / "run.json").read_text())["result"] == [1, 2, 3]
    assert list(jobs.pending()) == []


def test_manifest_conflict_preserves_both_owned_outputs(tmp_path):
    path = tmp_path / "run.json"
    path.write_bytes(b'{"foreign":true}')
    outcome = run_recovery(tmp_path, "run-1").commit("run-1", {"id": "run-1"})
    assert outcome.state == "conflict" and outcome.recoverable
    assert path.read_bytes() == b'{"foreign":true}'


def test_immutable_json_refuses_overwrite(tmp_path):
    path = tmp_path / "generation.json"
    write_json(path, {"version": 1}, immutable=True)
    with pytest.raises(FileExistsError):
        write_json(path, {"version": 2}, immutable=True)
    assert json.loads(path.read_text()) == {"version": 1}


def test_manifest_store_refuses_another_run_identity(tmp_path):
    outcome = run_recovery(tmp_path, "run-1").commit("run-2", {"id": "run-2"})
    assert not outcome.saved and outcome.recoverable
    assert not (tmp_path / "run.json").exists()


def test_manifest_does_not_follow_a_symlink(tmp_path):
    target = tmp_path / "outside.json"
    target.write_bytes(b"preserve")
    (tmp_path / "run.json").symlink_to(target)
    outcome = run_recovery(tmp_path, "run-1").commit("run-1", {"id": "run-1"})
    assert not outcome.saved and outcome.recoverable
    assert target.read_bytes() == b"preserve"


@pytest.mark.parametrize("failed_save", [False, True])
def test_measured_run_manifest_recovers_without_repeating_prediction(tmp_path, monkeypatch, failed_save):
    calls = []

    def predict(prompt, evidence, model):
        calls.append(evidence)
        assert "expected" not in json.dumps(evidence)
        return {"grade": "accept", "rationale": "synthetic fixture"}

    dataset = FakeDataset()
    evaluator = GradeEvaluator(dataset, predict, NEUTRAL_PROFILE)
    directory = tmp_path / "measured-run"
    record = {"id": "measured-run", "stage": "training", "workers": 1}
    original_write = persistence._write

    def write(path, content, **options):
        if failed_save and path.name == "run.json":
            raise OSError("fixture manifest save failure")
        return original_write(path, content, **options)

    monkeypatch.setattr(persistence, "_write", write)

    def measure():
        return measure_run(evaluator, {"version": 1, "system_prompt": "Fixture", "model": "fixture"},
                           [], dataset.cases(), record, directory, lambda: False, lambda count: None)

    if failed_save:
        with pytest.raises(RunSaveError) as failure:
            measure()
        assert failure.value.outcome.recoverable
        monkeypatch.setattr(persistence, "_write", original_write)
        jobs = run_recovery(directory, record["id"])
        staged = jobs.read(record["id"])
        assert staged.payload["status"] == "completed"
        assert jobs.recommit(staged).verified
    else:
        assert measure()["status"] == "completed"
    assert len(calls) == len(dataset.cases())
    saved = json.loads((directory / "run.json").read_text())
    assert saved["cases_finished"] == saved["metrics"]["case_count"] == len(calls)
    assert len((directory / "cases.jsonl").read_text().splitlines()) == len(calls)
    assert (directory / "best.json").is_file() and (directory / "worst.json").is_file()