"""Cosmos DB NoSQL — read, write, deploy, observe and verify planes.

``read.py`` queries a container, ``write.py`` mutates items in one,
``deploy.py`` provisions the account, database and container,
``observe.py`` reports counts, container shape and RU signal,
``verify.py`` enumerates ids and etags so a change can be diffed, and
``discover.py`` lists databases and containers from the management plane.
"""

from __future__ import annotations

from azdata.cosmos.deploy import (
    CosmosAccountProvisioner,
    CosmosContainerProvisioner,
    CosmosDatabaseProvisioner,
)
from azdata.cosmos.discover import CosmosDiscoverer
from azdata.cosmos.observe import CosmosStats
from azdata.cosmos.read import CosmosContainer, CosmosUnavailable
from azdata.cosmos.verify import CosmosKeys
from azdata.cosmos.write import CosmosItems

__all__ = [
    "CosmosAccountProvisioner",
    "CosmosContainer",
    "CosmosContainerProvisioner",
    "CosmosDatabaseProvisioner",
    "CosmosDiscoverer",
    "CosmosItems",
    "CosmosKeys",
    "CosmosStats",
    "CosmosUnavailable",
]
