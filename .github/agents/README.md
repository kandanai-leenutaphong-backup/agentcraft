# Workspace agent roster

`overseer` runs a portfolio of independent outcomes. Each `orchestrator` owns one bounded feature.
Specialists own bounded work inside it and approve nothing.

Every specialist is optional: delegate when it removes real risk or real unknowns, implement
directly otherwise. Contract for all:
[`work-contract.instructions.md`](../instructions/work-contract.instructions.md).

## Available agents

| Agent | Role | Employ when | Mutation boundary |
| --- | --- | --- | --- |
| [`overseer`](overseer.agent.md) | Leads several feature teams and owns integration | The objective genuinely splits into independently demonstrable outcomes | Edits directly for small changes; assigns larger mutation to one team |
| [`orchestrator`](orchestrator.agent.md) | Leads one feature end-to-end | One bounded feature, aspect, or experience | Its own assigned paths, contracts, deployments, resources |
| [`architecture-cartographer`](architecture-cartographer.agent.md) | Maps ownership, placement, dependency direction, and final-app readiness | Placement is genuinely contested or topology changed | Read-only except `ARCHITECTURE_STATUS.md` under the docs root |
| [`solution-architect`](solution-architect.agent.md) | Produces a minimum implementation-ready design | The route to value is unclear enough that coding would thrash | Read-only |
| [`data-explorer`](data-explorer.agent.md) | Proves feasibility of unfamiliar authorized sources | Inventory, parsing, rights, or extraction feasibility is unknown | Read-only; never executes source bytes |
| [`developer`](developer.agent.md) | Implements backend, infrastructure, and general code slices | The slice, constraints, and safety signal are known | Assigned writable paths only |
| [`frontend-developer`](frontend-developer.agent.md) | Implements frontend slices with browser evidence | Work belongs to one named frontend surface | Assigned frontend paths only |
| [`documentation_curator`](documentation_curator.agent.md) | Reconciles README, CONTRACT, runbook, and architecture prose with verified source | Documentation reconciliation is worth handing off | Documentation paths only |
| [`experience-evaluator`](experience-evaluator.agent.md) | Measures pre-change impact or a deployed journey | User impact or runtime evidence needs assessment | Read-only browser work |
| [`ui-experience-auditor`](ui-experience-auditor.agent.md) | Cold first-time UI walk returning one record per gap | A runnable surface needs independent usability scrutiny | Read-only browser work |

`overseer` is user-invocable; the rest are private to orchestration unless their frontmatter says
otherwise. Modules add agents beyond this table — `hyperframes-motion` adds
`hyperframes-motion-smith`.

## Coordination

- Dependency direction is `overseer -> orchestrator -> specialists`. Orchestrators never spawn
  orchestrators; specialists never report sideways.
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
