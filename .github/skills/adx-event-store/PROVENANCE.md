# Provenance

This distribution owns the event-store connector, schema inference, guarded CRUD and provisioning
workflow. Its source, contracts, gotchas and offline tests travel together; no source checkout,
customer dataset, deployment identity or private repository is required.

The portable contract includes explicit bootstrap confirmations and target validation,
content-based batch verification, logical CSV counting, a neutral trace name and declared SDK
dependencies. Third-party SDKs remain package-manager dependencies under their own licenses.

The library is an independent distribution snapshot, not a second in-application implementation.
Existing consumers of another connector should reuse it unless this operator workflow is needed.