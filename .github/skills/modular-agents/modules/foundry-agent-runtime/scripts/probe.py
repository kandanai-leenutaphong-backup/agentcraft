#!/usr/bin/env python3
"""probe — is this box actually able to reach Foundry from here?

Answers the question a stack trace at 2am does not: which of the four things
between the process and the model is broken — config, SDK, identity, or the
endpoint itself. Each stage is checked in the order that failures cascade, and
the first failure stops the run, because a token failure makes every later
result meaningless.

    python3 scripts/probe.py                    # config, SDK, token
    python3 scripts/probe.py --build            # also construct an agent
    python3 scripts/probe.py --run "ping"       # also take one turn

Exit codes: 0 all requested stages passed, 1 a stage failed, 2 bad invocation.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import foundryagent as fa

# The audience the Foundry data plane expects. Overridable because sovereign and
# air-gapped clouds use a different one, and hardcoding it would make the box
# useless there.
DEFAULT_SCOPE = "https://ai.azure.com/.default"


def stage(label: str) -> None:
    print(f"\n[{label}]")


def ok(msg: str) -> None:
    print(f"  ok   {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL {msg}")


def probe_config(prefix: str) -> fa.FoundryConfig | None:
    """Stage 1 — is the configuration present and shaped like a project?"""
    stage("config")
    try:
        config = fa.FoundryConfig.from_env(prefix=prefix)
    except ValueError as exc:
        fail(str(exc))
        return None
    ok(f"loaded: {config.redacted()}")
    for problem in config.warnings():
        print(f"  warn {problem}")
    return config


def probe_sdk() -> bool:
    """Stage 2 — are the SDKs importable? Checked before any network call."""
    stage("sdk")
    passed = True
    for path in ("agent_framework", "agent_framework.azure", "azure.identity"):
        if fa.sdk_available(path):
            ok(f"{path} importable")
        else:
            fail(f"{path} not installed")
            passed = False
    return passed


def probe_token(scope: str) -> bool:
    """Stage 3 — can this identity mint a token for the Foundry audience?

    Separated from the endpoint call because the two fail for entirely different
    reasons: no token means the identity is wrong or unassigned, while a token
    that the endpoint rejects means the role assignment is missing.
    """
    stage("identity")
    try:
        credential = fa.get_credential()
    except Exception as exc:
        fail(f"could not build a credential: {exc}")
        return False
    ok(f"credential: {type(credential).__name__}")
    try:
        token = credential.get_token(scope)
    except Exception as exc:
        fail(f"token request for {scope} failed: {exc}")
        print("       On a workstation this usually means no CLI login. "
              "In cloud it means no workload identity is assigned.")
        return False
    # Never print the token. Length and expiry are enough to prove it is real.
    ok(f"token acquired for {scope} (expires_on={getattr(token, 'expires_on', '?')})")
    return True


def probe_build(config: fa.FoundryConfig) -> object | None:
    """Stage 4 — does a client and an agent actually construct?"""
    stage("build")
    try:
        pool = fa.ClientPool(fa.foundry_agent_client(config))
        client = pool.client_for("probe")
        ok(f"client: {type(client).__name__}")
    except Exception as exc:
        fail(f"client construction failed: {exc}")
        return None
    try:
        agent = fa.build_agent(
            {"name": "probe", "instructions": "Reply with one word.",
             "tools": [], "model": ""},
            client, config, agent_id="probe",
        )
    except Exception as exc:
        fail(f"agent build failed: {exc}")
        return None
    ok("agent built")
    return agent


def probe_run(agent: object, config: fa.FoundryConfig, message: str) -> bool:
    """Stage 5 — does the deployment answer? The only stage that spends money."""
    stage("run")

    async def turn(model: str):
        return await agent.run(message)  # type: ignore[attr-defined]

    try:
        result = asyncio.run(fa.run_with_fallback(turn, config, context="probe"))
    except Exception as exc:
        fail(f"{fa.classify(exc)}: {exc}")
        return False
    ok(f"answered: {str(result)[:200]}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prefix", default=fa.DEFAULT_ENV_PREFIX,
                        help="environment variable prefix")
    parser.add_argument("--scope", default=DEFAULT_SCOPE,
                        help="token audience to request")
    parser.add_argument("--build", action="store_true",
                        help="also construct a client and an agent")
    parser.add_argument("--run", metavar="MESSAGE", default="",
                        help="also take one turn against the deployment")
    args = parser.parse_args()

    config = probe_config(args.prefix)
    if config is None:
        return 1
    if not probe_sdk():
        return 1
    if not probe_token(args.scope):
        return 1

    if not (args.build or args.run):
        print("\nPASS: config, sdk and identity are healthy "
              "(add --build / --run to go further)")
        return 0

    agent = probe_build(config)
    if agent is None:
        return 1
    if args.run and not probe_run(agent, config, args.run):
        return 1

    print("\nPASS: every requested stage succeeded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
