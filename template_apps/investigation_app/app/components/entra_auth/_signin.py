"""The browser half: an Authorization Code + PKCE flow that needs no client credential.

Module role:
    Mints and validates the short-lived state a sign-in redirect must survive — flow id,
    ``state``, ``nonce``, PKCE verifier and challenge — and builds the authorize URL from
    configuration. It performs no HTTP and stores nothing; the consumer owns both.

Why PKCE with a public client rather than a confidential one:
    A confidential client needs a secret on the server, and a secret needs somewhere to live,
    be rotated, and be kept out of logs and images. PKCE removes the secret entirely: the
    authorization code is redeemable only by whoever holds the verifier whose SHA-256 was
    published when the flow started. There is no long-lived value to steal.

Why the verifier is generated here and not in the browser:
    A verifier the browser generates has to survive a full-page redirect to the identity
    provider, which means ``sessionStorage``. Generating it server-side, holding it against a
    flow id in an ``HttpOnly`` cookie, and releasing it once to the same-origin callback page
    keeps it out of web storage entirely and gives it a lifetime measured in the seconds the
    redirect takes rather than the lifetime of a tab.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

from ._config import EntraAuthConfig

#: Bytes of entropy behind each opaque value. 32 bytes is 256 bits; the PKCE specification
#: requires a verifier of 43-128 characters, and 32 bytes base64url-encoded is 43.
_ENTROPY_BYTES = 32

#: How long an unfinished sign-in may sit before it is refused. Long enough to type a password
#: and satisfy a second factor, short enough that an abandoned flow is not a standing invitation.
DEFAULT_FLOW_TTL_SECONDS = 600


def _urlsafe(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


@dataclass(frozen=True, slots=True)
class SignInFlow:
    """One in-progress sign-in.

    Attributes:
        flow_id: Names the flow in the consumer's store. Travels in an ``HttpOnly`` cookie,
            never in a URL, so it is not readable by script and not captured by a referrer.
        state: Echoed by the identity provider and compared on return. The CSRF defence for
            the redirect itself: a callback whose state does not match a flow this browser
            started is somebody else's authorization code.
        nonce: Bound into the id token, for a consumer that inspects one.
        code_verifier: The PKCE secret. Released once, to the same-origin callback page.
        code_challenge: ``BASE64URL(SHA256(verifier))``, published when the flow starts.
        return_to: Where to send the browser afterwards. Validated by the consumer as a
            same-origin path before it is ever used.
    """

    flow_id: str
    state: str
    nonce: str
    code_verifier: str
    code_challenge: str
    return_to: str = "/"

    def to_record(self) -> dict[str, str]:
        """The fields a store must keep. The flow id is the key, not a field."""
        return {
            "state": self.state,
            "nonce": self.nonce,
            "code_verifier": self.code_verifier,
            "return_to": self.return_to,
        }


def new_flow(return_to: str = "/") -> SignInFlow:
    """Mint a fresh flow. Every value is from the system CSPRNG."""
    verifier = _urlsafe(secrets.token_bytes(_ENTROPY_BYTES))
    challenge = _urlsafe(hashlib.sha256(verifier.encode("ascii")).digest())
    return SignInFlow(
        flow_id=_urlsafe(secrets.token_bytes(_ENTROPY_BYTES)),
        state=_urlsafe(secrets.token_bytes(_ENTROPY_BYTES)),
        nonce=_urlsafe(secrets.token_bytes(_ENTROPY_BYTES)),
        code_verifier=verifier,
        code_challenge=challenge,
        return_to=return_to or "/",
    )


def authorize_url(config: EntraAuthConfig, *, redirect_uri: str, flow: SignInFlow) -> str:
    """Build the tenant-scoped authorize URL for this flow.

    Every component comes from configuration or from ``flow``. Nothing here is taken from a
    request parameter, so no caller can redirect a sign-in at an authority of their choosing.

    ``prompt`` is deliberately absent: forcing re-authentication on every visit trains people
    to type credentials at whatever asks, and forcing account selection is a preference, not a
    security control.
    """
    if not redirect_uri.startswith("https://"):
        raise ValueError("redirect_uri must be https")
    query = urlencode(
        {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": " ".join(("openid", "profile", *config.client_scopes())),
            "state": flow.state,
            "nonce": flow.nonce,
            "code_challenge": flow.code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{config.authorize_endpoint()}?{query}"


def logout_url(config: EntraAuthConfig, *, post_logout_redirect_uri: str) -> str:
    """Build the identity provider's sign-out URL.

    Local revocation is the consumer's job and happens first; this only ends the session the
    identity provider itself holds, so a later visit is a real sign-in rather than a silent
    re-issue.
    """
    if not post_logout_redirect_uri.startswith("https://"):
        raise ValueError("post_logout_redirect_uri must be https")
    query = urlencode({"post_logout_redirect_uri": post_logout_redirect_uri})
    return f"{config.logout_endpoint()}?{query}"


def constant_time_equals(left: str, right: str) -> bool:
    """Compare two opaque values without leaking their common prefix through timing."""
    return secrets.compare_digest((left or "").encode("utf-8"), (right or "").encode("utf-8"))


def new_session_id() -> str:
    """An opaque browser-session identifier. Never derived from anything the caller sends."""
    return _urlsafe(secrets.token_bytes(_ENTROPY_BYTES))


def session_lookup_key(session_id: str) -> str:
    """Hash a session id into the value a store may hold.

    The store keeps the hash, never the identifier. Read access to the table — a support
    query, a backup, an over-broad role assignment — then yields nothing that can be presented
    as a cookie, exactly as a password store keeps no password.
    """
    return hashlib.sha256((session_id or "").encode("utf-8")).hexdigest()


__all__ = [
    "SignInFlow",
    "new_flow",
    "authorize_url",
    "logout_url",
    "constant_time_equals",
    "new_session_id",
    "session_lookup_key",
    "DEFAULT_FLOW_TTL_SECONDS",
]
