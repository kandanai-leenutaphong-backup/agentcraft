# Foundry Evaluation Capability Proof

Strict SDK-result acceptance and fresh manifest binding are offline-tested; new live
acceptance remains pending. Use the [migration procedure](deploy/README.md#migration-canary-current-procedure),
not historical unmanifested writes. Historical results below are unchanged.

**Completed live evaluation, 2026-09-22.** This testbed proves evaluation
integration only; its directory name does not imply an optimization campaign.
No quality improvement or statistical claim is made.

Existing hosted agent `agentcraft-hosted-tool-proof`, version `3`, remains active
and unchanged. Its immutable image, source/configuration hashes and accepted
hosting receipts passed readback. Existing judge `gpt-5.6-luna`, model version
`2026-07-09`, scored all three rows through `builtin.coherence`.

One dataset/version, one definition and one run completed. Registered bytes read
back exactly: 134 bytes, frozen SHA-256. Eighteen offline tests pass.

| Query | Coherence / 5 | Threshold | Oracle |
| --- | --- | --- | --- |
| `00000000000000000000000000000001` | 4, pass | 3 | pass |
| `0123456789abcdef0123456789abcdef` | 4, pass | 3 | pass |
| `ffffffffffffffffffffffffffffffff` | 2, fail | 3 | pass |

Dataset: `hosted-nonce-learning`, version `sha256-7fa1aa57385f15a1eaead798f022f7cd`.
Evaluation: `eval_fdd44584d8ab47d297774229b7a29522`.
Run: `evalrun_c8d178cf43b546bc89af7328bea82164`.
[Foundry report](https://ai.azure.com/nextgen/r/ZyVa_oZwRAGhuN9spjo1Fg,personal-llm,,han-primary-foundry-resource,han-primary-foundry/build/evaluations/eval_fdd44584d8ab47d297774229b7a29522/run/evalrun_c8d178cf43b546bc89af7328bea82164).

Four reservation requests, two blob uploads and three registration requests were
needed; only one version registered. First two attempts failed local guards before
bytes. Third uploaded bytes but registration rejected the 71-character version;
registration-only diagnostic replay exposed the 50-character service limit.
Fourth reservation used a valid version and completed. All failures remain retained.
Initial result extraction mishandled JSON-encoded content blocks; replaying retained
outputs repaired the adapter without another run or inference.

- [Approved bounds and pins](deploy/records/approved-decision.json).
- [Judge selection and SDK prerequisites](deploy/records/selection.json).
- [Failed upload receipt](deploy/records/20260922T072841080789Z-upload.json).
- [Read-only reconciliation](deploy/records/20260922T072927085513Z-inspect-upload.json).
- [Recovery authorization](deploy/records/reservation-recovery-decision.json).
- [Second failed upload](deploy/records/20260922T073816162404Z-upload.json).
- [Eighteen passing tests](deploy/records/20260922T075746929453Z-validate.json).
- [Live verification](deploy/records/20260922T075653771799Z-verify.json).
- [Final result and settlement](deploy/records/20260922T075756325970Z-closeout.json).
- [Reusable Skill: Hosted Evaluation Integration](deploy/README.md#reusable-skill-hosted-evaluation-integration).

Final receipt SHA-256: `1d1caa3fd83116ff8476c97c496ee28122bd5092dfac1972e3287590d6964a9f`.
Hosting and judge unchanged; dataset, evaluation, completed run, registered blob,
one orphan uploaded blob and possible reservations retained. No cleanup, new agent,
optimization, worker dispatch or background process. Cost, reservation lifetime and
effective runtime effort unknown. No further write is authorized by this completion.
[Specification](../../specs/20260922_FOUNDRY_HOSTED_AGENT_EVALUATION.md) owns acceptance;
[operator recipe](deploy/README.md) owns reusable contracts and failure lessons.