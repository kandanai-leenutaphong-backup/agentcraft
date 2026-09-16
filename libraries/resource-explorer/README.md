# Resource Explorer

One owner for the allowlisted inventory service, wire schemas, content/status contracts,
and React explorer. Python imports `resource_explorer` and `resource_explorer.content`;
frontend imports `@agentcraft/resource-explorer`. Hosts inject source registries, probes,
credentials and authorization. Requests cannot widen configured source scope.

This package owns no ADX/Search/Gremlin transport, provisioning or write connector.
The optional `azure` extra provides `resource_explorer.probes.AdxProbe`, `SearchProbe`
and `GremlinProbe`. ADX/Search probes use public `azdata`; graph probes receive an explicit
source factory and allowed account. Hosts supply credentials and source coordinates.
Counts, schema ordering, missing/forbidden states, preview bounds and connector cleanup
have one implementation here. A missing graph source factory never discovers identity.
Graph previews use the injected `GraphElementSource`.
The source viewer is the separate `@agentcraft/source-code` dependency.

Source and tests originate at baseline `00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4` in
Investigation's `resource_explorer` and `data_connector_library/core` components.
Original contracts and provenance remain beside the source.

Checks: relocated resource-explorer tests, Investigation inventory tests, both frontend
builds, the existing guarded scanner and catalogue/source-viewer browser read-back.
These source checks do not claim registry publication or deployed auth acceptance.
