# Situation Detector

Public query-test reference. The [package guide](../../README.md) owns installation;
[workflow guidance](../../docs/skills/situation-detector.md) covers host integration.

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
| `run_battery_async(..., max_concurrency=8) -> dict` | Same result, bounded concurrent rules |
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
  "version": "perth-replay-1.0.0",
  "max_window_seconds": 172800,
  "rule_sets": [{
    "id": "perth_replay", "name": "Perth replay detection rules", "enabled": true,
    "rules": [{
      "id": "explicit_credential_burst", "name": "Explicit credential use",
      "query": "EventsUnified | where source_time between (start .. end) ...",
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
A stricter application rule (CyberEye requires a strictly positive window of at most 48 hours)
stays with the application.

## Failure

An execution failure is never an empty successful detection. `execute` raising, returning `None`,
or `process` returning something other than an object raises `RuleExecutionError` carrying
`rule_set_id`, `rule_id`, `stage` and a safe `code`. Callback payloads are not
included. `stream_battery` raises out of the iterator and cancels and awaits
pending rules rather than emitting `battery_completed`. Cancellation propagates.

## Immediate Consumers

Investigation's detector (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/investigation/detector`)
owns Perth rules, evidence semantics, stricter windows and synthesis. Its
protected API (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/api/scanning.py`)
reads active rules/configuration under the application's authorization gate; the library
creates no route or caller identity. Current composition belongs to the
application owner map (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/docs/ARCHITECTURE_OVERVIEW.md`).

agent_optimization.workflow (source-or-asset-not-bundled; source reference: `../../../agent-optimization/src/agent_optimization/workflow.py`)
runs the same battery over schema-2 rules. Its injected callbacks own query execution and
sandboxed processing. This library never compiles configuration-supplied code or grants access.

The existing Perth rules and GUIDE rules are separate configurations over different inputs, not
interchangeable detector logic. A caller's supplied window bounds every query. Detector output
contains observations/patterns and a summary, never a triage grade or executed response action.

Inspiration: GridIQ `tools/situations` — its config-driven rule declarations, stable config hash
for result provenance, entry-point window bounds that refuse zero-width and over-range windows,
and its separation of query, processing and synthesis stages. No grid rule, source file, import,
runtime dependency or license grant is copied from GridIQ; that project's license was not
inspected and none is claimed here.

Acceptance: component tests (source-or-asset-not-bundled; source reference: `../../tests/test_situation_detector.py`) cover ruleset add/remove/
disable, deterministic hashes, query and processing failures, window bounds and propagation,
ordered output, and a second non-security consumer. App-specific acceptance belongs to the
Investigation runbook (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/deploy/README.md`).