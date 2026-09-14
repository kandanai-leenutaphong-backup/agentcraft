---
name: situation-detector
description: "Use when configurable query-test rules must run over explicit time windows and produce ordered observations, stable configuration digests, or streamed results. Includes a domain-neutral synchronous/asynchronous battery and refusal tests. Hosts provide queries and processing; this skill executes no configuration-supplied code itself."
---

# Situation Detector

Install the package from this directory into the consuming environment; import `situation_detector`.
The [complete API contract](python/situation_detector/README.md) and source travel with the skill.
The host owns data access, caller authorization, domain rules, bounds and processing. Configuration
is data; the battery passes opaque queries/processing to injected callbacks and imports no application.

Use `normalize_config`, `configuration_digest`, `selected_rules`, `normalize_window`, `run_battery`,
`run_battery_async` or `stream_battery`. Input windows are validated but passed to callbacks unchanged;
results carry normalized ISO timestamps. Failures raise named errors, never empty successful detection.

Resolve `SKILL_ROOT` from the loaded file. Verify with
`PYTHONPATH="$SKILL_ROOT/python" python3 -m unittest discover -s "$SKILL_ROOT/tests" -q`.
The sixteen copied tests cover refusal paths, ordering, time-window bounds and an unrelated consumer.
No live source, credentials, deployment or model is needed. The application-specific examples in the
retained source contract are historical provenance, not an installation prerequisite.