# purpose-built-tools

Give a model a raw query interface and it will author queries. Some are
malformed, and every malformed one costs a turn and teaches it nothing.
Give it a narrow tool for the thing it actually needs and the malformed
call becomes **unrepresentable** — there is no syntax left to get wrong.

This box packages that move, and the meter that tells you when to make it.

Measured on a live agent: a raw graph-query tool ran at a **44% hard error
rate**. Deleting it made outcomes *worse* — it was doing real work some of
the time. Replacing it with three shaped tools over the same backend cut
error noise **75%** and recovered the outcomes.

Self-contained. The Python half has **no dependencies at all**; the optional
renderer half needs React and Tailwind.

```
purpose-built-tools/
  README.md            you are here — the argument and the design decisions
  SKILL.md             agent-facing: decide, install, use, measure, remove
  CONTRACT.md          exact shapes, schemas, thresholds, ablation protocol
  GOTCHAS.md           eighteen measured failures, symptom-first
  toolshape/           the mechanism (stdlib only)
    __init__.py          public surface
    _spec.py             ToolSpec — the affordance, declared once
    _validators.py       checks whose rejection message is the fix
    _envelope.py         the five result shapes, and their classification
    _decorator.py        @purpose_built — validate, dedupe, wrap, record
    _ledger.py           per-turn call ledger + the call-record sink
    _stats.py            the weight meter
    _catalogue.py        surface page + affordance lint
  renderers/           the operator-facing half (React, optional)
    ToolResultCard.tsx   the scaffold: scope / signal / body / note + 3 states
    ResultTable.tsx      preview cap, prominent columns
    archetypes/          seven shapes, seven cards, one registry
    tokens.css           every colour, as CSS variables
    tailwind-preset.cjs  maps the variables onto the class names used
  scripts/
    tool_report.py       score a surface from recorded calls
    lint_surface.py      check a surface against the affordance rules
  examples/
    promote_raw_query.py the whole argument, runnable, in one file
    azure/               one worked surface per Azure data service
  tests/
    selftest.py          227 checks, no framework, both halves round-tripped
    test_validators.py   validator and spec edge cases
```

---

## 1. The problem

A tool is not an API. It is an interface a fallible reasoner chooses from,
under uncertainty, with a limited attention budget, and its cost is paid on
every decision — not only when it is called.

Raw query access looks like the general solution. It is the expensive one:

| What the raw surface asks | What it costs |
| --- | --- |
| Author valid syntax in a formal grammar | A steady error rate no prompt fixes (G1) |
| Know the schema | Invented column and table names |
| Know the vocabulary | Plausible synonyms returning empty results (G15) |
| Bound the result | Whole-table reads into a context window |
| Interpret a parser error | A message about a token, not about the intent |

Every one of those failures consumes a turn and produces no information the
caller can act on. That is the actual cost of a raw tool: not that it is
dangerous, but that its failures are **unteachable**.

A purpose-built tool inverts each line. The caller states intent; the code
holds the syntax, the schema, the vocabulary and the bound. What remains
expressible is what is answerable.

## 2. What "purpose-built" means concretely

Five properties, each of which is a mechanism in this box, not a
convention:

**One declaration.** `ToolSpec` holds the purpose, the "when to call"
sentence, the parameters and their validators. The description the model
reads is *generated* from it, so a documented constraint is the enforced
constraint. The three artefacts that normally drift cannot.

**Refusals that teach.** Every validator carries the accepted form, and the
refusal quotes it: parameter, problem, accepted. That text is the only
feedback before the retry, so it is worth more than the same words in a
system prompt (G11).

**One result shape.** `{columns, rows, scope}` for everything. `scope`
echoes what was asked and always carries `row_count`, which is what turns
an empty result from an ambiguous non-answer into a definite one (G10).

**A memory of the turn.** Identical calls within a turn are answered from a
ledger with a result that says so, instead of re-querying the backend and
returning the same nothing.

**A record of every call.** Which makes the second half possible at all.

## 3. The second half: measure, then decide

Tool design without measurement is taste, and taste does not survive the
third tool. Every call emits a record; the meter turns records into a
per-tool table:

```
| tool          | calls | runs using | error | refused | dup | unproductive | signal |
| `run_query`   |    10 |    1 (50%) |   40% |      0% | 10% |          60% | review / cull candidate |
| `find_events` |     6 |    1 (50%) |    0% |     50% |  0% |           0% | ok |
```

That is real output from `examples/promote_raw_query.py`: the same backend
and the same three questions, asked both ways.

Each rate answers a different design question, which is why they are not
collapsed into one:

| Signal | What it means | What to change |
| --- | --- | --- |
| High **error** | The caller cannot form a valid call | Shape the tool. Prompting will not fix a grammar (G1) |
| High **refusal** | The caller cannot satisfy the validator | Narrow the type, enumerate the vocabulary, or name the value's source (G12, G15) |
| High **duplicate** | The result did not read as an answer | Populate `scope` (G10) |
| High **empty** | The tool asks the backend the wrong question | Fix the query, not the interface |
| Low **usage** | The caller never reaches for it | Fix `call_when`, or delete the tool |

## 4. The loop this exists to serve

```
shape a tool  ->  record every call  ->  measure weight
      ^                                        |
      |                                        v
   keep or revert  <-  ablate to confirm  <-  flag a hypothesis
```

Four rules, each learned the expensive way:

**One change per iteration.** Including removals. Two variables make the
accept-gate uninterpretable, and an uninterpretable result is not reusable
(G4).

**Replace before you cull.** A flagged tool is a hypothesis about *noise*,
never evidence about *value*. The 44%-error tool was ablated first, and
outcomes regressed; the shaped replacement is what worked (G2).

**Association is not causation.** Cases that reach for a tool are the cases
the caller already understands. Ablation is the only test (G16).

**Judge on the outcome gate.** Not adoption, not error rate. A tool posting
0% errors and 100% adoption was still reverted, because it moved cases from
failing to *partially* passing while raising overreach (G9).

## 5. Design decisions a reimplementation would get wrong

**Refusals are not "unproductive".** The obvious aggregate is "everything
that wasn't a useful result", and it flags well-shaped tools for culling
because their guardrails are working. A refusal hands the caller a specific
next step; an error hands it nothing. `unproductive_rate` covers error,
empty and missing; `turn_cost_rate` reports the wider measure, and only the
narrow one may justify a removal. This box's own worked example was the
first thing to trip it (G13).

**"Missing" is not "empty".** A call with no recorded result and a call
that returned zero rows are different events. Merging them poisons every
rate in the table, and it happens on the first iteration run without
transcripts (G7).

**A truncated payload is productive.** Truncation only happens to results
too large to transmit, which are by definition non-empty. Classifying
unparseable as empty makes the most useful tool look like the worst one
(G8).

**Only the first validation failure is reported.** A caller repairing one
problem at a time converges. Given five, it rewrites the call and
introduces a sixth.

**The dedupe guard is inert outside a turn.** Tests, scripts and one-off
invocations must never be suppressed, so with no ledger installed the guard
returns False and behaves as if absent.

**Call records carry no argument values.** Only the tool name, the outcome
class and the timing. An analysis artefact full of caller data becomes a
data-handling problem, and the meter does not need it.

**Tools should return facts, not conclusions.** The tools that survived
here resolve a name to a code, list what exists, return events in a window.
The ones reverted classified, diagnosed or decided — and were wrong exactly
where judgement mattered (G6).

## 5a. One shape, three consumers

The envelope is not an implementation detail — it is the contract three
audiences read:

| Consumer | Reads | Lives in |
| --- | --- | --- |
| The model | the generated description, then the result | `toolshape/_spec.py` |
| The meter | the result class of every call | `toolshape/_stats.py` |
| The operator | the card | `renderers/` |

`renderers/` is the third. Seven archetypes — `tabular`, `graph`, `search`,
`metrics`, `document`, `status`, `action` — cover what tools return, so the
Nth tool gets a proper card by declaring its shape rather than by someone
writing a component. Critically, the three envelope states look *different*:
error is red and announced, a refusal is amber and leads with what would be
accepted, a duplicate is muted. Collapsing them tells an operator that a
working guardrail is a fault (G13).

There is no raw-JSON fallback. A shape mismatch renders a bounded card
naming the archetype with a capped preview — loud enough to notice, small
enough not to flood the transcript. A JSON dump "renders", and therefore
never gets fixed.

See [renderers/README.md](renderers/README.md). React and Tailwind, and
nothing else; the Python half stays dependency-free.

## 5b. One worked surface per Azure data service

`examples/azure/` shows the shape against the five backends this pattern
was proven on. Each runs offline against a stand-in backend, with the
one-line swap to a real client marked `# real:`.

| Example | Service | Tools | Archetypes |
| --- | --- | --- | --- |
| `graph_gremlin.py` | Cosmos DB Gremlin | `graph_node`, `graph_neighbours`, `graph_summary` | tabular, graph |
| `telemetry_kql.py` | Fabric Eventhouse / Data Explorer | `find_events`, `summarise_metric` | tabular, metrics |
| `knowledge_search.py` | Azure AI Search | `search_knowledge` | search |
| `ontology_gql.py` | Fabric GraphModel | `query_ontology` | tabular |
| `documents_cosmos.py` | Cosmos DB NoSQL | `list_documents`, `read_document` | tabular, document |

Each carries the specific lesson of its backend: the Gremlin trio is the
44%-error promotion itself; the KQL example shows the window validated as a
*pair*; the search example shows why the per-hit projection cannot be
defaulted; the GQL example converts a 200-carrying-an-error into an error
envelope; the Cosmos example splits listing from reading so neither is
forced into the wrong card.

## 6. What this is not

* **Not an agent framework.** It does not register anything with an SDK.
  Apply your SDK's decorator outside `@purpose_built`; they compose.
* **Not an evaluation harness.** It consumes outcomes; it does not produce
  them. How a task is graded is yours.
* **Not a security boundary.** Validators bound what reaches a backend and
  are worth having, but a read-only identity is the actual guarantee.
* **Not a replacement for raw access.** Keep a raw tool for the long tail —
  on a separate, wider surface, and expect it to look bad in the table.
* **Not a client library.** The Azure examples ship stand-in backends and a
  marked one-line swap; connecting is somebody else's job.

## 7. Verify it works here

```bash
python3 tests/selftest.py                        # 227 checks, no framework
python3 examples/promote_raw_query.py            # the argument, end to end
python3 examples/azure/telemetry_kql.py          # one service, worked
python3 scripts/lint_surface.py examples/promote_raw_query.py
```

The selftest drives tools built with the shaping half through a scripted
caller and asserts on what the measuring half reports. Testing either half
alone proves nothing about the contract between them, which is where a
rewrite drifts.

It also gates the contract between the tool layer and `renderers/`: every
declared archetype resolves to a component, is wired into the registry, and
appears in `CONTRACT.md`. That check runs with no Node toolchain — the
link between a Python tool and a React card is a string, and a string link
needs a test (G18).

## 8. Removal

Nothing is registered globally and no import is patched.

1. Replace `@purpose_built(spec)` with your SDK's decorator alone, and move
   the validation into the body — or leave the specs and delete only the
   measurement by installing `NullSink` (the default).
2. Delete `toolshape/`.
3. Delete the record files.

The only process-wide state is the record sink, a module-level variable
that resets to `NullSink` and dies with the process. The turn ledger is a
context variable with no persistence.
