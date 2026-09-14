# Caller Guide

**Proposed interface, not an installed library.** This is the intended first-use entry
point for a coding agent. The examples describe acceptance targets, not working `llm_interface`
imports today. Framework mechanisms beneath them have separate [validation](VALIDATION.md).

## Before Calling

The host supplies an authorized `connection`, or an `agent` and its owner-checked `session`.
It configures the target, credentials, grants and execution bounds once and owns their
lifetime. Missing setup is a configuration error, not a reason to guess an endpoint, pick
another credential or grant access. Inspect `connection.describe()` without making a call.

## Choose One Operation

| Task | Standard Operation | Read Back |
| --- | --- | --- |
| Model response | `await connection.chat.get_response(messages)` | Framework response text, finish reason and usage |
| Structured response | Same method with `options={"response_format": MySchema}` | Validated framework result, or explicit refusal/incomplete state |
| Embeddings | `await connection.embeddings.get_embeddings(texts)` | Ordered, validated vectors and observed usage |
| Agent turn | `await agent.run(message, session=session)` | Final agent response; registered tools run under host authority |
| Streaming agent | `agent.run(message, session=session, stream=True)` | Versioned events and `await stream.get_final_response()` |

Messages and schema types use the existing framework/Pydantic contracts. The package's
supported public exports and examples must make those imports explicit; callers should
not have to search a provider SDK. No alternate `ask`/`respond`/`complete` naming family
is required for the supported portable surface.

```python
response = await connection.chat.get_response(messages)
```

```python
stream = agent.run(message, session=session, stream=True)
async for event in stream:
    consume(event)
final = await stream.get_final_response()
```

These snippets intentionally start after host setup. Full runnable offline setup examples
are a release requirement; a collection of undefined handles alone is not low-friction
adoption. Never execute a second call just to retrieve a stream's final result.

## Predictable Boundaries

- Changing provider changes an approved connection binding, not these operation names.
  Required capabilities must match; provider conversation IDs are not interchangeable.
- Direct model calls return tool requests without executing functions. Agent mode uses
  the one framework loop to invoke approved tools. Streaming arguments are not tool progress.
- Incomplete/refused output is not a complete answer. Denied, unsupported, malformed or
  interrupted work has a stable safe code and a documented next action; never blind retry.
- Host configuration owns credentials, tool permissions, retries and resource cleanup.
  Do not pass them through prompts or use raw SDK options to bypass a refusal.
- Additional result storage, browser/SSE wiring and remote-agent hosting are optional
  integrations. They are not prerequisites for a library call.

## Acceptance

The friction claim is **realistic but unproven**. Framework already makes basic calls
short; another package only helps if it removes repeated decisions, not merely lines.

Proposed release experiment: give a fresh coding-agent session this guide, the package
and a synthetic host fixture, with no provider-specific hints. Ask it to make a response,
embed inputs, run a tool-using streaming agent, inspect the final result, switch a compatible
binding and diagnose one intentional refusal. Do not use the investigation application.

Compare with Agent Framework alone under the same tasks, tools, policy and fixtures.
Record actual documentation lookups, clarification requests, provider-specific choices,
custom glue, failed attempts and time to first correct result. Keep host setup effort
separate from repeat-call effort; do not hide it in the fixture when evaluating adoption.

Pass the structural minimum: every task is reachable from this guide; no private/provider
SDK imports or native-event parsing in caller code; no caller-authored tool loop; no caller
code changes for a compatible binding swap; refusals explain the supported next action
without exposing payload. The negative case must remain refused, never bypassed for brevity.

Until that experiment runs against an implemented package, report friction and cognitive-load
reduction as unknown. Existing dependency tests prove feasibility and safeguards only.