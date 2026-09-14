"""Subscription-wide ARM access: generic reads, discovery, and estate search.

``ArmApi``            — ``GET`` any resource, any child collection, any KQL query.
``EstateDiscoverer``  — resource groups, resources, ARM child collections.
``EstateReader``      — one resource's ARM JSON, and full-text estate search.
``build_estate_access`` — every discoverer and reader a browser needs, wired once.
"""

from __future__ import annotations

from azdata.estate.access import EstateAccess, build_estate_access
from azdata.estate.armapi import (
    ARM_ENDPOINT,
    ARM_SCOPE,
    ArmApi,
    child_type_of,
    kql_literal,
    name_of,
    resource_group_of,
    subscription_of,
    type_of,
)
from azdata.estate.discover import EstateDiscoverer
from azdata.estate.read import EstateReader, redact_credentials

__all__ = [
    "ARM_ENDPOINT",
    "ARM_SCOPE",
    "ArmApi",
    "EstateAccess",
    "EstateDiscoverer",
    "EstateReader",
    "build_estate_access",
    "child_type_of",
    "kql_literal",
    "name_of",
    "redact_credentials",
    "resource_group_of",
    "subscription_of",
    "type_of",
]
