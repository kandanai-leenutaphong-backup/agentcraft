---
name: portable-app-composition
description: >
  Use when a human-authored configuration document must become a running
  application — members, routes, static assets, startup and shutdown order —
  without the document being allowed to name code. Use for versioned canonical
  JSON with a safe YAML form, byte-identical round trips, field-addressed
  validation, unique ids, dependency DAGs and credential refusal; and for
  assembling capabilities through a caller-owned allowlist resolver with
  explicit route and asset ownership, dependency-ordered startup with rollback,
  reverse-order exactly-once shutdown, and availability separated from
  readiness. Trigger phrases: config-driven app, manifest composition, plugin
  entrypoint is unsafe, two members claim the same route, asset collision,
  startup ordering, remove a member and recompose, YAML duplicate key or alias.
---

# Portable App Composition

Read [the canonical guide](../../../libraries/app-composition/GUIDE.md).
Install `portable-app-composition`; import `appcompose`.
The host supplies the resolver, configuration and authorization. Installation grants none.
MCP registration and portable discovery generation remain host integration work.