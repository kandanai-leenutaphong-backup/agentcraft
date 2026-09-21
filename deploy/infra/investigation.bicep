targetScope = 'resourceGroup'

param location string
param names object
param tags object

resource runtime 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: names.identity
  location: location
  tags: tags
}

resource ingestion 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: '${names.identity}-ingest'
  location: location
  tags: tags
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: names.registry
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: { adminUserEnabled: false }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: names.environment
  location: location
  tags: tags
  properties: {
    workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }]
    zoneRedundant: false
  }
}

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: names.cosmos
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [{ name: 'EnableServerless' }]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: location, failoverPriority: 0, isZoneRedundant: false }]
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    minimalTlsVersion: 'Tls12'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2024-11-15' = {
  parent: cosmos
  name: 'investigation'
  properties: { resource: { id: 'investigation' } }
}

resource telemetry 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: database
  name: 'telemetry'
  properties: {
    resource: {
      id: 'telemetry'
      partitionKey: { paths: ['/partition'], kind: 'Hash' }
    }
  }
}

resource state 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2024-11-15' = {
  parent: database
  name: 'state'
  properties: {
    resource: {
      id: 'state'
      partitionKey: { paths: ['/owner'], kind: 'Hash' }
    }
  }
}

resource graph 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: names.gremlin
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    capabilities: [{ name: 'EnableGremlin' }, { name: 'EnableServerless' }]
    consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: location, failoverPriority: 0, isZoneRedundant: false }]
    publicNetworkAccess: 'Enabled'
    minimalTlsVersion: 'Tls12'
  }
}

resource graphDatabase 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2024-11-15' = {
  parent: graph
  name: 'investigation'
  properties: { resource: { id: 'investigation' } }
}

resource graphContainer 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs@2024-11-15' = {
  parent: graphDatabase
  name: 'ontology'
  properties: {
    resource: {
      id: 'ontology'
      partitionKey: { paths: ['/partition'], kind: 'Hash' }
    }
  }
}

resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: names.search
  location: location
  tags: tags
  sku: { name: 'basic' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    disableLocalAuth: true
    publicNetworkAccess: 'enabled'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: names.storage
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    publicNetworkAccess: 'Enabled'
  }
}

resource tables 'Microsoft.Storage/storageAccounts/tableServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource authTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  parent: tables
  name: 'auth'
}

resource replayTable 'Microsoft.Storage/storageAccounts/tableServices/tables@2023-05-01' = {
  parent: tables
  name: 'replay'
}

resource vault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: names.vault
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    enablePurgeProtection: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: 'Enabled'
    accessPolicies: []
  }
}

resource readonlySecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'graph-readonly'
  properties: { value: graph.listKeys().primaryReadonlyMasterKey }
}

resource writerSecret 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = {
  parent: vault
  name: 'graph-ingestion'
  properties: { value: graph.listKeys().primaryMasterKey }
}

resource runtimePull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, runtime.id, 'pull')
  scope: registry
  properties: {
    principalId: runtime.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource ingestionPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, ingestion.id, 'pull')
  scope: registry
  properties: {
    principalId: ingestion.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')
  }
}

resource runtimeSecret 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(readonlySecret.id, runtime.id, 'read')
  scope: readonlySecret
  properties: {
    principalId: runtime.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

resource ingestionSecret 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(writerSecret.id, ingestion.id, 'read')
  scope: writerSecret
  properties: {
    principalId: ingestion.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
  }
}

resource runtimeState 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, runtime.id, 'state-contributor')
  properties: {
    principalId: runtime.properties.principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: '${cosmos.id}/dbs/investigation/colls/state'
  }
  dependsOn: [state]
}

resource runtimeTelemetry 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, runtime.id, 'telemetry-reader')
  properties: {
    principalId: runtime.properties.principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000001'
    scope: '${cosmos.id}/dbs/investigation/colls/telemetry'
  }
  dependsOn: [telemetry]
}

resource ingestionTelemetry 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, ingestion.id, 'telemetry-contributor')
  properties: {
    principalId: ingestion.properties.principalId
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002'
    scope: '${cosmos.id}/dbs/investigation/colls/telemetry'
  }
  dependsOn: [telemetry]
}

resource runtimeSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, runtime.id, 'reader')
  scope: search
  properties: {
    principalId: runtime.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '1407120a-92aa-4202-b7e9-c0e197c71c8f')
  }
}

resource ingestionSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, ingestion.id, 'writer')
  scope: search
  properties: {
    principalId: ingestion.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
  }
}

resource ingestionSearchSchema 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, ingestion.id, 'schema')
  scope: search
  properties: {
    principalId: ingestion.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0')
  }
}

resource runtimeAuth 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(authTable.id, runtime.id, 'table')
  scope: authTable
  properties: {
    principalId: runtime.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3')
  }
}

resource runtimeReplay 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(replayTable.id, runtime.id, 'table')
  scope: replayTable
  properties: {
    principalId: runtime.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '0a9a7e1f-b9d0-4cc4-a60d-0319b160aaa3')
  }
}

output runtimeIdentityId string = runtime.id
output ingestionIdentityId string = ingestion.id
output registryId string = registry.id
output environmentId string = environment.id
output cosmosId string = cosmos.id
output graphId string = graph.id
output searchId string = search.id
output storageId string = storage.id
output vaultId string = vault.id