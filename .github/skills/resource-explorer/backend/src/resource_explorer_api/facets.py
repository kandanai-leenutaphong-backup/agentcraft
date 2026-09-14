"""What one resource opens into. The hierarchy decision, in one table.

WHY A TABLE AND NOT A CHAIN OF ``if``
-------------------------------------
Twenty-six resource types exist in the estate today and the number only goes
up. A table keyed by ARM type says, in one screen, exactly what the tree
shows for each of them and exactly what it does not — and adding the next
type is a row, not a code path.

THE UNIVERSAL LEAF IS WHY THIS IS GENERAL
-----------------------------------------
Every resource, of every type, known or not, gets a ``properties`` leaf
holding its complete ARM JSON. Sixteen of the twenty-six types have no
richer data plane; for them ARM's own document *is* the content, and a
browser that showed only a name would have thrown away what the operator
opened the node for. A type absent from this table is therefore still fully
browsable — it just has nothing below the universal leaf.

TWO KINDS OF FACET
------------------
An **ARM collection** is ``GET {resourceId}/{collection}``, which every
provider implements identically. Container-app revisions, job executions,
Cognitive Services deployments, storage queues and Key Vault secret *names*
are all the same call with a different path.

A **data-plane branch** is a service-specific enumeration — blob containers,
Cosmos databases, Search indexes, Kusto databases, Log Analytics tables,
registry repositories. It costs a different SDK and a different grant, and it
is the only way to reach actual contents.

WHY BOTH COSMOS BRANCHES ALWAYS APPEAR
--------------------------------------
An account's API is not reliably readable from its ARM type: the same type
serves NoSQL and Gremlin, and the distinguishing capability is buried in the
property bag. Showing both branches and letting the wrong one answer
``empty`` is honest and costs one call; guessing is neither.

KEY VAULT IS NAMES ONLY
-----------------------
``secrets`` and ``keys`` list *metadata* from the management plane. Secret
values need a data-plane ``GET`` this component never issues, and the
standing instruction forbids reading one into the tree at all.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The service that means "an ARM child collection", as opposed to a
#: service-specific data plane.
ARM = "estate"


@dataclass(frozen=True, slots=True)
class Facet:
    """One branch under a resource.

    ``level`` is the coordinate the branch expands at, and it is also what the
    node id carries — so a facet stub is minted without any call at all.
    """

    label: str
    service: str
    level: str
    collection: str = ""


def arm(label: str, collection: str) -> Facet:
    return Facet(label=label, service=ARM, level="collection", collection=collection)


#: Keyed by lowercased ARM type. Serves resources and ARM children alike:
#: a container-app revision is looked up by
#: ``microsoft.app/containerapps/revisions`` exactly as its parent is looked
#: up by ``microsoft.app/containerapps``.
FACETS_BY_TYPE: dict[str, tuple[Facet, ...]] = {
    "microsoft.storage/storageaccounts": (
        Facet("Blob containers", "blob", "account"),
        arm("Tables", "tableServices/default/tables"),
        arm("Queues", "queueServices/default/queues"),
        arm("File shares", "fileServices/default/shares"),
    ),
    "microsoft.documentdb/databaseaccounts": (
        Facet("SQL databases", "cosmos", "account"),
        Facet("Gremlin databases", "gremlin", "account"),
    ),
    "microsoft.search/searchservices": (Facet("Indexes", "search", "service"),),
    "microsoft.kusto/clusters": (Facet("Databases", "kusto", "cluster"),),
    "microsoft.operationalinsights/workspaces": (
        Facet("Log tables", "logs", "workspace"),
    ),
    "microsoft.containerregistry/registries": (
        Facet("Repositories", "acr", "registry"),
    ),
    "microsoft.app/containerapps": (arm("Revisions", "revisions"),),
    "microsoft.app/containerapps/revisions": (arm("Replicas", "replicas"),),
    "microsoft.app/jobs": (arm("Executions", "executions"),),
    "microsoft.app/managedenvironments": (
        arm("Certificates", "certificates"),
        arm("Storages", "storages"),
    ),
    "microsoft.cognitiveservices/accounts": (
        arm("Model deployments", "deployments"),
        arm("Projects", "projects"),
    ),
    "microsoft.keyvault/vaults": (
        arm("Secrets (names only)", "secrets"),
        arm("Keys (names only)", "keys"),
    ),
    "microsoft.network/virtualnetworks": (arm("Subnets", "subnets"),),
    "microsoft.network/networksecuritygroups": (
        arm("Security rules", "securityRules"),
    ),
    "microsoft.eventgrid/systemtopics": (
        arm("Event subscriptions", "eventSubscriptions"),
    ),
}


def facets_for(resource_type: str) -> tuple[Facet, ...]:
    """The branches one type opens into. Unknown types open into none."""
    return FACETS_BY_TYPE.get(str(resource_type or "").lower(), ())


__all__ = ["ARM", "FACETS_BY_TYPE", "Facet", "arm", "facets_for"]
