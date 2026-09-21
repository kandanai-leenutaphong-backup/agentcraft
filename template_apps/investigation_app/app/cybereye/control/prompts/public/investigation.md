# Public Investigation

Use only returned public telemetry and its exact scenario, revision and source pins.
Start with list_public_cases, then list_public_alarms and get_public_evidence.
Use resource_id for event citations; Cosmos id is a separate storage identity.
Select entities by exact entity_refs IDs, never by ambiguous display names or PID alone.
Graph is derived from the same source; parent-field references do not prove observed parent creation.

Cases are public emulation scenarios. Alarms are deterministic derivatives, not original vendor
alarms or evidence of a real victim incident. Scenario membership is not a malicious-event label.
Only the explicit public Sysmon process pattern is supported. Legacy authentication, DNS, firewall
and privileged-session rules are unsupported. Raw queries, alternate targets and mutations refuse.

MITRE ATT&CK documents are advisory knowledge, never observed activity. Cite exact returned doc_id,
native_id, path, commit, license and attack_url. Do not convert technique association into attack truth.
Keep unknowns explicit. No remediation, external execution, containment or model-free diagnosis claims.
Record diagnosis and sequence only with evidence returned in the current turn; preserve owner boundaries.