# CONTRACT.md — purpose-built-tools

Everything needed to reimplement this box in another language, or to feed
the meter from a system that does not use the shaping half. Shapes are
exact; the constants are the ones tuned against a live agent.

---

## 1. Result shapes

Every delivered tool result is a **JSON string**: a success table or an
explicit refusal, failure, duplicate or missing envelope. Key order is insertion order.

### 1.1 Success

```json
{
  "columns": ["site", "at", "kind"],
  "rows": [{"site": "SITE_A", "at": "2026-04-15T10:01:00", "kind": "trip"}],
  "scope": {"site": "SITE_A", "start": "...", "end": "...", "row_count": 1},
  "note": "optional one-line hint"
}
```

* `columns` is explicit, never derived from the first row. An empty result
  must still declare what it would have returned.
* `scope` echoes the identifying arguments and always carries `row_count`.
  This is what stops a speculative re-call (GOTCHAS.md G10).
* `note` is omitted when empty.

### 1.2 Refusal — input rejected, body never ran

```json
{
  "refused": true,
  "parameter": "site",
  "problem": "value is 21 characters",
  "accepted": "a code of letters, digits, underscore, hyphen or space (for example 'SITE_A'), at most 16 characters"
}
```

`accepted` is mandatory. A refusal that does not state the acceptable form
is a dead end (GOTCHAS.md G11).

### 1.3 Failure — the tool could not answer

```json
{
  "error": true,
  "detail": "tool_failed",
  "code": "tool_failed",
  "category": "failed",
  "action": "inspect_tool_and_read_back_effects",
  "effect": "unknown",
  "retry": "read_back_first"
}
```

All diagnostic values are fixed machine metadata, independent of exception
type, message or payload. `failure(detail, exc=...)` keeps its call signature
but ignores both legacy diagnostic inputs without inspecting or formatting them.
Unknown effects require read-back before any retry; this is guidance, not retry
authorization or a claim that no external effect occurred.

Both `purpose_built` wrappers use the same failure handler. Default warning logs
carry only the declared tool name and fixed failure code, never exception text or
tracebacks. The optional measurement sink receives `detail="tool_failed"`.

The existing body-error policy remains: body `Exception` failures, including
programming errors raised inside the body, become error envelopes. Validation
and result-shaping errors are outside that handler and propagate. Cancellation
(`asyncio.CancelledError` and `concurrent.futures.CancelledError`), interrupts,
exits and other `BaseException` controls propagate without a result or call record.
No blanket `BaseException` handler is used.

`sanitize_detail` still URL-strips and caps authored refusal messages at 500
characters; it is not a sanitizer for arbitrary exception or sensitive data.
Tool-authored envelopes and logging remain the tool author's responsibility.

### 1.4 Duplicate — this exact call already ran this turn

```json
{
  "duplicate": true,
  "tool": "find_events",
  "scope": {"site": "SITE_A", "...": "..."},
  "detail": "find_events already ran with these arguments in this turn. Reuse the earlier result; do not repeat the call. If the earlier result was empty, that is the answer."
}
```

Not an error: the answer exists in the transcript. A caller that reads
"error" retries.

### 1.5 Missing - the body delivered no result

```json
{"missing": true}
```

A body returning `None` produces this envelope, with no fabricated `rows`,
`scope` or `row_count`. The object survives hosted JSON decoding unchanged.
An explicit `[]` or `(columns, [])` instead produces a successful empty table
with `row_count: 0`. Consumers must not treat absent output as a zero-result query.

---

## 2. Result classification

One function, used by both the envelope and the meter. Given a decoded
result:

| Input | Class |
| --- | --- |
| `Ellipsis` (truncation sentinel) | `productive` |
| `None` or JSON `null` | `missing` |
| object with truthy `error` | `error` |
| object with truthy `refused` | `refused` |
| object with truthy `duplicate` | `duplicate` |
| object with truthy `missing` | `missing` |
| object with `rows == []` | `empty` |
| object with `summary.total_rows == 0` | `empty` |
| `[]` | `empty` |
| non-empty list, object, scalar, non-empty text | `productive` |
| empty string | `empty` |

A JSON string is decoded once before classification. Unparseable non-empty
text is `productive` (GOTCHAS.md G8).

Aggregate sets:

```
UNPRODUCTIVE = {error, empty, missing}
TURN_COST    = UNPRODUCTIVE ∪ {refused, duplicate}
```

The split is load-bearing. Only `UNPRODUCTIVE` may contribute to a cull
decision; refusals and duplicates cost a turn but hand the caller a next
step (GOTCHAS.md G13).

---

## 3. Call record schema

One JSON object per line. This is the meter's entire input, so a system
with its own tool layer can feed it by emitting this shape.

```json
{
  "tool": "find_events",
  "result_class": "productive",
  "ms": 12.4,
  "run_id": "run-3",
  "case_id": "incident-7",
  "split": "held_out",
  "detail": "site",
  "ts": 1776470400.0
}
```

| Field | Meaning |
| --- | --- |
| `tool` | Tool name. The only required field besides `result_class`. |
| `result_class` | One of the six classes above. |
| `ms` | Wall-clock duration. |
| `run_id` | One attempt at one task. Groups calls. |
| `case_id` | The task. Groups runs, and joins to outcomes. |
| `split` | Free-form partition label, e.g. `train` / `held_out`. |
| `detail` | Refusal: the refused **parameter name**. Error: the fixed code `tool_failed`. Never exception types, payloads or argument values. |
| `ts` | Unix seconds. |

Rules:

* Records carry **no argument values**. The meter needs shapes, not data.
* A malformed or truncated line is skipped, not fatal — the file is being
  appended to by a process that may still be running.
* When `run_id` is absent, `"{case_id}:0"` is used, so single-run data
  still aggregates.

## 3.1 Outcome schema

Optional. Without it every rate still computes; only the association
columns are omitted.

```json
[
  {"case_id": "incident-7", "gates": {"detect": "pass", "explain": "partial"}, "split": "held_out"}
]
```

`gates` is an open dict — gate names are domain knowledge. Bands treated as
success: `pass`, `partial`. Any other string counts as failure.

---

## 4. Spec and validation

A tool is declared by a spec:

```
ToolSpec(name, purpose, call_when, params, returns, dedupe_on,
         max_calls=1, cross_checks=(), replaces="")
Param(name, description, validator=None, required=True, default=None)
```

Validation order, first failure wins:

1. For each declared parameter, in order: resolve the value (argument,
   else default). Missing or blank and required → refusal
   `"value is missing"`.
2. Missing and optional → the default, no validation.
3. Run the parameter's validator. A `Rejection` returns immediately.
4. Copy through any argument not named in the spec, unvalidated. An SDK may
   inject its own; refusing them would strand the call.
5. Run each cross-check against the fully validated dict. First
   `Rejection` returns.

Only the **first** failure is reported. A caller repairing one problem at a
time makes progress; a list of five usually produces a rewrite that
introduces a sixth.

Dedupe key: `tuple(str(arguments[name]).strip().lower() for name in dedupe_on)`.
Scope: `{name: arguments[name] for name in dedupe_on}` plus `row_count`.

Generated description, exactly:

```
{purpose}

When to call: {call_when}
Returns: {returns}
```

Parameters are documented per parameter, as `{description} Accepts {validator.accepted}.`
plus `Optional.` when not required. They are not repeated in the tool
description — two copies diverge.

### 4.1 Validator contract

A validator is `(value, parameter_name) -> cleaned value | Rejection`, plus
an `accepted` string describing the acceptable form. `accepted` appears in
both the parameter documentation and the refusal, from the same field, so
the documented rule and the enforced rule cannot drift.

| Validator | Accepts |
| --- | --- |
| `identifier(max_len, example)` | `^[A-Za-z0-9_\-\s]+$`, trimmed, quote-escaped |
| `label(max_len)` | `^[A-Za-z0-9_/\-\.\s\|,]+$`, trimmed, quote-escaped |
| `uuid()` | canonical 8-4-4-4-12 hex |
| `one_of(options, case_sensitive=False)` | membership; returns the canonical member |
| `timestamp()` | ISO 8601, trailing `Z` accepted, returned normalised |
| `integer_range(low, high)` | integer, inclusive bounds |
| `bounded_list(item, cap, min_items=1)` | list, each element via `item`, refusal names `param[i]` |
| `time_window(start, end, max_hours)` | cross-check: end after start, span within cap |

The character classes exclude the single quote, so quote escaping is
defence in depth for a future widening rather than the active guard.

---

## 5. Turn ledger

Per-turn, stored in a context-local variable so concurrent turns cannot see
each other's calls and no tool signature has to carry it.

* `record_call_once(tool, key, max_calls)` increments the count for
  `(tool, *key)` and returns True once the count **before** the increment
  reaches `max_calls`.
* With no ledger installed it returns False, so a tool called outside a
  turn behaves exactly as if the guard were absent. This is required: unit
  tests, scripts and one-off invocations must not be suppressed.
* Records are stamped with the turn's `run_id` / `case_id` / `split`.
* A sink failure is swallowed. Measurement must never take down the thing
  being measured.

---

## 6. The weight meter

### 6.1 Per-tool statistics

| Column | Definition |
| --- | --- |
| `total_calls` | every observed invocation |
| `runs_using` | distinct `run_id` with at least one call |
| `cases_touched` | distinct `case_id` with at least one call |
| `avg_calls_per_run` | `total_calls / runs_using` |
| `error_rate` | `error / total_calls` |
| `refusal_rate` | `refused / total_calls` |
| `duplicate_rate` | `duplicate / total_calls` |
| `empty_rate` | `empty / total_calls` |
| `unproductive_rate` | `(error + empty + missing) / total_calls` |
| `turn_cost_rate` | `unproductive + refused + duplicate` over total |
| `top_refused_parameters` | the three most-refused `detail` values |

### 6.2 Outcome association (descriptive only)

For each gate, over cases: the pass-or-partial rate among cases that called
the tool, versus cases that did not. Cases with an outcome and no recorded
call belong to the unused arm — omitting them silently drops the control
group.

An association counts as evidence only when the unused arm has at least
`MIN_ASSOC_N` cases.

### 6.3 Signal

Thresholds:

```
LOW_USAGE_PCT     = 15.0   runs_using_pct below this: rarely reached
HIGH_UNPRODUCTIVE = 0.50   at or above: noisy
HIGH_ERROR        = 0.40   at or above: the caller cannot form a valid call
HIGH_REFUSAL      = 0.25   at or above: advisory only
HIGH_DUPLICATE    = 0.20   at or above: advisory only
MIN_ASSOC_N       = 2      smallest unused arm that counts as evidence
```

```
noisy       = unproductive_rate >= HIGH_UNPRODUCTIVE or error_rate >= HIGH_ERROR
rarely_used = runs_using_pct < LOW_USAGE_PCT
associated  = used rate > unused rate on any gate, with a qualifying unused arm

no cull reasons          -> "strong" if associated else "ok"
(noisy or rarely_used) and associated -> "noisy but associated"   (fix, do not cull)
(noisy or rarely_used)                -> "review / cull candidate"
otherwise                             -> "ok"
```

Refusal and duplicate rates never contribute to `noisy`. They append an
advisory to the reason string (GOTCHAS.md G13).

### 6.4 The ablation protocol — the causal test

A signal is a hypothesis. This confirms it.

1. **Change one thing.** Unregister the flagged tool. Nothing else — no
   prompt edit, no threshold change (GOTCHAS.md G4).
2. **Redeploy**, if the tool registration is baked into an artefact.
3. **Re-run** the full battery, **serially**, at least **three runs per
   case**, producing records and outcomes (GOTCHAS.md G3).
4. **Compare** against the pre-ablation baseline on: outcome gate rates,
   per split; and the surviving tools' `unproductive_rate` and total calls
   per case.
5. **Keep the removal if and only if** gate rates do not drop — train
   up-or-flat **and** held-out not down — **and** noise falls. Otherwise
   revert: the tool was load-bearing despite the noise, or the noise simply
   moved to another tool.

Before culling a noisy tool, prefer **replacement**: build the shaped tool
covering the same need, confirm outcomes hold, then remove the raw one.
That sequence is what worked; ablation alone was rejected (GOTCHAS.md G2).

---

## 7. Lint rules

Errors (objective, blocking):

* `purpose` empty.
* `call_when` shorter than 25 characters.
* A parameter with no description.
* `dedupe_on` naming something that is not a parameter.
* Duplicate tool names.

Warnings (need judgement):

* A parameter with no validator.
* A parameter description containing none of: `from `, `returned by`,
  `as returned`, `use the`, `output of`, `listed by`, `given by`, `one of`.
* A spec with parameters and no `dedupe_on`.
* A spec with no parameters.
* More than `max_tools` (default 8) tools on one surface.

---

## 8. Result shape to card archetype

The envelope has a third consumer after the model and the meter: the
operator's screen. `renderers/` maps each shape to one of seven archetypes,
so a new tool gets a real card by declaring which shape it returns rather
than by someone writing a component.

| Archetype | Envelope it renders | Card |
| --- | --- | --- |
| `tabular` | `{columns, rows\|data, scope}` | Scrollable table, preview cap, prominent columns |
| `graph` | `{nodes, edges, summary}` or a bare node list | Node/edge chips + union-keyed table |
| `search` | `{results: [{title, source, score, text}], count}` | Stacked hit cards |
| `metrics` | `{metrics: [{label, value, unit?}]}` or a scalar map | Metric grid |
| `document` | `{title?, document\|text\|content\|body}` or plain text | Scrollable prose |
| `status` | `{status, message?, detail?}` | Status chip + prose lines |
| `action` | `{action, status?, simulated?}` | Action chip + simulated banner |

Rules a reimplementation must preserve:

1. The three envelope states short-circuit the card in **every** archetype,
   and each looks different: `error` red and announced via `role="alert"`,
   `refused` amber and leading with the accepted form, `duplicate` muted.
   Rendering a refusal as an error tells the operator that a working
   guardrail is a fault (GOTCHAS.md G13).
2. A shape mismatch renders a **bounded unresolved card** naming the
   archetype with a preview capped at 180 characters. Never a raw-JSON
   dump: a dump renders, so it never gets fixed.
3. An empty result carries the scope badges and a zero chip. The reader must
   be able to see the question was asked (GOTCHAS.md G10).
4. Graph node tables use the **union** of every node's keys as headers.
   Heterogeneous nodes otherwise lose columns silently.
5. Archetype keys are a contract. A tool declares one; the box's selftest
   asserts every declared key resolves to a component and appears in this
   table, so a rename fails the build instead of orphaning a tool
   (GOTCHAS.md G18).

Declare the mapping next to the tools, as each example in
`examples/azure/` does:

```python
ARCHETYPES = {"find_events": "tabular", "summarise_metric": "metrics"}
```

---

## 9. Minimal reference implementation

The smallest thing satisfying sections 1, 2, 4 and 5:

Use public `purpose_built`; the single wrapper owner (source-or-asset-not-bundled; source reference: `toolshape/_decorator.py`)
implements validation, turn-local deduplication, body execution, missing/empty distinction
and measurement. Failure metadata follows section 1.3, never exception text or type.
Cancellation propagates; callers must not recreate a permissive wrapper from pseudocode.

---

<!-- api-surface:start -->

## Public surface

Names exported by toolshape (source-or-asset-not-bundled; source reference: `toolshape/__init__.py`). The public source owns signatures;
this reference does not require a retired template generator.

| Name | Kind | Description |
| --- | --- | --- |
| `DEFAULT_MAX_TOOLS` | constant | 8 |
| `DUPLICATE` | constant | 'duplicate' |
| `EMPTY` | constant | 'empty' |
| `ERROR` | constant | 'error' |
| `HIGH_DUPLICATE` | constant | 0.2 |
| `HIGH_ERROR` | constant | 0.4 |
| `HIGH_REFUSAL` | constant | 0.25 |
| `HIGH_UNPRODUCTIVE` | constant | 0.5 |
| `LOW_USAGE_PCT` | constant | 15.0 |
| `MIN_ASSOC_N` | constant | 2 |
| `MISSING` | constant | 'missing' |
| `PRODUCTIVE` | constant | 'productive' |
| `REFUSED` | constant | 'refused' |
| `RESULT_CLASSES` | constant | ('productive', 'error', 'empty', 'refused', 'duplicate', 'missing') |
| `SIGNAL_NOISY_ASSOCIATED` | constant | 'noisy but associated' |
| `SIGNAL_OK` | constant | 'ok' |
| `SIGNAL_REVIEW` | constant | 'review / cull candidate' |
| `SIGNAL_STRONG` | constant | 'strong' |
| `UNPRODUCTIVE_CLASSES` | constant | ('error', 'empty', 'missing') |
| `CallRecord` | class | One observed tool call. |
| `Finding` | class | One lint result. ``level`` is ``error`` or ``warn``. |
| `JsonlSink` | class | Appends one JSON object per line. The default in a deployed process. |
| `MemorySink` | class | Collects records in a list. The default in tests and short scripts. |
| `NullSink` | class | Discards records. The default when nothing is installed. |
| `Outcome` | class | How one task turned out, per gate. |
| `Param` | class | One tool parameter, with the rule the caller is told and held to. |
| `Rejection` | class | Why a value was refused, and what would be accepted instead. |
| `Report` | class | Everything the meter computed for one iteration. |
| `ToolSpec` | class | A purpose-built tool's whole affordance. |
| `ToolStat` | class | Aggregated weight statistics for one tool. |
| `Validator` | class | A named check: ``(value, parameter) -> cleaned value or Rejection``. |
| `aggregate` | function | Compute per-tool statistics from call records and optional outcomes. |
| `begin_turn` | function | Start a turn: a fresh ledger plus the labels stamped on its records. |
| `bounded_list` | function | A list of validated items, with a hard cap. |
| `catalogue` | function | Render the whole surface as one reviewable page. |
| `classify` | function | Classify one tool result. Accepts a JSON string or a decoded object. |
| `duplicate` | function | The repeat shape: this exact call already ran this turn. |
| `emit` | function | Send a record to the installed sink, stamped with the turn context. |
| `end_turn` | function | Restore the previous ledger and context. |
| `escape_quotes` | function | SQL-style ``'`` -> ``''`` escape. Idempotent on escaped input. |
| `failure` | function | The failure shape. The tool could not answer; the caller learned nothing. |
| `get_sink` | function | Return the installed record sink. |
| `identifier` | function | A code-shaped token: letters, digits, underscore, hyphen, space. |
| `integer_range` | function | An integer within an inclusive range. |
| `is_unproductive` | function | True when the call consumed a turn without delivering information. |
| `json_schema` | function | A JSON-schema-shaped description, for an SDK that wants one. |
| `label` | function | A free-form label: identifier characters plus ``/ . | ,``. |
| `lint` | function | Check a tool surface against the affordance rules. |
| `load_outcomes` | function | Read an outcomes JSON file: a list of ``{case_id, gates, split}``. |
| `one_of` | function | A closed vocabulary. |
| `purpose_built` | function | Wrap a function as a purpose-built tool returning a JSON string. |
| `read_records` | function | Read a JSONL record file. Malformed lines are skipped, not fatal. |
| `record_call_once` | function | Count this call and report whether the per-turn limit is exceeded. |
| `refusal` | function | The teaching shape: what was wrong and what would work. |
| `render_markdown` | function | Render the report as a reviewable markdown table. |
| `sanitize_detail` | function | Cap and URL-strip a caller-visible message. |
| `set_sink` | function | Install the process-wide record sink; returns the previous one. |
| `specs_in` | function | Collect every ToolSpec attached to a callable in the given namespaces. |
| `table` | function | The success shape: ``{columns, rows, scope}`` as a JSON string. |
| `time_window` | function | A cross-parameter check: end after start, span within a cap. |
| `timestamp` | function | An ISO 8601 timestamp, returned normalised. |
| `tool_names` | function | Every decorated tool name in the given namespaces. |
| `turn` | class | Context manager form of :func:`begin_turn` / :func:`end_turn`. |
| `uuid` | function | A UUID-shaped identifier. |

<!-- api-surface:end -->
