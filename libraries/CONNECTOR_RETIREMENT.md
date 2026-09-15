# Connector Skill Retirement

Assessment: **neither original skill is wholly superseded by the libraries**.
Evidence checked 2026-09-15. This record covers only the two connector skills;
it does not authorize cloud operations or retirement of other capabilities.

Completed: migrated the reusable operational findings into library-owned
[data guidance](azure-data-connectors/OPERATIONS.md) (G1-G27) and
[LLM guidance](llm-interface/OPERATIONS.md) (G1-G18), with source revision,
current-contract corrections and regression owners. Both library READMEs link them.
Original skill runtimes, package metadata, tests and MCP registrations remain intact;
no deletion or runtime migration is claimed.

## Owners And Decisions

| Existing Outcome | Library Owner / Public Surface | Decision |
| --- | --- | --- |
| Bounded data CRUD and addressed read-back | [azdata v4](azure-data-connectors/CONTRACT.md), `connect`, typed requests and `OperationResult` | Reuse for new callers; translate v3 callers explicitly. Both packages export `azdata`, but their APIs are incompatible. |
| [Provisioning, drift checks and separately granted teardown](../.github/skills/azure-data-connectors/src/azdata/core/provision.py) | No equivalent infrastructure implementation in v4 | Defer removal. Search index schema operations do not replace infrastructure provisioning. |
| [Hierarchical discovery, content and estate browsing](../.github/skills/azure-data-connectors/src/azdata/estate/access.py) | No equivalent v4 contract; Resource Explorer retains its independently distributed v3 snapshot | Keep existing owner until its actual callers migrate. `describe()` is not resource discovery. |
| [Service observation](../.github/skills/azure-data-connectors/src/azdata/core/observe.py) and [full effect snapshots/diffs](../.github/skills/azure-data-connectors/src/azdata/core/verify.py) | v4 operation metrics and addressed-item verification only | Defer removal; these have different observable results and concurrency guarantees. |
| [Live environment lifecycle/seeding](../.github/skills/azure-data-connectors/src/azdata/live/environment.py) and [SQL principal management](../.github/skills/azure-data-connectors/src/azdata/sqldb/principals.py) | Root deployment currently manages a resource group only | Defer removal; preserve explicit target/grant/ownership checks. No live operation authorized here. |
| Policy-bound model calls, structured output, streaming and embeddings | [llm_interface](llm-interface/CONTRACT.md), `connect`, `chat`, `embeddings`, `agent` | Reuse for new integrations; fixed targets, explicit credentials and async framework results replace the old facade. |
| [Synchronous/raw Responses compatibility](../.github/skills/azure-llm-connectors/CONTRACT.md) | Not implemented by `llm_interface` | Not equivalent. Do not add a raw escape hatch to the bounded library merely to claim parity. |
| [Registered bounded model MCP tools](../.github/skills/azure-llm-connectors/scripts/mcp_server.py) | Original LLM skill's `azllm_status`, `azllm_ask`, `azllm_embed` | Migrate adapter and its refusal/budget tests before removing its registered launch path. |
| [Registered read-only data MCP tools](../.github/skills/azure-data-connectors/scripts/mcp_server.py) | Original data skill's v3 handlers | Migrate against v4 public requests before removing its registered launch path; preserve projection and refusal contracts. |
| Operational failure knowledge | Library-owned [data](azure-data-connectors/OPERATIONS.md) and [LLM](llm-interface/OPERATIONS.md) operations guides | Migrated 45 findings with provenance and explicit legacy/current applicability. Original package-specific documentation remains required while those packages are supported. |

## Load-Bearing Evidence

- [MCP registration](../.github/mcp.json) launches scripts inside both original
  skills. Removing either directory now breaks that registered server.
- [Data contract](azure-data-connectors/CONTRACT.md) explicitly disclaims v3 API
  compatibility and infrastructure provisioning. v4 Gremlin uses a supplied
  resource token, unlike the old Entra-oriented examples.
- [Data verification](azure-data-connectors/VERIFICATION.md) distinguishes current
  source checks, the template's ADX adoption and remaining live gaps.
- [LLM contract](llm-interface/CONTRACT.md) explicitly excludes MCP, a synchronous
  legacy shim and arbitrary raw Responses options. Its stricter target, retention,
  stream-completion and error boundaries must survive adapter migration.
- [Historical LLM comparison](llm-interface/tests/test_existing_contracts.py)
  imports both legacy packages only for comparison; it is not a library runtime
  dependency. Its skip is not proof of compatibility or retirement readiness.
- [Resource Explorer contract](../.github/skills/resource-explorer/CONTRACT.md)
  describes its separately bundled v3 dependency. This preserves that consumer,
  but does not establish that v4 implements discovery/content/estate.
- [Deployment scope](../deploy/README.md) is resource-group management, not a
  replacement for the data skill's whole live environment.

Root architecture overview and notebook tooling are absent. The existing
[portfolio design](DESIGN.md) records that limitation; this assessment is the
durable comparison, not a new runtime registry.

## Offline Baseline

Run from the repository root. These checks do not invoke Azure:

```bash
PYTHONDONTWRITEBYTECODE=1 libraries/.venv/bin/python -B -m unittest discover -s libraries/azure-data-connectors/tests -t libraries/azure-data-connectors -q
UV_PROJECT_ENVIRONMENT="$PWD/libraries/.venv-llm-interface" uv run --project libraries --locked --package llm-interface --extra foundry --no-default-groups python -B -m unittest discover -s libraries/llm-interface/tests -v
```

Observed: data `4.0.0a3`, **126 tests passed**; LLM `0.1.0a1`, **33 tests
reported, one historical-comparison skip, no failures**. These establish current
library behavior, not legacy parity, installed-plugin correctness or live access.

## Removal Gate

1. Assign every retained contract, example, test and operational finding an owner;
   distinguish migrated behavior from intentionally retired behavior.
2. Migrate registered MCP consumers without adding request-level grants, target
   overrides, retries or unverified successful writes.
3. Run actual SDK client/server round-trips: default denial, configured fixture
   success, malformed/override refusal, budget exhaustion and cleanup.
4. Reconcile source catalogue, discovery guidance, launch configuration, packaging,
   examples and affected caller imports. Historical receipts keep their provenance.
5. Remove original runtime only when its supported workflows have verified owners,
   or the operator explicitly chooses to retire the remaining functionality.

Unknown: out-of-repository installations and operator configurations. No cloud
authorization, live parity, publication or external-consumer compatibility is
implied by this assessment.