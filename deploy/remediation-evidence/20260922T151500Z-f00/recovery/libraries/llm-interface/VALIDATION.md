# Validation And End-to-End Acceptance

## B03 Host Adoption

Both template hosts use the bounded native contract. Current full offline suite: 48 tests
and 48 subtests passed on Python 3.12.3. Obsolete `test_existing_contracts.py` comparison of
retired `azllm`/`modelaccess` behavior was removed. Native tests retain embedding alignment,
owner/tool refusal, bounds, terminal evidence and cleanup. One rerun was externally
interrupted after 43 tests; the subsequent complete rerun passed.

Host checks, fresh artifacts and remaining live/provider blockers:
[B02/B03 record](../azure-data-connectors/MIGRATION_B02_B03.md). Historical hashes below do
not certify changed source or current app integration.

## Consumer-Driven Schema Repair

2026-09-15: Investigation compatibility experiments reproduced loss of raw FunctionTool mapping
constraints during binding. The first strengthened regression failed because `value=0` executed
despite `minimum=1`. Preserving the native mapping alone still failed. The canonical guard now
uses standard JSON Schema validation with remote reference retrieval disabled before any batch
function executes; typed Pydantic validation and one native tool loop remain intact.

Current source and external sdist-rebuilt wheel: **48 tests passed, one optional legacy
comparison skipped**. The public offline example passed with four synthetic requests. Six tool
tests and 13 compatibility tests also pass with the newly declared dependency floors
`jsonschema==4.23.0`, `referencing==0.35.0`. Python 3.12.3 base-only installation imports and
refuses missing native providers without network. No existing app environment was synchronized.

Full artifact environment: Python 3.11.14, Agent Framework core 1.18.0/OpenAI 1.14.3,
Azure Projects 2.6.1, OpenAI 3.13.0, jsonschema 4.26.0 and referencing 0.37.0. The installed
runtime's nine files matched wheel bytes; import origin was outside the checkout. Source-built
and sdist-rebuilt wheels were byte-identical; installed dependency checks passed.

| Current Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| Wheel | 23,821 | `60491769947655ce6d5da3504a29902735218fabd95c7be51eb08c41d47decd5` |
| Sdist | 47,562 | `a8fa9510ebf4d7a8686deec5918a01aa9b9b7d8d33984cf44c5a80cce4b56857` |

[Receipt](../../deploy/records/library-integration-offline-2026-09-15.json),
[compatibility findings](tests/live_tests/INVESTIGATION_COMPATIBILITY.md) and
[frozen coverage](tests/live_tests/COVERAGE.md) preserve exact scope and remaining decisions.
No live inference, app runtime replacement, model-quality proof, independent usability result
or publication is claimed. Earlier checks/artifact records below retain their historical scope.

## Implementation Readiness

**`llm-interface` 0.1.0a1 is implemented and ready for independent testing.** The active contract is
[CONTRACT.md](CONTRACT.md), and [USAGE.md](USAGE.md) is now an implemented caller guide.
No investigation-application code, tests, server, browser or data were used as an integration
target. No live Azure inference, roles, resources or publication were performed.

Fresh verification after the interrupted session, 2026-09-15:

| Check | Observed Result | Scope |
| --- | --- | --- |
| Locked workspace suite | 32 passed; one optional historical-comparison module skipped | Python 3.11.14, Foundry extra; 26 implementation tests plus six framework comparisons |
| Installed wheel outside checkout | 38 passed, no failures/errors/skips | Python 3.11.14; includes the six optional legacy comparisons, installed from temporary source snapshots |
| Full offline example from sdist | Passed | Standalone response, aligned embeddings, streaming function/progress/result events and final-result read-back through real framework/SDKs with synthetic HTTP |
| Foundry example default mode | Passed without credential acquisition or inference | Describes the explicit synthetic target; `--confirm-live` was not used |
| Base-only installed wheel | Passed | Python 3.12.3; no OpenAI/Azure SDK installed, `provider_extra_missing` refusal before token/network calls |
| Wheel/sdist | Built successfully with `uv build --no-sources`; wheel built from sdist | Runtime bytes match source, `py.typed` included, no local-path runtime requirements or skill/application contents |
| Shared lock and editor diagnostics | Passed | `uv lock --project libraries --check`; no LLM source/test/example diagnostics |

The full installed test environment used framework core `1.18.0`, OpenAI integration
`1.14.3`, Foundry integration `1.13.0`, Azure Projects `2.6.1`, OpenAI `3.13.0`, Azure
Identity `1.25.3`, HTTPX `0.28.1` and Pydantic `2.13.5`. This is one observed combination,
not proof of every version allowed by package metadata. Python 3.12 evidence covers only
the base install/refusal path, not the complete Foundry suite.

Current offline suite exercises the package itself: configuration/grants, Foundry project
construction through `AIProjectClient`, account Responses, both native streaming-agent
protocols, structured output, native embedding validation, session isolation, tool grants/
authorization/arguments/results, progress, budgets, cancellation, concurrency, safe failures,
redirect refusal, response limits and provider extension/ownership.

The workspace uses its own ignored `.venv-llm-interface`; the implementation is an explicit
member with independently buildable metadata. Current test command and standalone example
are in [the package README](README.md#test-locally). Historical tests below remain comparison
evidence, not the implementation suite's sole acceptance. Their legacy module is skipped
when the optional old packages are not installed; it is not a runtime dependency.

Artifact and final run records are reported in [implementation.json](research/implementation.json).
Only commands that actually completed are recorded there. A working wheel is not registry
publication. Pending: authorized live Foundry identity/audience/model behavior, actual
non-OpenAI-provider conformance, broader dependency/Python combinations, load behavior and
the fresh-coding-agent usability comparison. Native project OpenAI-v1 embeddings do not
claim support for every separate Foundry models endpoint or multimodal embedding provider.

### Implementation Coverage

| Owning Tests | Observed Coverage |
| --- | --- |
| [test_config.py](tests/test_config.py) | Account/project profile selection, malformed targets, explicit/snapshotted policy, limits and capabilities |
| [test_connection.py](tests/test_connection.py) | Few-line call, borrowed credentials, policy/override refusal, real Foundry client construction, native embedding integrity |
| [test_agents.py](tests/test_agents.py) | Same agent path across two protocols, owner/binding isolation, per-run model budget, tool-authorization refusal |
| [test_safety.py](tests/test_safety.py) | Streaming completion/EOF, incomplete responses, structured/plain-agent calls, cancellation, timeout, concurrency, redirects, byte limits and safe provider failures |
| [test_tools.py](tests/test_tools.py) | Strict arguments/grants, no execution of invalid calls, safe failures, result limits and no implicit replay |
| [test_providers.py](tests/test_providers.py) | Explicit injected-provider guard contract, borrowing and exactly-once local resource cleanup |

These cases and the standalone example exercise the public package; they do not certify
live service permissions, adversarial production isolation or a usability improvement.
The extension API is available, but another provider's native enforcement must pass its
own conformance tests before being advertised as supported.

### Rebuild And Retest

Run from the repository root. Package/registry acquisition is separate from the tests,
which use synthetic HTTP and block socket connections. This command validates the wheel
outside the checkout using tests and examples from its source distribution:

```bash
uv build --project libraries --no-sources --package llm-interface \
  --out-dir libraries/dist/llm-interface
artifact_root="$PWD/libraries/dist/llm-interface"
test_root=$(mktemp -d /tmp/llm-interface-artifact.XXXXXX)
tar -xzf "$artifact_root/llm_interface-0.1.0a1.tar.gz" -C "$test_root"
cd "$test_root/llm_interface-0.1.0a1"
uv run --isolated --no-project --no-env-file --python 3.11 \
  --with "$artifact_root/llm_interface-0.1.0a1-py3-none-any.whl[foundry]" \
  python -B -m unittest discover -s tests -v
uv run --isolated --no-project --no-env-file --python 3.11 \
  --with "$artifact_root/llm_interface-0.1.0a1-py3-none-any.whl[foundry]" \
  python -B examples/offline.py
```

Without the optional legacy distributions, expect 33 reported test entries: 32 passing
tests and one skipped module. The recorded 38-test run additionally installed temporary
snapshots of `azllm` and `managed-identity-model-clients`, then ran this same sdist suite.
Neither legacy package is a runtime dependency; the source owners were not edited.

## Historical Design Evidence

**The original design review ran twelve comparison tests before runtime implementation.**
The following observation timestamps and records retain that narrower historical scope.

**Scope:** the investigation app is a read-only requirements reference. Do not modify it,
run its tests, start its server or use its browser/data for this work. The independent
comparisons and future library acceptance use synthetic consumers under this directory.
No existing application is selected as a future integration target by this document.

The twelve recorded tests establish dependency behavior, not low cognitive load. The
primary product claim is tested separately by [low-friction acceptance](#low-friction-acceptance).

The machine's UTC clock recorded the combined run at
`2026-09-14T17:30:13.958881+00:00`. This timestamp is retained as observed, separately
from the user/session design date. [Recorded results](research/validation.json) carry
the exact versions and scope; [source provenance](research/acquisitions.json) retains
original fetch timestamps, which also use the machine clock.

## Verified Environment

| Component | Observed Version |
| --- | --- |
| Python | `3.12.3` |
| Agent Framework core | `1.18.0` |
| Agent Framework OpenAI | `1.14.3` |
| OpenAI SDK | `3.13.0` |
| HTTPX | `0.28.1` |
| Pydantic | `2.13.5` |
| Azure Identity | `1.25.3` |
| Existing azllm | `1.1.0`, installed from a temporary source snapshot |
| Existing modelaccess distribution | `managed-identity-model-clients` `1.0.0`, installed from a temporary source snapshot |

Foundry package `1.13.0` was separately inspected in the preceding investigation: its
constructors, inheritance and published requirements were checked, not live model calls.
Foundry execution is not part of the twelve-test claim. The native inference SDK accepts
async token credentials; the framework embedding constructor's key-oriented annotation,
two-client construction and ownership still require a deliberate Entra compatibility test.

Critical framework/OpenAI/HTTPX versions were explicitly pinned for the comparison. The
remaining resolved versions are recorded, not a full dependency lock or lower-bound proof.
At that design stage Python 3.11 support was unverified. The implementation results above
now cover the full suite on Python 3.11.14; the historical pins remain unchanged.

## Reproduce Historical Comparisons

Run from the repository root. Public dependency acquisition may use the package registry;
the tests themselves use synthetic data/HTTP and block socket connections. No Azure login,
resource, endpoint, API key, real token, model invocation or paid inference is needed.

Copy the two local baselines to temporary storage so setuptools output cannot pollute the
canonical source owners. The temporary snapshots contain current source, not a frozen
released artifact; compare recorded baseline hashes before interpreting a changed result.

The former combined legacy-comparison command is retired with its obsolete test module.
Do not reinstall skill-owned model runtimes to run current acceptance. The current native
suite tests retained guarantees; the table below preserves historical observations only.

For framework-only changes, the narrow command is:

```bash
uv run --isolated --no-project --no-env-file \
    --with agent-framework-core==1.18.0 \
    --with agent-framework-openai==1.14.3 \
    --with openai==3.13.0 --with httpx==0.28.1 \
    python -B -m unittest discover -s libraries/llm-interface/tests \
    -p test_framework_comparison.py -v
```

Expected: six tests pass. Tests documenting an upstream gap assert its current observed
behavior. A later upstream fix should fail that assertion and trigger reassessment/removal
of the proposed custom rule, not an attempt to preserve the upstream defect.

## Reproduced Observations

Framework cases are in [test_framework_comparison.py](tests/test_framework_comparison.py).
Local legacy cases were retired in [B02/B03](../azure-data-connectors/MIGRATION_B02_B03.md).

| ID | Test Method | Observed Fact | What It Does Not Prove |
| --- | --- | --- | --- |
| F01 | `test_same_agent_and_tool_with_two_client_bindings` | Same agent/tool source works through Responses and Chat Completions; two model calls, one tool call, arguments before execution, correlated streamed result, final answer and middleware before both requests | Actual second vendor, live Foundry, UI compatibility, task quality or a production policy implementation |
| F02 | `test_framework_embeddings_sort_without_strict_index_integrity` | Reversed indices sort correctly; duplicate indices, a missing item and unequal dimensions are accepted by the selected framework mapping | That a live service routinely sends malformed embeddings or every framework provider behaves this way |
| F03 | `test_framework_eof_without_terminal_event_has_no_finish_reason` | A created/text-only stream ending at EOF yields text and `finish_reason=None` | Successful completion, automatic failure signaling or a packaged fix |
| F04 | `test_framework_responses_structured_output_and_explicit_retention` | Response text/usage and Pydantic output work; unset `store` is absent on the wire; explicit false is transmitted | Zero provider retention, all model/schema compatibility or application privacy compliance |
| F05 | `test_chat_middleware_can_refuse_before_native_transport` | A policy hook can refuse without any native request | Atomic counters, per-tenant limits, tool refusal propagation or complete security |
| F06 | `test_native_response_hook_can_refuse_before_embedding_normalization` | HTTPX's public response hook sees duplicate indices and aborts before framework normalization | Bounded production parsing, real expected-count correlation, live identity or all SDK transports |
| L01 | `test_both_existing_packages_validate_embedding_alignment` | Both local parsers reorder valid data and refuse eight malformed variants, including duplicate/missing/out-of-range indices and invalid vectors | All legacy API behavior, base64 support or completed migration |
| L02 | `test_borrowed_client_ownership_differs` | azllm closes an injected sync client; modelaccess leaves it open | Async lifecycle, thread safety or permission to silently change either consumer |
| L03 | `test_existing_text_streams_close_but_accept_quiet_eof` | Both local text helpers return partial text and close the stream after EOF without a terminal event | That their richer raw-event consumers make the same completion claim |
| L04 | `test_existing_text_streams_refuse_explicit_failure` | Both refuse `response.failed` with category `stream` and close resources | Handling every truncation, transport error or cancellation path |
| L05 | `test_safe_error_projection_does_not_make_traceback_safe` | Safe exception strings omit fixture payload, but `__cause__` retains it | Safe full tracebacks, SDK telemetry or all logging configurations |
| L06 | `test_modelaccess_allowlist_refuses_foreign_chat_or_embedding_host` | ModelConfig refuses an undeclared chat or embedding host | DNS/redirect security, Azure authority, or the proposed library's boundary |

These twelve cases are historical dependency/legacy evidence tests, including assertions
of limitations. They do not test the newly implemented runtime; its separate test modules
and installed-artifact results are listed in Implementation Readiness above.

## Source-Inspected Findings

- [AgentService.stream_turn](../../template_apps/investigation_app/app/cybereye/backend/agents/service.py#L196)
  owns the current generic tool loop and native event mapping. Tool results are emitted
  after complete function execution; running-tool partial output is not implemented there.
- [Agent configuration](../../template_apps/investigation_app/app/cybereye/backend/agents/config.py#L222)
  rejects deployments other than its selected application model. This is a reference
  example of host-specific policy, not a restriction scheduled for removal.
- [Chat ownership/session route](../../template_apps/investigation_app/app/cybereye/backend/api/chat.py#L65)
  checks owner and serializes turns. Its [existing tests](../../template_apps/investigation_app/app/cybereye/tests/test_chat_sessions.py)
  cover stale sessions, no replay after output and owner isolation. They were inspected,
  not rerun as evidence of a migration in this task.
- [Browser event dispatcher](../../template_apps/investigation_app/app/cybereye/frontend/src/shared/api/api.ts#L253)
  provides an example event vocabulary, not an integration target. No browser/app server
  was run, and none is to be run for this design.
- Historical modular hosting used a separate loop, completed-response token events and
  OpenAI below 3. That skill runtime and module-prefix binding are retired. The current
  [modular-agent contract](../modular-agents/CONTRACT.md) is the owning reference; historical
  observations here do not certify its new native provider integration.

## Original Acceptance Matrix

The following matrix is the original design-time plan. Its status cells retain the
pre-implementation baseline, not current readiness. The implemented contract, coverage
table and artifact record above supersede that baseline for the delivered alpha.
Optional integrations and broader/live testing remain separately scoped; not every item
in the original design is promised by `0.1.0a1`. In particular A26 remains unrun and is
the primary comparative usability gate, not permission to weaken the safety contract.

| ID | Required Observation | Positive And Negative Cases | Original Owner / Design-Time Status |
| --- | --- | --- | --- |
| A01 | Same public model contract | Both response protocols, structured output, native streaming and aligned embeddings; unsupported operation/mode refuses before I/O | Library; F01/F04 support feasibility only |
| A02 | No hidden initialization effects | Construct/describe/import with synthetic dependencies; assert zero token/network calls and no env/config/file reads below edge | Library; pending |
| A03 | Trusted target/auth binding | Approved endpoint/deployment/audience; foreign host, redirect, arbitrary factory ID, key fallback and option/header overrides refuse | Library/provider profile; L06 baseline only |
| A04 | Declared capabilities are honest | Required supported tool/stream/schema profile succeeds; unknown/unsupported model requirements refuse before submission | Library; pending |
| A05 | Every attempt consumes bounded authority | Direct and inner-loop calls share atomic budgets; exhausted/parallel reservations refuse without another native request | Library/host budget store; F01/F05 hooks only |
| A06 | Exactly one approved tool loop | Valid registered tools run; unregistered/ungranted tools, malformed arguments and privilege parameters never execute or trigger later model work | Agent binding; pending |
| A07 | Strict embedding integrity before information loss | Ordered/out-of-order valid vectors; all malformed indices/counts/numeric values/widths, body caps and simultaneous batches refuse correctly | Library/native adapter; F02/F06/L01 comparisons only |
| A08 | Valid terminal evidence | Normal terminal response, refusal and truncation; explicit failure, error, empty stream, missing terminal, broken JSON and partial tool arguments preserve honest outcome | Library; F03/L03/L04 comparisons only |
| A09 | Native async lifecycle | Owned resources close once; borrowed remain open; close during stream, cancellation and cross-loop misuse cannot leak local work or claim remote rollback | Library; L02 comparison only |
| A10 | No unsafe replay | Retry-After/deadline rules and SDK attempt counts; no replay after output, tool side effects, ambiguous response or persistence failure | Library/runtime; pending |
| A11 | Model/tool privacy | Approved retention settings; unsafe override refused; logs/traces exclude fixture prompts/results/keys and exception-chain payloads | Library/app observability; F04/L05 observations only |
| A12 | Compatible agent substitution | Same definition, tool source and standalone event consumer across tested profiles; only trusted connection binding differs | Library fixtures; F01 two-protocol comparison only |
| A13 | Real provider extensibility | Actual non-OpenAI provider's supported tool/stream behavior; incompatible profile refuses explicitly | Separately authorized integration; pending |
| A14 | Standalone streaming interaction | Synthetic response and tool loop emit actual text/arguments/results and a final outcome; incomplete/failed calls settle once without a browser | Library fixture consumer; pending, no reference-app parity claim |
| A15 | Session/tenant isolation contract | Synthetic host resolves owner; anonymous/other-owner/stale/wrong-version sessions cannot access or consume authority; concurrent turns serialize | Host fixture and binding; no existing app tests used |
| A16 | Explicit conversation portability | Fresh binding works; foreign response IDs, unsupported history content and policy-widening transcript transfers refuse | Standalone host fixture and binding; pending |
| A17 | Readable final result and honest save status | Get final result without a second model call; optional fixture store read-back matches owner/content, slow/failed/ambiguous saves retain known output | Final-response API required; store integration conditional, not a basic-call prerequisite |
| A18 | Result-bound failure recovery | Retry save only; cancelled/failed tool effects retain reference; no dropped output or invented rollback | Optional storage/recovery fixture; real application store outside scope |
| A19 | Bounded stream/backpressure | Slow consumer and parallel tools preserve correlation and final events; overflow/disconnect cannot silently lose terminal state | Event binding; pending |
| A20 | Incremental tool progress | Tool emits actual partial progress without masquerading as model arguments; bounded async/thread emission and cancellation | Optional addition under review; not initial completed-result parity |
| A21 | Optional browser integration | For a separately selected app, callable result matches displayed outcome and real controls handle authorized/error states at desktop/mobile | Not a core release gate; no app/browser target selected or authorized |
| A22 | Legacy compatibility | If a legacy surface is provided, installed synthetic callers retain its intended behavior and breaking differences are versioned | Conditional compatibility work; no existing consumer migration selected |
| A23 | Clean dependency/artifact boundary | Base/extras and Python 3.11+ supported matrix, lower/upper dependency combinations, wheel/sdist rebuild and isolated import; missing extra fails clearly | Package owner; no artifacts yet |
| A24 | Canonical package ownership | Standalone consumers import public artifacts without path hacks or namespace collisions; claim real consolidation only after separately approved adoption | Package boundary required; source retirement and application migration separate |
| A25 | Live Foundry correctness | Authorized real credential refresh/audience, endpoint/deployment, structured/tool streams, embedding read-back and actual usage; wrong identity/target refuses | Scoped live plan; not authorized or run |
| A26 | Low-friction coding-agent use | Fresh caller completes response/embedding/streaming-agent/swap/refusal tasks from the guide; compare lookups, decisions, glue, errors and setup effort with native framework | Primary usability gate; not run, see experiment below |
| A27 | Remote agent profile | Correct remote version/session/auth/tool boundary and event mapping; no unauthorized remote mutation or local-hook claims | Deferred from first release |

## Standalone User Journeys

1. Use a documented synthetic host setup to supply a permitted connection, credential
  fixture and one tool-using definition. No reference-app imports, files or runtime required.
2. Make a response, structured result and embedding request through the caller guide's
  public methods. Inspect result, usage and completion/refusal without native SDK parsing.
3. Run an owner-bound synthetic agent turn, consume arguments and tool results as emitted,
  then retrieve the final result without a second model invocation or a browser.
4. Change only the configured binding to another compatible profile and use a fresh session.
  Keep caller, definition, tool and event-consumer source unchanged.
5. Exercise a denied call and an unsupported capability. Follow the documented safe next
  action, without guessing new credentials, widening permissions or retrying blindly.
6. Independently validate integrity, budgets, cancellation and optional persistence hooks
  through matching positive/negative fixtures, not through the investigation app's tests.

## Low-Friction Acceptance

Status: **not run**; an implemented alpha and standalone examples are now available for
the fresh-caller experiment. Runtime checks establish behavior and executable short paths,
not a measured reduction in cognitive load versus native Agent Framework.

Evaluate two roles separately: a coding agent adding a call to an already configured host,
and a coding agent setting up a new host from the public examples. Do not hide all complexity
in supplied handles and report only the repeat-call path as easy adoption.

Give fresh sessions the [caller guide](USAGE.md), installed package and synthetic fixture.
Use equivalent tasks, authority, models/fixtures and safeguards for an Agent Framework-only
baseline. Counterbalance task order across sessions before drawing comparative conclusions;
report the number and configuration of sessions actually observed. This document schedules
no subagents or autonomous runs now.

| Measure | Observation To Record | Acceptance Meaning |
| --- | --- | --- |
| Discoverability | Documentation/tool lookups and clarification requests before each correct task | The public guide links everything required; private source or provider docs should not be necessary for supported basic calls |
| Decisions | Provider classes, protocol details, retry/retention/tool-loop choices the caller must supply | None at a preconfigured repeat-call site; host choices explicit and supported by a complete example |
| Glue | Task code and separately measured host/config/error/event wiring | No hand-written agent loop or provider event parser; extra framework adapters must remove demonstrated repeated work |
| Swap | Caller, tool and event-consumer diff for a compatible binding change | No such source change; configuration and fresh session may change |
| Recovery | Failed attempts and actions after intentional denied/unsupported input | Safe field/code/reason and next action are discoverable; zero permission bypasses |
| End-to-end effort | Actual time to first correct result, including host setup when evaluating setup | Report measured values, not estimates or line-count claims about cognition |

Structural acceptance is necessary, not sufficient for a comparative friction claim. If
the native framework is equally straightforward for the same policies and tasks, prefer
a recipe or smaller integration. Shorter code caused by omitting auth, cleanup, terminal
checks or required tool permissions does not count as improvement. Latency/cost/quality
benefits remain separate unmeasured claims, not proxies for cognitive load.

Any later real application or browser test requires its own scope and authorization. No
investigation-app modification, server startup, test run or live model call closes A26 here.

## Live Approval Boundary

Before any live invocation, approve exact tenant/subscription where applicable, target
accounts/projects/models or agent versions, credential principal, operations, input class,
tool/data permissions, call/token/time bounds and result retention. Wrong-target and denied
identity cases need their own permitted test identities, not implicit role changes.

Provisioning, role assignments and remote agent changes are separate approvals with the
existing deployment entry point/runbook. Live tests use synthetic per-run-owned fixtures,
record safe metadata and clean up only explicitly owned records. No teardown, grant or
test of unrelated tenant resources is implied by approval of inference.

## Completion Criteria

The requested implementation/testing handoff is satisfied by working short public paths,
independent offline positive/refusal checks, runnable complete examples, clean isolated
artifacts and an explicit pending-testing record. Those checks have passed for this alpha.
No claim of production readiness, live permissions or measured cognitive-load reduction
follows from them.

Promotion beyond the testing alpha requires the applicable live/provider/dependency/load
checks and comparative caller/setup experiment. Optional storage/browser integrations and
real application migrations remain separate, not implied prerequisites. No application
target is chosen here. Publication, source retirement and cloud actions require their own
authority; stop at the agreed testing handoff rather than expanding into them.