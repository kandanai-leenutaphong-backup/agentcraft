"""One seam for subscription-wide browsing: discoverers plus content readers.

WHY A BUNDLE AND NOT EIGHT CONSTRUCTORS
---------------------------------------
A browser over a whole subscription needs eight discoverers and six content
readers, and four of them must share one :class:`~azdata.estate.armapi.ArmApi`
or they each resolve api-versions and mint tokens again. Handing the consumer
a list of constructors makes that sharing its problem, and the first consumer
that forgets pays for it in round trips.

:func:`build_estate_access` is therefore the whole plane in one call, with the
ARM client shared and every credential lazy.

WHY NOT ``build_discovery_registry``
------------------------------------
That function registers the five service-addressed discoverers a caller
configured by name, and its service set is part of its contract. This one
registers the eight a subscription-wide browser walks, addressed by resource
id. Two different questions, two functions, and neither breaks the other.

CONSTRUCTION PERFORMS NO I/O
----------------------------
Not one client is built and not one token is minted here — the discover
plane's invariant 7, extended to the content plane, and what lets a health
check construct this object.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from azdata.core.discover import DiscovererRegistry
from azdata.estate.armapi import ArmApi
from azdata.estate.read import EstateReader


@dataclass(frozen=True)
class EstateAccess:
    """Everything a subscription-wide browser calls, wired once.

    ``discoverers`` answers "what is here"; the readers answer "what does it
    say". The tree that composes them owns the hierarchy; nothing in this
    bundle knows one exists.
    """

    discoverers: DiscovererRegistry
    arm: ArmApi
    properties: EstateReader
    blob: Any
    cosmos: Any
    kusto: Any
    search: Any
    logs: Any

    def discoverer(self, service: str) -> Any:
        return self.discoverers.get(service)


def build_estate_access(
    config: Any,
    credential_provider: Callable[[], Any] | None = None,
    *,
    arm: ArmApi | None = None,
) -> EstateAccess:
    """Register every discoverer and reader a subscription browser needs.

    Services registered: ``estate``, ``blob``, ``search``, ``cosmos``,
    ``gremlin``, ``kusto``, ``logs``, ``acr``. A service whose coordinates are
    empty is still registered and answers ``unconfigured``, because a consumer
    has to be able to show *why* a branch is dark.
    """
    from azdata.blobs.read import BlobReader
    from azdata.cosmos.content import CosmosReader
    from azdata.cosmos.discover import CosmosDiscoverer
    from azdata.core.credentials import credential_provider_for
    from azdata.estate.discover import EstateDiscoverer
    from azdata.gremlin.discover import GremlinDiscoverer
    from azdata.kusto.content import KustoReader
    from azdata.kusto.discover import KustoDiscoverer
    from azdata.logs.read import LogsDiscoverer, LogsReader
    from azdata.registry.discover import RegistryDiscoverer
    from azdata.search.content import SearchReader
    from azdata.search.discover import SearchDiscoverer
    from azdata.blobs.discover import BlobDiscoverer

    provider = credential_provider or credential_provider_for(config)
    client = arm or ArmApi(credential_provider=provider)

    registry = DiscovererRegistry()
    registry.register(
        EstateDiscoverer.from_config(config, provider, arm=client)
    )
    registry.register(BlobDiscoverer.from_config(config, provider))
    registry.register(SearchDiscoverer.from_config(config, provider))
    registry.register(CosmosDiscoverer.from_config(config, provider))
    registry.register(GremlinDiscoverer.from_config(config, provider))
    registry.register(KustoDiscoverer.from_config(config, provider))
    registry.register(LogsDiscoverer.from_config(config, provider, arm=client))
    registry.register(RegistryDiscoverer.from_config(config, provider, arm=client))

    return EstateAccess(
        discoverers=registry,
        arm=client,
        properties=EstateReader(
            arm=client, subscription_id=getattr(config, "subscription_id", "")
        ),
        blob=BlobReader(credential_provider=provider),
        cosmos=CosmosReader(credential_provider=provider),
        kusto=KustoReader(credential_provider=provider),
        search=SearchReader(credential_provider=provider),
        logs=LogsReader(arm=client),
    )


__all__ = ["EstateAccess", "build_estate_access"]
