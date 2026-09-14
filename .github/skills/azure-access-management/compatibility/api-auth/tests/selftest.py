#!/usr/bin/env python3
"""selftest — proves this box works in the environment it was copied into.

No test framework, no network, no Entra tenant. A throwaway RSA key pair is
generated in-process and used to publish a fake key set and mint real RS256
tokens, so the validator under test is driven by genuinely signed input — and by
genuinely hostile input, which is the half that matters.

Run:  python3 tests/selftest.py    (exit 0 = the box is functional here)
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa

import entraauth as ea
from entraauth._jwks import build_rsa_pem

# Every rejection logs a warning. Expected, and noisy.
logging.disable(logging.CRITICAL)

_PASS = 0
_FAIL = 0

# Syntactically valid, entirely fictional. No real tenant or application id
# appears anywhere in this box.
TENANT = "11111111-2222-3333-4444-555555555555"
OTHER_TENANT = "99999999-8888-7777-6666-555555555555"
CLIENT_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
KID = "test-key-1"


def check(label: str, condition: bool, detail: str = "") -> None:
    """Record one assertion. Never raises, so one run reports every failure."""
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  ok   {label}")
    else:
        _FAIL += 1
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


def rejects(reason: str, coro) -> bool:
    """True when awaiting ``coro`` raises AuthError with this reason."""
    try:
        asyncio.run(coro)
    except ea.AuthError as exc:
        if exc.reason == reason:
            return True
        print(f"       (got reason {exc.reason!r}, wanted {reason!r})")
        return False
    except Exception as exc:
        print(f"       (got {type(exc).__name__}: {exc})")
        return False
    return False


def raises(exc_type, fn, *args, **kwargs) -> BaseException | None:
    """Return the expected exception, or None if it was not raised."""
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    except Exception:
        return None
    return None


# ── a fake Entra ─────────────────────────────────────────────────────────────


class FakeEntra:
    """Mints tokens and publishes a key set, like the real thing but local."""

    def __init__(self, kid: str = KID) -> None:
        self.kid = kid
        self.private_key = rsa.generate_private_key(public_exponent=65537,
                                                    key_size=2048)
        self.fetch_count = 0
        self.fail_next = False
        self.document = {"keys": [self._jwk(self.private_key, kid)]}

    @staticmethod
    def _jwk(private_key, kid: str, issuer: str | None = None) -> dict:
        """Publish a public key in JWKS form."""
        numbers = private_key.public_key().public_numbers()

        def b64(value: int) -> str:
            raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
            import base64
            return base64.urlsafe_b64encode(raw).decode().rstrip("=")

        entry = {"kty": "RSA", "kid": kid, "use": "sig",
                 "n": b64(numbers.n), "e": b64(numbers.e)}
        if issuer:
            entry["issuer"] = issuer
        return entry

    def rotate(self, new_kid: str) -> None:
        """Replace the signing key, as a real rotation would."""
        self.kid = new_kid
        self.private_key = rsa.generate_private_key(public_exponent=65537,
                                                    key_size=2048)
        self.document = {"keys": [self._jwk(self.private_key, new_kid)]}

    def publish_key_issuer(self, issuer_template: str) -> None:
        """Republish the current key carrying an ``issuer`` field."""
        self.document = {
            "keys": [self._jwk(self.private_key, self.kid, issuer_template)]
        }

    async def fetcher(self, _url: str) -> dict:
        """Stands in for the discovery endpoint."""
        self.fetch_count += 1
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("discovery endpoint unreachable")
        return self.document

    def token(self, *, alg: str = "RS256", key=None, kid: str | None = None,
              **overrides) -> str:
        """Mint a token, with any claim overridable to make it hostile."""
        now = int(time.time())
        claims = {
            "iss": ISSUER, "aud": CLIENT_ID, "tid": TENANT,
            "oid": "user-object-id-1", "preferred_username": "person@example.test",
            "name": "Test Person", "iat": now, "nbf": now, "exp": now + 3600,
            "scp": "access_as_user",
        }
        claims.update(overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        headers = {"kid": kid or self.kid}
        signing_key = key if key is not None else self.private_key
        if alg == "none":
            return pyjwt.encode(claims, key=None, algorithm=None, headers=headers)
        return pyjwt.encode(claims, signing_key, algorithm=alg, headers=headers)


def make_validator(entra: FakeEntra, **config_kwargs) -> ea.TokenValidator:
    """A validator wired to the fake tenant."""
    config = ea.AuthConfig(
        enabled=True, tenant_id=TENANT, client_id=CLIENT_ID, **config_kwargs
    )
    return ea.TokenValidator(config, fetcher=entra.fetcher)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── checks ───────────────────────────────────────────────────────────────────


def test_config() -> None:
    print("\nAuthConfig")
    cfg = ea.AuthConfig(enabled=True, tenant_id=TENANT, client_id=CLIENT_ID)
    check("valid config constructs", cfg.client_id == CLIENT_ID)
    check("audiences accept bare and api:// forms",
          cfg.audiences() == [CLIENT_ID, f"api://{CLIENT_ID}"])
    check("G5 extra audiences appended",
          ea.AuthConfig(enabled=True, tenant_id=TENANT, client_id=CLIENT_ID,
                        extra_audiences=("https://api.example.test",)
                        ).audiences()[-1] == "https://api.example.test")
    check("single tenant expects v2 and v1 issuers",
          cfg.expected_issuers() == (
              f"https://login.microsoftonline.com/{TENANT}/v2.0",
              f"https://sts.windows.net/{TENANT}/"))
    check("jwks url points at the tenant",
          cfg.jwks_url().endswith(f"/{TENANT}/discovery/v2.0/keys"))

    check("enabled without tenant rejected",
          raises(ValueError, ea.AuthConfig, enabled=True, tenant_id="",
                 client_id=CLIENT_ID) is not None)
    check("enabled without client id rejected",
          raises(ValueError, ea.AuthConfig, enabled=True, tenant_id=TENANT,
                 client_id="") is not None)
    check("non-GUID tenant rejected",
          raises(ValueError, ea.AuthConfig, enabled=True, tenant_id="not-a-guid",
                 client_id=CLIENT_ID) is not None)
    check("G3 empty required_claims rejected",
          raises(ValueError, ea.AuthConfig, enabled=True, tenant_id=TENANT,
                 client_id=CLIENT_ID, required_claims=()) is not None)
    check("disabled config needs no tenant",
          ea.AuthConfig(enabled=False).enabled is False)
    check("config is frozen",
          raises(Exception, setattr, cfg, "enabled", False) is not None)

    multi = ea.AuthConfig(enabled=True, tenant_id="common", client_id=CLIENT_ID)
    check("multi-tenant flagged", multi.multi_tenant is True)
    check("multi-tenant has no exact issuer", multi.expected_issuers() == ())
    check("multi-tenant warns about breadth",
          any("ANY Entra tenant" in w for w in multi.warnings()))

    disabled = ea.AuthConfig(enabled=False)
    check("G11 disabled auth warns loudly",
          any("DISABLED" in w for w in disabled.warnings()))
    check("G11 require_enabled raises when disabled",
          raises(RuntimeError, disabled.require_enabled) is not None)
    check("require_enabled passes when enabled", cfg.require_enabled() is None)

    check("client setup hides everything when disabled",
          disabled.client_setup() == {"useLogin": False})
    setup = cfg.client_setup()
    check("client setup names the authority",
          setup["authority"].endswith(TENANT))
    check("client setup carries no secret",
          not any("secret" in k.lower() for k in setup))


def test_config_from_env() -> None:
    print("\nAuthConfig.from_env")
    cfg = ea.AuthConfig.from_env({
        "AUTH_ENABLED": "true", "AUTH_TENANT_ID": TENANT,
        "AUTH_CLIENT_ID": CLIENT_ID,
        "AUTH_EXTRA_AUDIENCES": "https://a.example.test, https://b.example.test",
    })
    check("enabled parsed", cfg.enabled is True)
    check("extra audiences split", len(cfg.extra_audiences) == 2)

    for value in ("false", "0", "no", "", "TRUE_ISH", "yes please"):
        parsed = ea.AuthConfig.from_env({"AUTH_ENABLED": value})
        if parsed.enabled:
            check(f"fails closed on {value!r}", False)
            break
    else:
        check("unrecognised AUTH_ENABLED fails closed to disabled", True)

    for value in ("true", "True", "1", "yes", "on"):
        parsed = ea.AuthConfig.from_env({
            "AUTH_ENABLED": value, "AUTH_TENANT_ID": TENANT,
            "AUTH_CLIENT_ID": CLIENT_ID})
        if not parsed.enabled:
            check(f"accepts affirmative {value!r}", False)
            break
    else:
        check("every affirmative form enables auth", True)

    check("prefix override works",
          ea.AuthConfig.from_env({"API_ENABLED": "true", "API_TENANT_ID": TENANT,
                                  "API_CLIENT_ID": CLIENT_ID},
                                 prefix="API_").enabled is True)


def test_jwks_cache() -> None:
    print("\nJWKS cache")
    entra = FakeEntra()
    now = [1000.0]
    config = ea.AuthConfig(enabled=True, tenant_id=TENANT, client_id=CLIENT_ID)
    cache = ea.JWKSCache(config, fetcher=entra.fetcher, clock=lambda: now[0])

    key = asyncio.run(cache.get_key(KID))
    check("key fetched on first use", key["kid"] == KID)
    check("one fetch so far", entra.fetch_count == 1)

    asyncio.run(cache.get_key(KID))
    check("G1 second lookup does not refetch", entra.fetch_count == 1)

    now[0] += config.jwks_ttl_seconds + 1
    asyncio.run(cache.get_key(KID))
    check("expired cache refetches", entra.fetch_count == 2)

    # Rotation: a new key id forces one refresh.
    now[0] += 1
    entra.rotate("test-key-2")
    fetched = asyncio.run(cache.get_key("test-key-2"))
    check("rotation refresh finds the new key", fetched["kid"] == "test-key-2")
    check("rotation cost exactly one fetch", entra.fetch_count == 3)

    # G10: unknown ids must not each cost a fetch.
    before = entra.fetch_count
    for _ in range(20):
        try:
            asyncio.run(cache.get_key(f"unknown-{uuid.uuid4()}"))
        except ea.AuthError:
            pass
    check("G10 cooldown caps rotation refreshes under probing",
          entra.fetch_count - before <= 1,
          f"{entra.fetch_count - before} fetches for 20 unknown key ids")

    now[0] += config.jwks_refresh_cooldown_seconds + 1
    before = entra.fetch_count
    try:
        asyncio.run(cache.get_key("still-unknown"))
    except ea.AuthError:
        pass
    check("G10 cooldown expiry permits one more refresh",
          entra.fetch_count - before == 1)

    unknown = None
    try:
        asyncio.run(cache.get_key("nope"))
    except ea.AuthError as exc:
        unknown = exc
    check("unknown key id rejected", unknown is not None
          and unknown.reason == "unknown_kid")
    check("G2 key id is not echoed in the public message",
          unknown is not None and "nope" not in unknown.public_message)
    check("G2 key id is not echoed in the log fields",
          unknown is not None and "nope" not in str(unknown.log_fields()))
    check("key id length is recorded for operators",
          unknown is not None and unknown.log_fields().get("kid_len") == 4)

    # A fetch failure with a warm cache is survivable.
    fresh = FakeEntra()
    cache2 = ea.JWKSCache(config, fetcher=fresh.fetcher, clock=lambda: now[0])
    asyncio.run(cache2.get_key(KID))
    now[0] += config.jwks_ttl_seconds + 1
    fresh.fail_next = True
    served = asyncio.run(cache2.get_key(KID))
    check("stale keys served when discovery is down", served["kid"] == KID)

    # A fetch failure with a cold cache is not.
    cold = FakeEntra()
    cold.fail_next = True
    cache3 = ea.JWKSCache(config, fetcher=cold.fetcher, clock=lambda: now[0])
    check("cold cache plus outage reports unavailable",
          rejects("jwks_unavailable", cache3.get_key(KID)))

    unavailable = None
    try:
        asyncio.run(ea.JWKSCache(config, fetcher=_always_fail,
                                 clock=lambda: now[0]).get_key(KID))
    except ea.AuthError as exc:
        unavailable = exc
    check("key-service outage is 503, not 401",
          unavailable is not None and unavailable.status_code == 503)

    # Single flight: concurrent misses share one fetch.
    burst = FakeEntra()
    cache4 = ea.JWKSCache(config, fetcher=burst.fetcher, clock=lambda: now[0])

    async def concurrent():
        await asyncio.gather(*(cache4.get_key(KID) for _ in range(10)))

    asyncio.run(concurrent())
    check("concurrent first-use collapses to one fetch", burst.fetch_count == 1)


async def _always_fail(_url: str) -> dict:
    raise RuntimeError("down")


def _hs256_forgery(header: dict, claims: dict, secret: bytes) -> str:
    """Hand-craft an HMAC-signed JWT. PyJWT refuses to build this on purpose."""
    import base64
    import hashlib
    import hmac
    import json

    def segment(data: dict) -> bytes:
        raw = json.dumps(data, separators=(",", ":")).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=")

    signing_input = segment(header) + b"." + segment(claims)
    signature = hmac.new(secret, signing_input, hashlib.sha256).digest()
    return (signing_input + b"."
            + base64.urlsafe_b64encode(signature).rstrip(b"=")).decode()


def test_key_parsing() -> None:
    print("\nsigning key parsing")
    entra = FakeEntra()
    jwk = entra.document["keys"][0]
    pem = build_rsa_pem(jwk)
    check("PEM built from a JWKS entry", pem.startswith(b"-----BEGIN PUBLIC KEY"))
    check("non-RSA key type refused",
          raises(ea.AuthError, build_rsa_pem, {"kty": "EC", "kid": "x"}) is not None)
    check("malformed key entry refused",
          raises(ea.AuthError, build_rsa_pem, {"kty": "RSA", "kid": "x"}) is not None)


def test_valid_token() -> None:
    print("\nvalid tokens")
    entra = FakeEntra()
    validator = make_validator(entra)

    principal = asyncio.run(validator.authenticate(bearer(entra.token())))
    check("valid token authenticates", principal.id == "user-object-id-1")
    check("email extracted", principal.email == "person@example.test")
    check("name extracted", principal.name == "Test Person")
    check("tenant extracted", principal.tenant_id == TENANT)
    check("kind is user", principal.kind == ea.KIND_USER)
    check("scopes parsed", principal.has_scope("access_as_user"))
    check("principal is not a developer identity", principal.is_developer is False)
    check("log fields omit the email",
          "email" not in str(principal.log_fields()).lower())

    api_audience = asyncio.run(
        validator.authenticate(bearer(entra.token(aud=f"api://{CLIENT_ID}"))))
    check("G5 api:// audience accepted", api_audience.id == "user-object-id-1")

    v1_issuer = asyncio.run(validator.authenticate(
        bearer(entra.token(iss=f"https://sts.windows.net/{TENANT}/"))))
    check("v1 issuer form accepted", v1_issuer.id == "user-object-id-1")

    lower = asyncio.run(validator.authenticate(
        {"authorization": f"Bearer {entra.token()}"}))
    check("G8 header lookup is case-insensitive", lower.id == "user-object-id-1")

    # An app-only token carries oid too — Entra issues one for a service
    # principal exactly as it does for a user — so the required-claim rule is
    # not what separates them, and nothing here relaxes it.
    app_principal = asyncio.run(validator.authenticate(bearer(entra.token(
        oid="service-principal-oid-1", sub="service-principal-1", idtyp="app",
        scp=None, preferred_username=None, roles=["Records.ReadWrite.All"]))))
    check("service principal identified by oid",
          app_principal.id == "service-principal-oid-1")
    check("service principal marked as service", app_principal.is_service is True)
    check("idtyp makes the classification certain",
          app_principal.kind_certain is True)
    check("app-only token carries no delegated scope",
          app_principal.scopes == ())
    check("app role parsed", app_principal.has_role("Records.ReadWrite.All"))


def test_claim_contract() -> None:
    """The five rows of the supported user/service contract, exactly.

    The premise this replaces — that an app-only token has no ``oid`` — is
    wrong. Microsoft's access-token claims reference states ``oid`` identifies
    the object in the directory, user *or* service principal, and that ``idtyp``
    is an optional claim. Guessing from ``oid`` therefore mislabels every
    service principal as a human.
    """
    print("\nclaim contract (user vs service)")

    def classify(**claims) -> ea.Principal:
        base = {"oid": "object-id", "tid": TENANT}
        base.update(claims)
        return ea.principal_from_claims(
            {k: v for k, v in base.items() if v is not None})

    stated_app = classify(idtyp="app", roles=["Reader"])
    check("idtyp=app is a service principal", stated_app.kind == ea.KIND_SERVICE)
    check("a stated kind is certain", stated_app.kind_certain is True)
    check("idtyp casing is normalised",
          classify(idtyp="App").kind == ea.KIND_SERVICE)

    stated_user = classify(idtyp="user", roles=["Reader"])
    check("idtyp=user is a user", stated_user.kind == ea.KIND_USER)
    check("idtyp beats every inference", stated_user.kind_certain is True)
    check("idtyp=user wins over an absent scp",
          classify(idtyp="user", scp=None).kind == ea.KIND_USER)

    delegated = classify(scp="access_as_user")
    check("a delegated scope means a human consented",
          delegated.kind == ea.KIND_USER)
    check("delegated classification is certain", delegated.kind_certain is True)
    check("a user may also hold app roles",
          classify(scp="access_as_user", roles=["Reader"]).kind == ea.KIND_USER)

    roles_only = classify(roles=["Records.ReadWrite.All"])
    check("roles without scp reads as a service principal",
          roles_only.kind == ea.KIND_SERVICE)
    check("but the reading is not certain", roles_only.kind_certain is False)

    bare = classify()
    check("a token stating neither defaults to user", bare.kind == ea.KIND_USER)
    check("and says so", bare.kind_certain is False)

    check("oid presence is never the signal",
          classify(oid="object-id", idtyp="app").kind == ea.KIND_SERVICE)
    check("oid absence is never the signal",
          classify(oid=None, sub="s", scp="access_as_user").kind == ea.KIND_USER)
    check("certainty is reported to operators",
          roles_only.log_fields()["principal_kind_certain"] is False)
    check("a developer identity is certain",
          ea.developer_principal().kind_certain is True)


def test_hostile_tokens() -> None:
    print("\nhostile tokens")
    entra = FakeEntra()
    validator = make_validator(entra)

    check("no Authorization header rejected",
          rejects("missing_header", validator.authenticate({})))
    check("wrong scheme rejected",
          rejects("missing_header", validator.authenticate({"Authorization": "Basic abc"})))
    check("empty bearer rejected",
          rejects("empty_token", validator.authenticate({"Authorization": "Bearer "})))
    check("garbage token rejected",
          rejects("malformed", validator.authenticate(bearer("not-a-jwt"))))
    check("oversized token rejected before parsing",
          rejects("malformed", validator.authenticate(bearer("x" * 20000))))

    check("alg=none rejected",
          rejects("bad_algorithm", validator.authenticate(bearer(entra.token(alg="none")))))

    # HS256 confusion: sign with the PUBLIC key as an HMAC secret. A verifier
    # that lets the token choose the algorithm accepts this, because the "secret"
    # is published. PyJWT refuses to *mint* it, so it is crafted by hand — which
    # is exactly what an attacker does.
    public_pem = build_rsa_pem(entra.document["keys"][0])
    forged = _hs256_forgery(
        {"kid": KID, "alg": "HS256", "typ": "JWT"},
        {"iss": ISSUER, "aud": CLIENT_ID, "tid": TENANT,
         "oid": "attacker", "exp": int(time.time()) + 3600},
        public_pem,
    )
    check("HS256 confusion rejected",
          rejects("bad_algorithm", validator.authenticate(bearer(forged))))

    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    check("signature from a foreign key rejected",
          rejects("bad_signature",
                  validator.authenticate(bearer(entra.token(key=other_key)))))

    now = int(time.time())
    check("expired token rejected",
          rejects("expired", validator.authenticate(
              bearer(entra.token(exp=now - 60, iat=now - 3600, nbf=now - 3600)))))
    check("token with no expiry rejected",
          rejects("missing_claim", validator.authenticate(bearer(entra.token(exp=None)))))
    check("not-yet-valid token rejected",
          rejects("not_yet_valid", validator.authenticate(
              bearer(entra.token(nbf=now + 600, iat=now + 600)))))
    check("G9 small clock skew tolerated",
          asyncio.run(validator.authenticate(
              bearer(entra.token(nbf=now + 5, iat=now + 5)))).id == "user-object-id-1")

    check("wrong audience rejected",
          rejects("bad_audience", validator.authenticate(
              bearer(entra.token(aud="some-other-app")))))
    check("foreign issuer rejected",
          rejects("bad_issuer", validator.authenticate(bearer(entra.token(
              iss=f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0")))))
    check("non-Entra issuer rejected",
          rejects("bad_issuer", validator.authenticate(
              bearer(entra.token(iss="https://evil.example.test/")))))
    check("G3 token without oid rejected",
          rejects("missing_claim", validator.authenticate(
              bearer(entra.token(oid=None)))))
    check("G3 token with empty oid rejected",
          rejects("missing_claim", validator.authenticate(
              bearer(entra.token(oid="")))))
    check("unknown signing key rejected",
          rejects("unknown_kid", validator.authenticate(
              bearer(entra.token(kid="no-such-key")))))


def test_error_disclosure() -> None:
    print("\nerror disclosure (G2)")
    entra = FakeEntra()
    validator = make_validator(entra)

    hostile_kid = "abc\n2026-01-01 CRITICAL forged log line \x1b[31m<script>"
    captured = None
    try:
        asyncio.run(validator.authenticate(bearer(entra.token(kid=hostile_kid))))
    except ea.AuthError as exc:
        captured = exc

    check("hostile key id rejected", captured is not None)
    message = captured.public_message if captured else ""
    check("no newline reaches the caller", "\n" not in message)
    check("no ANSI escape reaches the caller", "\x1b" not in message)
    check("no markup reaches the caller", "<script>" not in message)
    check("public message is the constant for its reason", message == "Invalid token")
    check("public message never contains the input",
          "abc" not in message)

    fields = captured.log_fields() if captured else {}
    check("log records the length, not the value",
          fields.get("kid_len") == len(hostile_kid) and hostile_kid not in str(fields))

    # Distinct internal reasons must not become distinct public messages.
    reasons = ["malformed", "unknown_kid", "bad_signature", "bad_algorithm"]
    messages = {ea.AuthError(r).public_message for r in reasons}
    check("forgery attempts are indistinguishable to the caller",
          len(messages) == 1, f"{messages}")
    check("expiry is distinguishable, because it is actionable",
          ea.AuthError("expired").public_message == "Token expired")
    check("credential failures are 401",
          ea.AuthError("bad_signature").status_code == 401)
    check("dependency failures are 503",
          ea.AuthError("jwks_unavailable").status_code == 503)


def test_multi_tenant() -> None:
    print("\nmulti-tenant")
    entra = FakeEntra()
    validator = ea.TokenValidator(
        ea.AuthConfig(enabled=True, tenant_id="common", client_id=CLIENT_ID),
        fetcher=entra.fetcher)

    foreign_issuer = f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0"
    principal = asyncio.run(validator.authenticate(
        bearer(entra.token(iss=foreign_issuer, tid=OTHER_TENANT))))
    check("any Entra tenant accepted", principal.tenant_id == OTHER_TENANT)
    check("non-Entra issuer still rejected",
          rejects("bad_issuer", validator.authenticate(
              bearer(entra.token(iss="https://accounts.example.test/x/v2.0")))))
    check("issuer without a tenant GUID rejected",
          rejects("bad_issuer", validator.authenticate(bearer(entra.token(
              iss="https://login.microsoftonline.com/not-a-guid/v2.0")))))

    # G6: the key's own issuer must agree with the token's.
    entra.publish_key_issuer("https://login.microsoftonline.com/{tenantid}/v2.0")
    validator.jwks.clear()
    ok = asyncio.run(validator.authenticate(
        bearer(entra.token(iss=foreign_issuer, tid=OTHER_TENANT))))
    check("templated key issuer matches its own tenant", ok.tenant_id == OTHER_TENANT)

    entra.publish_key_issuer(
        f"https://login.microsoftonline.com/{TENANT}/v2.0")
    validator.jwks.clear()
    check("G6 key scoped to another tenant rejected",
          rejects("key_issuer_mismatch", validator.authenticate(
              bearer(entra.token(iss=foreign_issuer, tid=OTHER_TENANT)))))


def test_developer_mode() -> None:
    print("\ndisabled-auth mode")
    validator = ea.TokenValidator(ea.AuthConfig(enabled=False))

    principal = asyncio.run(validator.authenticate({}))
    check("no token required when disabled", principal.id == "anonymous")
    check("G12 identity is marked developer, not user",
          principal.kind == ea.KIND_DEVELOPER)
    check("developer identity is self-declared", principal.is_developer is True)

    spoofed = asyncio.run(validator.authenticate(
        {}, dev_identity={"X-User-Id": "tab-2", "X-User-Name": "Second Tab"}))
    check("per-caller dev identity honoured", spoofed.id == "tab-2")
    check("dev display name honoured", spoofed.name == "Second Tab")

    off = ea.TokenValidator(ea.AuthConfig(enabled=False, dev_identity_headers=False))
    check("dev headers can be switched off",
          asyncio.run(off.authenticate({}, dev_identity={"X-User-Id": "x"})).id
          == "anonymous")

    # The property that matters: the dev path is unreachable when enabled.
    entra = FakeEntra()
    enforced = make_validator(entra)
    check("G12 dev headers are ignored when auth is enabled",
          rejects("missing_header", enforced.authenticate(
              {}, dev_identity={"X-User-Id": "attacker"})))
    check("G12 dev headers cannot accompany a real token to change identity",
          asyncio.run(enforced.authenticate(
              {**bearer(entra.token()), "X-User-Id": "attacker"})).id
          == "user-object-id-1")


def test_ownership() -> None:
    print("\nownership")
    owner = ea.Principal(id="user-1")
    other = ea.Principal(id="user-2")
    policy = ea.OwnershipPolicy()

    check("owner may read", policy.can_read("user-1", owner) is True)
    check("owner may write", policy.can_write("user-1", owner) is True)
    check("stranger may not read", policy.can_read("user-1", other) is False)
    check("stranger may not write", policy.can_write("user-1", other) is False)
    check("shared template is readable",
          policy.can_read(ea.DEFAULT_SHARED_OWNER, other) is True)
    check("shared template is not writable",
          policy.can_write(ea.DEFAULT_SHARED_OWNER, other) is False)
    check("unowned record is not readable by default",
          policy.can_read("", other) is False)
    check("unowned read can be opted into",
          ea.OwnershipPolicy(allow_unowned_read=True).can_read("", other) is True)
    check("unowned record is never writable",
          ea.OwnershipPolicy(allow_unowned_read=True).can_write("", other) is False)

    check("owner read passes", policy.assert_readable("user-1", owner, "r1") is None)
    denied = raises(ea.NotFoundError, policy.assert_readable, "user-1", other, "r1")
    check("G4 stranger read raises NotFound, not Forbidden", denied is not None)
    check("G4 status is 404", denied is not None and denied.status_code == 404)
    check("G4 response body does not confirm existence",
          denied is not None and denied.public_message == "Not found")
    check("G4 the log keeps what the caller is not told",
          denied is not None and denied.log_fields().get("owner_id") == "user-1")

    stranger_write = raises(ea.NotFoundError, policy.assert_writable,
                            "user-1", other, "delete", "r1")
    check("G4 stranger write is also 404", stranger_write is not None)

    shared_write = raises(ea.ForbiddenError, policy.assert_writable,
                          ea.DEFAULT_SHARED_OWNER, other, "patch", "r1")
    check("shared template write raises Forbidden", shared_write is not None)
    check("shared template write is 403, since it is already readable",
          shared_write is not None and shared_write.status_code == 403)
    check("owner write passes",
          policy.assert_writable("user-1", owner, "patch", "r1") is None)

    # Ownership must hold in dev mode too, or per-caller isolation is untested.
    dev_a = ea.developer_principal("tab-1")
    dev_b = ea.developer_principal("tab-2")
    check("G7 ownership still separates development identities",
          policy.can_read("tab-1", dev_a) and not policy.can_read("tab-1", dev_b))

    custom = ea.OwnershipPolicy(shared_owner_ids=("__demo__", "__sample__"))
    check("shared ids are configurable",
          custom.can_read("__sample__", other) and not custom.can_read("__default__", other))


def test_fastapi_adapter() -> None:
    print("\nFastAPI adapter")
    try:
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient
    except ImportError:
        check("FastAPI adapter (skipped — framework not installed)", True)
        return

    entra = FakeEntra()
    config = ea.AuthConfig(enabled=True, tenant_id=TENANT, client_id=CLIENT_ID)
    app = FastAPI()
    validator = ea.install_auth(app, config, fetcher=entra.fetcher)
    current = ea.principal_dependency(validator)

    @app.get("/api/me")
    async def me(principal: ea.Principal = Depends(current)) -> dict:
        return {"id": principal.id, "kind": principal.kind}

    @app.get("/api/records/{record_id}")
    async def record(record_id: str,
                     principal: ea.Principal = Depends(current)) -> dict:
        # Every record here belongs to someone else, on purpose.
        ea.DEFAULT_POLICY.assert_readable("someone-else", principal, record_id)
        return {"id": record_id}

    client = TestClient(app, raise_server_exceptions=False)

    unauth = client.get("/api/me")
    check("unauthenticated request is 401", unauth.status_code == 401)
    check("401 names the scheme, per RFC 6750",
          unauth.headers.get("WWW-Authenticate") == "Bearer")
    check("401 body carries a reason code",
          unauth.json().get("error") == "missing_header")
    check("401 body carries no token detail",
          "token" not in unauth.json().get("message", "").lower()
          or unauth.json()["message"] == "Missing or malformed Authorization header")

    good = client.get("/api/me", headers=bearer(entra.token()))
    check("valid token reaches the route", good.status_code == 200)
    check("route receives an identity", good.json()["id"] == "user-object-id-1")

    forged = client.get("/api/me", headers=bearer("garbage"))
    check("forged token is 401", forged.status_code == 401)

    denied = client.get("/api/records/r1", headers=bearer(entra.token()))
    check("G4 another user's record is 404 through the API",
          denied.status_code == 404)

    setup = client.get("/api/auth_setup")
    check("auth setup is reachable without a token", setup.status_code == 200)
    check("auth setup advertises login", setup.json()["useLogin"] is True)
    check("auth setup leaks no secret",
          "secret" not in setup.text.lower())

    # The composition seam: another mechanism authenticated the request first.
    handed_off = FastAPI()
    ho_validator = ea.install_auth(handed_off, config, fetcher=entra.fetcher,
                                   setup_path=None)
    ho_current = ea.principal_dependency(ho_validator)

    @handed_off.middleware("http")
    async def preauth(request, call_next):
        if request.headers.get("X-Pretend-Signed") == "yes":
            request.scope[ea.DEFAULT_SCOPE_KEY] = ea.Principal(
                id="signed-agent", kind=ea.KIND_SERVICE)
        return await call_next(request)

    @handed_off.get("/api/me")
    async def ho_me(principal: ea.Principal = Depends(ho_current)) -> dict:
        return {"id": principal.id, "kind": principal.kind}

    ho_client = TestClient(handed_off, raise_server_exceptions=False)
    handed = ho_client.get("/api/me", headers={"X-Pretend-Signed": "yes"})
    check("a prior mechanism's principal is honoured", handed.status_code == 200)
    check("handed-off identity is preserved", handed.json()["id"] == "signed-agent")
    check("without the hand-off the same request is still rejected",
          ho_client.get("/api/me").status_code == 401)
    check("setup endpoint can be suppressed",
          ho_client.get("/api/auth_setup").status_code == 404)

    # Disabled mode through the full stack.
    dev_app = FastAPI()
    dev_validator = ea.install_auth(dev_app, ea.AuthConfig(enabled=False))
    dev_current = ea.principal_dependency(dev_validator)

    @dev_app.get("/api/me")
    async def dev_me(principal: ea.Principal = Depends(dev_current)) -> dict:
        return {"id": principal.id, "kind": principal.kind}

    dev_client = TestClient(dev_app)
    anon = dev_client.get("/api/me")
    check("disabled mode serves without a token", anon.status_code == 200)
    check("G12 disabled mode identity is marked developer",
          anon.json()["kind"] == ea.KIND_DEVELOPER)
    check("disabled mode honours the caller header",
          dev_client.get("/api/me", headers={"X-User-Id": "tab-9"}).json()["id"]
          == "tab-9")
    check("disabled mode hides login config",
          dev_client.get("/api/auth_setup").json() == {"useLogin": False})


def test_scope_and_role_guards() -> None:
    print("\nscope and role guards")
    holder = ea.Principal(id="u1", scopes=("access_as_user",), roles=("Reader",))
    check("granted scope passes", ea.require_scope("access_as_user")(holder) is holder)
    check("missing scope raises Forbidden",
          raises(ea.ForbiddenError, ea.require_scope("admin"), holder) is not None)
    check("assigned role passes", ea.require_role("Reader")(holder) is holder)
    check("missing role raises Forbidden",
          raises(ea.ForbiddenError, ea.require_role("Writer"), holder) is not None)
    forbidden = raises(ea.ForbiddenError, ea.require_role("Writer"), holder)
    check("forbidden is 403, not 401",
          forbidden is not None and forbidden.status_code == 403)
    check("forbidden tells the caller nothing specific",
          forbidden is not None and forbidden.public_message == "Forbidden")


def main() -> int:
    print("entra-api-auth selftest")
    test_config()
    test_config_from_env()
    test_jwks_cache()
    test_key_parsing()
    test_valid_token()
    test_claim_contract()
    test_hostile_tokens()
    test_error_disclosure()
    test_multi_tenant()
    test_developer_mode()
    test_ownership()
    test_fastapi_adapter()
    test_scope_and_role_guards()

    print(f"\n{_PASS} passed, {_FAIL} failed")
    if _FAIL:
        print("SELFTEST FAILED")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
