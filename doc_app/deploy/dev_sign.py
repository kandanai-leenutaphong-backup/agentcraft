#!/usr/bin/env python3
"""Sign requests to the deployed writeup with an Ed25519 key.

Wire shape matches gridiq AUTODEV section 4.2, so the same canonical string
verifies on the server:

    X-Request-Timestamp   RFC 3339 UTC, rejected beyond 5 minutes of skew
    X-Request-Signature   base64(Ed25519.sign(METHOD\\npath?query\\nts\\nslug\\nsha256_hex(body)))
    X-Request-Context     optional slug, may be stripped by ingress

The private key stays on this machine at ~/.writeup/dev_signing_key (0600).
Only the public verifier is ever sent to Azure.

    python3 deploy/dev_sign.py init
    python3 deploy/dev_sign.py request GET /
    python3 deploy/dev_sign.py sign GET /index.html
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import os
import stat
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

KEY_PATH = Path.home() / ".writeup" / "dev_signing_key"


def _load_key() -> Ed25519PrivateKey:
    if not KEY_PATH.exists():
        sys.exit(f"no signing key at {KEY_PATH} — run: dev_sign.py init")
    mode = stat.S_IMODE(KEY_PATH.stat().st_mode)
    if mode & 0o077:
        sys.exit(f"refusing to read {KEY_PATH}: mode {mode:o} is too broad, want 0600")
    return serialization.load_pem_private_key(KEY_PATH.read_bytes(), password=None)


def cmd_init(args: argparse.Namespace) -> int:
    if KEY_PATH.exists() and not args.force:
        key = _load_key()
    else:
        KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        key = Ed25519PrivateKey.generate()
        KEY_PATH.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        KEY_PATH.chmod(0o600)
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    print(f"DEV_PUBLIC_KEY_ED25519={base64.b64encode(pub).decode()}")
    return 0


def _headers(method: str, path: str, body: bytes, slug: str) -> dict[str, str]:
    key = _load_key()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    canonical = "\n".join(
        [method.upper(), path, ts, slug, hashlib.sha256(body).hexdigest()]
    ).encode()
    sig = base64.b64encode(key.sign(canonical)).decode()
    headers = {"X-Request-Timestamp": ts, "X-Request-Signature": sig}
    if slug:
        headers["X-Request-Context"] = slug
    return headers


def cmd_sign(args: argparse.Namespace) -> int:
    body = sys.stdin.buffer.read() if not sys.stdin.isatty() else b""
    for header, value in _headers(args.method, args.path, body, args.context).items():
        print(f"{header}: {value}")
    return 0


def cmd_request(args: argparse.Namespace) -> int:
    base = args.url or os.environ.get("APP_URL", "")
    if not base:
        sys.exit("no target: pass --url or set APP_URL")
    body = sys.stdin.buffer.read() if not sys.stdin.isatty() else b""
    headers = _headers(args.method, args.path, body, args.context)

    req = urllib.request.Request(
        base.rstrip("/") + args.path,
        data=body or None,
        headers=headers,
        method=args.method.upper(),
    )
    try:
        with urllib.request.urlopen(req) as resp:
            payload = resp.read()
            print(f"HTTP {resp.status} {len(payload)} bytes", file=sys.stderr)
            sys.stdout.buffer.write(payload if args.show_body else b"")
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}", file=sys.stderr)
        return 1
    return 0


def cmd_session(args: argparse.Namespace) -> int:
    """Mint a browser cookie so a real browser session can be driven."""
    key = _load_key()
    expiry = datetime.now(timezone.utc) + timedelta(minutes=args.minutes)
    stamp = expiry.strftime("%Y-%m-%dT%H:%M:%SZ")
    sig = key.sign(f"SESSION\n{stamp}".encode())
    value = (
        base64.urlsafe_b64encode(stamp.encode()).decode()
        + "."
        + base64.urlsafe_b64encode(sig).decode()
    )
    print(value)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create or print the signing key")
    p_init.add_argument("--force", action="store_true", help="regenerate the key")
    p_init.set_defaults(func=cmd_init)

    p_session = sub.add_parser("session", help="mint a signed browser cookie")
    p_session.add_argument("--minutes", type=int, default=60)
    p_session.set_defaults(func=cmd_session)

    for name, func in (("sign", cmd_sign), ("request", cmd_request)):
        p = sub.add_parser(name)
        p.add_argument("method")
        p.add_argument("path")
        p.add_argument("--context", default="", help="optional identity slug")
        if name == "request":
            p.add_argument("--url", default="", help="base URL, or set APP_URL")
            p.add_argument("--show-body", action="store_true")
        p.set_defaults(func=func)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
