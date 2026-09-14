// role-assignment-search.bicep — grant a principal a role on a search service.
//
// Module role:
//   One role assignment, scoped to one Azure AI Search service.
//
// Why there is a module per target type, rather than one generic module:
//   A role assignment's `scope` must reference an `existing` resource of a
//   specific type. Bicep has no way to express "a resource of whatever type
//   this id points at", so a generic module taking a resource id cannot be
//   written. Adding a new target type is a five-line copy of this file with the
//   type changed — deliberate duplication that the language requires, not an
//   abstraction that was missed.
//
// Why the assignment name is a deterministic GUID:
//   The name is the identity of the assignment. Generate it randomly and every
//   deployment creates another assignment; generate it from something unstable
//   and redeployment fails with RoleAssignmentExists. `guid(scope, principal,
//   role)` is stable, unique per triple, and idempotent. See GOTCHAS.md G1.

targetScope = 'resourceGroup'

@description('Name of the existing search service to grant access on.')
param searchServiceName string

@description('Object id of the principal being granted access.')
param principalId string

@description('Built-in role definition GUID. Use bicep/roles.bicep rather than a literal.')
param roleDefinitionId string

@description('Principal type. Always set it for a managed identity: without it, a deployment that runs before the identity has replicated through the directory fails with "principal does not exist" (GOTCHAS.md G4).')
@allowed([
  'ServicePrincipal'
  'User'
  'Group'
  'ForeignGroup'
  'Device'
])
param principalType string = 'ServicePrincipal'

// NOT named `description`: a parameter of that name shadows the
// @description decorator and every decorator in the file stops compiling
// (GOTCHAS.md G8).
@description('Why this access exists. Recorded on the assignment so an audit reads the reason rather than inferring it.')
param reason string = ''

resource searchService 'Microsoft.Search/searchServices@2023-11-01' existing = {
  name: searchServiceName
}

resource assignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, principalId, roleDefinitionId)
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleDefinitionId)
    principalId: principalId
    principalType: principalType
    description: reason
  }
}

output assignmentId string = assignment.id
output assignmentName string = assignment.name
