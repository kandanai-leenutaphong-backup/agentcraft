---
name: hyperframes-motion
description: "Use for deterministic silent HTML-to-video authoring with HyperFrames: finite CSS timelines, local assets, beat sampling and verified repeat-render evidence."
---

# HyperFrames Motion

Use `@agentcraft/hyperframes-tools`: `composition`, `parseAtTimestamps`, `configuration`,
`validate`, `runtimeFacts`, `runAllowed`; CLI `hyperframes-tools`. Read the canonical
[authoring guide](../../../libraries/hyperframes-tools/GUIDE.md) and
[installation and verification](../../../libraries/hyperframes-tools/README.md).

Core validation requires Node 20.20+ and declared `parse5`; native execution additionally requires
explicit Node 22+/HyperFrames 0.8.12/media runtime and Chromium for browser gates. Engine stays upstream.
Require sized direct-body roots, finite seek-safe motion, local assets and pre-authored beat samples.
Render/browser installation needs explicit approval. Preserve lint/check/snapshot/probe/repeat-render
evidence; report blocked gates. Adapter checks are not an OS sandbox or cloud authorization.