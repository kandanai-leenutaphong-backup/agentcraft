// deploy.bicepparam — a worked parameter file.
//
// Copy, change the names, deploy:
//   az deployment group create -g <rg> --template-file bicep/main.bicep \
//       --parameters examples/deploy.bicepparam
//
// Every value here is a placeholder. Nothing in this box names a real
// subscription, tenant, resource or principal.

using '../bicep/main.bicep'

// The identity the workload runs as. Created by this deployment, and expected
// to outlive whatever compute is attached to it.
param identityName = 'id-example-workload'

// Grant it index management AND document access on this search service. Both
// are needed; neither implies the other (GOTCHAS.md G3).
param searchServiceName = 'srch-example'
param searchServiceResourceGroup = 'rg-example-search'

// Grant it model access, so it can embed documents and queries itself.
// A different resource group from the deployment's is fine: the module is
// scoped there (GOTCHAS.md G9).
param aiAccountName = 'aif-example'
param aiAccountResourceGroup = 'rg-example-models'

// Optional: also grant the SEARCH SERVICE's own identity model access, so it can
// embed query text server-side. This is a different principal from the workload
// identity — without it, an index with a vectorizer fails queries with a 502
// (GOTCHAS.md G6). Obtain the value with:
//
//   az search service show -n <svc> -g <rg> --query identity.principalId -o tsv
//
// param grantSearchServiceModelAccess = true
// param searchServicePrincipalId = '00000000-0000-0000-0000-000000000000'

param tags = {
  owner: 'platform-team'
  purpose: 'search indexing workload'
}
