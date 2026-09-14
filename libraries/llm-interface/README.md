# LLM Interface

**Status: design for review, 2026-09-15. Dependency-first direction agreed; runtime
implementation, consumer migration and publication are not authorized by this document.**

**Primary goal: reduce the decisions and code a coding agent needs to make a correct model
or agent call.** Configure approved connections and credentials at the application edge;
ordinary callers then use one documented interface without learning provider plumbing.

Start with the [caller guide](USAGE.md), not the architecture packet. Its proposed calls
are not implemented yet. Reduced cognitive load is a testable goal, not a measured benefit.

**Scope correction:** the investigation app is a read-only reference for capability
requirements, not a named integration or migration target. Do not modify it, run its tests,
start its server or drive its browser for this work. Use independent synthetic examples
under this directory. A later application integration requires separate agreement.

## Review Packet

| Document | Question Answered |
| --- | --- |
| [Caller guide](USAGE.md) | What is the shortest correct path for a coding agent to call a model or run a streaming agent? |
| [End-to-end design](DESIGN.md) | What is the complete application experience, contract, ownership and delivery sequence? |
| [Value and alternatives](VALUE.md) | What do we add beyond Agent Framework, provider SDKs and the existing local implementations? |
| [Validation and acceptance](VALIDATION.md) | What was actually tested, and what must pass before implementation or migration is considered complete? |
| [Framework comparison](tests/test_framework_comparison.py) | Can existing framework clients already support the proposed core interaction? |
| [Existing-contract comparison](tests/test_existing_contracts.py) | Which local guarantees and compatibility differences must be preserved deliberately? |

## Decision In Brief

**Reuse Microsoft Agent Framework for model clients, message/result types, structured
output, streaming and the model/tool execution loop. Add only reusable policy,
integrity, lifecycle and application-event integration that has a named consumer.**

Do not build another universal SDK, HTTP client, agent loop, tool schema generator,
credential chain, YAML loader, persistence engine or deployment service.

Proposed distribution name: `llm-interface`; proposed import: `llm_interface`.
Neither name is reserved or published. No installable package exists here yet. This
directory is not a uv workspace member and adds no dependency to the shared lock.

## What Was Validated

- The same synthetic agent definition and tool implementation run through the framework's
  Responses and Chat Completions clients, with streamed arguments, correlated results,
  exactly one fixture-tool invocation and the final answer. This is two protocols of one
  provider family, not live cross-provider parity.
- Framework chat middleware executes before each of the two internal model calls and
  can refuse before native transport. Structured results and explicit `store=False` work.
- The tested framework embedding client sorts results but accepts duplicate indices,
  missing vectors and unequal widths. Both existing local packages reject those shapes.
- A quiet stream EOF can return text without a completion reason. Both local text-only
  helpers also accept quiet EOF, despite refusing explicit provider failure events.
- A public native HTTP response hook can reject an invalid embedding before framework
  normalization loses its indices. The probe is not a bounded production interceptor.
- Borrowed-client ownership differs between the local packages. Their safe exception
  strings do not make full tracebacks safe to log.

Exact versions, commands and limits belong to [the validation record](VALIDATION.md).
Passing comparisons prove dependency behavior and design feasibility, not delivery of
the proposed library's security controls, event adapter or persistence contract.

## Intended Application Shape

| Need | Application Supplies | Standard Call |
| --- | --- | --- |
| One response or structured result | Authorized input and required capabilities | `connection.chat.get_response(...)` |
| Streaming model response | Same input plus stream consumer | `connection.chat.get_response(..., stream=True)` |
| Embeddings | Explicit embedding connection and bounded inputs | `connection.embeddings.get_embeddings(...)` |
| Tool-using agent | Definition, registered tools, owned session and run authority | `agent.run(..., stream=True)` |
| Browser integration | Existing HTTP authorization and presentation callbacks | Application adapter consumes versioned run events |

These are proposed integration shapes. Agent Framework already implements the underlying
calls; the guarded connection factory and application run-event binding remain proposed.

## Review Decisions

1. Keep Agent Framework's public Python types and protocols as a deliberate dependency,
   not a promise that arbitrary agent frameworks can be exchanged without adaptation.
2. Test a standalone synthetic streaming tool loop alongside one-off calls and embeddings.
   The investigation app illustrates requirements only; it is not a release acceptance target.
3. Bind agent definitions to logical connection IDs, not provider-specific deployments.
   Swaps require compatible capabilities and a fresh or explicitly migrated session.
4. Default direct calls to no automatic tool execution. Enable exactly one framework
   tool loop for agents, with host-supplied authorization at every tool invocation.
5. Keep Azure authentication Entra-only; host injects credentials. Native provider
   authentication outside Azure is a separately configured integration, never a fallback.
6. Keep synchronous legacy callers and raw Responses callers working until named migrations
   pass. Do not silently narrow their contract under an unchanged package version.
7. Do not introduce a second maintained agent-definition loader. Compare and adapt the
   existing modular-agent contracts before reusing their current runtime bindings.
8. Keep provider selection, credentials, policy wiring and event adaptation out of ordinary
   call sites. Require an independently demonstrated low-friction caller path, not only
   successful dependency tests; see the [usability acceptance](USAGE.md#acceptance).

## Limits

No live model calls, RBAC changes, remote agent creation, application modifications,
source retirement or registry publication occurred. Production policy enforcement,
full application/browser parity, independent package artifacts, actual non-OpenAI
provider substitution, live identity and performance benefits remain unverified.

The design and evidence are the durable record. No repository notebook is installed;
none is added solely for this work. Existing library documentation and concurrent
connector work remain unchanged.