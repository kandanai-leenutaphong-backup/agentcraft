// main.bicep — one identity, and every grant it holds, in one reviewable file.
//
// Template role:
//   Creates a user-assigned managed identity and grants it exactly the access
//   the workload needs: index management and document access on a search
//   service, and model access on an AI account.
//
// The point of the whole box:
//   Reviewing this file is reviewing the permission surface. Every grant is
//   named, scoped to a single resource, carries a written reason, and is
//   idempotent. Nothing here is a secret, so there is nothing to rotate: the
//   deployment provisions *access*, not credentials.
//
// What deliberately is not here:
//   Subscription- or resource-group-scoped grants. They are one line to add and
//   almost always wider than intended — a Contributor at resource-group scope
//   is not a shortcut for two resource-scoped grants, it is a different and
//   much larger permission. See GOTCHAS.md G5.

targetScope = 'resourceGroup'

@description('Name of the user-assigned managed identity to create.')
param identityName string

@description('Location for the identity.')
param location string = resourceGroup().location

@description('Name of an existing Azure AI Search service to grant access on. Empty skips the search grants.')
param searchServiceName string = ''

@description('Resource group holding the search service. Defaults to this one. A grant on a resource in another group needs the MODULE scoped there — the resource reference alone cannot cross groups (GOTCHAS.md G9).')
param searchServiceResourceGroup string = resourceGroup().name

@description('Name of an existing Azure AI / Cognitive Services account to grant model access on. Empty skips it.')
param aiAccountName string = ''

@description('Resource group holding the AI account. Defaults to this one.')
param aiAccountResourceGroup string = resourceGroup().name

@description('Also grant the search service its own model access, so it can embed query text itself. Requires searchServicePrincipalId.')
param grantSearchServiceModelAccess bool = false

@description('Principal id of the search service system-assigned identity. Required only when grantSearchServiceModelAccess is true.')
param searchServicePrincipalId string = ''

@description('Tags applied to the identity.')
param tags object = {}

import { roleIds } from 'roles.bicep'

module identity 'modules/identity.bicep' = {
  name: 'identity'
  params: {
    name: identityName
    location: location
    tags: tags
  }
}

// -- Search: two roles, because control plane and data plane are separate
//    permission systems and holding one grants nothing on the other (G3).

module searchManagement 'modules/role-assignment-search.bicep' = if (!empty(searchServiceName)) {
  name: 'search-management'
  scope: resourceGroup(searchServiceResourceGroup)
  params: {
    searchServiceName: searchServiceName
    principalId: identity.outputs.principalId
    roleDefinitionId: roleIds.searchServiceContributor
    reason: 'Create and update indexes from the deployment pipeline.'
  }
}

module searchData 'modules/role-assignment-search.bicep' = if (!empty(searchServiceName)) {
  name: 'search-data'
  scope: resourceGroup(searchServiceResourceGroup)
  params: {
    searchServiceName: searchServiceName
    principalId: identity.outputs.principalId
    roleDefinitionId: roleIds.searchIndexDataContributor
    reason: 'Upload and delete documents. Not implied by index management.'
  }
}

// -- Model access for the workload itself.

module modelAccess 'modules/role-assignment-cognitive.bicep' = if (!empty(aiAccountName)) {
  name: 'model-access'
  scope: resourceGroup(aiAccountResourceGroup)
  params: {
    accountName: aiAccountName
    principalId: identity.outputs.principalId
    roleDefinitionId: roleIds.cognitiveServicesOpenAiUser
    reason: 'Embed documents and queries.'
  }
}

// -- Model access for the SEARCH SERVICE, which is a different principal.
//    Without this, an index carrying a vectorizer is accepted and then fails
//    every text vector query with a 502 (G6).

module searchServiceModelAccess 'modules/role-assignment-cognitive.bicep' = if (grantSearchServiceModelAccess && !empty(aiAccountName) && !empty(searchServicePrincipalId)) {
  name: 'search-service-model-access'
  scope: resourceGroup(aiAccountResourceGroup)
  params: {
    accountName: aiAccountName
    principalId: searchServicePrincipalId
    roleDefinitionId: roleIds.cognitiveServicesOpenAiUser
    reason: 'Server-side vectorization: the search service embedding query text.'
  }
}

@description('Resource id of the identity, for attaching it to a workload.')
output identityId string = identity.outputs.id

@description('Principal id. Changes if the identity is recreated, orphaning existing grants (G2).')
output principalId string = identity.outputs.principalId

@description('Client id, for selecting this identity at runtime.')
output clientId string = identity.outputs.clientId

@description('Every grant this deployment made, for the verifier to assert against.')
output grants array = concat(
  empty(searchServiceName) ? [] : [
    {
      scopeType: 'search'
      scopeName: searchServiceName
      principalId: identity.outputs.principalId
      roleDefinitionId: roleIds.searchServiceContributor
      role: 'searchServiceContributor'
    }
    {
      scopeType: 'search'
      scopeName: searchServiceName
      principalId: identity.outputs.principalId
      roleDefinitionId: roleIds.searchIndexDataContributor
      role: 'searchIndexDataContributor'
    }
  ],
  empty(aiAccountName) ? [] : [
    {
      scopeType: 'cognitive'
      scopeName: aiAccountName
      principalId: identity.outputs.principalId
      roleDefinitionId: roleIds.cognitiveServicesOpenAiUser
      role: 'cognitiveServicesOpenAiUser'
    }
  ],
  (grantSearchServiceModelAccess && !empty(aiAccountName) && !empty(searchServicePrincipalId)) ? [
    {
      scopeType: 'cognitive'
      scopeName: aiAccountName
      principalId: searchServicePrincipalId
      roleDefinitionId: roleIds.cognitiveServicesOpenAiUser
      role: 'cognitiveServicesOpenAiUser'
    }
  ] : []
)
