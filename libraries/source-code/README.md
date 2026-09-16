# Source Code Viewer

Public frontend import: `SourceCodeViewer` and `SourceCodeViewerProps` from
`@agentcraft/source-code`. React, lucide-react and Shiki are explicit host peers.
No Python dependency, source execution, network fetch or upload is introduced.

Canonical source moved unchanged from `template_apps/shared` at baseline
`00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`. Both Investigation and Custom Optimizer
consume this package. Safe text rendering, stale-highlight cancellation, original line
numbers, clipboard feedback and wrapping preserve the existing component contract.

Verification uses both existing frontend builds and real source-viewer controls in the
local Investigation app; no model call or cloud write is needed.
