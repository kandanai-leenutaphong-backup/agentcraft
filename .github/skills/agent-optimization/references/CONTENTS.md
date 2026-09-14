# Contents Map

Paths below are relative to the extraction directory. The complete per-file inventory lives in
the pack manifest. The payload holds only this skill's own first-party sources plus a synthetic
example ledger. No host application, customer configuration, dataset or third-party component
is included.

Two roots: `runtime/` and `example/`.

## Reusable Runtime

| Path under `runtime/` | Owns |
| --- | --- |
| `agent_optimization/README.md` | Public service, profile, terminal and dataset contracts |
| `agent_optimization/PROCESS.md` | Question -> data -> evidence view -> tool -> interpretation -> measured feedback |
| `agent_optimization/LESSONS.md` | Exact-parent controls, probe semantics, recovery, repeated attempts and honest gains/regressions |
| `agent_optimization/skills/creative-agent-optimization/SKILL.md` | Creative design skill installed into native CLI workspaces |
| `agent_optimization/process.py` | Creative coverage, question-plan validation and CLI task contract |
| `agent_optimization/service.py` | Experiments, owner isolation, publication, full-stage lifecycle and finish gates |
| `agent_optimization/joint.py`, `workflow.py` | Window-bounded detector configurations, probe execution and knowledge arguments |
| `agent_optimization/evaluation.py`, `runs.py` | Scoring, audits, stage metadata, error retention and exemplar persistence |
| `agent_optimization/python_tools.py`, `python_worker.py` | Generated Python validation, Bubblewrap process boundary and syscall/resource limits |
| `agent_optimization/cli.py` | Bounded native CLI lifecycle, skill injection and exact parent-configuration feedback |
| `agent_optimization/_local_query/` | Private read-only, bounded SQLite reader |
| `agent_optimization/scripts/` | Helper installation and complete-ledger verification |
| `agent_optimization/tests/` | The offline fixture suite for everything above |
| `pyproject.toml`, `component-package.json` | The package manifests this skill installs from |
| `package.json`, `frontend-check.tsconfig.json`, `frontend-check.mjs` | Dependency set and recipe for compiling the extracted UI |

`situation_detector` and `copilot_terminal` are declared dependencies installed from their own
packages. They are deliberately not vendored into this archive.

## Optimization UI

All files below are under `runtime/agent_optimization/frontend/`.

| File | Surface |
| --- | --- |
| `OptimizationWorkspace.tsx` | Four-column workspace, protocol selection, experiment lifecycle and coding-agent dialog |
| `panes.tsx` | Dataset/profile views and chronological tool/source panes |
| `views.tsx` | Version history, metrics, investigation plans, exact probes and lever audits |
| `DetectorView.tsx` | Detector versions, rules, parameters, queries and processing source |
| `PerformanceView.tsx`, `TrajectoryChart.tsx`, `trajectory.ts` | Separate training F1, evaluation F1 and average-case-latency plots with real-version selection |
| `RunReplay.tsx` | Saved best/worst training and evaluation conversations and evidence |
| `columns.ts`, `optimization.css` | Resizing, collapse/focus/restore controls and workspace styling |
| `api.ts`, `types.ts`, `index.ts` | Host-injected HTTP adapter, typed wire contracts and public frontend exports |

Labels, empty-state copy and domain vocabulary are host-supplied. A target host still owns its
own presentation decisions and must keep measured-data and authorization semantics intact.

## Synthetic Example

`example/` contains hand-authored record shapes: a campaign summary, a trajectory CSV, three
generation records, one schema-2 detector configuration and one evidence tool with its metadata.
Every file carries `"synthetic": true` or an equivalent notice.

These are illustrations of structure. They were not produced by a run, a model or a measurement,
and their numbers are invented. Never cite them as performance and never compare them with a
real campaign.
