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

Lifecycle is React-owned; stale work is cancelled by the component. No network
client or credential lifecycle is introduced. No standalone library selftest is
declared; source equivalence verifies this retirement, not an unperformed browser
journey.

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

All three frontend files are checked against their pre-retirement Git blobs.
Parent integration owns application imports, shared discovery and package metadata.