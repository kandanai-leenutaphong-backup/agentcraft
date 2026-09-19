"""Reproducible development-sample CSV inspection; no detector training or held-out scoring."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time

from datasets import DATA, LOCK, PROJECT, check_file, contained, fingerprint, save_new


def profile_csv(path: Path, limit: int, additional_label_columns=()) -> dict:
    if limit < 1:
        raise ValueError("Sample limit must be positive")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        columns = next(reader)
        if not columns or len(columns) != len(set(columns)):
            raise ValueError("Missing or duplicate CSV columns")
        label_columns = [name for name in columns if name in additional_label_columns or
                         "label" in name.lower() or name.lower() in {
                             "attack", "attack_cat", "traffic_category", "category", "tactic", "tactics", "technique"}]
        labels = {name: Counter() for name in label_columns}
        missing = Counter()
        seen = set()
        rows = malformed = duplicates = 0
        for row in reader:
            rows += 1
            if len(row) != len(columns):
                malformed += 1
            else:
                values = dict(zip(columns, row))
                for name, value in values.items():
                    missing[name] += value.strip().lower() in {"", "null", "none", "nan"}
                for name in label_columns:
                    labels[name][values[name]] += 1
                digest = hashlib.sha256(json.dumps(row).encode()).hexdigest()
                duplicates += digest in seen
                seen.add(digest)
            if rows >= limit:
                break
    return {"columns": columns, "sample_rows": rows, "sample_limit": limit,
            "malformed_sample_rows": malformed, "exact_duplicate_sample_rows": duplicates,
            "missing_sample_values": {name: count for name, count in sorted(missing.items()) if count},
            "label_candidates": {name: {"distinct_sample_values": len(counts),
                                        "top_values": sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:30]}
                                 for name, counts in labels.items()},
            "time_column_candidates": [name for name in columns if "time" in name.lower() or name.lower() == "ts"],
            "scope": "First N rows in file order are development evidence, not a random sample or held-out evaluation."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--label-column", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    evidence_root = PROJECT / "agentcraft_projects/overseer-self-optimization/results"
    output = args.output.absolute()
    if not output.is_relative_to(evidence_root):
        parser.error("Output must be beneath the project results directory")
    output = contained(evidence_root, str(output.relative_to(evidence_root)))
    started = time.monotonic()
    document = json.loads(LOCK.read_text())
    entries = [document["derived"], *[entry for entry in document["files"] if entry["path"].endswith(".csv")]]
    profiles = []
    for entry in entries:
        path = contained(DATA, entry["path"])
        check_file(path, entry)
        profiles.append({"path": entry["path"], "source_sha256": entry["sha256"],
                         **profile_csv(path, args.rows, args.label_column)})
    missing_columns = set(args.label_column) - {name for profile in profiles for name in profile["columns"]}
    if missing_columns:
        raise ValueError(f"Requested label columns absent from all inputs: {sorted(missing_columns)}")
    observations = {"source_lock_sha256": fingerprint(LOCK)["sha256"],
                    "additional_label_columns": sorted(set(args.label_column)), "profiles": profiles}
    identity = hashlib.sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest()
    matches = None
    if args.compare:
        matches = json.loads(args.compare.read_text())["observations_sha256"] == identity
        if not matches:
            raise ValueError("Repeated observations differ")
    result = {"schema_version": 1, "stage": "data-understanding", "evidence_class": "exploratory",
              "recorded_at": datetime.now(timezone.utc).isoformat(), "observations_sha256": identity,
              "script_sha256": fingerprint(Path(__file__))["sha256"],
              "elapsed_seconds": time.monotonic() - started, "repeat_matches": matches,
              **observations,
              "limitations": ["CSV prefix samples only; no population counts or trained detector.",
                              "Label and time column candidates are name-based leads, not established semantics.",
                              "Parquet contents and cross-file overlap are not inspected by this probe."]}
    save_new(output, result)
    print(json.dumps({"status": "saved", "output": str(output), "csv_files": len(profiles),
                      "observations_sha256": identity, "repeat_matches": matches}, indent=2))


if __name__ == "__main__":
    main()