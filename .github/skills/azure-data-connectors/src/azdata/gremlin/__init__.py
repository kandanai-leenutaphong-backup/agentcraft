"""Cosmos DB Gremlin — read, write and deploy planes.

``read.py`` runs traversals, ``write.py`` mutates vertices and edges, and
``deploy.py`` provisions the Gremlin database and graph. The account
itself is provisioned through ``azdata.cosmos.deploy``: the Gremlin
capability is account-level. ``discover.py`` lists databases and graphs
from the management plane, so it opens no WebSocket.
"""

from __future__ import annotations

from azdata.gremlin.deploy import GremlinDatabaseProvisioner, GremlinGraphProvisioner
from azdata.gremlin.discover import GremlinDiscoverer
from azdata.gremlin.observe import GremlinStats
from azdata.gremlin.read import GremlinConnector, GremlinTarget
from azdata.gremlin.verify import GremlinKeys, GremlinVerifyError
from azdata.gremlin.write import GremlinElements, GremlinWriteError

__all__ = [
    "GremlinConnector",
    "GremlinDatabaseProvisioner",
    "GremlinDiscoverer",
    "GremlinElements",
    "GremlinGraphProvisioner",
    "GremlinKeys",
    "GremlinStats",
    "GremlinTarget",
    "GremlinVerifyError",
    "GremlinWriteError",
]
