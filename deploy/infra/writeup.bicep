param name string
param registryName string
param location string = resourceGroup().location
param deployApplication bool = false
param containerImage string = ''
param ingressExternal bool = false
param authClientId string
param authTenantId string
param signingPublicKey string = ''

var tags = {
  'managed-by': 'agentcraft-deploy'
  capability: 'writeup'
  purpose: 'project-testing'
}
var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: registryName
  location: location
  tags: tags
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
  }
}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${name}'
  location: location
  tags: tags
}

resource acrPull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, identity.id, acrPullRoleId)
  scope: registry
  properties: {
    roleDefinitionId: acrPullRoleId
    principalId: identity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${name}'
  location: location
  tags: tags
  properties: {}
}

resource app 'Microsoft.App/containerApps@2024-03-01' = if (deployApplication) {
  name: 'ca-${name}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: ingressExternal
        targetPort: 8080
        transport: 'auto'
        allowInsecure: false
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: [
        {
          server: registry.properties.loginServer
          identity: identity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'writeup'
          image: containerImage
          env: [
            {
              name: 'DEV_PUBLIC_KEY_ED25519'
              value: signingPublicKey
            }
          ]
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          probes: [
            {
              type: 'Readiness'
              httpGet: {
                path: '/healthz'
                port: 8080
              }
              initialDelaySeconds: 2
              periodSeconds: 10
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 1
      }
    }
  }
  dependsOn: [
    acrPull
  ]
}

resource auth 'Microsoft.App/containerApps/authConfigs@2024-03-01' = if (deployApplication) {
  parent: app
  name: 'current'
  properties: {
    platform: {
      enabled: true
    }
    globalValidation: {
      unauthenticatedClientAction: 'AllowAnonymous'
    }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true
        registration: {
          clientId: authClientId
          openIdIssuer: '${az.environment().authentication.loginEndpoint}${authTenantId}/v2.0'
        }
        validation: {
          allowedAudiences: [
            authClientId
          ]
        }
      }
    }
    httpSettings: {
      requireHttps: true
    }
  }
}

output registryId string = registry.id
output registryLoginServer string = registry.properties.loginServer
output identityId string = identity.id
output identityPrincipalId string = identity.properties.principalId
output pullRoleAssignmentId string = acrPull.id
output environmentId string = environment.id
output appName string = 'ca-${name}'
output url string = 'https://ca-${name}.${environment.properties.defaultDomain}'