"""Command line: the same six verbs, plus the offline ones that answer
questions without a cloud account.

OFFLINE BY DEFAULT
------------------
Nothing here contacts Azure unless ``--live`` is passed. Without it, verbs that
need an estate exit 1 and print the exact command that would work, rather than
silently reaching for whatever credential happens to be lying around.

CONFIRMATION IS A REVIEWED PLAN, NOT A FLAG
-------------------------------------------
``apply`` used to take ``--confirm`` and then run
``manager.apply(plan, confirmations=manager.confirm(plan))`` — minting and
consuming a token for every step, including ``administrative`` ones, inside one
expression. That is a boolean pretending to be a target-bound authorisation,
and it made the whole confirmation ledger decorative at the only entry point
operators actually use.

The lifecycle now is three commands and two artefacts:

1. ``azaccess plan … --save-plan plan.json`` writes the plan and prints its
   ``digest`` — a SHA-256 over the steps, stable across runs because it
   excludes the per-run ``plan_id``;
2. a human reads ``plan.json``;
3. ``azaccess apply … --expect-digest <digest> --confirm-target <fingerprint>``
   re-plans, refuses unless the freshly computed digest is the one that was
   reviewed, and mints a token only for the fingerprints named on the command
   line. A step that needs confirmation and was not named is refused, and a
   fingerprint that is not in the plan is refused.

EXIT CODES
----------
``0`` the answer is yes / the operation succeeded and verified.
``1`` refused, failed, or verified as not-present. A refusal is a normal
      outcome of a safety gate, so it is an exit code and not a traceback.
``2`` bad usage — argparse's own code, kept because operators script against it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence

from azaccess.authorization import AuthorityPolicy, bounded_policy
from azaccess.engine import AccessManager
from azaccess.errors import AccessError, AuthorizationRefused
from azaccess.identity import IdentityRef
from azaccess.ledger import OwnershipLedger
from azaccess.matrix import LIVE_VERIFICATION, counts, render_matrix
from azaccess.model import Plan, declarations_from_records
from azaccess.roles import BUILTIN_ROLES, TIERS
from azaccess.scopes import Scope

PROG = "azaccess"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Inspect, plan, diff, apply, verify and revoke Azure access "
                    "across the five assignment planes. Read-only and offline "
                    "unless --live is given.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser(
        "matrix", help="print the support matrix, derived from the adapters"
    ).add_argument("--json", action="store_true", help="machine-readable output")

    roles = subparsers.add_parser("roles", help="print the role catalogue")
    roles.add_argument("--tier", choices=TIERS, help="only roles at this tier")
    roles.add_argument("--plane", help="only roles on this assignment plane")

    scope = subparsers.add_parser(
        "scope", help="parse an ARM scope and show its derivable ancestors")
    scope.add_argument("arm_id")

    ledger = subparsers.add_parser(
        "ledger",
        help="read an ownership ledger a previous run wrote, and print the "
             "manual cleanup for anything outstanding")
    ledger.add_argument("--ownership-ledger", required=True,
                        help="directory a previous run wrote records into")
    ledger.add_argument("--json", action="store_true")

    for name, help_text in (
        ("inspect", "exact and inherited assignments for one principal"),
        ("plan", "what would change to reach the declared state"),
        ("diff", "declared versus observed, inherited access kept separate"),
        ("apply", "execute a reviewed plan (needs --live and --expect-digest)"),
        ("verify", "read the declared state back at exact scope"),
        ("revoke", "delete assignments this run owns"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--declarations", help="JSON file of declarations")
        sub.add_argument("--principal", help="principal object id")
        sub.add_argument("--principal-kind", default="managed-identity")
        sub.add_argument("--tenant", help="tenant id (required for any mutation)")
        sub.add_argument("--subscription", help="subscription id for role definition ids")
        sub.add_argument("--scope", action="append", default=[],
                         help="allowlisted scope; repeatable. Bounds reads too")
        sub.add_argument("--max-tier", choices=TIERS, default="read")
        sub.add_argument("--write", action="store_true",
                         help="authorise mutations; without it the policy is "
                              "read-only and every create is refused")
        sub.add_argument("--authorize-role", action="append", default=[],
                         help="permit this exact role above --max-tier; repeatable")
        sub.add_argument("--save-plan", help="plan: write the plan JSON here for review")
        sub.add_argument("--expect-digest",
                         help="apply: the digest printed by the plan you reviewed. "
                              "apply refuses if the freshly computed plan differs")
        sub.add_argument("--confirm-target", action="append", default=[],
                         help="apply: the fingerprint of one step you are "
                              "confirming; repeatable, and every step needing "
                              "confirmation must be named")
        sub.add_argument("--ownership-ledger",
                         help="directory to record created assignments in, so a "
                              "crash leaves a recoverable trail")
        sub.add_argument("--authorized-id", action="append", default=[],
                         help="revoke: an assignment id this run did not create "
                              "but you explicitly authorise deleting; repeatable")
        sub.add_argument("--live", action="store_true",
                         help="contact Azure using the signed-in Azure CLI identity")
        sub.add_argument("--json", action="store_true")
    return parser


def _print(payload: Any, as_json: bool = True) -> None:
    del as_json  # output is JSON on every verb; the flag exists for scripts
    print(json.dumps(payload, indent=2, sort_keys=True))


def _offline_refusal(command: str) -> int:
    print(
        f"{command} needs to read live state and --live was not given.\n"
        f"\n"
        f"  Offline, you can still run:\n"
        f"    {PROG} matrix          # what this skill supports, and on which plane\n"
        f"    {PROG} roles --tier read\n"
        f"    {PROG} scope /subscriptions/<sub-id>/resourceGroups/<name>\n"
        f"\n"
        f"  To run it for real, sign in first and re-run with --live:\n"
        f"    az login --tenant <tenant-id>\n"
        f"    {PROG} {command} --live --tenant <tenant-id> --subscription <sub-id> \\\n"
        f"        --scope /subscriptions/<sub-id>/resourceGroups/<name> \\\n"
        f"        --declarations declarations.json\n",
        file=sys.stderr,
    )
    return 1


def _policy(args: argparse.Namespace) -> AuthorityPolicy:
    if not args.tenant:
        raise AccessError("--tenant is required: the allowlist is per tenant")
    if not args.scope:
        raise AccessError("--scope is required at least once: the allowlist is "
                          "fixed at start-up and never taken from the request")
    policy = bounded_policy(
        tenant_id=args.tenant, scopes=args.scope, max_tier=args.max_tier
    )
    if getattr(args, "write", False) or getattr(args, "authorize_role", []):
        # Widening is one visible call, made because a flag was typed.
        policy = policy.with_authorized(
            roles=getattr(args, "authorize_role", []),
            read_only=not getattr(args, "write", False),
        )
    return policy


def _live_manager(args: argparse.Namespace) -> AccessManager:
    from azaccess.providers.arm import ArmRbacProvider
    from azaccess.providers.cosmos import CosmosSqlRbacProvider
    from azaccess.providers.kusto import KustoDatabaseProvider

    if not args.subscription:
        raise AccessError("--subscription is required for ARM role definition ids")
    transport = _live_transport(args)
    ownership_ledger = (
        OwnershipLedger(Path(args.ownership_ledger))
        if getattr(args, "ownership_ledger", None) else None
    )
    return AccessManager(
        {
            "azure-rbac": ArmRbacProvider(transport, subscription_id=args.subscription),
            "cosmos-sql-rbac": CosmosSqlRbacProvider(transport),
            "kusto-database": KustoDatabaseProvider(transport),
        },
        policy=_policy(args),
        ownership_ledger=ownership_ledger,
    )


def _live_transport(args: argparse.Namespace) -> Any:
    """The CLI backend for reads; a real-status backend for mutations.

    ``az rest`` prints a body and no status line, so it cannot distinguish
    201 from 202 or a 409 that should be adopted. Reads do not need that
    distinction and mutations cannot be made safely without it, so ``apply``
    and ``revoke`` require a credential-backed transport instead.
    """
    from azaccess.transport import AzureCliTransport, TokenCredentialTransport

    if args.command not in ("apply", "revoke"):
        return AzureCliTransport()
    try:
        from azure.identity import DefaultAzureCredential  # type: ignore import-not-found
    except ImportError as exc:
        raise AccessError(
            "apply and revoke need a transport that reports real HTTP statuses, "
            "because 201 Created, 202 Accepted and 409 RoleAssignmentExists are "
            "three different outcomes and 'az rest' reports none of them. "
            "Install azure-identity (pip install azure-identity) so "
            "DefaultAzureCredential can be used, or drive AccessManager "
            "directly with your own TokenCredentialTransport"
        ) from exc
    return TokenCredentialTransport(DefaultAzureCredential)


def _declarations(args: argparse.Namespace) -> tuple[Any, ...]:
    if not args.declarations:
        raise AccessError("--declarations is required for this command")
    if not args.principal:
        raise AccessError("--principal is required: the object id to grant to")
    with open(args.declarations, "r", encoding="utf-8") as handle:
        records = json.load(handle)
    principal = IdentityRef(
        object_id=args.principal, kind=args.principal_kind,
        tenant_id=args.tenant or "",
    )
    return declarations_from_records(records, principal)


def _confirmations(manager: AccessManager, plan: Plan,
                   args: argparse.Namespace) -> dict[str, str]:
    """Tokens for exactly the targets the operator named, or a refusal.

    Three separate checks, and none of them is a boolean:

    * the plan just computed must have the digest that was reviewed;
    * every step that needs confirmation must be named by ``--confirm-target``;
    * nothing may be named that the plan does not contain.
    """
    required = sorted(
        step.declaration.fingerprint()
        for step in plan.mutating
        if step.requires_confirmation
    )
    named = sorted({str(f) for f in args.confirm_target})
    if not args.expect_digest:
        raise AuthorizationRefused(
            "apply needs --expect-digest: run `plan --save-plan plan.json`, read "
            "the plan, then pass the digest it printed.\n"
            f"  this plan's digest: {plan.digest()}\n"
            + (f"  targets needing confirmation: {required}" if required else "")
        )
    if plan.digest() != args.expect_digest:
        raise AuthorizationRefused(
            f"the plan computed now does not match the plan you reviewed. "
            f"reviewed {args.expect_digest[:16]}…, computed {plan.digest()[:16]}…; "
            f"state changed under it — re-plan and re-read before applying"
        )
    if named != required:
        raise AuthorizationRefused(
            f"confirmation targets do not match the plan: needs {required}, "
            f"named {named}. Name each one with --confirm-target"
        )
    return manager.confirm(plan, fingerprints=named)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command

    if command == "matrix":
        if args.json:
            from azaccess.matrix import support_matrix

            _print(
                {
                    "rows": [r.to_dict() for r in support_matrix()],
                    "counts": counts(),
                    "live_verification": LIVE_VERIFICATION,
                },
                True,
            )
        else:
            print(render_matrix())
            print()
            print(json.dumps(counts(), sort_keys=True))
        return 0

    if command == "roles":
        rows = [
            {"name": r.name, "tier": r.tier, "plane": r.plane, "id": r.definition_id,
             "note": r.note}
            for r in sorted(BUILTIN_ROLES.values(), key=lambda r: (r.plane, r.name))
            if (not args.tier or r.tier == args.tier)
            and (not args.plane or r.plane == args.plane)
        ]
        _print(rows, True)
        return 0

    if command == "scope":
        try:
            parsed = Scope.parse(args.arm_id)
        except AccessError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        _print(
            {
                **parsed.describe(),
                "ancestors": [a.value for a in parsed.ancestors()],
                "note": "management-group ancestry is not derivable from an ARM id",
            },
            True,
        )
        return 0

    if command == "ledger":
        try:
            _print(OwnershipLedger(Path(args.ownership_ledger)).cleanup_report(), True)
        except (AccessError, OSError) as exc:
            print(f"ledger: {exc}", file=sys.stderr)
            return 1
        return 0

    if not args.live:
        return _offline_refusal(command)

    try:
        if command == "apply":
            # Checked before any transport or credential is constructed: a
            # missing authorisation is decidable here and costs nothing.
            if not args.expect_digest:
                raise AuthorizationRefused(
                    "apply needs --expect-digest: run `plan --save-plan "
                    "plan.json`, read the plan, then pass the digest it "
                    "printed. A flag saying 'yes' is not a target-bound "
                    "authorisation"
                )
        manager = _live_manager(args)
        if command == "inspect":
            if not args.principal or not args.scope:
                raise AccessError("--principal and --scope are required")
            _print(manager.inspect(args.principal, args.scope[0]).to_dict(), True)
            return 0
        declarations = _declarations(args)
        if command == "plan":
            plan = manager.plan(declarations)
            payload = plan.to_dict()
            if args.save_plan:
                with open(args.save_plan, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2, sort_keys=True)
            _print(payload, True)
            return 0
        if command == "diff":
            report = manager.diff(declarations)
            _print(report.to_dict(), True)
            return 0 if not report.missing else 1
        if command == "verify":
            results = manager.verify(declarations)
            _print([r.to_dict() for r in results], True)
            return 0 if all(r.status == "present" for r in results) else 1
        if command == "apply":
            plan = manager.plan(declarations)
            tokens = _confirmations(manager, plan, args)
            report = manager.apply(plan, confirmations=tokens)
            _print(report.to_dict(), True)
            return 0 if report.ok else 1
        if command == "revoke":
            report = manager.revoke(declarations,
                                    authorized_ids=args.authorized_id)
            _print(report.to_dict(), True)
            return 0 if report.ok else 1
    except AccessError as exc:
        print(f"{exc.category}: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"io: {exc}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
