from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import MAX_SIGNED_BODY_BYTES, RequestSigner, SigningError, load_private_key


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SigningError("invalid_arguments")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(prog="python -m signed_dev_access")
    commands = parser.add_subparsers(dest="command", required=True)
    request = commands.add_parser("request", help="Send one explicitly authorized signed request; output metadata only")
    request.add_argument("method")
    request.add_argument("path")
    request.add_argument("--origin", required=True)
    request.add_argument("--key-file", required=True)
    request.add_argument("--context", default="")
    request.add_argument("--send", action="store_true")
    request.add_argument("--allow-mutation", action="store_true")
    request.add_argument("--allow-loopback-http", action="store_true")
    request.add_argument("--content-type", default="application/octet-stream")
    request.add_argument("--timeout", type=float, default=30)
    request.add_argument("--max-response-bytes", type=int, default=1_048_576)
    body = request.add_mutually_exclusive_group()
    body.add_argument("--body-file")
    body.add_argument("--body-stdin", action="store_true")
    try:
        args = parser.parse_args(argv)
        if not args.send:
            print(json.dumps({"sent": False}, sort_keys=True))
            return 0
        payload = b""
        if args.body_file:
            location = Path(args.body_file)
            if location.samefile(args.key_file):
                raise SigningError("key_as_body_refused")
            if not location.is_file():
                raise SigningError("invalid_body_file")
            with location.open("rb") as stream:
                payload = stream.read(MAX_SIGNED_BODY_BYTES + 1)
        elif args.body_stdin:
            payload = sys.stdin.buffer.read(MAX_SIGNED_BODY_BYTES + 1)
        if len(payload) > MAX_SIGNED_BODY_BYTES:
            raise SigningError("invalid_body")
        signer = RequestSigner(
            load_private_key(args.key_file),
            origin=args.origin,
            context_slug=args.context,
            allow_mutations=args.allow_mutation,
            allow_loopback_http=args.allow_loopback_http,
        )
        result = signer.request(
            args.method, args.path, payload,
            content_type=args.content_type,
            timeout_seconds=args.timeout,
            max_response_bytes=args.max_response_bytes,
        )
        print(json.dumps(result.metadata(), sort_keys=True))
        return 0 if 200 <= result.status < 300 else 1
    except SigningError as error:
        print(json.dumps({"ok": False, "code": error.code}, sort_keys=True))
        return 2
    except Exception:
        print(json.dumps({"ok": False, "code": "request_failed"}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())