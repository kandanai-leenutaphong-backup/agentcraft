#!/usr/bin/env python3
"""diagnose — explain a 401 without guessing.

Reads a token, decodes it **without verifying**, and reports every reason the
configured validator would reject it — audience, issuer, tenant, expiry, missing
claims, algorithm — rather than the first one. A real validation stops at the
first failure by design; a diagnosis should not, because the second failure is
usually the one you did not expect.

    python3 scripts/diagnose.py --token-file /tmp/token.txt
    az account get-access-token --resource api://<app-id> --query accessToken -o tsv \\
        | python3 scripts/diagnose.py
    python3 scripts/diagnose.py --check-discovery      # can we reach the keys?

The token is read from a file or from stdin, never from an argument. Command
lines are visible to every process on the host and are recorded in shell
history; an access token there is a credential in a world-readable place.

Exit codes: 0 the token would be accepted, 1 it would be rejected, 2 bad
invocation.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import entraauth as ea
from entraauth._config import GUID_PATTERN, ISSUER_PATTERN


def ok(msg: str) -> None:
    print(f"  ok   {msg}")


def bad(msg: str) -> None:
    print(f"  FAIL {msg}")


def info(msg: str) -> None:
    print(f"       {msg}")


def read_token(args: argparse.Namespace) -> str:
    """Read the token from a file or stdin. Never from the command line."""
    if args.token_file:
        return Path(args.token_file).read_text(encoding="utf-8").strip()
    if sys.stdin.isatty():
        print("Paste the token, then Ctrl-D:", file=sys.stderr)
    return sys.stdin.read().strip()


def decode_segment(segment: str) -> dict:
    """Base64url-decode one JWT segment without verifying anything."""
    padded = segment + "=" * (-len(segment) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def split_token(token: str) -> tuple[dict, dict]:
    """Return (header, claims) from an unverified token."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError(
            f"not a JWT — expected 3 dot-separated segments, found {len(parts)}"
        )
    return decode_segment(parts[0]), decode_segment(parts[1])


def diagnose(config: ea.AuthConfig, header: dict, claims: dict) -> list[str]:
    """Return every reason this token would be rejected. Empty means accepted."""
    problems: list[str] = []

    print("\n[token]")
    info(f"algorithm     {header.get('alg')}")
    info(f"key id        {header.get('kid')}")
    info(f"issuer        {claims.get('iss')}")
    info(f"audience      {claims.get('aud')}")
    info(f"tenant        {claims.get('tid')}")
    info(f"object id     {claims.get('oid') or '(absent)'}")
    info(f"subject       {claims.get('sub') or '(absent)'}")
    if claims.get("scp"):
        info(f"scopes        {claims.get('scp')}")
    if claims.get("roles"):
        info(f"roles         {claims.get('roles')}")

    print("\n[algorithm]")
    if header.get("alg") in ea.ALLOWED_ALGORITHMS:
        ok(f"{header.get('alg')} is accepted")
    else:
        bad(f"{header.get('alg')!r} is not in {ea.ALLOWED_ALGORITHMS}")
        problems.append("bad_algorithm")

    print("\n[audience]")
    audience = claims.get("aud")
    accepted = config.audiences()
    values = audience if isinstance(audience, list) else [audience]
    if any(value in accepted for value in values):
        ok(f"{audience!r} is accepted")
    else:
        bad(f"{audience!r} is not one of {accepted}")
        info("The token was issued for a different application. Request the "
             "scope of THIS API, not of the client (G5).")
        problems.append("bad_audience")

    print("\n[issuer]")
    issuer = str(claims.get("iss", ""))
    if config.multi_tenant:
        if ISSUER_PATTERN.match(issuer):
            ok("issuer has the Entra ID form, accepted in multi-tenant mode")
        else:
            bad(f"{issuer!r} is not an Entra ID issuer")
            problems.append("bad_issuer")
    elif issuer in config.expected_issuers():
        ok(f"{issuer!r} matches the configured tenant")
    else:
        bad(f"{issuer!r} is not one of {list(config.expected_issuers())}")
        token_tenant = GUID_PATTERN.search(issuer)
        if token_tenant and token_tenant.group() != config.tenant_id:
            info(f"The token is from tenant {token_tenant.group()}, this API "
                 f"trusts {config.tenant_id}.")
        problems.append("bad_issuer")

    print("\n[validity]")
    now = int(time.time())
    exp = claims.get("exp")
    nbf = claims.get("nbf")
    if not exp:
        bad("no 'exp' claim — a token with no expiry is rejected")
        problems.append("missing_claim")
    elif exp < now:
        bad(f"expired {now - exp}s ago")
        problems.append("expired")
    else:
        ok(f"valid for another {exp - now}s")
    if nbf and nbf > now + config.leeway_seconds:
        bad(f"not valid for another {nbf - now}s (leeway "
            f"{config.leeway_seconds}s)")
        problems.append("not_yet_valid")

    print("\n[required claims]")
    for name in config.required_claims:
        if claims.get(name):
            ok(f"{name!r} present")
        else:
            bad(f"{name!r} missing or empty")
            if name == "oid":
                info("Service principal tokens have no 'oid'. Configure "
                     "required_claims=('sub',) and handle them deliberately (G3).")
            problems.append("missing_claim")

    return problems


async def check_discovery(config: ea.AuthConfig) -> bool:
    """Confirm the signing keys are reachable from this host."""
    print("\n[discovery]")
    info(config.jwks_url())
    cache = ea.JWKSCache(config)
    try:
        document = await ea.default_fetcher(config.jwks_url())
    except Exception as exc:
        bad(f"unreachable: {exc}")
        info("Check egress, proxy configuration and DNS. Until this succeeds "
             "no token can be validated, and the correct response is 503 "
             "rather than 401.")
        return False
    count = len(document.get("keys", []))
    ok(f"reachable, {count} signing key(s) published")
    del cache
    return count > 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--token-file", help="file containing the token")
    parser.add_argument("--prefix", default=ea.DEFAULT_ENV_PREFIX,
                        help="environment variable prefix")
    parser.add_argument("--check-discovery", action="store_true",
                        help="also confirm the signing keys are reachable")
    args = parser.parse_args()

    print("[config]")
    try:
        config = ea.AuthConfig.from_env(prefix=args.prefix)
    except ValueError as exc:
        bad(str(exc))
        return 2
    ok(f"tenant={config.tenant_id or '(unset)'} "
       f"client_id={config.client_id or '(unset)'} enabled={config.enabled}")
    for problem in config.warnings():
        print(f"  warn {problem}")

    if not config.enabled:
        info("Auth is disabled — no token is inspected at all. Diagnosing "
             "against the configured tenant regardless.")

    reachable = True
    if args.check_discovery:
        reachable = asyncio.run(check_discovery(config))

    token = read_token(args)
    if not token:
        bad("no token supplied on stdin or via --token-file")
        return 2

    try:
        header, claims = split_token(token)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        print("\n[token]")
        bad(f"cannot decode: {exc}")
        return 1

    problems = diagnose(config, header, claims)

    print()
    if problems:
        print(f"REJECTED: {len(problems)} problem(s) — {', '.join(sorted(set(problems)))}")
        print("Note: the signature itself is NOT checked here. A token that "
              "clears every check above can still fail verification if it was "
              "not signed by this tenant's current keys.")
        return 1
    if not reachable:
        print("INCONCLUSIVE: the token's claims are all acceptable, but the "
              "signing keys could not be fetched.")
        return 1
    print("ACCEPTED: every claim check passes (signature not verified here)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
