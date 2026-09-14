#!/usr/bin/env python3
"""Exercise the documented fetch example with offline HTTP responses."""

from __future__ import annotations

import io
import json
import os
import urllib.error
from pathlib import Path
from unittest.mock import patch


def main() -> None:
    document = Path(__file__).resolve().parents[1] / "SKILL.md"
    snippet = document.read_text(encoding="utf-8").split("```python\n", 1)[1].split("```", 1)[0]
    namespace: dict = {}
    exec(compile(snippet, str(document), "exec"), namespace)
    environment = {
        "IDENTITY_ENDPOINT": "https://identity.invalid/token",
        "IDENTITY_HEADER": "offline-fixture",
        "AZURE_CLIENT_ID": "offline-client",
    }
    payload = json.dumps({"access_token": "offline-fixture", "expires_on": 3600}).encode()
    with patch.dict(os.environ, environment, clear=True), patch("time.time", return_value=1000):
        with patch("urllib.request.urlopen", side_effect=lambda *args, **kwargs: io.BytesIO(payload)) as transport:
            assert namespace["_token"]() == "offline-fixture"
            assert namespace["_token"]() == "offline-fixture"
            assert transport.call_count == 1, "unexpired token should be cached"
            request = transport.call_args.args[0]
            assert request.get_header("X-identity-header") == "offline-fixture"
            assert "client_id=offline-client" in request.full_url
            namespace["_tok"]["exp"] = 1050
            assert namespace["_token"]() == "offline-fixture"
            assert transport.call_count == 2, "near-expiry token should refresh"

    namespace["_token"] = lambda: "offline-fixture"
    response = io.BytesIO(b"updated content")
    response.headers = {"ETag": '"new"'}
    with patch("urllib.request.urlopen", return_value=response) as transport:
        assert namespace["fetch"]("https://content.invalid/page", '"old"') == (b"updated content", '"new"')
        request = transport.call_args.args[0]
        assert request.get_header("If-none-match") == '"old"'
        assert request.get_header("Authorization") == "Bearer offline-fixture"

    unchanged = urllib.error.HTTPError("https://content.invalid/page", 304, "Not Modified", {}, None)
    with patch("urllib.request.urlopen", side_effect=unchanged):
        assert namespace["fetch"]("https://content.invalid/page", '"old"') == (None, '"old"')

    refused = urllib.error.HTTPError("https://content.invalid/page", 403, "Forbidden", {}, None)
    with patch("urllib.request.urlopen", side_effect=refused):
        try:
            namespace["fetch"]("https://content.invalid/page")
        except urllib.error.HTTPError as error:
            assert error.code == 403
        else:
            raise AssertionError("403 must not become cached content")
    print("content-from-a-store selftest: PASS")


if __name__ == "__main__":
    main()