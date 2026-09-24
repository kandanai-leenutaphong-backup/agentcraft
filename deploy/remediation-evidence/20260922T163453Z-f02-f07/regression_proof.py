"""Reproduce prechange adapter defects from archived bytes, without importing old runners."""

import ast
import copy
import importlib.util
import json
import sys
import tarfile
from types import SimpleNamespace

import evidence


def functions(text, names, namespace):
    nodes = [node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef) and node.name in names]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "archived-functions", "exec"), namespace)


def main():
    with tarfile.open(evidence.OUT / "before-f02-source.tar.gz") as archive:
        old_live = archive.extractfile("testbeds/foundry-agent optimization/deploy/live.py").read().decode()
        old_eval = archive.extractfile("testbeds/foundry-agent-evaluation/deploy/experiment.py").read().decode()
    old_code = next(node.value.value for node in ast.parse(old_live).body if isinstance(node, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "EXACT_CODE" for target in node.targets))
    old = {}
    exec(old_code, old)
    sys.path.insert(0, str(evidence.ROOT / "testbeds/foundry-agent optimization/deploy"))
    import live
    new = {}
    exec(live.EXACT_CODE, new)
    nested = {"sample": {"output_text": "Iris-setosa"}, "ground_truth": "Iris-setosa"}
    assert old["grade"]({}, nested) == 0 and new["grade"]({}, nested) == 1
    try:
        old["grade"](None, {"response": "Iris-setosa", "ground_truth": "Iris-setosa"})
    except AttributeError:
        old_null = "AttributeError"
    else:
        raise AssertionError("prechange sample=None defect did not reproduce")
    assert new["grade"](None, {"response": "Iris-setosa", "ground_truth": "Iris-setosa"}) == 1
    spec = importlib.util.spec_from_file_location("evaluation_current", evidence.ROOT / "testbeds/foundry-agent-evaluation/deploy/experiment.py")
    current = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(current)
    old_namespace = {"json": json, "require": current.require, "ORACLE": current.ORACLE, "PINS": current.PINS,
                     "read_record": current.read_record, "TERMINAL": current.TERMINAL, "sanitized": current.sanitized}
    functions(old_eval, {"sample_text", "rows_check", "collect"}, old_namespace)
    conflict = {"sample": {"output_text": "one", "output": [{"role": "assistant", "content": "two"}]}}
    assert old_namespace["sample_text"](conflict) == "one"
    try:
        current.sample_text(conflict)
    except ValueError:
        pass
    else:
        raise AssertionError("repaired conflict guard failed")
    retained = copy.deepcopy(current.read_record("20260922T075532691203Z-reconcile.json")["result"])
    retained["items"][0]["results"][0]["score"] = True
    def model(value):
        return SimpleNamespace(**value, model_dump=lambda **kwargs: value)
    criteria = current.read_record("definition-intent.json")["request"]["testing_criteria"]
    page = SimpleNamespace(data=[model(row) for row in retained["items"]], has_next_page=lambda: False)
    client = SimpleNamespace(evals=SimpleNamespace(retrieve=lambda identifier: model({"id": identifier, "testing_criteria": criteria}),
        runs=SimpleNamespace(output_items=SimpleNamespace(list=lambda **kwargs: page))))
    run = model(retained["aggregate"])
    assert old_namespace["collect"](client, retained["identity"], run)["accepted"]
    assert not current.collect(client, retained["identity"], run)["accepted"]
    result = {"F02": {"nested_before": 0, "nested_after": 1, "sample_none_before": old_null, "sample_none_after": 1},
        "F03": {"conflict_before": "silently chose direct output", "conflict_after": "ValueError",
                "boolean_score_accepted_before": True, "boolean_score_accepted_after": False},
        "source": evidence.digest((evidence.OUT / "before-f02-source.tar.gz").read_bytes()),
        "historical_receipts": "read only; modified fixture held in memory; no verdict overwrite or inference"}
    print(json.dumps(evidence.save("before-after-regression-proof.json", result)))


if __name__ == "__main__":
    main()