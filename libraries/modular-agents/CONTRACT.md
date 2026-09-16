# Modular Agent Contract

## Definition

`load_definition(control_dir, agent_id=..., allowed_prefixes=())` resolves the whole
roster before selecting an agent. Empty import grants deny all tool imports. Prompt
traversal, missing prompts, duplicate hosted tool names, unresolved annotations,
credentials in tool parameters and interactive-approval tools refuse before execution.
Configuration is operator-authored, not a model/MCP payload. `AgentSpec` remains the
coherent shared definition; no per-file compatibility wrapper package exists.

`ToolRegistry` owns schemas and direct validated invocation. `native_tools` adapts that
same invocation to native `llm_interface.tool`; tool bodies execute once. ToolSpec
validation, result envelopes and measurement remain with `toolshape`. Duplicate
suppression is per turn; it is not permission to retry an external side effect.

## Runtime

`RuntimePolicy` is immutable and denies model/tools by default. `execution_policy()`
maps its units to native `llm_interface.Policy` and `Limits`. A supplied connection
must match the exact model, grants and limits; the adapter never silently widens or
ignores an operator policy. Tool/model rounds, result sizes and timeout are enforced
by the single native executor. No model or raw SDK loop remains here.

`AgentRuntime.call`, `chat_events`, `result`, and `abort` require host-established
principal identity. Another owner cannot read or cancel a turn. HTTP accepts only
the declared invocation schema and sends `Cache-Control: no-store, private`.
Transport event mapping preserves token/tool events and one terminal done/error/aborted
outcome. Native incomplete output is not success. `aclose` cancels active work and
refuses new calls; borrowed connections remain caller-owned.

The last 128 completed turns are retained in-process only. No multi-replica/session
durability is claimed. A timed-out synchronous tool may outlive cancellation; its
external effects remain unknown. Tool bodies must enforce their own exact data grants.

## Bundles

`build_bundle` accepts explicit imported tool source roots, an output directory,
policy and target. It refuses symlinks, source mismatches, secret-shaped content,
unknown policy tools, targetless model grants and path-based dependency requirements.
Artifacts are content-addressed, never clobbered, and verified by `load_bundle`.

Bundles contain only host tool sources, resolved configuration, schemas, a runtime
launcher and exact canonical distribution requirements. They do not bundle copies
of `agentconfig`, `toolshape`, `hostedagents` or `llm_interface`. A caller-supplied
requirements file must include the selected releases. Remote builds require those
releases to exist on an authorized package source; local wheel tests do not prove that.
Building is local artifact creation only, never deployment or inferred permission.

## Conformance

| Standard | Selected Result / Remaining Gap |
| --- | --- |
| F1 | Distribution, coherent APIs and contracts named; generated parent catalogue/descriptor integration pending |
| F2 | Normal native dependency family, public type markers, wheel checks and declared provider extras; no skill source resolution |
| F3 | Immutable policy, empty default tool/model grants, matching connection, import/credential/path refusals; legacy roster YAML is not appcompose canonical JSON |
| F4 | Refusal/error envelopes and safe native failures; shared framework failure metadata not yet applied to all direct tools |
| F5 | Async adapter close, native cancellation, borrowed connection ownership; synchronous tool interruption is not guaranteed |
| F6 | One native limit/retry owner; no independent round loop; direct tools have a bounded host timeout |
| F7 | Native stream mapped once; owner-only bounded result store; legacy invocations event names remain, not common framework event conformance |
| F8 | Typed tool adapters, offline fixture/request counts, package and refusal checks; native Foundry hosting and live identity remain unverified |

Full portfolio/framework completion is not asserted. No deployment, cloud writes,
grants, model inference or publication is performed by migration acceptance.