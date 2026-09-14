---
name: agent-optimization
description: "Use when improving or independently adopting an agent optimization loop: frozen-cohort evaluation, immutable generations, evidence tools, detector rules, prompts, native CLI authoring and replay UI. Includes portable Python/React APIs plus a verified, extractable first-party source snapshot with a synthetic example ledger and host integration guides. No model score, access grant or remediation is implied."
---

# Agent Optimization

Use the portable runtime for application composition. Use the independent
[reference skillpack](README.md) for offline source-level adoption and process/UI comparisons.
Extracting the snapshot does not upgrade the portable package or change a running application.

## Portable Runtime

The full [process](python/agent_optimization/PROCESS.md),
[contract](python/agent_optimization/README.md), [lessons](python/agent_optimization/LESSONS.md),
source, receipts/verifier and UI are bundled. Domain labels, datasets, scorer/model requests,
authorization and storage roots are injected by the host, not read from the source application.

Install the declared `harness-situation-detector` and `copilot-terminal-runtime` packages first,
then this package as `harness-agent-optimization`; import `agent_optimization`. For local sources,
install the three explicitly selected package paths together with `pip --no-deps` after their
requirements are satisfied. No sibling skill discovery or hidden `app` import is used at runtime.
The frontend declares `copilot-terminal` and `@harness/source-code` dependencies through public APIs.

Use `OptimizationService` with a neutral `OptimizationProfile`; `authorize` and `identify` own
caller checks. `OptimizationTerminal` uses the shared terminal implementation with an explicitly
approved, workspace-contained `./opt` helper. Helper operations remain bounded and session-owned.
Generated Python execution requires caller-supplied bubblewrap plus libseccomp. No sandbox fallback
or automatic tool grant is allowed when unavailable. The private SQLite reader excludes labels,
writes, extensions and out-of-scope tables; it is not a general SQL execution service.

Read a completed parent, hypothesize, preview on contrasting development cases, publish the exact
probed configuration, evaluate frozen cohorts, then read persisted outcomes. Preserve failures and
denominators. The embedded [creative workflow](python/agent_optimization/skills/creative-agent-optimization/SKILL.md)
adds measured experimentation, not a requirement to run a long campaign for every task.

Verification: `python -m pytest "$SKILL_ROOT/python/agent_optimization/tests" -q -p no:cacheprovider`
after installing shared dependencies. The copied 63 tests use neutral datasets, fake model responses
and synthetic campaign receipts. They do not prove live models, Azure storage or OS sandbox availability.

## Independent Reference Snapshot

The [contents map](references/CONTENTS.md) covers the archived runtime, UI and synthetic example
ledger. Read the [integration guide](references/INTEGRATION.md) before adopting code. The payload
is built from this skill's own sources: no host application, customer configuration, dataset,
credential, cloud target or third-party clone, and no recorded origin path or source revision.
It is reference material, not a second installed runtime or an automatically discovered skill tree.

From this skill directory:

```bash
python3 -B scripts/skillpack.py verify
python3 -B -m unittest discover -s tests -p 'test_*.py' -v
python3 -B scripts/skillpack.py extract --destination /tmp/agent-optimization-reference
```

Choose a new extraction directory outside the repository. The verifier checks the
[manifest](manifest.json), every payload hash and safe archive membership; extraction refuses
existing destinations and reads back written hashes. Follow the [verification guide](references/VERIFICATION.md)
for isolated runtime and frontend checks. No command above installs dependencies or calls a model.

For either workflow, define the question, authorized data, useful evidence view and interpretation
before optimizing. Freeze model, cohorts, scorer, resource bounds and skill identity; probe contrasting
development cases and publish only the exact successful receipt. Require exact parent pins for
controlled comparisons, measure full training then evaluation, and preserve failures and regressions.
Actions remain recommendations. Historical scores are not new measurements or promised outcomes.

Raw datasets, credentials, historical campaign artifacts and per-case outcome ledgers are excluded;
the bundled `example/` records are hand-authored illustrations of shape, not measurements. Hashes
establish internal consistency, not publisher authenticity or redistribution rights, and no overall
license is asserted here. Rebuilding the snapshot is a separate, explicit maintainer operation.