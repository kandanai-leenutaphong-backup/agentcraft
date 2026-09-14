"""Worked example 6 — the real SDK over a fake HTTP transport.

Run it: ``python3 examples/06_identity_over_fake_transport.py``. It needs the
declared dependencies (``pip install -r requirements.txt``) and still makes no
network call: ``httpx.MockTransport`` answers every request in-process.

Why this example exists at all: every other example injects a fake client, so
it proves this package's own logic and nothing about the SDK's. The claim that
identity works — *the token callable is re-invoked on every request, so
refresh belongs to the credential* — is a claim about the SDK's behaviour. It
is only evidence if the real SDK is the thing under test.

What is asserted here:

- the URL the request actually goes to, derived from the normalised endpoint;
- the ``Authorization`` header, which changes between the first and second
  request because the provider was called again rather than frozen;
- a provider 429 arriving as a classified, retryable ``ModelError`` with no
  provider body in it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
from openai import OpenAI

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import ModelConfig, ModelError, connect  # noqa: E402

config = ModelConfig(
    endpoint="example-account.openai.azure.com",
    deployment="my-chat-deployment",
    timeout_secs=5.0,
    max_retries=0,
)

seen: list[httpx.Request] = []
issued = iter(f"token-{n}" for n in range(100))

# A credential's token provider is a zero-argument callable. This one hands
# out a different value each time it is called, so "called again" is visible
# in the header the service would have received.
tokens_issued: list[str] = []


def token_provider() -> str:
    token = next(issued)
    tokens_issued.append(token)
    return token


def handler(request: httpx.Request) -> httpx.Response:
    seen.append(request)
    if len(seen) == 3:
        return httpx.Response(
            429,
            json={
                "error": {
                    "code": "429",
                    "message": "Requests to the deployment for prompt "
                    "'patient 12345 has a rash' exceeded the rate limit.",
                }
            },
            headers={"x-request-id": "req-abc123"},
        )
    return httpx.Response(
        200,
        json={
            "id": f"resp_{len(seen)}",
            "object": "response",
            "created_at": 0,
            "model": "my-chat-deployment",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "id": "msg_1",
                    "status": "completed",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "pong", "annotations": []}],
                }
            ],
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "usage": {
                "input_tokens": 5,
                "output_tokens": 2,
                "total_tokens": 7,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        },
    )


# Built exactly as this package builds it — base URL, callable credential,
# timeout, retry ceiling — with the socket replaced by an in-process handler.
sdk_client = OpenAI(
    base_url=config.base_url,
    api_key=token_provider,
    timeout=config.timeout_secs,
    max_retries=config.max_retries,
    http_client=httpx.Client(transport=httpx.MockTransport(handler)),
)

with connect(config, client=sdk_client) as model:
    first = model.ask("ping")
    second = model.ask("ping again")

    assert first.text == "pong"
    assert second.text == "pong"
    assert first.input_tokens == 5

    # The endpoint rule, end to end: a bare hostname reached the right path.
    assert str(seen[0].url) == (
        "https://example-account.openai.azure.com/openai/v1/responses"
    )

    # The identity claim. Two requests, two provider calls, two headers.
    assert tokens_issued == ["token-0", "token-1"]
    assert seen[0].headers["authorization"] == "Bearer token-0"
    assert seen[1].headers["authorization"] == "Bearer token-1"
    assert seen[0].headers["authorization"] != seen[1].headers["authorization"]

    # A provider error is classified, and its body — which quotes the prompt —
    # does not travel with it.
    try:
        model.ask("patient 12345 has a rash")
    except ModelError as limited:
        assert limited.category == "rate_limit"
        assert limited.status_code == 429
        assert limited.retryable is True
        assert limited.request_id == "req-abc123"
        assert "patient 12345" not in str(limited)
        assert "patient 12345" in str(limited.__cause__)
    else:  # pragma: no cover
        raise AssertionError("a 429 must surface as a retryable ModelError")

assert len(seen) == 3
print("06_identity_over_fake_transport: ok")
