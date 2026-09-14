#!/usr/bin/env python3
"""One tiny identity-authenticated call: does this identity reach the model?

WHAT IT PRINTS
--------------
Status, latency, deployment, reported model, token usage, response id.
Never the prompt, never the completion, never a token. A probe that prints
model output is a probe nobody can run in a shared terminal.

WHAT IT COSTS
-------------
One request, ``store=false``, output capped at 16 tokens.

EXIT CODES
----------
0  the deployment answered
2  configuration is invalid (bad endpoint, key env var set, ...)
3  authentication or authorization failed — check the RBAC role
4  the deployment was not found on this account
5  rate limited
6  timeout or connection failure
7  any other provider error

Usage:
    python scripts/probe.py
    python scripts/probe.py --deployment chat-batch
    python scripts/probe.py --endpoint https://other.openai.azure.com/ --json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

from azllm import DEFAULT_DEPLOYMENT, FoundryConfig, LlmError, connect  # noqa: E402

_EXIT_BY_CATEGORY = {
    "config": 2,
    "auth": 3,
    "not_found": 4,
    "rate_limit": 5,
    "timeout": 6,
    "connection": 6,
}
_EXIT_OTHER = 7

# Deliberately content-free. The answer is irrelevant; reachability is not.
_PROBE_PROMPT = "Reply with the single word: ok"
_PROBE_MAX_TOKENS = 16


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--deployment", default=None, help=f"deployment name (default: env or {DEFAULT_DEPLOYMENT})")
    parser.add_argument("--endpoint", default=None, help="account endpoint override")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds (default: 30)")
    parser.add_argument("--json", action="store_true", help="emit one JSON object instead of lines")
    args = parser.parse_args(argv)

    try:
        config = FoundryConfig.from_env()
        overrides: dict[str, Any] = {"timeout_secs": args.timeout, "max_retries": 0}
        if args.endpoint:
            overrides["endpoint"] = args.endpoint
        if args.deployment:
            overrides["deployment"] = args.deployment
        config = config.with_overrides(**overrides)
    except LlmError as exc:
        return _fail(exc, as_json=args.json)

    started = time.monotonic()
    try:
        with connect(config) as llm:
            result = llm.ask(
                _PROBE_PROMPT,
                max_output_tokens=_PROBE_MAX_TOKENS,
                store=False,
            )
    except LlmError as exc:
        return _fail(exc, as_json=args.json, elapsed_ms=_ms(started))

    report = {
        "ok": True,
        "host": config.account_host,
        "deployment": result.deployment,
        "model": result.model,
        "status": result.status,
        "latency_ms": _ms(started),
        "response_id": result.response_id,
        "usage": result.usage,
        "output_chars": len(result.text),
    }
    _emit(report, as_json=args.json)
    return 0


def _fail(exc: LlmError, *, as_json: bool, elapsed_ms: int | None = None) -> int:
    report = {
        "ok": False,
        "category": exc.category,
        "status_code": exc.status_code,
        "retryable": exc.retryable,
        "request_id": exc.request_id,
        "deployment": exc.deployment,
        "code": exc.code,
        "message": exc.message,
    }
    if elapsed_ms is not None:
        report["latency_ms"] = elapsed_ms
    _emit(report, as_json=as_json, stream=sys.stderr)
    return _EXIT_BY_CATEGORY.get(exc.category, _EXIT_OTHER)


def _emit(report: dict[str, Any], *, as_json: bool, stream: Any = sys.stdout) -> None:
    if as_json:
        print(json.dumps(report, sort_keys=True), file=stream)
        return
    for key, value in report.items():
        if value is not None:
            print(f"{key}: {value}", file=stream)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
