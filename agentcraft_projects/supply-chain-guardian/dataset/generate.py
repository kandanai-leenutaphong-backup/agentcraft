#!/usr/bin/env python3
"""Deterministic synthetic dataset generator for supply-chain-guardian.

Produces a mocked Fabric IQ ontology (Supplier -> Shipment -> Raw Material -> Plant ->
Production Order -> SKU -> Customer) and a fixed set of disruption scenarios, each with a
pre-computed blast radius (ground truth for evidence-grounded-recommendation checks). A mocked
Foundry IQ policy library stands in for enterprise knowledge if the real Azure AI Search index
lacks supplier/procurement content (per constitution data_understanding). All identifiers are
fictional. No real supplier, customer or procurement data is used.

Usage:
    python3 generate.py                 # writes ontology.json, scenarios.json, manifest.json
    python3 generate.py --check         # regenerates in-memory and verifies byte-for-byte
      match against the committed files (deterministic replay check)
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# --- Mocked Fabric IQ ontology -------------------------------------------------------------

SUPPLIERS = [
    {"id": "SUP-01", "name": "Supplier A", "region": "Southeast Asia", "approved_alternate": False},
    {"id": "SUP-02", "name": "Supplier B", "region": "South Asia", "approved_alternate": True},
    {"id": "SUP-03", "name": "Supplier C", "region": "East Asia", "approved_alternate": True},
]

RAW_MATERIALS = [
    {"id": "RM-14", "name": "Raw Material RM-14", "supplier_id": "SUP-01"},
    {"id": "RM-22", "name": "Raw Material RM-22", "supplier_id": "SUP-02"},
    {"id": "RM-31", "name": "Raw Material RM-31", "supplier_id": "SUP-03"},
]

SHIPMENTS = [
    {"id": "S102", "material_id": "RM-14", "supplier_id": "SUP-01", "status": "delayed", "eta_days_late": 9},
    {"id": "S211", "material_id": "RM-22", "supplier_id": "SUP-02", "status": "on_time", "eta_days_late": 0},
    {"id": "S307", "material_id": "RM-31", "supplier_id": "SUP-03", "status": "delayed", "eta_days_late": 3},
]

PLANTS = [
    {"id": "PLANT-BKK", "name": "Bangkok Plant", "material_ids": ["RM-14"], "inventory_days_on_hand": 2},
    {"id": "PLANT-PNH", "name": "Penang Plant", "material_ids": ["RM-14", "RM-22"], "inventory_days_on_hand": 6},
    {"id": "PLANT-SGN", "name": "Saigon Plant", "material_ids": ["RM-31"], "inventory_days_on_hand": 11},
]

PRODUCTION_ORDERS = [
    {"id": "PO-4001", "plant_id": "PLANT-BKK", "sku_id": "SKU-A"},
    {"id": "PO-4002", "plant_id": "PLANT-BKK", "sku_id": "SKU-B"},
    {"id": "PO-4003", "plant_id": "PLANT-PNH", "sku_id": "SKU-A"},
    {"id": "PO-4004", "plant_id": "PLANT-SGN", "sku_id": "SKU-C"},
]

SKUS = [
    {"id": "SKU-A", "name": "Widget A", "customer_ids": ["CUST-01", "CUST-02"]},
    {"id": "SKU-B", "name": "Widget B", "customer_ids": ["CUST-03"]},
    {"id": "SKU-C", "name": "Widget C", "customer_ids": ["CUST-04"]},
]

CUSTOMERS = [
    {"id": "CUST-01", "name": "Customer One", "tier": "strategic"},
    {"id": "CUST-02", "name": "Customer Two", "tier": "standard"},
    {"id": "CUST-03", "name": "Customer Three", "tier": "strategic"},
    {"id": "CUST-04", "name": "Customer Four", "tier": "standard"},
]

# --- Mocked Foundry IQ policy library (stand-in if the real index lacks content) -----------

FOUNDRY_POLICY_LIBRARY = [
    {
        "id": "POLICY-ALT-SUPPLIER",
        "title": "Approved Alternate Suppliers",
        "summary": (
            "Supplier B (SUP-02) and Supplier C (SUP-03) are pre-approved alternates for "
            "raw-material shortfalls; Supplier A (SUP-01) has no approved alternate on file."
        ),
    },
    {
        "id": "POLICY-EXPEDITE",
        "title": "Procurement Expedite SOP",
        "summary": (
            "Expediting from an approved alternate supplier requires Production Planning "
            "sign-off when inventory-days-on-hand at the affected plant is below 5 days."
        ),
    },
    {
        "id": "POLICY-CONTINUITY",
        "title": "Business Continuity Procedure",
        "summary": (
            "Strategic-tier customer impact must be flagged to account management within one "
            "business day of a confirmed production-order risk."
        ),
    },
]

# --- Mocked Work IQ organizational context (stand-in if live Work IQ probe is unavailable) --

WORK_IQ_CONTEXT = {
    "S102": {
        "responsible_stakeholders": ["Production Planning Lead", "Procurement Manager"],
        "recent_notes": [
            "Procurement flagged Supplier A logistics risk in last week's ops review.",
        ],
    },
}

# --- Mocked Web IQ external signal (stand-in if live Web IQ probe is unavailable) -----------

WEB_IQ_SIGNAL = {
    "S102": {
        "headline": "Regional port congestion reported to extend into next week",
        "implication": "Underlying logistics disruption behind shipment S102 may continue.",
    },
}


def _blast_radius(shipment_id: str) -> dict:
    shipment = next(s for s in SHIPMENTS if s["id"] == shipment_id)
    material_id = shipment["material_id"]
    affected_plants = [p for p in PLANTS if material_id in p["material_ids"]]
    plant_ids = {p["id"] for p in affected_plants}
    affected_orders = [po for po in PRODUCTION_ORDERS if po["plant_id"] in plant_ids]
    sku_ids = {po["sku_id"] for po in affected_orders}
    affected_skus = [s for s in SKUS if s["id"] in sku_ids]
    customer_ids = {c for s in affected_skus for c in s["customer_ids"]}
    affected_customers = [c for c in CUSTOMERS if c["id"] in customer_ids]
    return {
        "shipment_id": shipment_id,
        "material_id": material_id,
        "affected_plants": [p["id"] for p in affected_plants],
        "affected_production_orders": [po["id"] for po in affected_orders],
        "affected_skus": [s["id"] for s in affected_skus],
        "affected_customers": [c["id"] for c in affected_customers],
        "strategic_customer_impact": any(c["tier"] == "strategic" for c in affected_customers),
        "min_inventory_days_on_hand": min((p["inventory_days_on_hand"] for p in affected_plants), default=None),
    }


def build_ontology() -> dict:
    return {
        "suppliers": SUPPLIERS,
        "raw_materials": RAW_MATERIALS,
        "shipments": SHIPMENTS,
        "plants": PLANTS,
        "production_orders": PRODUCTION_ORDERS,
        "skus": SKUS,
        "customers": CUSTOMERS,
        "mocked": True,
        "source": "Fabric IQ workspace has no populated data yet; authored mock stands in.",
    }


def build_scenarios() -> list:
    scenarios = []

    # Scenario 1: clear single-supplier disruption, strategic-customer impact, low inventory.
    br = _blast_radius("S102")
    scenarios.append({
        "id": "scenario-01-clear-disruption",
        "kind": "clear_disruption",
        "trigger": "Shipment S102 delayed 9 days (Supplier A, no approved alternate).",
        "blast_radius": br,
        "foundry_iq_evidence": ["POLICY-ALT-SUPPLIER", "POLICY-EXPEDITE", "POLICY-CONTINUITY"],
        "work_iq_evidence": WORK_IQ_CONTEXT.get("S102"),
        "web_iq_evidence": WEB_IQ_SIGNAL.get("S102"),
        "expected_recommendation_mentions": ["SUP-02", "SUP-03", "PLANT-BKK", "Production Planning"],
        "expected_requires_approval": True,
    })

    # Scenario 2: cascading multi-plant disruption (RM-14 also feeds Penang Plant).
    scenarios.append({
        "id": "scenario-02-cascading-disruption",
        "kind": "cascading_disruption",
        "trigger": "Same shipment S102 delay, evaluated for cross-plant cascade via shared material RM-14.",
        "blast_radius": _blast_radius("S102"),
        "foundry_iq_evidence": ["POLICY-ALT-SUPPLIER", "POLICY-EXPEDITE"],
        "work_iq_evidence": WORK_IQ_CONTEXT.get("S102"),
        "web_iq_evidence": WEB_IQ_SIGNAL.get("S102"),
        "expected_recommendation_mentions": ["PLANT-BKK", "PLANT-PNH"],
        "expected_requires_approval": True,
    })

    # Scenario 3: minor delay, sufficient inventory buffer, no action needed.
    scenarios.append({
        "id": "scenario-03-no-action-needed",
        "kind": "no_action_needed",
        "trigger": "Shipment S307 delayed 3 days (Supplier C); Saigon Plant has 11 days inventory on hand.",
        "blast_radius": _blast_radius("S307"),
        "foundry_iq_evidence": ["POLICY-EXPEDITE"],
        "work_iq_evidence": None,
        "web_iq_evidence": None,
        "expected_recommendation_mentions": [],
        "expected_requires_approval": False,
    })

    # Scenario 4: on-time shipment, ambiguous/insufficient evidence probe (negative control).
    scenarios.append({
        "id": "scenario-04-insufficient-evidence",
        "kind": "insufficient_evidence",
        "trigger": "Shipment S211 on time; no disruption signal present.",
        "blast_radius": _blast_radius("S211"),
        "foundry_iq_evidence": [],
        "work_iq_evidence": None,
        "web_iq_evidence": None,
        "expected_recommendation_mentions": [],
        "expected_requires_approval": False,
    })

    return scenarios


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n", encoding="utf-8")


def generate() -> None:
    write_json(ROOT / "ontology.json", build_ontology())
    write_json(ROOT / "scenarios.json", build_scenarios())
    write_json(ROOT / "foundry_iq_policy_library.mock.json", FOUNDRY_POLICY_LIBRARY)

    manifest = {
        "mocked_sources": ["Fabric IQ (ontology)", "Foundry IQ policy library (fallback only)",
                            "Work IQ context (fallback only)", "Web IQ signal (fallback only)"],
        "note": "Work IQ / Web IQ / Foundry IQ fixtures here are fallbacks; live probes take precedence when available.",
        "files": {
            "ontology": {"path": "dataset/ontology.json", "sha256": _sha256(ROOT / "ontology.json")},
            "scenarios": {"path": "dataset/scenarios.json", "sha256": _sha256(ROOT / "scenarios.json"),
                          "count": len(build_scenarios())},
            "foundry_iq_policy_library_mock": {
                "path": "dataset/foundry_iq_policy_library.mock.json",
                "sha256": _sha256(ROOT / "foundry_iq_policy_library.mock.json"),
            },
        },
    }
    write_json(ROOT / "manifest.json", manifest)


def check() -> bool:
    before = {p.name: p.read_bytes() for p in ROOT.glob("*.json")}
    generate()
    after = {p.name: p.read_bytes() for p in ROOT.glob("*.json")}
    ok = before == after
    print(json.dumps({"deterministic_replay_match": ok}))
    return ok


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(0 if check() else 1)
    generate()
    print("wrote ontology.json, scenarios.json, foundry_iq_policy_library.mock.json, manifest.json")
