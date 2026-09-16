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

```bash
cp -r purpose-built-tools/renderers <your-app>/src/
npm install react                      # ^18, already present in most apps
```

Two wiring steps, both required or the cards render unstyled:

```js
// tailwind.config.js
module.exports = {
  presets: [require("./src/renderers/tailwind-preset.cjs")],
  content: ["./src/**/*.tsx"],          // must cover src/renderers
};
```

```ts
// your entry point, before your own stylesheet
import "./renderers/tokens.css";
```

Override any `--tool-*` variable in a later stylesheet to restyle every
card. There is no other colour in the set.

## Use

```tsx
import { getArchetypeRenderer, resolveToolRenderer } from "./renderers";

// Directly, when you know the shape:
const Table = getArchetypeRenderer("tabular")!;
<Table result={resultString} prominentColumns={["site", "kind"]} />

// Or through a tool -> archetype map, which is what a transcript does:
const ARCHETYPE_BY_TOOL = { find_events: "tabular", graph_summary: "graph" };
const Renderer = resolveToolRenderer(toolName, ARCHETYPE_BY_TOOL);
if (!Renderer) { /* loud: this tool has no card yet */ }
```

Keep `ARCHETYPE_BY_TOOL` next to the tool declarations — each Azure example
in `examples/azure/` exports exactly this map as `ARCHETYPES`, and the
box's selftest asserts every value is a real archetype key so a rename
fails the build instead of orphaning a tool.

`DocumentRenderer` renders markdown as wrapped preformatted text, because
this set takes no markdown dependency. Pass your own:

```tsx
<DocumentRenderer result={r} renderBody={(md) => <Markdown>{md}</Markdown>} />
```

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

Rendering itself is verified in your app, against your React version. There
are no shipped component tests, because a test that has never run in your
environment proves nothing about it.
