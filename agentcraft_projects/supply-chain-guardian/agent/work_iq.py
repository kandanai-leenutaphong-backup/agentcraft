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
import socket
import time
import urllib.error
import urllib.request
import urllib.parse
import json

try:
    from agent.iq_auth import get_token, get_managed_identity_token, auth_header
except ImportError:
    from iq_auth import get_token, get_managed_identity_token, auth_header  # type: ignore

GRAPH_SCOPE = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send offline_access"
# Mail stays on the delegated (single-mailbox, user-consented) flow deliberately: the
# managed identity only has the app-only User.Read.All permission (directory profile
# reads), not app-only Mail.Read -- granting tenant-wide app-only mailbox access was a
# deliberate scope decision (would let the app read ANY mailbox, not just this demo
# account) and was not made without the user confirming that trade-off.

_TOKEN_CACHE: dict = {"access_token": None, "expires_at": 0}
_RETRY_DELAY_SECONDS = 0.5


def _configured() -> bool:
    return all(
        os.environ.get(k)
        for k in ("WORK_IQ_TENANT_ID", "WORK_IQ_CLIENT_ID", "WORK_IQ_REFRESH_TOKEN")
    )


def _get_access_token() -> str | None:
    return get_token(GRAPH_SCOPE)


def _is_retryable_mail_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    return isinstance(exc, (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError))


def _load_json_with_single_retry(req: urllib.request.Request, timeout: int) -> dict:
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            if attempt == 1 or not _is_retryable_mail_error(exc):
                raise
            time.sleep(_RETRY_DELAY_SECONDS)


def live_recent_mail(top: int = 5) -> dict:
    """Fetch recent inbox messages (subject/from/receivedDateTime only) as live Work IQ
    evidence. Returns {"mocked": True} if not configured or the call fails. Always includes
    the exact Microsoft Graph request (method/url, no token) issued, so the UI can show
    precisely which Graph OData query produced the result. Retries once after 0.5s for
    transient timeout/connection/429/5xx failures only."""
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
        body = _load_json_with_single_retry(req, timeout=10)
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


def live_org_context() -> dict:
    """Fetch real organizational/collaboration context (manager + direct reports) for the
    Work IQ demo account via Microsoft Graph. Prefers the user-assigned managed identity
    (app-only User.Read.All, no delegated user context needed) and targets the specific
    demo user by UPN (WORK_IQ_USER_UPN); falls back to the delegated /me/... calls under
    the existing device-code-consented identity if managed identity is unavailable. A 404
    on manager (no manager set) or an empty directReports list are both valid live
    results, not failures."""
    upn = os.environ.get("WORK_IQ_USER_UPN")
    mi_token = get_managed_identity_token("https://graph.microsoft.com") if upn else None
    if mi_token and upn:
        base = f"https://graph.microsoft.com/v1.0/users/{upn}"
        token = mi_token
        auth_source = "managed_identity"
    else:
        base = "https://graph.microsoft.com/v1.0/me"
        token = _get_access_token()
        auth_source = "delegated"

    request_meta = {"method": "GET", "url": f"{base}/manager, {base}/directReports", "auth_source": auth_source}
    if not token:
        return {"mocked": True, "reason": "not configured", "request": request_meta}

    manager = None
    manager_body = None
    manager_req = urllib.request.Request(
        f"{base}/manager?$select=displayName,mail,jobTitle",
        headers=auth_header(token),
    )
    try:
        manager_body = _load_json_with_single_retry(manager_req, timeout=10)
        manager = {"displayName": manager_body.get("displayName"), "mail": manager_body.get("mail"),
                   "jobTitle": manager_body.get("jobTitle")}
    except urllib.error.HTTPError as exc:
        if exc.code != 404:
            return {"mocked": True, "reason": f"live call failed: {exc}", "request": request_meta}
    except Exception as exc:
        return {"mocked": True, "reason": f"live call failed: {exc}", "request": request_meta}

    reports_req = urllib.request.Request(
        f"{base}/directReports?$select=displayName,mail,jobTitle",
        headers=auth_header(token),
    )
    try:
        reports_body = _load_json_with_single_retry(reports_req, timeout=10)
    except Exception as exc:
        return {"mocked": True, "reason": f"live call failed: {exc}", "request": request_meta}
    reports = [{"displayName": r.get("displayName"), "mail": r.get("mail"), "jobTitle": r.get("jobTitle")}
               for r in reports_body.get("value", [])]

    return {
        "mocked": False,
        "manager": manager,
        "direct_reports": reports,
        "found": bool(manager or reports),
        "auth_source": auth_source,
        "request": request_meta,
        "raw_response": {"manager": manager_body if manager else None, "directReports": reports_body},
    }


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
