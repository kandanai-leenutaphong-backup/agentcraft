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

## Public Reference

Import the [public API](src/agentcraft_core/__init__.py). Install `agentcraft-core==0.1.0`
through [workspace setup](../README.md#installation); Python 3.12+ is required.

| Entry | Inputs, Defaults And Result |
| --- | --- |
| `CallerContext(principal, tenant="")` | Nonblank principal, at most 256 characters; host-established metadata, no credential lookup or authentication. |
| `ExecutionBudget(limits, parent=None)` | Nonempty mapping of named nonnegative integer attempt counts; child names/ceilings cannot widen the parent. `reserve(name, amount=1)` atomically charges the ancestor chain. |
| `ExecutionContext.create(caller, limits=..., timeout_seconds=30)` | Finite positive seconds; monotonic deadline and generated run id. `remaining()` returns seconds or raises `deadline_exceeded`. |
| `child(limits=..., timeout_seconds=None)` | Inherits caller/run id and remaining deadline; narrows budgets. `activate()` restores the prior context on exit; it owns no clients. |
| `reserve(name, amount=1)` | Checks the active deadline and budget; no-op without an active context. Participation is explicit, not an automatic whole-stack quota. |
| `mark_unknown(name, amount=1)` / `snapshot()` | Unknown counts require existing reservations and do not refund them; snapshots copy `limits`, `reserved` and `unknown`. |

`FailureInfo.to_dict()` is for safe machine diagnostics, not provider data. Only trusted
bounded fields belong in it. `FrameworkError` exposes its `failure`; it never adds a
provider payload. Fields are `code`, `category="failed"`, `capability_id=""`,
`operation=""`, `run_id=""`, `field=None`, `action`, `effect="none"`, `retry="never"`.
Effects are `none`, `accepted`, `unknown`; retry advice is `never`, `safe_after_correction`,
`read_back_first`, `unspecified`. `FrameworkError` defaults its category to `invalid`.
These are metadata values, not validation of arbitrary untrusted diagnostic text or a
universal replacement for native result/error contracts.

An exhausted budget raises `budget_exhausted`; correct the authorized caller budget,
never widen a child or refund unknown delivery. Construction and the example above do
no I/O and need no cleanup. [Context tests](tests/test_context.py) cover narrowing,
reservation integrity and refusals; [framework workflow](../../.github/skills/harness-guide/framework/README.md#offline-workflow)
shows real participating data/model/store calls and owned resource cleanup.