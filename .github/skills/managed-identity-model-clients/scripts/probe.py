#!/usr/bin/env python3
"""probe.py — the one script that really talks to a model account. Opt-in.

Nothing else in this box makes a network call. This does, and only when you
run it and only against the account **you** name:

    export MODEL_ENDPOINT=https://<your-account>.openai.azure.com/
    export MODEL_DEPLOYMENT=<your-chat-deployment>
    export MODEL_EMBEDDING_DEPLOYMENT=<your-embedding-deployment>   # optional
    python3 scripts/probe.py --confirm-live

Without ``--confirm-live`` it prints the coordinates it would use and exits 0
without opening a socket, so it is safe to run in CI by accident.

It spends tokens. Keep ``--max-output-tokens`` small; the default is 32.
Identity comes from the ambient credential — a managed identity on Azure
compute, a developer sign-in locally. There is no key path.

Exit codes: 0 success or dry run, 1 the call failed, 2 bad usage.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import ModelConfig, ModelError, connect, embedding_config


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="probe.py",
        description="Send one small prompt (and optionally one embedding) to the "
        "account named by the environment, using Entra identity.",
    )
    parser.add_argument(
        "--confirm-live",
        action="store_true",
        help="actually call the service; without it this is a dry run",
    )
    parser.add_argument("--prompt", default="Reply with the single word: ready.")
    parser.add_argument("--max-output-tokens", type=int, default=32)
    parser.add_argument(
        "--embed",
        action="store_true",
        help="also embed one short string, using the configured embedding deployment",
    )
    args = parser.parse_args(argv)

    try:
        config = ModelConfig.from_env().with_overrides(
            default_max_output_tokens=args.max_output_tokens
        )
    except ModelError as refused:
        print(f"configuration refused: {refused}", file=sys.stderr)
        return 2

    print(f"account host : {config.account_host}")
    print(f"base url     : {config.base_url}")
    print(f"deployment   : {config.deployment}")
    print(f"embeddings   : {config.embedding_deployment or '(not configured)'}")
    print(f"scope        : {config.credential_scope}")
    print(f"timeout/retry: {config.timeout_secs}s / {config.max_retries}")

    if not args.confirm_live:
        print("\ndry run: pass --confirm-live to spend tokens against this account")
        return 0

    try:
        with connect(config) as model:
            answer = model.ask(args.prompt)
            print(f"\nresult metadata: {answer.metadata()}")
            print(f"text: {answer.text!r}")

            if args.embed:
                with connect(embedding_config(config)) as embedder:
                    vector = embedder.embed("probe").vector
                    print(f"embedding dimensions: {len(vector)}")
    except ModelError as failed:
        # Everything an operator can act on, and nothing the model produced.
        print(f"\ncall failed: {failed}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
