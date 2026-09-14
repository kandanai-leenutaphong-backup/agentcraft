"""Worked example 1 — one synchronous call, offline, asserting what came back.

Run it: ``python3 examples/01_sync_call.py``. No network, no sign-in: the
client is injected, which is the same seam a test uses. Swap
``client=transport`` for nothing at all and the identical code talks to the
real account named by the config.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import (  # noqa: E402
    FakeClient,
    ModelConfig,
    ModelError,
    connect,
    fake_text_response,
)

# Neutral coordinates. In production these come from ModelConfig.from_env(),
# which refuses with a named environment variable when either is missing.
config = ModelConfig(
    endpoint="https://example-account.openai.azure.com/",
    deployment="my-chat-deployment",
    default_max_output_tokens=256,
)

# The endpoint is normalised to exactly what the SDK needs, once, at startup.
assert config.base_url == "https://example-account.openai.azure.com/openai/v1/"

transport = FakeClient(
    responses=[
        fake_text_response(
            "A paperclip holds paper, picks a lock, and resets a router.",
            response_id="resp_1",
            usage={"input_tokens": 12, "output_tokens": 14, "total_tokens": 26},
        ),
        fake_text_response("second answer", response_id="resp_2", status="incomplete"),
    ]
)

with connect(config, client=transport) as model:
    answer = model.ask("Name three uses for a paperclip.", instructions="Be terse.")

    assert answer.text.startswith("A paperclip holds paper")
    assert answer.response_id == "resp_1"
    assert answer.deployment == "my-chat-deployment"
    assert answer.complete is True
    assert answer.output_tokens == 14

    # metadata() is the projection that is safe to log: no prompt, no answer.
    assert "text_chars" in answer.metadata()
    assert answer.text not in repr(answer)

    # The request the SDK would have received. `store` defaults to False, so
    # a convenience call never opts an account into server-side retention.
    sent = transport.requests[0]
    assert sent["model"] == "my-chat-deployment"
    assert sent["store"] is False
    assert sent["instructions"] == "Be terse."
    assert sent["max_output_tokens"] == 256

    # The escape hatch: anything the API supports, unwrapped and untouched.
    raw = model.respond(input="ping", temperature=0.2, metadata={"trace": "example"})
    assert raw.status == "incomplete"
    assert transport.requests[1]["temperature"] == 0.2
    # respond() defaults only the deployment; it adds no `store`.
    assert "store" not in transport.requests[1]

# Leaving the block closed the client. Using it afterwards is a config error,
# not a confusing connection failure five frames deeper.
try:
    model.ask("anything")
except ModelError as refused:
    assert refused.category == "config"
    assert refused.retryable is False
else:  # pragma: no cover - the assertion above is the point
    raise AssertionError("a closed client must refuse further calls")

# The injected client is still open: it was the caller's, and close() does not
# take something it was only lent. A client this package builds is closed, and
# `connect(..., owns_client=True)` transfers the lifecycle deliberately.
assert transport.closed is False
connect(config, client=transport, owns_client=True).close()
assert transport.closed is True
print("01_sync_call: ok")
