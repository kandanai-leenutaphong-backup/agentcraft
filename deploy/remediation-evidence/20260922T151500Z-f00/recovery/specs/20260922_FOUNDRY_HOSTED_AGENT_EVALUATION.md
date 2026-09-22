# Hosted Agent Evaluation: Three-Row Learning Packet

Status: **live three-row evaluation completed**, 2026-09-22.
Current authorized implementation: [evaluation testbed](../testbeds/foundry-agent-evaluation/README.md).
Exact hosted version 3 and existing `gpt-5.6-luna` judge remained pinned.
One dataset/version, one evaluation definition and one completed run returned three
scores: coherence 4, 4, 2 (threshold 3); independent oracle passed 3/3.
[Final result](../testbeds/foundry-agent-evaluation/deploy/records/20260922T075756325970Z-closeout.json)
retains identities, report URL, failed attempts, full evidence hashes and settlement.
Four reservation requests and two uploads were necessary: two local guard refusals,
then service rejection of a 71-character version, diagnosed through registration-only
replay, then successful 39-character version. One prior uploaded blob remains orphaned.
No optimization, hosting change, replacement evaluation or cleanup occurred.

The preparation gates below are historical: current user assignment grants dataset,
evaluation and inference writes plus necessary scoped infrastructure decisions.
It supersedes the earlier no-provisioning restriction, not one-shot bounds or acceptance.
The packet remains the frozen dataset/oracle owner; its CLI stays offline.
Follow-on to [hosting experiment](20260922_FOUNDRY_HOSTED_AGENTS_EXPERIMENT.md),
not a deployment, optimization campaign, constitution or production quality benchmark.

## Scenario And Decision

Send three fixed synthetic hexadecimal nonces to the existing hosted Responses agent.
Learn dataset upload/versioning, evaluation definition, pinned agent targeting, bounded
polling and aggregate/row-result retrieval. No new tools or application changes.

- [Dataset](20260922_FOUNDRY_HOSTED_AGENT_EVALUATION/dataset.jsonl): exactly three
  unique `query` strings. No response column: target generates responses at run time.
  SHA-256: `7fa1aa57385f15a1eaead798f022f7cdb62f8b5a484a1b8bee367336118b3357`.
- Built-in: `builtin.coherence`, `query={{item.query}}`,
  `response={{sample.output_text}}`, `initialization_parameters.deployment_name`.
  Report score, threshold, label, errors and explanatory reason without tuning thresholds.
- Independent local oracle: recompute SHA-256 of UTF-8
  `foundry-custom-script-v1:` concatenated with nonce; check marker, nonce, exact result,
  one correlated ready/start/result chain and four loaded identity pins.
- Coherence is instructional only. A coherent lie fails the oracle; a correct JSON
  result can score poorly for prose. Neither score proves general agent quality.
- Synthetic negative control corrupts the digest locally. It never enters uploaded
  dataset and is **not an observed agent failure**.

## Existing Contracts

Read on 2026-09-22: [tool](../testbeds/foundry-hosted-agents/proof_tools.py),
[host](../testbeds/foundry-hosted-agents/main.py),
[configuration](../testbeds/foundry-hosted-agents/configuration.yaml),
[prompt](../testbeds/foundry-hosted-agents/prompts/proof.md),
[runner](../testbeds/foundry-hosted-agents/deploy/experiment.py),
[operator guide](../testbeds/foundry-hosted-agents/deploy/README.md).
Architecture overview absent; [docs overview](../docs/README.md),
[execution contract](../libraries/llm-interface/CONTRACT.md) and
[configuration contract](../libraries/modular-agents/modules/agent-config-build/CONTRACT.md)
used as routing fallback. No ownership or dependency edge changes.

Current host accepts only a bare 32-character lowercase hexadecimal nonce. Do not
send natural-language instructions or the documentation's additional developer message.
Its `TextResponse` carries host-generated evidence JSON in text. `tool_events` inside
that text are not native function-call records in `sample.output_items`. Therefore
task-adherence/tool-quality evaluators are deliberately not used as execution proof.
The oracle relies on the accepted host's provenance; it is not remote attestation.

## Mandatory Handoff Gate

Predecessor prose contains stale pending statuses. It neither certifies success nor
proves the current deployment is absent. **Wait for hosting owner's final accepted v2
receipt**, meaning the second distinct tool-bearing image, not record schema v2 or an
assumed numeric agent version `2`. No latest-version fallback.

Before any evaluation upload/inference, operator must retain and verify:

1. Final v2 acceptance and linked build/deploy/invoke/verify receipt paths and hashes;
   proof of added tool, Running/active readiness, protected call, anonymous 401/403 and
   stored response readback. A deploy receipt alone is insufficient.
2. Actual agent name/version, immutable image `@sha256:...`, source manifest and config
   hashes; compare exact remote version immediately before submission. Preserve
   source archive and installed package inventory, not merely a Git HEAD guess.
3. Confirmation accepted v2 retains this bare-nonce/`nonce_digest` contract. If changed,
   stop and adapt this packet to final contract before submission. Never silently
   target v1 or treat extra/missing tool events as a pass.
4. Explicit evaluation authority: project dataset/eval writes, three target rows,
   one judge criterion, bounds below and approved evidence storage. Hosting authority
   is not an evaluation grant. Foundry User or effective equivalent, storage access,
   existing quota and compatible region must be verified without provisioning.
5. An existing, authorized **chat-completion-capable judge deployment**, with its
   deployment/model/version recorded. `gpt-5.6-luna` is the agent model, not an
   automatically valid judge. Do not create a judge deployment or substitute a name.

Current verify receipt shape: `action=verify`, `status=complete`,
`result.readback=true`, `result.anonymous_status`, `result.version.definition`,
`result.tool_evidence.{source_sha256,config_sha256,agent_name,agent_version}`.
Cross-check linked deployment's `result.image`, `result.source`, `result.version`.
Final v2 fields can change; hosting owner must supply interpretation, not this packet
invent an acceptance field. Runtime pins remain intentionally unset here.

## Bounds And Acceptance

Current recovery assignment supersedes the original one-upload/reservation cap:
minimal diagnosed recovery is authorized; maximum one registered dataset/version,
one new evaluation definition,
one run submission and three unique input rows. No automatic retry of writes or
inference. Poll at most 30 times, at 10-second intervals, with a 600-second local
deadline and per-request timeouts. Fetch at most three expected output items;
unexpected pagination/extra rows fails completeness rather than silently truncating.

Current host caps each invocation at two model calls, one tool call, 512 output
tokens per model call and 90 seconds. Three rows imply at most six host model calls
**only if each row is invoked once**. Cloud evaluation can internally retry; client
submission bounds are not a hard service-side inference/token/billing cap. Judge
tokens and total cost unknown. Reject live execution if a hard billable cap is required
but cannot be enforced. Poll timeout does not cancel server work; retain IDs and settle
the existing run, never submit a replacement to recover results.

Learning acceptance: one completed run with all three distinct row outputs, aggregate
counts, per-criterion scores/errors, report location/IDs and pinned evidence. Record
deterministic passes out of three separately from coherence. Missing rows/errors are
not passes. A proof success claim requires 3/3; learning workflow completion can expose
failures without pretending the agent succeeded. No statistical/generalization claim.

## Operator Order

1. Run packet's offline `validate` and `dry-run` commands in
   [operator recipe](20260922_FOUNDRY_HOSTED_AGENT_EVALUATION/deploy/README.md).
2. Obtain final accepted v2 handoff and explicit evaluation grant; resolve judge and
   SDK/service prerequisites. Freeze actual identities at that time.
3. Follow recipe once: upload or verified reuse, define, submit pinned target, poll,
   retrieve aggregate and row outputs, sanitize, score offline, retain results.
4. Return IDs, artifact hashes, row failures and remaining service state. No automatic
   follow-on run, threshold change, teardown or optimization.

## Evidence And Gaps

Current live evidence and reusable service contracts are owned by the testbed's
[deployment guide](../testbeds/foundry-agent-evaluation/deploy/README.md).
Dataset version names must be <=50 characters; full content hash remains an
independent pin. Stored dataset bytes were retrieved and matched. Eighteen offline
tests and final live verification pass. Coherence's third-row failure is retained,
not overridden by deterministic correctness. Cost and provider-internal retries unknown.

The following bullets describe historical offline preparation, not current live status:

- Offline `validate` and entrypoint `dry-run` passed: 3 rows; one synthetic positive;
  four negative controls rejected (wrong digest, prose-only, wrong version, missing pins).
- Independent comparison against current real `nonce_digest`: 3/3 rows matched.
- Row scorer checked with synthetic outputs: valid 3/3, incorrect proof 2/3,
  missing-row refusal and duplicate-row refusal. No synthetic result is live evidence.
- Editor diagnostics for example: no errors. Shell syntax passed; 14 local document
  links resolved and four Python recipe blocks parsed. First documentation check used
  unsafe shell quoting: backtick expansion invalidated its snippet count. Corrected
  single-quoted command passed; invalid first count discarded. No cloud effect.
- Read-only `/usr/bin/python3` facts: `azure-ai-projects 2.6.1`,
  `azure-identity 1.26.0b2`, `openai 3.13.0`; public upload/get/client/create/list
  signatures inspected without requests. This is not the editor interpreter or image
  lock, and does not establish service compatibility. Recheck after hosting worker settles.
- Eight official pages checked directly; [source index and findings](20260922_FOUNDRY_HOSTED_AGENT_EVALUATION/SOURCES.md).
  Search not repeated; prior supplied context reports missing search key/zero fallback results.
- Live submission/reconciliation is a documented SDK recipe, **not an implemented live
  CLI**. Offline CLI cannot contact Azure. Automated final-v2 receipt ingestion, remote
  dataset-byte verification and SDK/service integration remain unimplemented/unverified.
  Packet is ready for offline learning and operator review, not unconditional live execution.
- No cloud call, inference, install, venv, commit, worker dispatch or predecessor edits.
  Requested max effort has no exposed host control; effective effort unverified.
  Total duration, tokens and cost unknown; tool calls remain in host session history.
  No formal archive/notebook added: this packet itself owns cheaply rechecked findings.
