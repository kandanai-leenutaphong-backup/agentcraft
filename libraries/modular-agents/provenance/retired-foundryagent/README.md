# foundry-agent-runtime

Run an agent roster on **Azure AI Foundry**, on the **Microsoft Agent Framework**,
with managed identity, per-agent client isolation, context compaction, tool
tracing, and a retry policy that can tell a throttle from a refusal.

Self-contained. Copy this folder anywhere. Python 3.10+. The SDKs are optional
at import time and substitutable at test time, so the selftest runs offline with
no Azure account.

```
foundry-agent-runtime/
  README.md            you are here — rationale and design decisions
  SKILL.md             agent-facing: wire it, verify it, remove it
  CONTRACT.md          exact schema, call shapes, and retry algorithm
  GOTCHAS.md           fourteen production failures, symptom-first
  foundryagent/        the mechanism
    _config.py           FoundryConfig — coordinates, read once, frozen
    _credentials.py      one credential per process
    _optional.py         lazy SDK loading, and the substitution seam
    _client.py           the client factory and the per-agent ClientPool
    _tools.py            SDK-free @tool stamp
    _maf.py              every Agent Framework import, in one file
    _build.py            spec + client -> agent. The seam.
    _retry.py            classification, backoff, model fallback
  scripts/
    probe.py             config / SDK / identity / build / run, exit-code driven
  examples/
    factory.py           the seam worked, runnable with or without Foundry
  tests/
    selftest.py          130 checks, no test framework, no network
```

---

## 1. The problem

Wiring a model into an agent runtime is four lines in every quickstart and about
two hundred in every production deployment. The gap is not complexity, it is
that the quickstart is wrong in ways that only appear later:

| Quickstart does | Production needs | Failure when it does not |
| --- | --- | --- |
| One client, shared | One client per agent | Agents answer with each other's tools (G2) |
| A credential per client | One per process | Uneven cold-start auth latency (G3) |
| `AzureOpenAI(api_key=...)` | Managed identity | A key in an env var, and a rotation project |
| Import the SDK at module load | Import at call | Cannot boot or test without the SDK |
| `except: retry` | Classify, then decide | Content-filter refusals retried across every fallback (G11) |
| The endpoint from the portal | The *project* endpoint | 403s that look like a permissions problem (G1) |
| Unbounded context | Compaction before truncation | Long runs die mid-investigation (G10) |

Every row is a defect that survives code review, because each looks correct in
isolation and only fails under concurrency, under load, or after a month of use.

## 2. The approach

Azure-native by construction, not by configuration. Foundry is the model host,
Entra is the identity, the Agent Framework is the runtime — and each of those
three is behind exactly one file, so committing to the stack costs nothing in
testability.

| Property | How |
| --- | --- |
| No key material, ever | `DefaultAzureCredential` only; CLI login locally, workload identity in cloud, same code |
| One credential per process | Cached behind a lock in `_credentials.py`; nothing else builds one |
| Per-agent isolation | `ClientPool` keyed by agent id |
| One SDK surface | Every `agent_framework` import lives in `_maf.py` |
| Boots without the SDK | Lazy imports; `import foundryagent` costs nothing |
| Testable offline | `set_sdk()` / `set_sdk_absent()` substitute the SDK through the shipping code path |
| Config read once | `FoundryConfig.from_env()` is the only environment read in the box |
| Retry that discriminates | Fatal / rate-limit / transient / unknown, each with its own policy |
| Tools stay plain functions | A stamp, not a wrapper; SDK binding happens at build |

## 3. Failure model

**Prevents:** a shared client bleeding state between agents; a credential storm at
startup; a key ending up in configuration; an empty tool list being sent as a
schema; a content-filter refusal walking the entire fallback queue; a fallback
list that retries the deployment already refusing; a tool failure being swallowed
by observational middleware; an agent built against an unresolvable model.

**Does not prevent:** a prompt that is present but wrong; a tool that binds and
misbehaves; a deployment that is healthy in the portal and 400s from the app
(G12); a safety filter firing on legitimate domain vocabulary (G13); quota that
is genuinely exhausted. Those need evaluation and capacity planning, not
validation.

**Deliberate trade-off — text-matched error classification.** Failures are
classified by matching text in the exception, not by exception type. Type
matching is more elegant and less durable: types vary by transport and SDK
version while the status code and reason in the message do not. This is stated
in CONTRACT.md §6 so a reimplementation does not "fix" it into fragility.

**Deliberate asymmetry — what degrades and what does not.** Compaction and
tracing return nothing when the SDK is missing, and the agent still runs. Tool
binding never degrades. An agent without compaction is degraded; an agent without
its tools is wrong, and it will answer anyway (G6).

## 4. Why it is portable, despite being Azure-native

Two seams, and they point in opposite directions.

```
roster (any source) ──► build_agent(spec, client, config) ──► SDK agent
                                      ▲
                        ClientPool(foundry_agent_client(config))
```

**Inbound: the spec is duck-typed.** `build_agent` accepts a mapping or any
object with the fields, falling back through attribute → key → `extra` mapping.
So a YAML-driven roster, a database row, or a hand-written dict all work, and
this box never needs to know which loader produced them. Pairing it with a
declarative config layer is a one-line factory:

```python
build_agents(lambda spec: build_agent(spec, pool.client_for(spec.agent_id), config))
```

**Outbound: the SDK is loaded through one substitutable function.** Swapping the
framework means rewriting `_maf.py` — one file, ~200 lines — and nothing else.
Substituting it for a test means one call, and the code under test is the code
that ships.

The consequence worth stating plainly: **an agent built here runs against an
in-memory stub client with no changes.** `bind_tools` no-ops on a non-SDK client,
so the same roster, the same tools and the same build call drive a stub in CI and
Foundry in production. `examples/factory.py` does exactly this, and runs either
way depending on whether one environment variable is set.

## 5. Design decisions worth keeping

- **The pool ships with the factory.** `foundry_agent_client` returns a factory
  rather than a client precisely so something can build more than one. Shipping
  the factory without `ClientPool` would be shipping the trap in G2 with a
  convenience wrapper on it.
- **`api_version` is omitted, not passed as `None`.** Some SDK versions treat an
  explicit null as a version request and fail rather than defaulting.
- **`tools or None`.** Empty and absent are different values on the wire, and the
  service distinguishes them (G4).
- **Fatal is classified before rate-limit.** A 403 whose body mentions throttling
  is still a 403. Reversing the order produces a retry loop that never terminates
  for the right reason.
- **Each fallback deployment gets a fresh attempt budget.** A saturated
  deployment must not consume the retries of a healthy one.
- **Tool-result compaction runs before truncation.** Reversing it discards
  messages while one oversized tool result still fills the window.
- **The `@tool` stamp returns the function unwrapped.** Tools stay unit-testable
  by calling them, no SDK is imported at module load, and — the reason that
  matters — a malformed annotation cannot take down every agent that shares the
  build step (G5).
- **Shape warnings warn; only impossible values raise.** An endpoint form nobody
  anticipated should be an investigation, not a boot failure.
- **Empty instructions build.** A purely tool-driven agent is legal. It logs
  loudly, because far more often it means a prompt file went missing.

## 6. Quick start

```bash
pip install agent-framework azure-identity

export FOUNDRY_PROJECT_ENDPOINT="https://<resource>.services.ai.azure.com/api/projects/<project>"
export FOUNDRY_MODEL_DEPLOYMENT="<deployment>"

python3 scripts/probe.py --run "reply with one word"
```

The probe checks config, SDK, identity, build and one live turn, in the order
failures cascade, and stops at the first one — so the output names which of the
four layers is broken rather than leaving you a stack trace.

Prove the box works here before trusting it, with no cloud account:

```bash
python3 tests/selftest.py     # 130 checks, offline
python3 examples/factory.py   # runs against a stub, or Foundry if configured
```

## 7. Removal

1. Delete `foundryagent/` and your factory call.
2. Construct clients and agents against the SDK directly, or drop in another
   binding — CONTRACT.md is sufficient to write one.

Nothing to unwind: the package holds a cached credential and a dict of clients,
both process-local. No resource is created in Azure by this box, so removing it
leaves nothing behind to clean up. Roles and deployments are provisioned
elsewhere and are unaffected.

## 8. Provenance

Extracted from a deployment running a roster of roughly fifteen agents across
three use cases against one Foundry project, under signed-request regression
suites and unattended agent piloting. Every gotcha except G8 was hit in
production; G8 was found while writing the fallback tests here, when a
`fallback_models` list that included the primary produced a retry loop that
could not escape the deployment already refusing.

**Changed during extraction**, disclosed because packaging should not silently
alter behaviour:

- Model resolution read a process-wide settings singleton in the origin. It now
  reads the injected `FoundryConfig`, because a settings singleton is a
  dependency on the consumer's configuration system.
- The retry helpers and the client factory lived in separate layers, connected
  through that singleton. They are one box here: a fallback queue and the client
  it falls back onto are one concern, and splitting them is what allowed the G8
  overlap to go unnoticed.
- `ClientPool` was a method on a larger agent registry that also owned prompt
  loading and session state. Only the client-caching behaviour is here; the rest
  is the consumer's.
- `set_sdk_absent()` is new, added when the compaction and tracing degradation
  tests passed for the wrong reason on a machine that had the SDK installed.
- Tool tracing gained the `on_event` callback and a guard around it. The origin
  logged only. A trace sink that can fail a tool call is a worse bug than no
  trace, so the guard is tested in both directions.
