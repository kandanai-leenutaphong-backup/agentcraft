"""Microsoft Entra ID access-token validation and browser sign-in, domain-blind.

Two decisions, kept apart on purpose: **who is calling**, which is token validation, and
**what may they see**, which is the consuming application's business and is not modelled here.
Collapsing them is how a valid token from one tenant reads another tenant's data.

**This component knows no identity type.** :class:`TokenValidator` returns a
:class:`VerifiedToken` — the verified claims, reduced. The consumer maps that onto its own
principal in one place it owns, so there is exactly one identity model in the application and
this component can move to another consumer unchanged.

What is deliberately absent
---------------------------
There is **no disabled mode and no development identity header**. The upstream box this was
adopted from carried both, together with a ``from_env`` that mapped any unrecognised
``AUTH_ENABLED`` value to *disabled* — the open state — so a typo produced a service that
granted every caller a self-asserted identity from ``X-User-Id``. Here a configuration either
names a real tenant and a real audience or cannot be constructed, and a deployment that fails
to configure Entra simply has no Entra resolver. The application's authorization gate then
refuses everyone, because it has no configuration either.

The other three hardening changes, all recorded in ``PROVENANCE.md``:

* **single tenant only** — ``common`` and ``organizations`` are refused at construction;
* **bounded staleness** — a key set whose refresh keeps failing is served for a limited window
  and then fails closed, rather than honouring possibly-revoked keys for the life of the
  process;
* **caller kind is policy, not an accident** — a service principal is refused unless the
  configuration opted in *and* the token carries an accepted application role. Requiring the
  ``oid`` claim does not filter service principals: a v2 client-credentials token carries the
  service principal's own object id.

Public surface
--------------
``EntraAuthConfig`` / ``EntraConfigurationError`` — the trust boundary as data.
``TokenValidator`` / ``VerifiedToken`` / ``extract_bearer`` / ``first_header`` — validation.
``JWKSCache`` / ``build_rsa_pem`` / ``default_fetcher`` / ``Fetcher`` — the key set.
``AuthError`` — every refusal, with a message selected by reason and never built from input.
``SignInFlow`` / ``new_flow`` / ``authorize_url`` / ``logout_url`` / ``new_session_id`` /
``session_lookup_key`` / ``constant_time_equals`` — the Authorization Code + PKCE flow.
``RecordStore`` / ``InProcessRecordStore`` / ``AzureTableRecordStore`` /
``RecordStoreUnavailable`` — the shared expiring store the flow and the session need.
``KIND_USER`` / ``KIND_SERVICE`` / ``ALLOWED_ALGORITHMS`` / ``MAX_TOKEN_BYTES`` — constants.

Dependencies are ``pyjwt``, ``cryptography`` and the standard library. No web framework is
imported. ``AzureTableRecordStore`` imports the Azure SDK lazily, so a deployment configuring
a different store never needs it installed.

Contract: ``README.md``. Origin and what changed: ``PROVENANCE.md``.
"""

from ._config import (
    ALLOWED_ALGORITHMS,
    DEFAULT_JWKS_MAX_STALE_SECONDS,
    DEFAULT_JWKS_REFRESH_COOLDOWN_SECONDS,
    DEFAULT_JWKS_TTL_SECONDS,
    DEFAULT_LEEWAY_SECONDS,
    DEFAULT_REQUIRED_SCOPE,
    GUID_PATTERN,
    MULTI_TENANT_VALUES,
    EntraAuthConfig,
    EntraConfigurationError,
)
from ._errors import AuthError
from ._jwks import Fetcher, JWKSCache, build_rsa_pem, default_fetcher
from ._signin import (
    DEFAULT_FLOW_TTL_SECONDS,
    SignInFlow,
    authorize_url,
    constant_time_equals,
    logout_url,
    new_flow,
    new_session_id,
    session_lookup_key,
)
from ._store import (
    AzureTableRecordStore,
    InProcessRecordStore,
    RecordStore,
    RecordStoreUnavailable,
)
from ._validator import (
    KIND_SERVICE,
    KIND_USER,
    MAX_TOKEN_BYTES,
    TokenValidator,
    VerifiedToken,
    extract_bearer,
    first_header,
)

__all__ = [
    "ALLOWED_ALGORITHMS",
    "AuthError",
    "AzureTableRecordStore",
    "DEFAULT_FLOW_TTL_SECONDS",
    "DEFAULT_JWKS_MAX_STALE_SECONDS",
    "DEFAULT_JWKS_REFRESH_COOLDOWN_SECONDS",
    "DEFAULT_JWKS_TTL_SECONDS",
    "DEFAULT_LEEWAY_SECONDS",
    "DEFAULT_REQUIRED_SCOPE",
    "EntraAuthConfig",
    "EntraConfigurationError",
    "Fetcher",
    "GUID_PATTERN",
    "InProcessRecordStore",
    "JWKSCache",
    "KIND_SERVICE",
    "KIND_USER",
    "MAX_TOKEN_BYTES",
    "MULTI_TENANT_VALUES",
    "RecordStore",
    "RecordStoreUnavailable",
    "SignInFlow",
    "TokenValidator",
    "VerifiedToken",
    "authorize_url",
    "build_rsa_pem",
    "constant_time_equals",
    "default_fetcher",
    "extract_bearer",
    "first_header",
    "logout_url",
    "new_flow",
    "new_session_id",
    "session_lookup_key",
]

__version__ = "1.0.0"
