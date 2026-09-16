# Template Process Supervision

`agentcraft-template-foundations` now contains only `template_foundations.local_server`:
loopback port selection, child process groups and shutdown for the two local templates.
Each app owns its accepted configuration, module entry point and writable state location.
Runtime dependencies: none; implementation uses the Python standard library.

Reusable data, models, rule execution, auth, catalogue, source viewing and SSE framing
belong to [canonical libraries](../../libraries/README.md). Both apps import those packages
directly. No model re-export, raw Search client, publishing helper or source-viewer copy
remains here.

The two runtime files total 2,744 logical bytes, down from 20 files/80,423 bytes at baseline
`00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`. Tests cover local consumer binding; capability
tests live with their libraries or the app workflows they exercise.

Both app launchers use this same helper. Their runbooks own setup and verification:
[Investigation](../investigation_app/deploy/README.md),
[Custom Optimizer](../custom_optimizer/deploy/README.md).
Builds are reproducible; `build/`, `dist/` and bytecode are ignored and are not runtime owners.

Historical migration evidence and exact remaining boundaries:
[Investigation migration](../investigation_app/docs/LIBRARY_MIGRATION.md).