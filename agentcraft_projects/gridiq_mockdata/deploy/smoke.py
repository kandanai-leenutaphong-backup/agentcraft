#!/usr/bin/env python3
"""Smoke-test the real GridIQ tools against the rg-test-grid stores.

Imports ../../gridiq read-only. Supplies non-secret endpoint config only and blanks the
Fabric service-principal triple and the Search API key, so every tool resolves
AzureCliCredential (the signed-in az identity).

    python3 -B smoke.py --outputs FILE
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
GRIDIQ = (HERE.parent.parent / "gridiq").resolve()
sys.path.insert(0, str(HERE))

import stores  # noqa: E402

WINDOW = ("2026-03-10T14:00:00", "2026-03-10T15:00:00")


def configure(outputs: dict) -> dict:
    cfg = {
        "EVENTHOUSE_QUERY_URI": outputs["adxQueryUri"],
        "FABRIC_KQL_DB_NAME": outputs["adxDatabase"],
        "COSMOS_GREMLIN_ENDPOINT": outputs["cosmosGremlinEndpoint"],
        "COSMOS_GREMLIN_DATABASE": outputs["cosmosDatabase"],
        "COSMOS_GREMLIN_GRAPH": outputs["cosmosGraph"],
        "AI_SEARCH_ENDPOINT": outputs["searchEndpoint"],
        "AI_SEARCH_OPERATOR_ENDPOINT": outputs["searchEndpoint"],
        "AI_SEARCH_operator_ENDPOINT": outputs["searchEndpoint"],
        "ACTION_FEEDBACK_SEARCH_ENDPOINT": outputs["searchEndpoint"],
        "AI_SEARCH_USE_CLEAN_INDEX": "0",
    }
    blanked = ["FABRIC_TENANT_ID", "FABRIC_CLIENT_ID", "FABRIC_CLIENT_SECRET", "AI_SEARCH_API_KEY",
               "FABRIC_WORKSPACE_ID", "OTEL_EXPORT_TARGET"]
    os.environ.update(cfg)
    for name in blanked:
        os.environ[name] = ""
    return {"set": cfg, "blanked": blanked}


def classify(raw) -> tuple[str, str]:
    text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return ("non-empty" if text.strip() else "empty"), text[:240]
    if isinstance(data, dict) and (data.get("error") or data.get("degraded")):
        return "error", text[:240]
    if isinstance(data, list):
        return ("non-empty" if data else "empty"), text[:240]
    if isinstance(data, dict):
        for key in ("rows", "results", "situations", "value", "documents", "endpoints", "equipment", "busbars"):
            if key in data and isinstance(data[key], list):
                return ("non-empty" if data[key] else "empty"), text[:240]
        return ("non-empty" if data else "empty"), text[:240]
    return "non-empty", text[:240]


async def run(outputs: dict) -> dict:
    sys.path.insert(0, str(GRIDIQ))
    from foundation.request_scope import fabric_config
    from tools.gremlin import _gremlin_tool
    from tools.search._aisearch import client as search_client
    from tools.grid_reference._resolve import resolve_station
    from tools.watcher._watcher_tools import find_alarms, find_scada, find_alarm_by_mrid
    from tools.watcher._graph_tools import graph_station_equipment, graph_bus_topology
    from tools.watcher._graph_extras.corridor_endpoints import graph_corridor_endpoints
    from tools.search.investigation_clues import search_investigation_clues
    from tools.search.smirks import search_smirks
    from tools.search.knowledge_base import search_paws, search_nearhit_reports
    from tools.situations._situation_tool import detect_situations
    from foundation.config import settings

    bound = {
        "kql_query_uri": fabric_config().eventhouse_query_uri,
        "kql_db": fabric_config().kql_db_name,
        "gremlin_endpoint": _gremlin_tool.COSMOS_GREMLIN_ENDPOINT,
        "search_endpoint": search_client.AI_SEARCH_ENDPOINT,
        "operator_endpoint": settings.ai_search_operator_endpoint,
        "fabric_sp_configured": bool(settings.fabric_client_id and settings.fabric_client_secret.get_secret_value()),
    }
    expected = {"kql_query_uri": outputs["adxQueryUri"], "kql_db": outputs["adxDatabase"],
                "gremlin_endpoint": outputs["cosmosGremlinEndpoint"], "search_endpoint": outputs["searchEndpoint"],
                "operator_endpoint": outputs["searchEndpoint"], "fabric_sp_configured": False}
    if bound != expected:
        raise SystemExit(f"tools are not bound to the test stores: {bound} != {expected}")

    mrid = next(line.split(",")[5] for line in (stores.DATA / "kql/WatcherAlarmsAll.csv").read_text().splitlines()[1:]
                if line.endswith(",KESTREL"))
    calls = [
        ("resolve_station", lambda: resolve_station("Kestrel"), {"name": "Kestrel"}),
        ("find_alarms", lambda: find_alarms("KESTREL", *WINDOW), {"station": "KESTREL", "window": WINDOW}),
        ("find_scada", lambda: find_scada("KESTREL", *WINDOW), {"station": "KESTREL", "window": WINDOW}),
        ("find_alarm_by_mrid", lambda: find_alarm_by_mrid(mrid), {"mrid": mrid}),
        ("graph_station_equipment", lambda: graph_station_equipment("KESTREL"), {"station": "KESTREL"}),
        ("graph_bus_topology", lambda: graph_bus_topology("KESTREL"), {"station": "KESTREL"}),
        ("graph_corridor_endpoints", lambda: graph_corridor_endpoints("KM1"), {"line_path": "KM1"}),
        ("search_investigation_clues", lambda: search_investigation_clues("KESTREL unit trip"), {"query": "KESTREL unit trip"}),
        ("search_smirks", lambda: search_smirks("KESTREL generator"), {"query": "KESTREL generator"}),
        ("search_paws", lambda: search_paws("MARLOW BESS"), {"query": "MARLOW BESS"}),
        ("search_nearhit_reports", lambda: search_nearhit_reports("KM1 KM2 double circuit trip"),
         {"query": "KM1 KM2 double circuit trip"}),
        ("detect_situations", lambda: detect_situations("2026-03-10 14:00", "2026-03-10 15:00"),
         {"start": "2026-03-10 14:00", "end": "2026-03-10 15:00"}),
    ]
    results = []
    for name, call, args in calls:
        start = time.monotonic()
        try:
            raw = await call()
            status, excerpt = classify(raw)
            size = len(raw) if isinstance(raw, str) else len(json.dumps(raw, default=str))
        except Exception as exc:  # noqa: BLE001 - recorded as a finding
            status, excerpt, size = "error", f"{type(exc).__name__}: {str(exc)[:220]}", 0
        results.append({"tool": name, "args": args, "status": status, "bytes": size,
                        "seconds": round(time.monotonic() - start, 2), "excerpt": excerpt})
        print(f"smoke: {name:28s} {status:9s} {excerpt[:110]!r}", flush=True)
    return {"bound": bound, "results": results}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outputs", required=True)
    args = ap.parse_args()
    outputs = stores.load_outputs(args.outputs)
    config = configure(outputs)
    receipt = {"step": "smoke", "started": stores.utcnow(), "gridiq_root": str(GRIDIQ), "config": config}
    receipt.update(asyncio.run(run(outputs)))
    receipt["finished"] = stores.utcnow()
    receipt["summary"] = {s: sum(1 for r in receipt["results"] if r["status"] == s) for s in ("non-empty", "empty", "error")}
    stores.write_record("smoke", receipt)
    print(f"smoke: {receipt['summary']}", flush=True)
    return 0 if receipt["summary"]["error"] == 0 and receipt["summary"]["empty"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
