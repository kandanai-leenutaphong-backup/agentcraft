# Agentcraft Documentation

Type: overview. Goal: find and compose current public capabilities. Status: current
checkout, 2026-09-17; not production or live acceptance. Applies to library consumers.
Owner: repository documentation; linked libraries own their contracts and examples.

[Start](#start) | [Tasks](#tasks) | [Concepts](#concepts) |
[Reference](#reference) | [Troubleshooting](#troubleshooting)

## Start

One entry point, with contracts and executable examples kept at their library owners.
Use `agentcraft` for composition and discovery, native async `azdata` for data and
`llm_interface` for the single model/agent engine. Guidance is not a runtime or a grant.

1. Follow [workspace installation](../libraries/README.md#installation): Python 3.12+,
  uv 0.9.30, reviewed dependencies and a fresh caller-owned environment. Locks are
  refreshed; artifact identity and acceptance are recorded separately.
2. Run `agentcraft describe [capability]` from that environment. Description is offline
  and reports `readiness: unverified`; it does not acquire credentials or test a service.
3. Run the [composed offline workflow](#offline-data-rules-and-recovery), or select an
  owning guide below. Live endpoint, identity, data-processing and budget authority
  must be supplied separately; installing extras authorizes none of them.

## Tasks

- Compose data, ordered rules, a model call and completed-output recovery: [offline route below](#offline-data-rules-and-recovery).
- Chat, embed or inspect semantic tool/run events: [model caller guide](../libraries/llm-interface/USAGE.md).
- Assemble allowlisted routes/assets: [appcompose guide](../libraries/app-composition/GUIDE.md).
- Configure rosters, typed tools and bundles: [modular APIs](../libraries/modular-agents/README.md#public-apis).
- Diagnose repository structure or retain findings: [inspection](../libraries/repository-inspection/README.md) and [notebook guide](../libraries/investigation-notebook/GUIDE.md).
- Extract authorized PDF layout through the official SDK: [Content Understanding recipe](../libraries/content-understanding/README.md).
- Find task guidance or explicitly enable MCP: [discovery and MCP](../libraries/README.md#discovery-and-mcp).
- Exercise Investigation with signed, synthetic native services: local runbook (outside-guidance-not-advertised; source reference: `../template_apps/investigation_app/deploy/README.md#offline-native-browser`).

### Offline Data, Rules And Recovery

Follow the [framework workflow](../libraries/framework/README.md#offline-workflow)
for setup, the public `offline_workflow` callable/module command, expected results,
refusal recovery and cleanup. Native SDK parsing uses **synthetic** service responses;
temporary filesystem writes are real. The guide owns executable instructions and proof.
For a real uncertain save, use the [recovery guide](../libraries/recoverable-jobs/GUIDE.md):
retain completed output and read back the existing run id before recommitting.

## Concepts

- **One composition, specialized operations.** `Framework` uses `appcompose` for graph
  validation and lifecycle. `data(name)`, `model(name)`, and `get(name, expected)` return
  typed bindings; they do not create a universal query or model protocol.
  `llm_interface` uses native Agent Framework for model/tool execution. Its semantic
  `RunEvent` has `kind`, `run_id`, `sequence`; browser SSE framing is a separate transport
  concern, not another agent loop or proof of successful completion.
- **Trust is not policy or credentials.** `CallerContext` carries principal and tenant
  context, not authenticated proof. The host verifies evidence and authorizes operations;
  workload credentials authenticate service access. Constructing a context grants nothing.
  `azdata.Policy` defaults to read/query grants, while model inference defaults denied.
  Requests cannot select new endpoints, credentials or broader grants. Signed agent and
  human identities remain distinct inputs to the host's common authorization decision.
- **Bounds are explicit.** `ExecutionContext` carries a monotonic deadline, run id and
  process-local `ExecutionBudget`. Child limits/deadlines cannot widen parents. Reservations
  charge the ancestor chain; unknown delivery is not a refund. A context does not add
  automatic retries or enforce every native operation's policy. Reservation participation
  is explicit, not an automatic whole-stack quota or portfolio-wide conformance guarantee.
- **Unknown is not empty or failed.** `describe()` reports configured bindings with
  `readiness: unverified`, not connectivity. `FailureInfo.effect` distinguishes `none`,
  `accepted`, `unknown`; `retry` distinguishes correction from required read-back. Native
  capability results retain their own meanings; no universal result wrapper is implied.
  Recovery distinguishes `saved`, `absent`, `conflict`, `unknown`; it preserves completed
  output and never resumes computation. Streaming text or SSE EOF is not model completion.
- **Lifetimes have owners.** Bindings are borrowed by default. `owned=True` requires a
  close method; async exit attempts owned close hooks, dependents before dependencies,
  with repeated handles closed once. A cleanup exception is not proof of release.
  New access after close refuses. Credentials and durable outputs retain their owning
  library's separate cleanup rules; closing a connector does not roll back remote effects.

## Reference

All 23 catalogue entries (outside-guidance-not-advertised; source reference: `../libraries/capabilities.json`): 20 distribution-owning
capabilities, one native SDK recipe and two retirement notices. Public-API tests and
consumers serve as examples; their owning guides state prerequisites and evidence class.
Retired entries have replacements, not executable examples. The catalogue owns metadata;
this table only routes to current references.

| Capability | Current reference | Public example |
| --- | --- | --- |
| Framework composition | Public exports (source-or-asset-not-bundled; source reference: `../libraries/framework/src/agentcraft/__init__.py`) | [Binding and async lifetime](../libraries/framework/README.md) |
| Caller, execution and failure context | Core public API (source-or-asset-not-bundled; source reference: `../libraries/framework-core/src/agentcraft_core/__init__.py`) | [Reservation example](../libraries/framework-core/README.md) |
| Configuration, routes and lifecycle: `appcompose` | [Contract](../libraries/app-composition/CONTRACT.md) | Two capabilities (source-or-asset-not-bundled; source reference: `../libraries/app-composition/examples/compose_two_capabilities.py`) |
| Async data: `azdata` | [Typed operations and profile matrix](../libraries/azure-data-connectors/CONTRACT.md) | Offline Kusto query/refusal (source-or-asset-not-bundled; source reference: `../libraries/azure-data-connectors/tests/adapters/test_kusto.py`) |
| Models, embeddings, sessions, tool events: `llm_interface` | [Contract](../libraries/llm-interface/CONTRACT.md) | Synthetic HTTP example (source-or-asset-not-bundled; source reference: `../libraries/llm-interface/examples/offline.py`) |
| Native PDF layout recipe: official Content Understanding SDK | [Recipe contract](../libraries/content-understanding/CONTRACT.md) | [Authorized extraction setup](../libraries/content-understanding/README.md#local-operator) |
| Rules: `situation_detector` | Public exports (source-or-asset-not-bundled; source reference: `../libraries/situation-detector/src/situation_detector/__init__.py`), [rule contract](../libraries/situation-detector/src/situation_detector/README.md) | Synthetic public battery tests (source-or-asset-not-bundled; source reference: `../libraries/situation-detector/tests/test_situation_detector.py`) |
| Completed-output recovery: `workrecovery` | [Contract](../libraries/recoverable-jobs/CONTRACT.md) | Commit then timeout (source-or-asset-not-bundled; source reference: `../libraries/recoverable-jobs/examples/02_commit_then_timeout.py`) |
| Human identity: `entra_auth` | [Contract](../libraries/entra-auth/src/entra_auth/README.md) | Token validation fixtures (source-or-asset-not-bundled; source reference: `../libraries/entra-auth/tests/test_entra_auth.py`) |
| Signed agent requests: `signed_dev_access` | [Client and server guide](../libraries/signed-dev-access/docs/skills/signed-dev-access.md) | [No-send CLI example](../libraries/signed-dev-access/docs/skills/signed-dev-access.md#cli) |
| Inventory: `resource_explorer`, `@agentcraft/resource-explorer` | [Package guide](../libraries/resource-explorer/README.md), [contract](../libraries/resource-explorer/src/resource_explorer/README.md) | Registry/probe fixtures (source-or-asset-not-bundled; source reference: `../libraries/resource-explorer/tests/test_resource_explorer.py`) |
| Roster, tools and hosted bundles: `agentconfig`, `toolshape`, `hostedagents`; `@agentcraft/modular-agents` renderers | [Modular contract](../libraries/modular-agents/CONTRACT.md) | Offline bundle/tool example (source-or-asset-not-bundled; source reference: `../libraries/modular-agents/examples/offline.py`), [npm surface](../libraries/modular-agents/README.md#public-apis) |
| Local evaluation, optimization and replay: `agent_optimization`, `@agentcraft/agent-optimization` | [Contract](../libraries/agent-optimization/CONTRACT.md) | Synthetic experiment (source-or-asset-not-bundled; source reference: `../libraries/agent-optimization/examples/offline.py`), replay UI (source-or-asset-not-bundled; source reference: `../libraries/agent-optimization/examples/replay/main.tsx`) |
| Architecture, catalogue and filesystem: `repository_inspection` | [Public modules and bounds](../libraries/repository-inspection/README.md) | Synthetic repository (source-or-asset-not-bundled; source reference: `../libraries/repository-inspection/examples/inspect_repository.py`) |
| Durable knowledge: `investigation_notebook` | [Public API and index side effects](../libraries/investigation-notebook/README.md) | [Temporary notebook example](../libraries/investigation-notebook/README.md#install-and-use) |
| Public web acquisition: `webres` | [Contract](../libraries/web-resource/CONTRACT.md) | Offline provenance round-trip (source-or-asset-not-bundled; source reference: `../libraries/web-resource/examples/catalogue_roundtrip.py`) |
| Terminal: `copilot_terminal`, `copilot-terminal` | [Contract](../libraries/copilot-terminal/CONTRACT.md) | [Explicit PTY fixture setup](../libraries/copilot-terminal/README.md#standalone-example) |
| Source viewing: `@agentcraft/source-code` | [Package guide](../libraries/source-code/README.md) | Public replay consumer (source-or-asset-not-bundled; source reference: `../libraries/agent-optimization/frontend/RunReplay.tsx`) |
| Named SSE frames: `@agentcraft/event-stream` | [Framing contract](../libraries/event-stream/README.md), [host-owned bounds](../libraries/event-stream/docs/skills/event-stream.md) | Public stream consumer (outside-guidance-not-advertised; source reference: `../template_apps/investigation_app/app/cybereye/frontend/src/shared/api/api.ts`) |
| Styling: `@harness/azure-sky-styling` | [Scoped CSS/React contract](../libraries/azure-sky-styling/README.md#contract-and-reuse) | [Synthetic gallery setup](../libraries/azure-sky-styling/README.md#run) |
| Rendering: `@agentcraft/hyperframes-tools` | [Contract](../libraries/hyperframes-tools/CONTRACT.md) | Offline beat sampling (source-or-asset-not-bundled; source reference: `../libraries/hyperframes-tools/examples/validate.mjs`), native composition (source-or-asset-not-bundled; source reference: `../libraries/hyperframes-tools/examples/pulse/index.html`) |
| Retired raw Responses compatibility: `azure-llm-compat` | Retirement notice (outside-guidance-not-advertised; source reference: `../libraries/azure-llm-compat/README.md`) | Replacement: native model example (source-or-asset-not-bundled; source reference: `../libraries/llm-interface/examples/offline.py`) |
| Retired synchronous Search facade: `search-read-adapter` | Retirement notice (outside-guidance-not-advertised; source reference: `../libraries/search-read-adapter/README.md`) | Replacement: [async data guide](../libraries/azure-data-connectors/README.md) |

## Troubleshooting

| Symptom | Check and safe next action |
| --- | --- |
| Locked workspace setup cannot resolve the framework | The refreshed workspace includes framework/core. Check Python 3.12+, uv 0.9.30 and the selected extras; report an actual metadata/lock mismatch to its owner without dropping `--locked`. |
| Install command rejects an extra or interpreter | Compare the selected distribution and Python version with metadata (source-or-asset-not-bundled; source reference: `../libraries/framework/pyproject.toml`); folder names are not distribution names. Use a caller-owned isolated environment. |
| `framework_not_active` or `framework_closed` | Access handles inside `async with Framework(...)`; a closed framework is not reusable. |
| `binding_type_or_name_mismatch` | Match the binding id and actual public type. A capability label is not proof of that type. |
| `budget_exhausted` or `deadline_cannot_widen` | Inspect limits and remaining time; correct the caller's authorized budget instead of widening a child or blindly retrying. |
| Configuration exists but service readiness is unknown | Run only the capability's explicitly authorized readiness/read operation. `describe()` is not a connectivity check. |
| Interrupted stream or unknown save status | Inspect the semantic terminal result or read back the existing run id. Do not restart inference/computation blindly; preserve recoverable output. |
| Owned shutdown raises | Inspect the owning resource's failure; a repeated framework close is not proof that release succeeded. Resolve retained resources before creating another composition. |
| Old imports or copy-from-skill instructions | Use current imports in [Reference](#reference) and package metadata. Preserved application snippets and renderer copy instructions are historical, not the supported install path. |
| Framework CLI or composed example unavailable | Check which environment supplied `agentcraft` and Python; use the selected profile and compare artifact identity with the release receipt. Old installed artifacts need not contain current source. |
| Catalogue lookup or MCP setup refuses | Select `tooling` for guidance lookup or explicitly select `mcp` and `--offline` for the CLI host. Missing registration is not a grant; live bindings, principal and context remain host-owned. |

## Design And Changes

The core objective (outside-guidance-not-advertised; source reference: `../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/0_CORE_OBJECTIVE.md`)
and documentation chapter (outside-guidance-not-advertised; source reference: `../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/05_DOCUMENTATION_AND_DEVELOPER_EXPERIENCE.md`)
are acceptance requirements, not execution evidence. Historical source plans and locally
retained specs may be absent from a distribution. The
execution ledger (outside-guidance-not-advertised; source reference: `../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/EXECUTION.md`) owns dated
migration evidence; [conformance](../libraries/framework/CONFORMANCE.md) and the
release receipt (source-or-asset-not-bundled; source reference: `../libraries/framework/distribution/release-candidate.json`) distinguish
source, artifact and required live acceptance. Retired imports are not alternatives.

[Agent optimization](../libraries/agent-optimization/README.md) implements local
frozen-cohort evaluation, immutable generations, evidence and persisted replay.
Its [evaluation research](../libraries/agent-optimization/EVALUATIONS.md),
[optimization research](../libraries/agent-optimization/OPTIMIZATION.md) and
[observability research](../libraries/agent-optimization/OBSERVABILITY.md) are reference
material, not measured model quality or implemented cloud observability.

The independent-reader receipt (source-or-asset-not-bundled; source reference: `../libraries/framework/distribution/independent-reader.json`)
records setup, repeated results, failure recovery and cleanup for three offline tasks,
with navigation depths of two or three links. It describes the recorded guide/artifact
bytes, not a fresh reader run against this revision. Current link inspection is separate
from execution; no comparative effort, model quality or production-readiness gain is claimed.