"""Live Work IQ integration: Microsoft Graph mail read/send.

Uses a delegated public-client refresh token (no client secret required - this is the
well-known "Microsoft Graph PowerShell" public client ID, consented via a one-time
device-code sign-in). The refresh token is read from environment variables only
(WORK_IQ_TENANT_ID, WORK_IQ_CLIENT_ID, WORK_IQ_USER_UPN, WORK_IQ_REFRESH_TOKEN) and is
never logged or returned in API responses. If any of these are missing, all functions
fall back to `mocked=True` so the caller can label evidence honestly.
"""
from __future__ import annotations

import os
import time
import urllib.request
import urllib.parse
import json

try:
    from agent.iq_auth import get_token, auth_header
except ImportError:
    from iq_auth import get_token, auth_header  # type: ignore

GRAPH_SCOPE = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send offline_access"

_TOKEN_CACHE: dict = {"access_token": None, "expires_at": 0}


def _configured() -> bool:
    return all(
        os.environ.get(k)
        for k in ("WORK_IQ_TENANT_ID", "WORK_IQ_CLIENT_ID", "WORK_IQ_REFRESH_TOKEN")
    )


def _get_access_token() -> str | None:
    return get_token(GRAPH_SCOPE)


def live_recent_mail(top: int = 5) -> dict:
    """Fetch recent inbox messages (subject/from/receivedDateTime only) as live Work IQ
    evidence. Returns {"mocked": True} if not configured or the call fails. Always includes
    the exact Microsoft Graph request (method/url, no token) issued, so the UI can show
    precisely which Graph OData query produced the result."""
    url = (
        "https://graph.microsoft.com/v1.0/me/messages"
        f"?$top={top}&$select=subject,from,receivedDateTime"
    )
    request_meta = {"method": "GET", "url": url}
    token = _get_access_token()
    if not token:
        return {"mocked": True, "reason": "not configured", "request": request_meta}
    req = urllib.request.Request(url, headers=auth_header(token))
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read())
    except Exception as exc:
        return {"mocked": True, "reason": f"live call failed: {exc}", "request": request_meta}
    messages = [
        {
            "subject": m.get("subject"),
            "from": (m.get("from") or {}).get("emailAddress", {}).get("address"),
            "received": m.get("receivedDateTime"),
        }
        for m in body.get("value", [])
    ]
    return {"mocked": False, "messages": messages, "request": request_meta, "raw_response": body}


def send_escalation_email(scenario_id: str, subject: str, body_text: str) -> dict:
    """Send a real escalation email to the configured Work IQ user via Microsoft Graph.
    Only called after an explicit human 'approved' decision (see agent/reasoning.py
    apply_decision) - never autonomously. Returns a result dict; never raises."""
    token = _get_access_token()
    to_addr = os.environ.get("WORK_IQ_USER_UPN")
    if not token or not to_addr:
        return {"sent": False, "mocked": True, "reason": "not configured"}

    payload = json.dumps({
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body_text},
            "toRecipients": [{"emailAddress": {"address": to_addr}}],
        }
    }).encode()
    req = urllib.request.Request(
        "https://graph.microsoft.com/v1.0/me/sendMail",
        data=payload,
        method="POST",
        headers={**auth_header(token), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            ok = resp.status in (200, 202)
    except Exception as exc:
        return {"sent": False, "mocked": False, "error": str(exc)}
    return {"sent": ok, "mocked": False, "to": to_addr, "scenario_id": scenario_id}
