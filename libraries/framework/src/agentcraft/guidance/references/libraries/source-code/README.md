# Source Code Viewer

Public frontend import: `SourceCodeViewer` and `SourceCodeViewerProps` from
`@agentcraft/source-code`. React, lucide-react and Shiki are explicit host peers.
No Python dependency, source execution, network fetch or upload is introduced.

## Build And Install

From this package directory, using the declared React 19, Lucide and Shiki peers
and TypeScript 5.9 development toolchain (verified on Node 20.20.0):

```bash
npm install
npm run typecheck
npm test
npm pack
```

`prepack` emits ES2022 ESM, declarations and byte-identical CSS in `dist`.
Install the returned `agentcraft-source-code-0.1.0.tgz` with
`npm install <archive-path>` in the host. Local `file:` consumers build this package
first and use installed exports, not source aliases. Hosts own peer lockfiles
and release selection; no registry publication is implied.

The main import loads scoped CSS in CSS-aware ESM bundlers such as Vite.
`@agentcraft/source-code/styles.css` is also exported. A CSS-unaware Node loader
cannot load the styled barrel directly. No fonts or images are fetched by the
viewer. Keep one host React instance with linked development packages.

```tsx
import { SourceCodeViewer } from "@agentcraft/source-code";

export function SourcePreview({ code, path }: { code: string; path: string }) {
	return <SourceCodeViewer code={code} filename={path} startLine={1} maxHeight={320} />;
}
```

The [canonical contract](docs/skills/source-code.md) owns input bounds, safe text,
clipboard refusal and shared-highlighter lifetime. Package tests render emitted
JavaScript and check declarations/CSS; host builds and browser controls remain
separate integration checks.

Canonical source moved unchanged from `template_apps/shared` at baseline
`00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`. Both Investigation and Custom Optimizer
consume this package. Safe text rendering, stale-highlight cancellation, original line
numbers, clipboard feedback and wrapping preserve the existing component contract.

The component and stylesheet retain that baseline behavior; packaging now emits
JavaScript. Browser verification can use synthetic text and installed artifacts
without reading application sources or invoking any service/model.
