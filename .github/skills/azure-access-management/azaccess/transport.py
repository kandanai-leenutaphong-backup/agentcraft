"""Transport seam: one neutral request interface, several real backends.

WHY A SEAM
----------
Planning, authorisation and verification are the hard parts, and none of them
should require a cloud account to exercise. Everything above this module talks
to a :class:`Transport` — ``request(method, url, json_body=None)`` returning a
:class:`Response` — so the whole interface is driven end-to-end offline
against :class:`RecordingTransport`, and the same code paths carry real
requests in production.

The seam is neutral about *transport*, never about *content*: the URLs and
bodies are built by the providers from the plan, so a recorded fake proves the
requests are serialised correctly rather than proving nothing.

HTTP AND SQL ARE DIFFERENT SEAMS
--------------------------------
A T-SQL statement is not an HTTP request and forcing one through this
interface would produce a transport that lies about what it can do. SQL has
its own protocol (:class:`SqlExecutor`), and the SQL provider is honest about
being delegated to whatever the host supplies.

NO ARBITRARY EXECUTION
----------------------
A transport takes a method, a URL and a JSON body. It never takes a command
line, a shell string or a callable from a plan. The Azure CLI backend builds
its own argument vector from those three values and passes ``shell=False``.

A TOKEN GOES WHERE THE CONFIGURATION SAYS, NEVER WHERE THE RESPONSE SAYS
------------------------------------------------------------------------
Every live transport is constructed against a :class:`CloudEndpoints` and one
audience, and validates the URL against that allowlist **before** it asks the
credential for anything. That ordering is the fix for a reproduced
exfiltration: paging followed an absolute ``nextLink`` and the transport
attached ``Authorization`` unconditionally, so a hostile list body received a
live ARM token. Redirects are refused outright for the same reason — urllib
follows them by default and forwards the header.

A STATUS IS READ, NOT GUESSED
-----------------------------
``az rest`` prints a body, not a status line. The previous backend grepped any
three-digit run out of stderr, so ``"Operation failed on rg-500"`` became HTTP
500 and a resource group named ``kv-404-prod`` became a 404; worse, success was
reported as a flat ``200``, which made a Cosmos ``202`` long-running create
indistinguishable from a completed one. Now: only structured error codes are
mapped, an unrecognised failure is :data:`UNKNOWN_STATUS` rather than a
fabricated number, and the CLI backend refuses mutating methods, because a
write whose real status cannot be read cannot be applied safely.

DEPENDENCIES
------------
Standard library only. The credential backend imports an Azure credential
lazily, so the package installs and self-tests without it.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib import error as urlerror
from urllib import request as urlrequest

from azaccess.endpoints import (
    AZURE_PUBLIC_CLOUD,
    CloudEndpoints,
    origin_of,
    require_trusted_url,
)
from azaccess.errors import AuthenticationError, AuthorizationRefused, TransportError

#: Returned when a backend genuinely does not know the HTTP status. Never
#: treated as success, never treated as a specific failure.
UNKNOWN_STATUS = 0

#: Read-only methods. The CLI backend is limited to these because it cannot
#: report the status of anything else faithfully.
READ_METHODS: tuple[str, ...] = ("GET", "HEAD")

#: Published ARM error codes mapped to the status they are documented to
#: arrive with. Structured: the code is read from the error object the service
#: returned, not from arbitrary text.
#: Reference: Azure Resource Manager "Common error codes" and the RBAC REST
#: reference for RoleAssignmentExists.
ARM_ERROR_CODE_STATUS: dict[str, int] = {
    "roleassignmentexists": 409,
    "roleassignmentupdatenotpermitted": 409,
    "conflict": 409,
    "authorizationfailed": 403,
    "insufficientprivileges": 403,
    "forbiddenbypolicy": 403,
    "requestdisallowedbypolicy": 403,
    "authenticationfailed": 401,
    "invalidauthenticationtoken": 401,
    "invalidauthenticationtokentenant": 401,
    "expiredauthenticationtoken": 401,
    "resourcenotfound": 404,
    "notfound": 404,
    "parentresourcenotfound": 404,
    "subscriptionnotfound": 404,
    "principalnotfound": 400,
    "invalidprincipalid": 400,
    "badrequest": 400,
    "invalidrequestcontent": 400,
    "missingsubscriptionregistration": 409,
    "toomanyrequests": 429,
    "throttled": 429,
    "serviceunavailable": 503,
    "internalservererror": 500,
}

_BEARER_RE = re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}")
_JWT_RE = re.compile(r"eyJ[A-Za-z0-9._-]{20,}")
_SECRETISH_RE = re.compile(
    r"(?i)\b(sig|sv|se|skoid|password|pwd|client_secret|primaryKey|secondaryKey|"
    r"connectionString|accountKey)\b\s*[=:]\s*[^&\s\"',}]+"
)


def sanitize_detail(text: str, *, limit: int = 400) -> str:
    """Strip anything token- or key-shaped before it reaches a log or error.

    Applied to every response body this package puts in an exception. It is a
    backstop, not a licence: providers do not put response bodies in errors
    unless the body is an ARM error object.
    """
    cleaned = _BEARER_RE.sub("Bearer <redacted>", str(text))
    cleaned = _JWT_RE.sub("<redacted-token>", cleaned)
    cleaned = _SECRETISH_RE.sub(lambda m: f"{m.group(1)}=<redacted>", cleaned)
    return cleaned[:limit]


@dataclass(frozen=True)
class Response:
    """A completed HTTP exchange, with no credential material retained.

    ``headers`` deliberately excludes request headers: the ``Authorization``
    header is constructed inside a backend, used, and dropped.
    """

    status: int
    body: Any = None
    headers: Mapping[str, str] = field(default_factory=dict)
    #: False when the backend inferred the status rather than reading it off
    #: the wire. Anything that distinguishes 200 from 201 or 202 must check it.
    status_exact: bool = True

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300

    def header(self, name: str) -> str:
        """One response header, case-insensitively."""
        wanted = str(name).lower()
        for key, value in dict(self.headers).items():
            if str(key).lower() == wanted:
                return str(value)
        return ""

    def json_body(self) -> dict[str, Any]:
        """The body as a mapping, or a transport failure naming the shape."""
        if isinstance(self.body, dict):
            return self.body
        if self.body in (None, ""):
            return {}
        raise TransportError(
            f"expected a JSON object, got {type(self.body).__name__}: "
            f"{sanitize_detail(str(self.body), limit=120)}"
        )


class Transport(Protocol):
    """The whole outbound surface above this module."""

    def request(
        self, method: str, url: str, *, json_body: Any = None
    ) -> Response:  # pragma: no cover - protocol
        ...


class SqlExecutor(Protocol):
    """A T-SQL seam, separate from HTTP on purpose."""

    def execute(self, statement: str, parameters: Sequence[Any] = ()) -> None:  # pragma: no cover
        ...

    def query(
        self, statement: str, parameters: Sequence[Any] = ()
    ) -> list[dict[str, Any]]:  # pragma: no cover
        ...


@dataclass
class RecordingTransport:
    """A scripted, offline transport that also records what it was asked.

    Two jobs, both needed by the tests: it returns the responses a scenario
    needs, and it keeps the exact ``(method, url, body)`` triples so a test can
    assert the *request* was serialised correctly — api-version, principal
    type, role definition id — rather than only that the code survived.

    An unscripted call is a failure, never an empty success: a silent default
    would let a test pass while the code called the wrong URL.
    """

    #: (method, url-substring) -> response, or a list consumed in order.
    responses: dict[tuple[str, str], Any] = field(default_factory=dict)
    calls: list[dict[str, Any]] = field(default_factory=list)
    default: Response | None = None
    #: The token audience this fake claims to hold. Providers that must not be
    #: driven with the wrong audience (Graph) check it, so a test can prove the
    #: refusal happens before any request is recorded.
    audience: str = AZURE_PUBLIC_CLOUD.arm_audience
    cloud: CloudEndpoints = AZURE_PUBLIC_CLOUD

    def script(self, method: str, url_fragment: str, *responses: Response) -> "RecordingTransport":
        key = (method.upper(), url_fragment)
        self.responses.setdefault(key, []).extend(responses)
        return self

    def request(self, method: str, url: str, *, json_body: Any = None) -> Response:
        self.calls.append({"method": method.upper(), "url": url, "body": json_body})
        for (scripted_method, fragment), queue in self.responses.items():
            if scripted_method != method.upper() or fragment not in url:
                continue
            if not queue:
                continue
            return queue[0] if len(queue) == 1 else queue.pop(0)
        if self.default is not None:
            return self.default
        raise TransportError(
            f"no recorded response for {method.upper()} {url[:120]} — script it "
            f"or the test is asserting nothing"
        )

    def urls(self, method: str = "") -> list[str]:
        return [
            c["url"]
            for c in self.calls
            if not method or c["method"] == method.upper()
        ]

    def bodies(self, method: str = "") -> list[Any]:
        return [
            c["body"]
            for c in self.calls
            if not method or c["method"] == method.upper()
        ]


class AzureCliTransport:
    """Read-only live backend that shells out to ``az rest``.

    Chosen as a live backend because it needs no Python dependency at all and
    reuses whatever identity the operator is already signed in as. It never
    sees a secret: the CLI holds the token.

    **Reads only, and that is a correctness limit, not caution.** ``az rest``
    reports no HTTP status and no response headers, so this backend cannot tell
    ``201 Created`` from ``202 Accepted`` — exactly the distinction a Cosmos or
    Kusto long-running create turns on, and exactly the distinction ARM's
    ``409 RoleAssignmentExists`` adoption path turns on. A mutation is
    therefore refused here and belongs on
    :class:`TokenCredentialTransport`, which reads the real status off the wire.

    Not used by any live test. The unit tests drive it through an injected
    ``runner``.
    """

    def __init__(
        self,
        *,
        executable: str = "az",
        timeout_secs: float = 120.0,
        cloud: CloudEndpoints = AZURE_PUBLIC_CLOUD,
        audience: str = "",
        runner: Callable[..., Any] | None = None,
    ) -> None:
        self._executable = executable
        self._timeout = timeout_secs
        self.cloud = cloud
        self.audience = audience or cloud.arm_audience
        self._resource = self.audience.removesuffix("/.default") or self.audience
        self._runner = runner or self._run

    def _run(self, argv: Sequence[str]) -> Any:
        return subprocess.run(  # shell=False: no string is ever interpreted
            list(argv), capture_output=True, text=True, timeout=self._timeout,
            shell=False, check=False,
        )

    def request(self, method: str, url: str, *, json_body: Any = None) -> Response:
        verb = method.upper()
        if verb not in READ_METHODS:
            raise AuthorizationRefused(
                f"AzureCliTransport refuses {verb}: 'az rest' reports no HTTP "
                f"status, so a write cannot be told from an accepted "
                f"long-running operation or from a 409 that should be adopted. "
                f"Use TokenCredentialTransport for mutations"
            )
        # Host allowlist first: nothing is spawned for an off-cloud URL.
        require_trusted_url(url, self.cloud.hosts(), what=f"{verb} via az rest")
        argv = [
            self._executable, "rest",
            "--method", verb.lower(),
            "--url", url,
            "--resource", self._resource,
            "--only-show-errors",
            "--output", "json",
        ]
        if json_body is not None:  # pragma: no cover - unreachable for reads
            raise AuthorizationRefused("a read carries no body")
        try:
            proc = self._runner(argv)
        except FileNotFoundError as exc:
            raise TransportError(
                f"'{self._executable}' is not on PATH; install the Azure CLI or "
                f"supply another transport"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise TransportError(f"{verb} timed out after {self._timeout}s") from exc
        if proc.returncode != 0:
            detail = sanitize_detail((proc.stderr or "").strip())
            if "AADSTS" in detail or "not logged in" in detail.lower():
                raise AuthenticationError(f"credential rejected: {detail}")
            status = status_from_cli_error(detail)
            return Response(
                status=status,
                body={"error": {"message": detail}},
                status_exact=status != UNKNOWN_STATUS,
            )
        text = (proc.stdout or "").strip()
        try:
            body = json.loads(text) if text else {}
        except json.JSONDecodeError:
            body = {"raw": sanitize_detail(text, limit=200)}
        # 2xx is known; *which* 2xx is not, and the flag says so.
        return Response(status=200, body=body, status_exact=False)


def status_from_cli_error(detail: str) -> int:
    """An HTTP status from a *structured* CLI failure, or :data:`UNKNOWN_STATUS`.

    Three structured sources, in order of trust: an explicit status the CLI
    printed (``HTTP 403``, ``status code: 409``), an ARM error object with a
    ``code`` field, and a bare recognised error code token. A digit that merely
    appears somewhere in a message — in a resource-group name, in a quota, in a
    date — is never a status.
    """
    text = str(detail or "")
    explicit = re.search(
        r"(?i)(?:http(?:/1\.[01])?\s+|status(?:\s+code)?\s*[:=]\s*|response\s+status\s*[:=]\s*)"
        r"([1-5]\d{2})\b",
        text,
    )
    if explicit:
        return int(explicit.group(1))
    for match in re.finditer(r'"code"\s*:\s*"([A-Za-z]+)"', text):
        status = ARM_ERROR_CODE_STATUS.get(match.group(1).lower())
        if status:
            return status
    for code, status in ARM_ERROR_CODE_STATUS.items():
        if re.search(rf"(?i)\b{re.escape(code)}\b", text):
            return status
    return UNKNOWN_STATUS


class _RefuseRedirects(urlrequest.HTTPRedirectHandler):
    """Follow nothing.

    urllib follows 301/302/303/307 by default and re-sends the request
    *including* ``Authorization``. A redirect is a server asking for the
    credential to be delivered somewhere the host allowlist never approved, so
    it is surfaced to the caller as data instead.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        return None


class TokenCredentialTransport:
    """Live backend for a caller that already holds a ``TokenCredential``.

    The credential is supplied by the host — ``DefaultAzureCredential``,
    ``ManagedIdentityCredential``, whatever it uses — and this class only ever
    calls ``get_token``. There is no key fallback, no connection string, and no
    place to persist a secret: the token lives in a local variable for the
    duration of one request.

    Bound to one cloud and one audience at construction. The host check runs
    before ``get_token`` on **every** send, so a URL that came from a response
    body cannot cause a token to be minted at all, and redirects are refused.
    """

    def __init__(
        self,
        credential_provider: Callable[[], Any],
        *,
        cloud: CloudEndpoints = AZURE_PUBLIC_CLOUD,
        audience: str = "",
        scope: str = "",
        timeout_secs: float = 60.0,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self._credential_provider = credential_provider
        self.cloud = cloud
        # ``scope`` is the historical name for the same value; one wins and the
        # other is a compatible alias rather than a second source of truth.
        self.audience = audience or scope or cloud.arm_audience
        self._allowed_hosts = frozenset(
            h for h in cloud.hosts()
            if _audience_matches(cloud.audience_for_host(h), self.audience)
        )
        if not self._allowed_hosts:
            raise AuthorizationRefused(
                f"audience {self.audience!r} matches no host in cloud "
                f"'{cloud.name}'; a transport that can reach nothing is a "
                f"configuration error, not a safe default"
            )
        self._timeout = timeout_secs
        self._opener = opener or urlrequest.build_opener(_RefuseRedirects()).open
        self._credential: Any = None

    @property
    def allowed_hosts(self) -> frozenset[str]:
        """Exactly where this transport will send its token."""
        return self._allowed_hosts

    def _bearer(self) -> str:
        if self._credential is None:
            self._credential = self._credential_provider()
        try:
            issued = self._credential.get_token(self.audience)
        except Exception as exc:  # credential libraries raise their own types
            raise AuthenticationError(
                f"could not obtain a token for {self.audience}: "
                f"{sanitize_detail(str(exc), limit=200)}"
            ) from exc
        return issued.token

    def request(self, method: str, url: str, *, json_body: Any = None) -> Response:
        # Ordering is the control: refuse first, mint second. Reversing these
        # two lines is the credential-exfiltration bug this package shipped.
        require_trusted_url(
            url, self._allowed_hosts, what=f"{method.upper()} with an Azure token"
        )
        data = None
        headers = {"Authorization": f"Bearer {self._bearer()}"}
        if json_body is not None:
            data = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urlrequest.Request(url, data=data, headers=headers, method=method.upper())
        try:
            with self._opener(req, timeout=self._timeout) as handle:
                payload = handle.read().decode("utf-8", "replace")
                status = handle.status
                response_headers = dict(handle.headers.items())
        except urlerror.HTTPError as exc:  # a 4xx/5xx is data, not an exception
            if exc.code in (301, 302, 303, 307, 308):
                raise AuthorizationRefused(
                    f"{origin_of(url)} answered HTTP {exc.code} redirect; refusing "
                    f"to re-send an Authorization header to a location this "
                    f"process did not authorise"
                ) from None
            payload = exc.read().decode("utf-8", "replace") if exc.fp else ""
            status, response_headers = exc.code, dict(exc.headers.items() if exc.headers else {})
        except urlerror.URLError as exc:
            raise TransportError(
                f"network failure calling {origin_of(url)}: "
                f"{sanitize_detail(str(exc.reason), limit=120)}"
            ) from exc
        try:
            body = json.loads(payload) if payload.strip() else {}
        except json.JSONDecodeError:
            body = {"raw": sanitize_detail(payload, limit=200)}
        return Response(status=status, body=body, headers=response_headers)


def _audience_matches(configured: str, wanted: str) -> bool:
    def base(value: str) -> str:
        return str(value or "").rstrip("/").removesuffix("/.default").rstrip("/").lower()

    return base(configured) == base(wanted)


__all__ = [
    "ARM_ERROR_CODE_STATUS",
    "AzureCliTransport",
    "READ_METHODS",
    "RecordingTransport",
    "Response",
    "SqlExecutor",
    "TokenCredentialTransport",
    "Transport",
    "UNKNOWN_STATUS",
    "sanitize_detail",
    "status_from_cli_error",
]
