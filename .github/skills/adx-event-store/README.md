# ADX Event Store

Complete connector, operator bootstrap, schema inference, preserved service gotchas and offline
tests. Python 3.11+; official Azure SDKs are declared in [pyproject.toml](pyproject.toml) and
resolved in [uv.lock](uv.lock). No MCP server, endpoint default, role grant or deployment hook.

Resolve `SKILL_ROOT` to the loaded skill directory. Keep dependencies outside the plugin:

```bash
UV_PROJECT_ENVIRONMENT="$RUNTIME_ROOT" uv sync --locked --no-install-project --project "$SKILL_ROOT"
"$RUNTIME_ROOT/bin/python" -B "$SKILL_ROOT/tests/selftest.py"
"$RUNTIME_ROOT/bin/python" -B "$SKILL_ROOT/tests/test_bootstrap.py"
```

`RUNTIME_ROOT` is an operator-chosen external directory. Windows uses `Scripts/python.exe`;
Windows execution has not been verified. To import into an application's own environment, install
this skill directory with that environment's `pip`. Its package is `adx_connector`.

```python
from adx_connector import AdxConfig, AdxConnector

config = AdxConfig(cluster_uri=operator_endpoint, database=operator_database)
with AdxConnector(config, credential=workload_credential) as store:
    result = store.query("Events | where record_id == record_key", {"record_key": requested_key})
```

This is an integration shape, not an authorized live query. The application owns authentication,
authorization and limits. `from_env()` is an optional composition-edge convenience, not ambient
configuration imported by the CLI. Pass credentials/configuration explicitly inside services.

[SKILL.md](SKILL.md) gives the ingestion sequence and operator command. Confirmation flags prevent
accidental invocation, not malicious callers: the direct Python API remains powerful and requires
an authorized caller. Use the existing query skill when ingestion/provisioning is not needed.

Offline evidence: 82 connector checks and five bootstrap test cases pass with the locked SDKs.
No cluster creation, ingestion, role assignment, production query or paid operation was run here.
Contracts: [CONTRACT.md](CONTRACT.md). Migration: [PROVENANCE.md](PROVENANCE.md).