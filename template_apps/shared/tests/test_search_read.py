"""Offline public facade contracts through native SDK serialization."""

from __future__ import annotations

import asyncio
import ast
import threading
from concurrent.futures import ThreadPoolExecutor
from contextvars import ContextVar
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from azdata import AsyncTransport, ConfigurationError, ConnectorConfig, DataConnector, HttpResponse, Limits, Policy, ResourceAddress
from search_read_adapter import SearchError, SearchReadClient


INDEX = "fixture"
HOST = "unit.search.windows.net"
CONFIG = ConnectorConfig(f"https://{HOST}", ResourceAddress({"index": INDEX}), (HOST,))
POLICY = Policy("offline-reader", grants={"query", "read"}, max_concurrency=1,
                limits=Limits(timeout_seconds=30, max_items=100,
                              max_output_bytes=1_048_576, max_attempts=1))


class Credential:
    def __init__(self):
        self.calls = 0
        self.closed = 0

    def get_token(self, scope):
        self.calls += 1
        return SimpleNamespace(token="offline-fixture", expires_on=2**31)

    def close(self):
        self.closed += 1


class ScriptedTransport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.closed = 0

    async def request(self, request):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response

    async def aclose(self):
        self.closed += 1


def client_for(*responses, config=CONFIG, policy=POLICY, credential=None):
    transport: AsyncTransport = ScriptedTransport(*responses)
    borrowed = credential if credential is not None else Credential()
    return SearchReadClient(config, credential=borrowed, policy=policy, transport=transport), borrowed, transport


def test_query_forwarding_thaws_values_and_only_aliases_knowledge_annotation():
    """Nested values thaw to normal dict/list; absent fields stay absent, ordinary null stays null;
    REST annotation alias only for knowledge caller; no sort/dedup.
    """
    hits = [{"id": "z", "title": None, "tags": ["Windows", "Linux"],
             "nested": {"ordinary": None, "values": [1, True]}, "@search.score": 1.25,
             "@search.rerankerScore": 2.5, "@search.highlights": {"title": ["hit"]}},
            {"id": "a", "@search.score": 1.25}]
    client, credential, transport = client_for(HttpResponse(200, {"value": hits}))
    with client:
        result = client.search(INDEX, "discovery", top=2, filter="doc_kind eq 'analytic'",
                               select=("id", "title", "tags", "nested"))
    request = transport.requests[0]
    assert request.method == "POST"
    assert request.body["search"] == "discovery"
    assert request.body["top"] == 2
    assert request.body["filter"] == "doc_kind eq 'analytic'"
    assert request.body["select"] == "id,title,tags,nested"
    assert [row["id"] for row in result] == ["z", "a"]
    assert result[0]["title"] is None
    assert "title" not in result[1]
    assert result[0]["nested"] == {"ordinary": None, "values": [1, True]}
    assert isinstance(result[0]["nested"], dict)
    assert isinstance(result[0]["nested"]["values"], list)
    assert result[0]["@search.rerankerScore"] == 2.5
    assert "@search.reranker_score" not in result[0]
    assert len(transport.requests) == credential.calls == 1


@pytest.mark.parametrize("count", [0, 1234])
def test_count_is_exact_metadata_not_number_of_key_documents(count):
    client, _, transport = client_for(HttpResponse(200, {"@odata.count": count, "value": [{"id": "one"}]}))
    with client:
        assert client.search_count(INDEX, "*", filter="doc_kind eq 'analytic'") == count
    assert transport.requests[0].body == {
        "search": "*", "top": 1, "select": "id", "filter": "doc_kind eq 'analytic'", "count": True}


@pytest.mark.parametrize("metadata", [{}, {"@odata.count": None}, {"@odata.count": True}, {"@odata.count": -1}])
def test_count_unknown_or_invalid_refuses_instead_of_zero(metadata):
    """Query success alone does not establish completeness; count missing is unknown;
    error codes are payload-free; borrowed resources stay borrowed.
    """
    client, _, _ = client_for(HttpResponse(200, {**metadata, "value": []}))
    with client, pytest.raises(SearchError) as caught:
        client.search_count(INDEX)
    assert caught.value.status == 503
    assert caught.value.body is None


def test_keyed_content_and_absence_remain_distinct():
    document = {"id": "one", "title": None, "path": "source.md", "commit": "fixture", "nested": [1, {"value": None}]}
    client, _, transport = client_for(HttpResponse(200, document), HttpResponse(404))
    with client:
        assert client.get_document(INDEX, "one") == document
        assert client.get_document(INDEX, "missing") is None
    assert [request.method for request in transport.requests] == ["GET", "GET"]
    assert "one" in transport.requests[0].url
    assert "missing" in transport.requests[1].url


@pytest.mark.parametrize("body", [{"title": "no key"}, {"id": "other"}, ["not a document"]])
def test_malformed_keyed_document_is_unavailable(body):
    client, _, _ = client_for(HttpResponse(200, body))
    with client, pytest.raises(SearchError) as caught:
        client.get_document(INDEX, "one")
    assert caught.value.status == 503


def test_first_response_continuation_does_not_walk_or_sort():
    client, _, transport = client_for(HttpResponse(200, {
        "value": [{"id": "z"}, {"id": "a"}],
        "@odata.nextLink": f"https://{HOST}/indexes/{INDEX}/docs/search?api-version=2024-07-01",
        "@search.nextPageParameters": {"search": "*", "top": 2, "skip": 2},
    }))
    with client:
        assert client.search(INDEX, top=2) == [{"id": "z"}, {"id": "a"}]
    assert len(transport.requests) == 1
    assert "filter" not in transport.requests[0].body


def test_output_bound_is_unavailable_not_empty_or_relaxable():
    policy = replace(POLICY, limits=replace(POLICY.limits, max_output_bytes=40))
    client, _, _ = client_for(HttpResponse(200, {"value": [{"id": "one"}, {"id": "two", "text": "x" * 100}]}), policy=policy)
    with client, pytest.raises(SearchError) as caught:
        client.search(INDEX, top=2)
    assert caught.value.status == 503


@pytest.mark.parametrize(("response", "status"), [
    (HttpResponse(403, {"error": {"message": "private-provider-body"}}), 403),
    (HttpResponse(429), 429), (HttpResponse(500), 503),
    (TimeoutError("private-provider-body"), 0),
])
def test_safe_numeric_failure_mapping(response, status):
    client, _, transport = client_for(response)
    with client, pytest.raises(SearchError) as caught:
        client.search(INDEX)
    assert caught.value.status == status
    assert "private-provider-body" not in str(caught.value)
    assert caught.value.body is None
    assert len(transport.requests) == 1


def test_lifecycle_construction_description_and_close_need_no_runner_or_io(monkeypatch):
    def refuse_runner():
        raise AssertionError("construction created a Runner")

    monkeypatch.setattr("search_read_adapter.read.asyncio.Runner", refuse_runner)
    credential, transport = Credential(), ScriptedTransport()
    client = SearchReadClient(CONFIG, credential=credential, policy=POLICY, transport=transport)
    assert client.describe()["credential_configured"] is True
    absent = SearchReadClient(CONFIG, credential=None, policy=POLICY, transport=transport)
    assert absent.describe()["configured"] is True
    assert absent.describe()["credential_configured"] is False
    with pytest.raises(SearchError, match="credential_not_configured"):
        absent.search(INDEX)
    client.close()
    client.close()
    absent.close()
    assert credential.calls == credential.closed == transport.closed == 0
    assert transport.requests == []


@pytest.mark.parametrize("top", [0, 101, -1, True, 1.0, "1", None])
def test_lifecycle_exact_integer_limit_refuses_before_io(top):
    client, credential, transport = client_for()
    with client, pytest.raises(SearchError) as caught:
        client.search(INDEX, top=top)
    assert caught.value.status == 400
    assert credential.calls == 0 and transport.requests == []


def test_lifecycle_target_grant_key_and_async_credential_refuse_before_io():
    async def async_token(scope):
        raise AssertionError("asynchronous credential was called")

    for policy, credential, index, key in (
        (POLICY, Credential(), "other", None),
        (replace(POLICY, grants=frozenset()), Credential(), INDEX, None),
        (POLICY, Credential(), INDEX, "../outside"),
        (POLICY, SimpleNamespace(get_token=async_token), INDEX, None),
    ):
        transport = ScriptedTransport()
        client = SearchReadClient(CONFIG, credential=credential, policy=policy, transport=transport)
        with client, pytest.raises(SearchError):
            client.get_document(index, key) if key is not None else client.search(index)
        assert transport.requests == []
        assert getattr(credential, "calls", 0) == 0
    for change in ({"grants": {"query", "schema.read"}}, {"max_concurrency": 2},
                   {"limits": replace(POLICY.limits, max_attempts=2)}):
        with pytest.raises(SearchError):
            SearchReadClient(CONFIG, credential=Credential(), policy=replace(POLICY, **change))
    with pytest.raises((ConfigurationError, SearchError)):
        wrong_host = replace(CONFIG, endpoint="https://outside.search.windows.net")
        SearchReadClient(wrong_host, credential=Credential(), policy=POLICY)


def test_lifecycle_active_loop_refuses_every_sync_method_before_coroutine_creation():
    client, credential, transport = client_for()

    async def check():
        for operation in (lambda: client.search(INDEX), lambda: client.search_count(INDEX),
                          lambda: client.get_document(INDEX, "one"), client.close):
            with pytest.raises(SearchError, match="active_event_loop"):
                operation()

    asyncio.run(check())
    client.close()
    assert credential.calls == 0 and transport.requests == []


def test_lifecycle_worker_calls_use_fresh_context_and_one_runner():
    marker = ContextVar("search_read_test_marker", default="missing")
    observed, loops = [], []

    class ContextTransport(ScriptedTransport):
        async def request(self, request):
            observed.append(marker.get())
            loops.append(asyncio.get_running_loop())
            marker.set("changed-inside-operation")
            return HttpResponse(200, {"value": []})

    client = SearchReadClient(CONFIG, credential=Credential(), policy=POLICY, transport=ContextTransport())

    def call(label):
        marker.set(label)
        assert client.search(INDEX) == []
        assert marker.get() == label

    with ThreadPoolExecutor(max_workers=1) as workers:
        for label in ("first", "second", "third"):
            workers.submit(call, label).result(timeout=3)
        workers.submit(client.close).result(timeout=3)
    assert observed == ["first", "second", "third"]
    assert len({id(loop) for loop in loops}) == 1


def test_lifecycle_close_marks_closing_before_wait_and_refuses_queued_reads(monkeypatch):
    entered, release, close_waiting = threading.Event(), threading.Event(), threading.Event()
    closed = []
    original_close = DataConnector.aclose

    async def counted_close(connector):
        closed.append(connector)
        await original_close(connector)

    monkeypatch.setattr(DataConnector, "aclose", counted_close)

    class BlockingTransport(ScriptedTransport):
        async def request(self, request):
            self.requests.append(request)
            entered.set()
            if not await asyncio.to_thread(release.wait, 3):
                raise TimeoutError()
            return HttpResponse(200, {"value": []})

    class ObservedLock:
        def __init__(self):
            self.lock = threading.Lock()

        def __enter__(self):
            if threading.current_thread().name == "close-reader":
                close_waiting.set()
            self.lock.acquire()

        def __exit__(self, *args):
            self.lock.release()

    transport, credential = BlockingTransport(), Credential()
    client = SearchReadClient(CONFIG, credential=credential, policy=POLICY, transport=transport)
    client._lock = ObservedLock()
    with ThreadPoolExecutor(max_workers=3) as workers:
        first = workers.submit(client.search, INDEX)
        assert entered.wait(3)
        queued = workers.submit(client.search, INDEX)
        closer = threading.Thread(target=client.close, name="close-reader")
        closer.start()
        try:
            assert close_waiting.wait(3)
            assert client.describe()["state"] == "closing"
            with pytest.raises(SearchError, match="client_clos"):
                client.search(INDEX)
        finally:
            release.set()
            closer.join(3)
        assert first.result(timeout=3) == []
        with pytest.raises(SearchError, match="client_clos"):
            queued.result(timeout=3)
    client.close()
    assert not closer.is_alive()
    assert len(closed) == len(transport.requests) == 1
    assert credential.closed == transport.closed == 0


def test_lifecycle_partial_startup_failure_closes_runner_not_borrowed_resources(monkeypatch):
    real_runner = asyncio.Runner
    runners = []

    class RecordingRunner(real_runner):
        close_calls = 0

        def close(self):
            self.close_calls += 1
            super().close()

    def create_runner():
        runner = RecordingRunner()
        runners.append(runner)
        return runner

    def refuse_connection(*args, **kwargs):
        raise ConfigurationError("synthetic startup failure")

    monkeypatch.setattr("search_read_adapter.read.asyncio.Runner", create_runner)
    monkeypatch.setattr("search_read_adapter.read.connect", refuse_connection)
    client, credential, transport = client_for()
    with pytest.raises(SearchError):
        client.search(INDEX)
    assert runners[0].close_calls == 1
    client.close()
    assert runners[0].close_calls == 1
    assert credential.closed == transport.closed == credential.calls == 0


def test_selected_read_never_constructs_retained_transport(monkeypatch):
    from template_foundations.azure_search import SearchIndexClient, Transport

    def refuse(*args, **kwargs):
        raise AssertionError("retained read transport selected")

    monkeypatch.setattr(SearchIndexClient, "__init__", refuse)
    monkeypatch.setattr(Transport, "__init__", refuse)
    client, _, _ = client_for(HttpResponse(200, {"value": []}))
    with client:
        assert client.search(INDEX) == []


def test_both_consumer_sources_select_the_same_public_owner():
    applications = Path(__file__).resolve().parents[2]
    paths = [applications / "investigation_app/app/cybereye/backend/knowledge/search.py",
             applications / "custom_optimizer/app/cybereye/backend/knowledge.py"]
    for path in paths:
        source = path.read_text(encoding="utf-8")
        imported = {alias.name for node in ast.walk(ast.parse(source))
                    if isinstance(node, ast.ImportFrom) and node.module == "search_read_adapter"
                    for alias in node.names}
        assert "SearchReadClient" in imported
        assert "SearchIndexClient" not in imported
        assert "Transport" not in imported


def test_accounting_covers_query_count_keyed_failure_and_no_io_description():
    client, credential, transport = client_for(HttpResponse(200, {"value": []}),
        HttpResponse(200, {"value": [], "@odata.count": 0}), HttpResponse(404), HttpResponse(403))
    assert client.describe()["metrics"]["submitted"] == 0
    with client:
        with pytest.raises(SearchError):
            client.search("other")
        assert client.search(INDEX) == []
        assert client.search_count(INDEX) == 0
        assert client.get_document(INDEX, "missing") is None
        with pytest.raises(SearchError):
            client.search(INDEX)
        metrics = client.describe()["metrics"]
    assert metrics == {"submitted": 4, "completed": 4, "known_attempts": 4,
                       "unknown_attempt_operations": 0, "operations": {"query": 3, "read": 1}}
    assert len(transport.requests) == 4
    assert credential.closed == 0


def test_accounting_unreported_operation_is_unknown_never_zero(monkeypatch):
    async def unexpected(*args, **kwargs):
        raise RuntimeError("unreported operation")

    monkeypatch.setattr(DataConnector, "query", unexpected)
    client, _, _ = client_for()
    with client, pytest.raises(SearchError):
        client.search(INDEX)
    metrics = client.describe()["metrics"]
    assert metrics["submitted"] == metrics["completed"] == metrics["unknown_attempt_operations"] == 1
    assert metrics["known_attempts"] == 0