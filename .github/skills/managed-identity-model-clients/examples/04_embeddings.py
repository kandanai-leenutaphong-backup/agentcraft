"""Worked example 4 — embeddings: index alignment, batches, and the refusals.

Run it: ``python3 examples/04_embeddings.py``.

Two things here are the whole reason ``embed()`` exists rather than a direct
SDK call:

1. An embedding deployment is *configured*, never inferred from the chat
   deployment. A chat deployment answers ``embeddings.create`` with a 404
   that reads like a misspelled name.
2. ``vectors[i]`` belongs to input ``i`` because the provider's ``index``
   field was checked, not because the list happened to arrive in order. A
   response that cannot be aligned raises instead of returning vectors
   quietly attached to the wrong text.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modelaccess import (  # noqa: E402
    ConfigError,
    FakeClient,
    ModelConfig,
    ModelError,
    connect,
    embedding_config,
    fake_embedding_response,
)

# An unconfigured embedding deployment is a refusal, before any socket opens.
chat_only = ModelConfig(
    endpoint="https://example-account.openai.azure.com/",
    deployment="my-chat-deployment",
)
try:
    connect(chat_only, client=FakeClient()).embed("hello")
except ConfigError as refused:
    assert "no embedding deployment is configured" in refused.message
else:  # pragma: no cover
    raise AssertionError("embedding without a configured deployment must refuse")

# Configured, on the same account.
config = chat_only.with_overrides(embedding_deployment="my-embedding-deployment")

transport = FakeClient(
    embeddings=[
        fake_embedding_response([[0.1, 0.2, 0.3]]),
        # Deliberately out of order: the provider is allowed to do this.
        fake_embedding_response([[9.0, 9.1], [1.0, 1.1], [5.0, 5.1]], indexes=[2, 0, 1]),
        # Two vectors for three inputs — unalignable, and refused.
        fake_embedding_response([[1.0], [2.0]]),
    ]
)

with connect(config, client=transport) as model:
    one = model.embed("a single document")
    assert one.count == 1
    assert one.vector == (0.1, 0.2, 0.3)
    assert one.dimensions == 3
    assert transport.requests[0]["model"] == "my-embedding-deployment"

    batch = model.embed(iter(["first", "second", "third"]))
    assert batch.count == 3
    # Re-ordered back into input order by the reported indexes.
    assert batch.vectors == ((1.0, 1.1), (5.0, 5.1), (9.0, 9.1))
    # A generator was accepted and copied before validation, so the request
    # carries the same three strings the caller believes were embedded.
    assert transport.requests[1]["input"] == ["first", "second", "third"]

    # `.vector` on a batch refuses rather than silently returning the first.
    try:
        batch.vector
    except ConfigError as refused:
        assert "3 vectors" in refused.message
    else:  # pragma: no cover
        raise AssertionError(".vector on a batch must refuse")

    # A response that cannot be aligned is an error, not a shorter list.
    try:
        model.embed(["one", "two", "three"])
    except ModelError as broken:
        assert broken.category == "unknown"
        assert broken.retryable is False
        assert "2 vectors for 3 inputs" in broken.message
    else:  # pragma: no cover
        raise AssertionError("a misaligned embedding response must raise")

# When the embedding deployment lives on another account, one client cannot
# serve both: embedding_config() builds the second one, pointed at the account
# that owns the deployment.
split = ModelConfig(
    endpoint="https://example-account.openai.azure.com/",
    deployment="my-chat-deployment",
    embedding_deployment="my-embedding-deployment",
    embedding_endpoint="https://example-embeddings-account.openai.azure.com/",
)
try:
    connect(split, client=FakeClient()).embed("hello")
except ConfigError as refused:
    assert "only reachable through its own account" in refused.message
else:  # pragma: no cover
    raise AssertionError("a cross-account embedding call must refuse")

second = embedding_config(split)
assert second.base_url == "https://example-embeddings-account.openai.azure.com/openai/v1/"
assert second.deployment == "my-embedding-deployment"

elsewhere = FakeClient(embeddings=[fake_embedding_response([[0.5, 0.5]])])
with connect(second, client=elsewhere) as embedder:
    assert embedder.embed("hello").vector == (0.5, 0.5)

print("04_embeddings: ok")
