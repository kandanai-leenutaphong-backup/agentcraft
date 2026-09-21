targetScope = 'resourceGroup'

param location string
param names object
param tags object
param runtimeConfig object
param tenantId string
param subscriptionId string
param image string
param external bool = false

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' existing = {
  name: names.environment
}
resource runtime 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: names.identity
}
resource ingestion 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' existing = {
  name: '${names.identity}-ingest'
}
resource registry 'Microsoft.ContainerRegistry/registries@2023-07-01' existing = {
  name: names.registry
}

var tableEndpoint = 'https://${names.storage}.table.core.windows.net'
var readonlySecretUri = 'https://${names.vault}.vault.azure.net/secrets/graph-readonly'
var writerSecretUri = 'https://${names.vault}.vault.azure.net/secrets/graph-ingestion'
var packageDigest = 'c9a96ffcdc3775b89685bac82f9941140b8dc2e724ce5f94442a838ab52e8e12'

resource job 'Microsoft.App/jobs@2024-03-01' = {
  name: 'agentcraft-dev-ingest'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${ingestion.id}': {} } }
  properties: {
    environmentId: environment.id
    configuration: {
      triggerType: 'Manual'
      replicaTimeout: 1800
      replicaRetryLimit: 0
      manualTriggerConfig: { replicaCompletionCount: 1, parallelism: 1 }
      registries: [{ server: registry.properties.loginServer, identity: ingestion.id }]
      secrets: [{ name: 'graph-writer', keyVaultUrl: writerSecretUri, identity: ingestion.id }]
    }
    template: {
      containers: [{
        name: 'ingest'
        image: image
        command: ['python', '/workspace/deploy/investigation_loader.py']
        args: ['--package', '/workspace/package', '--config', '/workspace/deploy/env/agentcraft-dev.json']
        resources: { cpu: 1, memory: '2Gi' }
        env: [
          { name: 'AZURE_CLIENT_ID', value: ingestion.properties.clientId }
          { name: 'GREMLIN_INGESTION_KEY', secretRef: 'graph-writer' }
          { name: 'PYTHON_DOTENV_DISABLED', value: '1' }
        ]
      }]
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: names.app
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${runtime.id}': {} } }
  properties: {
    managedEnvironmentId: environment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: { external: external, targetPort: 8080, transport: 'auto', allowInsecure: false }
      registries: [{ server: registry.properties.loginServer, identity: runtime.id }]
      secrets: [{ name: 'graph-readonly', keyVaultUrl: readonlySecretUri, identity: runtime.id }]
    }
    template: {
      scale: { minReplicas: 1, maxReplicas: 1 }
      containers: [{
        name: 'app'
        image: image
        resources: { cpu: 1, memory: '2Gi' }
        probes: [
          { type: 'Liveness', httpGet: { path: '/healthz', port: 8080 }, initialDelaySeconds: 30, periodSeconds: 20 }
          { type: 'Readiness', httpGet: { path: '/healthz', port: 8080 }, initialDelaySeconds: 10, periodSeconds: 10 }
        ]
        env: [
          { name: 'AZURE_CLIENT_ID', value: runtime.properties.clientId }
          { name: 'CYBEREYE_TELEMETRY_PROFILE', value: 'public-cosmos' }
          { name: 'CYBEREYE_COSMOS_ENDPOINT', value: 'https://${names.cosmos}.documents.azure.com' }
          { name: 'CYBEREYE_COSMOS_DATABASE', value: 'investigation' }
          { name: 'CYBEREYE_COSMOS_CONTAINER', value: 'telemetry' }
          { name: 'CYBEREYE_STATE_CONTAINER', value: 'state' }
          { name: 'CYBEREYE_PUBLIC_MANIFEST', value: '/workspace/package/manifest.json' }
          { name: 'CYBEREYE_PUBLIC_MANIFEST_SHA256', value: packageDigest }
          { name: 'CYBEREYE_AGENT_STORE_DIR', value: '/state/agents' }
          { name: 'CYBEREYE_OPENAI_ENDPOINT', value: 'https://han-primary-foundry-resource.openai.azure.com/openai/v1/' }
          { name: 'CYBEREYE_MODEL', value: 'gpt-5.6-luna' }
          { name: 'CYBEREYE_ALLOW_MODEL_CALLS', value: 'true' }
          { name: 'CYBEREYE_SEARCH_ENDPOINT', value: 'https://${names.search}.search.windows.net' }
          { name: 'CYBEREYE_MITRE_SEARCH_INDEX', value: 'public-mitre' }
          { name: 'GREMLIN_ACCOUNT', value: names.gremlin }
          { name: 'GREMLIN_DATABASE', value: 'investigation' }
          { name: 'GREMLIN_GRAPH', value: 'ontology' }
          { name: 'GREMLIN_RESOURCE_GROUP', value: resourceGroup().name }
          { name: 'GREMLIN_SUBSCRIPTION_ID', value: subscriptionId }
          { name: 'GREMLIN_READONLY_KEY', secretRef: 'graph-readonly' }
          { name: 'AUTH_TENANT_ID', value: tenantId }
          { name: 'AUTH_CLIENT_ID', value: runtimeConfig.client_id }
          { name: 'AUTH_PUBLIC_ORIGIN', value: runtimeConfig.origin }
          { name: 'AUTH_SESSION_TABLE_ENDPOINT', value: tableEndpoint }
          { name: 'AUTH_SESSION_TABLE_NAME', value: 'auth' }
          { name: 'DEV_PUBLIC_KEY_ED25519', value: runtimeConfig.public_key }
          { name: 'DEV_REPLAY_LEDGER', value: 'azure-table' }
          { name: 'DEV_REPLAY_TABLE_ENDPOINT', value: tableEndpoint }
          { name: 'DEV_REPLAY_TABLE_NAME', value: 'replay' }
          { name: 'CYBEREYE_ALLOWED_PRINCIPAL_IDS', value: 'entra:${tenantId}:${runtimeConfig.owner_object_id},devkey:${runtimeConfig.fingerprint}:default' }
          { name: 'CYBEREYE_CORS_ORIGINS', value: runtimeConfig.origin }
          { name: 'PYTHON_DOTENV_DISABLED', value: '1' }
        ]
      }]
    }
  }
}

output appId string = app.id
output jobId string = job.id
output ingressExternal bool = external
output appFqdn string = app.properties.configuration.ingress.fqdn