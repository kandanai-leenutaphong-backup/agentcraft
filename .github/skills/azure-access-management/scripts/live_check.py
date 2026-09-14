#!/usr/bin/env python3
"""live_check.py — the one script here that talks to Azure, and only on demand.

Reads. Never writes. It exists because "the assignment is present" and "the
access works" are different claims and only a real call separates them.

It contacts Azure ONLY when every coordinate is passed explicitly and
``--live`` is given. With no arguments it prints this contract and exits 2, so
an agent that runs it speculatively touches nothing.

    python3 scripts/live_check.py --live \
        --tenant <tenant-id> --subscription <sub-id> \
        --principal <object-id> \
        --scope /subscriptions/<sub-id>/resourceGroups/<name>

Identity comes from the Azure CLI you are already signed in to
(``az login --tenant <tenant-id>``). No key, connection string or secret is
read, written or accepted by this script.

Prerequisites, exactly:

* the Azure CLI on ``PATH``, signed in. It is not a Python package and is not
  installed by ``pip install`` of this skill;
* Python 3.10 or newer, and no third-party package at all;
* **no installation of this skill is required.** The line below puts the skill
  folder on ``sys.path``, so the script runs straight out of a copied folder. If
  the package *has* been installed (``pip install <skill folder>``) that line is
  harmless and the installed copy is used only when the folder is not there.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Deliberate: this script is meant to run from an uninstalled copy of the
# folder. Nothing else in the package touches sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from azaccess import (  # noqa: E402
    AccessManager,
    ArmRbacProvider,
    AzureCliTransport,
    bounded_policy,
)
from azaccess.errors import AccessError  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="live_check.py",
        description="Read one principal's exact and inherited assignments at "
                    "one scope. Read-only, and inert without --live.",
    )
    parser.add_argument("--live", action="store_true",
                        help="required; without it nothing is contacted")
    parser.add_argument("--tenant", help="tenant id for the runtime allowlist")
    parser.add_argument("--subscription", help="subscription id")
    parser.add_argument("--principal", help="principal object id to report on")
    parser.add_argument("--scope", help="the exact scope to read")
    parser.add_argument("--deny", action="store_true",
                        help="also list deny assignments at that scope")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    required = ("live", "tenant", "subscription", "principal", "scope")
    missing = [f"--{name}" for name in required if not getattr(args, name)]
    if missing:
        print(
            "refusing to contact Azure: missing " + ", ".join(missing) + "\n\n"
            + (__doc__ or ""),
            file=sys.stderr,
        )
        return 2

    transport = AzureCliTransport()
    provider = ArmRbacProvider(transport, subscription_id=args.subscription)
    manager = AccessManager(
        {"azure-rbac": provider},
        policy=bounded_policy(tenant_id=args.tenant, scopes=[args.scope],
                              max_tier="read"),
    )
    try:
        effective = manager.inspect(args.principal, args.scope)
        payload = effective.to_dict()
        if args.deny:
            payload["deny_assignments"] = [
                state.to_dict() for state in provider.list_deny_assignments(args.scope)
            ]
    except AccessError as exc:
        print(f"{exc.category}: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, indent=2, sort_keys=True))
    # Exit 1 when nothing was found at all: a silent empty answer reads like
    # success in a pipeline.
    return 0 if (effective.exact or effective.inherited) else 1


if __name__ == "__main__":
    raise SystemExit(main())
