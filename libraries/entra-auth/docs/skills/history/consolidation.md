# Consolidation Record

Status: filesystem consolidation and offline verification complete, 2026-09-15.
This records the explicitly requested consolidation,
not permission for Azure changes, authentication bypasses or application migration.

## Destination

One native skill remains: `azure-access-management`. Its directory is rebuilt in place
because the requested canonical name is also one of the source names. The old standalone
entry is replaced, not retained as a second skill. Other source skill directories and the
access-library experiment are retired after their useful content and checks were preserved.

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
  directory and workspace-only dependency group are retired; dependencies now belong to
  the skill's `sdk-comparison` development group.
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

## Observed Results

| Check | Observed Result |
| --- | --- |
| Capability inventory | 68 entries across API auth, strict browser/session auth, access, workload identity, Container Apps and SDK evidence; each has native comparison, disposition, source and check route |
| Original-file dispositions | 131 original records: 101 preserved destinations and 30 archived-only generated/superseded artifacts |
| Mechanism preservation | 62 Python/Bicep source files match their original SHA-256; the retained Bicep self-test changed only its missing-artifact repair instruction |
| Original directories retired | Three top-level source skills and the access-library experiment are absent; canonical `azure-access-management` rebuilt in place |
| Native discovery | 29 capability skills, 8 protocols and 5 embedded entries; four legacy lookup aliases resolve to the canonical entry |
| API auth | 164 checks passed before relocation, after relocation and after source retirement |
| Strict browser/session auth | 68 tests passed before relocation, after relocation and after source retirement |
| Retained access helper | 271 checks passed; transport suite: 35 checks passed |
| Native-workflow planner | 9 tests passed, including complete catalogue integrity, authority/secret refusal and no automatic anonymous fallback |
| SDK evidence | 11 tests passed at the new location; test-only synthetic transport, no live Azure calls |
| Bicep source/artifact | Rebuilt missing original artifact with Bicep 0.40.2; 62 checks passed, including source/render comparison |
| MCP contract | Fixture SDK smoke passed; same five tools and no mutation/confirmation tools |
| Named external consumer | Signed-access composition imports retained `entraauth`, grants no implicit scopes/roles and refuses another owner's record |
| Standalone portability | External skill copy validates its complete catalogue and synthetic frontend plan without repository siblings; optional packages reinstall successfully from their new paths |
| Documentation | Retained and new local links resolve after retirement; active portfolio/provenance links redirected |
| Workspace | Access experiment group/source removed; library lock resolves without it; SDK comparison is skill-owned |

Removal manifest measured 82 deleted files and 701,996 logical file-content bytes across
the four retired trees, including disposable files produced by package installation.
This is removed input, not net disk reclamation: preserved code, guides and inventory
were added under the canonical owner. No memory, latency or defect-rate improvement is claimed.

The old `entra-api-auth` distribution name and both Python imports remain for compatibility.
Old skill names occur only as lookup aliases, retained package/procedure history or
source-map provenance, not broken active entrypoints. Renamed `GUIDE.md` files are ordinary
references, not hidden embedded skills.

## Recovery

The verified archive is `/tmp/agentcraft-access-consolidation.A5Rm0x/source.tgz`, captured
against commit `c0d8149fa90cdf25c08977719aeb9abe44387a80` before retirement. Its contents
were compared with the source before any removal. The frozen deletion manifest is
`/tmp/agentcraft-access-consolidation.A5Rm0x/deletion-manifest.json`; the in-repository
[source map](source-map.json) records source hashes and preserved destinations.

Temporary storage is not a permanent backup. The missing original compiled Bicep artifact
was not in the filesystem archive; retained Bicep source deterministically rebuilt it and
render comparison passed. Historical source hashes and licence notices were not rewritten.
No commit, push, branch, tenant mutation or application runtime modification was performed
for this consolidation. Application documentation/provenance was redirected to its new owner.

## Pending Testing

- Real Easy Auth frontend/API sign-in, logout, token/cookie lifetime, provider references,
  wrong-tenant/expired/forged requests, CSRF, proxy identity headers and signed replica replay.
- PIM approval/expiry, pipeline external approval/locks and IaC ownership in an explicitly
  authorized host. The planner emits guidance and read-back argv, not an executable grant.
- Live identity and five-plane provider read-back, propagation, partial failure and ownership.
- Native migration of the investigation application's PKCE/routes/session component; its
  runtime remains unchanged. Offline compatibility tests are not native-host acceptance.
- Client-native discovery/slash behavior outside the validated local catalogue and full
  consumer/publication compatibility beyond the retained test set.

The API suite reports an upstream Starlette/httpx deprecation warning but passes. Native
workflow equivalence is documented, not asserted complete. Keep the existing support
matrix's implemented/delegated/documented/unsupported distinctions and live disclaimer.
The project README lists this skill and every current library under Pending Testing.
