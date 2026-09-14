---
name: resource-inventory
description: "Use when a host-declared datasource allowlist and agent/tool catalogue need a reusable React explorer with bounded previews, selection recovery and dependency highlighting. Adds the registry-backed inventory API; it does not replace the existing Azure estate explorer or grant caller authentication."
---

# Registry Resource Inventory

Embedded in `resource-explorer`. Install this directory's Python package as `resource-inventory`;
import `resource_inventory`. Its [contract](python/resource_inventory/README.md) owns registry,
node identifiers, per-request selection, four read routes, bounded previews and failure statuses.
Frontend source is in the same package's `frontend` directory. Import its npm public surface and
declare `@harness/source-code`; never reach into another application's component directory.

Hosts inject their registry, source probes, API prefix, agent loader and authentication/authorization.
Selection is a narrowing preference, not an access-control claim. Unknown or disabled sources refuse
before probing. Route failures include no-store/private headers and do not echo submitted tokens.
The private `_content` snapshot carries only required data-envelope definitions, not SDK clients.

With this capability's `python` directory on `PYTHONPATH`, run
`python -m unittest discover -s "$SKILL_ROOT/tests" -q` in its declared environment.
The copied suite verifies 43 allowlist, scope, status and service cases without network calls.
The original estate explorer and its four MCP tools stay intact and use their existing runtime.