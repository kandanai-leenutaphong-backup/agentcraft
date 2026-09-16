# Situation Detector

Canonical domain-neutral battery owner. Both Investigation and Custom Optimizer
import `situation_detector`. Async execution defaults to at most eight concurrent
rules, offloads synchronous callbacks and joins owned tasks on cancellation/close.

Public API: `normalize_config`, `configuration_digest`, `selected_rules`,
`normalize_window`, `run_battery`, `run_battery_async`, `stream_battery`, and the
configuration/execution errors and event constants exported from the package.
The host supplies query execution, processing, configuration, time bounds and authorization.
Installation and import perform no remote calls. This package has no Azure or model dependency.

The [canonical contract](docs/skills/situation-detector.md) owns configuration,
callback/thread lifetimes, safe error codes and streaming semantics. The
[historical consumer examples](src/situation_detector/README.md) retain provenance.
Offline acceptance from the repository root:

```bash
uv run --project libraries --package situation-detector --locked python -B -m unittest discover -s libraries/situation-detector/tests -v
```

Source provenance: template battery at Git `00c76c6bb55190877c3d4d4b5b3a14e55bce2cb4`.
App detector tests verify installed consumer compatibility offline. Previously
recorded read-only Perth runs are historical evidence, not a live check of this
revision. Cloud reads, model evaluation and registry publication are not required.
