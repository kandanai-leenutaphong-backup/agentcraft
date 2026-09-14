# Value Over Existing Implementations

**Review position, 2026-09-15: reuse dependencies first.** The package earns its cost
only if coding agents have fewer decisions and less repeated integration work when making
correct model or agent calls. A renamed SDK method, another result wrapper or a smaller
directory count is not sufficient value.

**Is lower friction realistic? Yes, conditionally; it is not established by today's tests.**
Agent Framework already has short call sites and a common interface. Our additional value
must be a predictable entry point, complete setup examples, safe reusable defaults, useful
diagnostics and compatible swaps without provider-specific glue. Adding policy/receipt/event
concepts to every call site would defeat that goal, even if the implementation is correct.

The original design mixed host setup with ordinary calls and treated the reference app as
an integration target. That was too broad. The [caller guide](USAGE.md) now separates roles,
and validation uses independent synthetic consumers. The investigation app stays read-only:
no modification, tests, server or browser work is selected or implied.

This ledger covers the full [proposed scope](DESIGN.md), including agent execution.
Evidence IDs refer to [reproduced observations](VALIDATION.md#reproduced-observations).
`Validated` means a specific comparison was run, not that the proposed package exists.

## 1. Recommendation And Alternatives

| Alternative | What It Already Solves | Remaining Cost / Decision |
| --- | --- | --- |
| Provider SDK directly | Native features, credentials, connection reuse and API fidelity | Best for a simple provider-specific call; each host otherwise repeats the cross-provider contract and shared policy |
| Agent Framework directly | Common messages/results, multiple providers, structured output, streaming, sessions, middleware, tool schema/invocation | Recommended foundation; may be sufficient for a host whose existing policy already covers every requirement |
| Move azllm or modelaccess unchanged | Existing sync/async behavior, errors, embeddings, Entra recipes and MCP | Does not make raw Responses objects/options universal or provide the complete framework-native agent integration |
| Extend the reference app's current loop | Preserves its exact UI, diagnosis behavior and provider events | Not selected: read-only reference, not an integration target; app-specific code is not the universal interface |
| Adopt modular-agents unchanged | Definitions, tools, optional framework binding, and a separate policy-bound hosted runtime | Current API/version assumptions need reconciliation; hosted response text is emitted after completion, not native token streaming |
| Build a new agent/provider framework | Full control | Reject: duplicates tested upstream mechanisms and creates an unnecessary maintenance surface |
| Thin llm-interface over existing clients/runtime | One supported caller path with shared configuration/policy/integrity/event rules | Recommended only if standalone conformance and usability comparisons justify it; real adoption is a later separate claim |

The answer is not "our library is safer than Microsoft." Microsoft supplies extensible
mechanisms and enforces service permissions. We specify a host's narrower contract and
prove how it composes with those mechanisms. A careful application could implement the
same rules; reuse across named callers is what would justify a maintained package.

## 2. Capability And Value Ledger

### Upstream Functionality To Reuse, Not Claim As New

| ID | User Need | Existing Implementation | Our Contribution | Evidence / Limit |
| --- | --- | --- | --- | --- |
| V01 | Coding agents find and use one predictable interface, including compatible swaps | Framework `get_response`, `get_embeddings`, messages and result types already make basic calls short | One caller guide, complete host examples, actionable diagnostics and a tested binding convention with no provider-specific caller glue | F01 proves protocol interchangeability only; reduced setup effort and cognitive load require A26, not yet measured |
| V02 | Run a streaming agent with tools | Framework Agent, function invocation, sessions, middleware and streamed content | Bind policy/authorized tools and translate to the application's event contract; no new loop | F01 proves arguments, execution, results and next-model feedback |
| V03 | Structured output and embedding API | Framework/Pydantic/native SDK parsers and common embedding values | Only semantic/shape integrity and capability enforcement not already covered | F02/F04; schema parsing is upstream value |
| V04 | Entra identity, token refresh and connection pools | Azure Identity, OpenAI/Azure SDKs; existing packages already cache clients/providers | Explicit target/audience/auth profile, ownership and no implicit credential fallback | Existing-source/public API inspection; real token refresh and live audiences remain unverified |

### Existing Safeguards To Preserve And Consolidate

| ID | Shared Rule | What Already Exists | Proposed Residual Value | Evidence / Remaining Gate |
| --- | --- | --- | --- | --- |
| V05 | Only call a trusted destination | modelaccess host allowlists; native clients support explicit configuration; hosted runtime restricts endpoint shape | One construction and per-dispatch rule for all registered profiles, including options and redirects | L06 proves local allowlist refusal; complete new boundary and malicious override tests pending |
| V06 | Refuse unapproved work and bound every attempt | MCP call budgets; hosted RuntimePolicy; framework chat/function middleware and invocation limits | Shared immutable policy and atomic aggregate run budget for direct calls and inner model/tool calls | F01/F05 prove enforcement hooks and pre-transport refusal, not the complete budget implementation |
| V07 | Execute only authorized, validated tools | Existing application registry, modular ToolRegistry/RuntimePolicy, framework schema and invocation mechanisms | Same host decision for direct tool calls and agent calls; local/hosted tool permissions kept distinct | Native loop tested; target/argument/side-effect refusal and no-subsequent-call gates pending |
| V08 | Embeddings remain attached to the right input | azllm and modelaccess already validate count, indices, width and finite numbers | Preserve one strict implementation at a pre-normalization boundary while reusing framework/native decoding | F02 accepts malformed shapes; L01 rejects them; F06 proves a public interception point; production bounds pending |
| V09 | Partial output cannot masquerade as completed output | Existing helpers reject explicit failure events; application tool loop requires a terminal response | Consistent terminal-evidence requirement for every direct/agent path, including quiet EOF | F03 and L03/L04 reproduce the exact gap; package-wide fix not implemented |
| V10 | Deliberate retention | Existing convenience calls use `store=False`; framework exposes the option | Enforce chosen retention profile across every internal call and disallow request overrides | F04 proves omission versus explicit false; no claim about actual service retention or logging |
| V11 | No payload in ordinary errors/logs | Existing safe exception strings and result metadata | One safe mapping for all paths plus telemetry configuration and suppression of sensitive tracebacks | L05 proves provider text remains in exception causes; complete logging/OTel refusal checks pending |
| V12 | Correct ownership, async cleanup and cancellation | Native clients; modelaccess explicit ownership; existing stream close logic | Consistent borrowed/owned contract across integrations and cancellation effects stated honestly | L02 proves local ownership disagreement; full async/cancellation/concurrency parity pending |

### Integration And Operations Value, Not A New SDK

| ID | Application Outcome | Existing Pieces | Proposed Additional Contract | Evidence / Remaining Gate |
| --- | --- | --- | --- | --- |
| V13 | Event consumers do not need provider-specific parsing | Reference app SSE callbacks; framework content/update types | Versioned run events, correlation and terminal cleanup, exercised by a standalone consumer; browser adapter optional | F01 proves native events only; no reference-app adapter or browser work is planned |
| V14 | Long-running tools report progress | Tools can expose their own callbacks; framework middleware observes invocation | Optional bounded per-run progress emitter, ordered with model/results, separate from argument generation | New integration feature relative to the inspected app path; no implementation or measured benefit yet |
| V15 | Sessions stay owned and swaps do not lose context silently | Reference app ownership/locking and provider response IDs; framework sessions; hosted in-memory results | Bind connection/profile/definition to session; validate owner/swap behavior with a synthetic host, optional persistence through host store | Source contracts inspected; standalone validation pending, no existing app test is part of this work |
| V16 | One maintained implementation, independently installable | Current skills already ship installable packages and tests | Canonical ownership and conformance across real consumers, independent release, generated rather than edited bundles | Design only; no source retired, no consumer migrated, no artifact published |
| V17 | Existing remote agents use the same app-facing event conventions | Framework Foundry agent invocation and modular hosting integration | Later invocation profile with explicit remote-agent identity, capabilities and event mapping | Deferred; neither inference clients nor local function hooks prove remote execution parity |

No capability in this ledger claims to grant Azure access, provision a model, implement
authentication protocols or guarantee output correctness. Library policy is not a sandbox
against code using the same underlying credential.

## 3. Where The Comparison Changed The Design

### Common Interface Already Exists

F01 ran the same agent/tool source through `OpenAIChatClient` and
`OpenAIChatCompletionClient`. Both returned tool argument updates, invoked the fixture
once, returned a correlated result and completed the next model call. The proposed public
surface therefore reuses the framework contract rather than inventing a second message API.

This is stronger than constructor inspection, weaker than changing a live model provider.
Different qualities, tool behavior and supported features still need profile/evaluation gates.

### Policy Must Run Inside The Loop

F01 observed chat middleware before both native requests. F05 refused before any request.
The framework extension point is usable. A wrapper checking only the outer `agent.run()`
could miss internal attempts; a result wrapper checks too late. Atomic concurrency budgets,
tool refusal semantics and hosted-tool authorization remain new integration acceptance.

### Sorting Is Not Alignment Verification

F02 sends malformed native batches. The selected framework embedding client accepts duplicate
indices, a missing vector and inconsistent dimensions. L01 sends corresponding shapes to both
existing local public result parsers; they refuse. The value is preserving that rule, not
writing another embeddings API.

The framework's normalized embedding values no longer contain the original index. A
post-processing wrapper cannot discover all duplicate-index failures. F06 proves a public
native HTTP response hook can refuse before information loss. The production hook still
needs bounded reads, real per-request counts, cancellation and concurrency-safe correlation.
It should disappear if a supported upstream version enforces the required invariant.

### A Finished Iterator Is Not Finished Inference

F03 produces a created event and text delta, then EOF. The framework returns the text with no
finish reason. L03 confirms both local text-only helpers also accept quiet EOF. L04 confirms
they do refuse explicit failure. A future package must validate each native call's terminal
state, including tool loops, rather than claim EOF protection already exists everywhere.

### Ownership And Logging Are Compatibility Decisions

L02 verifies `azllm` closes a supplied client and `modelaccess` leaves it open. Neither can
be copied blindly into the other consumer. The proposed default is borrowing, with explicit
ownership transfer and migration tests.

L05 verifies safe exception text while the original provider text remains in `__cause__`.
Logging a full traceback can still expose data. Sanitized result objects alone do not prove
the service is free of sensitive logs. Framework and SDK observability are part of acceptance.

### Existing Hosted Runtime Is Not A Token-Streaming Replacement

The [modular hosting contract](../../.github/skills/modular-agents/CONTRACT.md) already
defines policy, bounded turns, owner-only result access, abort and correlated tool events.
Its model adapter supplies completed responses. The proposed native-streaming binding can
reuse those rules where compatible, but must not silently inherit the hosting limitations
or replace the hosted runtime as part of a model-connector migration.

## 4. What Stays Outside

- Application prompts, task plans, domain result schemas, knowledge citations and evidence
  validation remain with the investigation workflow.
- Azure/Entra authenticates and authorizes service access. The application authenticates
  users and authorizes records/tools. A workload identity authenticates neither a browser
  user nor another agent calling the app.
- The host owns session stores, result durability, authorization of read-back and disaster
  recovery. Reuse existing recovery capabilities when a workflow warrants them.
- Provider SDKs own protocol details, native async streams and supported feature models.
  Platform/framework clients own agent/tool mechanics. We do not reimplement them.
- Deployment, role grants, remote agent creation and resource lifecycle stay with existing
  deployment/hosting owners. Installing a package performs none of them.

## 5. Costs, Falsifiers And Non-claims

Costs introduced: a supported framework/provider version matrix; policy and event contracts;
adapter compatibility for native evidence; test and packaging maintenance; migration effort;
and an intentional dependency on Agent Framework's public types.

The existing modular-agents package currently declares `openai>=2,<3`, while these tests
use `openai==3.13.0`. Its framework binding also tests the class module prefix
`agent_framework`, whereas current provider classes live in `agent_framework_openai` or
`agent_framework_foundry`. These are source-verified integration risks, not proof that no
compatible combination or adapter exists. Full reuse must pass the current API tests first.

Stop or simplify the library when any of these is observed:

1. A named consumer needs only native framework configuration with no repeated custom rule:
   provide a recipe, not a wrapper.
2. A rule is only meaningful for investigation data: keep it in the application.
3. Upstream meets the strict requirement in a tested release: remove the redundant adapter.
4. A provider cannot meet required guarantees through supported extension points: advertise
   unsupported or omit its profile; do not fork the SDK or silently weaken the guarantee.
5. No real consumer adopts the package: do not claim consolidation because source was moved.

Unknown, not measured: developer time saved, app code reduction after migration, latency,
throughput, memory, Azure cost, model quality, fewer incidents and long-term maintenance
savings. No percentage or speed claim is inferred from synthetic tests. Compare caller and
setup friction against Agent Framework alone in a standalone, policy-equivalent exercise
without requiring an existing app migration. Production benefits need separately observed
adoption and workload evidence.

### Friction Claim And Falsifier

| Claim | Current Evidence | Decision |
| --- | --- | --- |
| Standardization is technically feasible | F01 runs the same agent/tool source with two framework client bindings | Supported within that offline two-protocol scope |
| Ordinary calls can avoid provider mechanics | Proposed guide keeps method names fixed and host/provider wiring separate | Plausible design; implemented caller path not demonstrated |
| This is easier than Agent Framework alone | No controlled fresh-caller comparison or complete package setup example exists yet | Unknown; do not advertise as measured improvement |
| A credential makes every agent safe to run | Credential only authenticates provider access; user/tool authorization is separate | False; authority must remain explicit even when setup is concise |

Use [A26](VALIDATION.md#low-friction-acceptance) to test discoverability, setup effort,
repeated calls, swaps and failure recovery. Count task decisions and wrong turns as well
as caller code; include host wiring and documentation lookups. A wrapper that adds another
API vocabulary or requires reading the architecture to make one call fails the objective.
If Agent Framework plus a recipe is equally easy and satisfies the same safeguards, prefer
that smaller solution over a package with no demonstrated marginal value.