// role-assignment-cognitive.bicep — grant a principal a role on an AI account.
//
// Module role:
//   One role assignment, scoped to one Cognitive Services / Azure AI account.
//   This is the grant a search service needs before it can embed query text
//   itself, and the grant an application needs to call a model deployment.
//
// See role-assignment-search.bicep for why the module is per target type and
// why the assignment name is a deterministic GUID.

targetScope = 'resourceGroup'

@description('Name of the existing Cognitive Services / Azure AI account.')
param accountName string

@description('Object id of the principal being granted access.')
param principalId string

@description('Built-in role definition GUID. Use bicep/roles.bicep rather than a literal.')
param roleDefinitionId string

@description('Principal type. Always set it for a managed identity (GOTCHAS.md G4).')
@allowed([
  'ServicePrincipal'
  'User'
  'Group'
  'ForeignGroup'
  'Device'
])
param principalType string = 'ServicePrincipal'

// NOT named `description` — see role-assignment-search.bicep (GOTCHAS.md G8).
@description('Why this access exists.')
param reason string = ''

resource account 'Microsoft.CognitiveServices/accounts@2023-05-01' existing = {
  name: accountName
}

resource assignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, principalId, roleDefinitionId)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
    principalId: principalId
    principalType: principalType
    description: reason
  }
}

output assignmentId string = assignment.id
output assignmentName string = assignment.name
