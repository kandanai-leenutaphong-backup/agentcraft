# Portable ADX Gotchas

- G1: Ingestion acceptance is not arrival. Bootstrap reads back the tagged batch; total table count
  cannot establish that a new file was loaded.
- G2: File size is not identity. Different files of the same size must not share a replay tag.
- G3: Quoted CSV fields may contain newlines. Record counts use a CSV parser, not physical lines.
- G4: A confirmation flag is not authorization. Direct provisioning and management KQL still need
  an approved target and the operator/workload's actual Azure permissions.
- G5: Headerless bootstrap inference never worked correctly in the source. It now refuses; use
  the explicit-schema API instead. Existing table recreation additionally needs named confirmation.
- G6: Historical service timings and cluster observations in [references/gotchas.md](references/gotchas.md)
  were retained as source evidence, not rerun during this migration.