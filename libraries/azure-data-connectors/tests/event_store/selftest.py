#!/usr/bin/env python3
"""Offline contract tests for the ADX connector skill.

Runs without Azure. Gates the behaviours that must not regress: the injection
boundary, parameter typing, schema inference, guarded destructives, and imports
from the skill's own mechanism.

    python3 tests/selftest.py
"""

from __future__ import annotations

import csv
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from azdata.event_store import AdxConfig, AdxConnector  # noqa: E402
from azdata.event_store.client import AdxClient, _kusto_type_of  # noqa: E402
from azdata.event_store.crud import CrudRepository, UpsertStrategy  # noqa: E402
from azdata.event_store.errors import AdxConfigError, AdxIdentifierError, AdxQueryError  # noqa: E402
from azdata.event_store.identifiers import validate_identifier, validate_type  # noqa: E402
from azdata.event_store.models import ColumnSpec, QueryResult, TableSchema  # noqa: E402
from azdata.event_store.retry import backoff_delay, is_retryable  # noqa: E402
from azdata.event_store.schema import create_table_command, csv_mapping_command, infer_schema  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    (PASSED if condition else FAILED).append(f"{name}{': ' + detail if detail and not condition else ''}")


# ---------------------------------------------------------------- injection

HOSTILE = [
    "a; .drop table X",
    "a b",
    "1abc",
    "where",
    'a"b',
    "a'--",
    "a)|.drop",
    "",
    "x" * 200,
    "table",
    "../../etc/passwd",
    "a\nb",
]

for candidate in HOSTILE:
    try:
        validate_identifier(candidate)
        check(f"reject {candidate!r}", False, "was accepted")
    except AdxIdentifierError:
        check(f"reject {candidate!r}", True)

for good in ("source_time", "EventsUnified", "_internal", "a1"):
    try:
        validate_identifier(good)
        check(f"accept {good!r}", True)
    except AdxIdentifierError as exc:
        check(f"accept {good!r}", False, str(exc))

try:
    validate_type("nonsense")
    check("reject unknown kusto type", False, "was accepted")
except AdxIdentifierError:
    check("reject unknown kusto type", True)


# --------------------------------------------------------------- parameters

check("bool types as bool", _kusto_type_of(True) == "bool", str(_kusto_type_of(True)))
check("int types as long", _kusto_type_of(5) == "long")
check("float types as real", _kusto_type_of(1.5) == "real")
check("str types as string", _kusto_type_of("x") == "string")
check("datetime types as datetime", _kusto_type_of(datetime.now(timezone.utc)) == "datetime")
check("timedelta types as timespan", _kusto_type_of(timedelta(seconds=1)) == "timespan")
check("list types as dynamic", _kusto_type_of([1, 2]) == "dynamic")
check("unsupported type is None", _kusto_type_of(object()) is None)

declared = AdxClient.declare_parameters({"a": "s", "b": 1, "c": True})
check("declaration renders", declared.startswith("declare query_parameters("), declared)
check("declaration types bool before long", "c:bool" in declared, declared)
check("empty declaration is empty", AdxClient.declare_parameters(None) == "")

try:
    AdxClient.declare_parameters({"bad name": 1})
    check("declaration validates names", False, "accepted a hostile parameter name")
except AdxIdentifierError:
    check("declaration validates names", True)


# ------------------------------------------------------------------- config

try:
    AdxConfig(cluster_uri="http://insecure", database="db")
    check("config rejects non-https", False, "accepted http")
except AdxConfigError:
    check("config rejects non-https", True)

config = AdxConfig(cluster_uri="https://c.australiaeast.kusto.windows.net", database="db")
check(
    "ingest endpoint derives",
    config.ingestion_endpoint == "https://ingest-c.australiaeast.kusto.windows.net",
    config.ingestion_endpoint,
)
check("cannot provision without control-plane fields", config.can_provision is False)

try:
    AdxConfig(cluster_uri="https://c.kusto.windows.net", database="bad name")
    check("config validates database name", False, "accepted a hostile database name")
except AdxIdentifierError:
    check("config validates database name", True)


# ------------------------------------------------------------------- schema

with tempfile.TemporaryDirectory() as tmp:
    sample = Path(tmp) / "sample.csv"
    with sample.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["id", "when", "count", "ratio", "flag", "payload", "note", "empty"])
        writer.writerow(["a", "2026-08-13T03:00:00Z", "5", "1.5", "true", '{"k":1}', "text", ""])
        writer.writerow(["b", "2026-08-13T03:00:01Z", "6", "2.5", "false", '{"k":2}', "more", ""])
    schema = infer_schema(sample, "Sample")
    kinds = {column.name: column.kusto_type for column in schema.columns}
    check("infers datetime", kinds["when"] == "datetime", kinds["when"])
    check("infers long", kinds["count"] == "long", kinds["count"])
    check("infers real", kinds["ratio"] == "real", kinds["ratio"])
    check("infers bool", kinds["flag"] == "bool", kinds["flag"])
    check("infers dynamic", kinds["payload"] == "dynamic", kinds["payload"])
    check("infers string", kinds["note"] == "string", kinds["note"])
    check("all-null column widens to string", kinds["empty"] == "string", kinds["empty"])

    command = create_table_command(schema)
    check("create is merge, so it is idempotent", command.startswith(".create-merge table Sample ("), command[:40])
    mapping = csv_mapping_command(schema, "SampleCsv")
    # Kusto takes the mapping as a JSON string, so the payload is double-encoded
    # and the property names appear escaped in the command text.
    check("mapping binds ordinals", '\\"Ordinal\\"' in mapping, mapping[:120])
    check("mapping names every column", mapping.count('\\"Column\\"') == len(schema.columns), mapping[:120])


# ------------------------------------------------------------------- models

result = QueryResult(columns=("a", "b"), rows=((1, "x"), (2, "y")))
check("result length", len(result) == 2)
check("result scalar", result.scalar() == 1)
check("result dicts", result.to_dicts()[1] == {"a": 2, "b": "y"})
check("result column values", result.column_values("b") == ["x", "y"])
check("empty result scalar default", QueryResult(columns=(), rows=()).scalar("none") == "none")
try:
    result.column_values("missing")
    check("result rejects unknown column", False, "accepted")
except KeyError:
    check("result rejects unknown column", True)


# --------------------------------------------------------------------- CRUD

scratch = TableSchema(
    name="Scratch",
    columns=(ColumnSpec("record_id", "string"), ColumnSpec("score", "long")),
)
repo = CrudRepository(AdxClient(config), object(), scratch)  # type: ignore[arg-type]

for label, call in (
    ("delete refuses empty predicate", lambda: repo.delete_where("")),
    ("truncate refuses without confirm", lambda: repo.truncate()),
    ("truncate refuses wrong confirm", lambda: repo.truncate(confirm="Other")),
    ("drop refuses without confirm", lambda: repo.drop()),
    ("purge refuses without confirm", lambda: repo.purge_where("score > 0")),
    ("get refuses unknown column", lambda: repo.get("nope", 1)),
    ("get refuses hostile column", lambda: repo.get("a; .drop table X", 1)),
    ("read refuses non-positive limit", lambda: repo.read(limit=0)),
):
    try:
        call()
        check(label, False, "was not refused")
    except (AdxQueryError, AdxIdentifierError):
        check(label, True)

check("delete_in on empty keys is a no-op", repo.delete_in("record_id", []) == 0)
check("batch tags are unique", CrudRepository.new_batch_tag() != CrudRepository.new_batch_tag())
check("both upsert strategies exist", {s.value for s in UpsertStrategy} == {"soft_delete_replace", "append_versioned"})


# -------------------------------------------------------------------- retry

check("backoff respects the cap", all(0 <= backoff_delay(i, 0.5, 20.0) <= 20.0 for i in range(10)))
check("backoff is jittered", len({round(backoff_delay(5, 0.5, 20.0), 6) for _ in range(20)}) > 1)
check("plain errors are not retryable", is_retryable(ValueError("nope")) is False)


# --------------------------------------------------------------------- API

for name in ("ensure_infrastructure", "health", "create_table", "repository", "load_csv", "wait_for_rows", "query", "command"):
    check(f"connector exposes {name}", hasattr(AdxConnector, name))
for name in ("insert", "get", "read", "count", "update", "delete_where", "delete_in", "purge_where", "truncate", "drop"):
    check(f"repository exposes {name}", hasattr(CrudRepository, name))


check("connector imports from canonical azdata package", sys.modules["azdata.event_store"].__package__ == "azdata.event_store")


# ------------------------------------------------------------------- report

for line in FAILED:
    print(f"FAIL {line}")
print(f"{len(PASSED)}/{len(PASSED) + len(FAILED)} checks passed")
sys.exit(1 if FAILED else 0)
