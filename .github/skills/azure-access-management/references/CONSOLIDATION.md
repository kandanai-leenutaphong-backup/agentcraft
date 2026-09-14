# Consolidation Record

Status: in progress, 2026-09-15. This records the explicitly requested consolidation,
not permission for Azure changes, authentication bypasses or application migration.

## Destination

One native skill remains: `azure-access-management`. Its directory is rebuilt in place
because the requested canonical name is also one of the source names. The old standalone
entry is replaced, not retained as a second skill. Other source skill directories and the
access-library experiment are retired after their useful content and checks are preserved.

## Scope

- Catalogue every distinct outcome and public behavior from API authentication, embedded
  browser/session authentication, access administration, managed-identity infrastructure
  and Container Apps authentication.
- Prefer official authentication libraries, Easy Auth, PIM, deployment approvals and IaC
  lifecycle owners where they meet the requirement. A helper is not a complete orchestrator.
- Preserve incompatible `entraauth` and `entra_auth` contracts as clearly labelled
  compatibility packages until host migration proves equivalence. Do not weaken their
  policies or delete positive/refusal tests merely to simplify discovery.
- Keep useful `azaccess` policy/evidence helpers and their existing CLI/MCP contracts;
  local confirmations are not independent human approval or an Azure permission grant.
- Preserve Bicep modules, compiled artifact, verifier and failure knowledge as integration
  assets, not another Python resource-provisioning library.
- Preserve the SDK comparison as offline evidence, not production support. Its library
  directory and workspace-only dependency group will be retired.
- Investigate native frontend sign-in as guidance. The local investigation application
  and its authentication component remain unchanged by this filesystem consolidation.

## Checks Before Retirement

1. Capture a recoverable baseline outside the workspace and freeze old-path dispositions.
2. Populate the capability inventory with native equivalents, retained helpers, task
   scripts, source references, consumers, verification commands and honest status.
3. Run retained package tests, entry-point/reference checks and standalone skill checks.
4. Update catalogue discovery, dependent guidance and workspace metadata without altering
   other library owners' source or dependencies.
5. Remove only the named source trees, then repeat reference and consumer checks.

The final record will state observed counts, checks, recovery location and unresolved
live acceptance. Offline evidence does not prove Azure permissions or deployed sign-in.
