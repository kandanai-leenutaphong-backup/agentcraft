---
name: source-code
description: "Use for a read-only React source-code viewer with Shiki syntax highlighting, line numbers, safe text rendering, wrapping, clipboard feedback and stale-highlight cancellation. No source is executed, uploaded or fetched by this component."
---

# Source Code Viewer

Import `SourceCodeViewer` from `@harness/source-code`; public source is
[frontend/index.ts](frontend/index.ts). Pass `code`, optional filename/language/start line,
height and truncation state. The host fetches and authorizes content. Rendered tokens are React
text, not injected HTML. Unsupported languages and highlight failures fall back to plain text.

React, Lucide and Shiki are declared dependencies. The viewer loads no application API or config.
Copy operates on the original code, reports clipboard refusal, and never silently rewrites source.
Wrap and highlight controls have accessible names; preserve readonly/truncated status in consumers.
The shared browser gate exercises copy, wrap, token rendering and mobile geometry.