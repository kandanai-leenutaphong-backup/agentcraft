# Frozen Model Coverage

**Baseline:** MODEL-COVERAGE-2026-09-15-v1. **Authority:** [Implemented contract](../../CONTRACT.md),
`llm-interface` 0.1.0a1, Python >=3.11. Contract SHA-256:
`d0b67983894afb5d1bca185d108ef8432e83d3bc552125ea0e3d3921a93a7eb3`.

T004 preparation and bounded offline T025 evidence only. No live runner, live feature module,
new candidate artifact, app migration, cloud operation or model inference was implemented here.
Every expanded case below has **live status `NOT_RUN`**. Target, principal, deployment/model
version, artifact digest, usage, cost, live quality and cleanup observations remain **unknown**.
Execution authority is **BLOCKED** pending exact target/identity/operation/budget approval.
Those are different facts: an unattempted case is not a successful refusal.

The [offline compatibility record](INVESTIGATION_COMPATIBILITY.md) describes reproduced facts
and known incompatibilities. Its passing experiments do not become `PASS_LIVE`, resolve G4,
or certify these complete feature cases. The raw tool-schema loss was subsequently repaired
and covered by source/artifact refusal regressions; its expected support remains unchanged.
The original contract hash above identifies the frozen baseline, not the amended source.

## Frozen Profiles

Expected support comes from the contract above, not `Connection.describe()`, installed extras,
the candidate's current output, or the provider used by Investigation. Do not remove a required
positive because a changed candidate reports a capability as false.

| Profile ID | Public Selection And Native Protocol | Credential And Additional Preconditions | Expected Operations |
| --- | --- | --- | --- |
| FND | `connect(..., provider="foundry")`; auto for `/api/projects/<project>`; `AIProjectClient` / `FoundryChatClient` | `foundry` extra; explicit sync/async `get_token` credential; default scope `https://ai.azure.com/.default` | CHAT, CHAT_STREAM, AGENT, AGENT_STREAM; EMBED with explicit deployment |
| AZR | `provider="azure_openai"`; auto for account origin; `OpenAIChatClient` Responses | Native OpenAI dependencies plus Azure Identity; explicit sync/async credential or token callable; default scope `https://cognitiveservices.azure.com/.default` | CHAT, CHAT_STREAM, AGENT, AGENT_STREAM; EMBED with explicit deployment |
| AZC | Explicit `provider="azure_completions"`; `OpenAIChatCompletionClient` | Same Azure identity requirements; no auto selection of Completions | CHAT, CHAT_STREAM, AGENT, AGENT_STREAM; EMBED with explicit deployment |
| OAR | Explicit `provider="openai"`; Responses | `openai` extra; caller's supported HTTPS base URL and native key/token callable; no Azure-auth fallback | CHAT, CHAT_STREAM, AGENT, AGENT_STREAM; EMBED with explicit deployment |
| OAC | Explicit `provider="openai_completions"`; Chat Completions | Same explicit non-Azure credential requirements | CHAT, CHAT_STREAM, AGENT, AGENT_STREAM; EMBED with explicit deployment |
| INJ | `from_clients(config, chat_factory=..., policy=..., capabilities=...)` | Named trusted adapter and real framework client; guards attached, exactly one native tool loop; native enforcement remains adapter-owned | Same common surfaces when explicitly implemented; EMBED additionally requires native index validation assertion and implementation |

All profiles: local typed tools and structured output are advertised. Reasoning is **opt-in**:
`Capabilities.reasoning` defaults false; a declared reasoning profile still needs live deployment
evidence. Embeddings default disabled without `embedding_model`. These required configured-positive
cases remain visible alongside missing-configuration refusals. An absent reasoning-capable model
or embedding deployment blocks its positive case; the refusal does not replace it.

No INJ production adapter is selected in this increment. Preserve that slot as `NOT_RUN`; common
guard tests do not prove its native routing, retry, byte-limit or pre-normalization enforcement.
Sovereign/private-cloud/custom-scope identity correctness remains unverified, not implied by URL
or scope syntax. Separate embedding accounts require separate connections.

## Case Identity And Evidence

Full stable ID: `<Case ID>.<Profile ID>.<Mode>`. Expand each row's provider set and mode list as
a Cartesian product. Example: `MODEL-T04-P.OAR.AGENT`. No other implicit wildcard or mode exists.
Assertions listed within a case are mandatory subchecks; retain their individual failures.

Registry: **56 case families, 761 expanded cases: 361 positive and 400 refusal cases**.
Required evidence classes: LOCAL 218, LIVE 295, FAULT 248. These are coverage cells, not a
minimum number of model calls, test functions or new files. Reuse exact evidence across cells
when it satisfies each independent oracle; keep their outcomes separately attributable.

- Provider sets: `BUILTIN` = FND, AZR, AZC, OAR, OAC; `AZURE` = FND, AZR, AZC;
  `ALL` = BUILTIN plus INJ. Comma lists name only the listed profiles.
- Modes: `BIND` = import/construction/description; `CHAT` = awaited `chat.get_response`;
  `CHAT_STREAM` = streamed `chat.get_response`; `AGENT` = awaited `AgentBinding.run`;
  `AGENT_STREAM` = streamed `AgentBinding.run`; `EMBED` = awaited `get_embeddings`;
  `LIFETIME` = connection/session/stream lifetime; `WORKFLOW` = imported composed feature calls.
- `P` = required positive outcome, which can include a truthful incomplete/refused model result.
  `R` = expected guard/failure outcome, never a substitute for `P`.
- `LOCAL` = deterministic no-network evidence; `LIVE` = identified installed artifact against
  an approved real service; `FAULT` = controlled fault at native I/O, offline or explicitly
  labelled hybrid when composed with a live service. Never manufacture load or weaken auth.
- Scenario names below are **planned module identifiers**, not existing files or commands.
  Each future feature module needs public imports, one callable operation/check and a thin main;
  direct execution and deployment orchestration use the same guarded entry point.

## Feature Registry

All rows are frozen requirements, not passed tests. The denominator includes every expanded
profile/mode case, even when no script, extra, fixture, target or authority exists yet.

| Case ID | Providers | Modes | Independent Oracle / Expected Outcome | Evidence | Planned Scenario |
| --- | --- | --- | --- | --- | --- |
| MODEL-C01-P | BUILTIN | BIND | Explicit fields and `ConnectionConfig` select the contract's fixed endpoint/model/profile; import, construction and description cause zero token acquisitions and zero model requests; native extras stay lazy. Inspect counters outside the library. | LOCAL | construction |
| MODEL-C01-R | BUILTIN | BIND | Reject non-HTTPS, user-info, query, fragment, nondefault port, unsupported path, nonallowed exact host, missing model/credential and ambiguous policy before I/O. No request can choose or widen the target. | LOCAL | construction |
| MODEL-C02-P | AZURE | CHAT | Real sync credential reaches the selected native provider with the declared audience; refresh uses the identity provider, not a cached raw bearer token. Credential remains borrowed. | LIVE | credentials_sync |
| MODEL-C02-R | AZURE | BIND | Azure static key/string is not an Entra credential; Foundry also refuses a token callable without `get_token`. No token or model call on refusal. | LOCAL | credentials_sync |
| MODEL-C03-P | AZURE | CHAT | Real async credential uses the matching native async token provider; same audience/refresh/borrowing oracle as sync, not inferred from a sync pass. | LIVE | credentials_async |
| MODEL-C04-P | AZR,AZC,OAR,OAC | CHAT | Approved sync and async token callables are exercised independently; native calls receive refreshed supplier output, not an Azure fallback for OAR/OAC. Never retain token values in evidence. | LIVE | credential_callable |
| MODEL-C05-P | OAR,OAC | CHAT | Explicit provider credential and supported base URL succeed through the public connection; structural result and target observer agree. This is not Azure identity evidence. | LIVE | provider_credential |
| MODEL-C06-P | INJ | BIND | Factory receives the guards and invocation enablement; borrowed dependencies stay borrowed; owned duplicates close once. Adapter conformance establishes its native guarantees separately. | LOCAL | injected_adapter |
| MODEL-C06-R | INJ | EMBED | Missing native embedding validation assertion refuses before returning vectors; assertion alone is not proof that the adapter validates indices. | LOCAL | injected_adapter |
| MODEL-P01-P | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Explicit model-call grant permits the approved operation only; actual native attempt counts and receipts stay within frozen limits. Tool grants remain separate. | LIVE | policy |
| MODEL-P01-R | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Default model denial causes zero native dispatches. Local permission never grants Azure RBAC or app-record access. | LOCAL | policy |
| MODEL-P02-P | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Preselected required capabilities succeed on the approved deployment; native response structure and observed execution prove support independently of `describe()`. | LIVE | capabilities |
| MODEL-P02-R | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Each false required capability refuses before dispatch; unknown required agent capability refuses. Keep the configured-positive rows required. | LOCAL | capabilities |
| MODEL-I01-P | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM | Text, one `Message`, list/tuple of Messages, text/local function/result/usage/summary content preserve ordered native meaning. Caller mutations after invocation do not change the snapshotted request. Agent instructions remain fixed. | LIVE | messages |
| MODEL-I01-R | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM | Invalid input shape, unsupported image/URL/file/audio/hosted content and excessive input refuse; no silent truncation or generic content coercion. | LOCAL | messages |
| MODEL-O01-P | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM | `max_tokens`, finite bounded sampling, `tool_choice`, `parallel_tool_calls`, matching fixed `model` and `store=False` reach the native request with intended semantics. Direct tool declarations do not execute functions. | LIVE | options |
| MODEL-O01-R | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM | Unknown/raw SDK body/header/URL fields, public instruction overrides, `previous_response_id`, alternate model, `store=True`, invalid sampling and excessive token ceiling refuse before dispatch. Agent per-run tool overrides refuse. | LOCAL | options |
| MODEL-O02-P | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM | Explicit reasoning capability and approved supporting model forward public effort/summary settings. Inspect public summary content, not hidden reasoning; retain empty opening updates and actual IDs where emitted. | LIVE | reasoning |
| MODEL-O02-R | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM | Reasoning without declared capability or unsupported keys/settings refuses locally. Current accepted efforts exclude app effort `max`; no silent downgrade to another effort. | LOCAL | reasoning |
| MODEL-F01-P | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM | Frozen Pydantic schema validates `.value`; output satisfies required fields/enums/types. Observe finish/refusal independently. A plausible string is not a structured-output pass. | LIVE | structured_output |
| MODEL-F01-R | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM | Disabled structured capability refuses; malformed or refused model output must not be represented as a valid schema value. Preserve validation and completion evidence. | FAULT | structured_output |
| MODEL-E01-P | ALL | EMBED | Explicit deployment accepts 1-2048 nonempty texts and optional dimensions within bounds; exactly one finite, nonempty, correctly sized vector per input. Independent per-text native observation checks alignment under a frozen numeric tolerance. | LIVE | embeddings |
| MODEL-E01-R | ALL | EMBED | Missing embedding deployment/capability, empty/oversized/nontext input, invalid dimensions, base64/token-ID/image encoding or unsupported options refuses. A different account is not an implicit fallback. | LOCAL | embeddings |
| MODEL-E02-P | ALL | EMBED | A valid reversed native batch normalizes to input-index order, retaining upstream embedding and usage types; no vector is attributed by arrival position. | FAULT | embedding_integrity |
| MODEL-E02-R | ALL | EMBED | Missing/duplicate/noninteger/out-of-range indices, wrong count, empty/nonfinite/nonnumeric vectors or inconsistent dimensions return no usable batch. Inject before native normalization. | FAULT | embedding_integrity |
| MODEL-T01-P | ALL | AGENT,AGENT_STREAM | Typed sync/async functions and framework FunctionTools execute in the single native loop with exact granted names; sync tools run off-loop. Independent tool ledger and next native request agree on call/result identity. | LIVE | tools |
| MODEL-T01-R | ALL | BIND | Duplicate/ungranted names, hosted/declaration-only tools and interactive approval modes refuse binding. No tool or model effect. | LOCAL | tools |
| MODEL-T02-P | ALL | AGENT,AGENT_STREAM | Sync and async `authorize_tool(ToolCall)` returning exactly `True` receive correct principal, run ID, call ID and copied arguments before execution. | LIVE | tool_authorization |
| MODEL-T02-R | ALL | AGENT,AGENT_STREAM | False, non-True and denied authorization cause no denied function execution and no subsequent model request. Already-started authorized siblings may have effects; do not claim batch rollback. | FAULT | tool_authorization |
| MODEL-T03-P | ALL | AGENT,AGENT_STREAM | Complete valid argument batches preserve IDs and strict input types before any execution. Independent counters prove one execution per call ID and the shared model/tool budgets. | LIVE | tool_arguments |
| MODEL-T03-R | ALL | AGENT,AGENT_STREAM | Unknown names, duplicate call IDs, extra/wrong-type/malformed arguments and incomplete tool calls refuse before the invalid batch executes. No hidden retry, partial batch validation or coercion. | FAULT | tool_arguments |
| MODEL-T04-P | ALL | AGENT,AGENT_STREAM | Constraints of supplied public FunctionTool declarations survive agent binding: required fields, additional-properties policy, enums, scalar/array bounds. Compare predeclared schemas with native requests; cover callable, Pydantic and mapping declarations separately. | FAULT | tool_schema |
| MODEL-T04-R | ALL | AGENT,AGENT_STREAM | Values violating declared constraints do not execute. The initial mapping-constraint loss is repaired in the current source/artifact; retain its invalid-value, nested/reference and whole-batch regressions. Live coverage remains unrun. | FAULT | tool_schema |
| MODEL-T05-P | ALL | AGENT,AGENT_STREAM | Original bounded finite JSON, including a host-approved recoverable error object, reaches the next model request unchanged. Sink payloads do not create citation provenance. | LIVE | tool_results |
| MODEL-T05-R | ALL | AGENT,AGENT_STREAM | Thrown exceptions sanitize to `tool_failed`, stop further model work and interrupt session reuse; arbitrary objects, nonfinite JSON and oversized results refuse. No exception payload leaks through public cause/error metadata. | FAULT | tool_results |
| MODEL-T06-P | ALL | AGENT_STREAM | Explicit async-tool `report_progress` retains bounded original payload and call ID after authorization; it is neither model arguments nor a fabricated result. | LIVE | tool_progress |
| MODEL-T06-R | ALL | LIFETIME | Progress outside an executing streamed async tool refuses; invalid/oversized progress refuses. Nonstreaming callers cannot silently run progress-only tools. | LOCAL | tool_progress |
| MODEL-S01-P | ALL | AGENT,AGENT_STREAM | Owner-bound sessions serialize turns and preserve ordered local history under `store=False`; fresh omitted session is single-turn. Result reads are copies, require the owner and cause no provider request; failed later run preserves the prior result. | LIVE | sessions |
| MODEL-S01-R | ALL | AGENT,AGENT_STREAM | Wrong owner, changed binding/definition, interrupted session and oversized history refuse before another model request; no caller-provided provider conversation ID, implicit transcript transfer or silent history truncation. | LOCAL | sessions |
| MODEL-S02-P | ALL | AGENT_STREAM | Every declared RunEvent shape follows schema version 1, one run ID and monotonic sequence. Tool starts follow authorization; call/result IDs match. A normally consumed run has exactly one terminal event and matching receipt/counts. | LIVE | run_events |
| MODEL-S02-R | ALL | AGENT_STREAM | Tool/provider failure yields safe `tool.failed` where applicable and `run.failed` plus raised `LlmError`; no false completion or duplicate terminal. Cancellation/disconnection is not required to deliver an event. | FAULT | run_events |
| MODEL-S03-P | ALL | CHAT_STREAM,AGENT_STREAM | Terminal incomplete text and model refusal remain partial/refused, not completed answers. Agent terminal is `run.incomplete`/`run.refused`; retained result status is inspected before use. | FAULT | stream_completion |
| MODEL-S03-R | ALL | CHAT_STREAM,AGENT_STREAM | Quiet EOF, explicit native failure or incomplete tool output cannot become normal success. Preserve already-emitted partial output and raise the matching safe failure after bounded settlement. | FAULT | stream_completion |
| MODEL-S04-P | ALL | CHAT_STREAM,AGENT_STREAM | `get_final_response()` reads the same execution after consumption, including repeated reads; native request count does not increase. Owner `session.result()` reads back the prior result independently of the event list. | LIVE | stream_readback |
| MODEL-L01-P | ALL | LIFETIME | Async context management and idempotent close settle streams, close owned clients once and leave borrowed credentials/transports open. One connection uses one event loop; parallel independent runs do not share tool state. | LOCAL | lifetime |
| MODEL-L01-R | ALL | LIFETIME | Closing active work or cancelling/abandoning a stream interrupts local execution and prevents implicit session replay; subsequent closed-connection or cross-loop use refuses. No rollback, stopped sync thread or zero remote cost is inferred. | FAULT | lifetime |
| MODEL-L02-P | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Frozen positive limits permit bounded work; connection slots cap concurrency and a 16-update stream queue backpressures a slow consumer. Instrument request/tool/queue behavior externally, not with `describe()` values. | FAULT | limits |
| MODEL-L02-R | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Invalid bool/nonpositive/nonfinite limits and concurrency outside 1-64 refuse. Whole-operation deadline includes slot wait/backpressure; native calls, tool calls/results, serialized bytes and events stop at their separate bounds. No implicit retry after effects. | FAULT | limits |
| MODEL-N01-P | BUILTIN | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Native requests use only pinned inference routes, fixed deployments, explicit identity, `store=False` for chat/agents, float embeddings and zero hidden SDK retries/environment proxy routing. Observer validates destination and counts. | LIVE | native_transport |
| MODEL-N01-R | BUILTIN | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Redirect/off-target/native-route violations refuse; native byte bounds and malformed terminal evidence survive SDK normalization. No forwarded credentials to a redirected host. | FAULT | native_transport |
| MODEL-N02-R | BUILTIN | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Native 401/403, 404, 429, 5xx and transport failures surface safe error categories with no payload/cause or automatic retry. Local fault injection is not proof of a real provider denial. | FAULT | native_errors |
| MODEL-N03-R | AZURE | CHAT,EMBED | An approved restricted identity actually fails service authorization on the exact permitted target; independently approved observer confirms no forbidden effect. Local policy denial cannot satisfy this case. | LIVE | provider_denial |
| MODEL-N04-R | ALL | CHAT,CHAT_STREAM,AGENT,AGENT_STREAM,EMBED | Payload-capable SDK/framework DEBUG logging, sensitive framework telemetry and Azure Projects console logging refuse before use. Safe receipts contain counts/status, not prompt/tool/vector bodies. Arbitrary external instrumentation remains host-owned. | LOCAL | logging |
| MODEL-D01-R | BUILTIN | CHAT | In an authorized base-only artifact environment, first use of a missing native extra yields actionable dependency failure; construction still performs no I/O. Never install into a shared test environment to satisfy the case. | LOCAL | dependency_extras |
| MODEL-W01-P | ALL | WORKFLOW | Import feature functions: invoke -> pass actual output to structured step -> authorized tool-using stream -> inspect terminal -> read final/session result without another model call. Check immutable synthetic tool/evidence IDs and all component receipts. | LIVE | invoke_structured_tool_readback |
| MODEL-W01-R | ALL | WORKFLOW | Refused owner/tool/budget or interrupted step stops dependent work; retain prior results and reconcile possible effects. No subprocess-stdout composition, second tool loop or blind replay. | FAULT | invoke_structured_tool_readback |

The fixed limit oracle is the contract's tuple: timeout 120 seconds; model calls 8; tool calls 16;
output tokens 1024; input bytes 128000; output bytes 1000000; tool-result bytes 60000; concurrency 4
(valid 1-64); events 10000. Native bytes/events and emitted content have separate aggregate bounds.
These are process/run limits, not replica-wide limits or billing quotas.

For MODEL-S02-P, the frozen event vocabulary is `run.started`, `text.delta`,
`reasoning.summary.delta`, `tool.call.delta`, `tool.call.ready`, `tool.started`, `tool.progress`,
`tool.result`, `tool.failed`, `usage`, `run.completed`, `run.incomplete`, `run.refused`, `run.failed`.
Assert each event under its triggering case; do not require every kind in one successful run.
No promise of SSE hosting, network exactly-once delivery, event replay or automatic resumption exists.

## Consumer Cases Remain Separate

The following consumer acceptance cases are not additional library-provider combinations
and are **all `NOT_RUN`** for app acceptance.

| Seed | Required Public/Host Observation | Library Families / Remaining Host Check |
| --- | --- | --- |
| LI-AGENT-01 | Approved Investigator tools produce supported citations and ordered sequence with truthful completion | T01-T06, S02-S04, W01; real app ledger, sink early-stop semantics and analyst journey still unrun |
| LI-AGENT-02 | Wrong owner/tool/arguments/budget and interrupted work refuse without replay | P01-P02, T02-T05, S01, L01-L02; real authenticated app refusal and approved provider negatives still unrun |
| LI-VERSION-01 | Saved assignment reads back; running request remains pinned; next request uses fresh version/session according to approved history decision | S01; actual AgentEditor/SessionStore concurrency and unchanged visible transcript still unrun |
| LI-JOIN-01 | Identified joined artifacts work in Investigation and affected Custom Optimizer callable/browser workflows | No application substitution occurred; Python 3.12 integration, shared pins, predictor scheduling and app tests remain required |

## Execution And Accounting

Before any live attempt: identify wheel/sdist and digest, installed import origin, Python/OS and
native dependency versions; approve exact provider/endpoint/model/identity, operations, synthetic
fixtures, call/token/time/data/concurrency/spend bounds, lifetime and cleanup ownership. No existing
Azure login or blanket programme autonomy supplies that authority. Use the owning deployment entry
point when implemented; this document creates no alternative operator command.

Freeze structural expectations and synthetic fixture values before inference. A separate SDK
observer may corroborate target/vector/evidence state but never substitutes for the library call.
Do not require exact free-form prose. Quality needs a separately approved versioned dataset, scorer,
threshold and retained outcomes; **no live quality proof exists here**.

A future runner must materialize every full ID before execution and report expected, attempted,
passed-positive, passed-refusal, failed, blocked and unrun counts separately, with evidence class.
Only a real positive service case can be `PASS_LIVE`; a `PASS_REFUSAL` names local versus service
enforcement. Unknown observations stay null/unknown. Missing scripts, extras or targets never shrink
the denominator. A required `FAIL`, `BLOCKED`, `NOT_RUN`, mismatched refusal or unresolved cleanup
prevents capability-complete acceptance. Controlled faults on real operations are labelled hybrid.

Retain receipts under the owning deployment records location, with case/workflow IDs, contract and
artifact identities, approved target/principal references, UTC times, run/request IDs, observed
status/count/digest/usage and cleanup state. Never include credentials, raw customer content or
unreviewed model/tool payloads. No resource or fixture was provisioned by this increment.

Runtime/dependency/contract changes require affected cases to be rerun against new identified bytes.
An explicit support change versions this baseline and preserves old failed/unrun rows; changing
`describe()` output cannot rewrite the oracle. Planned live modules must be outside default offline
test discovery, perform no I/O at import and refuse execution without explicit live preflight.