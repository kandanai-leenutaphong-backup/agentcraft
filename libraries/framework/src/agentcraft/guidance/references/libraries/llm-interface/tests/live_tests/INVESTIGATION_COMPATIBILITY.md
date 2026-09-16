# Investigation Compatibility: Offline Increment

## Subsequent Source Repair

The integrator converted IC-09 to a refusal regression, observed it fail, then repaired
canonical binding and pre-execution validation. Preserving the mapping alone was insufficient:
the installed framework did not enforce the numeric constraint. `jsonschema` with a no-network
reference registry now validates raw mappings before any batch function executes; typed
Pydantic validation is retained. Local references, nested bounds/enums/required fields,
whole-batch refusal and remote-reference refusal are tested with both accepted and rejected data.

Current source evidence on 2026-09-15: 13 compatibility tests and six tool tests pass;
full suite reports 49 entries, 48 passed and one optional legacy comparison skipped.
Used a new isolated environment with `jsonschema` 4.26.0 and `referencing` 0.37.0; the old
environment and app dependencies were not synchronized. Live cases remain `NOT_RUN`.
Fresh artifact evidence, when available, is owned by [VALIDATION.md](../../VALIDATION.md).

The original observations, counts and fingerprints below are historical pre-repair evidence,
not descriptions of the corrected source. Mapping-schema preservation is no longer an open
source gap; model/app dependency and behavioral migration decisions remain open.

## Original MODEL Hand-Back

**2026-09-15: 13 compatibility experiments and 16 adjacent tests pass. Migration remains blocked.**
Public `llm_interface` APIs support a thin host adapter for fixed instructions/options, typed
tools, JSON results and owner-bound local sessions. They are not a drop-in raw Responses API.
Raw mapping-schema constraints are lost in current agent binding; the experiment reproduces
that gap rather than certifying parity. OpenAI pins, history, error/completion semantics and
Custom Optimizer scheduling still require integrator decisions.

Scope: T004 coverage and the offline experimental portion of T025. No runtime, app, dependency,
lock, README, programme-task or retirement changes; no cloud/model/credential operation. Only
the three assigned MODEL evidence files were written. No new team, runner or parallel model
transport was created. The [coverage registry](COVERAGE.md) retains every live case as `NOT_RUN`.
**No live identity, deployment compatibility, model quality, cost or app-parity proof exists.**

## Evidence Boundary

- **R (reproduced):** public API calls through real Agent Framework and native OpenAI clients;
  only HTTP responses are controlled by `httpx.MockTransport`, with socket connections blocked.
  No library internals, AgentService replacements or mocks above the interface are test oracles.
- **S (source-derived):** current app/shared implementation read from the linked source. No app
  runtime was imported or executed by the new library tests. Synthetic sink functions reproduce
  wire shapes, not the real diagnosis ledger, data authorization or tool implementation.
- **U (unknown):** unexecuted behavior, including real Azure identity, model/provider support,
  Python 3.12 joined installs, real app assignment races, UI retention and live cancellation effects.

Environment was used read-only via `libraries/.venv-llm-interface/bin/python -B`. No install,
sync or lock resolution occurred. Python 3.11.14, Linux WSL2 kernel 6.6.87.2; source import origin
was src/llm_interface/__init__.py (source-or-asset-not-bundled; source reference: `../../src/llm_interface/__init__.py`), not a fresh wheel.
Artifact digest and independently installed consumer-artifact evidence are **unknown**.

| Installed Distribution | Version |
| --- | --- |
| llm-interface | 0.1.0a1 |
| agent-framework-core | 1.18.0 |
| agent-framework-openai | 1.14.3 |
| agent-framework-foundry | 1.13.0 |
| openai | 3.13.0 |
| azure-ai-projects | 2.6.0 |
| azure-identity | 1.25.3 |
| httpx | 0.28.1 |
| pydantic | 2.13.5 |

Presence of Foundry packages does not establish a Foundry execution. New tests use the explicit
`openai` Responses profile against a synthetic HTTPS host. Adjacent agent tests additionally
exercise Completions; adjacent safety tests exercise the Azure OpenAI binding with fixture identity.
None is a live inference or authentication pass. Editor diagnostics reported no errors in the new
test file; interpreter facts above come from the explicit process, not inferred editor settings.

### Exact Test Commands

Run from repository root; these commands were executed without changing the environment:

```bash
libraries/.venv-llm-interface/bin/python -B -m unittest discover -s libraries/llm-interface/tests -p test_investigation_compatibility.py -v
libraries/.venv-llm-interface/bin/python -B -m unittest discover -s libraries/llm-interface/tests -p test_agents.py -v
libraries/.venv-llm-interface/bin/python -B -m unittest discover -s libraries/llm-interface/tests -p test_tools.py -v
libraries/.venv-llm-interface/bin/python -B -m unittest discover -s libraries/llm-interface/tests -p test_safety.py -v
```

Final results respectively: **13 tests OK; 4 tests OK; 3 tests OK; 9 tests OK. No skips.**
The first edit was one test, immediately run: 1 test OK. Iteration exposed raw-schema constraint
loss and an empty reasoning opening delta. Tests now record those actual facts; runtime behavior
was not patched to make the experiment pass. A green known-gap test is not a feature acceptance.

Read-only `importlib.metadata.distribution` inspection established the installed requirements
below. A separate public-API synthetic completion probe observed `AgentResponse.response_id ==
"resp"` for native fixture ID `resp`, plus `finish_reason`, `usage_details`, and the receipt keys
`run_id`, `model_calls`, `tool_calls`, `status`, `elapsed_ms`, `persistence`. This proves completion
metadata availability only, not provider-thread continuation or early streamed metadata.

Source fingerprints, read with `sha256sum` after the final test edit:

| Source | SHA-256 |
| --- | --- |
| [Contract](../../CONTRACT.md) | `d0b67983894afb5d1bca185d108ef8432e83d3bc552125ea0e3d3921a93a7eb3` |
| Compatibility tests (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py`) | `fec3e002f151d304ebcbf4c48c2b61c2707c40a4de2ef103422c39c58bdec6c2` |
| Agent binding (source-or-asset-not-bundled; source reference: `../../src/llm_interface/agents.py`) | `19ec9cc18ca3394d1d32f93934ad4d8c1497a9aab98682790bbda63f725f38c8` |
| Connection/guards (source-or-asset-not-bundled; source reference: `../../src/llm_interface/connection.py`) | `307d452e81d0d68cc4607ee08a166f4f46fe538f611fe17bee573a8d8f1a197b` |
| Completion integrity (source-or-asset-not-bundled; source reference: `../../src/llm_interface/integrity.py`) | `8c06658a9c2fb65160aba033153dd698973acde1b9c7aae8643664205539bd04` |

## Reproduced Public Facts

IC IDs identify offline experiments, not successful full provider/mode cases from the live registry.

| ID / Test | Observation | Compatibility Consequence |
| --- | --- | --- |
| IC-01 Instructions/options (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L45`) | Two native requests preserve fixed instructions, `max_output_tokens=128`, `parallel_tool_calls=False`, declared high/detailed reasoning and `store=False`; no `previous_response_id`. | Use binding instructions and supported run options; do not forward raw request kwargs. |
| IC-02 Legacy fields (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L76`) | `instructions`, `previous_response_id`, `max_output_tokens`, `extra_body`, `text` refuse as `option_unsupported`; alternate model/retention as `binding_override_denied`; `max_tokens=1200` exceeds default; effort `max` refuses. No HTTP requests. | Explicit field translation and reviewed bounds are necessary for both consumers. |
| IC-03 Reasoning capability (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L101`) | Both explicit `none` and `high` refuse as `reasoning_unsupported` under default capability, without HTTP. | Even the optimizer's `none` setting needs a deliberate capability/configuration decision. |
| IC-04 History/ownership (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L114`) | Awaited and streamed second turns send first user text, first assistant answer and follow-up in order; result reads are copies; receipt IDs differ; foreign run/read refuses `session_not_found`. | Local history and owner checks work. This is not import of an old provider conversation. |
| IC-05 Returned query error (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L162`) | A finite JSON error envelope survives into exactly one next native request, preserving call ID; the framework completes with one tool execution. | A reviewed recoverable-query envelope can remain app-owned; no second tool loop needed. |
| IC-06 Thrown error (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L191`) | Thrown tool exception becomes payload-free `tool_failed`, with no public cause or private marker in captured logs; no next model call; replay refuses `session_interrupted`; prior result survives. | Generic exception-to-model behavior changes. Last-result read-back is not permission to replay. |
| IC-07 Typed sink/events (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L226`) | Public `tool(schema=PydanticModel)` preserves scalar/array bounds and extra-field policy. Host context is absent from model parameters. Authorization/progress/result IDs align; sequences are monotonic; one completed terminal reports two model calls/one tool call. Original JSON reaches model and stream. | Thin adapters can bind context and restore app metadata. Even `unsupported-fixture` evidence ID survives unchanged: provenance must remain in the real app ledger. |
| IC-08 Incomplete tool call (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L309`) | Both modes reject a fully formed tool call on an incomplete response with `incomplete_tool_call`; zero function executions, one model request; no result and no session replay. Stream ends with `run.failed`, not a successful incomplete tool cycle. | Old continuation-from-incomplete behavior cannot be preserved by argument renaming. |
| IC-09 Raw schema gap (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L351`) | A public mapping declaration advertises `minimum=1`, but bound native schema loses it and executes value 0. Equivalent Pydantic model retains the bound and refuses value 0 with `invalid_tool_arguments`, zero executions. | Known incompatibility for `MODEL-T04-P.OAR.AGENT` and its refusal counterpart. Do not silently downgrade this to unsupported or remove it from coverage. |
| IC-10 Partial text/EOF (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L399`) | Terminal incomplete text returns `run.incomplete` and is retained with status `incomplete`; event lacks reason/provider response ID. Quiet EOF emits partial text then `missing_terminal_event`/`run.failed`, with no retained result and no replay. | Callers must inspect result status, not treat every non-None `session.result()` as complete. Preserve partial/error distinctions. |
| IC-11 Pinned binding (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L438`) | Creating a changed binding while an old request waits does not alter old instructions. Old session refuses the changed binding; fresh session sends only new-turn history. | Supports immutable request binding. Actual app assignment persistence/concurrency remains untested. |
| IC-12 Cancellation (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L478`) | Stream close cancels the pending local HTTP await; final-result waiter raises `CancelledError`; no result or replay; one request only. | Use explicit close and surface interruption. Remote work and running synchronous tools remain unknown. |
| IC-13 Reasoning events (source-or-asset-not-bundled; source reference: `../test_investigation_compatibility.py#L515`) | Native summary-part input produces empty opening plus text `reasoning.summary.delta`, both ID `reasoning-fixture`; no legacy start/end events. | Item-level delta aggregation is possible; summary-part boundaries/indexes are not preserved by RunEvent. |

IC-09's cause is source-derived: AgentBinding._bind_tools (source-or-asset-not-bundled; source reference: `../../src/llm_interface/agents.py`)
rebuilds each FunctionTool with `input_model=candidate.input_model`. The public framework tool
probe showed `schema=dict` has `input_model=None`, while `schema=PydanticModel` retains a model.
Rebuilding therefore regenerates the mapping tool's schema from the function signature. The
typed positive is an available path, not proof that all existing authored schemas were migrated.

## Exact Dependency Conflict

| Requirement Owner | Observed Requirement |
| --- | --- |
| Investigation manifest (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/pyproject.toml`) | Python >=3.12,<3.13; `openai==2.37.0`; `pydantic==2.12.5` |
| Custom Optimizer manifest (outside-guidance-not-advertised; source reference: `../../../../template_apps/custom_optimizer/pyproject.toml`) | Python >=3.12,<3.13; `openai==2.37.0`; `pydantic==2.12.5` |
| Shared foundations manifest (outside-guidance-not-advertised; source reference: `../../../../template_apps/shared/pyproject.toml`) | `openai>=2.37,<3` |
| Library manifest (source-or-asset-not-bundled; source reference: `../../pyproject.toml`) | Both native extras require `openai>=3.13.0,<3.14`; base library requires `agent-framework-core>=1.18.0,<1.19` |
| Installed agent-framework-openai 1.14.3 metadata | `openai>=2.25.0,<4`; `agent-framework-core>=1.17.0,<2` |
| Installed agent-framework-foundry 1.13.0 metadata | `agent-framework-openai>=1.14.2,<2`; `azure-ai-projects>=2.2.0,<2.7.0` |
| Installed azure-ai-projects 2.6.0 metadata | `openai>=3.0.0` |

**S/R:** `{2.37.0}` and `[3.13.0,3.14)` have empty intersection; shared `<3` also excludes
the tested SDK. This is not a claim that Agent Framework itself requires OpenAI 3.x: its installed
OpenAI adapter admits both major versions. Installed Azure Projects adds another 3.x constraint
for the tested Foundry combination. No alternative dependency solution was installed or tested.

Integrator direction: test one joined Python 3.12/OpenAI 3.13 cohort for the two apps, foundations
and canonical library, then change pins/locks under the reserved owner. Merely editing the
Investigation pin leaves foundations and Custom Optimizer incompatible. Downgrading the library,
using import order, retaining a second OpenAI 2.x client path or calling `from_clients` to evade
the contract is not an established resolution. Existing app Pydantic 2.12.5 is also not the tested
2.13.5 combination; compatibility remains U, not an asserted additional version conflict.

## Request And Tool Mapping

S baseline: AgentService (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/agents/service.py#L196`),
AgentSpec (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/agents/config.py`),
ToolMetadata/ToolContext (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/agents/tools/base.py`).
Mappings below are proposed host adaptation, not implemented application code.

| Old Field / Behavior | Public Mapping / Required Treatment | Evidence |
| --- | --- | --- |
| `settings.openai_endpoint`, `spec.model`, shared raw client | One host-owned `connect` per approved fixed target/model/policy; new model needs a new binding/connection, not per-request model override. Reuse native HTTP clients through that owner. | S; IC-01/02 |
| `credential()` / `bearer_token_provider` created inside AgentService | Inject credential/configuration at composition edge; library borrows credential. Retain authenticated caller derivation separately. Native identity refresh/scope behavior needs live proof. | S; U live |
| `config_id`, `config_version`, `config_digest`, `agent_id`, display name | Snapshot AgentSpec at request start and enrich outgoing app metadata from that snapshot. Library run/session IDs do not identify an authored version. Use bounded binding name separately from display text. | S; IC-11 |
| `instructions or spec.instructions`; diagnosis suffix | Construct fixed `AgentBinding` for the selected immutable instructions, including diagnosis suffix where required. Public run options cannot replace instructions. Do not mutate a binding in flight. | IC-01/02; S |
| `input`, analyst message, optional Situation envelope | Keep the current app string/envelope assembly; pass string or public Messages to `run`. Preserve evidence ordering and byte/history bounds. No app/domain imports into the library. | S; IC-04 |
| `previous_response_id` | Replace host-held provider pointer with an owner-bound library Session after the history decision below. Completed `AgentResponse.response_id` can be display/trace metadata only, not a resumption input. | IC-02/04; completion probe |
| `ResolvedTool.openai_schema()` dictionaries | Bind normal callables using public `tool(name=..., description=..., schema=...)`, with context captured outside arguments. Keep exact names and grants from selected registry. Existing metadata's strict schemas cannot currently be copied as raw mappings and assumed preserved. | S; IC-07/09 |
| `ToolContext(adx, scanner)` and purpose-built tool functions | Thin typed host wrapper calls existing `function(context, **arguments)`; do not expose context, credentials, caller identity or data-source selection as model arguments. Tool authorization stays host-owned. | S; synthetic context proof IC-07 |
| `reasoning_request(summarize=True)` | Run option `reasoning={effort, summary}` only with explicit capability. Supported app values none/low/medium/high/xhigh need deployment validation; app value `max` refuses. Summary emission is not guaranteed by a declaration. | IC-01/02/03/13 |
| `max_output_tokens` | Rename to `options.max_tokens`; set reviewed host `Limits.max_output_tokens` high enough for accepted normal/diagnosis/summary/classification requests. Library default 1024 cannot silently replace app caps up to 4000. | S; IC-01/02 |
| `max_tool_iterations`, diagnosis iterations | Decide `Limits.max_model_calls` and `max_tool_calls` separately. Old loop counts iterations, may run multiple tools per round, and uses a retrying transport; library counts native attempts and authorized executions. Default 8/16 is not automatic parity. | S; adjacent model-budget test |
| `parallel_tool_calls` | Forward supported option; host authorizer checks every call. Native simultaneous siblings are not an atomic transaction; failure cannot undo an already-started tool. | IC-01; contract |
| `json.dumps(result, default=str)` | Keep finite JSON-compatible domain result envelopes. Library does not promise arbitrary object/date coercion; app serialization decisions must precede the tool boundary. | S; IC-05/07 |
| Summary/classification synchronous `responses.create` | Use fixed-instruction, no-tool binding and awaited run with one-model-call policy; preserve current app summary/classification parsing and historical-replay fields. Migrate callers to async; no generic synchronous legacy shim is provided. | S; awaited library path reproduced; app path U |

## Event Mapping

S baseline: stream_turn (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/agents/service.py#L231`)
and diagnose_situation (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/agents/service.py#L362`).
RunEvent shapes are public contract; only IC-covered rows have runtime evidence in this increment.
The mapper owns framing/metadata/state, never another model/tool invocation loop.

| Existing App Frame / Fields | Portable Input And Host Action | Preservation / Decision |
| --- | --- | --- |
| `status {phase,label}` | Derive presentation status from `run.started`, `tool.started` and result/terminal progress. | Local labels can stay. There is no public per-native-round `response.created` event to reproduce exact old timing. |
| `metadata {response_id,model,agent_id,agent_name,config_id,config_version,config_digest}` | `run.started` supplies binding name/session ID; add run ID and pinned app spec. Completed result can supply final `response_id`. | Early/per-round provider response IDs are unavailable in RunEvent; wire consumers need an explicit timing/field decision. |
| `token {token}` | `text.delta.data.text`. | Direct rename; diagnosis currently excludes token frames from its forwarded set. |
| `tool_call_start {id,name,display_name,fallback}` | Open preview once per call ID on first `tool.call.delta`, or on ready if no preview; enrich name from configured registry. `tool.started` means authorization succeeded. | Preview is not execution authority. Do not emit duplicate cards for ready/started. |
| `tool_call_delta {id,arguments_delta}` | `tool.call.delta {call_id,name,arguments}` fragments. | Preserve fragments; complete argument validation belongs to library. |
| `tool_call_end {id,name,arguments,display_name,fallback}` | `tool.call.ready` contains complete validated arguments; add registry metadata. | Later/stronger boundary than old JSON parsing. Invalid batches can leave preview without a ready event. |
| `tool_result {id,name,result,fallback,agent_id,config_id}` | `tool.result {call_id,result}`; recover name from call-ID map and append pinned app metadata. | IC-07 proves original JSON. Library result event has no name/display/fallback fields. |
| Tool failure rendered as result error | `tool.failed` contains safe code/category/field/action plus call ID/name. | Map to safe app error envelope where appropriate; do not reconstruct private exception detail. Stop/recover policy needs decision. |
| `reasoning_start`, `reasoning_delta`, `reasoning_end` with `item_id:summary_index` | Aggregate `reasoning.summary.delta {id,text}`; first delta may be empty. | Item ID is present; summary index and exact start/end boundaries are not. Host grouping/final closure is possible only as an explicit UI/wire decision. Multi-part summary parity remains U. |
| No current forwarded usage frame | `usage` plus final framework usage and receipt. | Preserve optional metrics separately; synthetic fixture usage is not measured live consumption. |
| `done {response_id,incomplete}` | One of `run.completed`, `run.incomplete`, `run.refused`, followed by final response/receipt read-back. | Final ID can be supplied after completion. Exact old `incomplete_details.reason` is not in the event; do not invent it or call a refused/incomplete result complete. |
| `error {error,detail}` | `run.failed` safe metadata, then raised `LlmError`. | Track terminal state and emit one app failure, not one from the event and another from the exception. No legacy raw exception text. |
| `aborted {session_id}` | Caller cancellation/close outcome. | Best-effort local notification only; disconnected consumers may receive no terminal frame. Never automatically replay. |
| `diagnosis`, `sequence_step`, `sequence`, diagnosis `done {recorded,sequenced,elapsed_ms}` | Existing host sink/ledger rule consumes mapped tool-ready/results. | These are app outcomes, not missing library event kinds. Preserve same single domain owner. |

## History, Errors And Sinks

**S: current history.** ChatSession (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/security/sessions.py#L35`)
stores owner, `previous_response_id`, version key, lock and touch time. SessionStore is bounded
to 256 entries with 12-hour idle expiry; another owner returns the same missing lookup as an
unknown ID. Chat API (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/api/chat.py#L35`)
streams under the host session lock, captures response IDs and retries once from a cleared pointer
only for a stale-thread error before irreversible output. A changed
version key clears the pointer (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/api/chat.py#L78`).

**Proposed preservation:** keep app session IDs, owner lookup/404 behavior, retention bounds and
atomic version-key update. Store a library Session behind that host-owned entry; derive principal
from existing authentication, never posted JSON. Library session locking serializes native history;
host locking still protects entry/version replacement. Neither library default principal nor
managed identity authenticates a human or signed-agent caller.

**Decision required:** old provider-only state cannot be converted by feeding the ID to the
library. No public transcript-transfer API exists. Approve fresh backend sessions on migration and
version change, with visible old transcript retained by an explicitly tested app path, or specify
a separately reviewed trusted transcript migration. Tool history/provider state cannot be inferred
from visible text. Current UI retention and restart behavior are U. No private Session state writes.

**Version distinction:** AgentEditor (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/agents/editor.py#L85`)
resolves an authored version and copies AgentService with that spec. Library binding hashes cover
connection/policy, instructions, name and tool names/schemas, not app version IDs, callable bodies
or authorizer identity. A version change with otherwise identical inputs therefore still needs the
host version-key rule. IC-11 proves separate binding isolation, not the actual editor assignment race.

**Error distinction:** old tool invocation (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/agents/service.py`)
returns arbitrary caught exceptions as `{error: type, detail: str}` to the model. IC-05 proves that
a deliberately returned finite JSON error can remain recoverable. IC-06 proves thrown exceptions
are strict stops. Choose a small, explicit allowlist of recoverable domain/query failures and safe
messages, or approve strict-stop behavior. Authorization, invalid arguments, budgets, cancellation
and integrity failures must not be caught and converted into permission to continue. Remove no
existing required refusal from acceptance. The stale-provider-thread text retry has no equivalent
under local history and the library's no-retry contract; do not recreate it generically.

**Incomplete distinction:** old AgentService inspects `response.output` and can execute tool calls
after `response.incomplete`. IC-08 proves the public library forbids that even for complete JSON
arguments. Approve a truthful interrupted/no-tool outcome; preserving old continuation would require
a separate contract decision, not a raw Responses escape hatch. IC-10 also shows `session.result()`
can contain a terminal incomplete response: use receipt status/finish reason before consuming it as
a completed answer. Quiet EOF and later failures do not erase an earlier valid result.

**S: sink/provenance ownership.** Diagnosis tools and ledger (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/agents/tools/diagnosis.py`)
remain the authority for `record_situation_diagnosis`, `record_sequence_step` and
`complete_sequence_of_events`. Preserve diagnosis headline/narrative/assessment/confidence,
supporting observations, unknowns, evidence IDs, situation type and citation IDs. Preserve step
position/description/timestamp/evidence IDs and completion ordering note. Data result envelopes
retain kind/tool/category/scope/columns/rows/truncated/historical_replay/fallback.

Keep `EvidenceLedger.note_call` on validated complete arguments, record only non-sink retrieval
results, and resolve evidence/citations only from this run's returned rows. The existing three sink
tools do not feed the evidence ledger. Missing evidence remains unsupported; no adapter may mint
provenance. Preserve diagnosis-not-recorded and unfinished-card/sequence handling, including explicit
tests for error/cancel paths rather than assuming frames after a `finally` execute on an exception.

**Sink completion decision:** current diagnosis exits when diagnosis and sequence are recorded and
all opened calls settle; it then closes the underlying turn. A fully consumed native tool cycle in
IC-07 performs another model request after its sink result. Exact early-close timing for the complete
diagnosis workflow is U: the producer may already be ahead of the consumer. Choose bounded native
completion or a separately designed public stop contract; do not claim close prevents an already
started request or introduce another tool loop to regain old stepping behavior.

## Lifetime And Custom Optimizer

**S/R: lifetime.** The retained response_events bridge (outside-guidance-not-advertised; source reference: `../../../../template_apps/shared/src/template_foundations/azure_llm/streaming.py`)
uses a synchronous worker, unbounded event queue and one pre-output transport retry, then awaits
its producer on close. The library owns an async stream with a 16-update queue, whole-run deadline,
no automatic retry and at most one additional second of native settlement with new work denied.
IC-12 proves local await cancellation only. Running sync tool threads, remote work, effects and
charges may continue. Cancellation is not rollback and cannot guarantee delivery of `aborted/done`.

The Investigation lifespan (outside-guidance-not-advertised; source reference: `../../../../template_apps/investigation_app/app/cybereye/backend/main.py#L36`)
injects a credential into ADX, but AgentService independently constructs its model credential/client;
that lifespan's explicit finalizer closes ADX, not the model client. Future composition must own and
close the shared model connection while leaving its borrowed credential lifetime with the host.
This is a migration consequence, not an unrelated cleanup performed here.

**S: shared consumer.** AzureLlmClient (outside-guidance-not-advertised; source reference: `../../../../template_apps/shared/src/template_foundations/azure_llm/client.py`)
offers lazy synchronous raw `respond/stream/embed`, per-call model overrides, arbitrary kwargs and
optional separate embedding endpoint. LlmConfig (outside-guidance-not-advertised; source reference: `../../../../template_apps/shared/src/template_foundations/azure_llm/config.py`)
defaults to 120-second per-request timeout/two SDK retries. Do not retire it while another real
consumer still depends on that surface; unused shared methods need an authorized consumer inventory.

Custom Optimizer's composition (outside-guidance-not-advertised; source reference: `../../../../template_apps/custom_optimizer/app/cybereye/backend/main.py`)
creates it with timeout 45/retries 1, passes `model.client` to `model_predictor`, and closes that
client at shutdown. The app adapter (outside-guidance-not-advertised; source reference: `../../../../template_apps/custom_optimizer/app/cybereye/backend/optimization/evaluation.py`)
delegates to the component predictor/evaluator (outside-guidance-not-advertised; source reference: `../../../../template_apps/custom_optimizer/app/components/agent_optimization/evaluation.py#L158`):
synchronous `client.responses.create(**request_builder(...))`, then `json.loads(response.output_text)`.
Evaluation can run those calls in `ThreadPoolExecutor`; its cancellation flag is checked before a
case, not proof of cancellation of an in-flight model request.

| Actual Optimizer Contract | Consequence For Migration |
| --- | --- |
| model_request (outside-guidance-not-advertised; source reference: `../../../../template_apps/custom_optimizer/app/cybereye/backend/optimization/profile.py#L77`) builds prompt/evidence input, model, reasoning `none`, `store=False`, native `text.format` | Preserve domain prompt/evidence and fixed one-model-call step; translate to binding instructions and public `response_format`. IC-02/03 prove raw forwarding/default capability fails. Exact dynamic JSON-schema/JSON-object equivalence still needs an app fixture. |
| Output tokens 350 for grade, 1200 for workflow | Explicit reviewed ceiling must admit 1200; default 1024 refuses. Do not silently cap the workflow or widen a request-supplied policy. |
| Workflow schema has grade enum, bounded diagnosis/actions and returned-document citation enum | Keep these app-owned constraints and postchecks; preserve result/error/capture semantics. Switching to `.value` must be validated against current dictionary contract, not assumed equivalent. |
| Synchronous predictor called from concurrent worker threads | Canonical connection belongs to one event loop. Prefer an async predictor and bounded host scheduling; do not run `asyncio.run` per worker against a reused connection. Any temporary host bridge needs an explicit owner/lifetime decision, not a new generic library transport. |
| Timeout 45, one SDK retry, cancellation before each case | New whole-run deadline/no-retry behavior changes attempts, latency/error metrics and cancellation. Preserve denominators and model-call-attempted evidence; rebaseline only through approved evaluation, not this offline task. |
| Domain Python tools and optional knowledge retrieval precede one grade call | Keep that workflow/evidence policy outside the model library. Do not convert it into a second generic model-controlled tool loop or migrate/execute an optimization campaign here. |
| Both app pins and shared OpenAI range remain 2.x | Consumer-complete composition/dependency migration is required before retiring shared model code. CLI token injection is a separate host path, not automatically replaced by the model connection. |

No optimizer package/runtime was promoted. No model campaign, labels, saved generations, scoring
policy, sandbox, CLI credentials or shared source was changed or exercised.

## Blocking Decisions And Next Slice

| Decision | Required Resolution / Discriminating Check |
| --- | --- |
| Schema preservation | Fix canonical binding's accepted raw-schema loss or deliberately unify app constraints in typed declarations without two drifting schema owners. Native request plus invalid-value refusal must both pass; IC-09 remains a visible known gap. |
| One dependency cohort | Integrator owns joined Python 3.12/OpenAI 3.13 resolution, app/foundation pins and artifact installs. Test both apps and their declared Pydantic version before adoption; no concurrent lock edits. |
| History/version behavior | Approve old-thread transition, visible transcript retention and fresh-session behavior even for same-shaped new versions. Exercise real owner lookup, assignment persistence and queued/in-flight requests. |
| Tool errors/incomplete output | Approve recoverable error allowlist versus strict stop, and refusal of incomplete tool execution. Check no unintended tool effect/next model call and safe UI errors. |
| Event and sink completion | Approve early metadata/reasoning-boundary changes and terminal de-duplication; test sink early-close against actual app ledger, budget and cancellation behavior. No assumption of zero extra model work. |
| Optimizer callable migration | Resolve async scheduling, format conversion, 1200-token bound, reasoning declaration and retry/metric changes. Run existing optimizer contract checks without a campaign. |
| Live/artifact acceptance | Exact target-bound authority and identified joined artifacts remain absent. LI-AGENT-01/02, LI-VERSION-01, LI-JOIN-01 and library-wide live coverage stay `NOT_RUN`; no quality proof. |

**Smallest next implementation slice:** assign the canonical model owner
AgentBinding._bind_tools (source-or-asset-not-bundled; source reference: `../../src/llm_interface/agents.py`) and its regression test to preserve
the supplied FunctionTool schema and strict argument validation through native binding. Reuse IC-09:
native `minimum=1` survives, value 0 executes no function and sends no follow-up request; ordinary
typed/Pydantic tools remain green. When fixed, replace the known-gap expectation and update this
record, rather than preserving the obsolete loss. No app migration, shared manifest, cloud call or
second tool loop is needed for that slice. Runtime paths were not assigned for this increment.

After that gate, one context-bound read-only Investigation tool and its SSE mapping can be the next
app slice once the integrator assigns paths and history/error decisions. Current increment stops
at coverage plus bounded compatibility proof; programme task status remains integrator-owned.