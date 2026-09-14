"""selftest — proves the box works here, with no test framework and no SDKs.

Run: ``python3 tests/selftest.py``. Exits non-zero on any failure.

Every Azure SDK is replaced by a fake module through ``azdata.core.optional``,
which is why this can exercise token refresh, transient retry, throttle
release, continuation paging and quota fallback on a laptop with no cloud
account and nothing installed. The fakes assert on what the connector sent,
so this is a contract test of the transport, not a smoke test of imports.
"""

from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from azdata import (  # noqa: E402
    AzureDataConfig,
    CircuitBreaker,
    CosmosContainer,
    GraphConnector,
    GraphRetryBudget,
    GremlinConnector,
    KqlConnector,
    MissingDependency,
    SearchConnector,
    ThrottleError,
    ThrottleGate,
    connect,
    degraded_envelope,
    ensure_limit,
    error_envelope,
    is_error,
    reset_gates,
    validate_read_only,
)
import azdata.fabric_graph.read as graph_module  # noqa: E402
from azdata.core.optional import clear_overrides, load, override  # noqa: E402

_FAILURES: list[str] = []


def check(label: str, condition: bool) -> None:
    if condition:
        print(f"  ok   {label}")
    else:
        print(f"  FAIL {label}")
        _FAILURES.append(label)


def section(title: str) -> None:
    print(title)


# ── Fakes ────────────────────────────────────────────────────────────────────


class FakeToken:
    def __init__(self, token: str = "tok", expires_in: float = 3600.0) -> None:
        import time

        self.token = token
        self.expires_on = time.time() + expires_in


class FakeCredential:
    """Counts token acquisitions so refresh behaviour is observable."""

    def __init__(self, expires_in: float = 3600.0) -> None:
        self.calls = 0
        self._expires_in = expires_in

    def get_token(self, scope: str) -> FakeToken:
        self.calls += 1
        return FakeToken(f"tok-{self.calls}", self._expires_in)


def fake_gremlin_modules(results, fail_first_with: str | None = None):
    """Return (client_module, serializer_module, log) for the driver fakes."""
    log = {"queries": [], "clients": 0, "closed": 0}
    state = {"failed": False}

    class _Result:
        def __init__(self, value):
            self._value = value

        def result(self):
            return self._value

    class _Future:
        def __init__(self, value):
            self._value = value

        def all(self):
            return _Result(self._value)

    class _Client:
        def __init__(self, **kwargs):
            log["clients"] += 1
            self.kwargs = kwargs

        def submit(self, query):
            log["queries"].append(query)
            if fail_first_with and not state["failed"]:
                state["failed"] = True
                raise RuntimeError(fail_first_with)
            return _Future(results)

        def close(self):
            log["closed"] += 1

    client_mod = types.SimpleNamespace(Client=_Client)
    serializer_mod = types.SimpleNamespace(
        GraphSONSerializersV2d0=lambda: "serializer"
    )
    return client_mod, serializer_mod, log


def fake_kusto_module(rows, columns, raise_with: str | None = None):
    log = {"queries": [], "databases": []}

    class _Col:
        def __init__(self, name, ctype):
            self.column_name = name
            self.column_type = ctype

    class _Row(dict):
        pass

    class _Primary:
        def __init__(self):
            self.columns = [_Col(n, t) for n, t in columns]

        def __iter__(self):
            return iter(rows)

    class _Response:
        primary_results = [_Primary()]

    class _Client:
        def __init__(self, kcsb):
            self.kcsb = kcsb

        def execute(self, database, query):
            log["queries"].append(query)
            log["databases"].append(database)
            if raise_with:
                raise RuntimeError(raise_with)
            return _Response()

    class _Kcsb:
        @staticmethod
        def with_azure_token_credential(uri, credential):
            return {"uri": uri, "credential": credential}

    module = types.SimpleNamespace(
        KustoClient=_Client, KustoConnectionStringBuilder=_Kcsb
    )
    return module, log


def fake_search_modules(docs, quota_marker=None, fail_on_iteration=False):
    """quota_marker set => the semantic attempt raises the quota error."""
    log = {"calls": []}

    class _QuotaIterator:
        def __iter__(self):
            raise RuntimeError(quota_marker)

    class _Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def search(self, **params):
            log["calls"].append(params)
            semantic = "query_type" in params
            if quota_marker and semantic:
                if fail_on_iteration:
                    return _QuotaIterator()
                raise RuntimeError(quota_marker)
            return list(docs)

    documents = types.SimpleNamespace(SearchClient=_Client)
    models = types.SimpleNamespace(
        QueryType=types.SimpleNamespace(SEMANTIC="semantic"),
        QueryCaptionType=types.SimpleNamespace(EXTRACTIVE="extractive"),
        VectorizableTextQuery=lambda **kw: kw,
    )
    return documents, models, log


class FakeResponse:
    def __init__(self, status_code, body=None, headers=None, text=""):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = text or json.dumps(body or {})

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def fake_httpx_module(responses, log):
    """responses: list consumed one per POST."""

    class _AsyncClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            log["posts"].append({"url": url, "json": json, "headers": headers})
            return responses.pop(0)

        async def get(self, url, headers=None):
            log["gets"].append(url)
            return responses.pop(0)

    return types.SimpleNamespace(AsyncClient=_AsyncClient)


def fake_cosmos_module(rows, delay=0.0):
    log = {"queries": [], "closed": 0}

    class _Container:
        async def query_items(self, query=None, parameters=None):
            log["queries"].append(query)
            if delay:
                await asyncio.sleep(delay)
            for row in rows:
                yield row

    class _Database:
        def get_container_client(self, name):
            return _Container()

    class _Client:
        def __init__(self, url=None, credential=None):
            self.url = url
            self.credential = credential

        def get_database_client(self, name):
            return _Database()

        async def close(self):
            log["closed"] += 1

    return types.SimpleNamespace(CosmosClient=_Client), log


def install_gremlin(results, fail_first_with=None):
    client_mod, serializer_mod, log = fake_gremlin_modules(results, fail_first_with)
    override("gremlin_python.driver.client", client_mod)
    override("gremlin_python.driver.serializer", serializer_mod)
    return log


# ── Config ───────────────────────────────────────────────────────────────────


def test_config() -> None:
    section("config")
    cfg = AzureDataConfig.from_env(
        {
            "AZDATA_GREMLIN_ENDPOINT": "wss://example/gremlin",
            "AZDATA_GREMLIN_DATABASE": "db",
            "AZDATA_GREMLIN_GRAPH": "g",
            "AZDATA_MAX_CONCURRENT": "0",
            "AZDATA_MAX_ROWS": "not-a-number",
        }
    )
    check("reads prefixed environment variables", cfg.gremlin_database == "db")
    check("clamps max_concurrent to >= 1 (G6)", cfg.max_concurrent == 1)
    check("falls back on an unparseable int", cfg.max_rows == 500)

    unprefixed = AzureDataConfig.from_env({"SEARCH_ENDPOINT": "https://s"}, prefix="")
    check("adopts existing variable names", unprefixed.search_endpoint == "https://s")

    partial = AzureDataConfig(tenant_id="t", client_id="c")
    check("ignores a partial service principal", partial.service_principal is None)
    complete = AzureDataConfig(tenant_id="t", client_id="c", client_secret="s")
    check("accepts a complete service principal", complete.service_principal is not None)
    check("never repr()s the secret", "s3cr3t" not in repr(
        AzureDataConfig(client_secret="s3cr3t")))

    graph_cfg = AzureDataConfig(fabric_workspace_id="w", fabric_graph_model_id="m")
    check(
        "builds the executeQuery url",
        graph_cfg.fabric_graph_url.endswith("/workspaces/w/graphmodels/m/executeQuery"),
    )
    check("empty url when unconfigured", AzureDataConfig().fabric_graph_url == "")


# ── Envelope ─────────────────────────────────────────────────────────────────


def test_envelope() -> None:
    section("envelope")
    payload = json.loads(error_envelope("failed at https://acct.documents.azure.com/x"))
    check("strips urls from the detail", "azure.com" not in payload["detail"])
    check("keeps the error flag", payload["error"] is True)

    long_detail = json.loads(error_envelope("x" * 900))["detail"]
    check("caps the detail at 500 chars", len(long_detail) == 500)

    with_exc = json.loads(error_envelope("Search failed", exc=ValueError("bad")))
    check("appends the exception type", "ValueError" in with_exc["detail"])

    degraded = json.loads(degraded_envelope("breaker open"))
    check("degraded is a distinct shape", "error" not in degraded)
    check("is_error distinguishes them", is_error(degraded_envelope("x")) is False)
    check("is_error survives non-json", is_error("not json at all") is False)


# ── Guardrails ───────────────────────────────────────────────────────────────


def test_guardrails() -> None:
    section("guardrails")
    check(
        "blocks a gremlin write",
        validate_read_only("g.V().addV('x')", "gremlin") is not None,
    )
    check(
        "allows a gremlin read",
        validate_read_only("g.V().hasLabel('x')", "gremlin") is None,
    )
    check(
        "blocks a kql command hidden after a semicolon",
        validate_read_only("T | take 1; .drop table T", "kql") is not None,
    )
    check(
        "allows read-only schema discovery",
        validate_read_only(".show tables", "kql") is None,
    )
    check(
        "does not trip on a cypher string literal",
        validate_read_only("MATCH (n) WHERE n.s = 'CREATED' RETURN n", "cypher") is None,
    )
    check(
        "rejects an over-long query",
        validate_read_only("x" * 3000, "cypher") is not None,
    )

    check(
        "injects a gremlin limit",
        ensure_limit("g.V()", "gremlin", 5) == "g.V().limit(5)",
    )
    check(
        "is idempotent",
        ensure_limit(ensure_limit("g.V()", "gremlin", 5), "gremlin", 5)
        == "g.V().limit(5)",
    )
    check(
        "leaves an aggregate alone",
        ensure_limit("g.V().count()", "gremlin", 5) == "g.V().count()",
    )
    check(
        "injects a kql take",
        ensure_limit("Events", "kql", 10) == "Events | take 10",
    )
    check(
        "injects SQL TOP after SELECT",
        ensure_limit("SELECT * FROM c", "sql", 7) == "SELECT TOP 7 * FROM c",
    )
    check(
        "passes an unknown language through",
        ensure_limit("weird query", "sparql") == "weird query",
    )


# ── Breaker and gate ─────────────────────────────────────────────────────────


def test_breaker() -> None:
    section("circuit breaker")
    breaker = CircuitBreaker("t", failure_threshold=2, cooldown_secs=0.05)
    check("starts closed", breaker.is_open() is False)
    breaker.record_failure()
    check("one failure does not trip", breaker.is_open() is False)
    breaker.record_failure()
    check("threshold trips it", breaker.is_open() is True)

    import time as _time

    _time.sleep(0.06)
    check("cooldown grants one probe", breaker.is_open() is False)
    check("and only one", breaker.is_open() is True)
    breaker.record_success()
    check("a successful probe closes it", breaker.is_open() is False)

    breaker2 = CircuitBreaker("t2", failure_threshold=1, cooldown_secs=0.05)
    breaker2.record_failure()
    _time.sleep(0.06)
    breaker2.is_open()          # take the probe
    breaker2.record_failure()   # probe fails
    check(
        "a failed probe doubles the cooldown",
        breaker2.status()["cooldown_secs"] > 0.05,
    )


async def test_gate() -> None:
    section("throttle gate")
    gate = ThrottleGate("g", max_concurrent=1, failure_threshold=1, cooldown_secs=0.05)
    was_probe = await gate.acquire()
    check("a normal acquire is not a probe", was_probe is False)
    check("the permit is taken", gate.status()["semaphore_available"] == 0)
    gate.release(was_probe=was_probe)
    check("release returns the permit", gate.status()["semaphore_available"] == 1)

    await gate.record_429()
    try:
        await gate.acquire()
        check("open circuit raises ThrottleError", False)
    except ThrottleError as exc:
        check("open circuit raises ThrottleError", exc.retry_after >= 0)
        check("the message names no internal service", "circuit" not in str(exc).lower())

    await asyncio.sleep(0.06)
    probe = await gate.acquire()
    check("the probe bypasses the semaphore", probe is True)
    check("so no permit was consumed", gate.status()["semaphore_available"] == 1)
    gate.release(was_probe=probe)
    check("and a probe release adds none back", gate.status()["semaphore_available"] == 1)


# ── Gremlin ──────────────────────────────────────────────────────────────────


async def test_gremlin() -> None:
    section("gremlin connector")
    cfg = AzureDataConfig(
        gremlin_endpoint="wss://example/gremlin",
        gremlin_database="db",
        gremlin_graph="g",
        max_rows=25,
    )
    cred = FakeCredential()

    log = install_gremlin([{"id": "a"}])
    conn = GremlinConnector.from_config(cfg, lambda: cred)
    payload = json.loads(await conn.execute("g.V()"))
    check("returns a bare list", payload == [{"id": "a"}])
    check("injected the configured limit", log["queries"][-1] == "g.V().limit(25)")
    check("acquired exactly one token", cred.calls == 1)

    await conn.execute("g.V().hasLabel('x')")
    check("reuses the cached client", log["clients"] == 1)
    check("and does not re-acquire the token", cred.calls == 1)

    blocked = json.loads(await conn.execute("g.V().drop()"))
    check("refuses a write", blocked["error"] is True)
    check("without reaching the driver", len(log["queries"]) == 2)

    unconfigured = GremlinConnector.from_config(AzureDataConfig(), lambda: cred)
    detail = json.loads(await unconfigured.execute("g.V()"))["detail"]
    check("names the missing configuration", "not configured" in detail)

    # A transport error rebuilds the client and retries exactly once.
    retry_log = install_gremlin(
        [{"id": "b"}], fail_first_with="Connection was already closed"
    )
    retry_conn = GremlinConnector.from_config(cfg, lambda: FakeCredential())
    retried = json.loads(await retry_conn.execute("g.V()"))
    check("retries a transient transport failure", retried == [{"id": "b"}])
    check("after rebuilding the client (G1)", retry_log["clients"] == 2)

    # A non-transient error is not retried.
    perm_log = install_gremlin([], fail_first_with="syntax error in traversal")
    perm_conn = GremlinConnector.from_config(cfg, lambda: FakeCredential())
    failed = json.loads(await perm_conn.execute("g.V()"))
    check("does not retry a query error", failed["error"] is True)
    check("so the client is built once", perm_log["clients"] == 1)

    # An expiring token forces a rebuild before the query runs.
    expiring_log = install_gremlin([{"id": "c"}])
    expiring_cred = FakeCredential(expires_in=10.0)   # inside the 300s margin
    expiring = GremlinConnector.from_config(cfg, lambda: expiring_cred)
    await expiring.execute("g.V()")
    await expiring.execute("g.V()")
    check("rebuilds before the token margin (G1)", expiring_cred.calls == 2)
    check("closing the old client first", expiring_log["closed"] == 1)


# ── KQL ──────────────────────────────────────────────────────────────────────


async def test_kql() -> None:
    section("kql connector")
    reset_gates()
    cfg = AzureDataConfig(
        kql_query_uri="https://cluster.kusto.windows.net",
        kql_database="db",
        max_rows=10,
        max_concurrent=1,
        breaker_threshold=1,
        breaker_cooldown_secs=0.05,
    )

    class _Stamp:
        def isoformat(self):
            return "2026-01-01T00:00:00Z"

    rows = [{"name": "a", "ts": _Stamp()}]
    module, log = fake_kusto_module(rows, [("name", "string"), ("ts", "datetime")])
    override("azure.kusto.data", module)

    conn = KqlConnector.from_config(cfg, lambda: FakeCredential(), gate_name="kql-test")
    payload = json.loads(await conn.execute("Events"))
    check("shapes columns and rows", payload["columns"][0]["name"] == "name")
    check("stringifies datetimes", payload["rows"][0]["ts"] == "2026-01-01T00:00:00Z")
    check("injected the take", log["queries"][-1] == "Events | take 10")
    check("used the configured database", log["databases"][-1] == "db")

    gate = await conn._gate_provider()  # noqa: SLF001 — asserting the invariant
    check("released the permit", gate.status()["semaphore_available"] == 1)

    blocked = json.loads(await conn.execute("Events; .drop table Events"))
    check("refuses a management command", blocked["error"] is True)

    unconfigured = KqlConnector.from_config(AzureDataConfig(), lambda: FakeCredential())
    check("reports missing configuration", is_error(await unconfigured.execute("T")))

    # A failure must still release the permit, or the gate deadlocks.
    reset_gates()
    failing_module, _ = fake_kusto_module([], [], raise_with="Request is throttled (429)")
    override("azure.kusto.data", failing_module)
    failing = KqlConnector.from_config(
        cfg, lambda: FakeCredential(), gate_name="kql-fail"
    )
    check("an SDK failure is an envelope", is_error(await failing.execute("Events")))
    failing_gate = await failing._gate_provider()  # noqa: SLF001
    check(
        "the permit is released on failure",
        failing_gate.status()["semaphore_available"] == 1,
    )
    check("a 429 counts against the breaker", failing_gate.status()["state"] == "open")


# ── Search ───────────────────────────────────────────────────────────────────


def test_search() -> None:
    section("search connector")
    from azdata.search.read import SEMANTIC_QUOTA_MARKER

    cfg = AzureDataConfig(search_endpoint="https://search.example.net")
    docs = [{"chunk": "hello", "title": "t"}]

    documents, models, log = fake_search_modules(docs)
    override("azure.search.documents", documents)
    override("azure.search.documents.models", models)

    conn = SearchConnector.from_config(cfg, lambda: FakeCredential())
    payload = json.loads(
        conn.execute(
            "q",
            index_name="idx",
            semantic_config="idx-sem",
            project_doc=lambda d: {"text": d["chunk"]},
        )
    )
    check("returns results and a count", payload["count"] == 1)
    check("applies the injected projection", payload["results"][0] == {"text": "hello"})
    check("used the semantic ranker", "query_type" in log["calls"][0])

    # Quota exhaustion on the call must degrade, not fail.
    documents, models, quota_log = fake_search_modules(
        docs, quota_marker=f"{SEMANTIC_QUOTA_MARKER} for this service"
    )
    override("azure.search.documents", documents)
    override("azure.search.documents.models", models)
    quota_conn = SearchConnector.from_config(cfg, lambda: FakeCredential())
    quota_payload = json.loads(
        quota_conn.execute(
            "q", index_name="idx", semantic_config="idx-sem",
            project_doc=lambda d: {"text": d["chunk"]},
        )
    )
    check("falls back without the semantic ranker (G4)", quota_payload["count"] == 1)
    check("and retried exactly once", len(quota_log["calls"]) == 2)
    check(
        "the retry dropped query_type", "query_type" not in quota_log["calls"][1]
    )
    check(
        "the breaker did not trip",
        quota_conn.breaker_for(cfg.search_endpoint).is_open() is False,
    )

    # The same error can arrive while iterating the lazy pager.
    documents, models, iter_log = fake_search_modules(
        docs, quota_marker=SEMANTIC_QUOTA_MARKER, fail_on_iteration=True
    )
    override("azure.search.documents", documents)
    override("azure.search.documents.models", models)
    iter_conn = SearchConnector.from_config(cfg, lambda: FakeCredential())
    iter_payload = json.loads(
        iter_conn.execute(
            "q", index_name="idx", semantic_config="idx-sem",
            project_doc=lambda d: {"text": d["chunk"]},
        )
    )
    check("recovers from quota during iteration (G5)", iter_payload["count"] == 1)
    check("having retried once", len(iter_log["calls"]) == 2)

    # An open breaker degrades rather than calling the service.
    documents, models, _ = fake_search_modules(docs)
    override("azure.search.documents", documents)
    override("azure.search.documents.models", models)
    open_conn = SearchConnector.from_config(
        cfg, lambda: FakeCredential(), breaker_key_prefix="search-open-test"
    )
    breaker = open_conn.breaker_for(cfg.search_endpoint)
    for _ in range(5):
        breaker.record_failure()
    degraded = json.loads(
        open_conn.execute("q", index_name="idx", project_doc=lambda d: d)
    )
    check("an open breaker degrades", degraded["degraded"] is True)

    unconfigured = SearchConnector.from_config(
        AzureDataConfig(), lambda: FakeCredential()
    )
    check(
        "reports a missing endpoint",
        is_error(unconfigured.execute("q", index_name="i", project_doc=lambda d: d)),
    )


# ── Fabric GraphModel ────────────────────────────────────────────────────────


async def test_graph() -> None:
    section("graph connector")
    reset_gates()
    cfg = AzureDataConfig(
        fabric_workspace_id="w",
        fabric_graph_model_id="m",
        max_concurrent=1,
        breaker_cooldown_secs=0.05,
    )
    budget = GraphRetryBudget(default_429_wait=1, continuation_wait_secs=0)

    slept: list[float] = []
    permits_during_sleep: list[int] = []
    real_asyncio = graph_module.asyncio

    async def fake_sleep(seconds):
        slept.append(seconds)

    graph_module.asyncio = types.SimpleNamespace(sleep=fake_sleep)
    try:
        # Happy path.
        log = {"posts": [], "gets": []}
        override(
            "httpx",
            fake_httpx_module(
                [FakeResponse(200, {"status": {"code": "00000"},
                                    "result": {"columns": [{"name": "n"}],
                                               "data": [{"n": 1}]}})],
                log,
            ),
        )
        conn = GraphConnector.from_config(
            cfg, lambda: FakeCredential(), gate_name="graph-ok", budget=budget
        )
        result = await conn.execute("MATCH (n) RETURN n")
        check("returns a dict, not a string", isinstance(result, dict))
        check("carries columns and data", result["data"] == [{"n": 1}])
        check("sent a bearer token", log["posts"][0]["headers"]["Authorization"].startswith("Bearer "))

        # HTTP 200 with a GQL error code is a failure (G7).
        override(
            "httpx",
            fake_httpx_module(
                [FakeResponse(200, {"status": {"code": "42001",
                                               "cause": {"description": "bad syntax"}}})],
                {"posts": [], "gets": []},
            ),
        )
        gql_err = await GraphConnector.from_config(
            cfg, lambda: FakeCredential(), gate_name="graph-gqlerr", budget=budget
        ).execute("MATCH")
        check("treats a GQL status code as an error (G7)", gql_err["error"] is True)
        check("surfaces the cause", "bad syntax" in gql_err["detail"])

        # 429 honours Retry-After, and releases the permit while waiting (G3).
        reset_gates()
        gate_log = {"posts": [], "gets": []}
        override(
            "httpx",
            fake_httpx_module(
                [
                    FakeResponse(429, {}, headers={"Retry-After": "3"}),
                    FakeResponse(200, {"status": {"code": "00000"},
                                       "result": {"columns": [], "data": [{"n": 2}]}}),
                ],
                gate_log,
            ),
        )
        throttled_conn = GraphConnector.from_config(
            cfg, lambda: FakeCredential(), gate_name="graph-429", budget=budget
        )
        gate = await throttled_conn._gate_provider()  # noqa: SLF001

        async def watching_sleep(seconds):
            slept.append(seconds)
            permits_during_sleep.append(gate.status()["semaphore_available"])

        graph_module.asyncio = types.SimpleNamespace(sleep=watching_sleep)
        throttled = await throttled_conn.execute("MATCH")
        check("retries after a 429", throttled["data"] == [{"n": 2}])
        check("honoured Retry-After with jitter", 2.0 <= slept[-1] <= 4.0)
        check(
            "released the permit while waiting (G3)",
            permits_during_sleep and permits_during_sleep[-1] == 1,
        )
        check("and re-acquired it", gate.status()["semaphore_available"] == 1)

        # Retry-After is bounded, so a bad header cannot park the process.
        graph_module.asyncio = types.SimpleNamespace(sleep=fake_sleep)
        reset_gates()
        override(
            "httpx",
            fake_httpx_module(
                [
                    FakeResponse(429, {}, headers={"Retry-After": "99999"}),
                    FakeResponse(200, {"status": {"code": "00000"},
                                       "result": {"columns": [], "data": []}}),
                ],
                {"posts": [], "gets": []},
            ),
        )
        slept.clear()
        await GraphConnector.from_config(
            cfg, lambda: FakeCredential(), gate_name="graph-badheader", budget=budget
        ).execute("MATCH")
        check("bounds an absurd Retry-After", slept[-1] < 10)

        # Cold start backs off and retries.
        reset_gates()
        override(
            "httpx",
            fake_httpx_module(
                [
                    FakeResponse(500, {"errorCode": "ColdStartTimeout"}),
                    FakeResponse(200, {"status": {"code": "00000"},
                                       "result": {"columns": [], "data": [{"n": 3}]}}),
                ],
                {"posts": [], "gets": []},
            ),
        )
        cold = await GraphConnector.from_config(
            cfg, lambda: FakeCredential(), gate_name="graph-cold", budget=budget
        ).execute("MATCH")
        check("retries a cold start", cold["data"] == [{"n": 3}])

        # Any other 500 is a real failure.
        reset_gates()
        override(
            "httpx",
            fake_httpx_module(
                [FakeResponse(500, {"errorCode": "Other"}, text="boom")],
                {"posts": [], "gets": []},
            ),
        )
        hard = await GraphConnector.from_config(
            cfg, lambda: FakeCredential(), gate_name="graph-500", budget=budget
        ).execute("MATCH")
        check("does not retry an ordinary 500", hard["error"] is True)

        # Continuation paging accumulates every page.
        reset_gates()
        page_log = {"posts": [], "gets": []}
        override(
            "httpx",
            fake_httpx_module(
                [
                    FakeResponse(200, {"status": {"code": "02000"},
                                       "result": {"columns": [{"name": "n"}],
                                                  "data": [{"n": 1}],
                                                  "nextPage": "cursor-1"}}),
                    FakeResponse(200, {"status": {"code": "00000"},
                                       "result": {"columns": [{"name": "n"}],
                                                  "data": [{"n": 2}]}}),
                ],
                page_log,
            ),
        )
        paged = await GraphConnector.from_config(
            cfg, lambda: FakeCredential(), gate_name="graph-page", budget=budget
        ).execute("MATCH")
        check("accumulates continuation pages", paged["data"] == [{"n": 1}, {"n": 2}])
        check(
            "sent the continuation token",
            page_log["posts"][1]["json"]["continuationToken"] == "cursor-1",
        )

        unconfigured = GraphConnector.from_config(
            AzureDataConfig(), lambda: FakeCredential(), gate_name="graph-unset"
        )
        check("reports missing configuration", (await unconfigured.execute("M"))["error"])
    finally:
        graph_module.asyncio = real_asyncio


# ── Cosmos ───────────────────────────────────────────────────────────────────


async def test_cosmos() -> None:
    section("cosmos container")
    module, log = fake_cosmos_module([{"id": "1"}])
    override("azure.cosmos.aio", module)

    store = CosmosContainer.from_config(
        AzureDataConfig(cosmos_endpoint="https://acct.documents.azure.com/"),
        FakeCredential(),
        database="db",
        container="items",
    )
    # The regression that matters: a missing asyncio import inside is_healthy
    # is swallowed by the bare except and pins the caller on its fallback
    # store forever. This assertion is what makes that impossible (G11).
    check("a healthy container probes True (G11)", await store.is_healthy() is True)
    check("used a bounded probe query", "SELECT TOP 1" in log["queries"][0])

    slow_module, _ = fake_cosmos_module([{"id": "1"}], delay=1.0)
    override("azure.cosmos.aio", slow_module)
    slow = CosmosContainer.from_config(
        AzureDataConfig(cosmos_endpoint="https://acct.documents.azure.com/"),
        FakeCredential(),
        database="db",
        container="slow",
    )
    check("a slow container probes False", await slow.is_healthy(timeout=0.05) is False)

    store.check_breaker()  # closed: must not raise
    for _ in range(5):
        store.fail(RuntimeError("cosmos down"))
    try:
        store.check_breaker()
        check("an open breaker refuses the call", False)
    except Exception as exc:
        check("an open breaker refuses the call", "unavailable" in str(exc))
    wrapper = store.fail(ValueError("root"))
    check("the wrapper keeps __cause__", isinstance(wrapper.__cause__, ValueError))

    await store.close()
    check("closes the client", log["closed"] == 1)


# ── Seam and dependency surface ──────────────────────────────────────────────


def test_seam() -> None:
    section("injection seam")
    cfg = AzureDataConfig(
        gremlin_endpoint="wss://x", gremlin_database="d", gremlin_graph="g",
        search_endpoint="https://s",
    )
    connectors = connect(cfg, credential_provider=lambda: FakeCredential())
    check("connect() needs no environment", connectors.config is cfg)
    check("connectors are cached", connectors.gremlin is connectors.gremlin)
    reported = connectors.configured()
    check("reports what is configured", reported["gremlin"] and reported["search"])
    check("and what is not", reported["kql"] is False and reported["graph"] is False)
    check("building a connector performs no I/O", connectors.search is not None)


def test_missing_dependency() -> None:
    section("missing dependency")
    clear_overrides()
    try:
        load("definitely_not_installed_sdk", dist="some-distribution")
        check("raises MissingDependency", False)
    except MissingDependency as exc:
        check("raises MissingDependency", True)
        check("names the distribution to install", "some-distribution" in str(exc))


# ── Runner ───────────────────────────────────────────────────────────────────


async def main() -> int:
    try:
        test_config()
        test_envelope()
        test_guardrails()
        test_breaker()
        await test_gate()
        await test_gremlin()
        await test_kql()
        test_search()
        await test_graph()
        await test_cosmos()
        test_seam()
        test_missing_dependency()
    finally:
        clear_overrides()
        reset_gates()

    print()
    if _FAILURES:
        print(f"FAILED: {len(_FAILURES)} check(s)")
        for failure in _FAILURES:
            print(f"  - {failure}")
        return 1
    print("selftest passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
