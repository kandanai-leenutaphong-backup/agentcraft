"""Deny by default, at the ASGI edge, before anything of the application runs.

Every method and every path is refused unless an authentication mechanism has already put a
:class:`Principal` on the ASGI scope. That includes the API, the built frontend, its assets,
``/docs``, ``/openapi.json`` and every path that matches no route at all — an unauthenticated
404 still tells a stranger which paths exist, and a static asset served before authorization is
data served before authorization.

Pure ASGI, deliberately. A FastAPI dependency runs after routing, after path parsing and after
body parsing, so a dependency-based guard leaves all of that reachable to an anonymous caller.
``BaseHTTPMiddleware`` is also out: it buffers the response body and would break every
server-sent-event stream in this application.

**There is no switch that turns this off.** No environment variable, no flag, no debug mode.
An application whose authorization can be disabled by a misspelled variable has an
authorization bug waiting for a typo, and the only way to be sure the lever is not pulled by
accident is not to build the lever. Access is granted by configuring an authentication
mechanism, never by disabling this.

The seam for Microsoft Entra ID is :meth:`AuthorizationGate.add_resolver`: an async callable
that inspects the raw ASGI scope and returns a principal or ``None``. Resolvers are registered
in-process by the composition root, never named in configuration, so no deployed value can
introduce one.

A person needs somewhere to sign in, and that somewhere cannot itself require a signature. The
gate therefore admits a short, **exact** list of public routes — never a prefix, never a
wildcard — supplied in process by the composition root alongside the resolvers. Exactness is
the whole safety property: ``/auth`` as a prefix would publish anything anyone later mounted
beneath it, and ``/assets`` as a wildcard publishes the application bundle.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Iterable, Mapping
from urllib.parse import quote

from .principal import Principal

#: ASGI scope key the authenticated principal lives under. Shared with the signed-request
#: middleware so both mechanisms converge on one principal and nothing authenticates twice.
SCOPE_KEY = "auth_principal"

#: The one unauthenticated path. It exists for a platform liveness probe and answers a fixed
#: one-field body: no version, no configuration, no data, no evidence that anything else here
#: exists. ``/api/health`` stays protected — it reports store reachability and agent
#: configuration, which is exactly the reconnaissance an anonymous caller would want.
PUBLIC_PROBE_PATH = "/healthz"
_PROBE_METHODS = frozenset({"GET", "HEAD"})
_PROBE_BODY = b'{"status":"ok"}'

#: Applied to every response that leaves through this gate, including refusals and static
#: assets. An authenticated response cached by a shared proxy is an authenticated response
#: served to whoever asks next.
_NO_STORE = (b"cache-control", b"no-store, private")

#: A same-origin absolute path and nothing else. ``//host`` is excluded deliberately: browsers
#: read a leading double slash as protocol-relative, so a "path" beginning with one is an
#: absolute URL to somebody else's host and would turn the sign-in redirect into an open one.
_SAFE_PATH = re.compile(r"^/(?!/)[A-Za-z0-9._~!$&'()*+,;=:@%/-]*$")

#: Requests below this prefix are answered, never redirected. A programmatic caller needs a
#: status code it can act on; a 303 to a sign-in page is an HTML answer to a JSON question.
_API_PREFIX = "/api/"

PrincipalResolver = Callable[[Mapping[str, Any]], Awaitable[Principal | None]]


@dataclass(frozen=True, slots=True)
class PublicRoute:
    """One path that may be reached without a principal, and the methods allowed on it.

    Attributes:
        path: Matched **exactly**. Not a prefix and not a pattern.
        methods: Upper-case method names. Anything else on this path is refused like any
            other unauthenticated request, so a public ``GET`` never publishes a ``POST``.
    """

    path: str
    methods: frozenset[str]

    def __post_init__(self) -> None:
        if not self.path.startswith("/") or "*" in self.path:
            raise ValueError(f"a public route must be an exact absolute path, got {self.path!r}")
        if not self.methods:
            raise ValueError(f"public route {self.path!r} allows no method")


def safe_return_path(candidate: str) -> str:
    """Reduce a caller-influenced destination to a same-origin path, or to ``/``.

    Used wherever a redirect target is derived from a request. The allowlist is deliberately
    narrower than the URL grammar: anything that is not plainly a path on this origin becomes
    the root, because the cost of being wrong is an open redirect that lends this origin's
    credibility to somebody else's page.
    """
    value = (candidate or "").strip()
    if not value or len(value) > 512 or not _SAFE_PATH.match(value):
        return "/"
    return value


class ResolverRegistry:
    """The live set of authentication mechanisms the gate consults.

    A registry rather than a list argument because Starlette builds middleware instances when
    the application first serves, which is after the composition root has finished. Passing a
    registry lets a mechanism be registered at any point before the first request and still be
    seen, without reaching into a middleware instance that may not exist yet.
    """

    def __init__(self, resolvers: Iterable[PrincipalResolver] = ()) -> None:
        self._items: list[PrincipalResolver] = list(resolvers)

    def add(self, resolver: PrincipalResolver) -> None:
        self._items.append(resolver)

    def clear(self) -> None:
        self._items.clear()

    def __iter__(self):
        return iter(tuple(self._items))

    def __len__(self) -> int:
        return len(self._items)


async def _send_denial(send: Callable, challenge: tuple[bytes, bytes] | None) -> None:
    """Bare 401. No body, no reason, no hint about why it failed."""
    headers = [(b"content-length", b"0"), _NO_STORE]
    if challenge is not None:
        headers.append(challenge)
    await send({"type": "http.response.start", "status": 401, "headers": headers})
    await send({"type": "http.response.body", "body": b"", "more_body": False})


async def _send_probe(send: Callable, *, body: bool) -> None:
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(_PROBE_BODY)).encode("ascii")),
            _NO_STORE,
        ],
    })
    await send({
        "type": "http.response.body",
        "body": _PROBE_BODY if body else b"",
        "more_body": False,
    })


class AuthorizationGate:
    """Refuses every request that arrives without an authenticated principal.

    Args:
        app: The next ASGI callable.
        resolvers: Authentication mechanisms consulted, in order, when no principal is already
            on the scope. The first to return one wins. Empty means the only way in is a
            mechanism mounted further out, such as signed-request access.
        probe_path: The single unauthenticated path, or ``None`` for no public path at all.
        public_routes: Exact paths that may be reached without a principal, with the methods
            allowed on each. Registered in process by the composition root; never read from
            configuration, so no deployed value can publish a route.
        sign_in_path: Where a person is sent to sign in. When set, a top-level browser
            navigation to a protected non-API path is answered with a redirect there instead
            of a bare 401, so the application is usable by a human without publishing a byte
            of it. Everything else — every API call, every subresource, every non-browser
            client — still gets the bare 401.
        challenge: Optional ``WWW-Authenticate`` header to attach to refusals. ``None``: a
            challenge names the scheme and the tenant, which is a hint an anonymous caller has
            not earned, and the sign-in redirect already tells a browser what it needs.
    """

    def __init__(
        self,
        app: Callable,
        *,
        resolvers: Iterable[PrincipalResolver] = (),
        probe_path: str | None = PUBLIC_PROBE_PATH,
        public_routes: Iterable[PublicRoute] = (),
        sign_in_path: str | None = None,
        challenge: tuple[str, str] | None = None,
        scope_key: str = SCOPE_KEY,
    ) -> None:
        self._app = app
        # Held, not copied: a ResolverRegistry passed here stays live.
        self._resolvers = resolvers if isinstance(resolvers, ResolverRegistry) else list(resolvers)
        self._probe_path = probe_path
        self._public: dict[str, frozenset[str]] = {r.path: r.methods for r in public_routes}
        self._sign_in_path = sign_in_path
        self._scope_key = scope_key
        self._challenge = (
            (challenge[0].encode("latin-1"), challenge[1].encode("latin-1"))
            if challenge is not None
            else None
        )

    def add_resolver(self, resolver: PrincipalResolver) -> None:
        """Register an authentication mechanism. The primary-authentication seam.

        In-process only. Nothing reads a resolver name from configuration, so no deployed
        value can add one and no typo can remove the gate.
        """
        if isinstance(self._resolvers, ResolverRegistry):
            self._resolvers.add(resolver)
        else:
            self._resolvers.append(resolver)

    @property
    def resolvers(self) -> tuple[PrincipalResolver, ...]:
        return tuple(self._resolvers)

    async def __call__(self, scope: dict, receive: Callable, send: Callable) -> None:
        kind = scope.get("type")
        if kind == "lifespan":
            await self._app(scope, receive, send)
            return
        if kind == "websocket":
            # This application serves no websocket. Refusing here means adding one later is a
            # deliberate decision rather than an accidentally public endpoint.
            await send({"type": "websocket.close", "code": 1008})
            return
        if kind != "http":
            return

        method = str(scope.get("method", "")).upper()
        path = str(scope.get("path", ""))
        if (
            self._probe_path is not None
            and path == self._probe_path
            and method in _PROBE_METHODS
        ):
            await _send_probe(send, body=method == "GET")
            return

        if method in self._public.get(path, frozenset()):
            await self._app(scope, receive, _no_store(send))
            return

        principal = scope.get(self._scope_key)
        if principal is None:
            for resolve in self._resolvers:
                try:
                    principal = await resolve(scope)
                except Exception:
                    principal = None
                if principal is not None:
                    scope[self._scope_key] = principal
                    break

        if principal is None:
            if self._sign_in_path is not None and _is_page_navigation(scope, method, path):
                await _send_sign_in_redirect(send, self._sign_in_path, path)
                return
            await _send_denial(send, self._challenge)
            return

        await self._app(scope, receive, _no_store(send))


def _is_page_navigation(scope: Mapping[str, Any], method: str, path: str) -> bool:
    """Whether this is a person typing a URL, rather than a program or a subresource.

    Decided from ``Sec-Fetch-Mode``/``Sec-Fetch-Dest`` where the browser sends them, falling
    back to the ``Accept`` header for clients that do not. Getting it wrong in either
    direction is safe: a false negative is a bare 401, and a false positive is a redirect to a
    page that itself publishes nothing.
    """
    if method not in ("GET", "HEAD") or path.startswith(_API_PREFIX):
        return False
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in scope.get("headers", [])
    }
    mode = headers.get("sec-fetch-mode", "")
    dest = headers.get("sec-fetch-dest", "")
    if mode or dest:
        return mode == "navigate" and dest in ("document", "", "empty")
    return "text/html" in headers.get("accept", "")


async def _send_sign_in_redirect(send: Callable, sign_in_path: str, requested: str) -> None:
    """Send a browser to sign in, remembering only a same-origin path."""
    target = safe_return_path(requested)
    location = f"{sign_in_path}?return_to={quote(target, safe='')}"
    await send({
        "type": "http.response.start",
        "status": 303,
        "headers": [
            (b"location", location.encode("latin-1")),
            (b"content-length", b"0"),
            _NO_STORE,
        ],
    })
    await send({"type": "http.response.body", "body": b"", "more_body": False})


def _no_store(send: Callable) -> Callable:
    """Wrap ``send`` so every response past the gate refuses to be cached.

    Only the response-start message is touched, so streamed bodies pass through untouched and
    server-sent events keep arriving as they are produced.
    """

    async def wrapped(message: dict) -> None:
        if message.get("type") == "http.response.start":
            headers = [
                (name, value)
                for name, value in message.get("headers", [])
                if name.lower() != b"cache-control"
            ]
            headers.append(_NO_STORE)
            message = {**message, "headers": headers}
        await send(message)

    return wrapped
