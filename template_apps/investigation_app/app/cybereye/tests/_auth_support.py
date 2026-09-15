"""Test authentication: drive the real gate rather than bypassing it.

The application denies every request that arrives without a principal, and there is no
environment variable that changes that — deliberately, so a typo cannot open the door. Tests
therefore authenticate the same way Microsoft Entra ID will: by registering a principal
resolver in process.

That is not a back door. A resolver is a Python callable registered by code inside the
process; no header, no configuration value and no request can introduce one. A test that wants
to see the gate refuse uses :func:`anonymous` and gets exactly what a stranger gets.
"""

from __future__ import annotations

from contextlib import contextmanager

from app.cybereye.backend.security import (
    ISSUER_SIGNED_DEV,
    KIND_SERVICE,
    Principal,
    register_principal_resolver,
)

#: The identity most tests run as. Shaped like a real signed-access identity so ownership
#: assertions exercise the same namespace production uses.
DEFAULT = Principal(
    id="devkey:testfingerprint:default",
    kind=KIND_SERVICE,
    issuer=ISSUER_SIGNED_DEV,
    display="test caller",
)

OTHER = Principal(
    id="devkey:testfingerprint:other",
    kind=KIND_SERVICE,
    issuer=ISSUER_SIGNED_DEV,
    display="second test caller",
)


class _Current:
    principal: Principal | None = DEFAULT


_current = _Current()
_installed: set[int] = set()


async def _resolver(_scope) -> Principal | None:
    return _current.principal


def install(app) -> None:
    """Register the test resolver on an application, once."""
    if id(app) not in _installed:
        register_principal_resolver(app, _resolver)
        _installed.add(id(app))


@contextmanager
def as_principal(principal: Principal):
    """Run the block as ``principal``."""
    previous = _current.principal
    _current.principal = principal
    try:
        yield principal
    finally:
        _current.principal = previous


@contextmanager
def anonymous():
    """Run the block with no principal at all — what an unauthenticated stranger sees."""
    with as_principal(None):  # type: ignore[arg-type]
        yield
