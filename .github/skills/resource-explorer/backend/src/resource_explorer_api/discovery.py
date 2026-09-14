"""Which access bundle this process talks to. One decision, made at startup.

Fixture mode is chosen here rather than inside the tree composer so that
exactly one object in the process knows whether the estate is real, and the
``fixtures`` flag on every response is read from the same fact.

Construction performs no I/O and builds no credential — that is the discover
plane's invariant, and it is what lets a health check exist at all.
"""

from __future__ import annotations

from typing import Any

from azdata import build_estate_access, credential_provider_for

from resource_explorer_api.fixtures import build_fixture_access
from resource_explorer_api.settings import Settings


def build_access(settings: Settings) -> Any:
    """The real subscription, or the fixture one. Never a mix."""
    if settings.fake_discovery:
        return build_fixture_access()
    return build_estate_access(settings.azure, credential_provider_for(settings.azure))


__all__ = ["build_access"]
