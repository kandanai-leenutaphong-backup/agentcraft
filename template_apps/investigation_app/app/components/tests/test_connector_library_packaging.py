"""The two function-app deployments stage the connector library, not a copy of it.

The staging block is extracted from each deploy.sh and executed verbatim, so this fails
when the script drifts; a hand-written recipe here would keep passing when it breaks.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

BLOCK_START = 'say "staging into ${STAGE}"'
BLOCK_END = "-type d -name tests -prune"

PIPELINE_MODULES = ("pipeline", "load_adx", "load_gremlin")


def extract_staging_block(script: Path) -> str:
    lines = script.read_text().splitlines()
    starts = [i for i, line in enumerate(lines) if BLOCK_START in line]
    ends = [i for i, line in enumerate(lines) if BLOCK_END in line]
    if len(starts) != 1 or not ends:
        raise AssertionError(f"cannot locate the staging block in {script}")
    return "\n".join(lines[starts[0] : ends[-1] + 1])


def run_staging_block(script: Path, stage: Path) -> None:
    deploy_dir = script.parent
    preamble = "\n".join(
        [
            "set -euo pipefail",
            'say() { echo "$*"; }',
            f'REPO_ROOT="{REPO_ROOT}"',
            f'DEPLOY_DIR="{deploy_dir}"',
            f'HERE="{deploy_dir}"',
            f'STAGE="{stage}"',
        ]
    )
    result = subprocess.run(
        ["bash", "-c", preamble + "\n" + extract_staging_block(script)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise AssertionError(f"staging {script} failed: {result.stderr}")


def import_in_stage(stage: Path, pipeline: str, modules: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    names = [f"app.data.data_pipelines.{pipeline}.{module}" for module in modules]
    probe = (
        "import importlib, sys\n"
        f"for name in {names!r}:\n"
        "    module = importlib.import_module(name)\n"
        f"    assert module.__file__.startswith({str(stage)!r}), (name, module.__file__)\n"
        "library = importlib.import_module('app.components.data_connector_library')\n"
        f"assert library.__file__.startswith({str(stage)!r}), library.__file__\n"
        "library.AdxConnector, library.GremlinGraph, library.SearchIndexClient\n"
        "print('staged-import-ok')\n"
    )
    # No repository path anywhere: PYTHONPATH and cwd are the stage, so a missing file cannot
    # be satisfied by the checkout it was copied from.
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "PYTHONPATH": str(stage),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [sys.executable, "-c", probe],
        cwd=stage,
        env=env,
        capture_output=True,
        text=True,
    )


class FunctionAppStagingTests(unittest.TestCase):
    pipelines = ("perth", "ait")

    def script(self, pipeline: str) -> Path:
        return REPO_ROOT / "app" / "data" / "data_pipelines" / pipeline / "deployment" / "deploy.sh"

    def test_each_stage_carries_the_library_search_and_pipeline_and_no_old_package(self) -> None:
        for pipeline in self.pipelines:
            with self.subTest(pipeline=pipeline), tempfile.TemporaryDirectory() as tmp:
                stage = Path(tmp) / "stage"
                stage.mkdir()
                run_staging_block(self.script(pipeline), stage)

                for required in (
                    "function_app.py",
                    "host.json",
                    "app/__init__.py",
                    "app/components/__init__.py",
                    "app/components/data_connector_library/__init__.py",
                    "app/components/data_connector_library/kusto/connector.py",
                    "app/components/data_connector_library/graph/connector.py",
                    "app/components/azure_search/__init__.py",
                    "app/data/data_pipelines/framework/__init__.py",
                    f"app/data/data_pipelines/{pipeline}/pipeline.py",
                ):
                    self.assertTrue((stage / required).exists(), f"{pipeline}: missing {required}")

                self.assertFalse(
                    (stage / "app/data/data_connectors").exists(),
                    f"{pipeline}: the superseded package was staged",
                )
                stale = [
                    str(path.relative_to(stage))
                    for path in stage.rglob("*.py")
                    if "data_connectors" in path.read_text(errors="ignore")
                ]
                self.assertEqual([], stale, f"{pipeline}: staged files still name the old package")

    def test_each_stage_imports_its_pipeline_in_isolation(self) -> None:
        for pipeline in self.pipelines:
            with self.subTest(pipeline=pipeline), tempfile.TemporaryDirectory() as tmp:
                stage = Path(tmp) / "stage"
                stage.mkdir()
                run_staging_block(self.script(pipeline), stage)
                result = import_in_stage(stage, pipeline, PIPELINE_MODULES)
                self.assertEqual(0, result.returncode, f"{pipeline}: {result.stderr}")
                self.assertIn("staged-import-ok", result.stdout)

    def test_a_stage_without_azure_search_fails_to_import(self) -> None:
        pipeline = "perth"
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "stage"
            stage.mkdir()
            run_staging_block(self.script(pipeline), stage)
            shutil.rmtree(stage / "app" / "components" / "azure_search")
            result = import_in_stage(stage, pipeline, PIPELINE_MODULES)
            self.assertNotEqual(0, result.returncode, "staging azure_search is not actually required")
            self.assertIn("azure_search", result.stderr)


if __name__ == "__main__":
    unittest.main()
