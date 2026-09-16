---
name: azure-access-management
description: "Use for Azure access and identity workflows: Entra API JWT
  validation and record ownership, browser/session PKCE and Container Apps
  frontend sign-in, native Easy Auth/MSAL, managed identity and Bicep/AVM, PIM
  and deployment approvals, RBAC and Cosmos/ADX/SQL/Graph permissions, 401/403
  diagnosis, exact-scope verification and owned cleanup. Native administrative
  procedures only; installed entra_auth and signed_dev_access own auth
  mechanisms. Plans never execute commands or grant authority; cloud mutations
  need explicit target-bound authorization. Replaces the former separate
  entra-api-auth, entra-auth-container-apps and bicep-managed-identity entries;
  no azaccess engine or MCP runtime."
license: MIT
---

# Azure Access And Identity

Read the [canonical guide](../../../libraries/entra-auth/docs/skills/azure-access-management.md)
and [native administrative procedures](../../../libraries/entra-auth/docs/skills/native-access-workflows.md).
Use installed `entra-auth` (`entra_auth`) for strict token/PKCE/store mechanisms
and canonical `signed_dev_access` for request signatures. Hosts own authorization,
sessions and deployment. `azaccess`, legacy auth helpers and MCP runtimes are
retired; this entry grants no credentials, inference, role or resource mutation.
