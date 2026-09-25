"""Template adapter over `foundry_ops.pipeline` for one agent package.

Owns only what is template-specific: the image layout (runtime `app/` minus its built-in example package, the
package under `package/`, vendored libraries, Dockerfile, lock), the `agentconfig` package reading, the offline
self-check and the env + run-manifest context. Action functions keep the `(ctx, client...)` signatures `cli.py`
calls; every lifecycle rule lives in the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
import io
import os
from pathlib import Path
import sys
import time
from typing import Any, Callable
import unittest

from foundry_ops import pipeline
from foundry_ops.core import EvidenceLedger, RefusedError, RunManifest
# ENV_FORMATS, MANIFEST_KEYS, parse_env, validate_env, release_label, source_manifest, stage, _canonical: re-exported.
from foundry_ops.pipeline import (ENV_FORMATS, MANIFEST_KEYS, PACKAGE_IMAGE_DIR, Clients, RunSpec, check_package_tools,
                                  contained, parse_env, release_label, source_manifest, validate_env)
from foundry_ops.pipeline import canonical as _canonical, stage_context as stage

DEPLOY = Path(__file__).resolve().parent
ROOT = DEPLOY.parent
APP = ROOT / "app"
REPO = ROOT.parents[1]
ENV_DIR = DEPLOY / "env"
RECORDS = DEPLOY / "records"
CLOUD_ACTIONS = ("preflight", "build", "deploy", "invoke", "verify", "evaluate", "register-evaluator", "optimize",
                 "select", "promote", "inspect", "logs", "teardown")
WRITE_ACTIONS = frozenset({"build", "deploy", "invoke", "evaluate", "register-evaluator", "optimize", "promote",
                           "teardown"})
LEDGER_ACTIONS = frozenset({"select"})
APP_SUFFIXES = frozenset({".py", ".yaml", ".md"})
# The built-in example package inside app/; with or without an external package it is never runtime source.
EXAMPLE_FILES = frozenset({"configuration.yaml", "agent_tools.py"})
EXAMPLE_PROMPTS = "prompts/"
LIBRARY_PACKAGES = {"agentcraft_core": "framework-core/src/agentcraft_core",
                    "llm_interface": "llm-interface/src/llm_interface",
                    "agentconfig": "modular-agents/modules/agent-config-build/agentconfig"}
DEPLOY_FILES = ("Dockerfile", "runtime-requirements.lock")


# --- image layout ----------------------------------------------------------------------------

def _is_example(name: str) -> bool:
    return name in EXAMPLE_FILES or name.startswith(EXAMPLE_PROMPTS)


def package_inputs(package: Path | None) -> dict[str, Path]:
    """Package-relative files: an external package folder, or the built-in example inside app/ when None."""
    return pipeline.package_inputs(APP if package is None else package,
                                   include=_is_example if package is None else None)


def package_config(package: Path | None) -> dict[str, Any]:
    """Default agent's model and tools; every tool `module:function` must resolve to a module inside the package."""
    from agentconfig import load_agent_config

    root = APP if package is None else package
    files = package_inputs(package)
    sources: list[tuple[Path, bytes]] = []
    try:
        config = load_agent_config(root / "configuration.yaml", strict=True, sources=sources)
        roster = config["agents"]
        agent = roster[roster["default"]]
        model, tools = agent["model"], agent.get("tools", [])
    except (Exception, SystemExit) as error:
        raise RefusedError("package_config", "configuration.yaml is not one valid default agent") from error
    if any(Path(path).resolve() != (root / "configuration.yaml").resolve() for path, _ in sources):
        raise RefusedError("package_config", "configuration includes fragments outside configuration.yaml")
    if not isinstance(model, str) or not model or not isinstance(tools, list):
        raise RefusedError("package_config", "agent model and tool list required")
    return {"agent": roster["default"], "model": model, "tools": check_package_tools(tools, files)}


def source_inputs(libraries: Path, package: Path | None = None) -> dict[str, Path]:
    """Exact build context: runtime (app/ minus the example package), package/, vendored libraries, Dockerfile, lock."""
    files: dict[str, Path] = {}
    for path in sorted(APP.rglob("*")):
        name = path.relative_to(APP).as_posix()
        if path.is_file() and path.suffix in APP_SUFFIXES and "__pycache__" not in path.parts \
                and name != "source-manifest.json" and not _is_example(name):
            files["app/" + name] = contained(path, APP)
    for name, path in package_inputs(package).items():
        files[f"{PACKAGE_IMAGE_DIR}/{name}"] = path
    for package_name, relative in LIBRARY_PACKAGES.items():
        base = libraries / relative
        if not (base / "__init__.py").is_file():
            raise RefusedError("library_missing", f"library package not found: {package_name}")
        for path in sorted(base.rglob("*")):
            if path.is_file() and (path.suffix == ".py" or path.name == "py.typed") and "__pycache__" not in path.parts:
                files[f"lib/{package_name}/{path.relative_to(base).as_posix()}"] = contained(path, libraries)
    for name in DEPLOY_FILES:
        files[name] = contained(DEPLOY / name, DEPLOY)
    return files


def run_offline_tests() -> dict[str, Any]:
    output = io.StringIO()
    started = time.monotonic()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"), top_level_dir=str(ROOT / "tests"))
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    summary = {"tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
               "skipped": len(result.skipped), "seconds": round(time.monotonic() - started, 3)}
    if not result.wasSuccessful():
        sys.stderr.write(output.getvalue())
        raise RuntimeError("offline tests failed")
    return summary


@dataclass(frozen=True)
class TemplateLayout:
    """`pipeline.ImageLayout` for this template."""

    libraries: Path

    def build_inputs(self, package: Path | None) -> dict[str, Path]:
        return source_inputs(self.libraries, package)

    def package_config(self, package: Path | None) -> dict[str, Any]:
        return package_config(package)

    def self_check(self) -> dict[str, Any]:
        return run_offline_tests()


# --- context ---------------------------------------------------------------------------------

@dataclass
class Context:
    spec: RunSpec
    ledger: EvidenceLedger
    layout: TemplateLayout
    run: RunManifest | None = None

    @property
    def agent(self) -> str:
        return self.spec.agent

    @property
    def observed_inputs(self) -> dict[str, dict[str, str]]:
        return self.spec.observed_inputs

    def clients(self, **values: Any) -> Clients:
        return Clients(layout=self.layout, **values)


def load_context(environment: str, manifest_sha256: str, action: str, *, libraries: Path, env_dir: Path = ENV_DIR,
                 records: Path = RECORDS, repo: Path = REPO) -> Context:
    """Env targets, then the digest-pinned run manifest binding them; only then create evidence state."""
    spec, run, ledger = pipeline.load_env_manifest(environment, manifest_sha256, action, env_dir=env_dir,
                                                   records=records, repo=repo)
    return Context(spec, ledger, TemplateLayout(libraries), run)


def load_spec_context(path: str | os.PathLike[str], spec_sha256: str, *, libraries: Path, repo: Path = REPO) -> Context:
    """One digest-pinned run spec; binds its bytes under `<records>/<series>/run-spec.json`."""
    spec = pipeline.load_run_spec(path, expected_sha256=spec_sha256, repo=repo)
    return Context(spec, pipeline.open_ledger(spec), TemplateLayout(libraries))


# --- actions: (ctx, client...) -> pipeline stage ---------------------------------------------

def expected_identity(ctx: Context, deployed: dict[str, Any]) -> dict[str, str]:
    return pipeline.expected_identity(ctx.spec, deployed)


def preflight(ctx: Context, az: Callable[[list[str]], Any], project: Any) -> dict[str, Any]:
    return pipeline.preflight(ctx.spec, ctx.clients(az=az, project=project), ctx.ledger)


def build(ctx: Context, az: Callable[[list[str]], Any], project: Any) -> dict[str, Any]:
    return pipeline.build(ctx.spec, ctx.clients(az=az, project=project), ctx.ledger)


def deploy(ctx: Context, project: Any, *, optimization_config: Any = None, candidate_record: Any = None,
           **timing: Any) -> dict[str, Any]:
    return pipeline.deploy(ctx.spec, ctx.clients(project=project, **timing), ctx.ledger,
                           optimization_config=optimization_config, candidate_record=candidate_record)


def promote(ctx: Context, project: Any, *, optimization_config: Any = None, candidate_record: Any = None,
            **timing: Any) -> dict[str, Any]:
    return pipeline.promote(ctx.spec, ctx.clients(project=project, **timing), ctx.ledger,
                            optimization_config=optimization_config, candidate_record=candidate_record)


def invoke(ctx: Context, openai_client: Any, text: str, *, stream: bool = False) -> dict[str, Any]:
    return pipeline.invoke(ctx.spec, ctx.clients(openai=openai_client), ctx.ledger, text, stream=stream)


def load_journeys(ctx: Context, path: Any) -> list[dict[str, Any]]:
    return pipeline.load_journeys(ctx.spec, path)


def invoke_journeys(ctx: Context, openai_client: Any, path: Any) -> list[dict[str, Any]]:
    return pipeline.invoke_journeys(ctx.spec, ctx.clients(openai=openai_client), ctx.ledger, path)


def verify(ctx: Context, project: Any, openai_client: Any, bearer_token: str, http_client: Any = None,
           journeys: Any = None) -> dict[str, Any]:
    clients = ctx.clients(project=project, openai=openai_client, http=http_client, token=lambda: bearer_token)
    return pipeline.verify(ctx.spec, clients, ctx.ledger, journeys=journeys)


def evaluate(ctx: Context, eval_client: Any, criteria: Any, items: Any, *, previous: bool = False, project: Any = None,
             **timing: Any) -> dict[str, Any]:
    return pipeline.evaluate(ctx.spec, ctx.clients(evals=eval_client, project=project, **timing), ctx.ledger, criteria,
                             items, previous=previous)


def register_evaluator(ctx: Context, project: Any, eval_client: Any, evaluator: Any, **timing: Any) -> dict[str, Any]:
    return pipeline.register_evaluator(ctx.spec, ctx.clients(project=project, evals=eval_client, **timing), ctx.ledger,
                                       evaluator)


def optimize(ctx: Context, project: Any, optimization: Any, train: Any, validation: Any, *, eval_client: Any = None,
             previous: bool = False, request_factory: Any = None, sleep: Callable[[float], None] = time.sleep,
             clock: Callable[[], float] = time.monotonic) -> dict[str, Any]:
    clients = ctx.clients(project=project, evals=eval_client, request_factory=request_factory, sleep=sleep, clock=clock)
    return pipeline.optimize(ctx.spec, clients, ctx.ledger, optimization, train, validation, previous=previous)


def select(ctx: Context, rule: Any, *, demonstration: bool = False) -> dict[str, Any]:
    return pipeline.select(ctx.spec, None, ctx.ledger, rule, demonstration=demonstration)


def inspect_agent(ctx: Context, project: Any) -> dict[str, Any]:
    return pipeline.inspect(ctx.spec, ctx.clients(project=project), ctx.ledger)


def logs(ctx: Context, project: Any, session_id: str | None = None, max_sessions: int = 3) -> dict[str, Any]:
    return pipeline.logs(ctx.spec, ctx.clients(project=project), ctx.ledger, session_id, max_sessions)


def teardown(ctx: Context, project: Any, openai_client: Any, bearer_token: str, *, execute: bool,
             http_client: Any = None, sleep: Callable[[float], None] = time.sleep) -> dict[str, Any]:
    clients = ctx.clients(project=project, openai=openai_client, http=http_client, token=lambda: bearer_token,
                          sleep=sleep)
    return pipeline.teardown(ctx.spec, clients, ctx.ledger, execute=execute)
