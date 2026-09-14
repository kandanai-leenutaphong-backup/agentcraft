"""Worked example 5 — the failure model: refusals, sanitised errors, ownership.

Run it: ``python3 examples/05_failure_modes.py``.

Three claims are demonstrated, each of which is a bug somewhere else if it is
untrue:

1. A missing endpoint or deployment fails at startup, naming the variable to
   set. There is no built-in account to fall back to.
2. A provider error reaches the application as a classified ``ModelError``
   with no prompt, completion or provider body in it — while the original
   exception is still attached as ``__cause__`` for a debugger.
3. A credential the caller built is still the caller's after ``close()``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import (  # noqa: E402
    ConfigError,
    FakeClient,
    ModelClient,
    ModelConfig,
    ModelError,
    connect,
)

# ---------------------------------------------------------------- 1. config

try:
    ModelConfig.from_env(env={})
except ConfigError as refused:
    assert "MODEL_ENDPOINT is not set" in refused.message
    assert refused.category == "config"
    assert refused.retryable is False
else:  # pragma: no cover
    raise AssertionError("an unset endpoint must refuse at startup")

try:
    ModelConfig.from_env(env={"MODEL_ENDPOINT": "https://example-account.openai.azure.com/"})
except ConfigError as refused:
    assert "MODEL_DEPLOYMENT is not set" in refused.message
else:  # pragma: no cover
    raise AssertionError("an unset deployment must refuse at startup")

# A key in the environment is refused loudly rather than ignored quietly: this
# package never sends one, and a silent ignore leaves a person debugging a 401.
try:
    ModelConfig.from_env(
        env={
            "MODEL_ENDPOINT": "https://example-account.openai.azure.com/",
            "MODEL_DEPLOYMENT": "my-chat-deployment",
            "OPENAI_API_KEY": "unset-placeholder",
        }
    )
except ConfigError as refused:
    assert "never sends a key" in refused.message
else:  # pragma: no cover
    raise AssertionError("a key environment variable must be refused")

config = ModelConfig.from_env(
    env={
        "MODEL_ENDPOINT": "example-account.openai.azure.com",
        "MODEL_DEPLOYMENT": "my-chat-deployment",
        "MODEL_TIMEOUT_SECONDS": "30",
        "MODEL_MAX_RETRIES": "1",
    }
)
assert config.base_url == "https://example-account.openai.azure.com/openai/v1/"
assert config.timeout_secs == 30.0
assert config.max_retries == 1

# --------------------------------------------------------------- 2. errors


class PretendCredentialFailure(Exception):
    """Named like the identity library's failure, which is how it is matched."""


PretendCredentialFailure.__name__ = "ClientAuthenticationError"

SECRET_PROMPT = "patient 12345 has a rash"
auth_failure = PretendCredentialFailure(
    f"AADSTS700016 while sending prompt {SECRET_PROMPT!r} to the deployment"
)

model = connect(config, client=FakeClient(responses=[auth_failure]))
try:
    model.ask(SECRET_PROMPT)
except ModelError as failed:
    assert failed.category == "auth"
    assert failed.retryable is False
    assert failed.deployment == "my-chat-deployment"
    # Nothing the provider said crosses the boundary — not in the message,
    # not in str(), not in repr().
    assert SECRET_PROMPT not in failed.message
    assert SECRET_PROMPT not in str(failed)
    assert SECRET_PROMPT not in repr(failed)
    # The original is still there for a debugger, one attribute away.
    assert failed.__cause__ is auth_failure
    assert SECRET_PROMPT in str(failed.__cause__)
else:  # pragma: no cover
    raise AssertionError("a credential failure must surface as ModelError")
finally:
    model.close()

# ------------------------------------------------------------ 3. ownership


class CountingCredential:
    """Stands in for a credential the caller built and still holds."""

    def __init__(self) -> None:
        self.closes = 0

    def close(self) -> None:
        self.closes += 1


caller_owned = CountingCredential()
client = ModelClient(config, client=FakeClient(), credential=caller_owned)
client.close()
assert caller_owned.closes == 0, "closing our client must not close the caller's credential"

package_owned = CountingCredential()
client = ModelClient(config, client=FakeClient(), credential=package_owned, owns_credential=True)
client.close()
client.close()  # idempotent: a second close is not a second teardown
assert package_owned.closes == 1

print("05_failure_modes: ok")
