# Situation Detector

Portable import: `situation_detector`. The portable tests and [entry point](../../SKILL.md)
travel with this skill. No particular application or dataset is required.

Config-driven query-test battery shared by the application scanner and optimization.

The host supplies data access, time-window bounds, rules and domain processing. The component
owns ruleset selection, validated query-test definitions, stable configuration identity,
ordered results, and explicit failures. It imports no application or external repository, reads
no configuration at import time, and executes no code a configuration names: `query`,
`parameters` and `processing` are opaque values handed back to injected callbacks.

## Public surface (`situation_detector`)

| Name | Contract |
| --- | --- |
| `normalize_config(configuration) -> dict` | Validates and deep-copies a configuration; returns the normalized object |
| `selected_rules(configuration) -> list[dict]` | Enabled rules of enabled sets, declaration order, each with `rule_set_id` |
| `configuration_digest(configuration) -> str` | SHA-256 hex of the canonical normalized configuration |
| `normalize_window(window, max_window_seconds) -> {"start","end"}` | Parses and bounds a window |
| `run_battery(configuration, window, execute, process, *, summarize=None) -> dict` | Sequential run |
| `run_battery_async(...) -> dict` | Same result, every rule started concurrently |
| `stream_battery(...) -> AsyncIterator[dict]` | `rule_started` per rule, `rule_completed` as each finishes, one `battery_completed` |
| `ConfigurationError`, `RuleExecutionError` | Structural refusal, and a named rule failure |

Callbacks: `execute(rule, window)` returns an opaque query envelope (any bounded value except
`None`); `process(rule, envelope, window)` returns an object of observations; optional
`summarize(entries, window)` returns the final summary object. Async batteries accept sync or
async callbacks.

**Both callbacks receive the caller's original `window` object, unchanged.** The component
validates and bounds a normalized copy for its own use and never substitutes it: a host that
passed ISO strings gets ISO strings, and a host that passed datetimes gets datetimes. Only the
result's `window` is normalized, and it is emitted as `isoformat()` strings, so a caller reading
`result["window"]["start"]` gets `str` and never a `datetime`. A callback needing parsed
instants parses them itself.

Result: `{configuration_digest, window: {start, end} (ISO), rules: [{rule_set_id, rule_id, name,
status: "completed", query_result, processed, elapsed_ms}], summary}`. Rules stay in declaration
order regardless of completion order. The default summary is
`{tests_run, rule_sets_run, configuration_version}`.

## Configuration

```json
{
  "version": "example-replay-1.0.0",
  "max_window_seconds": 172800,
  "rule_sets": [{
    "id": "example_replay", "name": "Example replay detection rules", "enabled": true,
    "rules": [{
      "id": "explicit_credential_burst", "name": "Explicit credential use",
      "query": "Events | where source_time between (start .. end) ...",
      "parameters": {"threshold": 5, "score": 35, "role": "anchor"},
      "processing": {"kind": "entity_groups", "max_rows": 100},
      "enabled": true,
      "metadata": {"origin": "declared"}
    }]
  }]
}
```

`enabled` defaults to true; `parameters`/`processing`/`metadata` default to empty objects.
Additional fields at any level are retained unchanged, bounded at 32 extra keys per object,
64 rule sets, 256 rules per set and 1 MiB serialized. Rule-set ids and rule ids are globally
unique. Missing IDs, duplicate IDs, a non-numeric or non-positive `max_window_seconds`, an empty
query and a non-serializable configuration all fail with `ConfigurationError`.

Windows accept datetimes or ISO-8601 strings (`Z` accepted). `end == start` is permitted, so a
same-timestamp incident window is expressible; `end < start`, a span beyond
`max_window_seconds`, and mixing an aware with a naive instant are refused rather than coerced.
A stricter rule, such as requiring a positive window of at most 48 hours, stays with the
consuming application.

## Failure

An execution failure is never an empty successful detection. `execute` raising, returning `None`,
or `process` returning something other than an object raises `RuleExecutionError` carrying
`rule_set_id`, `rule_id` and `stage`. `stream_battery` raises out of the iterator and cancels
pending rules rather than emitting `battery_completed`.

## Host Integration

A scanner and an optimization experiment can use the same battery with different configurations
and different inputs. The host owns rule semantics, query authorization, result interpretation
and any stricter window limit. Similar rule names do not make datasets interchangeable.

Read configuration once at the composition root. Validate application-specific thresholds,
bounded row counts and processing kinds before constructing callbacks. If a host supports
references to built-in rules, resolve them through an allowlisted registry; unknown identifiers
and override fields must fail, not silently select a default rule.

Expose the active normalized configuration and its `configuration_digest` through the host's
authorized readback contract. A disabled or retuned rule must be visible there; displaying a
compiled-in default does not prove which configuration produced an observation.

An optimization host may interpret `processing.code` as candidate source in its own isolated
runner. This battery still executes no configuration-supplied code: it passes `query`,
`parameters` and `processing` to the injected callbacks. The host must authorize and bound that
runner independently. Detector output is an observation, not an executed response action.

[Component tests](../../tests/test_situation_detector.py) cover ruleset add/remove/disable,
deterministic hashes, query and processing failures, window bounds and propagation, ordered
output, and a second non-security consumer. They use offline fixtures, not customer data.