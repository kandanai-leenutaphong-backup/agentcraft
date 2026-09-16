# Situation Detector

Install `situation-detector`; import `situation_detector`. No application, dataset,
Azure credential or model is required. The [package](../../README.md) owns the runtime.
This guide preserves the portable skill contract; application-specific examples in
the older source README are historical, not package installation instructions.

## Contract

| Public API | Result |
| --- | --- |
| `normalize_config(configuration)` | Validated deep copy with explicit defaults |
| `selected_rules(configuration)` | Enabled rules in declaration order, with `rule_set_id` |
| `configuration_digest(configuration)` | SHA-256 of canonical normalized configuration |
| `normalize_window(window, max_window_seconds)` | Parsed and bounded start/end |
| `run_battery(configuration, window, execute, process, *, summarize=None)` | Sequential ordered result |
| `run_battery_async(...)` | Concurrent execution, declaration-ordered result |
| `stream_battery(...)` | Rule starts, completions as they finish, one final result |
| `ConfigurationError`, `RuleExecutionError` | Structural refusal or explicit rule failure |

`execute(rule, window)` returns an opaque bounded envelope other than `None`;
`process(rule, envelope, window)` returns an observation object. Optional
`summarize(entries, window)` returns the summary. Async batteries accept synchronous
or asynchronous callbacks. Callbacks receive the original window unchanged; only
the result window is normalized to ISO strings.

The result contains `configuration_digest`, `window`, `rules` and `summary`.
Each rule records set/rule identity, name, completed status, query result, processed
observations and elapsed time. Default summary: `tests_run`, `rule_sets_run`,
`configuration_version`. Completion order never reorders the final rules.

## Bounds And Refusals

Configuration retains extra fields, bounded to 32 extra keys per object, 64 rule
sets, 256 rules per set and 1 MiB serialized. IDs must be globally unique; empty
queries, missing IDs, nonserializable values and nonpositive or nonnumeric window
limits raise `ConfigurationError`. `enabled` defaults true; parameters, processing
and metadata default to empty objects.

Windows accept datetimes or ISO strings, including `Z`. Zero-width windows are
permitted. Reversed, over-limit or mixed aware/naive windows are refused. Stricter
host bounds do not belong in this package.

Execution exceptions, `None` query results and non-object processed results raise
`RuleExecutionError`, carrying `rule_set_id`, `rule_id` and `stage`. Failure never
becomes empty successful detection. A failing stream raises and cancels pending
rules without emitting `battery_completed`.

## Host Integration And Lifecycle

Read configuration at the composition root. The host authorizes queries, bounds
rows and processing, supplies callback resource lifetimes and interprets results.
Configuration names no executable code here: `query`, `parameters` and `processing`
remain opaque callback inputs. A host running candidate code must separately
authorize and isolate that runner. Detection is an observation, not a response action.

Resolve built-in rule references through an allowlist. Reject unknown identifiers
and overrides. Expose the active normalized configuration and digest through an
authorized readback contract; a compiled-in default does not prove what ran.
Different inputs and rule semantics remain different host configurations.

## Retirement And Verification

The four skill runtime files and the sixteen-test suite were byte-identical to
their canonical counterparts. The useful portable contract moved here; no source
was stored under documentation. Exact paths and hashes:
[retirement manifest](situation-detector-retirement.json).

```bash
python -B -m unittest discover -s libraries/situation-detector/tests -v
```

Use an environment with the canonical package installed. Tests cover refusals,
window preservation, order, digest stability, streaming failure and an unrelated
consumer. The Microsoft MIT notice remains in the native skill and the library.
Parent integration owns application imports and generated discovery.