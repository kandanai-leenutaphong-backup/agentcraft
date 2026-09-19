# Native Investigation Adapter

Run from repository root using an existing installed interpreter. No install, environment
creation, model/provider call, cloud action, production source edit or original `.local`
write is part of the offline commands. The separately authorized `prompt-live` command below
does make bounded model requests. Generated browser builds and retained evidence stay outside
the checkout. Candidate controls and authored fixture state use temporary directories.

```bash
/tmp/agentcraft-investigation-closeout/env/bin/python -B optimization_framework/adapters/investigation/adapter.py describe
/tmp/agentcraft-investigation-closeout/env/bin/python -B optimization_framework/adapters/investigation/adapter.py preflight
/tmp/agentcraft-investigation-closeout/env/bin/python -B optimization_framework/adapters/investigation/adapter.py verify \
  --artifact-dir /tmp/investigation-native-adapter \
  --report optimization_framework/reports/investigation-local-first.json
/tmp/agentcraft-investigation-closeout/env/bin/python -B optimization_framework/adapters/investigation/adapter.py verify \
  --artifact-dir /tmp/investigation-native-adapter \
  --pins optimization_framework/reports/investigation-local-first.json \
  --report optimization_framework/reports/investigation-local-repeat.json
```

`--python` selects another existing interpreter. Receipt paths refuse overwrite; artifacts
use a fresh private `adapter-*` directory. `--pins` refuses source drift before subprocesses.
Describe/preflight are also callable Python functions; `verify` returns the same receipt the
CLI writes. These are adapter-owned entry points, not a new framework service registration.

## Evidence

- Actual `load_agent_spec` loads copied app YAML, prompts and registered Python callables.
- Availability removes, restores and replaces optional selections, checks native advertised
  schemas, dispatches real activity tools and refuses unavailable calls before ADX execution.
  Actual `AgentEditor`/`AgentLibrary` preserve saved versions and refuse each required-tool
  removal. Authored fixture state is read back after reopening the store.
- Definition candidate wraps actual `profile_host_activity`: row cap becomes two and result
  carries a marker plus runtime-observed implementation digest. Native schema refusal and
  direct invalid-input refusal preserve the original implementation and query envelope.
- Prompt candidate changes only a copied agent prompt. Native request delivery, digest changes,
  foundation/tool invariants and fixture evidence are verified. **Prompt behavior remains
  unproven by fixture tests.** The opt-in live probe below verifies only narrow formatting
  adherence on two synthetic inputs, with its outcome recorded in a separate receipt.
- Suspect profile is **pending, not implemented**. Task contract states required ownership,
  persistence, citation, revision and real browser acceptance. It has no fabricated pass.
- Existing `deploy/deploy.sh browser-verify native-offline` builds and operates the baseline
  app through signed loopback HTTP, with synthetic native I/O and matching auth refusals.
  It does not install or synchronize dependencies. Browser evidence is not candidate UI proof.

The native SDK receives an in-memory `httpx.MockTransport`; its explicit fixture inference
permission is not permission for a real model call. Focused tests refuse socket connect/DNS.
Browser network guards and fixture lifecycle remain owned by the existing verifier.

Receipts retain actual subprocess argv, cwd, exit, measured duration, final 16,000 output
bytes with truncation flag, source hashes, import origins, candidate hashes and native browser
report hash/path. Editable imports are intentional: **no independent isolation, held-out
acceptance, production lifespan or deployed verification claim**. First three task statuses
mean offline checks only; OF-14/G3 are not complete.

Source and original `.local` hashes are compared before/after; this detects changes, not an
OS-enforced write sandbox. Temporary candidates are removed; external browser receipts,
screenshots, synthetic state and build outputs are retained. No automatic deletion of retained
evidence. The runner terminates its process group on timeout and reports failure.

## Opt-In Prompt Behavior Probe

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/agentcraft-investigation-closeout/env/bin/python -B \
  optimization_framework/adapters/investigation/adapter.py prompt-live --allow-model-calls \
  --report optimization_framework/reports/investigation-prompt-live-first.json
```

Run with the existing SDK interpreter directly. No installation or environment creation.
Missing explicit permission returns `refusal` before credential construction. Receipts refuse
overwrite. Endpoint comes from `CYBEREYE_OPENAI_ENDPOINT`, otherwise the existing committed
`deploy/env/existing-perth-m1.env` target; model remains the loaded `gpt-5.6-luna`.
Current async `DefaultAzureCredential` follows the app's noninteractive pattern. Tokens,
authorization headers and raw exception/provider message bodies are never recorded.

Two frozen synthetic incidents run in baseline/candidate, candidate/baseline order. Both
variants load copied real controls through `load_agent_spec`; candidate appends only the
task instruction. Native `AgentService.stream_turn` uses the public `llm_interface.connect`
API. Summary methods are unsuitable because they replace source instructions. Tool schemas
remain identical, but all execution is denied and ADX/scanner objects refuse access.
Evidence is supplied in the analyst message, not presented as tool retrieval.

Four HTTP inference requests maximum, one per native run, 120 seconds per run, no retry or
provider fallback. First provider/auth failure stops the schedule. Transport records actual
dispatch count, HTTP status, prompt/request hashes and validates delivered instructions and
tool schemas before sending. Receipt includes measured run durations, synthetic outputs,
source pins, owner refusal, unchanged original `.local`, and removed temporary controls.
SDK error codes are sanitized; remote work/billing after cancellation remains unknown.

Pass requires both candidates to meet exact JSON fields, scope, observed identity and supplied
citation IDs, and both baselines not to use that exact format. Output review must separately
confirm inference/unknown wording and citation entailment. This does not establish general
prompt quality, tool selection, persisted profiles, application quality or benchmark improvement.

Offline checks, which never establish live behavior:

```bash
PYTHONDONTWRITEBYTECODE=1 /tmp/agentcraft-investigation-closeout/env/bin/python -B -m pytest -q \
  -p no:cacheprovider optimization_framework/tests/test_investigation_prompt.py
```

## Smallest UI Follow-Up

Authorize one app-owned vertical change: typed owner/revision/citation-validated suspect-profile
service and persistent record; authorized tool and API adapters calling that service; profile
event/read-back schema; Investigation tool-board profile view. Extend the existing native
browser fixture to update via the typed tool, observe rendered citations, reload/read back,
and refuse foreign owner, unsupported citation, invalid update and stale revision. Existing
owners are backend models, agents/tools, API/persistence and frontend investigation feature.
Do not implement a second profile in this adapter or label an activity aggregation a new UI.