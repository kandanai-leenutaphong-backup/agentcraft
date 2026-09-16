# Framework Core

`agentcraft-core` has no runtime dependencies. It supplies immutable caller/run context,
safe failure metadata and an atomic process-local reservation budget. It grants no access,
stores no credentials, performs no I/O and installs no global client or retry engine.

```python
from agentcraft_core import CallerContext, ExecutionContext, reserve

run = ExecutionContext.create(CallerContext("operator"),
    limits={"data_calls": 2, "model_calls": 1, "tool_calls": 1}, timeout_seconds=30)
with run.activate():
    reserve("data_calls")
assert run.budget.snapshot()["reserved"]["data_calls"] == 1
```

Child budgets can only narrow parent limits/deadlines and share atomic parent reservations.
Unknown delivery never refunds work. Counts are not billing quotas or distributed limits.
Core context is optional for standalone native APIs; when activated, integrated capabilities
participate in the same run. `CallerContext` is host-established identity metadata, not
authentication. Capability policies retain exact grants; the context cannot widen them.

`FailureInfo.to_dict()` is for safe machine diagnostics, not provider data. Only trusted
bounded fields belong in it. `FrameworkError` exposes its `failure`; it never adds a
provider payload. Scope/permission failures and deadlines are explicit.