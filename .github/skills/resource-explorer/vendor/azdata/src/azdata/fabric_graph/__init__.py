"""Fabric GraphModel — read and observe planes, and two permanent absences.

``read.py`` runs GQL over HTTPS against a published GraphModel, and
``observe.py`` reports its schema metadata and the last GQL status code.

**No deploy plane, ever.** A Fabric GraphModel is a workspace item created
through the Fabric control plane, not an ARM resource. It has no resource
ID, cannot be placed in a resource group, and no ARM template or
management SDK can create one. A ``Provisioner`` for it is not missing
work; it is impossible. Creation stays a Fabric-side act.

**No write plane.** The GQL surface exposed to this connector is read-only:
mutations go through the Fabric item that backs the model, not through the
query endpoint.

**No verify plane, and that follows.** Verification exists to answer *what
changed after my operation*. Nothing here performs an operation that can
change anything, so there is no delta to take and no addressable key space
to enumerate — a GraphModel is a projection over data that lives in the
lakehouse behind it, and the keys worth diffing belong to that store, not
to the model. A ``KeySource`` here would enumerate somebody else's state
and attribute it to this connector.
"""

from __future__ import annotations

from azdata.fabric_graph.observe import GraphStats
from azdata.fabric_graph.read import GraphConnector, GraphRetryBudget

__all__ = [
    "GraphConnector",
    "GraphRetryBudget",
    "GraphStats",
]
