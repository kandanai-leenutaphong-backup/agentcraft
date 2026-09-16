# Template Foundations

## Current Scope

Live template behavior is limited to `template_foundations.local_server` process supervision
and a three-symbol `template_foundations.azure_llm` forward for the parent-owned agent service.
Rule execution, model implementation, Search reads and source viewing are library-owned.

| Capability | Canonical Public Owner |
| --- | --- |
| Rule battery | `libraries/situation-detector`, `situation_detector` |
| Legacy raw Responses compatibility | `libraries/azure-llm-compat`, `azure_llm_compat`; isolated uv project, OpenAI 2.x |
| Fixed-index sync Search reads | `libraries/search-read-adapter`, `search_read_adapter`; all transport remains `azdata` |
| Read-only source viewer | `libraries/source-code`, `@agentcraft/source-code`; frontend only |

Remaining cull blocker: `azure_search/{client,transport,config,schema}.py` is fixture-only
compatibility, not a selected application data path. The Investigation test helper imports
`app.data.data_pipelines.search`, whose initializer eagerly imports `load` and raw publishing
symbols. Removing that initializer/fixture dependency requires implementation changes outside
this assignment's mechanical-import authority. Parent owns that final retirement. No connector
writes were copied into a new library or exercised in this migration.

Parent model change: replace `template_foundations.azure_llm` in `backend/agents/service.py`
with its chosen canonical model integration; the compatibility-equivalent import is
`from azure_llm_compat import azure_credential, bearer_token_provider, response_events`.
Then remove the five-line bridge. This is not `llm_interface` parity evidence.

Current checks and exact move receipts: [library migration record](../investigation_app/docs/LIBRARY_MIGRATION.md).

## Historical Shared Contract

The following pre-extraction description and candidate receipts are historical, not current
runtime placement or a claim that old artifact hashes cover the new source.

One retained source owner for `azure_llm` and `azure_search`
capabilities used by Investigation and Custom Optimizer. Moved from the
investigation template during optimizer separation; these are not new library implementations.

The rule battery now belongs to [situation-detector](../../libraries/situation-detector/README.md).
Both applications declare that package directly and import `situation_detector`.
The source viewer now belongs to [source-code](../../libraries/source-code/README.md),
consumed through `@agentcraft/source-code` by both frontends.

Python consumers install `agentcraft-template-foundations` through an explicit local uv
dependency and import the public `template_foundations.<capability>` package.
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