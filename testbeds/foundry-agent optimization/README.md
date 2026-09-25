# Foundry Agent Optimization

SDK migration live acceptance passed on separate `agentcraft-migration-iris-v1`.
Two baseline-only jobs remain retained; third development-only job
`opt_4d8f98325041438aa3fa24dd54050bd4` returned baseline plus two generated configs.
Actual configs loaded as versions 3/4/5 on the uv-locked repaired image; nine stored
responses and instruction hashes verified. Native scores: 1/3, 2/3, 3/3; independent
development scores: 0/3, 2/3, 3/3. Not prediction improvement or generalization.
Both grader mappings prove 1/0/0. Native cancellation and anonymous refusal pass.
Fifty-one tests pass, including offline [replay equivalence](tests/test_replay_equivalence.py): migrated
code recomputes retained validation, selection, holdout and canary evidence exactly. F09 accepted, 2026-09-22:
[authoritative result](../../agentcraft_projects/foundry-official-integration-20260922/records/v2/20260922T200128628556Z-f09-migration-accepted/record.json).
[Migration procedure and exports](deploy/README.md#migration-canary-current-procedure).
Historical metrics, scorer, constitution and holdout below remain unchanged.

Live revision-2 execution. Native-generated demonstration configuration is active as hosted version 6; native
optimizer job `opt_21aee306b2db4bebb7eb89a07d9c1f8d` completed with baseline
and two generated instruction candidates. Earlier mapping-failed job is retained.

- [Specification](../../specs/20260922_FOUNDRY_AGENT_OPTIMIZATION.md) owns scope, frozen acceptance, native candidate semantics and next live increment.
- [Constitution](agentcraft_projects/foundry-agent-optimization/constitution/constitution.yaml) freezes task and local evaluator.
- [Dataset manifest](agentcraft_projects/foundry-agent-optimization/dataset/manifest.json): UCI Iris, verified CC BY 4.0, 147 unique rows, 87/30/30 stratified partitions.
- [Operator sequence](deploy/README.md) reproduces acquisition, preparation, verification and read-only preflight.
- [Configuration](configuration.yaml) loads through canonical `agentconfig`; [composition](composition.py) uses caller-owned `llm_interface` model, with no second engine.

Hosted baseline: accuracy 0.933333, macro-F1 0.933333, invalid rate 0 on all 30
validation rows, with stored-response readback. Independent validation: native
baseline 29/30, both generated prompts 28/30. Frozen selection retained baseline.
Historical final holdout: original baseline and selected baseline configuration each
30/30, accuracy and macro-F1 1.0, invalid rate 0. Those records remain unchanged.
Parent separately authorized native-generated `_0001` as a DEMONSTRATION, selected
only by existing validation with candidate-ID tie-break, not production promotion
or best-candidate selection. Validation regressed: macro-F1 0.9326599326599326 versus
baseline 0.9665831244778613. Generated candidate holdout: **not evaluated**.
Capability victory means native optimizer generated changed configuration actually
hosted plus complete candidate metrics, not guaranteed quality improvement.
No new optimizer run, holdout scoring, improvement or generalization claim.
Raw source and holdout are evaluator-only; candidate artifacts contain train/validation only.
Image contains 61 allowlisted source files and no dataset/private paths.

Native custom evaluator positive/wrong/invalid canaries returned 1/0/0. Official
optimization loader 1.0.0b1 feeds canonical agentconfig and llm_interface MAF.
Anonymous invocation refuses with 401; live config/prompt hashes and stored
response readback pass. Protected hosted v3 remains unchanged. Dedicated
gpt-5.4 optimizer deployment is retained. Native candidate IDs are not generations.

[Demonstration result](deploy/evidence/demonstration-result.json) proves v6 active,
three train-only authenticated scenarios, loaded native config/instruction digests,
stored-response readback and anonymous 401. Baseline v5 remains active restore target.
[Metrics CSV](deploy/evidence/candidate-validation-metrics.csv) and
[JSON](deploy/evidence/candidate-validation-metrics.json) retain baseline and both
generated candidates, independent scores and Foundry evaluation/run IDs. Generation
and parent remain null; native composite score is not independent macro-F1.