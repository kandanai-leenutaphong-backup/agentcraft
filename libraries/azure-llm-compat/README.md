# Azure LLM Compatibility Retired

B03 removes this runtime, package metadata/lock and raw Responses compatibility tests.
Both template hosts use [llm_interface](../llm-interface/CONTRACT.md) and OpenAI 3.13.x.
There is no compatibility import, provider-ID continuation, raw SDK escape hatch or second
tool loop. Native Agent Framework owns invocation and semantic run events.

Credentials are explicit and borrowed; model calls default denied. Hosts supply exact tool
schemas, authorizers and authenticated session owners. Interrupted sessions do not replay.
Historical campaign records and receipts remain unchanged, not reinterpreted or re-certified.

Removal rationale and current gates: [B02/B03 record](../azure-data-connectors/MIGRATION_B02_B03.md).
Live inference, provider compatibility and deployed identity remain separately unverified.
