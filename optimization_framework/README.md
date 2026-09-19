# Optimization Framework

Local persisted optimization reference loop, not a general-purpose coding campaign runner.
CLI, loopback HTTP API and dashboard call the same service. Start with the
[operator runbook](deploy/README.md) or [primary skill](skills/optimization-experiment/SKILL.md).

**partial: local process working; full acceptance blocked/incomplete**.
[Consolidated implementation report](reports/IMPLEMENTATION_REPORT.md),
[standalone HTML](reports/implementation-report.html) and
[derived summary](reports/implementation-summary.json) separate observed local results,
retained failures and full-spec gaps. [Dashboard](http://127.0.0.1:9020) is running from current
source. [Final verification](reports/final-verification.json): 157 framework tests, 11
Investigation adapter/prompt tests and two current-backend browser tests passed. These are
separate scopes, not a combined portfolio count. Specs live in [specs](specs/README.md).

## Current Support

| Surface | Implemented boundary |
| --- | --- |
| Deterministic execution | `agent-tool-availability` and `csv-export-transformation`; frozen source/config, passing baseline, deliberately failing candidate, bounded repair |
| Native execution | Same two tasks; Copilot authors configuration only, explicit model grant, deny-all tools, at most two attempts |
| Extension | Caller-owned typed TaskRegistry and strict experiment documents; third-domain offline registration tested without editing core |
| Evidence | Private local SQLite index, immutable hashed artifacts, retained failures, metrics, restart read-back |
| Collaboration | Attributed SME feedback, dispositions and links to verified candidates; no automatic task rewriting |
| Reports | JSON, CSV and self-contained HTML, without rerunning experiments |
| Restore | Re-evaluate and select a retained known-good synthetic snapshot; not application/cloud rollback |
| UI/API | Loopback-only service, fixed local operator, Host/Origin checks; not multi-user or nonlocal authentication |
| Skill packaging | VS Code workspace bundle; fresh exact overseer explicitly discovered and used installed runtime successfully after credential fix. Automatic discovery in a newly opened VS Code client remains unverified |

Both executors report `decision: inconclusive`. Accepted synthetic/config-only output is not
comparative improvement, independent held-out evaluation or measured architecture benefit.
Missing model telemetry remains null/unobserved, not zero.

## Local Sequence

Linux, Bash, Python 3.12+, Node.js/npm; pytest is required for tests. No virtual environment
or Python package install is required: entry point sets `PYTHONPATH` to its own `src`.
Run from the framework directory, or use the absolute script path from any directory:

```bash
./deploy/deploy.sh setup
./deploy/deploy.sh test
./deploy/deploy.sh verify --receipt /tmp/optimization-packaging-receipt.json
./deploy/deploy.sh local --port 8765 --root "$HOME/.local/state/agentcraft-optimization"
```

`local` stays in the foreground at `http://127.0.0.1:8765`; Ctrl-C stops it. No model permission
by default. Choose another port if occupied. `verify` starts no server and removes its isolated
temporary data. Receipt/report paths must be new; existing output is never overwritten.
Setup installs frontend dependencies without modifying its lockfile, then typechecks/builds.
This is a reproducible workflow, not a claim of hermetic or bit-identical dependency resolution.

One service process owns each storage root. While `local` runs, use HTTP/UI for that root;
another CLI command using it refuses `storage_root_in_use`. Stop the server before CLI work,
or give the CLI a separate root. Reports and feedback may contain sensitive operator input:
keep outside the repository and never submit credentials.

## Installation

```bash
./deploy/deploy.sh install-skill --client vscode --target /path/to/target-project
```

Creates `.github/skills/optimization-experiment/SKILL.md` in the target, with a `framework/`
bundle beneath it. Primary skill remains at `framework/skills/optimization-experiment/SKILL.md`;
its `../../specs` and `../../deploy` references resolve locally after installation. Runtime,
frontend sources/lockfile, core tests and packaging checks travel with it. No dependency install,
model call, cloud operation, credentials, reports, runtime state or Investigation app is copied.
Repeated identical installation verifies hashes; conflicting files refuse. Use a fresh target
for an updated bundle. Only VS Code workspace discovery is supported; other clients refuse.
The source repository's `.github` entry is a source-only pointer, not the portable export.

## Contracts And Gaps

- Actual commands, API fields, SME examples, recovery and failures: [runbook](deploy/README.md).
- Current CLI: [cli.py](src/optimization_framework/cli.py); service: [service.py](src/optimization_framework/service.py).
- HTTP schema: [API_CONTRACT.json](API_CONTRACT.json). Its start example uses deterministic;
  current runtime additionally accepts `copilot` only when the service was explicitly granted it.
- Normative target: [procedure](specs/PROCEDURE.md), [measurement](specs/MEASUREMENT.md),
  [authority/recovery](specs/RECOVERY_AND_AUTHORITY.md), [acceptance gates](specs/ACCEPTANCE.md).
  Specs remain design targets; status/evidence cells record partial acceptance. Proposed commands are not current CLI commands.

Pending: arbitrary code-edit executors, measured baseline change effort,
independent evaluator/held-out isolation, fair repeated comparisons,
automatic promotion, resumable computation, full integrated Investigation task acceptance,
held-out improvement and SME-led domain transfer. Supported fresh-overseer adoption passed;
its attributed SME input is not independent review. Narrow live prompt adherence and offline
native profile/UI acceptance passed, not the entire four-task campaign. `recover` is not implemented. Test coverage is not
completion of G1-G7; registered config-only tasks now support `preflight/run --experiment`.

Cloud deployment, nonlocal caller authentication, tenant/owner isolation at the HTTP edge,
deployed acceptance and exact application rollback are not implemented. Framework `cloud`/`teardown`
return blocked, not simulated success. Investigation has offline planning/preflight tooling;
isolated cloud scope is already authorized. Durable profile/agent filesystem semantics,
deployed authentication and live positive/negative proof remain blockers, not missing permission.