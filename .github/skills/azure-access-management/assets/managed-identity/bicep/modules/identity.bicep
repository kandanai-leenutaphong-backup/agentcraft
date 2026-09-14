// identity.bicep — one user-assigned managed identity.
//
// Module role:
//   Creates the identity that workloads run as, and outputs the three values
//   every consumer needs: the resource id (to attach it), the principal id (to
//   grant it access) and the client id (to select it at runtime).
//
// Why user-assigned rather than system-assigned:
//   A system-assigned identity is a property of a resource, so it is destroyed
//   and recreated with that resource — and every role assignment referencing it
//   is orphaned, silently, because an assignment holds a principal id rather
//   than a name. A user-assigned identity outlives the compute it is attached
//   to, which means the grants outlive it too. See GOTCHAS.md G2.
//
//   The trade: a user-assigned identity must be attached explicitly, and a
//   workload with more than one must say which to use.

targetScope = 'resourceGroup'

@description('Name of the managed identity. Stable: recreating it under the same name still produces a NEW principal id, which orphans every existing role assignment (GOTCHAS.md G2).')
param name string

@description('Location. Identities are regional resources even though tokens are not.')
param location string = resourceGroup().location

@description('Tags applied to the identity. An identity with no owner tag is one nobody can attribute later.')
param tags object = {}

resource identity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: name
  location: location
  tags: tags
}

@description('Resource id, for attaching the identity to a workload.')
output id string = identity.id

@description('Principal (object) id, for role assignments. This is the value that changes if the identity is recreated.')
output principalId string = identity.properties.principalId

@description('Client id, for selecting this identity at runtime when a workload has several attached.')
output clientId string = identity.properties.clientId

@description('The identity name, echoed so a caller composing outputs does not have to carry it separately.')
output name string = identity.name
