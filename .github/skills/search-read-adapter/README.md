# Search Read Adapter Retired

Runtime, package metadata and obsolete synchronous tests were removed in B02. No supported
`search_read_adapter` import remains. Both app knowledge readers await public `azdata`
`QueryRequest` and `ReadRequest` operations with explicit borrowed credentials and read grants.

MITRE document keys retain their exact existing encoding in Investigation's document schema.
Filtering, advisory meaning, citation provenance and count/error distinction remain host-owned.
No local corpus, sync Runner, alternate transport or credential fallback replaces this package.

Removal rationale, replacement tests and integration limits:
[B02/B03 record](../../../libraries/azure-data-connectors/MIGRATION_B02_B03.md).
