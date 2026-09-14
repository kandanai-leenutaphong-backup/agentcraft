#!/usr/bin/env python3
"""probe.py — prove the connectors can actually reach their services.

Usage:
    python3 scripts/probe.py                       # every configured service
    python3 scripts/probe.py --service kql
    python3 scripts/probe.py --search-index my-index
    python3 scripts/probe.py --cosmos-database db --cosmos-container items
    python3 scripts/probe.py --service cosmos-account

Exists because "did I configure this correctly" and "does my identity have
the role assignment" are the two questions that eat an afternoon, and both
are answerable in one round trip per service. Each probe issues the
smallest possible read.

THIS SCRIPT NEVER WRITES
------------------------
It is safe against production, and that constraint decides what the write
and deploy planes can be probed for:

* **Write plane** — the connectors are built with ``WritePolicy.read_only()``
  and probed with their ``query`` method. That proves the endpoint, the
  credential and the *reader* role assignment. It does **not** prove the
  write role assignment, and there is no way to prove that without
  writing. If you need that proof, write a disposable document to a
  disposable index yourself; this script will not do it for you.
* **Deploy plane** — the provisioners are built with
  ``ProvisionPolicy.read_only()`` and probed with ``describe``, which is a
  management-plane GET. ``ensure`` and ``teardown`` are never called, and
  the read-only policy means they would be refused if they were.

Exit codes:
    0  every configured service answered
    1  at least one configured service failed
    2  nothing was configured

Unconfigured services are skipped, not failed: a deployment that uses two
of the surfaces is normal.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from azdata import (  # noqa: E402
    AzureDataConfig,
    ProvisionPolicy,
    WritePolicy,
    connect,
    is_error,
)

# ``label`` and ``partition_key_field`` are write-plane parameters: they
# decide how an item's key is derived, and no read path in this script
# reaches them. A placeholder is honest here; demanding a flag that cannot
# change the outcome is not.
UNUSED_BY_READ_PROBE = "<probe-unused>"


async def _timed(label: str, coro) -> tuple[str, bool, str, float]:
    """Run a probe, returning (label, ok, detail, elapsed_ms). Never raises."""
    started = time.monotonic()
    try:
        ok, detail = await coro
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return label, ok, detail, (time.monotonic() - started) * 1000


async def _probe_gremlin(connectors) -> tuple[bool, str]:
    payload = await connectors.gremlin.execute("g.V().limit(1).count()")
    if is_error(payload):
        return False, json.loads(payload)["detail"]
    return True, f"count={payload}"


async def _probe_kql(connectors) -> tuple[bool, str]:
    payload = await connectors.kql.execute("print probe = 1")
    if is_error(payload):
        return False, json.loads(payload)["detail"]
    return True, f"rows={len(json.loads(payload)['rows'])}"


async def _probe_search(connectors, index: str, semantic: str) -> tuple[bool, str]:
    if not index:
        return False, "no --search-index given; cannot probe an index by guess"
    payload = await asyncio.to_thread(
        connectors.search.execute,
        "probe",
        index_name=index,
        semantic_config=semantic,
        project_doc=lambda doc: {"id": doc.get("id") or doc.get("chunk_id") or ""},
        top_k=1,
        vector_field="",
    )
    parsed = json.loads(payload)
    if parsed.get("error"):
        return False, parsed["detail"]
    if parsed.get("degraded"):
        return False, f"degraded: {parsed['detail']}"
    return True, f"hits={parsed['count']}"


async def _probe_graph(connectors) -> tuple[bool, str]:
    healthy = await connectors.graph.is_healthy()
    return healthy, "metadata 200" if healthy else "metadata endpoint did not answer"


async def _probe_cosmos(connectors, database: str, container: str) -> tuple[bool, str]:
    if not database or not container:
        return False, "no --cosmos-database/--cosmos-container given"
    store = connectors.cosmos(database, container)
    healthy = await store.is_healthy(timeout=5.0)
    return healthy, "container answered" if healthy else "probe query failed or timed out"


# ── Write plane. Read-only policies; nothing below mutates anything. ─────────


async def _probe_documents(connectors, index: str) -> tuple[bool, str]:
    """Search write plane, read side. Proves the reader role, not the writer."""
    if not index:
        return False, "no --search-index given; cannot probe an index by guess"
    documents = connectors.documents(index, policy=WritePolicy.read_only())
    payload = await documents.query(
        "probe", project_doc=lambda doc: {"id": doc.get("id", "")}, top=1
    )
    if is_error(payload):
        return False, json.loads(payload)["detail"]
    return True, f"hits={json.loads(payload)['count']} (read only; no write attempted)"


async def _probe_items(connectors, database: str, container: str) -> tuple[bool, str]:
    """Cosmos write plane, read side. The query is guarded and row-capped."""
    if not database or not container:
        return False, "no --cosmos-database/--cosmos-container given"
    items = connectors.items(
        database,
        container,
        partition_key_field=UNUSED_BY_READ_PROBE,
        policy=WritePolicy.read_only(),
    )
    payload = await items.query("SELECT TOP 1 c.id FROM c")
    if is_error(payload):
        return False, json.loads(payload)["detail"]
    return True, f"rows={json.loads(payload)['count']} (read only; no write attempted)"


async def _probe_elements(connectors) -> tuple[bool, str]:
    """Gremlin write plane, read side.

    ``GremlinElements.query`` deliberately runs on the read-only connector,
    so this probe also confirms that the caller-supplied path still carries
    the write guard.
    """
    elements = connectors.elements(
        UNUSED_BY_READ_PROBE,
        partition_key_field=UNUSED_BY_READ_PROBE,
        policy=WritePolicy.read_only(),
    )
    payload = await elements.query("g.V().limit(1).count()")
    if is_error(payload):
        return False, json.loads(payload)["detail"]
    return True, f"count={payload} (read only; no write attempted)"


# ── Deploy plane. describe() only — never ensure(), never teardown(). ────────


async def _describe(provisioner) -> tuple[bool, str]:
    """Run ``describe`` and project the envelope. Closes a client it opened."""
    try:
        payload = await provisioner.describe()
    finally:
        close = getattr(provisioner, "close", None)
        if close is not None:
            close()
    parsed = json.loads(payload)
    if parsed.get("error"):
        return False, parsed["detail"]
    state = parsed.get("state") or "-"
    return True, f"present={str(parsed.get('present')).lower()} state={state}"


def _read_only_deploy() -> ProvisionPolicy:
    """The grant this script makes: none. ``ensure`` and ``teardown`` refuse."""
    return ProvisionPolicy.read_only()


async def _probe_search_index(connectors, index: str) -> tuple[bool, str]:
    if not index:
        return False, "no --search-index given"
    return await _describe(
        connectors.provision_search_index(index, policy=_read_only_deploy())
    )


async def _probe_search_service(connectors) -> tuple[bool, str]:
    return await _describe(
        connectors.provision_search_service(policy=_read_only_deploy())
    )


async def _probe_cosmos_account(connectors) -> tuple[bool, str]:
    return await _describe(
        connectors.provision_cosmos_account(policy=_read_only_deploy())
    )


async def _probe_cosmos_database(connectors, database: str) -> tuple[bool, str]:
    if not database:
        return False, "no --cosmos-database given"
    return await _describe(
        connectors.provision_cosmos_database(database, policy=_read_only_deploy())
    )


async def _probe_cosmos_container(
    connectors, database: str, container: str
) -> tuple[bool, str]:
    if not database or not container:
        return False, "no --cosmos-database/--cosmos-container given"
    return await _describe(
        connectors.provision_cosmos_container(
            database, container, policy=_read_only_deploy()
        )
    )


async def _probe_gremlin_database(connectors) -> tuple[bool, str]:
    return await _describe(
        connectors.provision_gremlin_database(policy=_read_only_deploy())
    )


async def _probe_gremlin_graph(connectors) -> tuple[bool, str]:
    return await _describe(
        connectors.provision_gremlin_graph(policy=_read_only_deploy())
    )


def _availability(connectors) -> dict[str, bool]:
    """Which surfaces this config can address, in probe order.

    ``Connectors.configured()`` reports one aggregate ``management`` flag,
    which is the right shape for a health endpoint and the wrong shape
    here: each deploy-plane surface needs a different coordinate on top of
    it, and a surface listed without a probe would raise a KeyError below.
    """
    base = connectors.configured()
    cfg = connectors.config
    mgmt = base["management"]
    return {
        "gremlin": base["gremlin"],
        "kql": base["kql"],
        "search": base["search"],
        "graph": base["graph"],
        "cosmos": base["cosmos"],
        "documents": base["search"],
        "items": base["cosmos"],
        "elements": base["gremlin"],
        "search-index": base["search"],
        "search-service": mgmt and bool(cfg.search_service_name),
        "cosmos-account": mgmt and bool(cfg.cosmos_account_name),
        "cosmos-database": mgmt and bool(cfg.cosmos_account_name),
        "cosmos-container": mgmt and bool(cfg.cosmos_account_name),
        "gremlin-database": mgmt and bool(cfg.gremlin_account_name),
        "gremlin-graph": mgmt and bool(cfg.gremlin_account_name),
    }


async def run(args: argparse.Namespace) -> int:
    config = AzureDataConfig.from_env(prefix=args.prefix)
    connectors = connect(config)
    configured = _availability(connectors)

    wanted = (
        list(configured) if args.service == "all" else [args.service]
    )
    selected = [name for name in wanted if configured.get(name)]
    skipped = [name for name in wanted if not configured.get(name)]

    for name in skipped:
        print(f"  skip {name:<16} not configured")

    if not selected:
        print("\nnothing configured — set the endpoint variables and retry")
        return 2

    probes = {
        "gremlin": lambda: _probe_gremlin(connectors),
        "kql": lambda: _probe_kql(connectors),
        "search": lambda: _probe_search(
            connectors, args.search_index, args.semantic_config
        ),
        "graph": lambda: _probe_graph(connectors),
        "cosmos": lambda: _probe_cosmos(
            connectors, args.cosmos_database, args.cosmos_container
        ),
        "documents": lambda: _probe_documents(connectors, args.search_index),
        "items": lambda: _probe_items(
            connectors, args.cosmos_database, args.cosmos_container
        ),
        "elements": lambda: _probe_elements(connectors),
        "search-index": lambda: _probe_search_index(connectors, args.search_index),
        "search-service": lambda: _probe_search_service(connectors),
        "cosmos-account": lambda: _probe_cosmos_account(connectors),
        "cosmos-database": lambda: _probe_cosmos_database(
            connectors, args.cosmos_database
        ),
        "cosmos-container": lambda: _probe_cosmos_container(
            connectors, args.cosmos_database, args.cosmos_container
        ),
        "gremlin-database": lambda: _probe_gremlin_database(connectors),
        "gremlin-graph": lambda: _probe_gremlin_graph(connectors),
    }

    # Sequential on purpose: a parallel probe of a shared capacity can
    # produce the very throttling it is meant to detect.
    failures = 0
    for name in selected:
        label, ok, detail, elapsed = await _timed(name, probes[name]())
        status = "ok  " if ok else "FAIL"
        print(f"  {status} {label:<16} {elapsed:7.0f}ms  {detail}")
        failures += 0 if ok else 1

    await connectors.aclose()

    print()
    if failures:
        print(f"FAILED: {failures} of {len(selected)} configured service(s)")
        return 1
    print(f"PASSED: {len(selected)} service(s) reachable")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--service",
        default="all",
        choices=[
            "all",
            # Read plane.
            "gremlin",
            "kql",
            "search",
            "graph",
            "cosmos",
            # Write plane, probed read-only. Never writes.
            "documents",
            "items",
            "elements",
            # Deploy plane, probed with describe(). Never ensures or tears down.
            "search-index",
            "search-service",
            "cosmos-account",
            "cosmos-database",
            "cosmos-container",
            "gremlin-database",
            "gremlin-graph",
        ],
        help="one surface, or 'all' for every configured one",
    )
    parser.add_argument("--prefix", default="AZDATA_", help="environment variable prefix")
    parser.add_argument("--search-index", default="", help="index name for the search probe")
    parser.add_argument("--semantic-config", default="", help="semantic configuration name")
    parser.add_argument("--cosmos-database", default="")
    parser.add_argument("--cosmos-container", default="")
    args = parser.parse_args()

    print(f"probing azure data connectors (prefix={args.prefix or '<none>'})\n")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
