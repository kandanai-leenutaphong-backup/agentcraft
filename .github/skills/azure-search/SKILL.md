---
name: azure-search
description: "Use for Azure AI Search index schemas, document CRUD, semantic/vector/hybrid queries and explicit batch-result verification. The complete Python client supports injected identity and HTTP transport. Prefer existing azure-data-connectors for read-only MCP queries; this skill adds operator-owned index and write APIs, not automatic write authority."
---

# Azure Search

Install this directory as a Python package; import `azure_search`. The public exports in
[the package initializer](python/azure_search/__init__.py) define configuration, index/field/vector
schemas, `SearchIndexClient`, `Transport`, typed errors and safe document keys.

Supply `SearchConfig` at the composition edge and inject `Transport(credential=..., opener=...)`.
The optional default uses `azure.identity.DefaultAzureCredential`, never an application import.
Do not invoke cloud writes merely to verify installation. Index deletion/schema changes need explicit
operator authority and read-back. A service 200/207 is not proof every document succeeded.

The [fake-service suite](tests/test_azure_search.py) verifies CRUD, per-document failures, retries,
schema/query shape and name validation. Run with the skill's `python` directory on `PYTHONPATH`:
`python3 -m unittest discover -s "$SKILL_ROOT/tests" -q`. No credentials or network are used.
Live Search permissions, endpoint policy and provider behavior remain separately unverified.