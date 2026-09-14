"""Subscription-wide discovery — resource groups, resources, ARM children.

WHY THIS EXISTS
---------------
:class:`~azdata.arm.discover.ArmDiscoverer` answers "what is in this resource
group". A filesystem-grade browser needs three more answers, and all three
have to hold for resource types nobody enumerated in advance:

* what resource groups exist in this subscription;
* what resources are in one of them, without a per-provider client;
* what child objects one arbitrary resource has, again without one.

Resource Graph answers the first two in a single POST each. The third is
``GET {resourceId}/{collection}``, which every ARM provider implements the
same way and which therefore covers container-app revisions, job executions,
Cognitive Services deployments, Key Vault secret *names*, Kusto databases,
Cosmos databases and storage containers with one code path.

WHICH COLLECTIONS EXIST IS NOT DECIDED HERE
-------------------------------------------
This module will list any collection it is asked for. Which collections a
type is worth expanding is a hierarchy decision, and a library that owned it
would force the shape on the next consumer. The caller names the collection.

DEPENDENCIES
------------
``httpx`` (``graph`` extra), through :class:`~azdata.estate.armapi.ArmApi`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from azdata.core.config import AzureDataConfig
from azdata.core.discover import (
    DiscoveryBounds,
    DiscoveryNode,
    DiscoveryResult,
    DiscoveryScope,
    bounded_discovery,
    discovery_failure,
    normalize_attributes,
)
from azdata.estate.armapi import ArmApi, kql_literal, name_of, type_of

#: Resource groups plus the resource count in each, in one query. The join is
#: on a lowered name because ``Resources.resourceGroup`` is lowercased by the
#: service while ``ResourceContainers.name`` preserves the operator's casing.
RESOURCE_GROUPS_QUERY = """
ResourceContainers
| where type =~ 'microsoft.resources/subscriptions/resourcegroups'
| project id, name, location, key = tolower(name)
| join kind=leftouter (
    Resources | summarize resources = count() by key = tolower(resourceGroup)
  ) on key
| project id, name, location, resources
| order by name asc
"""

#: Every resource in one group, ordered so the tree groups by type for free.
RESOURCES_IN_GROUP_QUERY = """
Resources
| where tolower(resourceGroup) == tolower({group})
| project id, name, type, location, kind, skuName = tostring(sku.name)
| order by type asc, name asc
"""


class EstateDiscoverer:
    """Resource groups, resources, and any resource's ARM child collections.

    Args:
        subscription_id: Fallback when the scope does not carry one.
        credential_provider: Called on the first ``discover``, never at
            construction.
        arm: Injected for tests; built from the credential provider otherwise.
    """

    service = "estate"
    levels = ("subscription", "resource_group", "collection")

    _CHILD_LEVEL = {
        "subscription": "resource_group",
        "resource_group": "collection",
        "collection": None,
    }

    def __init__(
        self,
        *,
        subscription_id: str = "",
        credential_provider: Callable[[], Any],
        arm: ArmApi | None = None,
    ) -> None:
        self._subscription_id = subscription_id
        self._arm = arm or ArmApi(credential_provider=credential_provider)

    @classmethod
    def from_config(
        cls,
        config: AzureDataConfig,
        credential_provider: Callable[[], Any],
        **kwargs: Any,
    ) -> "EstateDiscoverer":
        return cls(
            subscription_id=config.subscription_id,
            credential_provider=credential_provider,
            **kwargs,
        )

    @property
    def arm(self) -> ArmApi:
        """The shared ARM client, so a caller need not build a second one."""
        return self._arm

    def child_level(self, level: str) -> str | None:
        return self._CHILD_LEVEL.get(level)

    async def discover(
        self,
        level: str,
        scope: DiscoveryScope,
        *,
        bounds: DiscoveryBounds = DiscoveryBounds(),
    ) -> DiscoveryResult:
        """Enumerate one level. Never raises."""
        if level not in self.levels:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unavailable",
                detail=f"unknown level '{level}' for service estate",
            )
        subscription_id = scope.subscription_id or self._subscription_id
        if not subscription_id:
            return discovery_failure(
                service=self.service,
                level=level,
                scope=scope,
                status="unconfigured",
                detail="estate discovery not configured: subscription_id",
            )

        if level == "subscription":
            collect = self._resource_groups(subscription_id, bounds)
        elif level == "resource_group":
            group = scope.path[0] if scope.path else ""
            if not group:
                return discovery_failure(
                    service=self.service,
                    level=level,
                    scope=scope,
                    status="unconfigured",
                    detail="estate discovery not configured: resource group",
                )
            collect = self._resources(subscription_id, group, bounds)
        else:
            resource_id = scope.path[0] if scope.path else ""
            collection = scope.path[1] if len(scope.path) > 1 else ""
            if not resource_id or not collection:
                return discovery_failure(
                    service=self.service,
                    level=level,
                    scope=scope,
                    status="unconfigured",
                    detail="estate discovery not configured: resource id and collection",
                )
            collect = self._children(resource_id, collection, bounds)

        return await bounded_discovery(
            service=self.service,
            level=level,
            scope=scope,
            bounds=bounds,
            collect=collect,
        )

    # -- level implementations ---------------------------------------------

    def _resource_groups(
        self, subscription_id: str, bounds: DiscoveryBounds
    ) -> Callable[[], Iterator[DiscoveryNode]]:
        def collect() -> Iterator[DiscoveryNode]:
            try:
                rows = self._arm.resource_graph(
                    RESOURCE_GROUPS_QUERY,
                    subscriptions=(subscription_id,),
                    top=bounds.max_items + 1,
                )
            except Exception:  # noqa: BLE001 - Resource Graph is an optimisation
                # A subscription without the Resource Graph provider still has
                # resource groups; losing the counts is better than losing the
                # tree.
                rows = [
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "location": item.get("location"),
                        "resources": None,
                    }
                    for item in self._arm.list_resource_groups(subscription_id)
                ]
            for index, row in enumerate(rows):
                if index > bounds.max_items:
                    return
                name = str(row.get("name") or "")
                if not name:
                    continue
                yield DiscoveryNode(
                    kind="resource_group",
                    name=name,
                    path=(name,),
                    has_children=True,
                    attributes=normalize_attributes(
                        {
                            "id": row.get("id"),
                            "location": row.get("location"),
                            "resources": row.get("resources"),
                        }
                    ),
                )

        return collect

    def _resources(
        self, subscription_id: str, group: str, bounds: DiscoveryBounds
    ) -> Callable[[], Iterator[DiscoveryNode]]:
        query = RESOURCES_IN_GROUP_QUERY.replace("{group}", kql_literal(group))

        def collect() -> Iterator[DiscoveryNode]:
            try:
                rows = self._arm.resource_graph(
                    query,
                    subscriptions=(subscription_id,),
                    top=bounds.max_items + 1,
                )
            except Exception:  # noqa: BLE001 - fall back to the ARM listing
                rows = [
                    {
                        "id": item.get("id"),
                        "name": item.get("name"),
                        "type": item.get("type"),
                        "location": item.get("location"),
                        "kind": item.get("kind"),
                        "skuName": (item.get("sku") or {}).get("name")
                        if isinstance(item.get("sku"), dict)
                        else None,
                    }
                    for item in self._arm.list_resources(subscription_id, group)
                ]
            for index, row in enumerate(rows):
                if index > bounds.max_items:
                    return
                yield _resource_node(row)

        return collect

    def _children(
        self, resource_id: str, collection: str, bounds: DiscoveryBounds
    ) -> Callable[[], Iterator[DiscoveryNode]]:
        def collect() -> Iterator[DiscoveryNode]:
            items = self._arm.list_children(resource_id, collection)
            for index, item in enumerate(items):
                if index > bounds.max_items:
                    return
                yield _child_node(resource_id, collection, item)

        return collect


def _resource_node(row: dict[str, Any]) -> DiscoveryNode:
    """One ARM resource.

    Tags are omitted for the same reason
    :mod:`azdata.arm.discover` omits them: they are operator free text and a
    plausible secret carrier, and a browsable inventory does not need them.
    """
    resource_id = str(row.get("id") or "")
    return DiscoveryNode(
        kind="resource",
        name=str(row.get("name") or name_of(resource_id)),
        path=(resource_id,),
        has_children=True,
        attributes=normalize_attributes(
            {
                "id": resource_id,
                "type": row.get("type") or type_of(resource_id),
                "location": row.get("location"),
                "kind": row.get("kind"),
                "sku": row.get("skuName"),
            }
        ),
    )


def _child_node(
    resource_id: str, collection: str, item: dict[str, Any]
) -> DiscoveryNode:
    """One item of an ARM child collection.

    Only scalar top-level fields plus a small, fixed set of well-known
    ``properties`` entries are surfaced. The whole property bag is available
    through the content plane; copying it into every node would put a
    kilobyte of JSON behind each label.
    """
    child_id = str(item.get("id") or "")
    name = str(item.get("name") or name_of(child_id) or "(unnamed)")
    properties = item.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    attributes: dict[str, Any] = {
        "id": child_id,
        "type": item.get("type"),
        "collection": collection,
    }
    for key in (
        "active",
        "createdTime",
        "creationDate",
        "endTime",
        "enabled",
        "healthState",
        "lastModified",
        "model",
        "provisioningState",
        "replicas",
        "runningState",
        "startTime",
        "status",
        "trafficWeight",
        "updated",
    ):
        value = properties.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            if value is not None:
                attributes[key] = value
    return DiscoveryNode(
        kind="arm_child",
        name=name,
        path=(resource_id, collection, name),
        has_children=False,
        attributes=normalize_attributes(attributes),
    )


__all__ = [
    "RESOURCES_IN_GROUP_QUERY",
    "RESOURCE_GROUPS_QUERY",
    "EstateDiscoverer",
]
