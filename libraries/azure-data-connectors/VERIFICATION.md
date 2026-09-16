# Verification

Version: `azdata` 4.0.0a4. Date: 2026-09-16.

## Current B02/B03 Work

Synchronous ADX/graph runtimes and model/Search compatibility distributions are retired.
Current contract and focused source evidence: [migration record](MIGRATION_B02_B03.md).
The earlier integration figures and hashes below are historical and do not validate this
source. Full current artifact/live acceptance remains separately recorded or blocked.

## Historical Template Integration

The prior source and wheels included public `azdata.adx_read` and `azdata.graph_read`.
The template's duplicate connectors, custom ARM transport and synchronous ADX plumbing are
retired; catalogue probes use `resource_explorer.probes` over canonical `azdata`.

- Full data-library suite: 190 passed, including read traversal acceptance/refusals,
  native read-only-key SDK wiring, borrowed-identity cleanup and default/no-grant refusal.
- Combined app/compatibility/consumer suite: 603 passed, 10 existing ontology-product skips.
- Installed wheels outside the checkout: 80 focused model/Search/ADX/graph tests pass,
  11 public import origins verified, no editable/local-path runtime dependency.
- Wheel-backed local Investigation: 23 API and 72 browser checks pass on existing Perth,
  Cosmos graph and MITRE. Exact native package identity matches runtime digest
  `c8867de1ebd8d1bfc2c96d57db995090f9fef11a3012976c6eb5e31c87feaaf5`.
- ADX lifecycle safety: 74 tests; event-store standalone: 82/82 checks. Read-back still
  reports Running/Succeeded/auto-stop false. Continuous billing is intentional.

[Current migration record](../../template_apps/investigation_app/docs/LIBRARY_MIGRATION.md)
owns command/measurement details. No inference, new data, grants, infrastructure provisioning
or publication was performed. The graph compatibility reader's read-only-key contract is not
proof of the uniform adapter's resource-token live path. Old receipts below remain historical;
their wheel hashes do not cover the newer read adapters.

## ADX Event-Store Consolidation

Current milestone: **offline and artifact verified**, with separately live-verified Perth
lifecycle. No current-artifact live data-plane or full operator provisioning/ingestion claim.

- Canonical API is `azdata.event_store`; the `event-store` extra declares its SDKs. No legacy
  `adx_connector` namespace or compatibility-wrapper tree is installed.
- All 26 original skill paths are accounted for in the [preservation manifest](docs/event-store/preservation.json):
  24 preserved destinations plus superseded standalone lock/ignore rules recoverable at the
  recorded Git baseline. Original gotchas and license remain; only the authorized skill was removed.
- Before migration: 82/82 original connector checks and 5/5 bootstrap tests passed. After
  migration and retirement: **175 library unittests plus 82/82 standalone checks pass**.
  The event-store slice includes 21 unittests: original bootstrap cases, default/narrow grant
  refusals, read-only request options, ingestion acceptance, existence uncertainty and retry behavior.
- The parent app's actual retry-attempt reporting was incorporated, with its five behavioral
  cases plus a no-replay mutation test. Parent files were read, not edited; its duplicate Kusto
  modules and app-specific content/metadata/read helpers remain parent-owned.
- Source-built wheel and sdist-rebuilt wheel are byte-identical. Every one of the **32 runtime
  Python files** matches current source. The wheel contains the retained MIT license and no
  skill, template, legacy namespace or local-path dependency. Sdist contains the tests and gotchas.
- Extracted-sdist tests ran against the installed rebuilt wheel outside the checkout, with
  `PYTHONPATH` unset: **175 tests plus 82 checks pass**. `uv pip check`: all 47 installed
  distributions compatible. Python 3.11.14, uv 0.9.30, Linux; Kusto data/ingest 5.0.2,
  management 4.0.0, Azure Identity 1.25.3 and Azure Core 1.41.0.
- Base-only wheel installation: configuration/schema/policy/identifier imports work, no
  optional SDK loaded, no old namespace present and no mutation granted. No token or I/O occurs.
- Root deployment safety suite: **74 tests pass**, including 19 exact-target lifecycle cases.
  Independent [Perth read-back](../../deploy/records/perth-adx-verify-20260916-v1.json) proves
  `Running`, `Succeeded`, `enableAutoStop=false`. The successful
  [one-property PATCH](../../deploy/records/perth-adx-keep-running-20260916-v2.json) preserved
  all projected protected settings. The earlier failed generic-CLI receipt is retained.
- Native catalogue: 28 remaining skills, 8 protocols and 5 embedded entries; no ADX skill
  registration remains. `.github/native-manifest.json` had no ADX record to edit. The root
  architecture checker reports no declared `architecture.json`, so it is advisory, not a gate.

Commands from the repository root, using an existing explicit source interpreter:

```bash
libraries/.venv/bin/python -B -m unittest discover -s libraries/azure-data-connectors/tests -t libraries/azure-data-connectors -q
libraries/.venv/bin/python -B libraries/azure-data-connectors/tests/event_store/selftest.py
PATH="$PWD/libraries/.venv/bin:$PATH" bash deploy/deploy.sh test
uv build --no-sources --project libraries --package azdata --out-dir "$ARTIFACTS"
uv build --wheel --no-sources "$SDIST" --out-dir "$REBUILT"
```

The shared environment and lock were neither synced nor updated. Parent must refresh
`libraries/uv.lock`, select extras in its consumers, migrate the listed imports, remove the
duplicated app subset and update root/portfolio status. Current app parity, dependency floors,
other Python/platform combinations, live operator writes and registry publication remain unverified.
Continuous cluster billing is intentional; price and external stop schedules are unknown.

### Verified Candidate

Candidate artifacts live outside the checkout; paths and hashes are in
[the machine record](docs/event-store/verification-20260916.json). Runtime/source equality is
the artifact claim; later evidence/provenance updates are not retroactively inside that sdist.

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| Source-built and sdist-rebuilt wheel | 107873 | `3b1a9bddcfab27e2ce57d75f579614fd7c445766f675e2caa254b727fb9a3794` |
| Sdist | 224655 | `0d89832d235b5322e8ba7e7f26fa779fba72487aac72971b7dbfc424c3ee0acd` |

All following sections describe **historical a3 evidence**, not the a4 artifact above.

## M1 Existing-Source Read Acceptance

The installed candidate passes the actual Investigation scan/evidence comparison and guarded
read-only browser journey. This proves the selected Perth transport/workflow, not the entire
connector catalogue, an independent domain-rule oracle, or model/graph/deployed-auth acceptance.

- Wheel SHA-256: `329e29f9bd56300e9703e268611f3a7c4b555253a3df866a65d125706d0f2f96`.
  All packaged bytes and import origin were read back from a new non-editable environment at
  `/tmp/agentcraft-m1.LlbuUO/env`. No canonical runtime file changed in this continuation.
- Python 3.12.3; Azure Core 1.41.0, Kusto 5.0.5, Identity 1.26.0b2, aiohttp 3.14.3.
  Native observer additionally needs `azure-kusto-data[aio]`; installing it added `asgiref`
  3.12.1. `uv pip check` passed for all 66 installed distributions.
- Independent SDK observations were frozen before candidate queries, then passed through
  unchanged application synthesis. Window: `2026-08-13T02:30:00Z` to `03:40:00Z`.
  Five rules produced two situations and evidence reads of 13 and 8 rows.
- [API receipt](../../deploy/records/m1-perth-candidate-20260915-v1.json): all 15 checks pass;
  expected/observed projected digest is
  `a26c0a933a59debf68456d9bbc6f1118fb1c9a4a698755f44017be4fb3b61cde`.
  Full row/schema order, event times, counts and truncation were compared.
- Browser: 62 checks pass at 1440x900, 900x800 and 390x844; real evidence control/read-back,
  zero horizontal overflow, catalogue-tab hit tests, mobile evidence and keyboard access.
  Ignored evidence: `template_apps/investigation_app/artifacts/browser/m1-20260915-v3/`.
- Native receipts: [failed prerequisite](../../deploy/records/m1-perth-rules-native-20260915-v1.json),
  [five rules](../../deploy/records/m1-perth-rules-native-20260915-v2.json), and
  [two evidence reads](../../deploy/records/m1-perth-evidence-native-20260915-v1.json).
  Native observations are not counted as public-library `PASS_LIVE` cases. Earlier passing
  Perth/AIT/MITRE receipts remain applicable to these unchanged library bytes.
- Focused checks: ten host-adapter tests, seven native-baseline assembly tests, thirteen
  application verifier tests and six ADX feature/observer tests pass. A nested timing omission
  and native datetime JSON failure were reproduced and repaired in test/verifier owners.
  No generic runtime defect was found in the accepted window; no duplicate owner was removed.

The browser guard aborts health, graph-entity, automatic summary and diagnosis requests before
delivery. Their visible unavailable states remain in screenshots; no fake result replaces them.
Only local gate refusals were exercised live. Actual provider-denied identities, broader
profile/mode rows, standalone feature CLI, independent developer acceptance and complete proving
environment remain blocked/unrun. Comparative usability/performance benefit is unmeasured.
The G5 investigation additionally passes six offline Gremlin tests. Three reduced app traversal
forms with bare `label`/`decr` and Groovy `true` refuse before credentials/driver construction.
No parser expansion or live graph claim follows: the app's ARM-key contract still conflicts
with canonical resource-token authority, so G5 is explicitly deferred.
Private customer fixtures remain outside version control; see the
[historical continuation record](../../deploy/records/library-integration-continuation-20260915.md) for bounds,
authority, exact commands, aggregate accounting and cleanup.

## First Offline Increment

At this earlier checkpoint, source and independently installed, sdist-rebuilt wheel each passed **130 offline tests**.
Four new checks exercise the public ADX feature through actual SDK/transport wiring with
controlled responses: matching and empty results, independent-oracle mismatch, service failure,
host refusal and honest offline evidence. Existing Kusto bearer/binding/refusal tests pass.

Fresh source-built and sdist-rebuilt wheels are byte-identical. Full tests were copied outside
the checkout and ran against the installed wheel with `PYTHONPATH` removed; `uv pip check`
passed. The host's real positive artifact preflight verified installed package files and import
origin against the wheel. Python 3.11.14; Azure Core 1.41.0, Kusto 5.0.2, Identity 1.25.3,
aiohttp 3.14.3. Broader environment/floor claims remain historical or unverified as labelled.

| Current Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| Wheel | 73,705 | `329e29f9bd56300e9703e268611f3a7c4b555253a3df866a65d125706d0f2f96` |
| Sdist | 106,109 | `60c33fe1eacef1730df8f7361e34b67ff496db9cdfdc02b08a9c64995c032d2f` |

[Machine receipt](../../deploy/records/library-integration-offline-2026-09-15.json) owns the
artifact location and run observations. [Deployment runbook](../../deploy/README.md) owns the
guarded, read-only `live plan/run` sequence. No live service call, fixture write, cluster start,
grant or publication occurred. A transport canary is not frozen application scan/evidence parity.

The earlier source/123-test artifact sections below are historical baselines, not these bytes.

## Observed Source Checks

- `uv 0.9.30`, CPython 3.11.14, Linux.
- Initial locked all-extras environment: 126 offline source tests passed after the template-integration
  fixes below; the earlier 123-test artifact evidence is preserved separately.
- Shared conformance covers all ten registered profiles and all ten async methods.
- Real Search/Cosmos/Blob/Table SDK request serialization and paging run over synthetic HTTP.
- Kusto request/response/ingestion models, Gremlin protocol/SASL and native SQL/PostgreSQL
  driver-call contracts are exercised. Database connections and remote services are synthetic.
- Blob exact-byte reads, Table typed values, ordered SQL parameters, scope/redirect refusal,
  unknown writes, no replay, GraphModel job references and Retry-After are covered.
- No editor diagnostics in the touched source/test directories at the checked state.

## Template Integration: Source Only

2026-09-15: the local [CyberEye migration template](../../template_apps/README.md) consumes
canonical `azdata` through a declared editable dependency in an independent Python 3.12.3
uv project. Its scanner, evidence and ADX tools use the library; its catalogue, Search, graph
and model paths remain legacy. Application/source project code is not imported by the library.

Two real consumer failures changed the shared SDK boundary:

- The generic Azure Core `AsyncPipelineClient` ignored the loose `authentication_policy`
  keyword. `Session.pipeline_client` now sets bearer, retry and redirect policies on explicit
  `Configuration`. Kusto/Eventhouse tests assert the bearer header and token audience, and
  prove invalid credentials refuse before transport.
- Passing `allow_redirects=False` to `AioHttpTransport.send` duplicated Azure Core's own
  aiohttp keyword and raised `TypeError` before network I/O. The wrapper no longer passes it;
  the new regression reaches the actual Azure Core transport and confirms aiohttp receives
  exactly one false redirect option. Redirect refusal remains enabled.

Observed: 126 library tests pass in the locked all-extras Python 3.11 environment; 505 copied
application tests pass (22 prerequisite skips), including eight real-facade migration tests
on Python 3.12/Kusto SDK 5.0.5. The eight cover typed parameter binding, dynamic/list values,
empty schemas, row caps, partial errors, permissions, no-I/O refusals and client lifetime.
Launcher, existing frontend and browser checks are recorded with the template.

Live ADX scan was attempted, first exposing the transport defect, then returning
`transport_unavailable`. Independent ARM read found the shared cluster stopped; it was not
started. Successful live ADX query/evidence parity remains unverified. No cloud mutation,
data write, new grant, model call or source-project edit occurred.

At that initial checkpoint the fixes had **not** been rebuilt into artifacts. The new
consumer-driven execution record above now identifies corrected bytes. Hashes and footprint
below continue to describe the earlier 123-test snapshot, not the current artifact.

## Artifact Checks

Local release gates passed after crash recovery on 2026-09-15. Earlier temporary release
outputs were absent; the results below come from newly built artifacts and fresh environments.
The [workspace release contract](../README.md#release-contract) owns the build sequence.

| Artifact / Environment | Python | Dependency Selection | Result |
| --- | --- | --- | --- |
| Wheel rebuilt from sdist, outside checkout | 3.11.14 | Current all-extras resolution | 123 tests pass |
| Same rebuilt wheel, outside checkout | 3.11.14 | Lowest jointly resolvable direct dependencies | 123 tests pass |
| Same rebuilt wheel, outside checkout | 3.12.3 | Current all-extras resolution | 123 tests pass |
| Base wheel, no provider packages installed | 3.11.14 | Base dependencies only | All ten profiles describe and return `missing_dependency_<service>` before credentials or I/O |

Each installed-wheel suite ran from copied tests outside the checkout with `PYTHONPATH`
unset. Import-location assertions proved `azdata` came from that environment's installed wheel.
`uv pip check` passed in all four environments. These are offline fixtures, not cloud tests.

Both source-built and sdist-rebuilt wheels are byte-identical. All 18 runtime Python files
in both wheels and the sdist matched source bytes at that build, before the integration fixes.
Wheel inspection found no bundled
tests, skills, templates or local-path dependency requirements. Source contains no skill or
template imports or path injection.

### Tested Dependencies

These are observed direct dependency versions, not a claim that every allowed combination
or platform works. Transitive dependencies were resolved normally, not minimized individually.

| Dependency | Current Python 3.11 Resolution | Lowest Joint Direct Resolution |
| --- | --- | --- |
| `azure-core` | 1.41.0 | 1.35.0 |
| `azure-identity` | 1.25.3 | 1.21.0 |
| `aiohttp` | 3.14.3 | 3.12.0 |
| `azure-search-documents` | 11.6.0 | 11.6.0 |
| `azure-cosmos` | 4.17.0 | 4.9.0 |
| `azure-storage-blob` | 12.30.1 | 12.26.0 |
| `azure-data-tables` | 12.7.0 | 12.7.0 |
| `azure-kusto-data` | 5.0.2 | 5.0.2 |
| `azure-kusto-ingest` | 5.0.2 | 5.0.2 |
| `mssql-python` | 1.15.0 | 1.15.0 |
| `sqlglot` | 28.10.1 | 28.10.1 |
| `psycopg` / `psycopg-binary` | 3.3.5 | 3.2.1 |
| `gremlinpython` | 3.7.7 | 3.7.7 |

The minimum run made the package's dependencies direct resolver inputs. Selecting
`--resolution lowest-direct` with only the wheel as input left its provider dependencies
at current versions; that earlier `minimum311` run is not minimum-version evidence.
Use the `declaredmin311` results. From the libraries directory, with an empty external
environment and the rebuilt wheel selected:

```bash
uv pip install --python "$VERIFY_ENV/bin/python" --resolution lowest-direct \
  --all-extras -r azure-data-connectors/pyproject.toml "$WHEEL"
```

The all-extras floor selected Azure Identity 1.21.0 and Psycopg 3.2.1; lower declared
versions were not individually verified in this pass. The tested Microsoft native ODBC
companion was `mssql-python-odbc` 18.6.2.1. Non-Linux native-driver behavior remains unverified.

### Artifact Identity

Build used uv 0.9.30, Python 3.11.14 and `SOURCE_DATE_EPOCH=1789408262` for deterministic
wheel timestamps. Artifact and test outputs are local, ignored and not published:

```text
libraries/dist/azdata-4.0.0a3-recovery.qMMiHR/
  artifacts/azdata-4.0.0a3-py3-none-any.whl
  artifacts/azdata-4.0.0a3.tar.gz
  rebuilt/azdata-4.0.0a3-py3-none-any.whl
  full311-*, full312-*, declaredmin311-*, base311-*
```

The last row names install/test/compatibility logs and frozen installed-package lists.
External test environments were under `/tmp/azdata-a3-verification-recovery.iczTKi`;
their persistence is not required by the recorded results.

| Artifact | Bytes | SHA-256 |
| --- | --- | --- |
| Source-built wheel | 73,429 | `b6f566fc4b73d559ede454432c15c6d789df4e25595822c2e172483f12ae3284` |
| Wheel rebuilt from sdist | 73,429 | `b6f566fc4b73d559ede454432c15c6d789df4e25595822c2e172483f12ae3284` |
| Sdist | 105,606 | `042cb024fac669ed45a964baa6300e38e08e2bbec5100c378254b095be2b6c9c` |

### Measured Footprint

| Scope | Python Files | Newline-Counted Lines |
| --- | --- | --- |
| Runtime | 18 | 3,052 |
| Tests | 20 | 1,846 |

Counts exclude documentation, lockfiles, dependencies, generated files and environments.
This increment adds service coverage; it does not claim net source-size reduction or
retirement of the legacy implementations.

## Not Established

- M1 adds the bounded existing-source proof above, not full Azure/Fabric CRUD, role, firewall,
  consistency, native-driver/server or capacity acceptance. Standalone/composed library entry
  points and remaining live catalogue rows are still incomplete or unrun.
- Gremlin's Python-3.11-compatible driver line is newer than Microsoft's recommendation;
  resource-token issuance is a caller-owned prerequisite, not an implemented identity broker.
- GraphModel query is beta and requires explicit opt-in.
- Infrastructure provisioning, most schema writes, queued batch verification, durable
  operation references and complete native SDK parity remain outside this implementation.
- No skill migration, package registry publication or cloud mutation occurred. The local ADX
  application migration is partial; the original application and other data paths are unchanged.