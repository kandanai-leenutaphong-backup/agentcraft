#!/usr/bin/env python3
"""One tiny identity-authenticated embedding call, per deployment, per account.

WHY A SEPARATE PROBE
--------------------
The two embedding deployments live on two different accounts, and a
deployment is reachable only through the endpoint of the account that owns
it. ``scripts/probe.py`` knows one endpoint; this one routes each deployment
to its own, through :func:`azllm.embedding_config`, so "small works but
large 404s" cannot be an artefact of the probe.

WHAT IT PRINTS
--------------
Host, deployment, reported model, vector count, dimensions, token usage and
latency. Never the input, never a vector component, never a token.

WHAT IT COSTS
-------------
One request per deployment, one short input each, no stored state.

EXIT CODES
----------
0  every probed deployment answered
2  configuration is invalid
3  authentication or authorization failed — check the RBAC role
4  the deployment was not found on the account it was sent to
5  rate limited
6  timeout or connection failure
7  any other provider error

Usage:
    python scripts/probe_embeddings.py                       # both deployments
    python scripts/probe_embeddings.py --deployment text-embedding-3-small
    python scripts/probe_embeddings.py --dimensions 256 --json
    python scripts/probe_embeddings.py --deployment text-embedding-3-small \
        --endpoint https://primary.example.invalid/
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

from azllm import (  # noqa: E402
    EMBEDDING_DEPLOYMENTS,
    LlmError,
    connect,
    embedding_config,
)

_EXIT_BY_CATEGORY = {
    "config": 2,
    "auth": 3,
    "not_found": 4,
    "rate_limit": 5,
    "timeout": 6,
    "connection": 6,
}
_EXIT_OTHER = 7

# Deliberately content-free and short: reachability is the question, and the
# text is never printed either way.
_PROBE_INPUT = "ok"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--deployment",
        action="append",
        default=None,
        help="embedding deployment; repeatable (default: every known one)",
    )
    parser.add_argument(
        "--endpoint",
        default=None,
        help="account endpoint override — the way to prove a wrong-account 404",
    )
    parser.add_argument("--dimensions", type=int, default=None, help="truncated vector width")
    parser.add_argument("--timeout", type=float, default=30.0, help="seconds (default: 30)")
    parser.add_argument("--json", action="store_true", help="emit one JSON object per probe")
    args = parser.parse_args(argv)

    targets = args.deployment or sorted(EMBEDDING_DEPLOYMENTS)
    worst = 0
    for name in targets:
        code = _probe(
            name,
            endpoint=args.endpoint,
            dimensions=args.dimensions,
            timeout=args.timeout,
            as_json=args.json,
        )
        worst = max(worst, code)
    return worst


def _probe(
    deployment: str,
    *,
    endpoint: str | None,
    dimensions: int | None,
    timeout: float,
    as_json: bool,
) -> int:
    try:
        config = embedding_config(deployment, endpoint=endpoint).with_overrides(
            timeout_secs=timeout, max_retries=0
        )
    except LlmError as exc:
        return _fail(exc, as_json=as_json)

    started = time.monotonic()
    try:
        with connect(config) as llm:
            result = llm.embed(_PROBE_INPUT, dimensions=dimensions)
    except LlmError as exc:
        return _fail(exc, as_json=as_json, elapsed_ms=_ms(started))

    _emit(
        {
            "ok": True,
            "host": config.account_host,
            "deployment": result.deployment,
            "model": result.model,
            "count": result.count,
            "dimensions": result.dimensions,
            "usage": result.usage,
            "latency_ms": _ms(started),
        },
        as_json=as_json,
    )
    return 0


def _fail(exc: LlmError, *, as_json: bool, elapsed_ms: int | None = None) -> int:
    report: dict[str, Any] = {
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
    print("", file=stream)


def _ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
