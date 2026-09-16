#!/usr/bin/env python3
"""Provision Azure Data Explorer and load any CSV, end to end.

    python3 bootstrap_adx.py \\
        --csv events.csv --table MyEvents \\
        --subscription <id> --resource-group my-rg --cluster mycluster01 \\
        --database MyDb --location <region> --confirm-database MyDb

Idempotent. An existing cluster, database, or table is reused; `.create-merge`
is additive; and a dedupe tag makes a replayed load a no-op rather than a
duplicate.

Prerequisites: `az login`, plus `azure-kusto-data`, `azure-kusto-ingest`,
`azure-mgmt-kusto`, and `azure-identity`. Authentication is Entra ID through
`DefaultAzureCredential`; no key or connection string is read or stored.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

from azdata.event_store import AdxConfig, AdxConnector, AdxError, EventStorePolicy
from azdata.event_store.identifiers import validate_identifier, validate_type
from azdata.event_store.ingest import IngestMode  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    source = parser.add_argument_group("source")
    source.add_argument("--csv", type=Path, required=True, help="CSV file to load")
    source.add_argument("--table", required=True, help="destination table name")
    source.add_argument("--no-header", action="store_true", help="the CSV has no header row")
    source.add_argument("--sample-rows", type=int, default=5_000, help="rows to inspect for type inference; 0 reads all")
    source.add_argument(
        "--force-type",
        action="append",
        default=[],
        metavar="COLUMN:KUSTO_TYPE",
        help="override inference for one column; repeatable",
    )

    target = parser.add_argument_group("target")
    target.add_argument("--cluster-uri", help="query endpoint; derived from --cluster when omitted")
    target.add_argument("--database", required=True)
    target.add_argument("--subscription", help="required to provision")
    target.add_argument("--resource-group", help="required to provision")
    target.add_argument("--cluster", help="cluster name; required to provision")
    target.add_argument("--location", help="explicit region; required when provisioning or deriving the endpoint")
    target.add_argument("--sku", default="Dev(No SLA)_Standard_E2a_v4")
    target.add_argument("--sku-tier", default="Basic")

    behaviour = parser.add_argument_group("behaviour")
    behaviour.add_argument("--confirm-database", help="must equal --database before any connection or write")
    behaviour.add_argument("--confirm-table", help="must equal --table when --recreate is requested")
    behaviour.add_argument("--skip-provision", action="store_true", help="assume cluster and database exist")
    behaviour.add_argument("--recreate", action="store_true", help="drop the table before loading")
    behaviour.add_argument("--streaming", action="store_true", help="managed streaming instead of queued")
    behaviour.add_argument("--batching-seconds", type=int, default=30, help="table batching latency")
    behaviour.add_argument("--expect-rows", type=int, help="fail unless this many rows become queryable")
    behaviour.add_argument("--timeout", type=int, default=900, help="seconds to wait for rows")
    behaviour.add_argument("--report", type=Path, help="write a JSON report here")
    behaviour.add_argument("--verbose", action="store_true")
    return parser


def count_data_rows(path: Path, has_header: bool) -> int:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        if has_header:
            next(reader, None)
        return sum(1 for row in reader if row)


def batch_identity(path: Path, table: str, *, has_header: bool, force_types: dict[str, str]) -> str:
    digest = hashlib.sha256()
    digest.update(json.dumps({"table": table, "has_header": has_header, "force_types": force_types}, sort_keys=True).encode())
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def batch_rows(adx: AdxConnector, table: str, tag: str) -> int:
    validate_identifier(table, kind="table")
    return int(adx.query(f"{table} | where set_has_element(extent_tags(), batch_tag) | count",
                         {"batch_tag": f"ingest-by:{tag}"}).scalar(0) or 0)


def wait_for_batch(adx: AdxConnector, table: str, tag: str, expected: int, timeout: int) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        observed = batch_rows(adx, table, tag)
        if observed == expected:
            return observed
        if observed > expected:
            raise AdxError(f"batch has {observed} rows, expected exactly {expected}")
        time.sleep(min(5, max(0, deadline - time.monotonic())))
    raise AdxError(f"batch did not reach exactly {expected} rows within {timeout}s")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        validate_identifier(args.table, kind="table")
        validate_identifier(args.database, kind="database")
    except AdxError as exc:
        print(f"invalid target: {exc}", file=sys.stderr)
        return 2
    if args.confirm_database != args.database:
        print("writes require --confirm-database matching --database", file=sys.stderr)
        return 2
    if args.recreate and args.confirm_table != args.table:
        print("recreation requires --confirm-table matching --table", file=sys.stderr)
        return 2
    if not args.skip_provision and not all((args.subscription, args.resource_group, args.cluster, args.location)):
        print("provisioning requires explicit subscription, resource group, cluster and location", file=sys.stderr)
        return 2
    if args.no_header:
        print("bootstrap requires a CSV header; use the connector's explicit-schema ingestion API for headerless data", file=sys.stderr)
        return 2
    if args.timeout <= 0 or args.sample_rows < 0 or not 1 <= args.batching_seconds <= 59:
        print("invalid timeout, schema sample size, or batching seconds (1-59)", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    # The Azure SDKs log every HTTP exchange at INFO, burying this script's output.
    for noisy in ("azure", "azure.core", "azure.identity", "msal", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    if not args.csv.is_file():
        print(f"csv not found: {args.csv}", file=sys.stderr)
        return 2

    cluster_uri = args.cluster_uri
    if not cluster_uri:
        if not args.cluster or not args.location:
            print("supply --cluster-uri, or --cluster and --location to derive it", file=sys.stderr)
            return 2
        cluster_uri = f"https://{args.cluster}.{args.location}.kusto.windows.net"

    force_types: dict[str, str] = {}
    for item in args.force_type:
        if ":" not in item:
            print(f"--force-type expects COLUMN:KUSTO_TYPE, got {item!r}", file=sys.stderr)
            return 2
        column, kusto_type = item.split(":", 1)
        try:
            validate_identifier(column, kind="column")
            validate_type(kusto_type)
        except AdxError as exc:
            print(f"invalid type override: {exc}", file=sys.stderr)
            return 2
        force_types[column] = kusto_type

    config = AdxConfig(
        cluster_uri=cluster_uri,
        database=args.database,
        subscription_id=args.subscription,
        resource_group=args.resource_group,
        cluster_name=args.cluster,
        location=args.location or "",
        sku_name=args.sku,
        sku_tier=args.sku_tier,
    )

    actual = count_data_rows(args.csv, not args.no_header)
    if actual <= 0 or args.expect_rows is not None and args.expect_rows != actual:
        print("CSV must contain rows and --expect-rows must equal its record count", file=sys.stderr)
        return 2
    expected = actual
    tag = batch_identity(args.csv, args.table, has_header=not args.no_header, force_types=force_types)
    started = time.monotonic()
    report: dict[str, object] = {
        "csv": str(args.csv),
        "table": args.table,
        "cluster_uri": cluster_uri,
        "database": args.database,
        "expected_rows": expected,
        "batch_tag": tag,
    }

    grants = {"ingest", "schema"}
    if not args.skip_provision:
        grants.add("provision")
    if args.recreate:
        grants.update({"command", "delete"})
    policy = EventStorePolicy(principal="confirmed-bootstrap-operator", grants=frozenset(grants))
    try:
        with AdxConnector(config, policy=policy) as adx:
            if not args.skip_provision:
                if not config.can_provision:
                    print("provisioning needs --subscription, --resource-group, and --cluster", file=sys.stderr)
                    return 2
                print("ensuring cluster and database ...")
                info = adx.ensure_infrastructure()
                report["cluster"] = {"name": info.name, "state": info.state, "created": info.created}
                print(f"  {info.name} is {info.state}")

            health = adx.health()
            if not health.get("reachable"):
                print(f"cluster unreachable: {health.get('error')}", file=sys.stderr)
                return 1
            print(f"  authenticated as {health.get('principal')}")

            if args.recreate:
                adx.command(f".drop table {args.table} ifexists")
                print(f"  dropped {args.table}")

            schema = adx.infer_schema_from_csv(
                args.csv, args.table, sample_rows=args.sample_rows, force_types=force_types
            )
            report["columns"] = len(schema.columns)
            print(f"  inferred {len(schema.columns)} columns")

            mapping = f"{args.table}CsvMapping"
            adx.create_table(schema, mapping_name=mapping)
            adx.set_batching_latency(args.table, args.batching_seconds)
            adx.enable_streaming(args.table)
            print(f"  {args.table} ready; batching {args.batching_seconds}s, streaming enabled")

            present = batch_rows(adx, args.table, tag)
            if present > expected:
                raise AdxError(f"batch has {present} rows, expected exactly {expected}")
            if present == expected:
                print(f"  batch already holds {present:,} rows; skipping ingest")
                report["ingest"] = {"skipped": True, "rows_present": present}
                report["rows_queryable"] = present
            else:
                mode = IngestMode.MANAGED_STREAMING if args.streaming else IngestMode.QUEUED
                print(f"  ingesting {args.csv.stat().st_size:,} bytes via {mode.value} ...")
                result = adx.ingestor.ingest_file(
                    args.csv,
                    args.table,
                    mode=mode,
                    mapping_reference=mapping,
                    dedupe_tag=tag,
                    ignore_first_record=not args.no_header,
                )
                report["ingest"] = {
                    "mode": result.mode.value,
                    "bytes": result.bytes_sent,
                    "accepted_seconds": round(result.elapsed_seconds, 2),
                    "dedupe_tag": tag,
                }
                print(f"  accepted in {result.elapsed_seconds:.2f}s; waiting for rows ...")
                # Acceptance is not arrival: queued ingestion batches before rows
                # become queryable, so success is only provable by counting.
                observed = wait_for_batch(adx, args.table, tag, expected, args.timeout)
                report["rows_queryable"] = observed
                print(f"  {observed:,} rows queryable")

            failures = adx.ingestion_failures(hours=1)
            report["recent_ingestion_failures"] = len(failures)
            if len(failures):
                print(f"  WARNING: {len(failures)} ingestion failure(s) in the last hour")

    except AdxError as exc:
        print(f"ERROR {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    report["total_seconds"] = round(time.monotonic() - started, 2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
        print(f"wrote {args.report}")
    print(f"done in {report['total_seconds']}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
