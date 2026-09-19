"""CLI composition root; direct service calls do not require a browser Origin."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

from .api import make_server
from .contracts import LOCAL_OPERATOR, Refusal, strict_json, experiment_document
from .executors import CopilotExecutor
from .registry import TaskRegistry, default_registry
from .service import OptimizationService, preflight_experiment

DEFAULT_ROOT = Path.home() / ".local" / "state" / "agentcraft-optimization"


def native_environment(use_github_cli: bool) -> dict[str, str]:
    environment = dict(os.environ)
    if not use_github_cli:
        return environment
    executable = shutil.which("gh")
    if executable is None:
        raise Refusal("github_cli_unavailable", 409)
    try:
        result = subprocess.run([executable, "auth", "token", "--hostname", "github.com"],
                                capture_output=True, timeout=15, check=False)
        token = result.stdout.decode("utf-8").strip()
    except (OSError, UnicodeError, subprocess.TimeoutExpired) as error:
        raise Refusal("github_cli_auth_unavailable", 409) from error
    if result.returncode != 0 or not token or any(character.isspace() for character in token):
        raise Refusal("github_cli_auth_unavailable", 409)
    environment["COPILOT_GITHUB_TOKEN"] = token
    return environment


def main(argv=None, *, registry: TaskRegistry | None = None, copilot_executor=None) -> int:
    parser = argparse.ArgumentParser(description="Local optimization loop; native config-only authoring requires explicit model-call grant.")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="Private external artifact root")
    parser.add_argument("--allow-model-calls", action="store_true", help="Grant native model calls for this service process")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("describe", "preflight", "run", "status", "report", "serve", "cancel", "restore", "feedback", "respond"):
        command = commands.add_parser(name)
        command.add_argument("--root", type=Path, default=argparse.SUPPRESS)
        command.add_argument("--allow-model-calls", action="store_true", default=argparse.SUPPRESS)
        command.add_argument("--json", action="store_true", help="JSON is the default structured output")
        if name == "run":
            source = command.add_mutually_exclusive_group(required=True)
            source.add_argument("--task")
            source.add_argument("--experiment", type=Path)
            command.add_argument("--executor", default=None, choices=["deterministic", "copilot"])
            command.add_argument("--idempotency-key", default=None)
        if name == "preflight":
            command.add_argument("--experiment", type=Path, required=True)
        if name in {"run", "serve", "preflight"}:
            command.add_argument("--github-cli-auth", action="store_true",
                                 help="Explicitly borrow the existing gh login in memory for native inference")
            command.add_argument("--native-max-attempts", type=int, choices=[1, 2], default=None)
            command.add_argument("--native-timeout-seconds", type=float, default=None)
        if name in {"report", "cancel", "restore", "feedback", "respond"}:
            command.add_argument("--run", required=True)
        if name == "status":
            command.add_argument("--run")
        if name == "report":
            command.add_argument("--format", choices=["json", "csv", "html"], default="json")
        if name == "serve":
            command.add_argument("--host", default="127.0.0.1")
            command.add_argument("--port", type=int, default=8765)
        if name in {"restore", "feedback", "respond"}:
            command.add_argument("--idempotency-key", required=True)
            command.add_argument("--candidate-id", required=name == "restore")
        if name == "feedback":
            command.add_argument("--text", required=True)
        if name == "respond":
            command.add_argument("--feedback-id", required=True)
            command.add_argument("--disposition", choices=["apply", "clarify", "defer", "decline"], required=True)
            command.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    try:
        if getattr(args, "github_cli_auth", False) and not args.allow_model_calls:
            raise Refusal("model_calls_not_allowed", 409)
        registry = registry if registry is not None else default_registry()
        document = None
        if getattr(args, "experiment", None) is not None:
            if (getattr(args, "executor", None) is not None or getattr(args, "native_max_attempts", None) is not None
                    or getattr(args, "native_timeout_seconds", None) is not None):
                raise Refusal("experiment_argument_conflict")
            try:
                with args.experiment.open("rb") as stream:
                    content = stream.read(32769).decode("utf-8")
            except (OSError, UnicodeError) as error:
                raise Refusal("experiment_unreadable") from error
            document = experiment_document(strict_json(content, "invalid_experiment", 32768))
        native = copilot_executor
        if args.allow_model_calls and native is None:
            try:
                native = CopilotExecutor(
                    command=(str(Path.home() / ".local" / "bin" / "copilot"),),
                    original_repository=Path(__file__).resolve().parents[3],
                    environment=native_environment(getattr(args, "github_cli_auth", False)),
                    model="gpt-6-astra", effort="max",
                    supported_efforts=("low", "medium", "high", "xhigh", "max"))
            except (OSError, ValueError) as error:
                raise Refusal("native_executor_not_configured", 409) from error
        if document is not None:
            receipt = preflight_experiment(document, registry=registry, allow_model_calls=args.allow_model_calls,
                                           copilot_executor=native)
            if args.command == "preflight":
                print(json.dumps(receipt, indent=2, ensure_ascii=True, allow_nan=False))
                return 0
        with OptimizationService(args.root, allow_model_calls=args.allow_model_calls,
                                 copilot_executor=native, registry=registry,
                                 native_max_attempts=getattr(args, "native_max_attempts", None) or 2,
                                 native_timeout_seconds=(120 if getattr(args, "native_timeout_seconds", None) is None
                                                         else args.native_timeout_seconds)) as service:
            if args.command == "describe":
                result = service.describe()
            elif args.command == "run":
                if document is not None:
                    result = service.run_experiment(LOCAL_OPERATOR, document, args.idempotency_key or uuid.uuid4().hex,
                                                    background=False)
                else:
                    result = service.start(LOCAL_OPERATOR, args.task, args.executor or "deterministic",
                                           args.idempotency_key or uuid.uuid4().hex, background=False)
            elif args.command == "status":
                result = service.get_run(LOCAL_OPERATOR, args.run) if args.run else {"runs": service.list_runs(LOCAL_OPERATOR)}
            elif args.command == "cancel":
                result = service.cancel(LOCAL_OPERATOR, args.run)
            elif args.command == "restore":
                result = service.restore(LOCAL_OPERATOR, args.run, args.candidate_id, args.idempotency_key)
            elif args.command == "feedback":
                result = service.submit_feedback(LOCAL_OPERATOR, args.run, args.text, args.candidate_id, args.idempotency_key)
            elif args.command == "respond":
                result = service.respond_feedback(LOCAL_OPERATOR, args.run, args.feedback_id, args.disposition,
                                                   args.reason, args.candidate_id, args.idempotency_key)
            elif args.command == "report":
                content, _ = service.report(LOCAL_OPERATOR, args.run, args.format)
                sys.stdout.buffer.write(content)
                return 0
            else:
                server = make_server(service, args.host, args.port)
                bound = f"[{args.host}]" if ":" in args.host else args.host
                print(f"http://{bound}:{server.server_port}", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
                return 0
            print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
            return 1 if args.command == "run" and result.get("status") in {"failed", "blocked", "timed_out"} else 0
    except Refusal as error:
        print(json.dumps({"error": error.code}), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())