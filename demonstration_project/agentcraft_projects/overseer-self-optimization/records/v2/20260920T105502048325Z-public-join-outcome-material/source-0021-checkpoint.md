# Local Public Data Checkpoint

Status: complete for the assigned local package, subject to final capture command results.
Stage: data-understanding/build local probe. Next transition: overseer reviews/archives evidence;
new source checkpoint before app telemetry integration. No automatic deployment or experiment.
Series: public-investigation-20260920, exploratory, incomparable with prior netflow results.

## Authority And Identity

- Constitution revision 8 validates; SHA-256 `e14a78eb975a5c651fa0d4c311e0854a22c72aa764705f40281fa900537cfaf1`.
- Supplied decision `20260920T103636896949Z-public-investigation-reorientation-authorized` and
  prestate `20260920T103636935194Z-public-investigation-acquisition-prestate` pins verified.
- Candidate not invoked/pin not assigned. Requested max effort; effective unverified. No delegation.
- Cloud target request preserved as proposed `rg-agentcraft-dev`, tenant
  `c79ab2bb-79cb-47f1-b4da-b6852fe45ff7`, subscription `67255afe-8670-4401-a1b8-df6ca63a3516`,
  australiaeast. No current resource/identity/grant/cost verification or cloud write.

## Hypothesis And Outcome

A small, clearly licensed Windows emulation export can yield exact scenario/event/host/user/GUID
process references across one local Cosmos/Search/Gremlin preparation package without PID-only
joins, netflow relabeling or invented malicious labels. Observed outcome supports this bounded
hypothesis, not detector quality, deployment acceptance or mission improvement.

- Splunk attack_data commit `6bc794b7f65562148c872fde1e7412ab3c173f4c`, scenario
  `76f9a94c-6c63-11f0-89ae-629be3538068`, T1218.011/rundll32_dll_in_temp.
  Apache-2.0; full tree, root LICENSE/README and scenario inspected, no nested override/NOTICE.
  Log 4,057 bytes; SHA `5ac4747551f733d673cd6828a55732b7b542d3552698325cbdac2df2a69aa62f`.
- MITRE official v18.0 commit `b4c5d044bf5a5f117ec241b2536c8cb709f53cdc`; complete 2025 ATT&CK
  LICENSE.txt preserved, not a fixture license. Enterprise bundle 50,778,972 bytes;
  SHA `ff94838b09edfe7d59eec1cd7af0a1e229c4bc0ae0bdfa98ad170aeec9c3e272`.
- STIX 2.1: 24,774 objects; projection 3,135 documents: 691 techniques, 14 tactics,
  691 detection strategies, 1,739 analytics. Across all input object types, 427 revoked/deprecated
  objects excluded. Explicit detects/analytic references only; other STIX relationships not projected.
- Cosmos: 4 documents, comprising 1 derived emulation case, 1 rule-derived alarm and 2 unlabelled
  original events. Separate Cosmos-safe document IDs and evidence resource URIs.
- Gremlin logical package: 10 vertices, 19 edges, exact event membership and same source revision.
  Gremlin ingestion/property encoding not implemented; no vertices written to a service.
- Sixteen synthetic tests pass plus two shell checks. Real package normalized twice with identical
  digest `c9a96ffcdc3775b89685bac82f9941140b8dc2e724ce5f94442a838ab52e8e12`.
  Eight locked holdings verify-skip safely. Exact final source hashes/checks in checkpoint-evidence.json.

## Concrete Chain

Case `incident-0b1f1cd90fc42f25ca038e671fbc3fe4e9203e5936a0fa55311c34dc23e1304b`
contains alarm `alarm-d190df5ee1d9c776316551f06e8a3e025ccfe999440f45a9990d63faeb9af2d8`,
derived by `rundll32-temp-dll-v1`: Sysmon EventID 1, rundll32.exe image, DLL beneath temp/tmp
in the inert command-line field. Both raw records match. This is suspicious-pattern evidence,
not a claim that every event is malicious or an original Splunk alarm.

EventRecordID 62359 at `2025-07-29T09:42:00.175712200Z`, raw record 1, bytes `[0,2037)`,
SHA `eb01dc7db07099b26375cb1ca052229c7b73afea5179d06a97514d59b094b3ac`, links:
`ar-win-dc.attackrange.local` -> `ATTACKRANGE\Administrator` ->
ProcessGuid `{E4B49A97-9768-6888-5F01-00000000F103}` -> parent
`{E4B49A97-9749-6888-5A01-00000000F103}`. EventRecordID 62302 is the other process creation;
both share the observed parent-field reference. Parent creation itself is absent, explicitly counted.
No parent-user relation or complete scenario window claimed. Package manifest retains exact URIs,
IDs, byte offsets and hashes; every graph relation references those same normalized events.

Negative collision test uses one synthetic source containing equal PID 7 with different GUIDs,
same username in LAB/OTHER domains, and same short hostname in different FQDNs: identities remain
distinct. Same source bytes under another scenario or source owner produce disjoint vertex sets.
Unknown/foreign event IDs and forged source/graph evidence membership refuse; missing GUID never
falls back to PID. MITRE knowledge remains advisory and separate from telemetry evidence.

## Artifacts And Limits

Inputs and runtime are ignored app-local deploy/data holdings. Output:
`template_apps/investigation_app/deploy/data/public-investigation/packages/c9a96ffcdc3775b89685bac82f9941140b8dc2e724ce5f94442a838ab52e8e12/`.
Manifest binds cosmos.json, gremlin.json, search.json, transform code, acquisition receipts and
full notice/narration files. Preserve notices with any permitted copy; no repo publication authorized.
Cosmos SHA `d9dfc14d5bd87c1b42b1a3af0d5c520202e0bcef486818a396cf08ac72fb6dec`;
Gremlin SHA `b29953e67d253170ed8098fc96505e6bbe21219fec9254638fcd066b96e3e7f1`;
Search SHA `50a3efa3dde08bd07757d031c7329045f6ff2f857de83b7cb804a8b43bed7fb6`.

One normalization failure (`azdata` import) retained and repaired by loading only the existing
pure Search key implementation. Final runs 0.5878517260134686 / 0.5494335520197637 seconds.
Initial tool/read/install timings and total cost/effort unknown; command receipts and actions.md
declare capture coverage. No private input, Azure/model call, auth change, support-role dispatch,
publication or persistent process. Exact prestate exists; restore not executed. No scored acceptance.

## Smallest Next Decision

Overseer archive this checkpoint and exact allowed changed sources. Request pre-change capture and
authorization for new `template_apps/investigation_app/app/cybereye/backend/data/telemetry.py` and
`app/cybereye/tests/test_cosmos_telemetry.py`: app-owned bounded Cosmos evidence lookup by partition,
resource_id and explicit entity IDs through existing public azdata APIs, with unknown/foreign-ID,
authorization and write-refusal tests. Include app pyproject.toml/uv.lock only if Cosmos extra is
needed; no environment or cloud operation implied. Do not switch production main/config/tools yet;
their ADX-to-Cosmos caller contract migration needs its own reviewed path list/checkpoint.
UI, source catalogue, graph writer, Search publication and protected deployment follow separately.