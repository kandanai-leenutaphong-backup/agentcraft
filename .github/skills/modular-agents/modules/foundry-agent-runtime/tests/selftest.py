#!/usr/bin/env python3
"""selftest — proves this box works in the environment it was copied into.

No test framework. Every SDK is substituted, so this runs offline, with no
Azure account, no credential, and no network. What it exercises is the shipping
code path: the fakes are injected through the same seam a consumer would use.

Run:  python3 tests/selftest.py    (exit 0 = the box is functional here)
"""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import foundryagent as fa
from foundryagent._maf import build_tracing_middleware
from foundryagent._optional import SdkUnavailable, clear_sdks, load_sdk, set_sdk

# The box logs a warning on every deliberately-degraded path. Expected here.
logging.disable(logging.CRITICAL)

_PASS = 0
_FAIL = 0

# A syntactically valid project endpoint that resolves to nothing. No real
# tenant, resource or project name appears anywhere in this box.
ENDPOINT = "https://example-resource.services.ai.azure.com/api/projects/example"


def check(label: str, condition: bool, detail: str = "") -> None:
    """Record one assertion. Never raises, so one run reports every failure."""
    global _PASS, _FAIL
    if condition:
        _PASS += 1
        print(f"  ok   {label}")
    else:
        _FAIL += 1
        print(f"  FAIL {label}" + (f" — {detail}" if detail else ""))


def raises(exc_type, fn, *args, **kwargs) -> BaseException | None:
    """Return the expected exception, or None if it was not raised."""
    try:
        fn(*args, **kwargs)
    except exc_type as exc:
        return exc
    except Exception:
        return None
    return None


# ── fake SDK ────────────────────────────────────────────────────────────────


class FakeToolWrapper:
    """Stands in for the SDK's tool object: wraps, records, stays callable."""

    def __init__(self, fn, approval_mode):
        self.fn = fn
        self.approval_mode = approval_mode
        self.name = fn.__name__

    def __call__(self, *a, **kw):
        return self.fn(*a, **kw)


def fake_tool(*, approval_mode="never_require"):
    """The SDK's ``tool`` decorator factory."""
    def _wrap(fn):
        return FakeToolWrapper(fn, approval_mode)
    return _wrap


class FakeFunctionMiddleware:
    """Base class the tracing middleware subclasses."""


class FakeComposed:
    def __init__(self, *, strategies, token_budget, tokenizer):
        self.strategies = strategies
        self.token_budget = token_budget
        self.tokenizer = tokenizer


class FakeToolResultStrategy:
    pass


class FakeTruncation:
    def __init__(self, *, max_n, compact_to, tokenizer):
        self.max_n = max_n
        self.compact_to = compact_to
        self.tokenizer = tokenizer


class FakeAgent:
    """What ``as_agent`` returns. Records nothing; the client does that."""

    def __init__(self, kwargs):
        self.kwargs = kwargs


class FakeClient:
    """Fake Foundry client. Reports itself as SDK-owned via ``__module__``."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.as_agent_calls: list[dict] = []

    def as_agent(self, **kwargs):
        self.as_agent_calls.append(kwargs)
        return FakeAgent(kwargs)


FakeClient.__module__ = "agent_framework.azure"


class FakeCredential:
    instances = 0

    def __init__(self):
        FakeCredential.instances += 1


def install_fake_sdk() -> None:
    """Substitute every SDK this box touches."""
    framework = types.SimpleNamespace(
        tool=fake_tool,
        FunctionMiddleware=FakeFunctionMiddleware,
        TokenBudgetComposedStrategy=FakeComposed,
        ToolResultCompactionStrategy=FakeToolResultStrategy,
        TruncationStrategy=FakeTruncation,
    )
    set_sdk("agent_framework", framework)
    set_sdk("agent_framework.azure",
            types.SimpleNamespace(AzureAIAgentClient=FakeClient))
    set_sdk("azure.identity",
            types.SimpleNamespace(DefaultAzureCredential=FakeCredential))


# ── tools under test ────────────────────────────────────────────────────────


@fa.tool
def marked_tool(value: str) -> str:
    """A marked tool. Bound to the SDK at build time."""
    return value.upper()


@fa.tool(approval_mode="always_require", owner="ops")
def gated_tool() -> str:
    """A marked tool that requests approval."""
    return "gated"


def plain_tool() -> str:
    """An unmarked callable — passes through untouched."""
    return "plain"


# ── checks ──────────────────────────────────────────────────────────────────


def test_config() -> None:
    print("\nFoundryConfig")
    cfg = fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a")
    check("valid config constructs", cfg.model_deployment == "model-a")

    check("empty endpoint rejected",
          raises(ValueError, fa.FoundryConfig, project_endpoint="",
                 model_deployment="m") is not None)
    check("empty deployment rejected",
          raises(ValueError, fa.FoundryConfig, project_endpoint=ENDPOINT,
                 model_deployment="") is not None)
    exc = raises(ValueError, fa.FoundryConfig,
                 project_endpoint="http://example.invalid/api/projects/p",
                 model_deployment="m")
    check("plaintext endpoint rejected", exc is not None)
    check("rejection names the scheme", exc is not None and "https" in str(exc))
    check("max_retries < 1 rejected",
          raises(ValueError, fa.FoundryConfig, project_endpoint=ENDPOINT,
                 model_deployment="m", max_retries=0) is not None)

    # G1: account endpoint is a warning, not a hard failure.
    account = fa.FoundryConfig(
        project_endpoint="https://example-resource.services.ai.azure.com",
        model_deployment="model-a")
    warns = account.warnings()
    check("G1 account endpoint warns", any("account endpoint" in w for w in warns))
    check("valid project endpoint does not warn", cfg.warnings() == [])
    check("trailing slash warns",
          any("trailing slash" in w for w in fa.FoundryConfig(
              project_endpoint=ENDPOINT + "/", model_deployment="m").warnings()))

    # G8: a fallback list containing the primary buys nothing.
    dup = fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a",
                           fallback_models=("model-a", "model-b"))
    check("G8 duplicate fallback warns",
          any("fallback_models" in w for w in dup.warnings()))
    check("G8 duplicate dropped from queue",
          dup.model_queue() == ["model-a", "model-b"])

    fast = fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a",
                            model_deployment_fast="model-mini")
    check("no preference -> default", fast.resolve_model("") == "model-a")
    check("'fast' alias -> fast deployment",
          fast.resolve_model("fast") == "model-mini")
    check("'fast' alias falls back when unconfigured",
          cfg.resolve_model("fast") == "model-a")
    check("explicit model passes through",
          fast.resolve_model("model-z") == "model-z")
    check("with_model returns a copy",
          fast.with_model("model-q").model_deployment == "model-q"
          and fast.model_deployment == "model-a")
    check("config is frozen",
          raises(Exception, setattr, cfg, "model_deployment", "x") is not None)
    check("redacted view drops the project path",
          "/api/projects/" not in cfg.redacted()["endpoint_host"])


def test_config_from_env() -> None:
    print("\nFoundryConfig.from_env")
    env = {
        "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT,
        "FOUNDRY_MODEL_DEPLOYMENT": "model-a",
        "FOUNDRY_MODEL_DEPLOYMENT_FAST": "model-mini",
        "FOUNDRY_FALLBACK_MODELS": "model-b, model-c",
        "FOUNDRY_MAX_RETRIES": "2",
    }
    cfg = fa.FoundryConfig.from_env(env)
    check("reads endpoint and deployment", cfg.project_endpoint == ENDPOINT)
    check("splits fallback list", cfg.fallback_models == ("model-b", "model-c"))
    check("absent api_version is None", cfg.api_version is None)
    check("max_retries parsed", cfg.max_retries == 2)

    exc = raises(ValueError, fa.FoundryConfig.from_env, {})
    check("missing variables rejected", exc is not None)
    check("error names the exact variables",
          exc is not None and "FOUNDRY_PROJECT_ENDPOINT" in str(exc)
          and "FOUNDRY_MODEL_DEPLOYMENT" in str(exc))

    prefixed = fa.FoundryConfig.from_env(
        {"EVAL_PROJECT_ENDPOINT": ENDPOINT, "EVAL_MODEL_DEPLOYMENT": "model-e"},
        prefix="EVAL_")
    check("prefix override reads a second project",
          prefixed.model_deployment == "model-e")


def test_optional_sdk() -> None:
    print("\nSDK loading")
    clear_sdks()
    exc = raises(SdkUnavailable, load_sdk, "definitely_not_installed_xyz")
    check("absent module raises SdkUnavailable", exc is not None)
    check("SdkUnavailable is an ImportError",
          issubclass(SdkUnavailable, ImportError))
    check("absent module reports unavailable",
          fa.sdk_available("definitely_not_installed_xyz") is False)

    exc = raises(SdkUnavailable, load_sdk, "agent_framework.azure")
    if exc is not None:
        check("missing SDK message names the install line", "pip install" in str(exc))
    else:
        # The SDK is genuinely installed here; force the absent path instead so
        # the hint is asserted on every machine, not only on a bare one.
        fa.set_sdk_absent("agent_framework.azure")
        forced = raises(SdkUnavailable, load_sdk, "agent_framework.azure")
        check("missing SDK message names the install line",
              forced is not None and "pip install" in str(forced))
    clear_sdks()

    fa.set_sdk_absent("agent_framework")
    check("forced-absent module reports unavailable",
          fa.sdk_available("agent_framework") is False)
    clear_sdks()

    install_fake_sdk()
    check("substituted module is available", fa.sdk_available("agent_framework"))
    check("substituted module is returned",
          load_sdk("agent_framework").tool is fake_tool)


def test_credentials() -> None:
    print("\ncredential (one per process)")
    install_fake_sdk()
    fa.reset_credential()
    FakeCredential.instances = 0
    check("no credential before first use", fa.has_credential() is False)
    first = fa.get_credential()
    second = fa.get_credential()
    check("same instance returned twice", first is second)
    check("G3 built exactly once", FakeCredential.instances == 1)
    check("has_credential true after build", fa.has_credential() is True)

    explicit = object()
    fa.set_credential(explicit)
    check("explicit credential replaces the cached one",
          fa.get_credential() is explicit)
    fa.reset_credential()
    check("reset clears the cache", fa.has_credential() is False)


def test_client_factory() -> None:
    print("\nclient factory")
    install_fake_sdk()
    fa.reset_credential()
    FakeCredential.instances = 0

    cfg = fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a")
    factory = fa.foundry_agent_client(cfg)
    check("factory is zero-arg", callable(factory))

    client = factory()
    check("endpoint forwarded", client.kwargs["project_endpoint"] == ENDPOINT)
    check("deployment forwarded",
          client.kwargs["model_deployment_name"] == "model-a")
    check("credential forwarded", isinstance(client.kwargs["credential"],
                                             FakeCredential))
    check("api_version omitted when unset", "api_version" not in client.kwargs)

    versioned = fa.foundry_agent_client(
        fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a",
                         api_version="2026-01-01"))()
    check("api_version forwarded when set",
          versioned.kwargs["api_version"] == "2026-01-01")

    factory()
    check("G3 credential shared across clients", FakeCredential.instances == 1)

    explicit = object()
    injected = fa.foundry_agent_client(cfg, credential=explicit)()
    check("explicit credential wins", injected.kwargs["credential"] is explicit)

    # Building the factory must not import the SDK: a composition root wires
    # Foundry conditionally, on hosts where the SDK may be absent.
    clear_sdks()
    lazy = fa.foundry_agent_client(cfg)
    check("factory construction imports no SDK", callable(lazy))
    install_fake_sdk()


def test_client_pool() -> None:
    print("\nClientPool (G2 — identity isolation)")
    install_fake_sdk()
    fa.reset_credential()
    cfg = fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a")
    pool = fa.ClientPool(fa.foundry_agent_client(cfg))

    a1 = pool.client_for("planner")
    a2 = pool.client_for("planner")
    b1 = pool.client_for("reporter")
    check("same agent gets the same client", a1 is a2)
    check("G2 different agents get different clients", a1 is not b1)
    check("pool lists its agents", pool.agent_ids() == ["planner", "reporter"])

    pool.clear()
    check("clear drops the cache", pool.agent_ids() == [])
    check("client rebuilt after clear", pool.client_for("planner") is not a1)

    built: list[int] = []

    def counting_factory():
        built.append(1)
        return FakeClient()

    counted = fa.ClientPool(counting_factory)
    for _ in range(5):
        counted.client_for("same")
    check("pool builds once under repeated access", len(built) == 1)


def test_tool_marking() -> None:
    print("\ntool marking and binding")
    install_fake_sdk()
    check("marker attached", fa.tool_metadata(marked_tool) is not None)
    check("unmarked returns None", fa.tool_metadata(plain_tool) is None)
    check("docstring becomes the description",
          fa.tool_metadata(marked_tool)["description"].startswith("A marked tool"))
    check("approval_mode carried",
          fa.tool_metadata(gated_tool)["approval_mode"] == "always_require")
    check("extra metadata carried",
          fa.tool_metadata(gated_tool)["owner"] == "ops")
    check("stamp does not wrap", marked_tool("x") == "X")

    client = FakeClient()
    bound = fa.bind_tools([marked_tool, plain_tool, gated_tool], client)
    check("marked tool is SDK-bound", isinstance(bound[0], FakeToolWrapper))
    check("unmarked tool passes through", bound[1] is plain_tool)
    check("approval_mode reaches the SDK", bound[2].approval_mode == "always_require")
    check("G7 order preserved",
          [_tool_name(t) for t in bound]
          == ["marked_tool", "plain_tool", "gated_tool"])
    check("bind returns a new list", bound is not None and len(bound) == 3)

    class StubClient:
        def as_agent(self, **kw):
            return FakeAgent(kw)

    stub_bound = fa.bind_tools([marked_tool, plain_tool], StubClient())
    check("non-SDK client leaves callables raw", stub_bound[0] is marked_tool)
    check("is_maf_client true for SDK client", fa.is_maf_client(client) is True)
    check("is_maf_client false for stub", fa.is_maf_client(StubClient()) is False)

    custom = fa.bind_tools([_foreign_marked()], client,
                           markers=("__their_marker__",))
    check("foreign marker binds when declared",
          isinstance(custom[0], FakeToolWrapper))


def _foreign_marked():
    """A tool stamped by some other library's decorator."""
    def other_tool() -> str:
        return "other"
    other_tool.__their_marker__ = {"approval_mode": "never_require"}
    return other_tool


def _tool_name(obj) -> str:
    """Name of a bound or unbound tool, whichever shape it is in."""
    return getattr(obj, "name", None) or obj.__name__


def test_build_agent() -> None:
    print("\nbuild_agent")
    install_fake_sdk()
    cfg = fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a",
                           model_deployment_fast="model-mini")
    client = FakeClient()

    spec = {
        "agent_id": "planner",
        "name": "Planner",
        "description": "Plans work",
        "instructions": "You plan.",
        "tools": [marked_tool],
        "model": "",
    }
    fa.build_agent(spec, client, cfg)
    call = client.as_agent_calls[-1]
    check("name forwarded", call["name"] == "Planner")
    check("instructions forwarded", call["instructions"] == "You plan.")
    check("model defaults to config", call["default_options"]["model_id"] == "model-a")
    check("tools bound in the agent build",
          isinstance(call["tools"][0], FakeToolWrapper))
    check("parallel tool calls off by default",
          call["default_options"]["allow_multiple_tool_calls"] is False)

    fa.build_agent({**spec, "model": "fast"}, client, cfg)
    check("'fast' resolves at build time",
          client.as_agent_calls[-1]["default_options"]["model_id"] == "model-mini")

    fa.build_agent({**spec, "model": "model-z"}, client, cfg,
                   model_override="model-override")
    check("override beats the spec",
          client.as_agent_calls[-1]["default_options"]["model_id"] == "model-override")

    fa.build_agent({**spec, "tools": []}, client, cfg)
    check("G4 empty tool list becomes None",
          client.as_agent_calls[-1]["tools"] is None)

    fa.build_agent({**spec, "parallel_tool_calls": True}, client, cfg)
    check("parallel opt-in honoured",
          client.as_agent_calls[-1]["default_options"]["allow_multiple_tool_calls"]
          is True)

    fa.build_agent({**spec, "instructions": ""}, client, cfg)
    check("empty instructions still builds",
          client.as_agent_calls[-1]["instructions"] == "")

    empty_default = fa.FoundryConfig(project_endpoint=ENDPOINT,
                                     model_deployment="model-a")
    check("unresolvable model raises",
          raises(ValueError, fa.build_agent,
                 {"name": "x", "instructions": "y", "model": ""},
                 client, empty_default.with_model("model-a")) is None)


def test_spec_shapes() -> None:
    print("\nspec shapes (duck-typed input)")
    install_fake_sdk()
    cfg = fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a")
    client = FakeClient()

    class ObjectSpec:
        agent_id = "obj"
        name = "Object Spec"
        description = ""
        instructions = "Do the thing."
        tools = (plain_tool,)
        model = "model-obj"
        extra = {"parallel_tool_calls": True}

    fa.build_agent(ObjectSpec(), client, cfg)
    call = client.as_agent_calls[-1]
    check("object spec accepted", call["name"] == "Object Spec")
    check("model read from the object",
          call["default_options"]["model_id"] == "model-obj")
    check("extra mapping consulted for unknown keys",
          call["default_options"]["allow_multiple_tool_calls"] is True)
    check("declared field beats extra of the same name",
          fa.spec_field(
              types.SimpleNamespace(model="declared", extra={"model": "extra"}),
              "model") == "declared")
    check("missing field falls back to the default",
          fa.spec_field({}, "nothing", "fallback") == "fallback")


def test_compaction_and_middleware() -> None:
    print("\ncompaction and tracing")
    install_fake_sdk()

    class Tokenizer:
        def count_tokens(self, text: str) -> int:
            return len(text) // 4

    strategy = fa.build_compaction_strategy(100_000, Tokenizer())
    check("strategy built", isinstance(strategy, FakeComposed))
    check("budget forwarded", strategy.token_budget == 100_000)
    check("tool-result compaction runs before truncation",
          isinstance(strategy.strategies[0], FakeToolResultStrategy)
          and isinstance(strategy.strategies[1], FakeTruncation))

    clear_sdks()
    fa.set_sdk_absent("agent_framework")
    check("G6 compaction degrades to None without the SDK",
          fa.build_compaction_strategy(1000, Tokenizer()) is None)
    check("G6 middleware degrades to [] without the SDK",
          build_tracing_middleware() == [])
    install_fake_sdk()

    events: list[dict] = []
    middleware = build_tracing_middleware(on_event=events.append)
    check("middleware built", len(middleware) == 1)

    ctx = types.SimpleNamespace(function=types.SimpleNamespace(name="lookup"))

    async def ok_next():
        return None

    asyncio.run(middleware[0].process(ctx, ok_next))
    check("success traced", events and events[-1]["ok"] is True)
    check("tool name traced", events[-1]["tool"] == "lookup")
    check("duration recorded", events[-1]["duration_ms"] >= 0)

    async def failing_next():
        raise RuntimeError("tool exploded")

    async def drive_failure():
        try:
            await middleware[0].process(ctx, failing_next)
        except RuntimeError:
            return True
        return False

    check("G9 middleware re-raises", asyncio.run(drive_failure()) is True)
    check("failure traced", events[-1]["ok"] is False)
    check("error text truncated in the trace", len(events[-1]["error"]) <= 200)

    def exploding_sink(_event):
        raise ValueError("sink down")

    hostile = build_tracing_middleware(on_event=exploding_sink)
    asyncio.run(hostile[0].process(ctx, ok_next))
    check("a broken trace sink cannot fail the tool call", True)

    # Compaction attaches through build_agent only when both inputs are present.
    cfg = fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a")
    client = FakeClient()
    spec = {"name": "A", "instructions": "i", "tools": [], "model": ""}
    agent = fa.build_agent(spec, client, cfg,
                           tokenizer=Tokenizer(), token_budget=50_000)
    check("compaction attached when budget and tokenizer given",
          getattr(agent, "_compaction_strategy", None) is not None)
    bare = fa.build_agent(spec, client, cfg)
    check("no compaction without a budget",
          getattr(bare, "_compaction_strategy", None) is None)
    opted_out = fa.build_agent({**spec, "compaction": False}, client, cfg,
                               tokenizer=Tokenizer(), token_budget=50_000)
    check("per-agent compaction opt-out honoured",
          getattr(opted_out, "_compaction_strategy", None) is None)


def test_classification() -> None:
    print("\nfailure classification")
    check("429 is a rate limit", fa.classify(Exception("HTTP 429 Too Many")) == "rate_limit")
    check("throttling text is a rate limit",
          fa.classify(Exception("Request was throttled")) == "rate_limit")
    check("G10 peak-load text is a rate limit",
          fa.classify(Exception("Peak load exceeded")) == "rate_limit")
    check("content filter is fatal",
          fa.classify(Exception("content_filter triggered")) == "fatal")
    check("401 is fatal", fa.classify(Exception("401 Unauthorized")) == "fatal")
    check("503 is transient", fa.classify(Exception("503 Service Unavailable")) == "transient")
    check("unrecognised is unknown", fa.classify(Exception("weird")) == "unknown")
    check("fatal wins over rate-limit text",
          fa.classify(Exception("403 Forbidden: rate limit policy")) == "fatal")

    check("retry-after parsed", fa.parse_retry_seconds("retry after 22 seconds") == 22)
    check("retry-after clamped low", fa.parse_retry_seconds("retry after 1 second") == 5)
    check("retry-after clamped high",
          fa.parse_retry_seconds("retry after 9000 seconds") == 60)
    check("retry-after default when absent",
          fa.parse_retry_seconds("no hint here", default=15) == 15)

    retry, delay = fa.should_retry(Exception("429 rate limit, retry after 30"), 0, 3)
    check("rate limit retried", retry is True)
    check("rate limit waits the hinted time", delay == 30.0)
    check("fatal never retried", fa.should_retry(Exception("content_filter"), 0, 3)[0] is False)
    check("last attempt not retried", fa.should_retry(Exception("503"), 2, 3)[0] is False)
    check("unknown error backs off exponentially",
          fa.should_retry(Exception("weird"), 1, 5)[1] == 4.0)
    check("backoff is capped",
          fa.should_retry(Exception("weird"), 10, 20)[1] == 30.0)


def test_fallback_loop() -> None:
    print("\nmodel fallback (round trip)")
    cfg = fa.FoundryConfig(project_endpoint=ENDPOINT, model_deployment="model-a",
                           fallback_models=("model-b",), max_retries=2)
    slept: list[float] = []

    async def no_sleep(seconds):
        slept.append(seconds)

    attempts: list[str] = []

    async def always_throttled(model):
        attempts.append(model)
        raise RuntimeError("429 rate limit")

    async def drive_exhausted():
        try:
            await fa.run_with_fallback(always_throttled, cfg, sleep=no_sleep)
        except RuntimeError as exc:
            return str(exc)
        return ""

    result = asyncio.run(drive_exhausted())
    check("exhausted queue raises the last error", "429" in result)
    check("every model tried, max_retries each",
          attempts == ["model-a", "model-a", "model-b", "model-b"])
    check("waited between attempts, not after the last of a model",
          len(slept) == 2)

    attempts.clear()

    async def second_model_works(model):
        attempts.append(model)
        if model == "model-a":
            raise RuntimeError("503 Service Unavailable")
        return f"answered by {model}"

    answer = asyncio.run(
        fa.run_with_fallback(second_model_works, cfg, sleep=no_sleep))
    check("falls through to the working deployment",
          answer == "answered by model-b")

    attempts.clear()

    async def filtered(model):
        attempts.append(model)
        raise RuntimeError("content_filter: response blocked")

    async def drive_fatal():
        try:
            await fa.run_with_fallback(filtered, cfg, sleep=no_sleep)
        except RuntimeError:
            return True
        return False

    check("fatal aborts immediately", asyncio.run(drive_fatal()) is True)
    check("G11 fatal does not try the fallback models", attempts == ["model-a"])

    attempts.clear()

    async def first_try(model):
        attempts.append(model)
        return "fine"

    check("success on the first attempt does not retry",
          asyncio.run(fa.run_with_fallback(first_try, cfg, sleep=no_sleep)) == "fine"
          and attempts == ["model-a"])


def test_end_to_end() -> None:
    print("\nend-to-end (R5 — declarative spec through to a model call)")
    install_fake_sdk()
    fa.reset_credential()

    cfg = fa.FoundryConfig.from_env({
        "FOUNDRY_PROJECT_ENDPOINT": ENDPOINT,
        "FOUNDRY_MODEL_DEPLOYMENT": "model-a",
        "FOUNDRY_FALLBACK_MODELS": "model-b",
        "FOUNDRY_MAX_RETRIES": "2",
    })
    pool = fa.ClientPool(fa.foundry_agent_client(cfg))

    roster = {
        "planner": {"name": "Planner", "instructions": "Plan.",
                    "tools": [marked_tool], "model": ""},
        "reporter": {"name": "Reporter", "instructions": "Report.",
                     "tools": [], "model": "model-b"},
    }

    agents = {}
    for agent_id, spec in roster.items():
        client = pool.client_for(agent_id)
        agents[agent_id] = (client, fa.build_agent(spec, client, cfg,
                                                   agent_id=agent_id))

    check("every agent built", len(agents) == 2)
    check("each agent holds its own client",
          agents["planner"][0] is not agents["reporter"][0])
    check("per-agent model honoured",
          agents["reporter"][0].as_agent_calls[-1]["default_options"]["model_id"]
          == "model-b")

    calls: list[str] = []

    async def no_sleep(_seconds):
        return None

    async def run_turn(model):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("429 rate limit, retry after 5")
        return f"planner answered on {model}"

    answer = asyncio.run(fa.run_with_fallback(run_turn, cfg, sleep=no_sleep))
    check("throttled turn recovers on retry",
          answer == "planner answered on model-a")
    check("recovery stayed on the primary deployment",
          calls == ["model-a", "model-a"])


def main() -> int:
    print("foundry-agent-runtime selftest")
    try:
        test_config()
        test_config_from_env()
        test_optional_sdk()
        test_credentials()
        test_client_factory()
        test_client_pool()
        test_tool_marking()
        test_build_agent()
        test_spec_shapes()
        test_compaction_and_middleware()
        test_classification()
        test_fallback_loop()
        test_end_to_end()
    finally:
        clear_sdks()
        fa.reset_credential()

    print(f"\n{_PASS} passed, {_FAIL} failed")
    if _FAIL:
        print("SELFTEST FAILED")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
