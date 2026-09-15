# Verification

Version: `azdata` 4.0.0a3. Date: 2026-09-15.

## Observed Source Checks

- `uv 0.9.30`, CPython 3.11.14, Linux.
- Locked all-extras environment: 126 offline source tests pass after the template-integration
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

These fixes have **not** been rebuilt into release artifacts. The artifact hashes, byte
counts and footprint below describe the earlier 123-test snapshot, not current source.

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

- No live Azure/Fabric CRUD, identity, role, firewall, consistency, native driver/server or
  capacity check ran for this increment. The live-test directory remains design-only.
- Gremlin's Python-3.11-compatible driver line is newer than Microsoft's recommendation;
  resource-token issuance is a caller-owned prerequisite, not an implemented identity broker.
- GraphModel query is beta and requires explicit opt-in.
- Infrastructure provisioning, most schema writes, queued batch verification, durable
  operation references and complete native SDK parity remain outside this implementation.
- No skill migration, package registry publication or cloud mutation occurred. The local ADX
  application migration is partial; the original application and other data paths are unchanged.