from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import threading
import time
from typing import Mapping, Sequence
import uuid


_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}\Z")
_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
_USAGE_NUMBERS = {
    "totalPremiumRequestCost", "totalUserRequests", "totalNanoAiu",
    "totalApiDurationMs", "lastCallInputTokens", "lastCallOutputTokens",
    "inputTokens", "outputTokens", "cacheReadTokens", "cacheWriteTokens",
    "cost", "duration", "premiumRequests", "totalRequests",
    "totalInputTokens", "totalOutputTokens", "totalCacheReadTokens",
    "totalCacheWriteTokens", "totalDurationMs",
    "reasoningTokens", "count", "tokenCount", "linesAdded", "linesRemoved", "filesModifiedCount",
}
_BASE_LIMITATIONS = [
    "Trusted local caller only; path checks and CLI permissions are not an OS sandbox.",
    "No independent evaluator isolation or provider-side cancellation guarantee.",
    "Only deny-all tools is supported; nonempty allowlists refuse.",
    "Raw stdout, stderr, prompts, tool arguments and private reasoning are not returned.",
    "CLI usage is self-reported, not billing reconciliation; hidden requests remain unknown.",
    "Fresh private runtime state is retained in the caller workspace for caller cleanup.",
    "Escaped descendants and remote inference settlement are unverified; same-group children are signalled.",
]
_KNOWN_EVENTS = {
    "session.start", "session.idle", "session.shutdown", "assistant.turn_start",
    "assistant.turn_end", "assistant.message_start", "assistant.message_delta",
    "assistant.reasoning", "assistant.reasoning_delta", "assistant.usage",
    "tool.execution_complete", "user.message", "session.info", "assistant.idle",
    "session.mcp_servers_loaded", "session.tools_updated", "session.usage_checkpoint",
}


def _number(value: object) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value) and value >= 0
    except OverflowError:
        return False


def _safe_name(value: object) -> str | None:
    return value if isinstance(value, str) and _NAME.fullmatch(value) else None


def _numeric_fields(raw: dict) -> dict:
    return {key: value for key, value in raw.items() if key in _USAGE_NUMBERS and _number(value)}


def _metrics(raw: dict) -> dict:
    result = _numeric_fields(raw)
    for field in ("requests", "usage", "codeChanges"):
        if isinstance(raw.get(field), dict):
            result[field] = _numeric_fields(raw[field])
    if isinstance(raw.get("tokenDetails"), dict):
        result["tokenDetails"] = {
            key: _numeric_fields(value) for key, value in raw["tokenDetails"].items()
            if key in {"input", "output", "cache_read", "cache_write"} and isinstance(value, dict)
        }
    return result


def _usage(path: Path) -> dict | None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > 1_000_000:
                return None
            content = stream.read(1_000_001)
            if len(content) > 1_000_000:
                return None
            raw = json.loads(content)
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(raw, dict):
        return None
    result = _metrics(raw)
    metrics = raw.get("modelMetrics")
    if isinstance(metrics, dict):
        result["modelMetrics"] = {
                model: _metrics(values)
            for model, values in metrics.items()
            if _safe_name(model) and isinstance(values, dict)
        }
    return result or None


class CopilotExecutor:
    """One synchronous native prompt. Configuration and cancellation belong to the host.

    supported_efforts must come from host-validated CLI model metadata, never task text.
    command is trusted host configuration; a Python script prefix supports offline fixtures.
    run returns payload-free evidence unless final-answer capture is explicitly approved.
    Captured candidate_output is final assistant text, never reasoning or raw events.
    """

    def __init__(
        self, *, command: Sequence[str], original_repository: Path,
        environment: Mapping[str, str], model: str, effort: str = "max",
        supported_efforts: Sequence[str] = (), allowed_tools: Sequence[str] = (),
        max_output_bytes: int = 2_000_000,
    ) -> None:
        if not command or not Path(command[0]).is_absolute() or not Path(command[0]).is_file():
            raise ValueError("command requires an absolute installed executable")
        if isinstance(command, str) or any(not isinstance(part, str) or "\0" in part for part in command):
            raise ValueError("command must be a trusted argv sequence")
        if not _safe_name(model) or model == "auto" or effort not in _EFFORTS:
            raise ValueError("explicit model and effort required")
        if allowed_tools:
            raise ValueError("nonempty tool allowlists are not yet supported")
        if not set(supported_efforts) <= _EFFORTS:
            raise ValueError("invalid supported efforts")
        if type(max_output_bytes) is not int or not 1024 <= max_output_bytes <= 10_000_000:
            raise ValueError("output bound must be 1024..10000000 bytes")
        repository = Path(original_repository)
        if not repository.is_absolute() or not repository.is_dir():
            raise ValueError("original_repository must be an existing absolute directory")
        self.command = tuple(command)
        self.repository = repository.resolve()
        self.environment = dict(environment)
        self.model = model
        self.effort = effort
        self.supported_efforts = tuple(supported_efforts)
        self.max_output_bytes = max_output_bytes

    def _workspace(self, workspace: Path) -> Path:
        supplied = Path(workspace)
        resolved = supplied.resolve(strict=True)
        if not supplied.is_absolute() or supplied != resolved or not resolved.is_dir():
            raise ValueError("workspace must be an absolute real directory without symlinks")
        if resolved == self.repository or resolved.is_relative_to(self.repository) or self.repository.is_relative_to(resolved):
            raise ValueError("workspace must be outside original repository ancestry")
        home = Path.home().resolve()
        if resolved == home or resolved.is_relative_to(home) or home.is_relative_to(resolved):
            raise ValueError("workspace must be outside user-home ancestry")
        for index, entry in enumerate(resolved.rglob("*")):
            if index >= 10000:
                raise ValueError("workspace exceeds bounded inspection")
            if entry.is_symlink() or (not entry.is_file() and not entry.is_dir()):
                raise ValueError("workspace contains symlink or special file")
            if entry.is_file() and entry.stat().st_nlink != 1:
                raise ValueError("workspace contains hardlinked file")
            if entry.name in {".git", ".github", ".copilot", "AGENTS.md"}:
                raise ValueError("workspace contains inherited native configuration")
        return resolved

    def run(
        self, prompt: str, *, workspace: Path, timeout_seconds: float = 120,
        cancel: threading.Event | None = None, expected_output: str | None = None,
        capture_final_answer: bool = False,
    ) -> dict:
        if type(capture_final_answer) is not bool:
            raise ValueError("capture_final_answer must be boolean")
        if not isinstance(prompt, str) or not prompt or "\0" in prompt or len(prompt) > 100000:
            raise ValueError("prompt must be nonempty bounded text")
        if not _number(timeout_seconds) or not 0 < timeout_seconds <= 120:
            raise ValueError("timeout_seconds must be positive and at most 120")
        if expected_output is not None and (not isinstance(expected_output, str) or not expected_output):
            raise ValueError("expected_output must be nonempty text")
        root = self._workspace(workspace)
        started = time.monotonic()
        session_id = str(uuid.uuid4())
        result = {
            "schema_version": 1, "status": "blocked", "elapsed_seconds": 0.0,
            "session_id": session_id, "model": self.model, "effort": self.effort,
            "resolved_model": None, "resolved_effort": None, "exit_code": None,
            "events": [], "usage": None,
            "coverage": {
                "jsonl": "unobserved", "usage": "unobserved",
                "tool_requests": "unobserved", "model_requests": "unobserved",
                "effort": "unverified", "expected_output": "not_requested",
            },
            "limitations": list(_BASE_LIMITATIONS), "failure_code": None,
            "cleanup": "not_started", "runtime_directory": None,
        }
        if self.effort not in self.supported_efforts:
            result["failure_code"] = "unvalidated_model_effort"
            result["elapsed_seconds"] = time.monotonic() - started
            return result
        if cancel is not None and cancel.is_set():
            result["status"] = "cancelled"
            result["elapsed_seconds"] = time.monotonic() - started
            return result
        runtime = root / (".native-" + session_id)
        runtime.mkdir(mode=0o700)
        home = runtime / "home"
        home.mkdir(mode=0o700)
        usage_path = runtime / "usage.json"
        result["runtime_directory"] = str(runtime)
        env = {key: value for key, value in self.environment.items()
               if key in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT", "COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"}}
        env.update({
            "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_CACHE_HOME": str(home / ".cache"), "XDG_STATE_HOME": str(home / ".state"),
            "TMPDIR": str(runtime), "COPILOT_HOME": str(runtime / "state"),
            "COPILOT_AUTO_UPDATE": "false", "COPILOT_OTEL_ENABLED": "false",
            "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT": "false", "CI": "true",
        })
        argv = [
            *self.command, "-C", str(root), "--model", self.model,
            "--reasoning-effort", self.effort, "--session-id", session_id,
            "--output-format", "json", "--stream", "on", "--usage-output-file", str(usage_path),
            "--available-tools=", "--deny-tool=shell", "--deny-tool=write", "--deny-tool=url",
            "--disallow-temp-dir", "--disable-builtin-mcps", "--no-custom-instructions",
            "--no-ask-user", "--no-auto-update", "--no-remote", "--no-remote-export",
            "--no-bash-env", "--log-level", "none",
            "--secret-env-vars=COPILOT_GITHUB_TOKEN,GH_TOKEN,GITHUB_TOKEN", "-p", prompt,
        ]
        try:
            process = subprocess.Popen(argv, cwd=root, env=env, stdin=subprocess.DEVNULL,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        except OSError:
            result["failure_code"] = "launch_failed"
            result["elapsed_seconds"] = time.monotonic() - started
            return result
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        interrupted = None
        try:
            with selectors.DefaultSelector() as selector:
                for stream, name in ((process.stdout, "stdout"), (process.stderr, "stderr")):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, selectors.EVENT_READ, name)
                while selector.get_map() or process.poll() is None:
                    if cancel is not None and cancel.is_set():
                        interrupted = "cancelled"
                        break
                    remaining = timeout_seconds - (time.monotonic() - started)
                    if remaining <= 0:
                        interrupted = "timed_out"
                        break
                    for key, _mask in selector.select(min(remaining, 0.05)):
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        if sum(map(len, buffers.values())) + len(chunk) > self.max_output_bytes:
                            interrupted = "output_limit"
                            break
                        buffers[key.data].extend(chunk)
                    if interrupted:
                        break
        finally:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    pass
                if sig == signal.SIGTERM:
                    try:
                        process.wait(timeout=0.3)
                    except subprocess.TimeoutExpired:
                        pass
            try:
                process.wait(timeout=1)
                result["cleanup"] = "process_reaped_group_signalled"
            except subprocess.TimeoutExpired:
                result["cleanup"] = "incomplete"
            process.stdout.close()
            process.stderr.close()
        result["exit_code"] = process.returncode
        self._parse(bytes(buffers["stdout"]), bytes(buffers["stderr"]), usage_path, expected_output,
                result, capture_final_answer=capture_final_answer)
        if interrupted:
            result["status"] = interrupted if interrupted != "output_limit" else "failed"
            result["failure_code"] = interrupted
        if result["cleanup"] == "incomplete":
            result["status"] = "blocked"
            result["failure_code"] = "unsettled_process"
        if result["status"] != "completed":
            result.pop("candidate_output", None)
        result["elapsed_seconds"] = time.monotonic() - started
        secrets = [self.environment[key] for key in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
                   if self.environment.get(key)]

        def redact(value):
            if isinstance(value, str):
                for secret in secrets:
                    value = value.replace(secret, "[REDACTED]")
            elif isinstance(value, list):
                value = [redact(item) for item in value]
            elif isinstance(value, dict):
                value = {redact(key): redact(item) for key, item in value.items()}
            return value

        return redact(result)

    def _parse(self, stdout: bytes, stderr: bytes, usage_path: Path, expected: str | None,
               result: dict, *, capture_final_answer: bool = False) -> None:
        result["usage"] = _usage(usage_path)
        result["coverage"]["usage"] = "read_back" if result["usage"] else "missing_or_invalid"
        malformed = False
        refusal = False
        terminal = False
        answer = None
        unknown = False
        requested = []
        dispatched = []
        completions = 0
        model_calls = 0
        observed_models = set()
        terminal_count = 0
        seen = {}
        for sequence, line in enumerate(stdout.splitlines(), 1):
            try:
                event = json.loads(line)
                if not isinstance(event, dict) or not isinstance(event.get("type"), str):
                    raise ValueError("unsupported event")
            except (ValueError, UnicodeError, RecursionError):
                malformed = True
                continue
            kind = event["type"]
            data = event.get("data", {})
            if not isinstance(data, dict):
                malformed = True
                continue
            event_id = _safe_name(event.get("id"))
            if event_id is not None:
                canonical = json.dumps(event, sort_keys=True)
                if event_id in seen:
                    malformed |= seen[event_id] != canonical
                    continue
                seen[event_id] = canonical
            public = {
                "sequence": sequence, "kind": "unsupported", "id": event_id,
                "parent_id": _safe_name(event.get("parentId")),
                "at": _safe_name(event.get("timestamp")),
            }
            refusal |= event.get("is_error") is True or bool(data.get("error"))
            if terminal_count:
                malformed = True
            if kind == "assistant.message":
                public["kind"] = kind
                answer = data.get("content")
                model = _safe_name(data.get("model"))
                if model:
                    observed_models.add(model)
                requests = data.get("toolRequests", [])
                if not isinstance(requests, list):
                    malformed = True
                else:
                    public["tool_requests"] = []
                    for request in requests:
                        if not isinstance(request, dict):
                            malformed = True
                            continue
                        call_id = _safe_name(request.get("toolCallId"))
                        name = _safe_name(request.get("name"))
                        malformed |= call_id is None or name is None
                        requested.append(call_id)
                        public["tool_requests"].append({"tool_call_id": call_id, "tool_name": name})
            elif kind == "result":
                public["kind"] = kind
                terminal_count += 1
                terminal = (type(event.get("exitCode")) is int and event["exitCode"] == 0
                            and event.get("sessionId") == result["session_id"])
                refusal |= event.get("exitCode", 0) != 0
            elif kind in {"session.error", "error", "assistant.refusal"}:
                public["kind"] = kind
                refusal = True
            elif kind == "tool.execution_start":
                public["kind"] = kind
                public["tool_name"] = _safe_name(data.get("toolName"))
                public["tool_call_id"] = _safe_name(data.get("toolCallId"))
                dispatched.append(public["tool_call_id"])
            elif kind == "model.call_start":
                public["kind"] = kind
                model_calls += 1
                model = _safe_name(data.get("model"))
                if model:
                    observed_models.add(model)
                public["model"] = model if model == self.model else None
                public["turn_id"] = _safe_name(data.get("turnId"))
            elif kind == "model.call_finished":
                public["kind"] = kind
                outcome = data.get("outcome")
                if not isinstance(outcome, str):
                    outcome = "unknown"
                    malformed = True
                public["outcome"] = outcome if outcome in {"success", "error", "failed", "cancelled"} else "unknown"
                public["turn_id"] = _safe_name(data.get("turnId"))
                refusal |= outcome in {"error", "failed", "cancelled"}
            elif kind in _KNOWN_EVENTS:
                public["kind"] = kind
                if kind == "tool.execution_complete":
                    completions += 1
                    public["tool_call_id"] = _safe_name(data.get("toolCallId"))
                    public["success"] = data.get("success") if type(data.get("success")) is bool else None
            else:
                unknown = True
            result["events"].append(public)
        diagnostic = stderr.decode("utf-8", errors="replace")
        if re.search(r"error|refus|not supported|unauthori[sz]ed|authentication|permission denied", diagnostic, re.I):
            refusal = True
        if isinstance(answer, str) and re.match(r"\s*(?:I (?:cannot|can't|am unable)|unable to|request (?:refused|denied))\b", answer, re.I):
            refusal = True
        if stderr.strip():
            result["limitations"].append("Stderr emitted; raw diagnostics withheld.")
        coverage = result["coverage"]
        coverage["jsonl"] = "invalid" if malformed else "partial" if unknown else "recognized" if result["events"] else "unobserved"
        coverage["tool_requests"] = {
            "observed_requests": len(requested), "observed_dispatches": len(dispatched),
            "observed_completions": completions,
            "completeness": "observed_events_only", "nested_commands": "unobserved",
            "nonempty_request_schema": "fixture_only",
        }
        coverage["model_requests"] = {"observed_starts": model_calls, "completeness": "observed_events_only"}
        if expected is not None:
            coverage["expected_output"] = "matched" if isinstance(answer, str) and answer.strip() == expected else "not_matched"
        models = (result["usage"] or {}).get("modelMetrics", {})
        if set(models) == {self.model} and (not observed_models or observed_models == {self.model}):
            result["resolved_model"] = self.model
        if result["usage"] and "modelMetrics" in result["usage"]:
            result["usage"]["modelMetrics"] = {model: values for model, values in models.items() if model == self.model}
        result["status"] = "failed"
        if refusal:
            result["failure_code"] = "native_refusal_or_error"
            result["status"] = "blocked"
        elif result["exit_code"] != 0:
            result["failure_code"] = "nonzero_exit"
        elif requested or dispatched or completions:
            result["failure_code"] = "deny_all_tool_violation"
        elif any((result["usage"] or {}).get("codeChanges", {}).values()):
            result["failure_code"] = "deny_all_write_violation"
        elif malformed or unknown or not terminal or not isinstance(answer, str) or not answer.strip():
            result["failure_code"] = "unsupported_or_incomplete_events"
        elif expected is not None and coverage["expected_output"] != "matched":
            result["failure_code"] = "unexpected_output"
        elif not result["usage"] or result["resolved_model"] is None:
            result["failure_code"] = "unverified_usage_or_model"
        elif (model_calls == 0
              or models[self.model].get("requests", {}).get("count", 0) < 1):
            result["failure_code"] = "unverified_model_request"
        else:
            result["status"] = "completed"
            result["resolved_effort"] = self.effort
            coverage["effort"] = "validated_metadata_and_accepted_flag_not_provider_echo"
            result["limitations"].append("Effort accepted by CLI; provider effective effort is not independently echoed.")
            if capture_final_answer:
                result["candidate_output"] = answer