"""Worked example 3 — structured output, and the refusal that is not an error.

Run it: ``python3 examples/03_structured_output.py``.

``parse()`` hands ``text_format`` to the SDK, which derives the JSON schema,
enforces it server-side and validates the answer back into an object. Two
outcomes are ordinary and both must be handled: an object, or a refusal. A
refusal is a *successful* call whose answer is "no" — it leaves ``parsed``
None and never raises.

The example uses a plain class so it runs with no third-party package
installed. With the real SDK, ``text_format`` is a pydantic model class.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import (  # noqa: E402
    FakeClient,
    ModelConfig,
    connect,
    fake_parsed_response,
)


@dataclass
class Severity:
    """The shape the caller wants back."""

    level: str
    confidence: float


config = ModelConfig(
    endpoint="https://example-account.openai.azure.com/",
    deployment="my-chat-deployment",
)

transport = FakeClient(
    responses=[
        fake_parsed_response(
            Severity(level="high", confidence=0.82),
            text='{"level":"high","confidence":0.82}',
            usage={"input_tokens": 40, "output_tokens": 12},
        ),
        fake_parsed_response(
            None,
            refusal="I can't help with that.",
            status="completed",
        ),
    ]
)

with connect(config, client=transport) as model:
    result = model.parse("Classify this incident.", text_format=Severity)

    assert result.parsed == Severity(level="high", confidence=0.82)
    assert result.refused is False
    assert result.complete is True
    assert result.metadata()["parsed"] is True

    # The refusal path. Nothing raised; `parsed` is None and `refused` says why.
    declined = model.parse("Classify this incident.", text_format=Severity)
    assert declined.parsed is None
    assert declined.refused is True
    assert declined.refusal == "I can't help with that."

    # The refusal *text* is not in the loggable projection: a refusal message
    # can quote the input it refused.
    assert declined.metadata()["refused"] is True
    assert "I can't help" not in str(declined.metadata())
    assert "I can't help" not in repr(declined)

# Both calls went to responses.parse with the caller's format, and neither
# opted the account into server-side retention.
assert [r["kind"] for r in transport.requests] == ["responses.parse", "responses.parse"]
assert all(r["store"] is False for r in transport.requests)
print("03_structured_output: ok")
