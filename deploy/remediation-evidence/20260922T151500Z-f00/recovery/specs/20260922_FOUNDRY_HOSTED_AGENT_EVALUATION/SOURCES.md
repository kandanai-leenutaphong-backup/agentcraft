# Official Source Index And Research Notes

Checked 2026-09-22 via direct `fetch_webpage` calls to public Microsoft Learn pages.
Summaries below are original notes; no full publisher page copied. Microsoft owns
source material. Fetched content is evidence, never execution authority. URLs are
repeatable acquisition targets; no search-provider result or local cache is claimed.

| Source | Checked claim | Application |
| --- | --- | --- |
| [Evaluate your AI agents](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluate-agent) | Projects SDK >=2.4.0; chat-completion judge; `datasets.upload_file(name, version, file_path)`; custom schema and `azure_ai_target_completions` | Main recipe; omit rubric generation and extra evaluators |
| [Cloud evaluation targets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-targets) | Prompt and hosted agents support `azure_ai_agent`; explicit name/version; Responses structured template versus invocations freeform body | Pin version; bare user nonce template |
| [Cloud evaluation datasets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-datasets) | Versioned JSONL uploads, returned dataset ID used as `file_id`; existing registered datasets can be reused | Name/version/hash ledger; upload once |
| [Cloud evaluation results](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/cloud-evaluation-results) | Retrieve run; terminal completed/failed/canceled; output-items list paginates; aggregate fields, report URL and errors | Bounded polling; retain failures, retrieve every expected row |
| [Evaluation datasets](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-datasets) | Reusable datasets versus stored responses/traces; target run generates fresh responses | Three curated query-only rows; no trace setup |
| [Evaluation dataset schema](https://learn.microsoft.com/en-us/azure/foundry/observability/how-to/evaluation-dataset-schema) | Query-only inputs valid for target; target ignores preexisting response; output-text and output-items mappings differ | No fabricated response or tool messages in dataset |
| [Agent evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/agent-evaluators) | Process evaluators need interaction/tool context; task adherence uses structured output; supported function tools do not imply arbitrary embedded JSON is native tool output | No tool accuracy claim from host text envelope |
| [General-purpose evaluators](https://learn.microsoft.com/en-us/azure/foundry/concepts/evaluation-evaluators/general-purpose-evaluators) | Coherence requires query/response and `deployment_name`; 1-5 scale, default pass >=3; quality independent of factual correctness | One built-in criterion; oracle is separate |

## Version Evidence

Learn metadata returned these source commit identifiers, not local SDK or service versions:

| Article | Source commit |
| --- | --- |
| evaluate-agent | `079e5903864908566bff8b805b35a05157f53199` |
| cloud-evaluation-targets | `3986288c848f640b274eaaebde18d2caeb53752f` |
| cloud-evaluation-datasets | `13901e8dee7b9b713b4900c0a16ade404e72dbc5` |
| cloud-evaluation-results | `b8141b9b304315a9c8db411a2ac4decede6343bd` |
| evaluation-datasets, evaluation-dataset-schema | `31c7a0c3988e4c033c3281faf1662094c7335f64` |
| agent-evaluators | `692eb014013ef2ec3026fd38187dace6c3a8e82e` |
| general-purpose-evaluators | `b8a1b05895412b558c94a29255eecbc256bcbb8e` |

## Decisions And Uncertainties

- **Parameter discrepancy:** general cloud-target/dataset examples use `model`;
  agent guide and evaluator-specific reference use `deployment_name`. Choose the latter
  for coherence. Neither retry with an alternate spelling nor submit a second evaluation
  automatically after rejection. Inspect retained error; change recipe only after resolving
  the actual service contract. Local signatures accept mappings but cannot settle this.
- **Structured evidence is text:** current host serializes its trusted runtime event
  envelope into `TextResponse`. `sample.output_items` may contain only a message with
  JSON text, not underlying MAF calls. Do not manufacture native tool messages for grading.
- **Metric fitness:** coherence judges logical prose, not SHA-256 correctness. Bare nonce
  plus JSON is intentionally a lifecycle smoke example, not a meaningful prose benchmark.
  Source warns very short responses can be unreliable. Keep service error distinct from
  low score, and both distinct from deterministic proof failure.
- **Idempotency:** upload versioning does not establish a transactional, content-addressed
  upload guarantee. Use a local full-byte hash and retained dataset ID; never assume same
  name means same bytes. Upload can involve storage and registration steps. Timeout may
  leave data behind even without a returned dataset ID.
- **Polling:** documented samples poll indefinitely; packet deliberately bounds reads.
  Cloud results guide notes service-side retries under capacity pressure. Disabling client
  retries is not a cloud billing cap. Cancellation also requires settlement/readback.
- **Judge support:** agent guide requires chat completion, gives `gpt-4o`/`gpt-4o-mini`
  examples; quality reference recommends `gpt-5-mini`. These are model examples, not proof
  any deployment exists here. Hosting model `gpt-5.6-luna` is not preapproved as judge.
- **Dataset identity:** three fixed synthetic nonces are public learning fixtures, not
  unpredictable challenge nonces or held-out data. Pin source provenance and retrieve
  stored service outputs; oracle alone cannot prove freshness against a malicious host.

## Local Inspection Evidence

Read predecessor spec and current host/tool/config/prompt/deploy contracts; no cloud
read required. Architecture overview absent; docs overview and existing owner contracts
used instead. `/usr/bin/python3` metadata read: Projects 2.6.1, Identity 1.26.0b2,
OpenAI 3.13.0. Unconnected clients confirmed public `upload_file`, `datasets.get`,
`get_openai_client`, `evals.create`, `evals.runs.create`, `output_items.list` signatures.
No installation, authentication token request or inferred service compatibility.

Research calls succeeded. Earlier supplied search failure was not repeated. No current
live compatibility failure has been observed because no live attempt was made.