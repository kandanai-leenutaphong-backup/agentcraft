"""Security configuration, resolved at call time and validated loudly.

Every value here either configures an authentication mechanism or configures the store that
keeps it honest. None of them can weaken the authorization gate, because the gate has no
configuration: it denies unless a mechanism was successfully built.

Misconfiguration fails at startup with a message naming the variable. The alternative — a
default that quietly produces a weaker mode — is how an application ends up serving
unauthenticated traffic that nobody chose.

**There is no on/off switch here, by any name.** Authentication is not switched on; it is
configured, or it is absent and nobody gets in. A variable whose misspelling opens an
application is a defect regardless of how carefully it is parsed, and the only parsing that is
safe is the parsing that is never reached. ``test_authorization_gate.py`` scans every module
in this package for the names such a switch usually travels under, and fails on any of them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from entra_auth import GUID_PATTERN

#: Base64 of the 32-byte Ed25519 public key that authorises signed developer access. Public by
#: nature: it verifies, it cannot sign. Empty means no signed path is mounted at all.
PUBLIC_KEY_VAR = "DEV_PUBLIC_KEY_ED25519"
#: Which replay ledger to build. ``from_env`` accepts only ``azure-table`` once a signing key
#: is configured: there is no environment value that selects a per-process ledger, because a
#: per-process ledger is indistinguishable from no replay protection across a restart.
LEDGER_VAR = "DEV_REPLAY_LEDGER"
TABLE_ENDPOINT_VAR = "DEV_REPLAY_TABLE_ENDPOINT"
TABLE_NAME_VAR = "DEV_REPLAY_TABLE_NAME"

#: Microsoft Entra ID. Both identifiers are public: an application id and a tenant id are
#: disclosed by the sign-in redirect itself. There is no client secret anywhere in this
#: application, because the browser flow is a public client using PKCE.
ENTRA_TENANT_VAR = "AUTH_TENANT_ID"
ENTRA_CLIENT_VAR = "AUTH_CLIENT_ID"
#: Absolute ``https://`` origin this application is reached at. The redirect URI is built from
#: it rather than from the request, so a forged ``Host`` header cannot redirect a sign-in.
PUBLIC_ORIGIN_VAR = "AUTH_PUBLIC_ORIGIN"
SESSION_TABLE_ENDPOINT_VAR = "AUTH_SESSION_TABLE_ENDPOINT"
SESSION_TABLE_NAME_VAR = "AUTH_SESSION_TABLE_NAME"
SESSION_MAX_HOURS_VAR = "AUTH_SESSION_MAX_HOURS"

LEDGER_AZURE_TABLE = "azure-table"
#: Constructible, never selectable from the environment. Tests inject it and a workstation may
#: build it directly; :meth:`SecuritySettings.from_env` refuses it.
LEDGER_IN_PROCESS = "in-process"
_LEDGERS = (LEDGER_AZURE_TABLE, LEDGER_IN_PROCESS)

DEFAULT_TABLE_NAME = "devauthreplay"
DEFAULT_SESSION_TABLE_NAME = "browserauth"

#: Hard ceiling on a browser session, independent of the token that minted it. A session also
#: never outlives that token; this bounds the case where the token is long-lived.
DEFAULT_SESSION_MAX_HOURS = 8
MAX_SESSION_MAX_HOURS = 24

class SecurityConfigurationError(RuntimeError):
    """The deployment is not configured well enough to be safe. Never caught to continue."""


@dataclass(frozen=True, slots=True)
class SecuritySettings:
    """Resolved security configuration.

    Attributes:
        public_key_b64: The signed-access verification key, or empty.
        ledger_kind: ``azure-table``, ``in-process``, or empty when no signing key is set.
        table_endpoint: Table service endpoint for the durable ledger.
        table_name: Table holding the ledger.
        entra_tenant_id: The one tenant whose people may sign in, or empty.
        entra_client_id: This application's Entra application id, or empty.
        public_origin: ``https://host`` this application is reached at.
        session_table_endpoint: Table service endpoint for sign-in flows and browser sessions.
        session_table_name: Table holding them.
        session_max_hours: Ceiling on a browser session's life.
    """

    public_key_b64: str = ""
    ledger_kind: str = ""
    table_endpoint: str = ""
    table_name: str = DEFAULT_TABLE_NAME
    entra_tenant_id: str = ""
    entra_client_id: str = ""
    public_origin: str = ""
    session_table_endpoint: str = ""
    session_table_name: str = DEFAULT_SESSION_TABLE_NAME
    session_max_hours: int = DEFAULT_SESSION_MAX_HOURS

    @property
    def signed_access_configured(self) -> bool:
        return bool(self.public_key_b64)

    @property
    def ledger_is_durable(self) -> bool:
        return self.ledger_kind == LEDGER_AZURE_TABLE

    @property
    def entra_configured(self) -> bool:
        return bool(self.entra_tenant_id and self.entra_client_id)

    def redirect_uri(self) -> str:
        """Where Entra returns the browser. Built from configuration, never from a request."""
        return f"{self.public_origin}/auth/callback"

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "SecuritySettings":
        """Read and validate. Raises :class:`SecurityConfigurationError` on anything unsafe."""
        source = os.environ if env is None else env
        public_key = (source.get(PUBLIC_KEY_VAR) or "").strip()
        ledger = (source.get(LEDGER_VAR) or "").strip().lower()
        endpoint = (source.get(TABLE_ENDPOINT_VAR) or "").strip()
        table = (source.get(TABLE_NAME_VAR) or "").strip() or DEFAULT_TABLE_NAME

        entra = _entra_from(source)

        if not public_key:
            # No signing key, so no signed authorizing path exists. A ledger without a key to
            # protect is inert, and naming one is a misunderstanding worth reporting.
            if ledger:
                raise SecurityConfigurationError(
                    f"{LEDGER_VAR} is set but {PUBLIC_KEY_VAR} is not: there is no signed "
                    "access path for a replay ledger to protect"
                )
            return cls(**entra)

        if ledger != LEDGER_AZURE_TABLE:
            # The environment selects the durable ledger or it selects nothing. The
            # per-process ledger remains constructible — tests and a workstation build it
            # directly — but no deployed configuration can reach it, because the value that
            # would select it is the one that quietly removes replay protection.
            #
            # Capping replicas is not the alternative, and is deliberately not offered as one:
            # a restart empties a per-process ledger, and a rollout runs two processes at
            # once, so every captured signature inside the skew window becomes spendable again
            # on a single-replica deployment too.
            raise SecurityConfigurationError(
                f"{PUBLIC_KEY_VAR} is set, so {LEDGER_VAR} must be {LEDGER_AZURE_TABLE}; got "
                f"{ledger or '<unset>'!r}. A replay ledger that is not shared between "
                f"processes does not protect any deployment, whatever its replica count: "
                f"set {LEDGER_VAR}={LEDGER_AZURE_TABLE} and {TABLE_ENDPOINT_VAR}"
            )
        if not endpoint:
            raise SecurityConfigurationError(
                f"{LEDGER_VAR}={LEDGER_AZURE_TABLE} needs {TABLE_ENDPOINT_VAR}, e.g. "
                "https://<account>.table.core.windows.net"
            )
        return cls(
            public_key_b64=public_key,
            ledger_kind=ledger,
            table_endpoint=endpoint,
            table_name=table,
            **entra,
        )

    def describe(self, *, fingerprint: str = "") -> dict[str, object]:
        """Non-secret summary. Names the key by fingerprint, never by value."""
        return {
            "signed_access": self.signed_access_configured,
            "key_fingerprint": fingerprint,
            "replay_ledger": self.ledger_kind or "none",
            "replay_ledger_durable": self.ledger_is_durable,
            "entra_sign_in": self.entra_configured,
            "entra_tenant_id": self.entra_tenant_id,
        }


def _entra_from(source) -> dict[str, object]:
    """Read the Entra half. All of it, or none of it — never a usable-looking partial.

    A half-configured sign-in is the dangerous state: it looks configured to an operator
    reading the variables and produces no resolver at all, so the application refuses everyone
    and the reason is invisible. Naming the missing variable at startup is the whole point.
    """
    tenant = (source.get(ENTRA_TENANT_VAR) or "").strip()
    client = (source.get(ENTRA_CLIENT_VAR) or "").strip()
    origin = (source.get(PUBLIC_ORIGIN_VAR) or "").strip().rstrip("/")
    table_endpoint = (source.get(SESSION_TABLE_ENDPOINT_VAR) or "").strip()
    table_name = (source.get(SESSION_TABLE_NAME_VAR) or "").strip() or DEFAULT_SESSION_TABLE_NAME
    raw_hours = (source.get(SESSION_MAX_HOURS_VAR) or "").strip()

    blank = {
        "entra_tenant_id": "", "entra_client_id": "", "public_origin": "",
        "session_table_endpoint": "", "session_table_name": DEFAULT_SESSION_TABLE_NAME,
        "session_max_hours": DEFAULT_SESSION_MAX_HOURS,
    }
    if not any((tenant, client, origin, table_endpoint)):
        return blank

    for name, value in (
        (ENTRA_TENANT_VAR, tenant), (ENTRA_CLIENT_VAR, client),
        (PUBLIC_ORIGIN_VAR, origin), (SESSION_TABLE_ENDPOINT_VAR, table_endpoint),
    ):
        if not value:
            raise SecurityConfigurationError(
                f"{name} is required once any of {ENTRA_TENANT_VAR}, {ENTRA_CLIENT_VAR}, "
                f"{PUBLIC_ORIGIN_VAR} or {SESSION_TABLE_ENDPOINT_VAR} is set. Configure Entra "
                "sign-in completely or not at all"
            )
    for name, value in ((ENTRA_TENANT_VAR, tenant), (ENTRA_CLIENT_VAR, client)):
        if not GUID_PATTERN.match(value):
            raise SecurityConfigurationError(f"{name} must be a GUID")
    if not origin.startswith("https://"):
        raise SecurityConfigurationError(
            f"{PUBLIC_ORIGIN_VAR} must be an https origin, e.g. https://app.example.com. "
            "A sign-in redirected over plain HTTP hands the authorization code to the network"
        )
    if not table_endpoint.startswith("https://"):
        raise SecurityConfigurationError(f"{SESSION_TABLE_ENDPOINT_VAR} must be an https endpoint")

    hours = DEFAULT_SESSION_MAX_HOURS
    if raw_hours:
        if not raw_hours.isdigit() or not 1 <= int(raw_hours) <= MAX_SESSION_MAX_HOURS:
            raise SecurityConfigurationError(
                f"{SESSION_MAX_HOURS_VAR} must be a whole number of hours between 1 and "
                f"{MAX_SESSION_MAX_HOURS}"
            )
        hours = int(raw_hours)

    return {
        "entra_tenant_id": tenant, "entra_client_id": client, "public_origin": origin,
        "session_table_endpoint": table_endpoint, "session_table_name": table_name,
        "session_max_hours": hours,
    }
