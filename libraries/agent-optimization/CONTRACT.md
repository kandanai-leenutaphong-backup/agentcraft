# Optimization Contract

## Inputs And Authority

`OptimizationService(dataset, root, model, predict, *, authorize, profile, identify, ...)`
receives host-owned dependencies. `authorize(caller)` supplies the authorized storage
owner and `identify(caller)` supplies record ownership. Every record read checks both.
Predictor receives prompt, evidence and model only, never the case's expected label.
`profile.model_request` describes replay input; it is not a second execution path.
The host binds model execution to `llm_interface`; `model_predictor` was retired.

`SQLiteReader(path, *, allowed_tables=...)` snapshots trusted table policy. A query's
`tables` can only narrow it. `labels`, SQLite catalogues, writes, DDL, extensions,
attached databases and unlisted functions refuse. Rows and elapsed work are bounded.
This is an evidence database, not permission to supply an arbitrary caller path.
Construction cannot make label-bearing host views safe; the host must classify its
tables and must never put evaluator labels in an allowed evidence table.

`PythonToolRunner` requires explicit Bubblewrap and libseccomp. Missing isolation
refuses; there is no unsandboxed fallback. Its result kind is
`optimization_tool_result`, replacing the application's `cybereye_tool_result`.

## Results And State

Generations, detector definitions, tools, probe receipts and cohort files are immutable.
Experiment status is a mutable local ledger. Host-owned roots are single-process,
not a multi-replica storage service. Owner-only persisted read-back is the result.
Unknown/denied/malformed operations raise documented Python exceptions; model failures
remain scored errors, not successful empty cases. Expected labels stay evaluator-only;
authorized development feedback and replay may show recorded outcomes after measurement.

`measure_run` writes case rows and exemplar files, then stages its completed manifest
through `workrecovery`. `run.json` is create-if-absent-or-identical and verified by
read-back. `RunSaveError.outcome` distinguishes failed/unknown/conflicting saves and
preserves staged bytes. Recovery never reruns a predictor:

```python
from agent_optimization import run_recovery

jobs = run_recovery(authorized_run_directory, saved_run_id)
artifact = jobs.read(saved_run_id)
outcome = jobs.recommit(artifact)
assert outcome.saved and outcome.verified
```

Only authorized host code receives the run directory. The `.recovery` directory is
operator state and must not be deleted. Case streaming and exemplar creation precede
manifest recovery; an earlier filesystem failure remains a limitation, not a claim
that unfinished computation can resume.

## Lifecycle And Limits

The service owns one evaluation executor; `cancel` sets its stop signal and `close`
cancels pending work. Running synchronous native work can outlive cancellation;
there is no forced termination or exactly-once side-effect guarantee. Model binding,
credentials, dataset and terminal host lifetime remain owned by their caller.
Protocol limits bound versions/tools/workers; SQL and sandbox have separate bounds.
No retry wraps a model call. Full campaign protocols remain opt-in and were not run.

## Conformance

| Standard | Selected Result / Remaining Gap |
| --- | --- |
| F1 | Named distribution/API and capability references here; generated framework descriptor/catalogue belongs to parent and is pending |
| F2 | Normal dependencies, wheel/npm owners and public imports; no skill runtime lookup; Python 3.12 selected profile; portable artifact checks recorded in migration evidence |
| F3 | Host authorization/identity; immutable table policy and matching label/write refusals; legacy profile is not an appcompose schema |
| F4 | Immutable receipts, scored failures and native workrecovery outcomes; unified framework failure metadata is not yet adopted |
| F5 | Explicit synchronous service close/cancel; native work may outlive cancellation; no async forced-close guarantee |
| F6 | Existing protocol/SQL/sandbox bounds; host llm_interface owns execution limits; no shared portfolio budget descriptor yet |
| F7 | Persisted owner ledger, replay and recovery; historical event schema retained, not claimed as common framework event conformance |
| F8 | Injected collaborators, offline positive/refusal tests; live model, sandbox, app browser and cloud workflows remain separately unverified |

These gaps are not full-framework acceptance. No license for customer data or external
assets is created by source movement.