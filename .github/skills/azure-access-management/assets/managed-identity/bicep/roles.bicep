// roles.bicep — built-in role definition ids, named once.
//
// Module role:
//   Maps a readable role name to the GUID Azure actually wants. Every module
//   that grants access imports this, so a role is written as
//   `roles.searchIndexDataContributor` and never as a bare GUID.
//
// Why this file exists:
//   A role assignment written with a literal GUID is unreviewable. Nobody
//   reading the pull request can tell whether it grants read or owner, and the
//   difference between those two is the entire point of the review. Naming the
//   roles is what turns "reviewing the template" into "reviewing the access".
//
// Why an exported variable rather than a module with outputs:
//   A module is a nested deployment. Using one to carry constants adds a
//   deployment operation, and its outputs only exist at runtime — so the values
//   cannot be used where the compiler needs them. `@export()` is resolved at
//   compile time and costs nothing.
//
// Why the ids are literal rather than looked up:
//   Built-in role definition ids are stable across every Azure tenant and cloud
//   by design. Resolving them at deploy time would add a control-plane read to
//   every deployment for a value that cannot change.

@export()
@description('Built-in role definition GUIDs, by readable name.')
var roleIds = {
  // Generic
  owner: '8e3af657-a8ff-443c-a75c-2fe8c4bcb635'
  contributor: 'b24988ac-6180-42a0-ab88-20f7382dd24c'
  reader: 'acdd72a7-3385-48ef-bd42-f606fba81ae7'
  userAccessAdministrator: '18d7d88d-d35e-4fb5-a5c3-7773c20a72d9'

  // Azure AI Search — control plane and data plane are separate roles, and
  // holding one grants nothing on the other. See GOTCHAS.md G3.
  searchServiceContributor: '7ca78c08-252a-4471-8644-bb5ff32d4ba0'
  searchIndexDataContributor: '8ebe5a00-799e-43f5-93ac-243d3dce84a7'
  searchIndexDataReader: '1407120a-92aa-4202-b7e9-c0e197c71c8f'

  // Azure AI / Cognitive Services
  cognitiveServicesUser: 'a97b65f3-24c7-4388-baec-2e87135dc908'
  cognitiveServicesOpenAiUser: '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
  cognitiveServicesOpenAiContributor: 'a001fd3d-188f-4b5d-821b-7da978bf7442'
  azureAiDeveloper: '64702f94-c441-49e6-a78b-ef80e0188fee'

  // Storage — data plane. "Contributor" on the account does not grant these.
  storageBlobDataReader: '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1'
  storageBlobDataContributor: 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'
  storageQueueDataContributor: '974c5e8b-45b9-4653-ba55-5f855dd0fb88'

  // Key Vault — data plane, for a vault using RBAC rather than access policies.
  keyVaultSecretsUser: '4633458b-17de-408a-b874-0445c86b69e6'
  keyVaultSecretsOfficer: 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7'

  // Cosmos DB control plane. The NoSQL data plane uses its own assignment type
  // (Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments), which is not an
  // RBAC role assignment at all — see GOTCHAS.md G7.
  cosmosDbAccountReader: 'fbdf93bf-df7d-467e-a4d2-9458aa1360c8'

  // Monitoring
  monitoringMetricsPublisher: '3913510d-42f4-4e42-8a64-420c390055eb'
}
