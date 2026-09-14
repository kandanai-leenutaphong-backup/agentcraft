# GOTCHAS — entra-api-auth

Thirteen ways token authentication fails, symptom first. Numbers are stable: code cites them.

Several are security findings rather than outages, and are marked — the symptom of a security
defect is usually **nothing at all**.

---

## G1 — Every authenticated request makes an outbound HTTPS call

**Symptom.** Latency proportional to nothing in your own code. Under load,
timeouts tracing into token validation. The identity provider's bad minute is
yours, every user, cached tokens included.

**Cause.** Fetching the signing key set per validation. Most published examples
do this: reads correctly, cheap in isolation, costly only at volume.

**Fix.** Cache the key set with a TTL. `JWKSCache` refreshes on a schedule and
serves stale keys when a refresh fails — keys valid a minute ago are still signed
by the same provider, and rejecting everything over a slow discovery endpoint
converts a dependency wobble into your outage.

**Rule.** A per-request call to a third party is a per-request dependency on
their availability, at your volume.

---

## G2 — A field from the token appears in the response body *(security)*

**Symptom.** None. That is the problem. A probe finds it, or nothing does.

**Cause.** Error messages built from the token: *"Unknown signing key `<kid>`"*.
An unverified token is attacker-controlled throughout, and that message reaches a
response body, a log, a dashboard, an alert. Probes planted newlines forging log
entries, ANSI escapes rewriting an operator's terminal, HTML executing where the
log renders, kilobyte padding bloating storage.

**Fix.** Public messages are **selected**, never built. `AuthError` maps a reason
code to a constant string; nothing input-derived reaches it. Operators get the
key id's *length* — enough to separate a rotation miss from a padding attack —
never its value.

**Rule.** Anything before signature verification is hostile input, including the
parts that look structural.

---

## G3 — Several users share one account, and none of them did anything wrong *(security)*

**Symptom.** Users see each other's data. Ownership checks present and correct.
Affected identities usually service principals or automation.

**Cause.** Reading the identity claim without requiring it. A token verifies
perfectly — real signature, right audience, right issuer — and still omits the
claim you key on, because claim presence depends on flow, resource and app
registration. Such callers all have `id=""`, so `owner_id == principal.id` makes
them one person.

**Fix.** Require the claim. `required_claims=("oid",)` is the default; an empty
required-claims list is rejected at construction. Do not relax it for a service
principal: app-only tokens carry `oid` too — the service principal's directory
object id — so the default already admits them. Classify with `idtyp`
(CONTRACT.md §`kind`).

**Rule.** A claim used as a primary key must be a claim you require.

---

## G4 — Returning 403 turns your id space into a directory *(security)*

**Symptom.** None, until someone iterates your identifiers and gets a clean list
of which exist.

**Cause.** `403` on a resource that exists but is not the caller's, `404` on one
that does not. The status code is an oracle answering "does this id exist", for
every id, to anyone with any valid token.

**Fix.** Both answer 404. `assert_readable` raises `NotFoundError` either way;
the log keeps the distinction for the operator.

**The exception, deliberately.** Writing to a *shared* template returns 403: the
caller can already read it, its existence is no secret, and 403 is the honest
answer to "may I change this".

**Rule.** Any distinguishable response is a query. Decide what it answers.

---

## G5 — Tokens are rejected for the wrong audience, and the audience is right

**Symptom.** Intermittent `Invalid audience`. Same user, API, app registration.
Often splits by client: web app works, script does not.

**Cause.** Entra issues `aud` as the bare application id or as
`api://<application-id>`, depending how the scope was requested. Accepting one
rejects the other, and the failure never names the form.

**Fix.** Accept both. `AuthConfig.audiences()` returns both, plus configured
extras.

---

## G6 — A multi-tenant API accepts a token signed by the wrong tenant's key *(security)*

**Symptom.** None. Token valid, issuer looks right, signature verifies.

**Cause.** Multi-tenant issuers cannot be exact-matched, so they are checked by
shape — which says nothing about the signing key. A token claiming tenant A,
signed by a key scoped to tenant B, passes both checks independently.

**Fix.** Cross-check. Entra publishes an `issuer` per key, sometimes templated
`{tenantid}`. Substitute the token's tenant, compare, reject a mismatch. Keys
with no issuer field are legacy and skip the check.

**Rule.** Two checks that each pass do not imply the pair is consistent. Somebody
has to compare them.

---

## G7 — Ownership bugs that only appear once auth is switched on

**Symptom.** Works in development. In production users see 404s for their own
data, or worse, do not.

**Cause.** Ownership enforcement wired to the auth switch. Disabled auth makes
every caller the same anonymous identity, so ownership checks pass trivially and
the path is first exercised in production.

**Fix.** Keep the two independent. Disabled auth still yields a principal with an
id, and `X-User-Id` gives each browser tab a distinct one, so two tabs are two
users and the rules run locally as they will live.

**Rule.** A check that cannot fail in development is first tested by your users.

---

## G8 — Auth works locally and 401s behind the load balancer

**Symptom.** Identical requests: 200 direct to the container, 401 through
ingress. Nothing in the app changed.

**Cause.** Two header variants.
*Case.* Header names are case-insensitive and any hop may normalise them. A
`headers["Authorization"]` lookup that works on one ASGI server returns nothing
behind a proxy that lowercases.
*Dropped headers.* Ingress may strip headers it does not recognise. Custom
context headers have survived in-container and vanished externally, while
`Authorization` — universally understood — passed untouched.

**Fix.** Look up case-insensitively; `_first()` does. Carry identity in
`Authorization`, not a bespoke header, and verify header survival through real
ingress, not a local server.

---

## G9 — Valid tokens rejected as expired, or as not yet valid

**Symptom.** Sporadic 401s clustered on one host or deployment. Retrying works.
Worst near the start or end of a token's life.

**Cause.** Clock drift between issuer and validating host. `nbf` and `exp` are
absolute instants; a host seconds fast rejects correctly minted tokens.

**Fix.** Ten seconds of leeway by default: enough for ordinary drift, small
enough that an expired token stays expired. Do not raise it to paper over a
wrong clock; fix the clock.
---

## G10 — An unauthenticated caller can make you flood the identity provider *(security)*

**Symptom.** Outbound discovery traffic tracking inbound volume. Then throttling,
then failed validations for legitimate users.

**Cause.** Refreshing the key set on every unrecognised key id. Correct response
to rotation, and a free amplifier: random key ids, no credential, one outbound
fetch each.

**Fix.** Rate-limit the rotation-triggered refresh: one forced refresh per
cooldown window, shared across concurrent callers by a single-flight lock. Real
rotation still resolves within one window; a probe gets one refresh however many
ids it invents.

**Rule.** Work an unauthenticated request can trigger must be bounded per unit
time, not per request.

---

## G11 — Authentication was disabled in production and nothing complained *(security)*

**Symptom.** None. Every request succeeds, dashboards green. Exactly what a
wide-open API looks like.

**Cause.** A development switch reaching an environment where it is wrong,
usually a typo rather than a decision: `AUTH_ENABLED` of `"True "`, `"1 "` or
`"enabled"` parsed by a permissive truthiness rule that gets it backwards.

**Fix.** Three layers. Parsing accepts only an explicit affirmative, so anything
unrecognised fails **closed** to enabled-and-strict. `warnings()` states that
every request is being granted an identity. `require_enabled()` refuses to start
— call it in any deployed environment and the mistake is a failed boot, not a
silent exposure.

**Rule.** The dangerous value must be hard to set by accident.

---

## G12 — The development identity header is honoured in production *(security)*

**Symptom.** None, until someone sends `X-User-Id` and becomes whoever they like.

**Cause.** Two shapes: the header consulted before the auth check, or as a
*fallback* when no token is present — the same thing with extra steps.

**Fix.** The development branch sits inside `if not config.enabled` and returns
before any header is read. With auth on, headers are not consulted: a request
carrying a valid token and `X-User-Id` resolves to the token's identity; one
carrying only `X-User-Id` is a plain 401. Both asserted.

Separately, the development principal is `kind="developer"`, so a self-asserted
identity never appears in a log or audit record as a proven one.

**Rule.** A bypass must be structurally unreachable, not conditionally skipped.

---

## G13 — The endpoint returns 422 asking for a query parameter you never declared

**Symptom.** A protected route responds `422 Unprocessable Entity`, body naming
`request` as a missing query parameter. Never 401, never 200 — the dependency
appears not to run.

**Cause.** Postponed annotation evaluation (`from __future__ import
annotations`) plus a framework-local import. `async def dep(request: Request)`
becomes the *string* `"Request"`, and the framework resolves annotations against
module globals, where `Request` is absent because the import sits inside the
function building the dependency. Unresolvable annotation, so the parameter is
treated as an ordinary query field.

**Fix.** Rebind the real objects after defining the function:
`dep.__annotations__ = {"request": Request, "return": Principal}`. Keeps the
framework a lazy import while giving the introspector something resolvable.

**Rule.** Any framework reading annotations at runtime is broken by string
annotations naming types it cannot import. Same family: schema builders
constructing a model per callable — one unresolvable name takes down everything
built in that pass, not just the offending function.
