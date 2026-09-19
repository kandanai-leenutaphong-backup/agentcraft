"""Investigation adapter: offline checks and explicitly authorized prompt-live probe."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time


REPO = Path(__file__).resolve().parents[3]
APP = REPO / "template_apps/investigation_app"
TASKS = REPO / "optimization_framework/tasks/investigation"
TEST = REPO / "optimization_framework/tests/test_investigation_adapter.py"
DEFAULT_PYTHON = "/tmp/agentcraft-investigation-closeout/env/bin/python"
LIMITS = [
    "Synthetic service fixtures, not real model behavior or live data acceptance.",
    "Native browser verifies baseline app and persisted profile UI with synthetic native tool invocations.",
    "Production ASGI lifespan and deployed authentication remain unverified.",
    "Editable app/library imports; no independent isolation or held-out acceptance claim.",
    "Suspect-profile implementation has local synthetic acceptance only; no live-model or deployed claim.",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_hashes(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): sha256(path) for path in sorted(root.rglob("*"))
            if path.is_file() and "__pycache__" not in path.parts}


def source_hashes() -> dict[str, str]:
    roots = [APP / relative for relative in (
        "app/cybereye/backend", "app/cybereye/control", "app/cybereye/tests",
        "app/cybereye/frontend/src", "app/cybereye/frontend/tests", "deploy")]
    roots += [Path(__file__).parent, TASKS]
    roots += sorted((REPO / "libraries").glob("*/src"))
    roots += sorted((REPO / "libraries/modular-agents/modules").glob("*/src"))
    paths = {TEST, APP / "pyproject.toml", APP / "uv.lock"}
    frontend = APP / "app/cybereye/frontend"
    paths.update(frontend.glob("*.*"))
    for root in roots:
        paths.update(path for path in root.rglob("*") if path.is_file()
                     and not {"__pycache__", ".pytest_cache", "records", "artifacts"}.intersection(path.parts)
                     and path.suffix not in {".pyc", ".tsbuildinfo"})
    return {str(path.relative_to(REPO)): sha256(path) for path in sorted(paths)
            if path.is_file() and not path.name.startswith(".env")}


def clean_environment(home: Path, python: str) -> dict[str, str]:
    node = shutil.which("node")
    directories = [str(Path(python).parent), str(Path(node).parent) if node else "/usr/bin", "/usr/bin", "/bin"]
    return {
        "PATH": os.pathsep.join(dict.fromkeys(directories)), "HOME": str(home),
        "LANG": "C.UTF-8", "PYTHONPATH": str(APP), "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHON_DOTENV_DISABLED": "1", "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "UV_OFFLINE": "1", "UV_NO_SYNC": "1", "LIVE_PYTHON": python,
        "PLAYWRIGHT_BROWSERS_PATH": os.environ.get(
            "PLAYWRIGHT_BROWSERS_PATH", str(Path.home() / ".cache/ms-playwright")),
        "CYBEREYE_ALLOW_MODEL_CALLS": "false",
        "CYBEREYE_AGENT_STORE_DIR": str(home / "agents"),
    }


def run_command(command: list[str], *, cwd: Path, env: dict[str, str], timeout: int) -> dict:
    started = time.monotonic()
    timed_out = False
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            exit_code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            exit_code = process.returncode
        output.seek(0, os.SEEK_END)
        size = output.tell()
        output.seek(max(0, size - 16000))
        text = output.read().decode("utf-8", errors="replace")
    return {"command": command, "cwd": str(cwd), "exit_code": exit_code,
            "duration_seconds": round(time.monotonic() - started, 6), "timed_out": timed_out,
            "output": text, "output_bytes": size, "output_truncated": size > 16000}


def describe() -> dict:
    return {"adapter_version": 1, "app_root": str(APP),
            "commands": ["describe", "preflight", "verify", "prompt-live"],
            "task_contracts": {path.stem: {"path": str(path.relative_to(REPO)), "sha256": sha256(path)}
                               for path in sorted(TASKS.glob("*.yaml"))},
            "native_entry": ["bash", "deploy/deploy.sh", "browser-verify", "native-offline"],
            "limitations": LIMITS}


def profile_acceptance(report: dict) -> dict:
    required = {
        "profile-empty-state", "profile-native-control-update-1-and-api-readback",
        "profile-native-control-update-2-and-api-readback", "profile-native-control-update-3-and-api-readback",
        "profile-full-page-refresh-persistence", "profile-desktop-real-controls-citations-and-geometry",
        "profile-mobile-real-controls-citations-and-geometry",
        *("profile-refusal-" + name for name in ("anonymous-read", "anonymous-write", "foreign-read",
            "foreign-write", "stale", "invalid", "unsupported", "forged-owner")),
    }
    observed = {check["name"] for check in report.get("checks", [])}
    phases = {phase["name"]: phase["status"] for phase in report.get("phases", [])}
    passed = (report.get("status") == "PASS" and required <= observed
              and all(phases.get(name) == "PASS" for name in ("profile", "profile-reload"))
              and report.get("browser_closed") is True
              and report.get("server_cleanup", {}).get("fixture_cleanup") is True
              and report.get("native", {}).get("external_attempts") == [])
    return {"status": "offline_native_passed" if passed else "failed",
            "acceptance_class": "synthetic_native_offline", "production_source_change": True,
            "independent_acceptance": "not claimed", "live_model": "not executed",
            "checks": sorted(required & observed), "missing_checks": sorted(required - observed)}


def inspect_app() -> dict:
    sys.path.insert(0, str(APP))
    from app.cybereye.backend.agents.config import load_agent_spec
    from app.cybereye.backend.agents.editor import INVESTIGATOR_TOOLS

    spec = load_agent_spec()
    modules = {}
    for name in ("agentconfig", "llm_interface", "agent_framework", "azdata", "pytest", "pytest_asyncio"):
        module = importlib.import_module(name)
        source = Path(module.__file__).resolve()
        modules[name] = {"path": str(source), "sha256": sha256(source)}
    return {"executable": sys.executable, "python_version": sys.version.split()[0],
            "config_digest": spec.config_digest, "agent_id": spec.agent_id,
            "instructions_sha256": hashlib.sha256(spec.instructions.encode()).hexdigest(),
            "tools": [tool.openai_schema() for tool in spec.tools],
            "tool_sources": {tool.metadata.name: {"path": inspect.getsourcefile(tool.function),
                             "sha256": sha256(Path(inspect.getsourcefile(tool.function)))} for tool in spec.tools},
            "required_tools": sorted(INVESTIGATOR_TOOLS), "import_origins": modules}


def copy_control(destination: Path) -> Path:
    shutil.copytree(APP / "app/cybereye/control", destination)
    return destination / "agent_config.yaml"


def select_tools(config: Path, *, remove: tuple[str, ...] = (), add: tuple[str, ...] = ()) -> None:
    import yaml

    fragment = config.parent / "agents/cyber.yaml"
    document = yaml.safe_load(fragment.read_text())
    selected = document["agents"]["cyber_defender"]["tools"]
    available = yaml.safe_load((APP / "app/cybereye/control/agents/cyber.yaml").read_text())
    registry = {ref.split(":")[-1]: ref for ref in available["agents"]["cyber_defender"]["tools"]}
    selected[:] = [ref for ref in selected if ref.split(":")[-1] not in remove]
    for name in add:
        if registry[name] not in selected:
            selected.append(registry[name])
    fragment.write_text(yaml.safe_dump(document, sort_keys=False))


def definition_candidate(spec):
    from copy import deepcopy
    from dataclasses import replace

    original = next(tool for tool in spec.tools if tool.metadata.name == "profile_host_activity")
    parameters = deepcopy(original.metadata.parameters)
    parameters["properties"]["max_rows"]["maximum"] = 2

    async def bounded_profile(context, *, host: str, start: str, end: str, max_rows: int):
        if type(max_rows) is not int or not 1 <= max_rows <= 2:
            raise ValueError("candidate max_rows must be between 1 and 2")
        result = await original.function(context, host=host, start=start, end=end, max_rows=max_rows)
        return {**result, "candidate_definition": "investigation-row-cap-v1",
            "candidate_implementation_sha256": sha256(Path(__file__))}

    changed = replace(original, function=bounded_profile,
                      metadata=replace(original.metadata, parameters=parameters))
    return replace(spec, tools=tuple(changed if tool is original else tool for tool in spec.tools))


def preflight(python: str, home: Path) -> dict:
    env = clean_environment(home, python)
    probe = run_command([python, "-B", str(Path(__file__).resolve()), "preflight", "--in-process"],
                        cwd=APP, env=env, timeout=60)
    result = {"status": "passed" if probe["exit_code"] == 0 else "failed", "probe": probe}
    if probe["exit_code"] == 0:
        result["runtime"] = json.loads(probe["output"])
    result["prerequisites"] = {
        "node": shutil.which("node"),
        "vite": (APP / "app/cybereye/frontend/node_modules/vite/bin/vite.js").is_file(),
        "playwright": (APP / "app/cybereye/frontend/node_modules/playwright/package.json").is_file(),
    }
    if not all(result["prerequisites"].values()):
        result["status"] = "failed"
    return result


def verify(python: str, artifact_dir: Path, expected_pins: dict | None = None) -> dict:
    artifact_dir = artifact_dir.resolve()
    if artifact_dir.is_relative_to(REPO):
        raise ValueError("ARTIFACT_DIR must resolve outside checkout")
    artifact_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    run_root = Path(tempfile.mkdtemp(prefix="adapter-", dir=artifact_dir))
    before = source_hashes()
    local = APP / "app/cybereye/.local"
    state_before = tree_hashes(local)
    receipt = {**describe(), "status": "running", "artifact_dir": str(run_root),
               "source_hashes": before, "commands": [], "tasks": {},
               "candidate_scope": "copied control and adapter callable wrapper; authorized app profile implementation; verification does not edit source"}
    for task in ("tool_availability", "tool_definition", "prompt"):
        receipt["tasks"][task] = {"status": "not_run"}
    receipt["tasks"]["suspect_profile"] = {"status": "not_run"}
    try:
        if expected_pins is not None and expected_pins != before:
            raise ValueError("source pins changed; verification refused")
        with tempfile.TemporaryDirectory(prefix="investigation-state-") as temporary:
            home = Path(temporary)
            env = clean_environment(home, python)
            receipt["preflight"] = preflight(python, home)
            if receipt["preflight"]["status"] != "passed":
                raise RuntimeError("native preflight failed; no install attempted")
            evidence = run_root / "task-evidence.json"
            env["INVESTIGATION_TASK_EVIDENCE"] = str(evidence)
            tested = run_command([python, "-B", "-m", "pytest", str(TEST),
                                  str(APP / "app/cybereye/tests/test_suspect_profiles.py"), "-v", "-rA",
                                  "-p", "no:cacheprovider", "-p", "pytest_asyncio.plugin",
                                  "--basetemp", str(home / "pytest")], cwd=REPO, env=env, timeout=180)
            receipt["commands"].append(tested)
            if evidence.exists():
                receipt["tasks"].update(json.loads(evidence.read_text()))
                receipt["task_evidence_sha256"] = sha256(evidence)
            env["ARTIFACT_DIR"] = str(run_root / "browser")
            browser = run_command(["bash", "deploy/deploy.sh", "browser-verify", "native-offline"],
                                  cwd=APP, env=env, timeout=300)
            receipt["commands"].append(browser)
            reports = list((run_root / "browser").glob("run-*/report.json"))
            browser_ok = False
            if len(reports) == 1:
                report = json.loads(reports[0].read_text())
                receipt["tasks"]["suspect_profile"] = profile_acceptance(report)
                receipt["native_browser"] = {"path": str(reports[0]), "sha256": sha256(reports[0]),
                    **{key: report.get(key) for key in ("status", "phases", "browser_errors",
                       "blocked_browser_requests", "browser_closed", "server_cleanup", "server_exit",
                              "production_lifespan", "screenshots")}, "checks": len(report.get("checks", [])),
                          "check_names": [check["name"] for check in report.get("checks", [])],
                          "external_attempts": report.get("native", {}).get("external_attempts")}
                browser_ok = (report.get("status") == "PASS" and report.get("browser_closed") is True
                              and report.get("server_cleanup", {}).get("fixture_cleanup") is True)
            receipt["status"] = "offline_checks_passed_with_pending_acceptance" if (
                tested["exit_code"] == browser["exit_code"] == 0 and browser_ok
                and all(receipt["tasks"][task]["status"] == "offline_native_passed"
                        for task in ("tool_availability", "tool_definition", "prompt", "suspect_profile"))) else "failed"
        receipt["temporary_candidate_state_removed"] = not home.exists()
    except Exception as error:
        receipt["status"] = "failed"
        receipt["error"] = f"{type(error).__name__}: {error}"
    finally:
        receipt["source_unchanged"] = source_hashes() == before
        receipt["original_local_state_unchanged"] = tree_hashes(local) == state_before
        receipt["original_local_state_manifest_sha256"] = hashlib.sha256(
            json.dumps(state_before, sort_keys=True).encode()).hexdigest()
        if not receipt["source_unchanged"] or not receipt["original_local_state_unchanged"]:
            receipt["status"] = "failed"
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("describe", "preflight", "verify", "prompt-live"))
    parser.add_argument("--allow-model-calls", action="store_true")
    parser.add_argument("--python", default=DEFAULT_PYTHON)
    parser.add_argument("--artifact-dir", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--pins", type=Path, help="Previous receipt: refuse changed source_hashes")
    parser.add_argument("--in-process", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.in_process:
        print(json.dumps(inspect_app(), separators=(",", ":")))
        return 0
    if args.report:
        report = args.report.absolute()
        allowed = REPO / "optimization_framework/reports"
        prefix = "investigation-prompt" if args.command == "prompt-live" else "investigation-local"
        if report.parent.resolve() != allowed.resolve() or not report.name.startswith(prefix) or report.suffix != ".json":
            parser.error(f"report must be optimization_framework/reports/{prefix}*.json")
        if report.exists() or report.is_symlink():
            parser.error("report exists; choose a new receipt")
    if args.command == "prompt-live":
        import asyncio
        from prompt_live import prompt_live

        if not args.report:
            parser.error("prompt-live requires --report")
        result = asyncio.run(prompt_live(allow_model_calls=args.allow_model_calls))
    elif args.command == "describe":
        result = describe()
    elif args.command == "preflight":
        with tempfile.TemporaryDirectory(prefix="investigation-preflight-") as temporary:
            result = preflight(args.python, Path(temporary))
    else:
        if not args.artifact_dir or not args.report:
            parser.error("verify requires --artifact-dir and --report")
        pins = json.loads(args.pins.read_text())["source_hashes"] if args.pins else None
        result = verify(args.python, args.artifact_dir, pins)
    if args.report:
        with args.report.open("x") as output:
            json.dump(result, output, indent=2)
            output.write("\n")
        print(json.dumps({"status": result.get("status"), "report": str(args.report),
                          "tasks": {name: task["status"] for name, task in result.get("tasks", {}).items()}}))
    else:
        print(json.dumps(result, indent=2))
    return int(result.get("status") in {"failed", "refusal"})


if __name__ == "__main__":
    raise SystemExit(main())