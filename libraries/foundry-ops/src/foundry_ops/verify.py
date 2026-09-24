"""Read-back verification: active version identity, runtime identity, anonymous refusal, stored responses."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import quote

from .errors import ReadbackError, RefusedError, VerificationError

REFUSAL_STATUSES = (401, 403)
DEFINITION_KEYS = ("kind", "cpu", "memory", "protocol_versions")
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
AI_SCOPE = "https://ai.azure.com/.default"


def safe_identifier(value: Any, what: str = "identifier") -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise RefusedError("identifier", f"unsafe {what}")
    return value


def is_not_found(error: BaseException) -> bool:
    """True only for an explicit 404. `openai.APIConnectionError` is not evidence of absence."""
    return getattr(error, "status_code", None) == 404 or type(error).__name__ in {"ResourceNotFoundError", "NotFoundError"}


def agent_responses_url(project_endpoint: str, agent_name: str) -> str:
    return (project_endpoint.rstrip("/") + "/agents/" + safe_identifier(agent_name, "agent name")
            + "/endpoint/protocols/openai/responses?api-version=v1")


def _http(http_client: Any, timeout: float) -> tuple[Any, bool]:
    if http_client is not None:
        return http_client, False
    try:
        import httpx
    except ImportError as error:  # pragma: no cover - depends on host
        raise ImportError("install agentcraft-foundry-ops[http] or pass http_client") from error
    return httpx.Client(timeout=timeout, follow_redirects=False), True


def anonymous_probe(url: str, *, http_client: Any = None, timeout: float = 30.0,
                    payload: Mapping[str, Any] | None = None) -> int:
    """POST without credentials, redirects not followed; return the HTTP status."""
    client, owned = _http(http_client, timeout)
    try:
        response = client.post(url, json=dict(payload or {"input": "unauthorized probe", "store": False}))
    finally:
        if owned:
            client.close()
    return response.status_code


def require_refusal(status: int) -> int:
    """Only 401/403 prove refusal; 404, a login redirect or any success do not."""
    if status not in REFUSAL_STATUSES:
        raise VerificationError("anonymous_accepted", f"anonymous refusal not proved: HTTP {status}")
    return status


def check_identity(observed: Mapping[str, Any] | None, expected: Mapping[str, Any], *, what: str = "identity") -> None:
    """Every expected key must equal; the message names mismatching keys, never values."""
    observed = observed or {}
    drifted = sorted(key for key, value in expected.items() if observed.get(key) != value)
    if drifted:
        raise VerificationError("identity_mismatch", f"{what} mismatch: " + ", ".join(drifted))


def check_active_version(actual: Mapping[str, Any], *, version: str, image: str,
                         metadata: Mapping[str, Any] | None = None, definition: Mapping[str, Any] | None = None,
                         definition_keys: tuple[str, ...] = DEFINITION_KEYS) -> dict[str, Any]:
    """Pure check of a `get_version().as_dict()` payload against the exact deployed identity."""
    observed = actual.get("definition") or {}
    failures = []
    if str(actual.get("version")) != str(version):
        failures.append("version")
    if actual.get("status") != "active":
        failures.append("status")
    if (observed.get("container_configuration") or {}).get("image") != image:
        failures.append("image")
    failures.extend("definition." + key for key in (definition_keys if definition else ())
                    if observed.get(key) != definition.get(key))
    recorded = actual.get("metadata") or {}
    failures.extend("metadata." + key for key, value in (metadata or {}).items() if recorded.get(key) != value)
    if failures:
        raise VerificationError("version_readback", "exact version not active: " + ", ".join(failures))
    return {"version": str(actual["version"]), "status": actual["status"], "definition": dict(observed)}


def read_stored_response(openai_client: Any, response_id: str, *, bearer_token: str, http_client: Any = None,
                         timeout: float = 60.0) -> dict[str, Any] | None:
    """Raw GET `{base_url}responses/{id}`. Returns the body, or None only for a JSON error 404.

    The OpenAI SDK maps this endpoint's 404 to `APIConnectionError`, so SDK retrieve cannot prove absence.
    `bearer_token` is a caller-acquired token for `AI_SCOPE`; it is sent, never retained.
    """
    url = str(openai_client.base_url).rstrip("/") + "/responses/" + quote(safe_identifier(response_id, "response id"))
    client, owned = _http(http_client, timeout)
    try:
        reply = client.get(url, params=dict(openai_client.default_query or {}),
                           headers={"Authorization": "Bearer " + bearer_token})
    finally:
        if owned:
            client.close()
    if reply.status_code == 200:
        return reply.json()
    if reply.status_code == 404:
        try:
            body = reply.json()
        except ValueError:
            body = None
        if isinstance(body, dict) and isinstance(body.get("error"), dict):
            return None
        raise ReadbackError("readback_unrecognized_404", "404 without service error body; absence not proved")
    raise ReadbackError("readback_status", f"stored response readback HTTP {reply.status_code}")
