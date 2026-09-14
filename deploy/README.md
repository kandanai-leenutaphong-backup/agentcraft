# Azure Connector Live-Test Infrastructure

**Scope: one dedicated resource group.** Search/Cosmos services, role assignments, sample
data and live test execution are not provisioned by this entry point. The intended consumer
is [the connector library](../libraries/azure-data-connectors/README.md).

## Target Authority

[env/azdata-live.env](env/azdata-live.env) is the authoritative non-secret target. It contains
the exact tenant, subscription, group and metadata location. The file is strict data, never
sourced as shell code. No credentials belong in it.

- Environment: `azdata-live`.
- Group: `rg-agentcraft-azdata-live-tests`.
- Metadata location: `eastus2`; future service locations/SKUs require their own availability check.
- Ownership tags: `managed-by=agentcraft-deploy`, `capability=azure-data-connectors`,
  `purpose=live-crud-tests`, `data-policy=synthetic-only`, `lifecycle=explicit-teardown`.
- Current status: created and independently verified on 2026-09-14. Last recorded state:
   `Succeeded`, matching required tags, zero child resources; repeat creation was `unchanged`.
- Empty resource-group ownership is not evidence of data-plane access or working CRUD.

The dated [creation and verification record](records/azdata-live-resource-group-2026-09-14.json)
contains the exact resource ID, observed timestamps, commands and verification limits. It is
historical evidence, not a substitute for running `verify` before future use. No services,
access grants, sample data or live CRUD tests were created or run in this change.

## Run Order

Run from this repository root using only [deploy.sh](deploy.sh). Python 3.11+ and a logged-in
Azure CLI are prerequisites. The script is invoked through Bash, so an executable file mode
is not required.

1. Run the offline safety checks. No Azure CLI call occurs:

   ```bash
   bash deploy/deploy.sh test
   ```

   Expected: unittest `OK`. Stop on failure before any cloud mutation.

2. Inspect the plan:

   ```bash
   bash deploy/deploy.sh -e azdata-live plan
   ```

   Expected: JSON with `action: plan`, the exact target, `would_create` and required confirmation.
   A matching group is reported, not rewritten. Another owner/location fails closed.

3. Create only after explicit authorization, confirming the full ID printed by the plan:

   ```bash
   bash deploy/deploy.sh -e azdata-live create --confirm '<full-resource-id-from-plan>'
   ```

   Replace the placeholder with the exact plan value. Expected: `created` or `unchanged`,
   `read_back_verified: true`, `provisioning_state: Succeeded` and actual resource inventory.
   A repeat with an owned matching group performs no second write.

4. Independently verify current state:

   ```bash
   bash deploy/deploy.sh -e azdata-live verify
   ```

   Expected: `verified`, ownership/location match and actual group contents. The current
   resource count should be zero until service provisioning is separately authorized.
   A later nonzero count is an observation to review, not a claim all children are owned.

The preflight refuses a different active tenant/subscription/cloud, disabled account,
unreported required permission or unavailable metadata region. CLI commands use explicit
subscription selection when the installed command supports it. No script silently changes
the shared Azure CLI context or grants itself permissions.

## Failure Handling

| Result | Next Action |
| --- | --- |
| Missing CLI/Python | Install prerequisites; no interactive privilege escalation is performed here. |
| Wrong active subscription | Operator runs the exact `az account set --subscription ...` printed by preflight. |
| Wrong tenant or expired login | Operator authenticates directly in their own terminal with the documented tenant; no password/token passes through an agent. |
| Missing permission | Review required resource-group action with an administrator. No automatic role grant. |
| Policy/lock refusal | Inspect the named policy or lock; do not disable or delete governance controls to make a test pass. |
| Existing owner/location mismatch | Preserve the resource; review target selection. Never silently adopt or retag it. |
| CLI timeout or failed read-back | Outcome may be unknown. Run `verify` before another mutation. No rollback is inferred. |
| Unexpected child resources | Stop before deletion and review their ownership. Group creation may not be the only subscription policy activity. |

Reported permission actions are not a complete effective-access audit. Azure Policy, deny
assignments, conditions, locks, quota and concurrent changes can still refuse an operation.
One writer owns this resource-group target; the existence check is not an atomic reservation.

## Teardown

Not authorized by the creation request. A future operator may run, after separately approving
deletion of this exact empty group:

```bash
bash deploy/deploy.sh -e azdata-live teardown --confirm '<full-resource-id-from-plan>'
```

This verifies owner/location, refuses any child resource or lock, deletes only the configured
group and reads back absence. It does not remove locks, grant roles or recursively retire
future paid services. Do not run it while another writer could populate the group.

## Next Live-Test Stage

The target group is for opt-in E2E connector checks using **synthetic data only**.
[The numbered live-test design](../libraries/azure-data-connectors/tests/live_tests/LIVE_TEST_DESIGN.md)
now records the service coverage and acceptance cases. No executable live tests or fixtures
have been added; the resource-group creation receipt remains historical evidence.

Before provisioning services or executing those cases, agree the instances, SKUs, regions, cost ceiling,
lifetime, network restrictions and least-privilege data-plane identity. Account-key or SAS
fallback is not a shortcut. Resource-group permission is not data-plane permission.

Live setup may use Azure CLI infrastructure APIs, but CRUD tests must call the library itself.
Use per-run IDs, a seed manifest and exact cleanup ownership. Cover native supported CRUD,
read-back of updated values, conflict/partition/permission failures and explicit unsupported
guarantees. Search atomic create and Cosmos merge are currently unsupported; a correct
refusal is part of interface coverage, not a reason to silently change operation semantics.

A live pass should produce dated non-secret evidence naming versions, resource IDs, run IDs,
operations, outcomes, verification and remaining sample data. Do not label the library live
verified until these checks actually run. Empty-group verification is infrastructure evidence only.

## Procedure Owner

[azure-cli-infra-management](../.github/skills/azure-cli-infra-management/SKILL.md) documents the
reusable procedure. This deployment directory, not the skill, owns this project's real targets,
runner and operational record. [tests/test_resource_group.py](tests/test_resource_group.py)
proves the target/policy/ownership guards with fake CLI responses; it does not use Azure.