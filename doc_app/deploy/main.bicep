// Static writeup hosting: ACR + Container Apps environment + Container App.
//
// Shape follows msiq_accelerator_main/infra/core.bicep: registry admin user is
// disabled and the app pulls with a user-assigned managed identity holding
// AcrPull, so no registry credentials exist anywhere.
//
// Entra sign-in is NOT configured here. Container Apps auth needs a client
// secret, which must not be written into a template or a parameter file; it is
// applied post-deploy by deploy.sh, which stores it as a Container App secret.

@description('Base name for resources. Lowercase alphanumeric and hyphens.')
@minLength(3)
@maxLength(24)
param name string = 'writeup-agent-loop'

@description('Azure region.')
param location string = resourceGroup().location

@description('Container image to run. The placeholder serves until the first real image is pushed.')
param containerImage string = 'mcr.microsoft.com/k8se/quickstart:latest'

@description('Registry login server the app pulls from. Empty on the first pass, when the placeholder image comes from MCR.')
param registryServer string = ''

@description('Reuse an existing Container Apps environment in this resource group. Empty creates a new one with its own Log Analytics workspace.')
param existingEnvironmentName string = ''

var createEnvironment = empty(existingEnvironmentName)
var environmentId = createEnvironment
  ? environment.id
  : resourceId('Microsoft.App/managedEnvironments', existingEnvironmentName)

var suffix = uniqueString(resourceGroup().id)
var acrName = toLower(replace('acr${name}${suffix}', '-', ''))
var acrPullRoleId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d')

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = if (createEnvironment) {
  name: 'log-${name}'
  location: location
  properties: {
    sku: {
      name: 'PerGB2018'
    }
    retentionInDays: 30
  }
}

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: acrName
  location: location
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

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = if (createEnvironment) {
  name: 'cae-${name}'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics!.properties.customerId
        sharedKey: logAnalytics!.listKeys().primarySharedKey
      }
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ca-${name}'
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${identity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      ingress: {
        external: true
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
      registries: empty(registryServer) ? [] : [
        {
          server: registryServer
          identity: identity.id
        }
      ]
    }
    template: {
      containers: [
        {
          name: 'writeup'
          image: containerImage
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
        // Documents are read rarely; scaling to zero makes idle cost nil.
        minReplicas: 0
        maxReplicas: 2
      }
    }
  }
  dependsOn: [
    acrPull
  ]
}

output fqdn string = app.properties.configuration.ingress.fqdn
output url string = 'https://${app.properties.configuration.ingress.fqdn}'
output acrLoginServer string = registry.properties.loginServer
output acrName string = registry.name
output appName string = app.name
output identityClientId string = identity.properties.clientId
