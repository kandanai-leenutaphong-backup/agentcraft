import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.cybereye.backend.optimization.python_tools import PythonToolRunner


@pytest.fixture
def runner(tmp_path):
    executable = os.getenv("CYBEREYE_PYTHON_SANDBOX") or shutil.which("bwrap") or str(Path(__file__).resolve().parents[1] / ".local/tools/bubblewrap/usr/bin/bwrap")
    if not Path(executable).is_file():
        pytest.skip("Run ./deploy/deploy.sh optimization-setup for Python isolation")
    database = tmp_path / "case.sqlite"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE evidence(detector_id TEXT, category TEXT)")
        connection.executemany("INSERT INTO evidence VALUES(?,?)", [("7", "InitialAccess"), ("7", "InitialAccess"), ("8", "Execution")])
        connection.execute("CREATE TABLE training_profile(feature TEXT, value TEXT, support INTEGER)")
    return PythonToolRunner(executable, timeout_seconds=4), database


def test_python_queries_then_computes_custom_logic(runner):
    runtime, database = runner
    result = runtime.run('''from collections import Counter
import math

def run(ctx):
    rows = ctx.query("SELECT detector_id FROM evidence")["rows"]
    counts = Counter(row["detector_id"] for row in rows)
    return {"counts": dict(counts), "weighted": round(math.sqrt(counts["7"]) + counts["8"], 3)}
''', database)
    assert result["data"] == {"counts": {"7": 2, "8": 1}, "weighted": 2.414}
    assert result["query_count"] == 1


def test_python_cannot_read_host_files_labels_or_credentials(runner, monkeypatch):
    runtime, database = runner
    monkeypatch.setenv("OPTIMIZATION_TEST_SECRET", "fixture-value-never-in-sandbox")
    with tempfile.NamedTemporaryFile() as host_file:
        source = f'''import os
def run(ctx):
    return {{"host_file": os.path.exists({host_file.name!r}), "home": os.path.exists("/home"),
             "credential": os.environ.get("OPTIMIZATION_TEST_SECRET"), "labels": os.path.exists("/labels.sqlite")}}
'''
        assert runtime.run(source, database)["data"] == {"host_file": False, "home": False, "credential": None, "labels": False}


def test_python_named_parameters_keep_quote_bearing_values_as_data(runner):
    runtime, database = runner
    result = runtime.run('''def run(ctx):
    values = ["7", "8' OR 1=1 --"]
    parameters = {"token" + str(index): value for index, value in enumerate(values)}
    placeholders = ",".join(":" + name for name in parameters)
    rows = ctx.query("SELECT detector_id FROM evidence WHERE detector_id IN (" + placeholders + ")", parameters)["rows"]
    return {"detectors": [row["detector_id"] for row in rows]}
''', database)
    assert result["data"] == {"detectors": ["7", "7"]}


@pytest.mark.parametrize("body", [
    'ctx.query("SELECT * FROM labels")',
    'ctx.query("DELETE FROM evidence")',
    'open("/case.sqlite", "wb").write(b"no")',
    '__import__("socket").socket()',
    '__import__("os").fork()',
    '__import__("subprocess").run(["/usr/bin/true"])',
])
def test_python_refuses_unauthorized_operations(runner, body):
    runtime, database = runner
    with pytest.raises(ValueError):
        runtime.run(f"def run(ctx):\n    {body}\n    return {{}}\n", database)


def test_python_limits_runtime_output_and_contract(runner):
    runtime, database = runner
    for code in ('def run(ctx):\n    return {"large": "x" * 30000}',
                 'def run(ctx):\n    return {"large": "x" * (300 * 1024 * 1024)}',
                 'def run(ctx):\n    while True: pass', 'def wrong(ctx): return {}'):
        with pytest.raises(ValueError):
            runtime.run(code, database)