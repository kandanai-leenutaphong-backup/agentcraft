"""Azure access management: inspect, plan, diff, apply, verify, revoke.

One import, one call site:

    from azaccess import AccessManager, bounded_policy, IdentityRef

    manager = AccessManager(providers, policy=bounded_policy(
        tenant_id=tenant, scopes=[resource_group_id], max_tier="read"))
    plan = manager.plan(declarations)          # read-only, refusals included
    report = manager.apply(plan, confirmations=tokens)
    results = manager.verify(declarations)

Five assignment planes, deliberately not conflated: Azure RBAC, Cosmos DB SQL
role assignments, Azure Data Explorer database principal assignments, contained
SQL database users, and Microsoft Graph for directory-plane app role
assignments. Only the first is what ``role assignment list`` shows, which
is why a revocation that walks only that plane leaves data access intact.

Standard library only. Live transports are the Azure CLI (``az rest``) or any
``TokenCredential`` the host already holds; no key, connection string, or
persisted secret is read or written anywhere in this package.
"""

from azaccess.authorization import (
    AuthorityPolicy,
    ConfirmationLedger,
    bounded_policy,
    refuse_embedded_authority,
)
from azaccess.conditions import (
    CONDITION_VERSION,
    SUPPORTED_CONDITION_VERSIONS,
    blob_tag_condition,
    container_name_condition,
    require_condition,
)
from azaccess.endpoints import (
    AZURE_CHINA_CLOUD,
    AZURE_PUBLIC_CLOUD,
    AZURE_US_GOVERNMENT,
    CloudEndpoints,
    cloud_by_name,
)
from azaccess.engine import AccessManager
from azaccess.errors import (
    AccessError,
    AuthenticationError,
    AuthorizationRefused,
    CoordinateError,
    OperationPending,
    PolicyRevertSuspected,
    ProviderConflict,
    TransportError,
)
from azaccess.identity import IdentityRef, user_assigned_identity
from azaccess.ledger import OwnershipLedger
from azaccess.matrix import MatrixRow, render_matrix, support_matrix
from azaccess.model import (
    AccessDeclaration,
    ApplyReport,
    AssignmentState,
    Completeness,
    DiffReport,
    EffectiveAccess,
    OwnershipRecord,
    Plan,
    PlanStep,
    RevokeReport,
    UNEVALUATED_SEMANTICS,
    VerificationResult,
    declarations_from_records,
)
from azaccess.planner import Planner
from azaccess.probe import AccessProbe, ProbeResult
from azaccess.providers import (
    ArmRbacProvider,
    CosmosSqlRbacProvider,
    GraphAppRoleProvider,
    KustoDatabaseProvider,
    SqlDatabaseUserProvider,
    federated_credential_request,
    group_member_add_request,
    group_member_remove_request,
    refuse_membership_url_without_ref,
    sql_grant_statements,
)
from azaccess.providers.sql import (
    RecordingSqlExecutor,
    quote_identifier,
    quote_literal,
    quote_principal_identifier,
)
from azaccess.roles import (
    BUILTIN_ROLES,
    READER_ROLE_FOR_SERVICE,
    TIERS,
    RoleDefinition,
    lookup_role,
    register_role,
    role_identity_matches,
)
from azaccess.scopes import Scope, normalize_scope
from azaccess.transport import (
    UNKNOWN_STATUS,
    AzureCliTransport,
    RecordingTransport,
    Response,
    TokenCredentialTransport,
    sanitize_detail,
    status_from_cli_error,
)

__version__ = "1.1.0"

__all__ = [
    "AZURE_CHINA_CLOUD",
    "AZURE_PUBLIC_CLOUD",
    "AZURE_US_GOVERNMENT",
    "AccessDeclaration",
    "AccessError",
    "AccessManager",
    "AccessProbe",
    "ApplyReport",
    "ArmRbacProvider",
    "AssignmentState",
    "AuthenticationError",
    "AuthorityPolicy",
    "AuthorizationRefused",
    "AzureCliTransport",
    "BUILTIN_ROLES",
    "CloudEndpoints",
    "Completeness",
    "ConfirmationLedger",
    "CoordinateError",
    "CosmosSqlRbacProvider",
    "DiffReport",
    "EffectiveAccess",
    "GraphAppRoleProvider",
    "IdentityRef",
    "KustoDatabaseProvider",
    "MatrixRow",
    "OperationPending",
    "OwnershipLedger",
    "OwnershipRecord",
    "Plan",
    "PlanStep",
    "Planner",
    "PolicyRevertSuspected",
    "ProbeResult",
    "ProviderConflict",
    "READER_ROLE_FOR_SERVICE",
    "RecordingSqlExecutor",
    "RecordingTransport",
    "Response",
    "RevokeReport",
    "RoleDefinition",
    "Scope",
    "SqlDatabaseUserProvider",
    "TIERS",
    "TokenCredentialTransport",
    "TransportError",
    "UNEVALUATED_SEMANTICS",
    "UNKNOWN_STATUS",
    "VerificationResult",
    "__version__",
    "bounded_policy",
    "cloud_by_name",
    "declarations_from_records",
    "federated_credential_request",
    "blob_tag_condition",
    "container_name_condition",
    "require_condition",
    "CONDITION_VERSION",
    "SUPPORTED_CONDITION_VERSIONS",
    "group_member_add_request",
    "group_member_remove_request",
    "lookup_role",
    "normalize_scope",
    "quote_identifier",
    "quote_literal",
    "quote_principal_identifier",
    "refuse_embedded_authority",
    "refuse_membership_url_without_ref",
    "register_role",
    "render_matrix",
    "role_identity_matches",
    "sanitize_detail",
    "sql_grant_statements",
    "status_from_cli_error",
    "support_matrix",
    "user_assigned_identity",
]
