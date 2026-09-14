# Native Workflow Selection

Prefer a supported workflow owner over assembling another orchestrator. The retained
`azaccess` functions are optional imperative policy/evidence helpers, not independent
approval, durable scheduling, grant expiry, automatic restart recovery or complete access
evaluation. A valid local confirmation can be minted by the same host that applies it.

| Requirement | Existing Workflow | Boundary To Verify |
| --- | --- | --- |
| Time-bound privileged activation and approval | [Microsoft Entra PIM](https://learn.microsoft.com/en-us/entra/id-governance/privileged-identity-management/pim-configure) | Principal/assignment type, resource support, licensing, expiry and activation policy; no automatic consent |
| Approval outside deployment code and serialized access | [Azure Pipelines checks](https://learn.microsoft.com/en-us/azure/devops/pipelines/process/approvals?view=azure-devops) | Protect resource/service-connection checks and exclusive locks; a script flag is not equivalent approval |
| Review exact infrastructure changes and maintain state | [Terraform plan/apply](https://developer.hashicorp.com/terraform/cli/run) | Use a reviewed saved plan, provider resource support and protected state; import/adoption requires an owner decision |
| Manage a Bicep deployment's lifecycle | [Azure deployment stacks](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deployment-stacks) | Explicit delete/detach semantics and supported resources; no second ledger competing for the same grant |
| Create user-assigned identity and scoped assignments | [Bicep RBAC](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/scenarios-rbac), [Azure Verified Module](https://learn.microsoft.com/en-us/azure/templates/microsoft.managedidentity/userassignedidentities) | Pin supported versions, compare target modules and verify exact grants after deployment |
| Sign in a Container Apps frontend | [Easy Auth](https://learn.microsoft.com/en-us/azure/container-apps/authentication) | Protect assets as well as APIs; compare cookies, CSRF, API refusals and custom signed-caller requirements |
| Obtain tokens from application code | [MSAL Python](https://learn.microsoft.com/en-us/entra/msal/python/getting-started/acquiring-tokens), [Azure Identity](https://learn.microsoft.com/en-us/python/api/overview/azure/identity-readme?view=azure-python) | Client token acquisition is not validation of incoming API access tokens |

## Compose, Do Not Compete

1. Identify caller, workload, administrative operator and current resource/grant owner.
2. Name the narrow task and inspect native support before choosing a helper.
3. Record trusted target configuration outside request data. Directory and resource
   permissions are separate; subscription Owner does not grant Graph administration.
4. Put mutations in the host's reviewed deployment/governance entry point. Keep one writer
   per grant, explicitly transfer ownership if changing from imperative code to IaC.
5. Read back exact state, and exercise the corresponding unauthorized path. Preserve
   uncertainty when reads fail; an accepted write may already have landed.

The [offline planner](../scripts/workflow.py) returns task references, prerequisite steps
and read-back argv only. It does not run commands or establish authority. Existing access
CLI/MCP contracts and their limitations remain in [CONTRACT.md](../CONTRACT.md).

## Retained Helpers

Use the [access workflow guide](access-workflows.md) only where a host truly needs callable
per-operation bounds, declarations, comparison, read-back or conservative cleanup across
its chosen adapters. Retain native semantics: ARM, Cosmos NoSQL, ADX, Graph and SQL are not
one permission system. `inspect` and the MCP inspection tool are Azure RBAC only.

Do not make an SDK comparison pass prove that a library is necessary. The comparison in
[the evidence record](../tests/sdk_comparison/README.md) proves selected offline behavior,
not superiority to the native workflows above or production readiness.
