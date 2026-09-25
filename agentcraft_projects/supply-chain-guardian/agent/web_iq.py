"""Live Web IQ integration: real-time web search per incident (api.microsoft.ai).

Called once per incident at request-build time (not a canned/pre-recorded snapshot). Falls
back to the scenario's mocked headline only if the live call fails or no API key is
configured, and always labels which happened.
"""
from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request

WEB_IQ_ENDPOINT = "https://api.microsoft.ai/v3/search/web"
_RETRY_DELAY_SECONDS = 0.5


def _is_retryable_web_error(exc: Exception) -> bool:
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code == 429 or 500 <= exc.code < 600
    return isinstance(exc, (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError))


def _load_json_with_single_retry(req: urllib.request.Request, timeout: int) -> dict:
    for attempt in range(2):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read())
        except Exception as exc:
            if attempt == 1 or not _is_retryable_web_error(exc):
                raise
            time.sleep(_RETRY_DELAY_SECONDS)


def live_web_search(query: str) -> dict:
    """Real-time web search. Returns {"mocked": True, ...} if not configured or the call
    fails, never raises. Always includes the exact request that was sent (method/url/body,
    api key redacted) so the UI can show precisely what was asked, not just a summary.
    Retries once after 0.5s for transient timeout/connection/429/5xx failures only."""
    request_meta = {"method": "POST", "url": WEB_IQ_ENDPOINT, "body": {"query": query, "count": 3}}
    api_key = os.environ.get("WEB_IQ_API_KEY")
    if not api_key:
        return {"mocked": True, "reason": "not configured", "request": request_meta}

    req = urllib.request.Request(
        WEB_IQ_ENDPOINT,
        data=json.dumps({"query": query, "count": 3}).encode(),
        headers={"x-apikey": api_key, "content-type": "application/json"},
        method="POST",
    )
    try:
        body = _load_json_with_single_retry(req, timeout=10)
    except Exception as exc:
        return {"mocked": True, "reason": f"live call failed: {exc}", "request": request_meta}

    results = body.get("webResults") or []
    titles = [r.get("title") for r in results[:3] if isinstance(r, dict) and r.get("title")]
    urls = [r.get("url") for r in results[:3] if isinstance(r, dict) and r.get("url")]
    if not titles:
        return {"mocked": True, "reason": "live call returned no results", "request": request_meta}
    return {
        "mocked": False,
        "query": query,
        "result_count": len(results),
        "titles": titles,
        "urls": urls,
        "headline": titles[0],
        "implication": f"Live web search for '{query}' returned {len(results)} current result(s); top result: {titles[0]}",
        "request": request_meta,
        "raw_response": body,
    }
