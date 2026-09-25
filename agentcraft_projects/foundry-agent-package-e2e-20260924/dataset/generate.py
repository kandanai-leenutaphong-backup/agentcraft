"""Deterministic generator for the parcel-quote dataset. Rerun-safe: identical bytes or refusal.

    python3 -B agentcraft_projects/foundry-agent-package-e2e-20260924/dataset/generate.py          # write if absent
    python3 -B agentcraft_projects/foundry-agent-package-e2e-20260924/dataset/generate.py --check  # byte replay
"""

import hashlib
import json
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import reference  # noqa: E402

REVISION = "parcel-quote-v1"
SEED = "agentcraft-pkg-e2e-parcel-v1"
# (split, standard_ok, express_ok, zone_unknown, weight_limit)
COMPOSITION = (("train", 14, 10, 3, 3), ("validation", 7, 5, 2, 1), ("verification", 3, 3, 2, 1))
TEMPLATES = (
    "Quote a {service} parcel weighing {grams} g to zone {zone}.",
    "How much to ship {kilograms} kg {service} to {zone}?",
    "{Service} delivery, {grams} grams, destination zone {zone}: what is the price?",
    "Price this {service} shipment of {kilograms} kg for zone {zone}.",
    "I need a {service} quote: {zone}, {grams}g.",
)
FILES = {split: f"{split}.jsonl" for split, *_ in COMPOSITION}


def kilograms(grams):
    return f"{grams // 1000}.{grams % 1000:03d}".rstrip("0").rstrip(".")


def build():
    rng = random.Random(SEED)
    known = sorted(reference.ZONES)
    seen = set()
    splits = {}
    for split, standard, express, zone_unknown, weight_limit in COMPOSITION:
        plan = ([("ok", False)] * standard + [("ok", True)] * express
                + [("zone", rng.random() < 0.5)] * zone_unknown + [("weight", rng.random() < 0.5)] * weight_limit)
        rows = []
        for case, is_express in plan:
            while True:
                if case == "zone":
                    zone, grams = rng.choice(reference.UNKNOWN_ZONES), rng.randrange(200, 25001)
                elif case == "weight":
                    zone, grams = rng.choice(known), rng.randrange(reference.MAX_WEIGHT_GRAMS + 1, 45001)
                else:
                    zone, grams = rng.choice(known), rng.randrange(120, reference.MAX_WEIGHT_GRAMS + 1)
                key = (zone, grams, is_express)
                if key not in seen:
                    seen.add(key)
                    break
            service = "express" if is_express else "standard"
            query = rng.choice(TEMPLATES).format(service=service, Service=service.capitalize(), grams=grams,
                                                 kilograms=kilograms(grams), zone=zone)
            rows.append({"query": query, "ground_truth": reference.expected_answer(zone, grams, is_express),
                         "case": {"ok": "ok", "zone": "error-zone-unknown", "weight": "error-weight-limit"}[case],
                         "zone": zone, "weight_grams": grams, "express": is_express,
                         "expected_tools": reference.expected_tools(zone)})
        rng.shuffle(rows)
        splits[split] = [dict(id=f"pq-{split}-{index:03d}", split=split, **row) for index, row in enumerate(rows, 1)]
    queries = [row["query"] for rows in splits.values() for row in rows]
    if len(queries) != len(set(queries)):
        raise RuntimeError("query collision across or within splits")
    return {split: "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
            for split, rows in splits.items()}, splits


def journeys(rows):
    first = lambda test: next(row["id"] for row in rows if test(row))  # noqa: E731
    return {"S3-nonstream-ok": first(lambda row: row["case"] == "ok" and not row["express"]),
            "S3-stream-ok": first(lambda row: row["case"] == "ok" and row["express"]),
            "S3-deliberate-failure": first(lambda row: row["case"] == "error-zone-unknown"),
            "S3-tool-error-after-lookup": first(lambda row: row["case"] == "error-weight-limit")}


def manifest(payloads, splits):
    digest = lambda data: hashlib.sha256(data).hexdigest()  # noqa: E731
    files = {}
    for split, data in payloads.items():
        rows = splits[split]
        files[split] = {"path": f"dataset/{FILES[split]}", "sha256": digest(data), "bytes": len(data), "rows": len(rows),
                        "cases": {case: sum(row["case"] == case for row in rows) for case in sorted({row["case"] for row in rows})},
                        "express": sum(row["express"] for row in rows)}
    return {
        "revision": REVISION,
        "seed": SEED,
        "source": "specs/20260924_FOUNDRY_AGENT_PACKAGE_E2E.md",
        "rights": "Synthetic, generated locally by this repository; no external or personal data.",
        "generator": {"path": "dataset/generate.py", "sha256": digest((HERE / "generate.py").read_bytes())},
        "oracle": {"path": "dataset/reference.py", "sha256": digest((HERE / "reference.py").read_bytes())},
        "answer_format": "TOTAL_CENTS=<integer> or ERROR=<E_CODE>; exact match after surrounding whitespace strip",
        "files": files,
        "membership": {
            "train": "Optimizer train input (query, ground_truth only).",
            "validation": "Optimizer-visible native validation input and independent candidate selection; development data, never called held out.",
            "verification": "Never sent to optimizer or eval-definition authoring; S3/S6 journeys and final baseline-vs-promoted report only.",
        },
        "journeys": journeys(splits["verification"]),
        "held_out": "verification split is evaluator-controlled; no tuning or reselection on its outcomes",
    }


def main(argv):
    payloads, splits = build()
    documents = {FILES[split]: data for split, data in payloads.items()}
    documents["manifest.json"] = (json.dumps(manifest(payloads, splits), indent=2, sort_keys=True) + "\n").encode()
    mismatched = [name for name, data in documents.items()
                  if (HERE / name).exists() and (HERE / name).read_bytes() != data]
    if "--check" in argv:
        missing = [name for name in documents if not (HERE / name).exists()]
        print(json.dumps({"check": not mismatched and not missing, "mismatched": mismatched, "missing": missing}))
        return 0 if not mismatched and not missing else 1
    if mismatched:
        print(json.dumps({"refused": "existing bytes differ; bump REVISION instead of overwriting", "files": mismatched}))
        return 1
    for name, data in documents.items():
        if not (HERE / name).exists():
            (HERE / name).write_bytes(data)
    print(json.dumps({name: hashlib.sha256(data).hexdigest() for name, data in documents.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
