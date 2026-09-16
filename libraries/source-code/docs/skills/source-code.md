# Source Code Viewer

Owner: installed `@agentcraft/source-code`. Public API: `SourceCodeViewer` and
`SourceCodeViewerProps`; [package guide](../../README.md).

Pass source text and optional filename, language, original start line, height and
truncation state. The host fetches and authorizes content and sets input and display
bounds. The viewer does not execute, fetch or upload source, read application
configuration, or infer permission from installation.

React, Lucide and Shiki are explicit host peers. Highlighted tokens render as React
text, never injected HTML. Unknown languages and highlight failures fall back to
plain text; stale asynchronous highlights cannot replace newer source. Copy uses
the original source and reports clipboard refusal. Preserve readonly and truncated
status in consumers and accessible names on wrap and highlight controls.

Lifecycle is React-owned. Unmount/source changes suppress stale result commits;
they do not interrupt an in-progress Shiki operation. The shared highlighter lives
for the module lifetime. Hosts bound source bytes and workload; `maxHeight` bounds
display, not memory or CPU. No network client, credential lifecycle, persistence
or automatic retry is introduced.

The package owns `npm run typecheck`, `npm test`, `npm run build` and `npm pack`.
Packed output includes ES2022 ESM, typed exports and scoped CSS. The styled barrel
expects a CSS-aware bundler; `./styles.css` is also exported. Package tests render
compiled code as safe text and check line/truncation state and CSS integrity.
Installation and consumer examples live in the package README. Browser controls
are separate from those static checks.

## Skill Retirement, 2026-09-16

Decision: reuse the existing library without changing its runtime. The native
`source-code` name and trigger description remain. The Microsoft MIT notice is
retained in the skill and copied to the library's `LICENSE`.

Exact retired paths relative to `.github/skills/source-code/`:

| Retired path | Replacement |
| --- | --- |
| `frontend/SourceCodeViewer.tsx` | `libraries/source-code/frontend/SourceCodeViewer.tsx` |
| `frontend/index.ts` | `libraries/source-code/frontend/index.ts` |
| `frontend/source-code.css` | `libraries/source-code/frontend/source-code.css` |
| `package.json` | Installed `@agentcraft/source-code`; `@harness/source-code` retired |

All three frontend files were checked against pre-retirement Git blobs. That is
historical provenance, not byte identity after ESM import emission changes.
Parent owns shared discovery; this package owns current build metadata and guide.