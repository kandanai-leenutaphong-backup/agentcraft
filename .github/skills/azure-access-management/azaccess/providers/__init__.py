"""Plane adapters. One module per assignment plane, one plane per module.

Every adapter answers the same four questions — list, create, delete, and what
it supports — but the five planes are deliberately not forced into one class
hierarchy beyond :class:`~azaccess.providers.base.Provider`, because they really
do differ: Azure RBAC create is idempotent and Cosmos SQL create is not, Kusto
addresses assignments under the database, Microsoft Graph is the directory
plane, and SQL is not an Azure resource at all.
"""

from azaccess.providers.arm import ArmRbacProvider
from azaccess.providers.base import Provider, page_values
from azaccess.providers.cosmos import CosmosSqlRbacProvider
from azaccess.providers.graph import (
    GraphAppRoleProvider,
    federated_credential_request,
    group_member_add_request,
    group_member_remove_request,
    refuse_membership_url_without_ref,
)
from azaccess.providers.kusto import KustoDatabaseProvider
from azaccess.providers.sql import SqlDatabaseUserProvider, sql_grant_statements

__all__ = [
    "ArmRbacProvider",
    "CosmosSqlRbacProvider",
    "GraphAppRoleProvider",
    "KustoDatabaseProvider",
    "Provider",
    "SqlDatabaseUserProvider",
    "federated_credential_request",
    "group_member_add_request",
    "group_member_remove_request",
    "page_values",
    "refuse_membership_url_without_ref",
    "sql_grant_statements",
]
