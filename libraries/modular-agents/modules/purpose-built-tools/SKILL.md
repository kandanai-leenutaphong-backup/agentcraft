---
name: purpose-built-tools
description: Replace raw query access with narrow, purpose-built agent tools - validated inputs, refusals that teach, one tabular result shape, per-turn duplicate suppression - and measure which tools earn their place with a call-weight meter and an ablation protocol. Use when an agent writes malformed queries, when tool calls return empty results and the agent retries the same call, when deciding whether to add, replace or remove a tool, when a tool surface has grown past a handful, when tuning tools during a hill-climbing loop, or when you need evidence rather than taste for "should this tool exist".
license: MIT
---

# Purpose-built tools

A raw query tool asks the caller to author a formal language. It will get
it wrong at a rate no prompt fixes, and the parser error teaches it
nothing. A purpose-built tool takes intent and holds the syntax in code, so
the malformed call cannot be expressed.

Measured here: a raw graph tool at **44% hard errors**. Deleting it made
outcomes worse — it was load-bearing. Replacing it with shaped tools cut
error noise **75%** and recovered the outcomes.

Two halves: shape a tool, then measure whether it earns its place.

## Decide in one line

| Situation | Action |
| --- | --- |
| The agent writes malformed queries | Shape the tool; prompting will not fix a grammar (G1) |
| Agent calls a tool, gets nothing, calls it again | Populate `scope` + set `dedupe_on` (G10) |
| Agent invents plausible parameter values | Name the value's source; use `one_of` (G12, G15) |
| Deciding whether to remove a tool | Run the meter, then the ablation protocol (G16) |
| The meter flags your best tool | Check refusal vs error — refusals are not waste (G13) |
| You removed the noisy tool and scores fell | Expected. Replace, do not cull (G2) |
| Surface has grown past ~8 tools | `scripts/lint_surface.py --catalogue`, then cull (G5) |
| A tool posts perfect numbers and no gain | Judge on the outcome gate, not adoption (G9) |
| Wiring a tool to Gremlin / KQL / AI Search / GQL / Cosmos | Copy the matching `examples/azure/` file |
| Tool results render as raw JSON in the UI | Declare an archetype; see `renderers/` |
| Cards render unstyled after copying `renderers/` | G17 — tokens + Tailwind `content` |
| Reimplementing in another language | `CONTRACT.md` only |

## Install

```bash
cp -r purpose-built-tools/toolshape <your-app>/
# no dependencies
```

Declare a tool, then wrap it:

```python
from toolshape import Param, ToolSpec, purpose_built, identifier, one_of, timestamp, time_window

FIND_EVENTS = ToolSpec(
    name="find_events",
    purpose="Return events at one site inside a time window, newest last.",
    call_when=(
        "Whenever you need event records for a site. Call this instead of "
        "writing a query. Use the site code returned by list_sites."
    ),
    params=[
        Param("site",  "Site code, as returned by list_sites.", validator=identifier(max_len=16)),
        Param("start", "Window start, from the incident time.", validator=timestamp()),
        Param("end",   "Window end, from the incident time.",   validator=timestamp()),
        Param("kind",  "Restrict to one event kind.", validator=one_of(("trip", "alarm")), required=False),
    ],
    returns="A table with columns site, at, kind, detail.",
    dedupe_on=("site", "start", "end", "kind"),
    cross_checks=(time_window(max_hours=48),),
    replaces="run_query",
)

@your_sdk.tool                      # your framework's decorator, outermost
@purpose_built(FIND_EVENTS)         # this box
async def find_events(site, start, end, kind=None):
    rows = await backend.events(site, start, end, kind)
    return ["site", "at", "kind", "detail"], rows
```

The body returns rows or a `(columns, rows)` pair. The wrapper validates,
suppresses repeats, builds the envelope, catches exceptions and records the
call. `__doc__` is generated from the spec, so the description the model
reads cannot drift from what the code enforces.

### Writing the fields that matter

`call_when` is what the model chooses by. Say when to reach for this tool
*rather than its siblings*, and say the order:

```
"Call this FIRST when investigating a site — it returns the vocabulary the
 other tools need."
"Call after find_sites, using the code it returns."
```

Parameter descriptions must say **where the value comes from**. "Site code"
gets invented values; "site code, as returned by `list_sites`" does not
(G12).

Anything with fewer than ~20 legal values is `one_of(...)`. The refusal
lists them, so one wasted call teaches the whole vocabulary (G15).

## Use

Validators: `identifier`, `label`, `uuid`, `one_of`, `timestamp`,
`integer_range`, `bounded_list`, and the cross-parameter `time_window`.
Each carries the accepted form, which appears in both the generated
documentation and the refusal.

```python
from toolshape import bounded_list, identifier

Param("sites", "Site codes from list_sites.",
      validator=bounded_list(identifier(), cap=12))
```

Result shapes (`CONTRACT.md` §1): success `{columns, rows, scope}`,
`{refused, parameter, problem, accepted}`, `{error, detail}`,
`{duplicate, tool, scope, detail}`.

Build one by hand when the wrapper's coercion is not enough:

```python
from toolshape import table
return table(["site", "at"], rows, scope={"site": site}, note="capped at 500")
```

## Measure

Record calls, group them by turn:

```python
from toolshape import JsonlSink, set_sink, turn

set_sink(JsonlSink("results/calls.jsonl"))         # once, at startup

with turn(run_id="run-3", case_id="incident-7", split="held_out"):
    ...                                             # the agent's turn
```

`turn` also scopes the duplicate ledger. Outside a turn the guard is inert,
so tests and scripts are never suppressed.

Then score the surface:

```bash
python3 scripts/tool_report.py results/calls.jsonl \
    --outcomes results/outcomes.json \
    --out results/iteration_4
# -> TOOL_WEIGHT.md + tool_weight.json
```

`outcomes.json` is optional — a list of
`{"case_id": ..., "gates": {"detect": "pass"}, "split": ...}`. Without it
the usage and failure rates still compute; only the association columns are
omitted.

Reading the table:

| Signal | Change |
| --- | --- |
| High error | Shape the tool (G1) |
| High refusal | Narrow the type, enumerate, or name the source (G12, G15) |
| High duplicate | Populate `scope` (G10) |
| High empty | The query asks the wrong question |
| Low usage | Fix `call_when`, or delete |
| `noisy but associated` | Fix it. Do not cull (G2) |

**A flag is a hypothesis.** Confirm with the ablation protocol
(`CONTRACT.md` §6): unregister one tool, change nothing else, re-run
serially with at least three runs per case, and keep the removal only if
outcome gates hold **and** noise falls. Before culling a noisy tool, prefer
replacing it — that is what worked (G2).

Fewer than about ten observed calls is unmeasured, whatever the signal says
(G3).

## Worked surfaces, one per Azure data service

`examples/azure/` — each runs offline against a stand-in backend, with the
swap to a real client marked `# real:`. Copy the closest one and edit.

| File | Service | Shows |
| --- | --- | --- |
| `graph_gremlin.py` | Cosmos DB Gremlin | The 44%-error promotion: three shaped tools, no traversal text |
| `telemetry_kql.py` | Fabric Eventhouse / Data Explorer | Window validated as a pair; row cap injected, not asked for |
| `knowledge_search.py` | Azure AI Search | Why the per-hit projection cannot be defaulted |
| `ontology_gql.py` | Fabric GraphModel | Turning a 200-carrying-an-error into an error envelope |
| `documents_cosmos.py` | Cosmos DB NoSQL | Async tools; listing split from reading |

Each exports `ARCHETYPES`, the tool-to-card map the renderers consume.

## Render the results

`renderers/` is the operator-facing half: React cards over the same
envelope. Eight archetypes cover what tools return, so a new tool gets a
proper card by declaring its shape.

```bash
cp -r purpose-built-tools/renderers <your-app>/src/
```

```js
// tailwind.config.js — both lines, or the cards render unstyled (G17)
presets: [require("./src/renderers/tailwind-preset.cjs")],
content: ["./src/**/*.tsx"],
```

```tsx
import "./renderers/tokens.css";
import { resolveToolRenderer } from "./renderers";

const Renderer = resolveToolRenderer(toolName, ARCHETYPE_BY_TOOL);
if (!Renderer) { /* loud: this tool has no card yet */ }
<Renderer result={resultString} prominentColumns={["site", "kind"]} />
```

| Archetype | Envelope |
| --- | --- |
| `tabular` | `{columns, rows\|data, scope}` |
| `graph` | `{nodes, edges, summary}` or a node list |
| `search` | `{results: [{title, source, score, text}], count}` |
| `metrics` | `{metrics: [{label, value, unit}]}` or a scalar map |
| `document` | `{title, document\|text\|content\|body}` or plain text |
| `status` | `{status, message?, detail?}` |
| `action` | `{action, status?, simulated?}` |
| `multi-tabular` | `{tables: [{title, columns, rows}]}` — several tables in one result |

The three envelope states render differently on purpose — error red and
announced, refusal amber leading with the accepted form, duplicate muted.
A shape mismatch renders a bounded preview card, never a JSON dump.

`graph` lays out with `buildGraphLayout` (deterministic layered BFS — the
same nodes always draw the same picture, so a screenshot is comparable
across runs) and reports `danglingEdges` rather than dropping them
silently. `document` and `search` render through `MarkdownBody`, which
builds React elements and never HTML, and refuses `javascript:` and
`data:` URLs — tool output is untrusted text.

### Cards are resizable, and stay that way

A result card is a viewport onto an unbounded result. Twelve rows fit;
the four-hundred-row answer to the same question does not. So the card
body is resizable by default and remembers the height it was dragged to.

```tsx
<Renderer result={resultString} resizeKey={toolCall.name} />
```

`resizeKey` is the persistence identity: the dragged height is stored at
`localStorage["cardh:<resizeKey>"]` and restored on reload. Key it by
what should share a height — the tool name means every `list_assets`
card opens at the height you last chose; `` `${toolName}:${callId}` ``
makes each call independent. Omit it and the card still resizes, but
forgets.

Until it is dragged, the body is capped (`maxHeight` 320) and scrolls
internally. The first drag *releases the cap* and promotes the height
into state — without that, the handle moves and the card does not grow,
which reads as a broken control (G19).

A renderer that scrolls internally must yield its own height instead of
imposing one, or the card grows and the content stays in its old box:

```tsx
const { resizable } = useCardBody();          // from ToolResultCard
<div className={resizable ? "flex-1 min-h-0" : "max-h-80"}>
```

`ResultTable` already does this. Any custom body inside a card should
read `useCardBody()` rather than hard-coding a maximum (G20).

## Review the surface

```bash
python3 scripts/lint_surface.py mytools/tools.py --catalogue SURFACE.md
python3 scripts/lint_surface.py mytools/tools.py --strict     # CI
```

Errors: no purpose, no usable `call_when`, an undescribed parameter, a
`dedupe_on` key that is not a parameter, duplicate names. Warnings: an
unvalidated parameter, a description that does not name its value's source,
no `dedupe_on`, a surface wider than its budget.

It cannot check whether `call_when` is *true* or whether two tools actually
differ. That is the meter's job, and yours.

## Verify

```bash
python3 tests/selftest.py            # 227 checks, no test framework
python3 -m pytest tests/ -q          # edge cases
python3 examples/promote_raw_query.py
```

The example runs the same three questions through a raw tool and a shaped
tool over one backend, then scores both. It is also the round-trip test
between the halves.

## Troubleshoot

| Symptom | Entry |
| --- | --- |
| Malformed queries at a steady rate | G1 |
| Culling the noisy tool made scores worse | G2 |
| Signals flip between iterations | G3 |
| Cannot attribute an improvement | G4 |
| Unused tools still in the codebase | G5 |
| A new tool over-triggers and regresses | G6 |
| Error rate high, transcript looks fine | G7 |
| The most useful tool scores worst | G8 |
| Perfect numbers, no measured gain | G9 |
| The agent calls the same thing twice | G10 |
| Refusals repaired with the same mistake | G11 |
| Invented parameter values | G12 |
| A good tool flagged for culling | G13 |
| All calls valid, all results empty | G14 |
| Reasonable synonyms returning nothing | G15 |
| Numbers "prove" a tool is valuable | G16 |

## Remove

1. Replace `@purpose_built(spec)` with your SDK's decorator alone, moving
   validation into the body — or keep the specs and drop only measurement
   by leaving the default `NullSink` installed.
2. Delete `toolshape/`.
3. Delete the record files.

The only process-wide state is the record sink, a module-level variable
that dies with the process. The turn ledger is a context variable with no
persistence.
