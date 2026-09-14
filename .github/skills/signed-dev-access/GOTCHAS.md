# GOTCHAS.md — signed-dev-access

Failures that cost real time to find. Each hit in production, not theorised.
Symptom first, because that is how you arrive here.
---

## G1 — Signed path must be the RAW path, not the decoded path

**Symptom.** A signed request 401s, only when the URL contains a percent-encoded
character (apostrophe, newline, semicolon, space). Plain paths verify.

**Cause.** ASGI exposes `scope["path"]` (percent-**decoded**) and
`scope["raw_path"]` (original wire bytes). The client signed the encoded form; a
server reconstructing from `scope["path"]` signs `A\nB` where the client signed
`A%0AB`.

**Fix.** Reconstruct from `raw_path` when present, falling back to `path`.
Implemented in `devauth/_middleware.py`; do not "simplify" it away.

**Corollary.** If your client library normalises or re-encodes URLs, sign the
post-normalisation form. Sign what goes on the wire.

---

## G2 — Ingress may percent-decode before forwarding

**Symptom.** The same signed request succeeds against the container and 401s
through platform ingress.

**Cause.** Some managed ingresses (Azure Container Apps observed) decode `%2F`
and friends before forwarding, so the application never sees the signed bytes.
`raw_path` is already decoded when it reaches you.

**Fix.** Avoid percent-encoded path segments in signed requests; put the value in
a query parameter or the body. Where you cannot, verify through the real ingress
before trusting it: in-container success proves nothing about the deployed path.

---

## G3 — Ingress may strip the optional context header

**Symptom.** Signed requests carrying `X-Request-Context` return 401 externally,
200 in-container. Timestamp and signature headers survive; only context is
dropped. An empty context externally returns 200.

**Cause.** External ingress can drop unrecognised non-standard headers while
preserving others. The signature covers the slug, so losing the header silently
invalidates it.

**Fix.** Test header preservation during environment bring-up. If the context
header does not survive, use the default (empty-slug) identity for live probes.
Do **not** weaken the primary auth path in response.

---

## G4 — Validate the slug at the trust boundary

**Symptom.** HTTP 500, not 401, on an unusual context value. Stack trace points
far downstream — partition-key construction, request-scope building, a storage
client.

**Cause.** An unconstrained `strip().lower()` accepts non-ASCII characters,
path-traversal shapes such as `probe/../admin`, and arbitrarily long values,
which flow into consumers assuming a tame identifier and crash there.

**Fix.** Allowlist the normalised slug to `^[a-z0-9_-]{0,64}$` inside the
verifier, before it is used for anything. An auth path convertible into a crash
class is an availability bug in an authentication costume. Empty stays valid and
maps to the consumer's default identity.

---

## G5 — Signing material has no nonce, so replay needs a cache

**Symptom.** A captured signed request replays successfully for up to five
minutes.

**Cause.** The canonical string is `(method, raw_path, timestamp, body_sha256)`.
No nonce, no `jti`; any capture is valid for the full skew window.

**Fix.** Single-flight rejection: record every accepted signature, reject the
second occurrence. TTL must equal the skew window — a shorter TTL evicts entries
that can still verify, reopening the hole.
---

## G6 — The replay cache is per-process (known limitation)

**Symptom.** Under horizontal autoscale, a captured signature replayed against a
different replica is accepted.

**Cause.** Each process holds its own `_seen` dictionary. Nothing shared.

**Status.** Deliberately unsolved here. `ReplayNonceStoreAdapter` is the
documented seam: inject a durable shared nonce store (Redis `SETNX`, an
optimistic-etag row, a signed-nonce ledger) with the same TTL; the call site does
not change.

**Rule.** Ship the limitation written down. An undocumented gap is worse.

---

## G7 — Never `BaseHTTPMiddleware`

**Symptom.** Server-sent events or streaming responses hang, buffer, or arrive
all at once, but only once auth is mounted.

**Cause.** Starlette's `BaseHTTPMiddleware` buffers the response body.

**Fix.** Pure ASGI middleware, as implemented. Inspect headers, read the body
once, replay it through a fresh `receive`. Delegate later `receive` calls to the
original transport so genuine `http.disconnect` reaches the framework — a
synthetic disconnect cancels a streaming response the moment it starts.

---

## G8 — Mount order matters for CORS preflight

**Symptom.** Browser preflight requests fail after mounting.

**Cause.** Mount position in the middleware stack.

**Fix.** Mount early, before CORS short-circuits a preflight. Preflight requests
carry no signing headers and fall through the pass-through branch untouched.

---

## G9 — Deploy must resolve the public key from more than one place

**Symptom.** A deploy silently ships without the key; every signed probe 401s and
the cause is invisible because failures are unlogged by design.

**Cause.** A deploy script reading only `${DEV_PUBLIC_KEY_ED25519:-}` gets an
empty string when the operator forgot to export it, and the middleware correctly
declines to mount.

**Fix.** Resolve in order: shell env, explicit key file, default key path, then
derive from the local private key. Echo which source won. The key is not a
secret, so this costs nothing.

---

## G10 — Silence is the feature, so build an aliveness probe

**Symptom.** Misconfigured key, wrong signature and stripped header are
indistinguishable — all three give an identical bare 401.

**Cause.** Working as designed.

**Fix.** Keep one known-good signed request as a canary, run it first after every
deploy. Diagnose by bisecting environments (in-container vs ingress), never by
adding a log line. Diagnostics on the failure path destroy the property that
makes this safe to leave mounted.

---

## G11 — The empty-key off switch is in the installer, not the class

**Symptom.** Constructing `SignedRequestASGIMiddleware` directly with an empty
`public_key_b64` does **not** pass requests through. Signed requests get a 401,
because verification against an empty key always fails.

**Cause.** The class docstring lists "public key non-empty" in the activation
gate, but the class gates on header presence only. The empty-key short-circuit
lives in `install_signed_request_auth`, which declines to mount and returns
`False`.

**Fix.** Always mount via `install_signed_request_auth`. Do not construct the
class directly unless pre-binding an identity factory in a subclass, and then
gate on the key yourself.

**Note.** Found by `tests/selftest.py` while packaging this box, not in
production. Behaviour left as-is because changing it would alter a
security-relevant code path; the contract is documented here instead.

---

## G12 — Timestamp precision must exceed your request concurrency

**Symptom.** Parallel identical requests intermittently 401. One succeeds, the
rest are rejected as replays. Sequential requests are fine.

**Cause.** A one-second-precision client timestamp. Two legitimate concurrent
requests with the same method, path, body and slug produced a byte-identical
canonical string, therefore an identical signature — and the replay cache (G5)
correctly rejected the second. The defence misfired on honest traffic.

**Fix.** Microsecond precision (`%Y-%m-%dT%H:%M:%S.%fZ`). Timestamps diverge
naturally, so the cache only catches true byte-replays.

**General rule.** When anti-replay identity is derived from request content, that
content must include something varying faster than your peak request rate.
Precision is a correctness property, not cosmetics.
