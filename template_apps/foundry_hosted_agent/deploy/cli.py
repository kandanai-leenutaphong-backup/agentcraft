"""deploy.sh command line: each action maps onto one `foundry_ops.pipeline` stage through `lifecycle.py`; `run`
executes the ordered stage sequence from one run spec. Refusals happen before any Azure call or evidence write."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

import lifecycle
from foundry_ops import pipeline
from foundry_ops.core import FoundryOpsError, RefusedError, error_summary, sanitize, utc_stamp
from lifecycle import CLOUD_ACTIONS, ENV_DIR, LEDGER_ACTIONS, RECORDS, REPO, WRITE_ACTIONS

DEFAULT_INPUT = "How many words are in: hello from a Foundry hosted agent"
# Option -> actions it applies to; any other combination refuses before side effects.
ACTION_OPTIONS = {"input": {"invoke"}, "stream": {"invoke"}, "journeys": {"invoke", "verify"},
                  "criteria": {"evaluate"}, "items": {"evaluate"}, "evaluator": {"register-evaluator"},
                  "optimization": {"optimize"}, "train": {"optimize"}, "validation": {"optimize"},
                  "rule": {"select"}, "demonstration": {"select", "run"},
                  "optimization_config": {"deploy", "promote"}, "instructions_from_candidate": {"deploy", "promote"},
                  "session_id": {"logs"}, "previous_version": {"evaluate", "optimize"},
                  "until": {"run"}, "from_stage": {"run"}}
# Env/manifest mode only; a run spec declares these inputs.
REQUIRED_OPTIONS = {"evaluate": ("criteria", "items"), "register-evaluator": ("evaluator",),
                    "optimize": ("optimization", "train", "validation"), "select": ("rule",)}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="deploy.sh", description=__doc__.splitlines()[0])
    parser.add_argument("action", choices=("test", *CLOUD_ACTIONS, "run"))
    parser.add_argument("-e", "--environment", help="env/<environment>.env and env/<environment>.run.json")
    parser.add_argument("--manifest-sha256", help="reviewed SHA-256 of env/<environment>.run.json")
    parser.add_argument("--spec", help="run spec (JSON or YAML) inside the repository; replaces -e/--manifest-sha256")
    parser.add_argument("--spec-sha256", help="reviewed SHA-256 of the run spec")
    parser.add_argument("--authorize-cloud-write", action="store_true",
                        help="explicit authorization for " + ", ".join(sorted(WRITE_ACTIONS)) + " and run (executed)")
    parser.add_argument("--records", help="evidence root inside the repository (default deploy/records)")
    parser.add_argument("--env-dir", help="directory inside the repository holding <environment>.env and "
                                          "<environment>.run.json (default deploy/env)")
    parser.add_argument("--plan", action="store_true", help="teardown: read and record the plan only")
    parser.add_argument("--input", help="invoke: text sent to the agent")
    parser.add_argument("--stream", action="store_true", help="invoke: streaming Responses call")
    parser.add_argument("--journeys", help="invoke/verify: pinned journeys JSON")
    parser.add_argument("--criteria", help="evaluate: pinned testing-criteria JSON")
    parser.add_argument("--items", help="evaluate: pinned item rows (JSON list or JSONL)")
    parser.add_argument("--evaluator", help="register-evaluator: pinned evaluator spec JSON")
    parser.add_argument("--optimization", help="optimize: pinned optimization spec JSON")
    parser.add_argument("--train", help="optimize: pinned train rows")
    parser.add_argument("--validation", help="optimize: pinned validation rows")
    parser.add_argument("--rule", help="select: pinned frozen selection rule JSON")
    parser.add_argument("--demonstration", action="store_true",
                        help="select/run: promote the top candidate as a labelled demonstration when none beats baseline")
    parser.add_argument("--optimization-config", help="deploy/promote: pinned {instructions, model?} overlay JSON")
    parser.add_argument("--instructions-from-candidate", help="deploy/promote: pinned select result record")
    parser.add_argument("--session-id", help="logs: one session id")
    parser.add_argument("--previous-version", action="store_true",
                        help="evaluate/optimize: target the run manifest's previous_version instead of this "
                             "series' version")
    parser.add_argument("--until", help="run: last stage (inclusive): " + ", ".join(pipeline.STAGES))
    parser.add_argument("--from", dest="from_stage", help="run: first stage; earlier stages must be retained complete")
    return parser.parse_args(argv)


def refuse(message: str) -> int:
    print(json.dumps({"status": "refused", "error": message}), file=sys.stderr)
    return 2


def _inside_repo(value: str, *, must_exist: bool, code: str, message: str) -> Path:
    path = Path(value)
    path = path if path.is_absolute() else Path.cwd() / path
    if path.is_symlink() or not path.resolve().is_relative_to(REPO.resolve()) \
            or not (path.is_dir() if must_exist else path.parent.is_dir()):
        raise RefusedError(code, message)
    return path


def _records_root(value: str | None) -> Path:
    if value is None:
        return RECORDS
    return _inside_repo(value, must_exist=False, code="records_path",
                        message="--records must be a non-symlink directory inside the repository")


def _env_root(value: str | None) -> Path:
    if value is None:
        return ENV_DIR
    return _inside_repo(value, must_exist=True, code="env_dir_path",
                        message="--env-dir must be an existing non-symlink directory inside the repository")


def _check(args: argparse.Namespace) -> str | None:
    """Every refusal decidable from the command line alone; returns the message or None."""
    spec_mode = args.spec is not None or args.spec_sha256 is not None
    if args.action == "run":
        writes = any(stage in pipeline.WRITE_STAGES for stage in pipeline.window(args.until, args.from_stage))
    else:
        writes = args.action in WRITE_ACTIONS
    execute = writes and not (args.action == "teardown" and args.plan)
    if execute and not args.authorize_cloud_write:
        return (f"{args.action} writes to the cloud; pass --authorize-cloud-write "
                "(or teardown --plan for a read-only plan)")
    if args.plan and (args.action != "teardown" or args.authorize_cloud_write):
        return "--plan applies only to teardown and excludes --authorize-cloud-write"
    if args.authorize_cloud_write and not writes:
        return f"--authorize-cloud-write does not apply to read-only action {args.action}"
    for option, actions in ACTION_OPTIONS.items():
        if getattr(args, option) not in (None, False) and args.action not in actions:
            return f"--{option.replace('_', '-').replace('from-stage', 'from')} does not apply to {args.action}"
    if spec_mode:
        if not (args.spec and args.spec_sha256):
            return "--spec requires --spec-sha256 <reviewed digest>"
        if args.environment or args.manifest_sha256 or args.env_dir or args.records:
            return "--spec excludes -e, --manifest-sha256, --env-dir and --records (the spec names its records)"
    else:
        if args.action == "run":
            return "run requires --spec FILE --spec-sha256 <reviewed digest>"
        missing = [option for option in REQUIRED_OPTIONS.get(args.action, ()) if getattr(args, option) is None]
        if missing:
            return f"{missing[0]}_missing: {args.action} requires " + " ".join(f"--{name} FILE" for name in missing)
    if args.input is not None and args.journeys is not None:
        return "invoke takes --input or --journeys, not both"
    if not spec_mode and (not args.environment or not args.manifest_sha256):
        return "cloud actions require -e <environment> and --manifest-sha256 <reviewed digest>"
    return None


def _dispatch(args: argparse.Namespace, ctx: lifecycle.Context, clients: pipeline.Clients) -> Any:
    declared = (lambda kind: ctx.spec.repo / ctx.spec.declared(kind)
                if ctx.spec.origin == "spec" and ctx.spec.declared(kind) else None)
    journeys = args.journeys if args.journeys is not None else declared("journeys")
    project, openai_client, token = clients.project, clients.openai, clients.token
    if args.action == "run":
        return pipeline.run(ctx.spec, clients, ctx.ledger, until=args.until, from_=args.from_stage,
                            demonstration=args.demonstration)
    if args.action == "invoke":
        if args.input is None and journeys is not None:
            return lifecycle.invoke_journeys(ctx, openai_client, journeys)
        return lifecycle.invoke(ctx, openai_client, args.input or DEFAULT_INPUT, stream=args.stream)
    overlay = {"optimization_config": args.optimization_config, "candidate_record": args.instructions_from_candidate}
    actions = {
        "preflight": lambda: lifecycle.preflight(ctx, clients.az, project),
        "build": lambda: lifecycle.build(ctx, clients.az, project),
        "deploy": lambda: lifecycle.deploy(ctx, project, **overlay),
        "promote": lambda: lifecycle.promote(ctx, project, **overlay),
        "verify": lambda: lifecycle.verify(ctx, project, openai_client, token(), journeys=journeys),
        "evaluate": lambda: lifecycle.evaluate(ctx, clients.evals, args.criteria, args.items,
                                               previous=args.previous_version, project=project),
        "register-evaluator": lambda: lifecycle.register_evaluator(ctx, project, clients.evals, args.evaluator),
        "optimize": lambda: lifecycle.optimize(ctx, project, args.optimization, args.train, args.validation,
                                               eval_client=clients.evals, previous=args.previous_version),
        "inspect": lambda: lifecycle.inspect_agent(ctx, project),
        "logs": lambda: lifecycle.logs(ctx, project, args.session_id),
        "teardown": lambda: lifecycle.teardown(ctx, project, openai_client, token(), execute=not args.plan),
    }
    return actions[args.action]()


def main(argv: list[str] | None = None, environ: dict[str, str] | os._Environ = os.environ) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.action == "test":
        print(json.dumps({"status": "complete", "action": "test", "result": lifecycle.run_offline_tests()}))
        return 0
    try:
        message = _check(args)
    except FoundryOpsError as error:
        message = f"{error.code}: {error}"
    if message:
        return refuse(message)
    libraries = Path(environ.get("AGENTCRAFT_LIBRARIES") or REPO / "libraries")
    try:
        if args.spec:
            ctx = lifecycle.load_spec_context(args.spec, args.spec_sha256, libraries=libraries)
            if args.action == "run":
                pipeline.plan(ctx.spec, ctx.ledger, until=args.until, from_=args.from_stage)
        else:
            ctx = lifecycle.load_context(args.environment, args.manifest_sha256, args.action, libraries=libraries,
                                         env_dir=_env_root(args.env_dir), records=_records_root(args.records))
    except (FoundryOpsError, ValueError, OSError) as error:
        return refuse(getattr(error, "code", type(error).__name__) + ": " + str(error))
    started, events = time.monotonic(), []
    receipt: dict[str, Any] = {"action": args.action, "environment": args.environment, "spec": args.spec,
                               "status": "blocked", "manifest_sha256": ctx.spec.sha256, "started_at": utc_stamp()}
    try:
        if args.action in LEDGER_ACTIONS:
            receipt["result"] = lifecycle.select(ctx, args.rule, demonstration=args.demonstration)
        else:
            with pipeline.cloud_clients(ctx.spec, layout=ctx.layout, events=events) as clients:
                receipt["result"] = _dispatch(args, ctx, clients)
        receipt["status"] = receipt["result"]["status"] if args.action == "run" else "complete"
    except Exception as error:
        receipt["error"] = error_summary(error)
        receipt["code"] = getattr(error, "code", None)
    receipt.update(seconds=round(time.monotonic() - started, 3), az=sanitize(events), inputs=ctx.observed_inputs)
    retained = ctx.ledger.retain(f"{utc_stamp()}-{args.action}.json", receipt)
    run_code = receipt["result"].get("code") if args.action == "run" and "result" in receipt else None
    print(json.dumps({"status": receipt["status"], "action": args.action, "receipt": retained["path"],
                      "code": receipt.get("code") or run_code, "seconds": receipt["seconds"]}))
    return 0 if receipt["status"] in ("complete", "pending", "baseline_retained") else 2


if __name__ == "__main__":
    sys.exit(main())
