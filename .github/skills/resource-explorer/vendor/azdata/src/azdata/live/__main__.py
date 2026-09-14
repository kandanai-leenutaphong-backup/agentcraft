"""``python -m azdata.live`` — up, status, pause, resume, down.

Progress goes to stderr and the answer goes to stdout, so ``status`` can
be piped into ``jq`` while a human still watches the steps go by.

``down`` needs ``--yes`` *and* an ownership tag on the resource group.
Neither alone is enough: the flag stops a mistyped subcommand, the tag
stops a correctly typed one aimed at somebody else's group.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from azdata.core.credentials import default_credential_provider
from azdata.core.optional import MissingDependency
from azdata.live.environment import (
    LOCATION,
    RESOURCE_GROUP,
    STATE_PATH,
    Environment,
    LiveEnvironmentError,
)


def _subscription(value: str) -> str:
    """An empty ``--subscription`` is a missing one, not a blank target."""
    target = value.strip()
    if not target:
        raise argparse.ArgumentTypeError(
            "--subscription must name a subscription"
        )
    return target


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m azdata.live",
        description=(
            "Create, inspect and tear down the live conformance environment "
            "in an explicitly named subscription."
        ),
    )
    parser.add_argument(
        "command", choices=("up", "status", "pause", "resume", "down")
    )
    parser.add_argument("--subscription", required=True, type=_subscription)
    parser.add_argument("--resource-group", default=RESOURCE_GROUP)
    parser.add_argument("--location", default=LOCATION)
    parser.add_argument("--state", default=str(STATE_PATH))
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="create the resources but skip the 40-record seed dataset",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required by 'down': confirm deleting the whole resource group",
    )
    return parser


async def run(args: argparse.Namespace) -> int:
    environment = Environment(
        # default_credential_provider() returns the credential itself and
        # caches it; Environment wants a callable it can invoke per client.
        credential_provider=default_credential_provider,
        subscription_id=args.subscription,
        resource_group=args.resource_group,
        location=args.location,
        state_path=Path(args.state),
    )
    try:
        if args.command == "up":
            answer = await environment.up(seed=not args.no_seed)
        elif args.command == "status":
            answer = await environment.status()
        elif args.command == "pause":
            answer = await environment.pause()
        elif args.command == "resume":
            answer = await environment.resume()
        else:
            answer = await environment.down(confirm=args.yes)
    except (LiveEnvironmentError, MissingDependency) as exc:
        # Operator language, not a stack trace: every one of these carries
        # the step that failed, or the distribution to install, and what
        # to do about it.
        print(json.dumps({"error": True, "detail": str(exc)}, indent=2))
        return 1
    print(json.dumps(answer, indent=2, sort_keys=True, default=str))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
