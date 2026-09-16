# Provenance

Canonical owner from 2026-09-16: `libraries/azure-data-connectors/src/azdata/event_store`.
Source baseline: `00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`, formerly
`.github/skills/adx-event-store`. [preservation.json](preservation.json) records every original
path and SHA-256 plus its staged destination. The fixed-manifest migration refuses symlinks,
unknown files, changed original bytes and destination collisions before retiring anything.

All 12 connector modules, bootstrap and both original test files were retained with canonical
imports, not vendored alongside another operator implementation. Original license and historical
gotchas are retained verbatim. Original package requirements remain as explicitly historical
[metadata](legacy-package.toml) and [requirements](legacy-requirements.txt), not install inputs.
The old standalone lock and ignore rules are superseded by the member metadata and parent-owned
workspace resolution; their hashes and source Git baseline remain in the manifest.

Current changes are explicit, not claimed byte-identical: namespace/import routing, lazy exports,
deny-by-default operator grants, named purge/extent confirmations, no wrapper retry of mutating
commands, server-enforced read-only queries, exact identifier fullmatch, unknown-not-absent
provisioning, and managed-streaming acceptance reporting. v4 and operator callers now share one
identifier validator. Their transports remain separate because bounded async results and native
synchronous operator commands have different contracts; neither silently substitutes for the other.

Parent app duplicate removal remains a separate owned change. Its content/metadata helpers are
not the operator connector. No customer source, data, credential or immutable deployment evidence
was copied into this migration. The [caller guide](README.md#migration-map) owns exact imports.

This distribution owns the event-store connector, schema inference, guarded CRUD and provisioning
workflow. Its source, contracts, gotchas and offline tests travel together; no source checkout,
customer dataset, deployment identity or private repository is required.

The portable contract includes explicit bootstrap confirmations and target validation,
content-based batch verification, logical CSV counting, a neutral trace name and declared SDK
dependencies. Third-party SDKs remain package-manager dependencies under their own licenses.

The library is an independent distribution snapshot, not a second in-application implementation.
Existing consumers of another connector should reuse it unless this operator workflow is needed.