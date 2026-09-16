# Agentcraft Knowledge

Type: overview. Goal: find and compose current public capabilities. Status: current
checkout, 2026-09-16; not production or live acceptance. Applies to library consumers.
Owner: repository documentation; linked libraries own their contracts and examples.

[Start](#start) | [Tasks](#tasks) | [Concepts](#concepts) |
[Reference](#reference) | [Troubleshooting](#troubleshooting)

## Start

Use the [framework](../libraries/framework/README.md) to bind capabilities; keep their
specialized typed APIs. Canonical data access is async `azdata`; canonical model access
is `llm_interface`. Installing a package supplies neither credentials nor permission.

Prerequisites: Python 3.12+ for `agentcraft`, uv 0.9.30 for this workspace, and reviewed
dependencies. **Setup gap:** the current [workspace lock](../libraries/uv.lock) has no
`agentcraft` or `agentcraft-core` entries. Parent-owned lock refresh must precede this
metadata-verified command; do not remove `--locked` to conceal the mismatch. After that
refresh, run from the repository root in a caller-owned development environment:

```bash
uv run --project libraries --package agentcraft --extra recovery --locked --no-default-groups python -B -c 'from agentcraft import Framework; print(Framework({}).describe())'
```

The Python body was verified directly against current source; the full uv command was
not run. It inspects an empty composition without acquiring credentials or calling a service.
Expect `framework: agentcraft`, no configured bindings, and `readiness: unverified`.
There is no resource to close. Dependency installation may need a configured package
source; the Python operation itself is offline. Do not reuse another worker's environment.

[Workspace metadata](../libraries/pyproject.toml) pins uv;
[framework metadata](../libraries/framework/pyproject.toml) defines Python support and
extras: `data`, `models`, `identity`, `inventory`, `agents`, `optimization`, `recovery`,
`tooling`, `mcp`. Extras select dependencies, not grants or automatic connections.
`data` selects Kusto/Search/Gremlin/identity, not all ten `azdata` profiles; `models`
selects `llm-interface[openai]`, not `[foundry]`. Provider-specific extras remain in
the [data metadata](../libraries/azure-data-connectors/pyproject.toml) and
[model metadata](../libraries/llm-interface/pyproject.toml). No `rules` extra exists;
`situation-detector` is a workspace member and an `optimization` dependency.

Outside the checkout, install reviewed `agentcraft==0.1.0` wheels and the complete
dependency wheel set into a fresh environment. Use an explicitly supplied local wheel
directory with `--no-index --find-links`; workspace source overrides are not published
dependencies. Public registry availability and external combined-profile acceptance
are not established by this page.

With `CONSUMER_ENV` naming a fresh Python 3.12+ environment and `WHEELHOUSE` an absolute
directory containing the reviewed wheels, the external install command is:

```bash
uv pip install --python "$CONSUMER_ENV/bin/python" --no-index --find-links "$WHEELHOUSE" 'agentcraft[recovery]==0.1.0'
```

No registry fallback is permitted by that command. Missing dependency wheels are a
missing release input, not a reason to install retired packages. Installation was not
run for this documentation check. npm packages below have separate metadata and builds.

## Tasks

- Compose data, rules and completed-output recovery: [offline route below](#offline-data-rules-and-recovery).
- Chat, embed or inspect semantic tool/run events: [model caller guide](../libraries/llm-interface/USAGE.md).
- Assemble allowlisted routes/assets: [appcompose guide](../libraries/app-composition/GUIDE.md).
- Configure rosters, typed tools and bundles: [modular APIs](../libraries/modular-agents/README.md#public-apis).
- Diagnose repository structure or retain findings: [inspection](../libraries/repository-inspection/README.md) and [notebook guide](../libraries/investigation-notebook/GUIDE.md).

### Offline Data, Rules And Recovery

How-to goal: follow the existing public pieces of a query -> rule result -> verified
save. **Current fallback: these examples run separately, not as one composed pipeline.**
No combined framework script exists in the inspected source; end-to-end output handoff
is pending. This route neither fabricates that script nor claims a composed pass.

1. Bind handles using the [framework example](../libraries/framework/README.md); inspect
  `describe()` before opening, and access them inside its async context. Bind data,
  callbacks and store at the host; request values cannot name code or choose credentials.
2. Inspect the [offline Kusto fixture](../libraries/azure-data-connectors/tests/adapters/test_kusto.py).
  It awaits public `query(QueryRequest(...))`: the synthetic row contains `value == 2`;
  an invalid credential produces `denied` with no transport request. Host callbacks
  must reject partial/failed query results before evaluating rules.
3. Follow the [rule battery fixture](../libraries/situation-detector/tests/test_situation_detector.py).
  `run_battery_async` receives explicit configuration, window, execute and process
  callbacks. The independent fixture returns three ordered rules and a configuration
  digest; `RuleExecutionError` is not an empty successful detection.
4. Pass only completed output to `RecoverableJobs.commit(run_id, payload)` with an
  operator-owned root and store. [Timeout read-back](../libraries/recoverable-jobs/examples/02_commit_then_timeout.py)
  distinguishes `saved` from `absent`; [unreadable destination](../libraries/recoverable-jobs/examples/03_absent_unknown.py)
  remains `unknown`. [Restart/recommit](../libraries/recoverable-jobs/examples/04_restart_and_recommit.py)
  reads the preserved payload without repeating computation and leaves unrelated runs intact.

Recovery examples use temporary directories and clean up their own fixtures; they are
not no-I/O examples and were not executed for this documentation change. Never apply
their fixture cleanup to a real recovery root. Keep unresolved artifacts until verified
read-back; consult the [recovery guide](../libraries/recoverable-jobs/GUIDE.md) for recovery
and the [contract](../libraries/recoverable-jobs/CONTRACT.md) for conditional writes and caps.

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

Direct routes to existing owners, not another package catalogue. Example links include
public-API tests and real consumers; filesystem, browser and live examples retain their
own prerequisites. Preserved guides may contain historical app import labels: use the
current package imports below, never old skill runtime paths.

| Capability | Current reference | Public example |
| --- | --- | --- |
| Framework composition | [Public exports](../libraries/framework/src/agentcraft/__init__.py) | [Binding and async lifetime](../libraries/framework/README.md) |
| Caller, execution and failure context | [Core public API](../libraries/framework-core/src/agentcraft_core/__init__.py) | [Reservation example](../libraries/framework-core/README.md) |
| Configuration, routes and lifecycle: `appcompose` | [Contract](../libraries/app-composition/CONTRACT.md) | [Two capabilities](../libraries/app-composition/examples/compose_two_capabilities.py) |
| Async data: `azdata` | [Typed operations and profile matrix](../libraries/azure-data-connectors/CONTRACT.md) | [Offline Kusto query/refusal](../libraries/azure-data-connectors/tests/adapters/test_kusto.py) |
| Synchronous ADX operators: `azdata.event_store` | [Distinct operator contract](../libraries/azure-data-connectors/docs/event-store/CONTRACT.md) | [Host-configured SDK query](../libraries/azure-data-connectors/docs/event-store/README.md#install-and-read) |
| Models, embeddings, sessions, tool events: `llm_interface` | [Contract](../libraries/llm-interface/CONTRACT.md) | [Synthetic HTTP example](../libraries/llm-interface/examples/offline.py) |
| Rules: `situation_detector` | [Public exports](../libraries/situation-detector/src/situation_detector/__init__.py), [rule contract](../libraries/situation-detector/src/situation_detector/README.md) | [Synthetic public battery tests](../libraries/situation-detector/tests/test_situation_detector.py) |
| Completed-output recovery: `workrecovery` | [Contract](../libraries/recoverable-jobs/CONTRACT.md) | [Commit then timeout](../libraries/recoverable-jobs/examples/02_commit_then_timeout.py) |
| Human identity: `entra_auth` | [Contract](../libraries/entra-auth/src/entra_auth/README.md) | [Token validation fixtures](../libraries/entra-auth/tests/test_entra_auth.py) |
| Signed agent requests: `signed_dev_access` | [Client and server guide](../libraries/signed-dev-access/docs/skills/signed-dev-access.md) | [No-send CLI example](../libraries/signed-dev-access/docs/skills/signed-dev-access.md#cli) |
| Inventory: `resource_explorer`, `@agentcraft/resource-explorer` | [Package guide](../libraries/resource-explorer/README.md), [contract](../libraries/resource-explorer/src/resource_explorer/README.md) | [Registry/probe fixtures](../libraries/resource-explorer/tests/test_resource_explorer.py) |
| Roster, tools and hosted bundles: `agentconfig`, `toolshape`, `hostedagents`; `@agentcraft/modular-agents` renderers | [Modular contract](../libraries/modular-agents/CONTRACT.md) | [Offline bundle/tool example](../libraries/modular-agents/examples/offline.py), [npm surface](../libraries/modular-agents/README.md#public-apis) |
| Evaluation and replay: `agent_optimization`, `@agentcraft/agent-optimization` | [Contract](../libraries/agent-optimization/CONTRACT.md) | [Synthetic experiment](../libraries/agent-optimization/examples/offline.py), [replay UI](../libraries/agent-optimization/examples/replay/main.tsx) |
| Architecture, catalogue and filesystem: `repository_inspection` | [Public modules and bounds](../libraries/repository-inspection/README.md) | [Synthetic repository](../libraries/repository-inspection/examples/inspect_repository.py) |
| Durable knowledge: `investigation_notebook` | [Public API and index side effects](../libraries/investigation-notebook/README.md) | [Temporary notebook example](../libraries/investigation-notebook/README.md#install-and-use) |
| Public web acquisition: `webres` | [Contract](../libraries/web-resource/CONTRACT.md) | [Offline provenance round-trip](../libraries/web-resource/examples/catalogue_roundtrip.py) |
| Terminal: `copilot_terminal`, `copilot-terminal` | [Contract](../libraries/copilot-terminal/CONTRACT.md) | [Explicit PTY fixture setup](../libraries/copilot-terminal/README.md#standalone-example) |
| Source viewing: `@agentcraft/source-code` | [Package guide](../libraries/source-code/README.md) | [Public replay consumer](../libraries/agent-optimization/frontend/RunReplay.tsx) |
| Named SSE frames: `@agentcraft/event-stream` | [Framing contract](../libraries/event-stream/README.md), [host-owned bounds](../libraries/event-stream/docs/skills/event-stream.md) | [Public stream consumer](../template_apps/investigation_app/app/cybereye/frontend/src/shared/api/api.ts) |
| Styling: `@harness/azure-sky-styling` | [Scoped CSS/React contract](../libraries/azure-sky-styling/README.md#contract-and-reuse) | [Synthetic gallery setup](../libraries/azure-sky-styling/README.md#run) |
| Rendering: `@agentcraft/hyperframes-tools` | [Contract](../libraries/hyperframes-tools/CONTRACT.md) | [Offline beat sampling](../libraries/hyperframes-tools/examples/validate.mjs), [native composition](../libraries/hyperframes-tools/examples/pulse/index.html) |

## Troubleshooting

| Symptom | Check and safe next action |
| --- | --- |
| Locked workspace setup cannot resolve the framework | Current lock lacks `agentcraft` and `agentcraft-core`; its owner must enroll/resolve them and verify the selected extras. Python source checks do not prove installation. |
| Install command rejects an extra or interpreter | Compare the selected distribution and Python version with [metadata](../libraries/framework/pyproject.toml); folder names are not distribution names. Do not edit a shared environment to resolve another worker's dependencies. |
| `framework_not_active` or `framework_closed` | Access handles inside `async with Framework(...)`; a closed framework is not reusable. |
| `binding_type_or_name_mismatch` | Match the binding id and actual public type. A capability label is not proof of that type. |
| `budget_exhausted` or `deadline_cannot_widen` | Inspect limits and remaining time; correct the caller's authorized budget instead of widening a child or blindly retrying. |
| Configuration exists but service readiness is unknown | Run only the capability's explicitly authorized readiness/read operation. `describe()` is not a connectivity check. |
| Interrupted stream or unknown save status | Inspect the semantic terminal result or read back the existing run id. Do not restart inference/computation blindly; preserve recoverable output. |
| Owned shutdown raises | Inspect the owning resource's failure; a repeated framework close is not proof that release succeeded. Resolve retained resources before creating another composition. |
| Old imports or copy-from-skill instructions | Use current imports in [Reference](#reference) and package metadata. Preserved application snippets and renderer copy instructions are historical, not the supported install path. |
| Framework CLI or composed example unavailable | Metadata declares `agentcraft.cli:main`, but that module and a combined data/rule/recovery example are absent in inspected source. Use the verified Python surface and separate examples; an extra alone does not establish a unified MCP host. |

## Design And Changes

The [core objective](../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/0_CORE_OBJECTIVE.md)
and [documentation chapter](../specs/20260916T045818Z_UNIFIED_LIBRARY_SPEC/05_DOCUMENTATION_AND_DEVELOPER_EXPERIENCE.md)
are design/acceptance requirements, not execution evidence. These locally retained specs
may be absent from a distributed checkout. Current source and package metadata take
precedence over older package lists. Retirement, consumer adoption, wheel installation,
live authorization and production readiness are separate claims.

[Raw model compatibility](../libraries/azure-llm-compat/README.md) and the
[synchronous Search adapter](../libraries/search-read-adapter/README.md) are retired,
not optional providers. Use `llm_interface` and awaited `azdata` operations respectively.
The [B02/B03 record](../libraries/azure-data-connectors/MIGRATION_B02_B03.md) and
[model validation](../libraries/llm-interface/VALIDATION.md) record their dated library,
artifact and host checks with explicit blockers; neither certifies this whole checkout.

Verification for this page: local file/anchor links and metadata-backed command syntax;
the Python quickstart plus existing framework/core snippets compiled and run against
current source in an isolated Python 3.12 interpreter with network and file writes blocked.
Direct reference/example routes are one click from this entry; independent reader usability
is unmeasured. Locked workspace setup is pending missing framework/core lock entries.
Other linked examples, wheel installation, unified MCP/CLI, live identity,
production behavior and full migration acceptance were not verified by this docs change.