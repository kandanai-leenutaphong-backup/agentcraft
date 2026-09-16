# Situation Detector

Canonical runtime owner extracted from `template_apps/shared` without changing battery
semantics. Both Investigation and Custom Optimizer import `situation_detector`.

Public API: `normalize_config`, `configuration_digest`, `selected_rules`,
`normalize_window`, `run_battery`, `run_battery_async`, `stream_battery`, and the
configuration/execution errors and event constants exported from the package.
The host supplies query execution, processing, configuration, time bounds and authorization.
Installation and import perform no remote calls. This package has no Azure or model dependency.

The [contract](src/situation_detector/README.md) preserves the original caller examples.
Offline acceptance from the repository root:

```bash
uv run --project libraries --package situation-detector --locked python -B -m unittest discover -s libraries/situation-detector/tests -v
```

Source provenance: template battery at Git `00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`.
App detector tests and the existing read-only Perth scan verify the installed consumer.
Cloud provisioning, model evaluation and registry publication are outside this migration.
