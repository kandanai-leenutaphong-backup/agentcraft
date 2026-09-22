# renderers — the operator-facing half

React cards for the tool result envelope. Same shapes the tool layer emits
and the weight meter counts; nothing here re-derives them.

Seven archetypes cover what tools actually return, so the Nth tool gets a
proper card without the Nth bespoke component — and never falls through to
a raw-JSON dump.

| Archetype | Envelope | Card |
| --- | --- | --- |
| `tabular` | `{columns, rows\|data, scope}` | Scrollable table, preview cap, prominent columns |
| `graph` | `{nodes, edges, summary}` or a node list | Node/edge chips + union-keyed table |
| `search` | `{results: [{title, source, score, text}], count}` | Stacked hit cards |
| `metrics` | `{metrics: [{label, value, unit}]}` or a scalar map | Metric grid |
| `document` | `{title, document\|text\|content\|body}` or plain text | Scrollable prose |
| `status` | `{status, message?, detail?}` | Status chip + lines |
| `action` | `{action, status?, simulated?}` | Action chip + simulated banner |

Three envelope states short-circuit the card in every archetype, and they
look different on purpose:

| State | Appearance | Why |
| --- | --- | --- |
| `{error: true, detail}` | Red, `role="alert"` | The tool could not answer |
| `{refused: true, ...}` | Amber, leads with what would be accepted | The guardrail worked — not a fault |
| `{duplicate: true, ...}` | Muted | The answer is already in the transcript |

Collapsing those into one red banner is the mistake this set exists to
prevent: an operator reads a working refusal as a failure and starts
debugging a tool that is behaving correctly.

## Install

Use `@agentcraft/modular-agents@0.2.0` from a reviewed npm artifact, with one host React 19
instance. [Package metadata](../../../package.json) owns exports and peers; the
[package guide](../../../README.md) owns build/install prerequisites. Do not copy renderers.

For the Tailwind archetypes, both wiring steps are required:

```js
// tailwind.config.js
module.exports = {
  presets: [require("@agentcraft/modular-agents/tailwind-preset")],
  content: ["./src/**/*.tsx", "./node_modules/@agentcraft/modular-agents/modules/purpose-built-tools/renderers/**/*.tsx"],
};
```

```ts
// your entry point, before your own stylesheet
import "@agentcraft/modular-agents/styles";
```

Override `--tool-*` variables in a later stylesheet to restyle cards.

Plain-CSS hosts using `ToolResultCard` can instead import
`@agentcraft/modular-agents/card-styles`. Every rule is scoped to `.tool-result-card`;
no Tailwind reset or global tokens are installed. Variable fallbacks supply the default
palette. This styles the scaffold and envelope banners, not every archetype's body.

### Card Composition

`ToolResultCard` retains these defaults: no header or band labels; scope, signal, note,
then body; `noteTone="warning"`; omitted signal tone means `accent`; `resizable=true`
with a 96px minimum, initial 320px maximum and optional `cardh:${resizeKey}` persistence.
Direct `error`, `refusal` and `duplicate` props still replace the normal card in that order.
Envelope helpers choose refusal, duplicate, then error before passing those props.

Opt-in host presentation:

| Prop | Behavior |
| --- | --- |
| `header` | React identity/header content, above every card mode |
| `bandLabels={{scope, result}}` | Labeled scope band and a shared signal/body band; signal value precedes its label |
| `notePosition="before-signal"` | Advisory between scope and results; default `after-signal` |
| `scopeLabel`, `signalLabel` | Accessible names for the definition list and signal list |
| `resizable={false}` | Natural body, no height observer or storage; nested tables retain their own caps |
| `className`, `classNames={{scope, signal, note, body}}` | Host theme and stable selector slots; no additional card wrapper |

The Investigation host supplies domain identity, Inputs/Results labels, advisory policy,
signal values and tone mapping. It deliberately disables card-body resize.

`projectObjectRow(columns, row)` projects an object in declared column order without
formatting or mutation. Missing fields remain `undefined`; duplicate columns remain duplicate.
Array/scalar fallback and float formatting remain caller policy, not part of this helper.

## Use

```tsx
import { getArchetypeRenderer, resolveToolRenderer } from "@agentcraft/modular-agents";

// Directly, when you know the shape:
const Table = getArchetypeRenderer("tabular")!;
<Table result={resultString} prominentColumns={["site", "kind"]} />

// Or through a tool -> archetype map, which is what a transcript does:
const ARCHETYPE_BY_TOOL = { find_events: "tabular", graph_summary: "graph" };
const Renderer = resolveToolRenderer(toolName, ARCHETYPE_BY_TOOL);
if (!Renderer) { /* loud: this tool has no card yet */ }
```

Keep `ARCHETYPE_BY_TOOL` next to the tool declarations — each
[Azure example](../examples/azure) exports this map as `ARCHETYPES`, and the
box's selftest asserts every value is a real archetype key so a rename
fails the build instead of orphaning a tool.

`DocumentRenderer` renders markdown as wrapped preformatted text, because
this set takes no markdown dependency. Pass your own:

```tsx
<DocumentRenderer result={r} renderBody={(md) => <Markdown>{md}</Markdown>} />
```

`ResultTable({headers, rows, previewRows=5, prominentColumns, maxHeightClass="max-h-64"})`
accepts `string[]` headers and `unknown[][]` rows. Pass `rows.length` to show all supplied
rows initially; prominent columns hide metadata until toggled. This is presentation,
not a query limit, fetch, authorization or model call. The
[Investigation caller](../../../../../template_apps/investigation_app/app/cybereye/frontend/src/shared/agent-output/ToolRender.tsx)
adapts the domain response to these public props. Empty/error/refused states remain distinct
at the owning envelope renderer; a cell is text, not executable content.

## Files

```
renderers/
  index.ts                 public surface
  ToolResultCard.tsx       the scaffold: scope / signal / body / note + 3 states
  ResultTable.tsx          table primitive: preview cap, prominent columns
  helpers.ts               parse, format, envelope-state extraction
  tokens.css               every colour, as CSS variables
  tailwind-preset.cjs      maps the variables onto the class names used
  archetypes/
    _common.tsx            shared props, unresolved + empty states
    index.ts               the registry
    TabularRenderer.tsx  GraphRenderer.tsx     SearchRenderer.tsx
    MetricsRenderer.tsx  DocumentRenderer.tsx  StatusRenderer.tsx
    ActionRenderer.tsx
```

## What is deliberately absent

* **No raw-JSON fallback.** A shape mismatch renders `ArchetypeUnresolved`:
  a bounded card naming the archetype with a 180-character preview. Loud
  enough to notice, small enough not to flood the transcript. A JSON dump
  "renders" and therefore never gets fixed.
* **No markdown, icon or date library.** React is the only dependency.
* **No per-tool components.** Those belong in your app. The archetypes are
  the floor, so the floor is never raw JSON.

## Verify

The box's Python selftest gates the contract between the tool layer and
this directory: every archetype key in `archetypes/index.ts` has a matching
file, appears in `CONTRACT.md`, and is used by an example — and every
archetype an example declares exists here. It runs with no Node toolchain.

The [installed UI receipt](../../../../framework/distribution/mobile-ui.json) records
selected renderer/browser checks; Investigation's
[signed offline task](../../../../../template_apps/investigation_app/deploy/README.md#offline-native-browser)
proves its actual caller. These are reused receipts, not tests rerun for this edit.
Missing styling: check preset content globs and the public stylesheet import before
changing renderers. Unmount releases presentation state; the host retains data and owns
any requests. No provider, artifact or user-data cleanup is performed by a renderer.
