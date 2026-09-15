# Template Foundations

One source owner for `situation_detector`, `azure_llm`, `azure_search` and
`source_code` capabilities used by Investigation and Custom Optimizer. Moved from the
investigation template during optimizer separation; these are not new library implementations.

Python consumers install `agentcraft-template-foundations` through an explicit local uv
dependency and import the public `template_foundations.<capability>` package.
Frontend consumers resolve `@foundations/source_code/frontend` to its public barrel.
No foundation imports either application or reads its configuration.

Optimizer-only workflow, sandbox reader and terminal code live in Custom Optimizer.
Other investigation-only components remain with Investigation. This package is a local
ownership boundary, not a published distribution or an additional universal utility layer.

`local_server.serve` also owns the identical loopback process/port/shutdown mechanics; each
app still owns which settings it accepts, which module it launches and where state belongs.
Inherited component documentation is source history. Current consumers resolve installed
`template_foundations` imports and the declared frontend alias, never the retired app paths.

## Search Read Owner

`template_foundations.azure_search.SearchReadClient` is the fixed-index synchronous read
facade used by both applications. It delegates query/count/keyed reads to public `azdata`
and the native Search SDK. Catalogue probes await public `azdata` directly on the app loop.
Domain filters, projections, citation keys and caller authorization remain application-owned.
`SearchIndexClient`, `Transport`, `FieldSpec`, `IndexSpec`, `render_index` and `safe_key`
remain importable for fixture construction and write/schema helpers; migrated reads never
select their retained transport. No physical retirement or package publication is claimed.

| Call | Result / Limit |
| --- | --- |
| `SearchReadClient(config, credential=credential, policy=policy)` | Fixed `ConnectorConfig`; explicit borrowed synchronous credential, or `None` for local description only |
| `search(index, text="*", top=10, filter="", select=None)` | Mutable ordered documents from one response; exact integer top 1..policy ceiling, no page walk |
| `search_count(index, text="*", filter="")` | Exact nonnegative count; one key-only query row discarded; missing/null/invalid count refuses |
| `get_document(index, key)` | Exact document or `None` for absence; malformed or failed item is unavailable |
| `describe()` | No service/token/Runner/thread I/O; configured state, selected transport and known/unknown attempt counters |
| `close()` / sync context manager | Drain current read, refuse queued/new work, close owned connector/Runner once; never close borrowed credential/transport |

Policy grants must be within `query/read`, concurrency 1, one attempt, timeout <=30 seconds,
max_items <=100 and max_output_bytes <=1 MiB. Configuration must be an HTTPS origin with
exact allowed host/index. Requests cannot widen it. An asynchronous host calls synchronous
methods, including `close`, via `await asyncio.to_thread(...)`; active-loop calls refuse
before coroutine creation. Use direct async `azdata` for native async callers.

`SearchError.status` compatibility: denial 403; invalid/unsupported 400; rate limit 429;
transport/deadline 0; incomplete/unknown/other failure 503. `body` is never provider payload.
Recover by correcting the caller input or obtaining separately authorized access, then use
the same target. No automatic retry, local corpus, ambient credential discovery or target fallback.
Nested values thaw to dict/list; ordinary null and absent stay distinct. Only knowledge
reranker annotation is aliased to `@search.rerankerScore`; hit order/ties are not sorted.

## Installed Candidate

The child candidate receipt is written to
`../../deploy/records/m2-search-catalogue-candidate-v1.json` after wheel/sdist verification.
Use its exact wheel hashes, absolute Python paths and source-stage paths, not an editable
checkout or the accepted M1 environment. Builds use `uv build --no-sources`; ordinary
version requirements in wheel metadata never contain local source paths.

```bash
uv pip install --no-sources --python /absolute/new/environment/bin/python \
  /absolute/candidate/agentcraft_template_foundations-0.1.0-py3-none-any.whl \
  /absolute/candidate/azdata-4.0.0a3-py3-none-any.whl
```

The following complete example is **offline only**. It injects synthetic transport beneath
the real SDK; it acquires no real token and cannot produce live acceptance. Run outside
the checkout using the installed candidate interpreter.

```python
from types import SimpleNamespace
from azdata import ConnectorConfig, HttpResponse, Limits, Policy, ResourceAddress
from template_foundations.azure_search import SearchError, SearchReadClient

class OfflineCredential:
	def get_token(self, scope):
		return SimpleNamespace(token="offline-fixture", expires_on=2**31)

class OfflineTransport:
	def __init__(self):
		self.responses = [
			HttpResponse(200, {"value": [{"id": "one", "title": "Fixture"}]}),
			HttpResponse(200, {"value": [{"id": "one"}], "@odata.count": 1}),
			HttpResponse(200, {"id": "one", "title": "Fixture"}),
		]

	async def request(self, request):
		return self.responses.pop(0)

config = ConnectorConfig("https://fixture.search.windows.net",
						 ResourceAddress({"index": "fixture"}), ("fixture.search.windows.net",))
policy = Policy("offline-reader", grants={"query", "read"}, max_concurrency=1,
				limits=Limits(timeout_seconds=30, max_items=100, max_output_bytes=1_048_576, max_attempts=1))
with SearchReadClient(config, credential=OfflineCredential(), policy=policy,
					  transport=OfflineTransport()) as client:
	try:
		client.search("wrong-index")
	except SearchError as refusal:
		assert refusal.status == 403
	assert client.search("fixture", top=1)[0]["id"] == "one"
	assert client.search_count("fixture") == 1
	assert client.get_document("fixture", "one")["title"] == "Fixture"
	assert client.describe()["metrics"]["known_attempts"] == 3
print("PASS_OFFLINE: public query/count/read, local refusal, same-target recovery and closure")
```

## Live Read Acceptance

Follow the [existing deployment guide](../../deploy/README.md#child-search-and-catalogue-reads).
Live calls require an approved existing target, current principal/interval, exact installed
candidate, independently frozen baseline and the single private continuation ledger. Native,
library, both consumers, independent developer and browser attempts share that ledger.
Initial reservation is 27/100 (26 known plus one unknown), leaving at most 73 additional.
Unknowns retain slots and unknown cost. A required cohort exceeding the remainder blocks.

Independent developer receives this guide, the root deployment guide, exact candidate receipt,
and approved frozen plans. Setup, query/read/count, local refusal, same-target recovery and
closure require separate observations. Author rehearsal is not independent acceptance.
Missing provider-denial identity or authentic citation state stays blocked; never create
grants, infer a diagnosis, fetch a secret, write Azure data or disable authentication.