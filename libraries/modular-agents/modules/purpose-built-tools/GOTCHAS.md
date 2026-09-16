# GOTCHAS.md — purpose-built-tools

Failures that cost real iterations. Most were measured on a live agent, not
theorised. Symptom first, because that is how you will arrive here.

Numbers are stable. Code comments cite them; a citation with no entry fails
`validate_box.py`.

---

## G1 — The model keeps writing malformed queries

**Symptom.** A raw query tool shows a high hard-error rate — measured at
**44%** on a live agent. The transcript is full of syntactically invalid
queries, each burning a turn. Every prompt revision helps for a week.

**Cause.** The tool asked the caller to author a formal language. There is
no prompt that makes a language model reliably emit valid syntax for a
grammar it cannot check, and the failure teaches it nothing: a parser error
names a token, not the intent that was wrong.

**Fix.** Move the syntax into code. A tool taking `site`, `start`, `end`
composes the same query with no grammar exposed, and the malformed call
becomes unrepresentable. Replacing one raw graph tool with three shaped
ones over the same backend cut error noise **75%**.

**Rule.** If the caller can express something invalid, it eventually will,
at a rate no prompt fixes. Narrow the type instead.

---

## G2 — You remove the noisy tool and the scores get worse

**Symptom.** The meter flags a tool with a 44% error rate. You unregister
it, re-run, and held-out outcomes **drop**.

**Cause.** The tool was doing real work in the 56% of calls that succeeded.
Error rate measures noise, not value, and a high-noise tool can still be
the only route to some answers.

**Fix.** Do not cull a flagged tool as the first move — **replace** it.
Build the shaped tool that covers the same need, register it, confirm the
outcomes hold, and only then remove the raw one. That sequence is what
worked here: ablation alone was rejected, ablation-then-replacement was
accepted.

**Rule.** A flag is a hypothesis about noise. It is never on its own
evidence about value.

---

## G3 — The signal column says "cull" for a tool you know is good

**Symptom.** A tool with two calls in one run is labelled a review
candidate. The next iteration labels it strong. Nothing changed.

**Cause.** One run per case is not evidence. Rates over a handful of calls
swing wildly, and the outcome association has an unused arm of one.

**Fix.** At least **three runs per case**, run **serially** — parallel runs
against one agent session interfere with each other. Treat any tool with
fewer than about ten observed calls as unmeasured, whatever the column
says.

**Rule.** The meter reports what it saw. It cannot report that it saw too
little; you have to know that.

---

## G4 — The iteration improved something and you cannot say what

**Symptom.** An iteration adds a tool, rewrites a prompt and adjusts a
threshold. Scores move. The next iteration undoes part of it and scores
move again, in an unrelated direction.

**Cause.** More than one variable changed, so the accept-gate compares two
populations that differ in several ways. Nothing is attributable and
nothing is safely reusable.

**Fix.** One general change per iteration, including removals. It feels
slow and it is the only thing that makes the result mean anything.

**Rule.** The accept-gate is only interpretable when exactly one thing
moved.

---

## G5 — A tool nobody uses is still in the codebase

**Symptom.** A surface reset cuts an agent to three tools. Months later
four compound tools are still present, imported, tested and maintained.
None is registered to any agent.

**Cause.** Tools are added one at a time and reviewed one at a time. Nobody
re-reads the set, so the set only grows.

**Fix.** Render the catalogue and read it as a page —
`scripts/lint_surface.py --catalogue`. Anything absent from every agent's
registration is dead: delete it, do not "keep it in case". `ToolSpec.replaces`
records which raw surface a shaped tool superseded, so the redundant one is
visible instead of merely unused.

**Rule.** An unregistered tool costs review time and ships. It is not free
because it is unreachable.

---

## G6 — The clever new tool made things worse

**Symptom.** A tool built to detect a specific composite condition
over-triggers on a superficially similar one. Overreach failures nearly
double. The iteration is reverted.

**Cause.** The tool encoded a *conclusion* rather than a *capability*. It
answered "is this happening" instead of "what is the value", so its
judgement was wrong in exactly the cases where judgement mattered.

**Fix.** Build tools that return facts and let the caller conclude. The
tools that survived here resolve a name to a code, return the events in a
window, list the equipment at a site. The ones reverted classified,
diagnosed or decided.

**Rule.** A general tool that returns a fact beats a specific tool that
returns an opinion. Narrow the *inputs*, not the *question*.

---

## G7 — A tool's error rate is high and its transcript looks fine

**Symptom.** The meter reports errors for calls whose results were clearly
delivered, or for an entire iteration that ran without transcripts.

**Cause.** A call with no result recorded was classified as an empty
result. "No output was captured" and "the answer is nothing" are different
events, and merging them poisons every rate in the table.

**Fix.** `missing` is its own class. Usage still counts; the failure rates
for that run are simply unknown, which is the honest answer.

**Rule.** Absence of measurement is not measurement of absence.

---

## G8 — Big results are counted as failures

**Symptom.** The most useful tool in the set has the worst unproductive
rate. Its results are large.

**Cause.** The transport truncates oversized payloads, the truncated JSON
does not parse, and the classifier treated unparseable as empty.

**Fix.** A truncated payload is **productive** — truncation only happens to
results too large to send, which are by definition non-empty. `classify`
takes `Ellipsis` as the truncation sentinel and says so.

**Rule.** When the measurement disagrees with the transcript, suspect the
classifier before the tool.

---

## G9 — A tool with perfect numbers is still not worth keeping

**Symptom.** A new fact tool posts a 0% error rate and 100% adoption. It is
reverted anyway.

**Cause.** Adoption measures whether the caller likes a tool. It says
nothing about whether the run succeeded. That tool moved cases from failing
to *partially* passing, and giving the caller more to work with also raised
its overreach — the accept-gate saw no net gain.

**Fix.** Judge on the outcome gate, never on adoption or error rate alone.
Both of those are diagnostics for *why* a tool is not working, not evidence
that it is.

**Rule.** A tool everyone calls and nobody benefits from is the most
expensive kind, because its usage makes it look essential.

---

## G10 — The caller keeps making the same call twice

**Symptom.** A high duplicate rate. The caller issues an identical call
seconds after receiving a perfectly good result.

**Cause.** The result did not read as an answer. Almost always a missing
scope block: `rows: []` with no context is indistinguishable from a failed
attempt, so the caller retries to find out which it was.

**Fix.** Populate `scope` on every result, including empty ones —
`{"site": "SITE_A", "start": ..., "row_count": 0}` says *this question was
asked and the answer is nothing*. Set `dedupe_on` so a repeat is answered
from the ledger with a result that says so explicitly.

**Rule.** A duplicate call is a defect in the previous result, not in the
caller.

---

## G11 — The caller repairs a refused call by making the same mistake

**Symptom.** A refusal is followed by a near-identical retry, then another.
The refusal message was accurate.

**Cause.** It said what was wrong and not what would work. "Invalid site"
leaves the caller guessing at the format; it guesses the same way twice.

**Fix.** Every refusal carries `accepted` — the form that would be taken,
with an example. The validators here cannot be written without it: the
field is a constructor argument, not an afterthought.

**Rule.** The rejection message is the only training signal the caller gets
before its retry. Spend words there before spending them in the prompt.

---

## G12 — The caller invents plausible values

**Symptom.** A parameter receives values that look right and match nothing:
a prose place name where a code was wanted, an ID in the wrong format.
Results are empty rather than refused, so nothing is learned.

**Cause.** The parameter description said what the value *means* and not
where it *comes from*. With no source named, the caller synthesises one
from the conversation.

**Fix.** Name the source in the description: "the code returned by
`list_sites`". The linter warns when a description contains no source
phrasing.

**Rule.** Every identifier a tool accepts should be obtainable from another
tool, and the description should say which.

---

## G13 — A tool is flagged for culling because its guardrails work

**Symptom.** A well-shaped tool with zero errors is labelled a review
candidate. Its refusal rate is high because the caller keeps hitting a cap
it then respects.

**Cause.** Refusals and duplicates were counted as "unproductive" alongside
errors and empties. But a refusal hands the caller a specific next step and
a duplicate points at an answer it already has; neither is a dead end. This
box's own worked example was the first thing to trip it.

**Fix.** `unproductive_rate` covers error, empty and missing only.
Refusals and duplicates are reported separately, roll into `turn_cost_rate`,
and produce advisories rather than cull flags.

**Rule.** Cost and waste are different measurements. Only waste justifies
removal.

---

## G14 — Every call is valid and every result is empty

**Symptom.** A run of well-formed calls returning nothing at all, with no
error anywhere and no indication of why.

**Cause.** Two individually valid parameters that are jointly wrong —
classically a reversed time window. Each passes its own check; the query is
syntactically perfect; the result set is necessarily empty.

**Fix.** Cross-parameter checks (`time_window`) that run after the
per-parameter pass and refuse the combination. `ToolSpec.cross_checks`
exists only for this.

**Rule.** A validator that only sees one parameter cannot catch a mistake
that lives between two.

---

## G15 — A free-text parameter that is really an enumeration

**Symptom.** A `kind` or `category` parameter receives a steady stream of
reasonable synonyms — `fault` for `trip`, `warning` for `alarm` — each
returning an empty result.

**Cause.** The parameter's type is `str`, so every string is legal. The
caller cannot discover the vocabulary from a description that does not
contain it, and an empty result does not distinguish "wrong word" from "no
such events".

**Fix.** `one_of(...)`. The refusal lists every legal value, so one wasted
call teaches the entire vocabulary.

**Rule.** If a parameter has fewer than about twenty legal values,
enumerate them. It is the highest-yield change available.

---

## G16 — The numbers prove a tool is valuable, and they do not

**Symptom.** Cases using a tool pass at 80%, cases not using it at 40%.
Removing the tool changes nothing.

**Cause.** Confounding. The tool is reached on the cases the caller already
understands well enough to know it is relevant. The association is real and
the causal claim is not.

**Fix.** Treat association as a flag only. The causal test is ablation:
remove one tool, change nothing else, re-run at least three runs per case,
and keep the removal only if outcomes hold **and** noise falls. Protocol in
`CONTRACT.md` §6.

**Rule.** The meter narrows where to look. Only an experiment decides.

---

## G17 — Every card renders unstyled after you copy the renderers

**Symptom.** The cards appear as unstyled stacked text: no borders, no
chips, no colour. The components are clearly mounting, and the Tailwind
config looks correct.

**Cause.** One of two things, and both look identical. Either the token
stylesheet was never imported, so `--tool-*` resolves to nothing; or the
renderer directory is missing from Tailwind's `content` globs, so Tailwind
sees no usage of `bg-neutral-bg3` and friends and purges every one of them.
The second is the nastier: the build succeeds, the config names the preset,
and the classes are simply not in the output CSS.

**Fix.** Both steps, together:

```js
// tailwind.config.js
presets: [require("./src/renderers/tailwind-preset.cjs")],
content: ["./src/**/*.tsx"],           // must cover src/renderers
```

```ts
import "./renderers/tokens.css";        // before your own stylesheet
```

Confirm with devtools: a card element carrying `bg-neutral-bg1` with no
background rule means purge; a background rule resolving to nothing means
the stylesheet.

**Rule.** A component library styled by utility classes ships three things,
not one: the components, the token values, and the build configuration that
keeps the classes alive.

---

## G18 — A tool renders as raw JSON after a rename

**Symptom.** One tool's results stop getting a card and fall back to a JSON
dump, or to the unresolved preview. Nothing about that tool changed.

**Cause.** Its declared archetype key no longer resolves — an archetype was
renamed, or the tool's entry was dropped from the tool-to-archetype map.
The link is a string, so nothing failed at build time.

**Fix.** Keep the map next to the tool declarations (each example exports
`ARCHETYPES`), and assert it. The selftest checks that every declared key
resolves to a component, is wired into the registry, and appears in
`CONTRACT.md` §8 — so a rename fails the test run rather than shipping.

**Rule.** Any link expressed as a string between two artefacts needs a test
that resolves it. "It renders" is not evidence that it renders correctly.

## G19 — The resize handle moves and the card does not grow

**Symptom.** The grip in the corner of a result card drags, the cursor
follows it, and the card stays exactly the height it was. Releasing does
nothing. It reads as a dead control.

**Cause.** The body carries a `maxHeight` cap so an unbounded result
cannot take over the transcript. CSS `resize` changes the element's own
height, but the cap still wins, so the drag has no visible effect.

**Fix.** Observe the drag and promote the result into state: a
`ResizeObserver` on the body writes the dragged height and *releases the
cap* once the user has expressed a height. The cap governs the default,
not the choice.

**Rule.** A control that a user can move must change something the user
can see, on the first attempt. A constraint that silently outranks direct
manipulation is a bug even when every individual rule is correct.

## G20 — The card grows but the content stays in its old box

**Symptom.** After dragging a card taller, the table inside keeps its
original height and leaves dead space below it — the card is bigger and
shows no more rows.

**Cause.** The inner renderer sets its own maximum (`max-h-80`) and
scrolls inside that. Growing its container cannot help, because the
content never asked for the extra room.

**Fix.** Inner bodies read `useCardBody()` and, when `resizable`, size
with `flex-1 min-h-0` instead of a fixed maximum — yielding their height
to whatever the card was given.

**Rule.** Height belongs to exactly one element in a stack. When an outer
element becomes resizable, every inner element that had its own maximum
has to give it up, or the two constraints disagree and the tighter one
wins invisibly.
