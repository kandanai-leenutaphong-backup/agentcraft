# Workspace agent roster

`overseer` runs a portfolio of independent outcomes. Each `orchestrator` owns one verifiable
increment end-to-end and returns evidence before taking another assignment. Specialists own
bounded work inside that increment and approve nothing.

Every specialist is optional: delegate when it removes real risk or real unknowns, implement
directly otherwise. Contract for all:
[`work-contract.instructions.md`](../instructions/work-contract.instructions.md).

## Available agents

Conciseness is mandatory for all agents, including support agents `archivist` and `note_scribe`.
Each definition carries `Conciseness (Required)`: fewer words, never less required information.
This is a behavioral requirement, not code-enforced language-model compliance.

| Agent | Role | Employ when | Mutation boundary |
| --- | --- | --- | --- |
| [`overseer`](overseer.agent.md) | Commissions small outcome teams and owns integration | The objective splits into independently verifiable increments | Edits directly for trivial changes; assigns team work with disjoint ownership |
| [`agentcraft-overseer`](agentcraft-overseer.agent.md) | Owns mission alignment, strategic priorities, authorization/criteria changes and evidence review | Whole-application AgentCraft development | Direct children exactly agentcraft-orchestrator, archivist, note_scribe, agentcraft-oracle (advisory only) |
| [`agentcraft-orchestrator`](agentcraft-orchestrator.agent.md) | Executes assigned AgentCraft stages/iterations and pilots candidates/specialists | Constitution-pinned exploration, implementation and measured iteration | Assigned paths/resources; no recursive orchestration or record/lesson publication |
| [`agentcraft-oracle`](agentcraft-oracle.agent.md) | Mock oracle; three bounded cryptic candidates, two randomly selected lines | Optional planning/critique consultation by AgentCraft overseer or orchestrator | One local selector invocation; no research, other file access, network or delegation; advice grants no authority |
| [`local-dev-test-subject`](local-dev-test-subject.agent.md) | Local cyber-agent candidate piloted by agentcraft-orchestrator | Authorized data understanding and later frozen cyber evaluation | Read/query assigned telemetry; approved scripts may write assigned derived evidence; no evaluator edits |
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

## AgentCraft v1.62 Delivery

Persistent practices from the timed deployment, not a proven causal speedup:

- Overseer assigns one end-to-end owner per coupled outcome with compact scope, authority, prerequisites,
  evidence pins, acceptance/refusals and return condition; independent outcomes may run in parallel.
- Orchestrator reuses verified facts, checks cheap prerequisites first and completes in-scope repairs.
  Mutable state and source drift require rechecks; extra handoffs and reassurance checks do not.
- User deadlines include the full process, including handoff, archival and notes. Check remaining time,
  reserve closure, report risk and retain failures; never weaken safety or relabel late closure as success.
- Archivist preserves selected bytes and linked primary receipts; note_scribe records concise lessons.
  Neither rebuilds unrelated history. Evidence, recovery and authorization obligations remain intact.
- Report verified usable results promptly with pending closure explicit. Source versions, applied behavior
  and measured improvement remain separate; no hot-reload or general speedup claim follows from these rules.

## Coordination

- Follow [assignment sizing](overseer.agent.md#assignment-size-and-cadence) and the [return contract](orchestrator.agent.md#return-evidence). Evidence from each return determines the next assignment; no automatic follow-on work.
- Dependency direction is `overseer -> orchestrator -> specialists`. Orchestrators never spawn
  orchestrators; specialists never report sideways.
- AgentCraft direction is `agentcraft-overseer -> agentcraft-orchestrator -> candidates/specialists`.
  Overseer direct children are exactly `agentcraft-orchestrator`, `archivist`, `note_scribe`, `agentcraft-oracle`. Direct
  specialists/candidates, including `local-dev-test-subject`, are prohibited; no direct-test-subject exception.
  The [process skill](../skills/agentcraft-process/SKILL.md) owns the loop, paths and constitution validation.
- Both AgentCraft callers may consult the oracle once per consultation, optionally, never recursively.
  This advisory-only exception supersedes the process's three-child rule, not its execution authority.
  Callers interpret, test or reject advice. Oracle requests `GPT-6 Astra` with `low` effort, without fallback;
  native model/effort availability, latency and cost remain unverified. Tool restrictions are not a sandbox.
- Only overseer dispatches `archivist` for authoritative records and `note_scribe` for lessons. Workers save
  primary evidence; orchestrators hand it to overseer, returning checkpoint requests when receipts are needed.
  No recursive orchestration, support-role dispatch by orchestrators, or waiting for undispatched peers.
  Candidates never own evaluators or authoritative records. Notebook lessons link the archive, not a second ledger.
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
