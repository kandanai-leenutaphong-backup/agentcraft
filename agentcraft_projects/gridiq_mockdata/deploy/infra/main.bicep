// GridIQ mock-data test stores. Resource-group scope; every grant is scoped to a resource declared here.
targetScope = 'resourceGroup'

param location string = resourceGroup().location
param namePrefix string
@description('Object id of the signed-in operator (az ad signed-in-user show --query id).')
param operatorPrincipalId string
param tags object = {}

param adxSku string = 'Dev(No SLA)_Standard_E2a_v4'
param adxDatabaseName string = 'gridiq'
param cosmosDatabaseName string = 'cim-db'
param cosmosGraphName string = 'cim-graph'
param searchSku string = 'basic'
@allowed(['free', 'standard'])
param searchSemantic string = 'free'
param embedModel string = 'text-embedding-3-large'
param embedModelVersion string = '1'
param embedSku string = 'Standard'
param embedCapacity int = 1
param storageContainerName string = 'reports'

var suffix = uniqueString(resourceGroup().id)
var names = {
  adx: toLower('${namePrefix}adx${suffix}')
  cosmos: toLower('${namePrefix}-gremlin-${suffix}')
  search: toLower('${namePrefix}-search-${suffix}')
  ais: toLower('${namePrefix}-ais-${suffix}')
  storage: toLower('${namePrefix}st${suffix}')
}

var roles = {
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  cognitiveServicesOpenAIUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
}
// Cosmos data-plane built-in role; ids live under the account, not Microsoft.Authorization.
var cosmosBuiltInDataContributor = '00000000-0000-0000-0000-000000000002'

// ---------------------------------------------------------------- ADX (Eventhouse stand-in)
resource adx 'Microsoft.Kusto/clusters@2023-08-15' = {
  name: names.adx
  location: location
  tags: tags
  sku: {
    name: adxSku
    tier: 'Basic'
    capacity: 1
  }
  properties: {
    enableAutoStop: true
    publicNetworkAccess: 'Enabled'
    enableStreamingIngest: false
  }
}

resource adxDb 'Microsoft.Kusto/clusters/databases@2023-08-15' = {
  parent: adx
  name: adxDatabaseName
  location: location
  kind: 'ReadWrite'
  properties: {
    softDeletePeriod: 'P365D'
    hotCachePeriod: 'P31D'
  }
}

// Database Admin for the operator is not declared here: ADX auto-assigns the creating principal
// as database Admin, and a second assignment with the same role and principal is rejected
// (BadRequest, observed 2026-09-24). deploy.sh provision reads it back and adds it only if absent.

// ---------------------------------------------------------------- Cosmos DB for Apache Gremlin
resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2024-11-15' = {
  name: names.cosmos
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard'
    locations: [
      {
        locationName: location
        failoverPriority: 0
        isZoneRedundant: false
      }
    ]
    capabilities: [
      { name: 'EnableGremlin' }
      { name: 'EnableServerless' }
    ]
    consistencyPolicy: {
      defaultConsistencyLevel: 'Session'
    }
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    minimalTlsVersion: 'Tls12'
  }
}

resource cosmosDb 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases@2024-11-15' = {
  parent: cosmos
  name: cosmosDatabaseName
  properties: {
    resource: {
      id: cosmosDatabaseName
    }
  }
}

resource cosmosGraph 'Microsoft.DocumentDB/databaseAccounts/gremlinDatabases/graphs@2024-11-15' = {
  parent: cosmosDb
  name: cosmosGraphName
  properties: {
    resource: {
      id: cosmosGraphName
      partitionKey: {
        paths: ['/pk']
        kind: 'Hash'
      }
    }
  }
}

resource cosmosDataContributor 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2024-11-15' = {
  parent: cosmos
  name: guid(cosmos.id, operatorPrincipalId, cosmosBuiltInDataContributor)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${cosmosBuiltInDataContributor}'
    principalId: operatorPrincipalId
    scope: cosmos.id
  }
}

// ---------------------------------------------------------------- AI Services + embedding deployment
resource ais 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: names.ais
  location: location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: names.ais
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: true
  }
}

resource embedDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: ais
  name: embedModel
  sku: {
    name: embedSku
    capacity: embedCapacity
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: embedModel
      version: embedModelVersion
    }
  }
}

// ---------------------------------------------------------------- Azure AI Search
resource search 'Microsoft.Search/searchServices@2023-11-01' = {
  name: names.search
  location: location
  tags: tags
  sku: {
    name: searchSku
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    semanticSearch: searchSemantic
    disableLocalAuth: false
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
  }
}

// ---------------------------------------------------------------- Storage (report PDFs)
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: names.storage
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: 'Enabled'
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource reportsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: storageContainerName
  properties: {
    publicAccess: 'None'
  }
}

// ---------------------------------------------------------------- Azure RBAC, each scoped to one resource
resource raSearchServiceContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, operatorPrincipalId, roles.searchServiceContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchServiceContributor)
    principalId: operatorPrincipalId
    principalType: 'User'
  }
}

resource raSearchIndexDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, operatorPrincipalId, roles.searchIndexDataContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.searchIndexDataContributor)
    principalId: operatorPrincipalId
    principalType: 'User'
  }
}

resource raOperatorOpenAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ais.id, operatorPrincipalId, roles.cognitiveServicesOpenAIUser)
  scope: ais
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAIUser)
    principalId: operatorPrincipalId
    principalType: 'User'
  }
}

resource raSearchOpenAIUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(ais.id, search.id, roles.cognitiveServicesOpenAIUser)
  scope: ais
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.cognitiveServicesOpenAIUser)
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource raStorageBlobDataContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, operatorPrincipalId, roles.storageBlobDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roles.storageBlobDataContributor)
    principalId: operatorPrincipalId
    principalType: 'User'
  }
}

// ---------------------------------------------------------------- Outputs (non-secret)
output adxName string = adx.name
output adxId string = adx.id
output adxQueryUri string = adx.properties.uri
output adxIngestUri string = adx.properties.dataIngestionUri
output adxDatabase string = adxDb.name
output cosmosName string = cosmos.name
output cosmosId string = cosmos.id
output cosmosGremlinEndpoint string = 'wss://${cosmos.name}.gremlin.cosmos.azure.com:443/'
output cosmosDatabase string = cosmosDatabaseName
output cosmosGraph string = cosmosGraphName
output searchName string = search.name
output searchId string = search.id
output searchEndpoint string = 'https://${search.name}.search.windows.net'
output searchPrincipalId string = search.identity.principalId
output aisName string = ais.name
output aisId string = ais.id
output aisEndpoint string = ais.properties.endpoint
output aisOpenAIEndpoint string = 'https://${names.ais}.openai.azure.com/'
output embedDeployment string = embedDeployment.name
output embedModel string = embedModel
output storageName string = storage.name
output storageId string = storage.id
output blobEndpoint string = storage.properties.primaryEndpoints.blob
output storageContainer string = reportsContainer.name
