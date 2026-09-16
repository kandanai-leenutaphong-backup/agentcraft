targetScope = 'subscription'

param target object
param apiClientId string
param activate bool = false

resource group 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: target.resource_group
  location: target.location
  tags: {
    owner: target.owner
    experiment: 'two-authorized-pdfs'
    lifecycle: 'manual-owned-teardown'
  }
}

module resources './resources.bicep' = {
  name: 'datacrafting-resources-20260916'
  scope: group
  params: {
    target: target
    apiClientId: apiClientId
    activate: activate
  }
}

output inventory object = resources.outputs.inventory