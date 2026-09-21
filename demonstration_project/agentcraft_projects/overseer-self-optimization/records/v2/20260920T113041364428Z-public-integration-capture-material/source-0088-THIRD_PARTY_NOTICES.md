# Public Investigation Source Notices

Local preparation only. This file does not authorize repository publication, imply endorsement,
or certify licenses of the whole app/dependency closure. No OTRF content is included: its observed
MIT LICENSE/GPL README conflict remains unresolved. No private Perth data is part of this package.

## Splunk Attack Data

- Source: https://github.com/splunk/attack_data/tree/6bc794b7f65562148c872fde1e7412ab3c173f4c
- Scenario: `datasets/attack_techniques/T1218.011/rundll32_dll_in_temp/`, authored by
  Teoderick Contreras, Splunk; generated in Attack Range, dated 2025-07-29.
- License: Apache License, Version 2.0. Exact pinned LICENSE SHA-256:
  `8505946b2464fa90223996d99eecbc7639a86648ca071f0cac21695be2623a0a`.
- LICENSE retains `Copyright [2023] [Splunk Inc]`; root README retains
  `Copyright 2025 Splunk Inc.`. The complete pinned tree contains no upstream NOTICE or
  nested license affecting the selected files. Both notices and full terms are preserved verbatim.
- Raw log is unchanged. Cosmos documents, derived alarm/case, graph and identity normalization
  are Agentcraft transformations, not upstream labels or an upstream-endorsed detector.
- Every generated package includes `notices/splunk/LICENSE`, `notices/splunk/README.md`,
  and `notices/splunk/scenario.yml`. Preserve them with permitted redistribution.

## MITRE ATT&CK

- Official v18.0 release: https://github.com/mitre-attack/attack-stix-data/tree/b4c5d044bf5a5f117ec241b2536c8cb709f53cdc
- Bundle: `enterprise-attack/enterprise-attack.json`; STIX 2.1. Advisory knowledge only.
- Terms: ATT&CK nonexclusive royalty-free research, development and commercial-use license,
  conditional on reproducing MITRE's copyright designation and complete license. This is
  not an MIT, Apache or Creative Commons license. No trademark/endorsement right inferred.
- Exact 2025 notice, permission wording and all disclaimers are copied byte-for-byte into
  every package at `notices/mitre/LICENSE.txt`; SHA-256
  `d67e295e4a569b59ca0f728cadf99103b07680c5a9ecff302e1ee3c4ad289e06`.
  Never substitute a newer master-branch notice or a synthetic test fixture's license.
- Derived Search projection filters revoked/deprecated objects and retains original native IDs,
  modified times, release, commit, source digest, URLs and license provenance. Preserve the full
  notice file with any permitted copy of the documents. External linked reports were not acquired.

[Source lock](deploy/public_sources.lock.json) carries exact paths, acquisition URLs, byte sizes,
rights-review basis and hashes. Raw receipts remain beside ignored inputs; package manifests bind
their hashes. Local test fixtures are explicitly synthetic, not copied source data.