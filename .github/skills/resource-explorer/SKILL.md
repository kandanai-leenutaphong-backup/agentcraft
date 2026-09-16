---
name: resource-explorer
description: Use when embedding a React/Python resource explorer, browsing a
  lazy resource tree, reading bounded resource contents or ARM metadata, or
  diagnosing forbidden versus unreachable branches. Canonical resource_explorer
  is host-declared data/agent/tool inventory, not estate-wide subscription
  discovery. Requests cannot widen the registry; no independent estate engine,
  vendored azdata or MCP runtime is shipped.
compatibility: Python 3.11+ for resource-explorer; Node LTS for the optional
  host frontend. Live reads require explicit host authorization, registered
  sources and identity. Tests use synthetic sources, not cloud access.
---

# Resource Explorer

Use installed `resource-explorer` (`resource_explorer`) and
`@agentcraft/resource-explorer`. Read the
[canonical guide](../../../libraries/resource-explorer/docs/skills/resource-explorer.md)
for declared-source inventory, probes, wire errors, bounds, host authentication,
lifecycle and provenance. Estate discovery, the embedded `resource_inventory`
package and vendor azdata are retired. This entry contains no runtime and grants
no live read, credential, administration or cloud-write authority.
