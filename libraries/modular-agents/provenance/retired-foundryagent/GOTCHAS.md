# GOTCHAS — foundry-agent-runtime

Fourteen ways this fails in production, symptom first. Every entry was hit on a
running deployment except where noted. Numbers are stable: code cites them.

---

## G1 — Agent creation fails with an authorization error that has nothing to do with authorization

**Symptom.** Config looks right, the identity has a role assignment, the token
mints fine, and every attempt to create or run an agent returns 401, 403 or 404.
The message names permissions, not the endpoint.

**Cause.** The endpoint is the **account** endpoint
(`https://<resource>.services.ai.azure.com`) rather than the **project**
endpoint (`https://<resource>.services.ai.azure.com/api/projects/<project>`).
The account endpoint exists and answers, so nothing looks malformed; it simply
does not host the Agents API for a project. The portal shows both and the labels
are similar enough to swap without noticing.

**Fix.** Check for the `/api/projects/` segment.
`FoundryConfig.warnings()` reports its absence; `scripts/probe.py` prints it.

**Rule.** When two endpoint forms differ only by path and one of them answers,
the failure will always be reported as a permissions problem. Check the shape
before you check the role assignment.

---

## G2 — One agent starts answering with another agent's tools or history

**Symptom.** An agent references a document it was never given, or calls a tool
that is not in its roster entry. Intermittent, worse under concurrency, and
never reproducible in a single-agent test.

**Cause.** One SDK client instance shared across the whole roster. Agent Framework
clients carry per-agent state — thread and tool registration among it — and a
shared instance lets whichever agent registered last win.

**Fix.** One client per agent id. `ClientPool` is exactly that and nothing else.
Do not "optimise" it into a single client; the construction it saves is once per
agent per process.

**Rule.** Isolation boundaries in an SDK are rarely documented. When state bleeds
between callers, look for an object shared across a boundary the SDK considers
significant.

---

## G3 — Intermittent auth latency at startup that nothing in the app explains

**Symptom.** Cold start is slow and uneven. Traces show time inside credential
acquisition, not inside the model call. It clears once warm and comes back on
every deploy.

**Cause.** A credential built per client. A `DefaultAzureCredential` is a token
cache; building N of them for N agents throws away the cache N−1 times and sends
N cold token requests to an identity endpoint that is itself rate-limited.

**Fix.** One credential per process. `get_credential()` caches it behind a lock
and every client in this box takes it from there.

**Rule.** Any object described as "handles caching for you" is a singleton whose
lifecycle is your problem.

---

## G4 — The service rejects a request from an agent that has no tools

**Symptom.** Agents with tools work. An agent with none returns a schema or
validation error from the service, not from your code.

**Cause.** `tools=[]` is a declaration that the agent has a tool set, and it
serialises to an empty tool schema. Some service versions reject that where they
would have accepted the field being absent.

**Fix.** Pass `None`, not `[]`. `build_agent` does this — the `tools or None` in
`_build.py` is load-bearing, not a style choice.

**Rule.** In a wire protocol, empty and absent are different values. Assume the
far side distinguishes them until you have proof it does not.

---

## G5 — One tool's annotation breaks every chat for the whole agent

**Symptom.** Every turn for one agent 500s with an internal error. The failure is
at the *first* turn, before any tool is called, so the tool never appears in a
trace. The endpoint that imports the tool module works perfectly. The error text
mentions Pydantic and a name you do not recognise.

**Cause.** A module-level `Annotated` alias used as a tool parameter type:

```python
_START = Annotated[str, Field(default="", description="...")]   # module level

@tool
def fetch(start: _START = "") -> dict: ...                      # breaks the build
```

The framework builds a Pydantic input model per tool via `get_type_hints`, and
Pydantic cannot resolve the alias name — `PydanticUserError: fetch_input is not
fully defined; you should define _START`. The schema for **every** tool is built
when the agent is built, so one malformed annotation takes the agent down, not
the tool.

**Fix.** Inline the annotation per parameter: `start: Annotated[str, Field(...)]
= ""`. Never alias an `Annotated` tool-parameter type at module scope.

**Reproduce without deploying.** `typing.get_type_hints(fn, include_extras=True)`
raises `NameError` on the bug, or build the schema directly with the SDK's own
`to_json_schema_spec()`. Both are cheap enough to run as a guard test over every
tool in the roster.

**Rule.** Blast radius follows the build step. Anything constructed per-agent
from all tools turns a per-tool defect into a per-agent outage.

---

## G6 — A capability silently disappears after a dependency change

**Symptom.** Context compaction or tool tracing stops happening. No error, no
failed deploy. It surfaces later as long sessions failing on context length, or
as an empty observability dashboard.

**Cause.** Optional-SDK paths that return `None` / `[]` when an import fails.
That is the correct behaviour — the agent should still run — but a `WARNING` in
a log nobody reads is not a notification.

**Fix.** The degradation is deliberate and asymmetric, and the asymmetry is the
design: **compaction and tracing degrade; tool binding does not.** An agent
running without compaction is degraded; an agent running without its tools is
wrong. Assert the capabilities you require at startup with `maf_available()`
rather than discovering the absence from behaviour.

**Rule.** Graceful degradation without an assertion at the boundary is just a
bug with good manners.

---

## G7 — Reordering the roster changes the agent's behaviour

**Symptom.** A cosmetic reorder of a tool list — alphabetising it, say — changes
which tool the model reaches for, and evaluation scores move with no code change.

**Cause.** Tools are presented to the model in list order, and order is a
positional signal like any other part of the prompt.

**Fix.** Treat tool order as configuration. `bind_tools` preserves it and never
sorts. If order matters enough to notice, pin it in the roster and record why.

**Rule.** Anything that reaches the model is a prompt, including the order of
things you did not think of as prompt.

---

## G8 — The fallback deployment never helps

**Symptom.** A rate-limited primary fails, the fallback engages, and the whole
queue fails identically. Latency triples and the outcome is unchanged.

**Cause.** The fallback list contains the primary — or lists deployments that
share the same quota pool. Retrying a saturated deployment against itself buys
only the wait.

**Fix.** `FoundryConfig.model_queue()` de-duplicates, and `warnings()` reports the
overlap. Verify the fallbacks draw on separate capacity; two deployments of the
same model in the same project usually do not.

**Rule.** A fallback that shares the failure domain is a retry with extra steps.

---

## G9 — A tool fails and the agent answers anyway

**Symptom.** The answer is confident and wrong. Logs show the tool raised. There
is no error anywhere in the response path.

**Cause.** Middleware that catches, logs and does not re-raise. The framework
then treats the invocation as complete, and the model continues with no result
and no indication that anything went wrong.

**Fix.** Observational middleware observes. `ToolTracingMiddleware` re-raises
after recording, and the trace sink is itself wrapped so a broken sink cannot
fail a tool call either. Both directions are covered by the selftest.

**Rule.** In a middleware pipeline, swallowing an exception is a decision about
product behaviour, not about logging.

---

## G10 — Long multi-step runs start being rejected part-way through

**Symptom.** The first few turns are fine. Somewhere mid-run every request is
rejected for peak load or maximum usage, including retries, including after a
wait. Shorter runs of the same task never fail.

**Cause.** Tool results accumulate in the transcript. A tool that returns a large
payload — an encoded image, a full document, a wide result set — is re-sent with
every subsequent turn, so the request grows with each step until it trips a
size or capacity limit that reports itself as load.

**Fix.** Return compact, semantic results and carry bulk out of band. Attach a
compaction strategy so tool results are compacted before message history is
truncated. Measured on a text-only multi-step run: 3,092 bytes of embedded
payload per frame failed repeatedly; 1,385 bytes of semantic summary with the
payload reconstructed by the caller completed the same sequence.

**Rule.** A tool result is not a return value; it is a permanent addition to
every future prompt in that session.

---

## G11 — A content-filter refusal takes ten times longer than it should

**Symptom.** A prompt that trips the responsible-AI filter takes a minute to come
back instead of a second, and the logs show every fallback deployment attempted.

**Cause.** A retry loop that classifies only on "did it fail". A filter rejection
and an authorization failure are properties of the *request*, not of the
deployment, so they reproduce identically on every model in the project.

**Fix.** Classify before retrying. `classify()` returns `fatal` for content
filter and auth, and `run_with_fallback` re-raises immediately without touching
the rest of the queue. Fatal is checked *before* rate-limit so that a 403 whose
body mentions throttling is still fatal.

**Rule.** Retry policy needs to know whether the failure belongs to the request
or to the endpoint. Without that distinction it can only be wrong in one of the
two directions.

---

## G12 — A model deployment is healthy in the portal and 400s from the app

**Symptom.** A new deployment shows as succeeded and can be exercised from the
portal playground. The application, pointed at the same project with the same
identity, gets 400 on every call. Reverting the deployment name restores
service instantly.

**Cause.** Deployment availability is not uniform across the access paths into a
project. Observed twice on the same swap attempt, days apart, with the portal
reporting healthy throughout.

**Fix.** Prove a deployment through `scripts/probe.py --run` on the real endpoint
*before* rolling it into config. Keep the previous deployment name in
`fallback_models` during a swap so a bad model degrades rather than fails.
Revert on the first failed turn — this one does not resolve by waiting.

**Rule.** "Available in the portal" is a statement about the portal.

---

## G13 — The safety filter fires on ordinary domain vocabulary

**Symptom.** Occasional, non-deterministic refusals on requests that are plainly
benign, clustered around domain terms with violent or sensitive homonyms.

**Cause.** Content classifiers are general-purpose. Technical vocabulary that
collides with unsafe language scores as unsafe, especially in short prompts with
little surrounding context.

**Fix.** Give the classifier context: a domain preamble in the system prompt
measurably reduces false positives, because the classifier sees the whole
request. Treat it as `fatal` in retry terms — do not retry it — and surface the
refusal to the user rather than silently returning nothing. If it persists on a
known-good vocabulary, a custom filter configuration is the supported route.

**Rule.** Non-deterministic refusals on benign input are a prompt-context
problem before they are a policy problem.

---

## G14 — Turns abort during the model's silent thinking time

**Symptom.** A run that has finished its tool calls is killed by a stall timeout
before producing any text. Simple turns are unaffected; the more tools a turn
used, the more often it happens.

**Cause.** A stall timeout measured as "time since the last event". Between the
final tool result and the first output token, a reasoning model can emit nothing
at all for a long interval — that is work, not a stall, and it lengthens with the
amount of context to reason over.

**Fix.** Size the stall timeout for the gap between tools-done and tokens-flowing
on your *slowest* agent, not for network latency. A value tuned on simple turns
will be wrong for exactly the complex turns that matter. Where one agent is an
outlier, override it per agent rather than raising the global value.

**Rule.** Silence is not evidence of a stall in a system whose main activity
produces no output.
