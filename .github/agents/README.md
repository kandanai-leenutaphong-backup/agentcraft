# Workspace agent roster

`overseer` runs a portfolio of independent outcomes. Each `orchestrator` owns one verifiable
increment end-to-end and returns evidence before taking another assignment. Specialists own
bounded work inside that increment and approve nothing.

Every specialist is optional: delegate when it removes real risk or real unknowns, implement
directly otherwise. Contract for all:
[`work-contract.instructions.md`](../instructions/work-contract.instructions.md).

## Available agents

| Agent | Role | Employ when | Mutation boundary |
| --- | --- | --- | --- |
| [`overseer`](overseer.agent.md) | Commissions small outcome teams and owns integration | The objective splits into independently verifiable increments | Edits directly for trivial changes; assigns team work with disjoint ownership |
| [`agentcraft-overseer`](agentcraft-overseer.agent.md) | Owns measurable SME-led missions and live optimization loops | Whole-application AgentCraft development; objective clarification before implementation | Constitution-scoped paths/resources; orchestrator teams plus notebook-only scribe |
| [`local-dev-test-subject`](local-dev-test-subject.agent.md) | Dispatched local cyber-agent candidate | Authorized data understanding and later frozen cyber evaluation | Read/query assigned telemetry; approved scripts may write assigned derived evidence; no evaluator edits |
| [`note_scribe`](note_scribe.agent.md) | Preserves evidence-linked lessons concisely | Each AgentCraft iteration or material discovery | Assigned `agentcraft_projects/<project-id>/notebook/lessons.md` only |
| [`archivist`](archivist.agent.md) | Owns versioned JSON system of record, snapshots and decision-to-outcome links | Before changes, at phase boundaries and after measured outcomes | Assigned project `records/v2/` only via recorder; no candidate, evaluator or live restore writes |
| [`orchestrator`](orchestrator.agent.md) | Owns one verifiable increment end-to-end | One behavior change or bounded uncertainty | Its own assigned paths, contracts, deployments, resources |
| [`architecture-cartographer`](architecture-cartographer.agent.md) | Maps ownership, placement, dependency direction, and final-app readiness | Placement is genuinely contested or topology changed | Read-only except `ARCHITECTURE_STATUS.md` under the docs root |
| [`solution-architect`](solution-architect.agent.md) | Produces a minimum implementation-ready design | The route to value is unclear enough that coding would thrash | Read-only |
| [`data-explorer`](data-explorer.agent.md) | Proves feasibility of unfamiliar authorized sources | Inventory, parsing, rights, or extraction feasibility is unknown | Read-only; never executes source bytes |
| [`developer`](developer.agent.md) | Implements backend, infrastructure, and general code slices | The slice, constraints, and safety signal are known | Assigned writable paths only |
| [`frontend-developer`](frontend-developer.agent.md) | Implements frontend slices with browser evidence | Work belongs to one named frontend surface | Assigned frontend paths only |
| [`documentation_curator`](documentation_curator.agent.md) | Reconciles README, CONTRACT, runbook, and architecture prose with verified source | Documentation reconciliation is worth handing off | Documentation paths only |
| [`experience-evaluator`](experience-evaluator.agent.md) | Measures pre-change impact or a deployed journey | User impact or runtime evidence needs assessment | Read-only browser work |
| [`ui-experience-auditor`](ui-experience-auditor.agent.md) | Cold first-time UI walk returning one record per gap | A runnable surface needs independent usability scrutiny | Read-only browser work |

`overseer` and `agentcraft-overseer` are user-invocable; the rest are private to orchestration unless their frontmatter says
otherwise. Modules add agents beyond this table — `hyperframes-motion` adds
`hyperframes-motion-smith`.

## Coordination

- Follow [assignment sizing](overseer.agent.md#assignment-size-and-cadence) and the [return contract](orchestrator.agent.md#return-evidence). Evidence from each return determines the next assignment; no automatic follow-on work.
- Dependency direction is `overseer -> orchestrator -> specialists`. Orchestrators never spawn
  orchestrators; specialists never report sideways.
- `agentcraft-overseer` uses the same team direction, with direct `note_scribe` dispatch solely for
  the project notebook. Its [process skill](../skills/agentcraft-process/SKILL.md) owns paths and constitution validation.
- Direct `archivist` dispatch owns authoritative record publication; all workers supply their observable
  actions/evidence through the overseer. Notebook lessons link records, not a second factual ledger.
- A constitution-named test subject may be dispatched directly as the candidate under evaluation;
  this is not another implementation team. It does not own its evaluator or authoritative run records.
- One writer per path, contract, deployment target, and cloud resource at a time.
- Subagent calls are synchronous to the parent. Peer chats, worktree sessions, and cloud-agent
  tasks are the asynchronous planes; join them before any claim depends on their result.

| Plane | Use |
| --- | --- |
| Synchronous subagent | Bounded research, review, feasibility, or design this turn needs |
| Same-session peer chat | Independent tracks needing the current dirty tree, with disjoint writable paths |
| Worktree session | Mutating tracks that may overlap or need independent rollback |
| Cloud-agent task | Clean, bounded branch or PR work from committed Git state |

Session-management tools are host-provided; never guess their identifiers into frontmatter.
