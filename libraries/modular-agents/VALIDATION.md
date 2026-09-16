# Selected Modular Validation

Native test interpreter: Python 3.11.14 in a temporary environment, with
`agent-framework-core==1.18.0`, `agent-framework-openai==1.14.3`, `openai==3.13.0`.
Canonical `llm-interface` and `modular-agents` installed as normal distributions.

| Check | Observed Result |
| --- | --- |
| Configuration module `tests/selftest.py` | All checks passed: prompts, specs, merge/import/path refusal |
| Tool module `tests/selftest.py` | All checks passed: validators, records, measurement, synthetic Azure examples, renderer contracts |
| `tests/test_definition.py` | 7 passed |
| `tests/test_packaging.py` | 7 passed: host-only bundle, immutable read-back, dependency/source/grant/tamper refusals |
| `tests/test_runtime.py` | 8 passed: exact native request/tool counts, owner refusal, HTTP, sanitized failure, cancellation, budget, policy/lifetime |
| `tests/test_portability.py` with `PYTHONPATH` unset | 4 passed, including a real localhost socket over the extracted host bundle |
| `examples/offline.py` | 1 measured fixture-tool call, 0 model calls, bundle read-back and unknown-tool refusal |
| Thin skill frontmatter/link check | Passed |
| Post-retirement `tests/selftest.py` | All 7 offline acceptance commands passed |
| Python 3.12.3 installed profile `tests/selftest.py --copy-out` | All 7 commands passed outside the checkout, `PYTHONPATH` unset |
| Retained `test_validators.py` on Python 3.12.3 | 54 passed |
| `npm run build` | Vite 7.3.6 ESM plus TypeScript declarations passed for 17 retained renderer modules |
| Local npm pack | Built exports, retained source, stylesheet/preset and notices packaged; no publication |

Runtime fixture uses the real native SDK with `httpx.MockTransport`; sockets are blocked.
The success path observed two transport requests and one validated tool invocation,
not two independently implemented loops and not actual inference. The first cancellation
fixture stalled because of a callback signature mismatch; corrected and bounded, then
the full runtime suite passed. One concurrent terminal result was unrelated and not counted;
the exact portability command was rerun and its four passing unittest results observed.

Still unverified: package index availability, native Foundry hosting/identity, parent
catalogue/descriptor integration, host renderer styling/browser workflow and full
common-event/failure conformance. No live or
framework-complete workflow is claimed. Further actual artifact checks are appended here.

Artifact proof root: `/tmp/agentcraft-selected-artifacts.BiwIbM`.
Final current-source wheel/sdist/npm artifacts: `/tmp/agentcraft-selected-final.hSpHoR/artifacts`.
All three public Python typing markers, legal notices, normal versioned requirements,
public npm export paths and source-distribution examples were verified. Exact SHA256
values are recorded in [MIGRATION.json](MIGRATION.json).
Protected skill deployment-state artifacts were read back hash-identical; no host
configuration, data or checkpoint was deleted. Historical guidance/notices remain
provenance, not an active administration runtime or a grant to deploy.