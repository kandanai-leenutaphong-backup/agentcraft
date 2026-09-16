targetScope = 'resourceGroup'

param target object
param apiClientId string
param activate bool = false

var tags = {
  owner: target.owner
  experiment: 'two-authorized-pdfs'
  lifecycle: 'manual-owned-teardown'
}
var blobOwnerRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b')
var cognitiveUserRole = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: target.identity_name
  location: target.location
  tags: tags
}

resource network 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: target.network_name
  location: target.location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: ['10.84.0.0/23']
    }
    subnets: [
      {
        name: 'functions'
        properties: {
          addressPrefix: '10.84.0.0/24'
          delegations: [
            {
              name: 'flex-functions'
              properties: {
                serviceName: 'Microsoft.App/environments'
              }
            }
          ]
        }
      }
      {
        name: 'private-endpoints'
        properties: {
          addressPrefix: '10.84.1.0/27'
          privateEndpointNetworkPolicies: 'Disabled'
        }
      }
    ]
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: target.storage_name
  location: target.location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    allowSharedKeyAccess: false
    allowBlobPublicAccess: false
    publicNetworkAccess: 'Disabled'
    minimumTlsVersion: 'TLS1_2'
    supportsHttpsTrafficOnly: true
    defaultToOAuthAuthentication: true
    networkAcls: {
      bypass: 'None'
      defaultAction: 'Deny'
    }
  }
}

resource blobs 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource containers 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = [for name in ['function-packages', 'jobs']: {
  parent: blobs
  name: name
  properties: {
    publicAccess: 'None'
  }
}]

resource blobOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, identity.id, blobOwnerRole)
  scope: storage
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: blobOwnerRole
    description: 'Owned datacrafting Function host/deployment storage and extraction artifacts'
  }
}

resource blobDns 'Microsoft.Network/privateDnsZones@2024-06-01' = {
  name: 'privatelink.blob.core.windows.net'
  location: 'global'
  tags: tags
}

resource blobLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2024-06-01' = {
  parent: blobDns
  name: 'datacrafting-network'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: network.id
    }
  }
}

resource blobEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = {
  name: target.private_endpoint_name
  location: target.location
  tags: tags
  properties: {
    subnet: {
      id: resourceId('Microsoft.Network/virtualNetworks/subnets', network.name, 'private-endpoints')
    }
    privateLinkServiceConnections: [
      {
        name: 'owned-blob-storage'
        properties: {
          privateLinkServiceId: storage.id
          groupIds: ['blob']
        }
      }
    ]
  }
  dependsOn: [network]
}

resource blobDnsGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = {
  parent: blobEndpoint
  name: 'blob'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'blob'
        properties: {
          privateDnsZoneId: blobDns.id
        }
      }
    ]
  }
}

resource cu 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: target.content_understanding_name
  location: target.location
  tags: tags
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: target.content_understanding_name
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
    allowProjectManagement: true
  }
}

resource cuUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(cu.id, identity.id, cognitiveUserRole)
  scope: cu
  properties: {
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: cognitiveUserRole
    description: 'Owned datacrafting Function native Content Understanding analysis'
  }
}

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: target.plan_name
  location: target.location
  tags: tags
  kind: 'functionapp'
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true
  }
}

resource app 'Microsoft.Web/sites@2024-04-01' = {
  name: target.function_name
  location: target.location
  tags: tags
  kind: 'functionapp,linux'
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    enabled: activate
    publicNetworkAccess: activate ? 'Enabled' : 'Disabled'
    serverFarmId: plan.id
    httpsOnly: true
    virtualNetworkSubnetId: resourceId('Microsoft.Network/virtualNetworks/subnets', network.name, 'functions')
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${storage.properties.primaryEndpoints.blob}function-packages'
          authentication: {
            type: 'UserAssignedIdentity'
            userAssignedIdentityResourceId: identity.id
          }
        }
      }
      runtime: {
        name: 'python'
        version: '3.12'
      }
      scaleAndConcurrency: {
        instanceMemoryMB: 512
        maximumInstanceCount: 40
        triggers: {
          http: {
            perInstanceConcurrency: 1
          }
        }
      }
    }
    siteConfig: {
      minTlsVersion: '1.2'
      scmMinTlsVersion: '1.2'
      ftpsState: 'Disabled'
      appSettings: [
        { name: 'AzureWebJobsFeatureFlags', value: '' }
        { name: 'AzureWebJobsStorage__accountName', value: storage.name }
        { name: 'AzureWebJobsStorage__credential', value: 'managedidentity' }
        { name: 'AzureWebJobsStorage__clientId', value: identity.properties.clientId }
        { name: 'AZURE_CLIENT_ID', value: identity.properties.clientId }
        { name: 'WEBSITE_AUTH_AAD_ALLOWED_TENANTS', value: target.tenant_id }
        { name: 'FUNCTIONS_REQUEST_BODY_SIZE_LIMIT', value: '1000000' }
      ]
    }
  }
  dependsOn: [blobOwner, containers, blobDnsGroup, blobLink, cuUser]
}

resource auth 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: app
  name: 'authsettingsV2'
  properties: {
    platform: {
      enabled: true
      runtimeVersion: '~1'
    }
    globalValidation: {
      requireAuthentication: true
      unauthenticatedClientAction: 'Return401'
    }
    httpSettings: {
      requireHttps: true
    }
    login: {
      tokenStore: {
        enabled: false
      }
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: apiClientId
          openIdIssuer: 'https://login.microsoftonline.com/${target.tenant_id}/v2.0'
        }
        validation: {
          allowedAudiences: [apiClientId, 'api://${apiClientId}']
          defaultAuthorizationPolicy: {
            allowedApplications: ['04b07795-8ddb-461a-bbee-02f9e1bf7b46']
            allowedPrincipals: {
              identities: [target.operator_principal_id]
            }
          }
        }
      }
    }
  }
}

resource basicPolicies 'Microsoft.Web/sites/basicPublishingCredentialsPolicies@2024-04-01' = [for policy in ['ftp', 'scm']: {
  parent: app
  name: policy
  properties: {
    allow: false
  }
}]

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: target.logs_name
  location: target.location
  tags: tags
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
    workspaceCapping: {
      dailyQuotaGb: json('0.1')
    }
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
      disableLocalAuth: true
    }
  }
}

resource diagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'owned-function-errors'
  scope: app
  properties: {
    workspaceId: logs.id
    logAnalyticsDestinationType: 'Dedicated'
    logs: [
      {
        category: 'FunctionAppLogs'
        enabled: true
      }
    ]
  }
}

output inventory object = {
  function_id: app.id
  function_hostname: app.properties.defaultHostName
  workload_identity: {
    id: identity.id
    client_id: identity.properties.clientId
    principal_id: identity.properties.principalId
  }
  storage_id: storage.id
  content_understanding_id: cu.id
  content_understanding_endpoints: cu.properties.endpoints
  network_id: network.id
  private_endpoint_id: blobEndpoint.id
  logs_workspace_id: logs.id
  role_assignment_ids: [blobOwner.id, cuUser.id]
}