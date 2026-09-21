# Foundry Adoption Lessons

## 2026-09-21 | foundry-adoption-research-20260921 | Separate adoption boundaries from documentation coverage

- Constitution: revision 1; SHA256
  `2c6468359916f0cec2bb7a6f91a108a4747837b58fbfe0ad0d877adba6decd6b`.
  Authority: [current research decision](../records/v2/20260921T112305597191Z-foundry-adoption-research-decision-20260921/record.json).
- Question/attempt: can current official family documentation sharpen the earlier
  evaluation/hosting/optimizer advisory without implying adoption? Research worker
  mapped public sources to existing local contracts; [handoff](../results/20260921-research/evidence/handoff.md)
  and [final research verification](../results/20260921-research/evidence/verification-final.json)
  supply evidence, not live acceptance.
- Evaluation is separable from hosting: score recorded outputs without migrating
  application execution. Paid judge calls still require authorization; target-based
  evaluation can execute agents/tools. Preserve frozen data, rubric and judge pins.
  Sources: [P22](../SOURCES.md#p22), [P13](../SOURCES.md#p13), [P09](../SOURCES.md#p09).
- Classify managed Foundry service, SDK/open-source framework and adjacent Azure
  service separately. Framework workflows do not establish managed hosting;
  shared branding does not merge APIs, billing, identity or data terms.
  Sources: [P16](../SOURCES.md#p16), [F49](../SOURCES.md#f49),
  [F21](../SOURCES.md#f21), [F28](../SOURCES.md#f28).
- Agent Optimizer is a service/configuration optimizer, not a mission or arbitrary
  application-code optimizer. Hosted use needs an approved configuration loader
  and supported Responses integration; model-weight training is separate.
  Validation feedback remains development evidence; estimates are not hard spend
  caps. Retain AgentCraft strategy, refusals, independent evaluation and recovery.
  Sources: [P06](../SOURCES.md#p06), [P27](../SOURCES.md#p27),
  [P28](../SOURCES.md#p28), [P25](../SOURCES.md#p25), [P15](../SOURCES.md#p15).
- Current public GA/preview/retirement documentation adds specificity beyond the
  prior advisory, not tenant proof. Agent Service GA does not make every hosted
  subfeature GA; declarative Foundry workflow documentation states retirement on
  2026-12-01. Recheck exact feature/version/region before selecting a dependency.
  Sources: [F02](../SOURCES.md#f02), [P04](../SOURCES.md#p04),
  [F65](../SOURCES.md#f65), [F36](../SOURCES.md#f36).
- Coverage units matter: 173 feature entries across 11 families are adoption
  decisions, not exhaustive SKUs. Source collection contains 83 fresh acquisitions
  and 30 retained records: 24 reference pages, five discovery responses and one
  historical 404. Retained records were hash-verified, not refetched. Failed P01
  and successful replacement F38 preserve lookup history; neither navigation nor
  search counts establish feature maturity. Sources: [coverage gaps](../FEATURES.md#coverage-and-honest-gaps),
  [availability](../SOURCES.md#evidence-and-availability),
  [P01](../SOURCES.md#p01), [F38](../SOURCES.md#f38).
- Reuse or extend [existing owners](../FEATURES.md#existing-owners): `llm_interface`
  for invocation, `modular-agents` for definitions/bundles, `agent_optimization`
  for frozen evaluation, `azdata` for bounded data access, existing identity,
  deployment and recovery owners for their contracts. Do not create parallel
  loops or infer Foundry compatibility from a local bundle. Mapping is
  contract-backed; package tests and live integrations were not rerun.
- Conclusion/confidence: supported as dated documentation and supplied verification
  evidence only. All proposed integrations remain `not_verified`; tenant
  entitlement, live compatibility, security outcomes and actual cost are unknown.
  No baseline or accepted-change denominator exists; effort savings are unknown,
  effort per accepted change undefined, not zero. [Measurement boundary](../FEATURES.md#proposed-phases-and-acceptance).
- Historical discovery boundary: the handoff reported final outcome archival
  **pending**. This describes that checkpoint only, not current archival status,
  acceptance or restoration completeness; authoritative outcomes belong to the
  archivist. No acceptance change or follow-on experiment follows from this note.
- Lesson/next: use documented capabilities to select a separately authorized,
  frozen evaluation/tracing pilot; require exact-target read-back and measured
  like-for-like effort before claiming readiness or savings.