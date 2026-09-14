# Workload Identity And Scoped Grants

Prefer [Azure Verified Modules](https://learn.microsoft.com/en-us/azure/templates/microsoft.managedidentity/userassignedidentities)
or native [Bicep RBAC declarations](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/scenarios-rbac).
The skill retains [identity integration assets](../assets/managed-identity/README.md), their
[contract](../assets/managed-identity/CONTRACT.md), verifier and failure knowledge for
existing users and requirements not yet compared against the native module.

## Required Sequence

1. Explicitly bind tenant, subscription, cloud, identity name, existing resource targets
   and required roles. Distinguish identity `principalId`, `clientId` and ARM resource id.
2. Prefer resource scope and least privilege. A catalogue containing Owner, UAA or generic
   Contributor does not authorize assigning them. Review which roles reach assignments.
3. Pin an AVM/module version or the reviewed retained asset. Preview through the host's
   `deploy/deploy.sh`; keep every needed step in that entry point and its runbook.
4. Obtain target-bound mutation authorization. Installation, a logged-in CLI or a successful
   preview does not authorize creating resources, granting roles or changing policy.
5. Apply the declaration and read back exact identity and assignment fields. Check missing
   and excess grants; require a data-plane check separately when that is the objective.
6. For retirement, use the current IaC owner or explicitly authorized exact ids. Remove
   eligible grants before the identity and read back absence. Never infer deletion
   authority from a name, tag or unverified ledger.

Resource provisioning and current environment ownership belong to the host and the
independently installed `azure-cli-infra-management` skill. A workload identity does not
authenticate an application user or authorize an incoming request.

## Retained Asset Checks

```bash
az bicep build --file assets/managed-identity/bicep/main.bicep --outfile assets/managed-identity/build/main.json
python3 assets/managed-identity/tests/selftest.py
```

These compile and test locally. They do not deploy or grant access. The compiled artifact
was missing in the original source baseline and is rebuilt during this consolidation.
Its live verification script remains opt-in and runs only through the authorized host
entry point. No paid service, RBAC assignment or directory mutation is performed here.

## Traps To Preserve

- Deterministic assignment ids make declarations repeatable but do not prove ownership of
  an already existing grant. CLI-created random ids can conflict with a Bicep triple.
- Search control-plane/data-plane roles are separate; neither implies the other. Assign
  only what the workload needs, not both merely because an example does.
- Search server-side vectorization uses the Search service's own identity, not the caller.
- Cosmos NoSQL data access uses its native SQL role-assignment plane. Ordinary ARM RBAC
  does not substitute for it.
- Cross-group scope belongs on the module; an `existing` resource name alone is insufficient.
- Propagation and governance can make a successful deployment disagree with observed state.
- Deleting a deployment record removes no resources; deployment-stack delete/detach behavior
  and existing Terraform state are separate, native ownership mechanisms.
