# Situation Detector

Config-driven query-test battery shared by the application scanner and optimization.

The host supplies data access, time-window bounds, rules and domain processing. The component
owns ruleset selection, validated query-test definitions, stable configuration identity,
ordered results, and explicit failures. It imports no application or external repository, reads
no configuration at import time, and executes no code a configuration names: `query`,
`parameters` and `processing` are opaque values handed back to injected callbacks.

## Public surface (`template_foundations.situation_detector`)

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
`rule_set_id`, `rule_id` and `stage`. `stream_battery` raises out of the iterator and cancels
pending rules rather than emitting `battery_completed`.

## Use here

Two consumers, one battery, different configurations over different data.

### The Perth scanner

`app/cybereye/backend/investigation/detector/` keeps the Perth rules, evidence semantics and
situation synthesis. Its `composition.py` expresses the declared registry as a configuration and
reads one back into `Rule` objects; `DetectorEngine(adx, configuration=None)` and
`Scanner(adx, configuration=None)` run both `scan` and `stream_scan` through this component, so
adding, removing, disabling or tuning a rule is a configuration change with no global mutation
and no change to the default scan.

The active configuration is a file, not a code edit. `Settings.detector_config_path` defaults to
`app/cybereye/control/situation_detector.json` and is overridable with
`CYBEREYE_DETECTOR_CONFIG_PATH`; `main.py` reads it once through
`composition.load_configuration(path)` and constructs the one `Scanner` the application uses.
`load_configuration` accepts two rule shapes in a rule set:

- `{"builtin": "<registry rule id>", "enabled": …, "parameters": {…}, "processing": {…}}` —
  selects a declared Perth rule and shallow-merges overrides over its `parameters` and
  `processing`, which is how a threshold or score is retuned without touching `rules.py`;
- a full rule object, validated the same way.

Application-side refusals beyond the component's own: `threshold` a positive `int`, `score` an
`int` in 0–100, `role` in `anchor|corroborator|contextual`, `confidence` in `high|medium|low`,
`processing.kind == "entity_groups"` with `max_rows` in 1–200, an unknown builtin id or an
unknown override field, and `max_window_seconds` above the application's 48-hour cap.

Two endpoints read that active configuration back, in `app/cybereye/backend/api/scanning.py`:

| Route | Auth | Returns |
| --- | --- | --- |
| `GET /api/cyber/rules` | open | the **active** rules of `scanner.engine.rules` — `rule_id`, `label`, `version`, `role`, `score`, `confidence`, `behaviour_class`, `threshold`, `technique_ids`, `description`. A disabled or retuned rule is visible here, not the compiled-in registry |
| `GET /api/cyber/detector/configuration` | caller required | `{configuration, configuration_digest, component: "situation_detector", historical_replay: true}` |

`local_app.py` builds the optimization `detector_reference` from the same objects, so the
reference the optimization UI shows carries the real active `configuration`, its
`configuration_digest`, and `version` as that digest's first 12 hex characters — not a
remembered constant. Its `scope` states plainly that these rules are neither trained nor
evaluated on GUIDE.

### GUIDE joint optimization

`app.components.agent_optimization` runs the same battery over a schema-2 detector configuration
whose `processing.code` is a Python `process(rows, parameters)` function. **This component still
executes nothing**: the optimization component's dataset adapter compiles and runs that source in
the isolated sandbox and hands the result back through `process`. `query`, `parameters` and
`processing` remain opaque values here.

The existing Perth rules and GUIDE rules are separate configurations over different inputs, not
interchangeable detector logic. A caller's supplied window bounds every query. Detector output
contains observations/patterns and a summary, never a triage grade or executed response action.

Inspiration: GridIQ `tools/situations` — its config-driven rule declarations, stable config hash
for result provenance, entry-point window bounds that refuse zero-width and over-range windows,
and its separation of query, processing and synthesis stages. No grid rule, source file, import,
runtime dependency or license grant is copied from GridIQ; that project's license was not
inspected and none is claimed here.

Acceptance: [component tests](../tests/test_situation_detector.py) cover ruleset add/remove/
disable, deterministic hashes, query and processing failures, window bounds and propagation,
ordered output, and a second non-security consumer; the application side is covered by
`app/cybereye/tests/test_detector_engine.py` and
`app/cybereye/tests/test_detector_configuration.py`, which asserts the shipped control file
equals `default_configuration()`, that a builtin selection with `{"threshold": 3}` executes only
that rule and binds `rule_threshold=3` into the issued query, that `/api/cyber/rules` lists the
configured rules rather than the whole registry, that `/api/cyber/detector/configuration`
returns that configuration and names the component, and that a missing file, an unknown builtin
and a non-`entity_groups` processing kind are each refused.