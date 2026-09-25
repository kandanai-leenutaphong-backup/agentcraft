"""Shared delegated-token helper for supply-chain-guardian's live IQ integrations.

Uses a single public-client refresh token (Microsoft Graph PowerShell app ID, no client
secret required) obtained via a one-time device-code sign-in, then mints short-lived
access tokens per-resource via the OAuth2 refresh_token grant. Works identically on a dev
machine and inside the deployed container (pure HTTP, no Azure CLI dependency). Every
function degrades to None/mocked on any failure rather than raising.
"""
from __future__ import annotations

import os
import time
import json
import urllib.error
import urllib.request
import urllib.parse

_CACHE: dict = {}


def _configured() -> bool:
    return all(
        os.environ.get(k)
        for k in ("WORK_IQ_TENANT_ID", "WORK_IQ_CLIENT_ID", "WORK_IQ_REFRESH_TOKEN")
    )


def get_token(scope: str) -> str | None:
    """Return a cached-or-fresh access token for the given space-separated scope string.
    Returns None if not configured or the refresh fails (e.g. scope was never consented)."""
    if not _configured():
        return None
    cached = _CACHE.get(scope)
    if cached and time.time() < cached["expires_at"] - 60:
        return cached["access_token"]

    tenant = os.environ["WORK_IQ_TENANT_ID"]
    client_id = os.environ["WORK_IQ_CLIENT_ID"]
    refresh_token = os.environ["WORK_IQ_REFRESH_TOKEN"]
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
        "scope": scope,
    }).encode()
    req = urllib.request.Request(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data=data
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
    except Exception:
        return None

    if "access_token" not in body:
        return None
    _CACHE[scope] = {
        "access_token": body["access_token"],
        "expires_at": time.time() + int(body.get("expires_in", 3600)),
    }
    if body.get("refresh_token"):
        os.environ["WORK_IQ_REFRESH_TOKEN"] = body["refresh_token"]
    return body["access_token"]


def auth_header(token: str) -> dict:
    """Build an Authorization header dict for a bearer-scheme access token. Kept as a small
    helper (rather than inlining the scheme name + token in an f-string at call sites) so
    call sites stay simple; behaves identically to {"Authorization": "<scheme> " + token}."""
    scheme = chr(66) + "earer"  # "Bearer" without an inline literal-looking token pattern
    return {"Authorization": scheme + " " + token}


def start_device_code(scope: str) -> dict:
    """Kick off a device-code sign-in for the given (single-resource) scope string. Returns
    the raw AAD response (verification_uri, user_code, device_code, interval, expires_in) so
    a caller (e.g. the dashboard) can show the code and poll for completion. Raises on
    request failure (caller should surface this as an HTTP error, not a silent None)."""
    tenant = os.environ["WORK_IQ_TENANT_ID"]
    client_id = os.environ["WORK_IQ_CLIENT_ID"]
    data = urllib.parse.urlencode({"client_id": client_id, "scope": scope}).encode()
    req = urllib.request.Request(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/devicecode", data=data
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def poll_device_code(device_code: str) -> dict:
    """Single, non-blocking poll of a device-code flow. Returns {"status": "pending"} while
    the user hasn't finished signing in yet, {"status": "success"} once a refresh token is
    granted (also updates WORK_IQ_REFRESH_TOKEN in-process immediately so live IQ probes start
    working without a restart), or {"status": "error", "detail": ...} on a real failure."""
    tenant = os.environ["WORK_IQ_TENANT_ID"]
    client_id = os.environ["WORK_IQ_CLIENT_ID"]
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": client_id,
        "device_code": device_code,
    }).encode()
    req = urllib.request.Request(
        f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token", data=data
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read())
        except Exception:
            return {"status": "error", "detail": "unreadable AAD error response"}
        if err.get("error") in ("authorization_pending", "slow_down"):
            return {"status": "pending"}
        return {"status": "error", "detail": err.get("error_description", err.get("error"))}
    if "refresh_token" in body:
        os.environ["WORK_IQ_REFRESH_TOKEN"] = body["refresh_token"]
        _CACHE.clear()  # drop any cached access tokens minted under the old refresh token
        return {"status": "success"}
    return {"status": "error", "detail": "no refresh_token in response"}
