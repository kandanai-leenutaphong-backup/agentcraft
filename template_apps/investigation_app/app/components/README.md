# Template Status

This is retained source-project documentation. The template's
[migration catalogue](../../docs/ARCHITECTURE_OVERVIEW.md) owns current component status;
styling studies and source deployment paths described below were not copied. ADX runtime
queries now use canonical `azdata`; the legacy component remains for catalogue reads and
baseline comparison pending live parity. No component here imports the source checkout.

# `app/components/` — reusable capabilities

Capabilities more than one pipeline or application needs, implemented once. A component is
importable on its own, holds no pipeline knowledge, and reads no configuration at import
time.

| Component | Import path | Provides |
| --- | --- | --- |
| Azure LLM connector | `app.components.azure_llm` | Azure OpenAI responses, streaming, and embeddings over one Entra ID identity |
| Azure AI Search CRUD | `app.components.azure_search` | Create, update, delete and query indexes and documents |
| Azure Resource Manager | `app.components.azure_arm` | Signed control-plane REST: read a resource, create one, wait for it to provision |
| Data connector library | `app.components.data_connector_library` | The datastore capability: bounded read-only content reads with a six-status failure model, plus full ADX, Gremlin and Azure AI Search CRUD |
| Resource Explorer | `app.components.resource_explorer`, `@components/resource_explorer/frontend` | Read-only inventory plus a three-column data/agent/tool viewer, with exact-ID dependency highlighting and an injected agent loader |
| Signed developer access | `app.components.signed_dev_access` | Ed25519 signed-request authentication for an ASGI application: pure verifier, pure-ASGI middleware, and a durable atomic replay ledger |
| Entra ID authentication | `app.components.entra_auth` | Microsoft Entra access-token validation and browser sign-in: token validator, bounded JWKS cache, Authorization Code + PKCE, and a shared expiring record store |
| Source code viewer | `@components/source_code/frontend` | Read-only Shiki syntax highlighting, filename-based language detection, original line numbers, copy and word wrap |
| Event stream decoder | `@components/event_stream/frontend` | Framework-free SSE framing and JSON event decoding with streaming UTF-8 and reader cleanup |
| Local query reader | `app.components.local_query` | Bounded read-only SQLite queries with table authorization, deadlines and result limits |
| Copilot terminal | `app.components.copilot_terminal`, `@components/copilot_terminal/frontend` | Native CLI over PTY, private sessions, bounded callbacks and React/xterm client |
| Azure Sky style study | `azure_sky_styling/frontend/index.ts`, `azure_sky_styling/frontend/azure-sky.css`, `azure_sky_styling/frontend/depth-effects.css` | Isolated React/HTML mockup, modular blue/light material recipes and seeded Painterly/Geometric architecture; credited local art masks, hide/regenerate controls, no cloud animation; [run and reuse](azure_sky_styling/README.md) |
| Azure Nightsky style study | `azure_nightsky_styling/frontend/index.ts`, `azure_nightsky_styling/frontend/azure-nightsky.css` | Independent violet/navy material gallery, seeded static star field and local recipe studies; no dependency on Azure Sky or CyberEye; [run and reuse](azure_nightsky_styling/README.md) |

The connector library, inventory, signed access and Entra components were **adopted from another repository**. Each owns its own
`README.md` (the contract: public surface, bounds, statuses, seams) and `PROVENANCE.md`
(the origin, the revision, the full hash of every upstream file, the licence, and what was
changed). None creates any build, import or test dependency on that repository.
`data_connector_library` is the one that is now part adopted and part local: its read plane
came from upstream, its ADX and Gremlin CRUD plane was written here, and its `PROVENANCE.md`
keeps the two apart file by file.

- [`data_connector_library/README.md`](data_connector_library/README.md)
- [`resource_explorer/README.md`](resource_explorer/README.md)
- [`signed_dev_access/README.md`](signed_dev_access/README.md)
- [`entra_auth/README.md`](entra_auth/README.md)

All four upstream boxes are **MIT**, declared in their `SKILL.md` frontmatter. The notice
travels with the code, in each `PROVENANCE.md`.

The separately adopted [Copilot terminal](copilot_terminal/README.md) has its own
[hash-pinned provenance](copilot_terminal/PROVENANCE.md); its license is unverified, not covered
by the four MIT declarations above. [Local query](local_query/README.md) was implemented here.

`resource_explorer` and `source_code` have React frontends; `event_stream` is framework-free
TypeScript. All are imported through the `@components/`
alias declared in `architecture.json`, `app/cybereye/frontend/tsconfig.app.json` and
`app/cybereye/frontend/vite.config.ts`. `app/components/*/frontend/index.ts` is a declared
public surface, so a reach past that barrel fails `arch.py`.

### Source code viewer

```tsx
import { SourceCodeViewer } from "@components/source_code/frontend";

<SourceCodeViewer code={sourceText} filename="tools/investigate.py" startLine={41} />
```

`code` is required. Optional props: `filename`, explicit `language` (Shiki id or alias),
`startLine` (default 1), `maxHeight` (default 480), `truncated` (default false), and
`defaultWrap` (default false; the optimization Tools column enables it).
The host supplies React, `lucide-react` and Shiki (CyberEye pins 4.4.3). Styles load with the
barrel and stay scoped to `scv-`. Grammars load on demand; unsupported filenames or failed
highlighting render plain text. The VS Code Dark+ theme uses Shiki's JavaScript regex engine,
without a WASM worker or external CDN. The viewer takes text, never reads a file or executes
source, and imports no application code. Copy preserves the original text and line endings.

## Rules

- **No credential is read from repository configuration.** Authentication is Microsoft Entra
  ID through `DefaultAzureCredential` / `AzureCliCredential`. No API key, admin key, query
  key, or connection string appears in code, `.env`, or a default.
- **Configuration resolves at call time.** `from_env()` is a classmethod that reads the
  environment when it is called. A module-level frozen `Settings` object cannot be switched
  by a caller and cannot be tested without reloading the module — the failure this repository
  already recorded in `app/cybereye/backend/config.py`.
- **Clients build lazily.** Importing a component costs nothing and needs no Azure identity;
  the SDK client is constructed on first use.
- **Components do not import pipelines, connectors, or the analyst application.** Dependency
  runs one way: components are imported by pipelines and by `app/cybereye/`, never the
  reverse. `azure_search` may use `azure_llm` for embeddings; nothing in `azure_llm` knows
  about search. `azure_arm` uses `azure_llm` for the credential and knows no resource type.
  `resource_explorer` uses `data_connector_library` for the content plane and the six
  statuses, and knows no use case, table, graph or index — those arrive as a registry.
  `data_connector_library` re-exports `azure_search`'s client rather than carrying a second
  copy of it, so there is one Azure AI Search write path in the repository.
  `signed_dev_access` knows no identity type — the consumer injects a factory and the
  verified principal is attached to the ASGI scope. `entra_auth` returns verified claims and
  never a principal, for the same reason and by the same rule: one identity model in the
  application, owned by the application.
- **A component holds no domain literal.** `resource_explorer` never names Perth, AIT, a
  cluster or an index; `app/cybereye/control/data_inventory.yaml` does, and the application
  resolves it and hands the result in.

The first rule is enforced: `components` is declared in `architecture.json` with
`may_depend_on: []` and a public surface of `app/components/*/__init__.py`, so
`python3 .github/tools/arch.py` fails on an import that reaches out of the boundary or into a
component's internals.

## Tests

Offline, no Azure account, no network:

```bash
/usr/bin/python3 -m unittest discover -s app/components/tests -t .
```

---

## `azure_llm` — Azure model endpoint

```python
from app.components.azure_llm import AzureLlmClient, LlmConfig

client = AzureLlmClient.from_env()                                  # AZURE_LLM_* environment
client = AzureLlmClient(LlmConfig(endpoint="https://<account>.cognitiveservices.azure.com/openai/v1/",
                                  model="gpt-5.6-luna"))            # explicit
client = AzureLlmClient.from_env(prefix="CYBEREYE_OPENAI_", model="gpt-5.6-luna")
```

| Call | Returns |
| --- | --- |
| `respond(*, input, instructions=None, model=None, max_output_tokens=None, reasoning_effort=None, tools=None, **kwargs)` | the SDK response object |
| `respond_text(**same)` | `str`, stripped |
| `stream(**same)` | an iterator of streaming events; close it when done |
| `response_events(create, /, **request)` | async events from an injected synchronous Responses `create` callable; closes the stream and retries one transport failure only before visible output |
| `embed(texts, *, deployment=None, dimensions=None)` | `list[list[float]]`, in the order sent |
| `describe()` | non-secret dict; makes no request |
| `config` / `client` / `embeddings_client` | the resolved config and the lazily built SDK clients |

Also exported: `azure_credential()`, `bearer_token_provider(scope, credential=None)`,
`set_credential_factory(factory)` (the injection seam for tests and hosts), `LlmConfigError`,
`COGNITIVE_SCOPE`, and `DEFAULT_ENV_PREFIX` (`AZURE_LLM_`).

### Configuration keys

| Key | Required | Default |
| --- | --- | --- |
| `AZURE_LLM_ENDPOINT` | yes | — |
| `AZURE_LLM_MODEL` | for `respond` without an explicit `model` | — |
| `AZURE_LLM_EMBEDDING_DEPLOYMENT` | for `embed` without an explicit `deployment` | — |
| `AZURE_LLM_EMBEDDING_ENDPOINT` | no | falls back to `AZURE_LLM_ENDPOINT` |
| `AZURE_LLM_SCOPE` | no | `https://cognitiveservices.azure.com/.default` |
| `AZURE_LLM_TIMEOUT_SECONDS` | no | `120.0` |
| `AZURE_LLM_MAX_RETRIES` | no | `2` |

The prefix is an argument: `LlmConfig.from_env("OTHER_")` reads `OTHER_ENDPOINT`. Explicit
keyword overrides beat both.

### Auth

`AzureCliCredential` when `~/.azure` exists, otherwise
`DefaultAzureCredential(exclude_interactive_browser_credential=True)`. The token provider is
a callable invoked per request, so a long-lived client survives token expiry. Role required
on the model account: **Cognitive Services OpenAI User**.

---

## `azure_search` — Azure AI Search

REST over the standard library against a pinned API version (`2024-07-01`). No search SDK
dependency. Patterned on `reference_skills/harness/data/azure-ai-search-management`; read its
`CONTRACT.md` for request shapes and `GOTCHAS.md` for the failure modes handled here.

```python
from app.components.azure_search import (
    SearchIndexClient, SearchConfig, IndexSpec, FieldSpec, VectorSpec, safe_key,
)

client = SearchIndexClient.from_env()                    # SEARCH_* environment
spec = IndexSpec(
    name="perth-kb",                                     # lowercase, digits, single dashes
    purpose="Retrieval for situation characterisation.", # required, non-empty
    fields=(
        FieldSpec("id", key=True, filterable=True),
        FieldSpec("title", searchable=True, filterable=True),
        FieldSpec("content", searchable=True),
        FieldSpec("source", filterable=True, facetable=True),
    ),
    vector=VectorSpec("content_vector", 1536, "content"),  # optional
    semantic_title_field="title",
    semantic_content_fields=("content",),
)
client.create_or_update_index(spec)
client.upload_documents("perth-kb", [{"id": safe_key("docs/a.md"), "title": "A", "content": "..."}])
hits = client.search("perth-kb", "explicit credential logon", top=5)
```

| Operation | Call |
| --- | --- |
| List indexes | `list_indexes() -> list[str]` |
| Read index | `get_index(name) -> dict \| None`, `index_exists(name) -> bool` |
| Create/update index | `create_or_update_index(spec: IndexSpec) -> dict` |
| Delete index | `delete_index(name, *, missing_ok=True) -> bool` |
| Index stats | `index_stats(name) -> dict`, `document_count(name) -> int` |
| Create/update documents | `upload_documents(index, documents, *, action="mergeOrUpload", batch_size=50) -> dict` |
| Read document | `get_document(index, key) -> dict \| None` |
| Delete documents | `delete_documents(index, key_field, keys, *, batch_size=50) -> dict` |
| Query | `search(index, text="*", *, top=10, filter="", select=None, order_by=None, vector=None, vector_field="", vector_k=None, embedder=None, **kwargs) -> list[dict]` |
| Describe | `describe() -> dict`; makes no request |

Also exported: `Transport`, `SearchError`, `SearchConfig`, `SearchConfigError`,
`render_index(spec)`, `safe_key(value)`, `valid_index_name(name)`, `SEARCH_SCOPE`,
`DEFAULT_SEARCH_API_VERSION`, `DEFAULT_ENV_PREFIX`.

### Configuration keys

| Key | Required | Default |
| --- | --- | --- |
| `SEARCH_ENDPOINT` | yes | — |
| `SEARCH_API_VERSION` | no | `2024-07-01` |
| `SEARCH_SCOPE` | no | `https://search.azure.com/.default` |
| `SEARCH_TIMEOUT_SECONDS` | no | `60.0` |
| `SEARCH_MAX_ATTEMPTS` | no | `4` |

### Auth

Entra ID bearer token on the `https://search.azure.com/.default` audience. The service must
be created with `--auth-options aadOrApiKey` or it will not accept a token. **Both roles are
required** — the first manages indexes, the second reaches their contents:

```bash
az search service create -n <svc> -g <rg> --sku basic --auth-options aadOrApiKey
SCOPE=$(az search service show -n <svc> -g <rg> --query id -o tsv)
OID=$(az ad signed-in-user show --query id -o tsv)
for role in "Search Service Contributor" "Search Index Data Contributor"; do
  az role assignment create --assignee-object-id "$OID" \
      --assignee-principal-type User --role "$role" --scope "$SCOPE"
done
```

Index management succeeding while document upload returns 403 means the second role is
missing.

### Behaviours worth knowing

- **A 200 or a 207 can still mean documents failed.** Every per-document entry is inspected;
  `upload_documents` and `delete_documents` raise `SearchError` naming the first failed key
  rather than returning a success that lost data.
- **Creating an index answers 201 with a body; updating one answers 204 with none.**
  `create_or_update_index` reads the stored definition back on an empty body, so it always
  returns what the service actually holds.
- **`document_count` lags a write.** It reads the service's own statistics, which settle
  behind the index. Observed live: 0 reported three seconds after a delete that should have
  left one document. Do not gate a pipeline on it; read a document back instead.
- **Index names are validated before they reach a URL.** A capital, an underscore, or a path
  separator is refused locally instead of becoming a 400 or a traversal attempt.
- **Only `429, 502, 503, 504` retry**, at most `max_attempts` times, using the service's
  `retryAfterSeconds` when present and jittered exponential backoff otherwise. A client fault
  fails immediately.
- **The vector field is never retrievable.** Thousands of floats per document are useless to a
  caller and dominate the response.
- **A destructive index change drops every document.** Removing a field, changing its type or
  key, or changing vector `dimensions` is a rebuild. Compare with `get_index` before applying
  to an index that holds data — this component does not guess on the caller's behalf.
- **`safe_key` is deterministic**, so reloading the same source overwrites rather than
  duplicating.

### Injection seams

`Transport(credential=..., opener=..., sleep=...)` where
`opener(request, timeout) -> (status, body_bytes)`. That one seam makes every operation
testable with no Azure account; `app/components/tests/test_azure_search.py` implements a fake
service that keeps 207 partial success, 404s, and retryable statuses intact.

---

## `azure_arm` — Azure Resource Manager control plane

REST over the standard library. No management SDK dependency, because the one thing this
repository needs the control plane for must also run inside an Azure Function, which has no
`az` binary and no room for the ARM SDK.

**Why it exists.** Cosmos DB for Gremlin has no Entra data plane, so an account key must be
read from ARM at run time, and a Gremlin graph must be created through ARM. Three callers
had grown their own copy of that plumbing: `app/cybereye/backend/data/graph.py`, and the
byte-identical `arm.py` in each of the two pipelines. This is the single copy.

**What it does not know.** Resource semantics. There is no `cosmos_*` function here; what a
`databaseAccounts` path means belongs to the connector that owns that datastore. This
component signs, sends, retries, decodes, and waits.

```python
from app.components.azure_arm import ArmClient, ArmError, resource_path

client = ArmClient.from_env()                        # ARM_* environment, read when called
path = resource_path(subscription, resource_group,   # every part percent-encoded
                     "Microsoft.DocumentDB", "databaseAccounts", account)
status, payload = client.post(f"{path}/readonlykeys?api-version=2024-11-15")
```

| Call | Returns |
| --- | --- |
| `request(method, path, *, body=None, timeout=None, max_attempts=None, absent_ok=False)` | `(status, decoded)`; an empty body decodes to `{}` |
| `get(path, **kwargs)` / `post(...)` / `put(...)` | the same, with the method fixed |
| `await_provisioned(path, *, wait_seconds=300, interval_seconds=5)` | `None`; raises `ArmError` at the deadline |
| `token()` | a bearer token for the configured scope, cached until near expiry |
| `describe()` | non-secret dict; makes no request |

Also exported: `resource_path(subscription, resource_group, provider, *segments)`,
`ArmConfig`, `ArmConfigError`, `ArmError`, `RETRYABLE_STATUS`, `DEFAULT_ARM_ENDPOINT`,
`DEFAULT_ARM_SCOPE`, `DEFAULT_ENV_PREFIX`.

### Configuration keys

| Key | Required | Default |
| --- | --- | --- |
| `ARM_ENDPOINT` | no | `https://management.azure.com` |
| `ARM_SCOPE` | no | `https://management.azure.com/.default` |
| `ARM_TIMEOUT_SECONDS` | no | `120` |
| `ARM_MAX_ATTEMPTS` | no | `4` |

The prefix is an argument, and explicit keyword overrides beat both. Sovereign clouds are the
reason the endpoint and scope are configurable at all; a non-`https` endpoint is refused.

### Auth

`azure_credential()` from `azure_llm` — `AzureCliCredential` when `~/.azure` exists, otherwise
`DefaultAzureCredential`. The token is fetched on first use and reused until five minutes
before expiry. The role required depends entirely on the operation; grant the narrowest one.
For the Cosmos key read this repository performs, `Cosmos DB Account Reader Role` carries
`readonlykeys` and cannot write, while `listKeys` needs `DocumentDB Account Contributor`.

### Behaviours worth knowing

- **A caller-supplied name is percent-encoded with `safe=""`.** `resource_path` is the reason
  a configured account name containing a slash or a dot-segment cannot re-point the request at
  another resource. Building an ARM path with an f-string skips that control.
- **A bodyless POST is still sent an empty payload.** ARM answers `listKeys` and
  `readonlykeys` only when the request carries a body at all; sending `None` produces a GET-
  shaped request that fails.
- **201 does not mean usable.** ARM accepts a child-resource PUT and provisions it afterwards,
  which is what `await_provisioned` exists for.
- **Only `429, 500, 502, 503, 504` retry**, at most `max_attempts` times, with jittered
  exponential backoff. A client fault fails on the first attempt rather than four times.
- **ARM's own error message survives into `ArmError`**, truncated to 300 characters. Callers
  that surface an error to a user should not pass it on verbatim: it can name a subscription.

### Injection seams

`ArmClient(credential=..., opener=..., sleep=..., monotonic=...)` where
`opener(request, timeout) -> (status, body_bytes)`. That one seam makes every operation
testable with no Azure account; `app/components/tests/test_azure_arm.py` scripts a fake ARM
that keeps 404s, throttling, and provisioning delays intact.

---

## `data_connector_library` — bounded reads, and the ADX/Gremlin/Search CRUD surfaces

The read plane is adopted from `azdata` 3.4.0. **A subset**: the content plane, the discover plane's status
vocabulary and failure classifier, the shared envelope, and the lazy SDK loader. The write,
deploy, observe, verify and estate planes were not taken. The CRUD plane is this repository's
own: the ADX and Gremlin connectors, moved here from `app/data/data_connectors/` when that
package was retired, plus Azure AI Search re-exported from `azure_search` rather than copied.

Contract, bounds and truncation semantics:
[`data_connector_library/README.md`](data_connector_library/README.md). Origin and hashes:
[`data_connector_library/PROVENANCE.md`](data_connector_library/PROVENANCE.md).

```python
from app.components.data_connector_library import (
    ContentBounds, KustoReader, KustoTableInspector, SearchReader,
    GraphReader, GraphTarget, normalize_sample, classify_discovery_failure,
)

reader = KustoReader(credential_provider=azure_credential)
result = await reader.rows(query_uri=..., database=..., table=...,
                           bounds=ContentBounds(max_rows=25))
result.status   # ok | empty | forbidden | unreachable | unconfigured | unavailable
```

The three things most often got wrong by a caller:

- **Failure is a status, never an exception**, and the six are not interchangeable.
  Rendering any of them as "no rows" throws the diagnosis away.
- **`KustoReader.rows` cannot report its own truncation.** It issues `take n`. Compare the
  sample against a count; `SearchReader` and `GraphReader` ask for `n + 1` and report it.
- **`sanitize_detail` is for exception text, not for data.** Running it over rows rewrites
  the evidence and returns it as original. A bounded sample says what a bound cut, in
  `RowSample.notes`.

---

## `resource_explorer` — the use-case data inventory

Adopted from the `resource_explorer` component. **Re-rooted**: upstream browses an Azure
subscription and discovers downward; this serves a declared registry of use cases and can
address nothing else.

Contract, routes, selection semantics and seams:
[`resource_explorer/README.md`](resource_explorer/README.md). Origin and hashes:
[`resource_explorer/PROVENANCE.md`](resource_explorer/PROVENANCE.md).

```python
from app.components.resource_explorer import (
    InventoryRegistry, UseCase, InventorySource, SourceBinding,
    InventoryService, build_inventory_router, parse_selection,
)

registry = InventoryRegistry([UseCase(...)])          # the allowlist
service  = InventoryService(registry, {"adx": probe}) # one probe per connector
app.include_router(build_inventory_router(lambda request: request.app.state.inventory))
```

The registry is the security control: a node id decodes to `(use_case_id, source_id)` and
nothing else, so a forged token has nowhere to put a cluster. The selection is a scope
filter and is **not** an access control. A component holds no domain literal —
`app/cybereye/control/data_inventory.yaml` names Perth, AIT and their coordinates, and the
application validates and hands the result in.

---

## `signed_dev_access` — Ed25519 signed-request authentication

Adopted from the `signed-dev-access` box. **Hardened**: the replay ledger is keyed on the
decoded signature rather than its base64 text, retention runs to the instant the signature
stops verifying rather than a fixed TTL, and a shared ledger is a required argument rather
than a per-process default.

Contract, wire format, bounds and known limits:
[`signed_dev_access/README.md`](signed_dev_access/README.md). Origin, hashes and every
change with its reason: [`signed_dev_access/PROVENANCE.md`](signed_dev_access/PROVENANCE.md).

```python
from app.components.signed_dev_access import (
    AzureTableReplayLedger, InProcessReplayLedger, install_signed_request_auth, verify,
)

install_signed_request_auth(
    app,
    public_key_b64=os.environ.get("DEV_PUBLIC_KEY_ED25519", ""),   # empty mounts nothing
    identity_factory=lambda slug: my_principal(slug),              # the domain seam
    replay_ledger=AzureTableReplayLedger(endpoint=..., table_name="devauthreplay"),
)
```

The private key never leaves the operator's machine and the public half is not a secret:
it verifies and cannot sign, so it travels as a plain environment variable and revocation is
clearing it. The component holds no identity type; `app/cybereye/backend/security/` owns the
`Principal` this application uses and injects the factory that produces it.

---

## `entra_auth` — Microsoft Entra ID authentication

Adopted from the `entra-api-auth` box. **Hardened in four ways, each because the upstream
behaviour was wrong rather than merely different**: the disabled mode and its
`X-User-Id` development identity are gone entirely, so no configuration mistake can reach a
self-asserted caller; `common` and `organizations` are refused at construction; a key set
whose refresh keeps failing is served for a bounded window and then fails closed rather than
honouring possibly-revoked keys for the life of the process; and a service principal is
refused unless the configuration opted in *and* the token carries an accepted application role,
because requiring the `oid` claim does **not** filter service principals the way upstream's
documentation states.

Contract, check order, and known limits: [`entra_auth/README.md`](entra_auth/README.md).
Origin, licence, hashes and every change with its reason and its evidence:
[`entra_auth/PROVENANCE.md`](entra_auth/PROVENANCE.md).

```python
from app.components.entra_auth import EntraAuthConfig, TokenValidator

validator = TokenValidator(EntraAuthConfig(tenant_id=TENANT, client_id=CLIENT))
verified = await validator.validate_token(token)     # raises AuthError on any refusal
principal = my_principal_from(verified)              # the domain seam
```

The component also owns the browser half — `new_flow`, `authorize_url`, `logout_url`, opaque
session identifiers and their digests, and a shared expiring `RecordStore` over one Azure Table
reached with a managed identity. It performs no HTTP of its own beyond fetching signing keys,
imports no web framework, and stores no token: a session record holds the SHA-256 of its
identifier and the identity fields already proved.

