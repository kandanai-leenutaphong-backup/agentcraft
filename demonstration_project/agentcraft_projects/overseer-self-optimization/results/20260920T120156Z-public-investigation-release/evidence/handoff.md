# Public Investigation Release Checkpoint

Status: **complete for this deployed-baseline checkpoint**, not AgentCraft optimization.
Objective: actual protected stack, real public package, native tools, durable owner state and matched refusals.
Stage: data-understanding / deployed baseline test-measure. Next transition: overseer archival review,
then human sign-in acceptance or a separately assigned experiment. No follow-on optimization started.

## Pins And Authority

- Constitution revision 9 SHA-256 `070cadee2c44731d1b984dafc906a6bba2f2797de1bd2530474ef5777b8c0e37`; validator passed.
- Runtime authority record SHA-256 `b7259330556f4294e2d718577358a5512fc493437c286652d1d7be8027c37560`.
- Runtime prestate record SHA-256 `ea0297cbef7abb7fafd1193b00fb465437606d8b75f7c702c6f5c9a58d5caa63`.
- Supplied receipt SHA-256 `5d0df3ef022cae283cd7059eaffd113637fde02f20e266c1c2fabe1fbc1b6436`.
- Verified all 24 mapped initial sources and retained snapshots before edits. Public graph, public tests,
  fixture and metadata docs additionally matched retained accepted-after artifacts in
  `records/v2/20260920T115844026840Z-public-app-local-acceptance-outcome/` before edits.
- Exact new filenames were recorded absent in `20260920T120306189567Z-capture.json`.
- User explicitly authorized resource choices/scoped grants/model reuse/single-tenant registration and
  unique operator Ed25519 key. No candidate invoked or modified; max effort requested, effective runtime unverified.
- User unavailable clarification response instructed autonomous decisions. Used documented server-side
  `listKeys().primaryReadonlyMasterKey` projection after literal `listReadOnlyKeys()` failed in ARM.
  No runtime list-key role or local secret retrieval. Reference:
  https://learn.microsoft.com/en-us/rest/api/cosmos-db-resource-provider/database-accounts/list-keys?view=rest-cosmos-db-resource-provider-2024-11-15

## Deployed Result

URL: https://agentcraft-investigation-dev.greensand-416301ba.australiaeast.azurecontainerapps.io

- Target subscription `67255afe-8670-4401-a1b8-df6ca63a3516`, tenant `c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`,
  `rg-agentcraft-dev`, `australiaeast`. Current CLI identity reused; no login/account switch.
- Revision `agentcraft-investigation-dev--0000003`.
- Image `agentcraftdev67255.azurecr.io/investigation@sha256:3c4861abff1584d63e017ac6709898d41eb258f3be9ae07267a21f602e84e5a7`.
- Exact image archive/member hashes: `20260920T125650219530Z-package.json`; successful ACR build:
  `20260920T125658322736Z-build.json`. Canonical packages installed from pinned lock export; no local venv.
- Actual frontend production build passed: `20260920T122100053669Z-command.json`. Chunk-size warning retained.
- Root `deploy/deploy.sh investigation` owns plan/preflight/constraints/provision/registration/key/build/
  ingestion/private verification/release/live verification/restart/status/inventory/source sealing.
- Human registration app ID `cbf742c7-5072-41c8-aff0-a83b2e595a24`, single tenant, SPA PKCE callback,
  `access_as_user` only; no external API permission/admin consent. Exact owner allowlist enforced after auth.
- Signed caller fingerprint `4f063942c9064f3f`, authorized principal `devkey:4f063942c9064f3f:default`.
  Private key only at `~/.local/state/agentcraft/rg-agentcraft-dev/caller.ed25519`, directory 0700/file 0600.
  Private bytes never returned, snapshotted, uploaded or logged. Browser prerequisite installed with
  system pip `--target` into operator-local `browser-runtime`, not globally and not into a new venv.

## Real Data And Acceptance

- Package SHA-256 `c9a96ffcdc3775b89685bac82f9941140b8dc2e724ce5f94442a838ab52e8e12`.
  All source artifact sizes/hashes verified before build. Licensed notices included. No private input.
- Platform ingestion job `agentcraft-dev-ingest-m3l2mv9` Succeeded. Two passes each verified Cosmos 4,
  graph 10 vertices/19 edges, Search 3,135, same IDs/generation/content/provenance. No mock acceptance.
  Primary logs/status: `20260920T125134076375Z-ingest-logs.json`, `20260920T125131629497Z-ingest-status.json`.
- Graph uses runtime-injected read-only key; separate ingestion identity/writer secret. Fixed bound edge
  traversals remain deployment-only. JSON list/map properties decode in production; omitted system edge
  partition derives only from two qualified endpoints. Explicit foreign partition/source/evidence still refuses.
- Actual Cosmos owner-document create/ETag CAS verified with separate instances, concurrent `[2,409]`,
  foreign-owner refusal, immutable version and pinned assignment. No filesystem/AzureFiles durability claim.
- Actual Azure Tables flow atomic consume, cross-instance session resolution/revocation, concurrent replay
  claim and recreated-client replay refusal verified. `20260920T130020168438Z-private-verify.json`.
- Signed external API: case -> alarm -> evidence -> host/user/process graph -> MITRE; authoring save/readback/
  stale CAS; anonymous 401, signature tamper 401, replay 401, disallowed signed owner 403, foreign partition 422.
  Primary release `20260920T130045401995Z-release.json`; request receipts retained individually.
- Browser: actual deployed 1440x1000 and 390x844 case/alarm/event, host/user/process graph, source provenance,
  keyboard focus, measured overflow. Eight screenshots; no browser/signing errors.
  `20260920T130137636986Z-browser.json`; desktop/mobile process screenshots inspected visually.
- Actual `gpt-5.6-luna` native model run completed with three tool-result events and owner-readable result:
  `20260920T130214544018Z-verify.json`. Model deployment unchanged; exact-resource Cognitive Services OpenAI User grant.
- Further native model turn created labeled deployment-test profile from freshly retrieved public evidence.
  HTTP readback matched, citations verified, stale revision 409, HTTP update to revision 2 persisted:
  `20260920T130604783965Z-verify.json`. No malicious-person assertion or quality score inferred.
- Actual replica replacement verified twice. Final restart preserves authored agent and profile, rejects
  previously accepted signature with 401. Before `...79577db854-484zw`, after `...6566d77d58-chlhb`.
  `20260920T130736868060Z-restart-verify.json`; 55 bounded readiness observations retained.

## Final Checks

- 101 application/public/auth tests: `20260920T131336621731Z-command.json`.
- 36 shared authoring store tests: `20260920T131355661104Z-command.json`.
- 17 deployment/loader tests: `20260920T131357118718Z-command.json`.
- Both Bicep templates compiled; Azure provider validation and actual writes/readback passed.
- Current ready revision/image/ingress readback: `20260920T131357290788Z-app-status.json`.
- Full resources/SKUs/security fields/grants: `20260920T131001998756Z-inventory.json`.
- Tests overlap earlier runs; no aggregate quality score or independent repeated sample claim.

## Failures Retained

1. System Python lacked `azdata`; existing installed interpreter reused. Invalid credential fixture corrected.
2. Initial runner indentation error repaired; all focused checks rerun. Policy mocks adjusted for new reads.
3. Initial deny check rejected unrelated managed-resource groups; scope comparison corrected and tested.
4. ARM literal `listReadOnlyKeys` unsupported. First deployment failed after partial infrastructure creation;
   retained exact failed template, read actual inventory, waited terminal state, corrected server-side projection.
5. Source capture guard matched its own source string; narrowed to full PEM header, retained failed capture.
6. First ACR run `cr1` failed on workspace source mapping; `uv pip --no-sources` uses exported pinned inputs.
7. Job name exceeded 32 characters; shortened to `agentcraft-dev-ingest`, revalidated and redeployed privately.
8. First ingestion rejected setting edge partition system property. Corrected fixed writer; second attempt
   verified graph then failed invalid local `schema` policy grant. Explicit `schema.read/schema.create` fixed it.
9. Early private verify refused unready revision. Probe import-root/cleanup APIs corrected. Final result parsing
   requires complete state/table/anonymous result, not an intermediate success marker.
10. First public release reached auth/Cosmos positives but graph returned 503 for omitted edge partition.
    Ingress automatically closed/read back. Native graph probe initially hit CLI quoting; corrected nonsecret
    command encoding, proved source-membership failure, fixed owner module with regression, rebuilt/retested.
11. Browser prerequisite install found no pip in existing interpreter; system pip --target succeeded without
    changing system site-packages or creating/activating any environment.

No valid SKU, effective permission, or policy refusal was bypassed. No broad grants, exemptions or teardown.
All successful and failed automated command receipts remain immutable. Initial manual reads/patches and
some early tests exist in host trace only; exact timestamps and complete host-tool export are unavailable.

## Retained Resources And Limits

Eleven resources, all retained as requested: two managed identities, two serverless Cosmos accounts,
Basic Search, Basic ACR, Standard_LRS Storage, standard Key Vault (RBAC/soft-delete/purge protection),
Consumption environment, app and manual ingestion job. Full exact IDs in inventory, no invented inventory.
Runtime role readback has only Search reader, AcrPull, two table-scoped contributors, read-only-secret reader,
and model-resource user; Cosmos telemetry reader/state contributor are separate container-scoped assignments.
Ingestion has separate telemetry writer, Search document/schema roles, writer-secret reader and AcrPull.

- Ongoing service/model costs unknown; no pricing/billing query. Basic tiers and min-one app have ongoing costs.
- Human interactive sign-in/first-use consent **not_verified**. Tenant/callback/scope configuration read back;
  signed path tested. No unavailable human session invented or used as a deployment blocker.
- Two-event smoke, no held-out quality, complete scenario coverage or comparative optimization claim.
- Public owner namespaces refuse above 1.5 MB serialized content. No silent truncation or ephemeral downgrade.
- Chat sessions, evidence grants and scan caches are process-local; restart loses them, unlike profiles/authoring/auth.
- Graph labels remain visually dense; observed navigation and responsive geometry pass. No unrelated redesign.
- Test agents, labeled profile, owner-state probe records, expired/expiring replay rows, failed jobs/images/revisions
  remain retained. No destructive cleanup or early replay-row purge authorized/performed.
- Full automatic action capture, total effort/cost, complete tenant policy expansion, disaster recovery and restoration
  remain unverified. Exact selected source snapshots retained; source restore/cloud rollback not executed.
- Current image receipt is known-good recovery input; prior failed/partial images are not certified rollback targets.
- No child workers, support-role dispatch, records/v2 publication or lesson publication. Browser contexts closed;
  cloud writes settled; app/services retained. Archivist publication belongs to overseer.

Smallest next decision: archive supplied source/evidence manifest and checkpoint; schedule actual owner sign-in
acceptance. No further technical approval gate required for this completed deployed-baseline assignment.