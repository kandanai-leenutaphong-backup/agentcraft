"""Round-trip proof: the shipped CLI signs what the shipped verifier accepts.

The two halves of this box are written independently and must agree on the
canonical string byte for byte. Everything else can be correct and the box
still useless if they drift, so this asserts the contract directly rather
than testing either half in isolation.

Run: ``python3 tests/test_roundtrip.py`` or under pytest.
"""

from __future__ import annotations

import base64
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from devauth import verify

_CLI = _ROOT / "scripts" / "dev_sign.py"


def _run(args: list[str], key_dir: Path) -> str:
    """Invoke the CLI as a real subprocess, as an operator would."""
    result = subprocess.run(
        [sys.executable, "-B", str(_CLI), *args],
        capture_output=True, text=True, check=True,
        env={"PATH": "/usr/bin:/bin", "HOME": str(key_dir),
             "DEVAUTH_KEY_DIR": str(key_dir)},
    )
    return result.stdout


def _parse_headers(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if ":" in line and not line.startswith("#"):
            name, _, value = line.partition(":")
            out[name.strip().lower()] = value.strip()
    return out


def test_cli_signature_verifies_server_side():
    with tempfile.TemporaryDirectory() as tmp:
        key_dir = Path(tmp)

        init_out = _run(["init"], key_dir)
        pub = init_out.split("DEV_PUBLIC_KEY_ED25519=")[1].strip()
        assert len(base64.b64decode(pub)) == 32

        for method, path in [
            ("GET", "/api/sessions"),
            ("GET", "/api/sessions?limit=10&order=desc"),
            ("GET", "/api/topology/A%0AB"),          # G1: encoded path
            ("DELETE", "/api/sessions/abc-123"),
        ]:
            headers = _parse_headers(_run(["sign", method, path], key_dir))
            result = verify(
                public_key_b64=pub,
                method=method,
                path_and_query=path,
                ts=headers["x-request-timestamp"],
                sig_b64=headers["x-request-signature"],
                body=b"",
            )
            assert result.ok is True, f"{method} {path} failed to verify"


def test_cli_signature_does_not_verify_under_a_different_key():
    with tempfile.TemporaryDirectory() as tmp_a, \
            tempfile.TemporaryDirectory() as tmp_b:
        _run(["init"], Path(tmp_a))
        other_pub = _run(["init"], Path(tmp_b)).split(
            "DEV_PUBLIC_KEY_ED25519=")[1].strip()

        headers = _parse_headers(_run(["sign", "GET", "/a"], Path(tmp_a)))
        assert verify(public_key_b64=other_pub, method="GET",
                      path_and_query="/a",
                      ts=headers["x-request-timestamp"],
                      sig_b64=headers["x-request-signature"],
                      body=b"").ok is False


def test_private_key_is_owner_only():
    with tempfile.TemporaryDirectory() as tmp:
        key_dir = Path(tmp)
        _run(["init"], key_dir)
        key_file = key_dir / "dev_signing_key"
        assert key_file.exists()
        assert oct(key_file.stat().st_mode)[-3:] == "600"


def test_init_refuses_to_clobber_existing_key():
    """Silent key replacement would revoke every deployed public key."""
    with tempfile.TemporaryDirectory() as tmp:
        key_dir = Path(tmp)
        first = _run(["init"], key_dir)
        result = subprocess.run(
            [sys.executable, "-B", str(_CLI), "init"], capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(key_dir),
                 "DEVAUTH_KEY_DIR": str(key_dir)},
        )
        assert result.returncode != 0
        assert _run(["pubkey"], key_dir).strip() in first


def test_sign_headers_helper_verifies_server_side():
    """The helper browser piloting depends on must produce valid signatures.

    A piloted browser signs each intercepted request in-process rather than
    shelling out, so this path needs its own proof.
    """
    snippet = (
        "import sys, json; sys.path.insert(0, %r)\n"
        "from dev_sign import sign_headers\n"
        "print(json.dumps(sign_headers('POST', '/api/chat?x=1',"
        " b'{\"a\":1}', 'alice')))\n" % str(_CLI.parent)
    )
    with tempfile.TemporaryDirectory() as tmp:
        key_dir = Path(tmp)
        pub = _run(["init"], key_dir).split(
            "DEV_PUBLIC_KEY_ED25519=")[1].strip()

        proc = subprocess.run(
            [sys.executable, "-B", "-c", snippet], capture_output=True, text=True,
            check=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(key_dir),
                 "DEVAUTH_KEY_DIR": str(key_dir)},
        )
        import json
        headers = {k.lower(): v for k, v in json.loads(proc.stdout).items()}

        assert headers["x-request-context"] == "alice"
        result = verify(
            public_key_b64=pub,
            method="POST",
            path_and_query="/api/chat?x=1",
            ts=headers["x-request-timestamp"],
            sig_b64=headers["x-request-signature"],
            body=b'{"a":1}',
            user_slug=headers["x-request-context"],
        )
        assert result.ok is True and result.user_slug == "alice"


def test_browser_pilot_path_extraction():
    """G1: the signed path must be the raw wire path, not a normalised one."""
    sys.path.insert(0, str(_ROOT / "examples"))
    from browser_pilot import _path_and_query

    assert _path_and_query("https://h.example/api/x") == "/api/x"
    assert _path_and_query("https://h.example/api/x?a=1&b=2") == "/api/x?a=1&b=2"
    assert _path_and_query("https://h.example/api/a%0Ab") == "/api/a%0Ab"


def test_signatures_differ_for_concurrent_identical_requests():
    """G12: identical requests must not collide into a false replay."""
    snippet = (
        "import sys, json; sys.path.insert(0, %r)\n"
        "from dev_sign import sign_headers\n"
        "print(json.dumps([sign_headers('GET', '/api/x')"
        "['X-Request-Signature'] for _ in range(5)]))\n" % str(_CLI.parent)
    )
    with tempfile.TemporaryDirectory() as tmp:
        key_dir = Path(tmp)
        _run(["init"], key_dir)
        proc = subprocess.run(
            [sys.executable, "-B", "-c", snippet], capture_output=True, text=True,
            check=True,
            env={"PATH": "/usr/bin:/bin", "HOME": str(key_dir),
                 "DEVAUTH_KEY_DIR": str(key_dir)},
        )
        import json
        sigs = json.loads(proc.stdout)
        assert len(set(sigs)) == len(sigs), "identical signatures would 401"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok   {name}")
            except Exception as exc:  # noqa: BLE001 - selftest reporting
                print(f"  FAIL {name}: {exc}")
                failures += 1
    print("all checks passed" if not failures else f"FAILED: {failures}")
    raise SystemExit(1 if failures else 0)
