"""The Entra component, exercised offline against keys minted here.

No tenant, no network, no Azure identity. The fetcher is injected and the signing keys are
generated in-process, which is what lets the hostile cases be tested at all: ``alg: none``,
HS256 confusion using the published public key, a foreign signing key, a foreign tenant, and
tokens whose time claims are wrong in each direction.

Every rejection is asserted by *reason code*, never by message, because the messages are
constants chosen for the wire and the reasons are what the code decides.
"""

from __future__ import annotations

import asyncio
import base64
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import jwt as pyjwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat

from entra_auth import (
    AuthError,
    EntraAuthConfig,
    EntraConfigurationError,
    InProcessRecordStore,
    JWKSCache,
    RecordStoreUnavailable,
    SessionService,
    TokenValidator,
    authorize_url,
    build_rsa_pem,
    constant_time_equals,
    logout_url,
    new_flow,
    new_session_id,
    session_lookup_key,
)

TENANT = "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7"
OTHER_TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT = "b1fa8094-e820-4d5b-8552-4dbf64fb70d0"
KID = "test-key-1"


def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class Signer:
    """One RSA keypair, plus the JWKS document that publishes its public half."""

    def __init__(self, kid: str = KID, issuer_template: str | None = None) -> None:
        self.kid = kid
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.issuer_template = issuer_template

    @property
    def private_pem(self) -> bytes:
        return self.key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )

    @property
    def public_pem(self) -> bytes:
        return self.key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)

    def jwk(self) -> dict:
        numbers = self.key.public_key().public_numbers()
        entry = {
            "kty": "RSA",
            "kid": self.kid,
            "use": "sig",
            "n": _b64u(numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")),
            "e": _b64u(numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")),
        }
        if self.issuer_template:
            entry["issuer"] = self.issuer_template
        return entry

    def document(self) -> dict:
        return {"keys": [self.jwk()]}

    def mint(self, **overrides) -> str:
        now = int(time.time())
        claims = {
            "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
            "aud": CLIENT,
            "tid": TENANT,
            "oid": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "sub": "subject-value",
            "scp": "access_as_user",
            "name": "Test Analyst",
            "preferred_username": "analyst@example.test",
            "iat": now,
            "nbf": now,
            "exp": now + 900,
        }
        claims.update(overrides)
        for key in [k for k, v in claims.items() if v is None]:
            del claims[key]
        return pyjwt.encode(claims, self.private_pem, algorithm="RS256", headers={"kid": self.kid})


def config(**overrides) -> EntraAuthConfig:
    values = {"tenant_id": TENANT, "client_id": CLIENT}
    values.update(overrides)
    return EntraAuthConfig(**values)


def validator_for(signer: Signer, cfg: EntraAuthConfig | None = None, *, calls: list | None = None):
    async def fetch(url: str) -> dict:
        if calls is not None:
            calls.append(url)
        return signer.document()

    return TokenValidator(cfg or config(), fetcher=fetch)


def run(coro):
    return asyncio.run(coro)


def reason_of(callable_):
    try:
        run(callable_())
    except AuthError as exc:
        return exc.reason
    raise AssertionError("expected the token to be refused")


# ── configuration is the trust boundary ────────────────────────────────────────

@pytest.mark.parametrize("tenant", ["common", "organizations", "consumers", "COMMON"])
def test_multi_tenant_values_are_refused(tenant):
    with pytest.raises(EntraConfigurationError) as caught:
        config(tenant_id=tenant)
    assert "single-tenant" in str(caught.value)


@pytest.mark.parametrize("tenant", ["", "not-a-guid", "contoso.onmicrosoft.com", TENANT[:-1]])
def test_tenant_must_be_a_guid(tenant):
    with pytest.raises(EntraConfigurationError):
        config(tenant_id=tenant)


def test_client_must_be_a_guid():
    with pytest.raises(EntraConfigurationError):
        config(client_id="cybereye")


def test_there_is_no_enabled_flag():
    # The upstream box carried one, and with it a disabled mode that granted a header-declared
    # identity. Nothing here can express that state.
    assert not hasattr(EntraAuthConfig, "enabled")
    assert "enabled" not in EntraAuthConfig.__dataclass_fields__


def test_empty_required_claims_is_refused():
    with pytest.raises(EntraConfigurationError):
        config(required_claims=())


def test_service_principals_need_a_role_before_they_can_be_allowed():
    with pytest.raises(EntraConfigurationError):
        config(allow_service_principals=True)
    assert config(allow_service_principals=True, required_roles=("Reader",)).allow_service_principals


def test_leeway_is_bounded():
    with pytest.raises(EntraConfigurationError):
        config(leeway_seconds=-1)
    with pytest.raises(EntraConfigurationError):
        config(leeway_seconds=3600)


def test_max_stale_cannot_be_shorter_than_the_ttl():
    with pytest.raises(EntraConfigurationError):
        config(jwks_ttl_seconds=3600, jwks_max_stale_seconds=60)


def test_both_audience_forms_are_accepted():
    assert config().audiences() == (CLIENT, f"api://{CLIENT}")


def test_jwks_url_is_derived_from_configuration_only():
    url = config().jwks_url()
    assert url == f"https://login.microsoftonline.com/{TENANT}/discovery/v2.0/keys"
    assert TENANT in url


def test_public_client_setup_carries_no_secret():
    setup = config().public_client_setup()
    serialised = json.dumps(setup).lower()
    for forbidden in ("secret", "password", "key", "credential", "thumbprint"):
        assert forbidden not in serialised


# ── the happy path ─────────────────────────────────────────────────────────────

def test_a_correct_token_is_accepted():
    signer = Signer()
    verified = run(validator_for(signer).validate_token(signer.mint()))
    assert verified.tenant_id == TENANT
    assert verified.object_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert verified.kind == "user"
    assert verified.scopes == ("access_as_user",)
    assert verified.expires_at > time.time()


def test_the_api_audience_form_is_accepted_too():
    signer = Signer()
    verified = run(validator_for(signer).validate_token(signer.mint(aud=f"api://{CLIENT}")))
    assert verified.object_id


def test_the_v1_issuer_form_is_accepted():
    signer = Signer()
    token = signer.mint(iss=f"https://sts.windows.net/{TENANT}/")
    assert run(validator_for(signer).validate_token(token)).object_id


# ── hostile tokens ─────────────────────────────────────────────────────────────

def test_alg_none_is_refused():
    signer = Signer()
    header = _b64u(json.dumps({"alg": "none", "typ": "JWT", "kid": KID}).encode())
    payload = _b64u(json.dumps({"aud": CLIENT, "tid": TENANT, "oid": "x", "exp": int(time.time()) + 60}).encode())
    token = f"{header}.{payload}."
    assert reason_of(lambda: validator_for(signer).validate_token(token)) == "bad_algorithm"


def test_hs256_confusion_with_the_published_public_key_is_refused():
    # Built by hand: PyJWT refuses to *encode* with a PEM as an HMAC secret, which is a
    # defence in the signing library and says nothing about what this verifier accepts. The
    # attack is a token an attacker constructs without PyJWT, so the test constructs one too.
    import hashlib
    import hmac

    signer = Signer()
    secret = signer.public_pem
    header = _b64u(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    now = int(time.time())
    payload = _b64u(json.dumps({
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENT,
        "tid": TENANT, "oid": "x", "scp": "access_as_user", "iat": now, "exp": now + 900,
    }).encode())
    signing_input = f"{header}.{payload}".encode("ascii")
    signature = _b64u(hmac.new(secret, signing_input, hashlib.sha256).digest())
    forged = f"{header}.{payload}.{signature}"
    assert reason_of(lambda: validator_for(signer).validate_token(forged)) == "bad_algorithm"


def test_a_foreign_signing_key_is_refused():
    published, attacker = Signer(), Signer()
    token = attacker.mint()
    assert reason_of(lambda: validator_for(published).validate_token(token)) == "bad_signature"


def test_a_foreign_tenant_is_refused_even_with_a_valid_signature():
    signer = Signer()
    token = signer.mint(
        iss=f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0", tid=OTHER_TENANT
    )
    assert reason_of(lambda: validator_for(signer).validate_token(token)) == "bad_issuer"


def test_a_tenant_claim_that_disagrees_with_the_issuer_is_refused():
    signer = Signer()
    assert reason_of(lambda: validator_for(signer).validate_token(signer.mint(tid=OTHER_TENANT))) == "bad_tenant"


def test_a_signing_key_scoped_to_another_tenant_is_refused():
    signer = Signer(issuer_template=f"https://login.microsoftonline.com/{OTHER_TENANT}/v2.0")
    assert reason_of(lambda: validator_for(signer).validate_token(signer.mint())) == "key_issuer_mismatch"


def test_a_wrong_audience_is_refused():
    signer = Signer()
    assert reason_of(lambda: validator_for(signer).validate_token(signer.mint(aud="api://someone-else"))) == "bad_audience"


def test_an_expired_token_is_refused():
    signer = Signer()
    now = int(time.time())
    token = signer.mint(iat=now - 7200, nbf=now - 7200, exp=now - 3600)
    assert reason_of(lambda: validator_for(signer).validate_token(token)) == "expired"


def test_a_token_that_is_not_yet_valid_is_refused():
    signer = Signer()
    now = int(time.time())
    token = signer.mint(iat=now + 3600, nbf=now + 3600, exp=now + 7200)
    assert reason_of(lambda: validator_for(signer).validate_token(token)) == "not_yet_valid"


def test_a_token_with_no_issuance_time_is_refused():
    signer = Signer()
    assert reason_of(lambda: validator_for(signer).validate_token(signer.mint(iat=None))) == "missing_claim"


def test_a_token_with_no_object_id_is_refused():
    signer = Signer()
    assert reason_of(lambda: validator_for(signer).validate_token(signer.mint(oid=None))) == "missing_claim"


def test_a_token_with_no_accepted_scope_is_refused():
    signer = Signer()
    assert reason_of(lambda: validator_for(signer).validate_token(signer.mint(scp="User.Read"))) == "missing_scope"


def test_a_token_with_no_scope_at_all_is_refused():
    signer = Signer()
    assert reason_of(lambda: validator_for(signer).validate_token(signer.mint(scp=None))) in {
        "missing_scope", "service_principal_refused"
    }


def test_an_unknown_key_id_is_refused():
    signer = Signer()
    token = pyjwt.encode(
        {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENT, "tid": TENANT,
         "oid": "x", "scp": "access_as_user", "iat": int(time.time()), "exp": int(time.time()) + 900},
        signer.private_pem, algorithm="RS256", headers={"kid": "some-other-key"},
    )
    assert reason_of(lambda: validator_for(signer).validate_token(token)) == "unknown_kid"


def test_an_oversized_token_is_refused_before_parsing():
    signer = Signer()
    assert reason_of(lambda: validator_for(signer).validate_token("a" * 20000)) == "oversized"


@pytest.mark.parametrize("token", ["", "   ", "not.a.jwt", "a.b", "..", "\x00\x01"])
def test_malformed_tokens_are_refused(token):
    signer = Signer()
    assert reason_of(lambda: validator_for(signer).validate_token(token)) in {
        "empty_token", "malformed", "bad_algorithm",
    }


# ── service principals are a decision, not an accident ────────────────────────

def test_a_service_principal_token_is_refused_by_default():
    signer = Signer()
    token = signer.mint(idtyp="app", scp=None, preferred_username=None, roles=["Reader"])
    assert reason_of(lambda: validator_for(signer).validate_token(token)) == "service_principal_refused"


def test_requiring_oid_does_not_filter_service_principals():
    # The documented "a service principal has no oid" rule is false for v2 tokens: the token
    # carries the service principal's own object id, so the oid requirement passes and only
    # the caller-kind policy stops it.
    signer = Signer()
    token = signer.mint(idtyp="app", scp=None, preferred_username=None, roles=["Reader"])
    claims = pyjwt.decode(token, options={"verify_signature": False})
    assert claims["oid"]
    assert reason_of(lambda: validator_for(signer).validate_token(token)) != "missing_claim"


def test_an_allowed_service_principal_still_needs_the_role():
    signer = Signer()
    cfg = config(allow_service_principals=True, required_roles=("Ingestor",), required_scopes=())
    token = signer.mint(idtyp="app", scp=None, preferred_username=None, roles=["Reader"])
    assert reason_of(lambda: validator_for(signer, cfg).validate_token(token)) == "missing_scope"


def test_an_allowed_service_principal_with_the_role_is_accepted():
    signer = Signer()
    cfg = config(allow_service_principals=True, required_roles=("Ingestor",), required_scopes=())
    token = signer.mint(idtyp="app", scp=None, preferred_username=None, roles=["Ingestor"])
    verified = run(validator_for(signer, cfg).validate_token(token))
    assert verified.is_service and verified.roles == ("Ingestor",)


# ── nothing from the token reaches a message ──────────────────────────────────

@pytest.mark.parametrize("hostile", [
    "\n\nFAKE LOG LINE",
    "\x1b[2J\x1b[H",
    "<script>alert(1)</script>",
    "A" * 4096,
])
def test_a_hostile_key_id_never_reaches_a_message(hostile):
    signer = Signer()
    token = pyjwt.encode(
        {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENT, "tid": TENANT,
         "oid": "x", "scp": "access_as_user", "iat": int(time.time()), "exp": int(time.time()) + 900},
        signer.private_pem, algorithm="RS256", headers={"kid": hostile},
    )
    try:
        run(validator_for(signer).validate_token(token))
    except AuthError as exc:
        assert hostile not in exc.public_message
        assert hostile not in str(exc)
        assert hostile not in json.dumps(exc.log_fields())
        assert exc.log_fields().get("kid_len") == len(hostile)
    else:
        raise AssertionError("expected refusal")


def test_public_messages_are_selected_not_built():
    assert AuthError("bad_audience", "aud was api://evil.example").public_message == (
        "the token is not accepted here"
    )
    assert "evil" not in AuthError("bad_audience", "aud was api://evil.example").public_message


def test_an_unknown_reason_degrades_rather_than_raising():
    assert AuthError("no_such_reason").public_message == "the token was refused"


# ── the key set ───────────────────────────────────────────────────────────────

def test_the_key_set_is_fetched_once_for_many_tokens():
    signer, calls = Signer(), []
    validator = validator_for(signer, calls=calls)

    async def drive():
        for _ in range(5):
            await validator.validate_token(signer.mint())

    run(drive())
    assert len(calls) == 1


def test_a_burst_of_unknown_key_ids_buys_one_refresh():
    signer, calls = Signer(), []
    validator = validator_for(signer, calls=calls)

    async def drive():
        await validator.validate_token(signer.mint())
        for index in range(12):
            token = pyjwt.encode(
                {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENT,
                 "tid": TENANT, "oid": "x", "scp": "access_as_user",
                 "iat": int(time.time()), "exp": int(time.time()) + 900},
                signer.private_pem, algorithm="RS256", headers={"kid": f"invented-{index}"},
            )
            try:
                await validator.validate_token(token)
            except AuthError:
                pass

    run(drive())
    # One scheduled fetch, then one rotation fetch. The cooldown absorbs the other eleven.
    assert len(calls) == 2


def test_a_key_set_past_the_stale_ceiling_fails_closed():
    signer = Signer()
    ticks = {"now": 0.0}
    attempts = {"count": 0}

    async def fetch(_url):
        attempts["count"] += 1
        if attempts["count"] == 1:
            return signer.document()
        raise RuntimeError("discovery endpoint is down")

    cfg = config(jwks_ttl_seconds=60, jwks_max_stale_seconds=120)
    cache = JWKSCache(cfg, fetcher=fetch, clock=lambda: ticks["now"])
    validator = TokenValidator(cfg, jwks_cache=cache)

    async def drive():
        await validator.validate_token(signer.mint())
        ticks["now"] = 90.0  # expired, but inside the stale window: still served
        await validator.validate_token(signer.mint())
        ticks["now"] = 500.0  # past the ceiling
        return await validator.validate_token(signer.mint())

    with pytest.raises(AuthError) as caught:
        run(drive())
    assert caught.value.reason == "jwks_stale"


def test_an_unreachable_key_set_with_nothing_cached_is_refused():
    async def fetch(_url):
        raise RuntimeError("no network")

    validator = TokenValidator(config(), fetcher=fetch)
    assert reason_of(lambda: validator.validate_token("a.b.c")) in {"malformed", "jwks_unavailable"}


def test_concurrent_first_requests_produce_one_fetch():
    signer, calls = Signer(), []

    async def fetch(url):
        calls.append(url)
        await asyncio.sleep(0.01)
        return signer.document()

    validator = TokenValidator(config(), fetcher=fetch)

    async def drive():
        await asyncio.gather(*[validator.validate_token(signer.mint()) for _ in range(8)])

    run(drive())
    assert len(calls) == 1


def test_a_non_https_discovery_url_is_refused():
    from entra_auth._jwks import _http_get_json

    with pytest.raises(AuthError) as caught:
        _http_get_json("http://login.microsoftonline.com/keys")
    assert caught.value.reason == "jwks_unavailable"


def test_a_non_rsa_key_entry_is_refused():
    with pytest.raises(AuthError):
        build_rsa_pem({"kty": "EC", "kid": "x", "n": "a", "e": "b"})


# ── the sign-in flow ──────────────────────────────────────────────────────────

def test_every_flow_value_is_distinct_and_long():
    first, second = new_flow(), new_flow()
    for field in ("flow_id", "state", "nonce", "code_verifier"):
        assert getattr(first, field) != getattr(second, field)
        assert len(getattr(first, field)) >= 43


def test_the_challenge_is_the_sha256_of_the_verifier():
    import hashlib

    flow = new_flow()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(flow.code_verifier.encode()).digest()
    ).decode().rstrip("=")
    assert flow.code_challenge == expected


def test_the_authorize_url_names_the_configured_tenant_and_pkce():
    url = authorize_url(config(), redirect_uri="https://app.example/auth/callback", flow=new_flow())
    assert url.startswith(f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/authorize?")
    assert "code_challenge_method=S256" in url
    assert "response_type=code" in url
    assert f"client_id={CLIENT}" in url
    assert "client_secret" not in url


def test_a_plaintext_redirect_uri_is_refused():
    with pytest.raises(ValueError):
        authorize_url(config(), redirect_uri="http://app.example/auth/callback", flow=new_flow())
    with pytest.raises(ValueError):
        logout_url(config(), post_logout_redirect_uri="http://app.example/bye")


def test_state_comparison_is_constant_time_and_exact():
    assert constant_time_equals("abc", "abc")
    assert not constant_time_equals("abc", "abd")
    assert not constant_time_equals("abc", "")
    assert not constant_time_equals("abc", "abcd")


def test_a_session_id_is_never_stored_in_the_clear():
    session_id = new_session_id()
    key = session_lookup_key(session_id)
    assert session_id not in key
    assert len(key) == 64
    assert key == session_lookup_key(session_id)


# ── the shared store ──────────────────────────────────────────────────────────

def test_a_record_disappears_at_its_expiry():
    from datetime import datetime, timedelta, timezone

    store = InProcessRecordStore()

    async def drive():
        now = datetime.now(timezone.utc)
        await store.put("live", {"a": "1"}, now + timedelta(seconds=60))
        await store.put("dead", {"a": "2"}, now - timedelta(seconds=1))
        return await store.get("live"), await store.get("dead")

    live, dead = run(drive())
    assert live == {"a": "1"}
    assert dead is None


def test_deleting_an_absent_record_is_success():
    store = InProcessRecordStore()
    run(store.delete("never-existed"))


def test_a_full_store_refuses_rather_than_evicting():
    from datetime import datetime, timedelta, timezone

    from entra_auth import RecordStoreUnavailable

    store = InProcessRecordStore(max_entries=2)

    async def drive():
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        await store.put("a", {}, future)
        await store.put("b", {}, future)
        await store.put("c", {}, future)

    with pytest.raises(RecordStoreUnavailable):
        run(drive())


def test_an_empty_store_is_still_truthy():
    # ``store or fallback`` must not silently replace a working store with something weaker.
    assert bool(InProcessRecordStore())


def test_session_service_round_trips_host_records_and_existing_digests():
    store = InProcessRecordStore()
    now = datetime.now(timezone.utc)
    service = SessionService(
        store=store, flow_store=InProcessRecordStore(),
        max_lifetime=timedelta(hours=8), clock=lambda: now,
    )
    identity = {"subject": "operator-42", "permissions": "inspect", "workspace": "research"}
    expiry = now + timedelta(minutes=10)

    async def drive():
        session_id, expires_at = await service.create(identity, token_expires_at=expiry)
        assert expires_at == expiry
        assert await store.get(session_id) is None
        assert await store.get(session_lookup_key(session_id)) == identity
        assert await service.resolve(session_id) == identity
        assert await service.resolve(session_lookup_key(session_id)) is None
        await store.put(session_lookup_key("existing-cookie"), identity, expiry)
        assert await service.resolve("existing-cookie") == identity
        await service.revoke(session_id)
        assert await service.resolve(session_id) is None
        await service.revoke(session_id)

    run(drive())


@pytest.mark.parametrize("token_seconds,expected_seconds", [(120, 120), (7200, 3600)])
def test_session_service_caps_expiry_with_injected_clock(token_seconds, expected_seconds):
    now = datetime.now(timezone.utc)
    store = InProcessRecordStore()
    store.put = AsyncMock(wraps=store.put)
    service = SessionService(
        store=store, flow_store=InProcessRecordStore(),
        max_lifetime=timedelta(hours=1), clock=lambda: now,
    )
    session_id, expiry = run(service.create(
        {"subject": "person"}, token_expires_at=now + timedelta(seconds=token_seconds),
    ))
    assert expiry == now + timedelta(seconds=expected_seconds)
    store.put.assert_awaited_once_with(
        session_lookup_key(session_id), {"subject": "person"}, expiry,
    )


@pytest.mark.parametrize("remaining", [-1, 0])
def test_session_service_refuses_expired_tokens_without_writing(remaining):
    now = datetime.now(timezone.utc)
    store = InProcessRecordStore()
    store.put = AsyncMock(wraps=store.put)
    service = SessionService(
        store=store, flow_store=InProcessRecordStore(),
        max_lifetime=timedelta(hours=1), clock=lambda: now,
    )
    with pytest.raises(AuthError) as caught:
        run(service.create({}, token_expires_at=now + timedelta(seconds=remaining)))
    assert caught.value.reason == "expired"
    assert str(caught.value) == "token expires too soon to mint a session"
    store.put.assert_not_awaited()


def test_session_service_claims_once_and_preserves_flow_record_and_ttl():
    now = datetime.now(timezone.utc)
    flows = InProcessRecordStore()
    flows.put = AsyncMock(wraps=flows.put)
    flows.consume = AsyncMock(wraps=flows.consume)
    flows.get = AsyncMock(wraps=flows.get)
    flows.delete = AsyncMock(wraps=flows.delete)
    service = SessionService(
        store=InProcessRecordStore(), flow_store=flows,
        max_lifetime=timedelta(hours=1), clock=lambda: now,
    )
    flow = new_flow(return_to="/workspace")
    ttl = timedelta(minutes=5)

    async def drive():
        await service.start_flow(flow, ttl=ttl)
        flows.put.assert_awaited_once_with(flow.flow_id, flow.to_record(), now + ttl)
        results = await asyncio.gather(
            *(service.claim_flow(flow.flow_id, flow.state) for _ in range(50))
        )
        assert [record for record in results if record is not None] == [flow.to_record()]
        assert flows.consume.await_count == 50
        flows.get.assert_not_awaited()
        flows.delete.assert_not_awaited()

    run(drive())


def test_session_service_wrong_state_spends_flow_and_malformed_inputs_touch_no_store():
    flows = InProcessRecordStore()
    flows.consume = AsyncMock(wraps=flows.consume)
    service = SessionService(
        store=InProcessRecordStore(), flow_store=flows, max_lifetime=timedelta(hours=1),
    )
    flow = new_flow()

    async def drive():
        await service.start_flow(flow, ttl=timedelta(minutes=5))
        for malformed in (None, 123, "", "a" * 15, "a" * 129, "has spaces here!", "/" * 32):
            assert await service.claim_flow(malformed, flow.state) is None
            assert await service.claim_flow(flow.flow_id, malformed) is None
        flows.consume.assert_not_awaited()
        assert await service.claim_flow(flow.flow_id, "wrong" * 8) is None
        assert await service.claim_flow(flow.flow_id, flow.state) is None
        assert flows.consume.await_count == 2

    run(drive())


@pytest.mark.parametrize("operation", ["put", "get", "consume", "delete", "purge_expired"])
def test_session_service_propagates_store_outages(operation):
    store = InProcessRecordStore()
    setattr(store, operation, AsyncMock(side_effect=RecordStoreUnavailable("offline")))
    service = SessionService(store=store, flow_store=store, max_lifetime=timedelta(hours=1))

    async def drive():
        calls = {
            "put": lambda: service.create(
                {}, token_expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            ),
            "get": lambda: service.resolve("cookie"),
            "consume": lambda: service.claim_flow("a" * 32, "b" * 32),
            "delete": lambda: service.revoke("cookie"),
            "purge_expired": service.purge_expired,
        }
        with pytest.raises(RecordStoreUnavailable):
            await calls[operation]()

    run(drive())


def test_session_service_empty_cookie_and_read_expiry_and_housekeeping():
    store, flows = InProcessRecordStore(), InProcessRecordStore()
    service = SessionService(store=store, flow_store=flows, max_lifetime=timedelta(hours=1))
    store.get = AsyncMock(wraps=store.get)
    store.delete = AsyncMock(wraps=store.delete)
    expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    flow = new_flow()

    async def drive():
        assert await service.resolve("") is None
        await service.revoke("")
        store.get.assert_not_awaited()
        store.delete.assert_not_awaited()
        await store.put(session_lookup_key("expired"), {"subject": "person"}, expired)
        assert await service.resolve("expired") is None
        await flows.put(flow.flow_id, flow.to_record(), expired)
        assert await service.claim_flow(flow.flow_id, flow.state) is None
        await store.put("dead-session", {}, expired)
        await flows.put("dead-flow", {}, expired)
        assert await service.purge_expired() == 2
        assert await service.purge_expired() == 0

    run(drive())
