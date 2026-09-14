
# bicep-managed-identity

Provision **access, not credentials**. Reviewing the template is reviewing the
permission surface, or the template is not doing its job.

## Decide

Use when an Azure workload needs to reach another Azure resource — every case
where a connection string or account key would otherwise appear.

Not for: third-party API keys (Key Vault), Cosmos DB NoSQL data-plane access (a
different resource type entirely — GOTCHAS.md G7), or subscription-scoped grants,
which this box deliberately does not do.

## Install

The consolidated skill supplies these retained integration assets; it does not copy them
into a project. Here `ASSET_ROOT` means its `assets/managed-identity` directory.
Python 3.10+ is required for the offline
check; Azure CLI with Bicep is needed for compilation and authorized deployment.

```bash
python3 "$ASSET_ROOT/tests/selftest.py"
az bicep version
```

**Deploying is the project's `deploy/`, not this directory.** Vendor `bicep/`,
`build/` and `scripts/` together under `deploy/infra/identity/`, preserving their
relative layout. Call that copy's `scripts/deploy.sh` from `deploy/deploy.sh`.
Require operator authorization and explicit targets before any cloud mutation.
Installation neither signs in to Azure nor grants permissions.

## Use

### 1. Declare the identity and its grants

Edit `examples/deploy.bicepparam`, or pass parameters directly. Every grant is
conditional — an omitted target is skipped.

```bicep
using '../bicep/main.bicep'

param identityName = 'id-my-workload'
param searchServiceName = 'srch-mine'
param searchServiceResourceGroup = 'rg-search'
param aiAccountName = 'aif-mine'
param aiAccountResourceGroup = 'rg-models'
```

Search grants are **two** roles: control plane and data plane are separate
permission systems, neither implying the other (G3).

### 2. Preview, deploy, verify

```bash
./scripts/deploy.sh -g <rg> -n id-my-workload -s <search> -a <ai-account> -A <ai-rg>
./scripts/deploy.sh ... -p          # preview only
./scripts/deploy.sh ... -V          # also grant the SEARCH SERVICE model access
```

That is the call the project's `deploy/deploy.sh` wraps, not a command given to
an operator directly. `-h` is not a help flag: unknown options exit 2 and point
at the script's header comment, where usage lives.

`-V` covers server-side vectorization, where the search service embeds query text
using **its own** identity — a different principal from the workload's. Without
it, an index carrying a vectorizer is accepted and then fails every text vector
query with a 502 (G6).

### 3. Verify at any time

```bash
python3 scripts/verify.py -g <rg> -n identity-id-my-workload
python3 scripts/verify.py -g <rg> -n identity-id-my-workload --strict
```

Compares live assignments against the declared ones, both directions:

- **declared but absent** — something removed or rewrote it after the deployment
  reported success. Check the Activity Log for an Azure Policy `Modify` effect
  (G12).
- **held but not declared** — granted out of band, or left over from a previous
  shape. Warning by default, failure with `--strict`.
- **Owner or User Access Administrator** — always a failure.

### 4. Add a new target type

A role assignment's scope must reference an `existing` resource of a specific
type, so there is one module per type. Copy `role-assignment-search.bicep`,
change the `resource ... existing` block, done. The duplication is the language's
requirement, not a missed abstraction.

### 5. Add a role

Add it to `bicep/roles.bicep` with its GUID and a comment saying what it is for.
Never write a GUID in a template — the selftest fails on it: a grant nobody can
read is a grant nobody can review (G5).

## Rebuild the artefact

`build/main.json` is the compiled template, committed because it is what actually
deploys. Regenerate whenever the sources change:

```bash
az bicep build --file bicep/main.bicep --outfile build/main.json
```

The selftest recompiles and diffs; drift fails the check.

## Verify

```bash
python3 tests/selftest.py        # invariants + render-and-diff, offline
```

Asserted: deterministic assignment names; `principalType` and a written reason on
every grant; role ids via `subscriptionResourceId`; no literal role GUIDs outside
the catalogue; no secret-reading functions; no hardcoded subscription or tenant;
Owner/UAA/Contributor never granted; committed artefact matching sources.

## Symptoms

| Symptom | Read |
| --- | --- |
| `RoleAssignmentExists` naming an unknown id | G1 |
| Access stopped after a resource was recreated | G2 |
| Management works, data access is 403 | G3 |
| "Principal does not exist in the directory" | G4 |
| The grant is far wider than the review believed | G5 |
| Vector query returns 502 "failed to authenticate" | G6 |
| Cosmos grant deploys and does nothing | G7 |
| `BCP062`/`BCP079` on lines you did not change | G8 |
| Grant targets the wrong resource group | G9 |
| A key appeared in deployment history | G10 |
| what-if showed nothing, deployment changed things | G11 |
| Deployment succeeded, resource does not match | G12 |
| 403 for the first minute after granting | G13 |

## Remove

```bash
az role assignment delete --assignee <principalId> --scope <scope> --role "<role>"
az identity delete -n <identity> -g <rg>
```

In that order. Deleting the identity first leaves assignments pointing at a
principal that no longer exists (G2). Deleting the deployment record removes
nothing.
