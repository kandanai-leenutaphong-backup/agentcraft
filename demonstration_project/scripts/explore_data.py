"""Reproducible development inspection; no detector training or held-out scoring."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import random
import resource
import signal
import sys
import time

from datasets import DATA, LOCK, PROJECT, check_file, contained, fingerprint, save_new


MISSION = PROJECT / "agentcraft_projects/overseer-self-optimization"


def label_names(columns, additional=()):
    return [name for name in columns if name in additional or "label" in name.lower() or
            name.lower() in {"attack", "attack_cat", "traffic_category", "category", "tactic", "tactics", "technique"}]


def sample_csv(path: Path, limit: int, sampling: str = "prefix", seed: int = 0):
    if limit < 1:
        raise ValueError("Sample limit must be positive")
    if sampling not in {"prefix", "reservoir"}:
        raise ValueError("Unknown sampling mode")
    generator = random.Random(seed)
    selected = []
    scanned = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        columns = next(reader)
        if not columns or len(columns) != len(set(columns)):
            raise ValueError("Missing or duplicate CSV columns")
        for ordinal, row in enumerate(reader, 1):
            scanned = ordinal
            if len(selected) < limit:
                selected.append((ordinal, row))
            elif sampling == "reservoir":
                slot = generator.randrange(ordinal)
                if slot < limit:
                    selected[slot] = (ordinal, row)
            if sampling == "prefix" and ordinal >= limit:
                break
    return columns, sorted(selected), scanned


def summarize_rows(columns, selected, limit, additional_label_columns=()):
    labels = {name: Counter() for name in label_names(columns, additional_label_columns)}
    missing = Counter()
    seen = set()
    rows = malformed = duplicates = 0
    for ordinal, row in selected:
        rows += 1
        if len(row) != len(columns):
            malformed += 1
        else:
            values = dict(zip(columns, row))
            for name, value in values.items():
                missing[name] += str(value).strip().lower() in {"", "null", "none", "nan"}
            for name in labels:
                labels[name][str(values[name])] += 1
            key = tuple(row)
            duplicates += key in seen
            seen.add(key)
    return {"columns": columns, "sample_rows": rows, "sample_limit": limit,
            "development_row_ordinals": [ordinal for ordinal, _row in selected],
            "malformed_sample_rows": malformed, "exact_duplicate_sample_rows": duplicates,
            "missing_sample_values": {name: count for name, count in sorted(missing.items()) if count},
            "label_candidates": {name: {"distinct_sample_values": len(counts),
                                        "top_values": sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:30]}
                                 for name, counts in labels.items()},
            "time_column_candidates": [name for name in columns if "time" in name.lower() or name.lower() == "ts"],
            "scope": "Selected rows are development evidence, not held-out evaluation or population estimates."}


def profile_csv(path: Path, limit: int, additional_label_columns=(), *, sampling="prefix", seed=0) -> dict:
    columns, selected, scanned = sample_csv(path, limit, sampling, seed)
    return {**summarize_rows(columns, selected, limit, additional_label_columns),
            "sampling": sampling, "seed": seed, "scanned_rows": scanned,
            "population_rows": scanned if sampling == "reservoir" else None}


def csv_survey(path, limit, seed, additional):
    generator = random.Random(seed)
    prefix, selected = [], []
    scanned = malformed = 0
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, strict=True)
        columns = next(reader)
        if not columns or len(columns) != len(set(columns)):
            raise ValueError("Missing or duplicate CSV columns")
        counts = {name: Counter() for name in label_names(columns, additional)}
        indices = {name: columns.index(name) for name in counts}
        for ordinal, row in enumerate(reader, 1):
            scanned = ordinal
            if len(row) != len(columns):
                malformed += 1
            else:
                for name, index in indices.items():
                    counts[name][row[index]] += 1
                    if len(counts[name]) > 1000:
                        raise ValueError("Label cardinality exceeds 1000; narrow the declared labels")
            if ordinal <= limit:
                prefix.append((ordinal, row))
                selected.append((ordinal, row))
            else:
                slot = generator.randrange(ordinal)
                if slot < limit:
                    selected[slot] = (ordinal, row)
    return columns, prefix, sorted(selected), {"rows": scanned, "malformed_rows": malformed,
            "label_counts": {name: dict(sorted(counter.items())) for name, counter in counts.items()}}


def parquet_survey(path, limit, seed, additional, batch_size):
    import pyarrow.compute as compute
    import pyarrow.parquet as parquet

    table = parquet.ParquetFile(path)
    columns = table.schema_arrow.names
    if len(columns) != len(set(columns)):
        raise ValueError("Duplicate Parquet columns")
    total = table.metadata.num_rows
    ordinals = set(random.Random(seed).sample(range(1, total + 1), min(limit, total)))
    counts = {name: Counter() for name in label_names(columns, additional)}
    prefix, selected = [], []
    offset = 0
    for batch in table.iter_batches(batch_size=batch_size, use_threads=False):
        for name in counts:
            for pair in compute.value_counts(batch.column(columns.index(name))).to_pylist():
                counts[name][str(pair["values"])] += pair["counts"]
            if len(counts[name]) > 1000:
                raise ValueError("Label cardinality exceeds 1000; narrow the declared labels")
        positions = [index for index in range(batch.num_rows)
                     if offset + index + 1 <= limit or offset + index + 1 in ordinals]
        selected_values = batch.take(positions).to_pylist() if positions else []
        for index, values in zip(positions, selected_values):
            ordinal = offset + index + 1
            row = [values[name] for name in columns]
            if ordinal <= limit:
                prefix.append((ordinal, row))
            if ordinal in ordinals:
                selected.append((ordinal, row))
        offset += batch.num_rows
    if offset != total:
        raise ValueError("Parquet metadata/stream row count mismatch")
    return columns, prefix, selected, {"rows": total, "malformed_rows": 0,
            "label_counts": {name: dict(sorted(counter.items())) for name, counter in counts.items()},
            "row_groups": table.metadata.num_row_groups,
            "arrow_schema": {field.name: str(field.type) for field in table.schema_arrow}}


def semantic_observations(columns, rows, additional):
    times, entities = {}, {}
    selected_labels = label_names(columns, additional)
    for index, name in enumerate(columns):
        values = [row[index] for _ordinal, row in rows if len(row) == len(columns)]
        lowered = name.lower()
        if "time" in lowered or "duration" in lowered or lowered == "ts":
            numeric = []
            for value in values:
                try:
                    number = float(value)
                    if math.isfinite(number):
                        numeric.append(number)
                except (TypeError, ValueError):
                    pass
            units = {}
            for unit, divisor in (("seconds", 1), ("milliseconds", 1000), ("microseconds", 1000000), ("nanoseconds", 1000000000)):
                converted = []
                for number in numeric:
                    try:
                        converted.append(datetime.fromtimestamp(number / divisor, timezone.utc).isoformat())
                    except (OverflowError, OSError, ValueError):
                        pass
                units[unit] = {"parseable": len(converted), "min_utc": min(converted, default=None),
                               "max_utc": max(converted, default=None),
                               "in_2000_through_2030": sum("2000" <= value[:4] <= "2030" for value in converted)}
            times[name] = {"sample_values": len(values), "finite_numeric": len(numeric),
                           "non_numeric_or_nonfinite": len(values) - len(numeric),
                           "numeric_min": min(numeric, default=None), "numeric_max": max(numeric, default=None),
                           "epoch_hypotheses": units,
                           "semantics": "unknown; plausible epoch range is not proof of units or event time; duration may be elapsed"}
            if lowered in {"datetime", "timestamp"}:
                parsed, deltas = [], []
                naive = 0
                for _ordinal, row in rows:
                    if len(row) != len(columns):
                        continue
                    try:
                        instant = datetime.fromisoformat(str(row[index]))
                        naive += instant.tzinfo is None
                        assumed = instant.replace(tzinfo=timezone.utc) if instant.tzinfo is None else instant.astimezone(timezone.utc)
                        parsed.append(assumed.isoformat())
                        if "ts" in columns:
                            delta = assumed.timestamp() - float(row[columns.index("ts")])
                            if math.isfinite(delta):
                                deltas.append(round(delta, 3))
                    except (ValueError, TypeError, OverflowError, OSError):
                        pass
                times[name]["iso8601"] = {"parseable": len(parsed), "timezone_naive": naive,
                    "min_assuming_naive_utc": min(parsed, default=None), "max_assuming_naive_utc": max(parsed, default=None),
                    "datetime_minus_ts_seconds": {"pairs": len(deltas), "min": min(deltas, default=None),
                                                  "max": max(deltas, default=None), "top_rounded_millisecond_counts": Counter(deltas).most_common(10)},
                    "assumption": "Naive datetime interpreted as UTC only to test agreement with ts seconds; actual timezone unknown"}
        if lowered in {"uid", "community_id", "originh", "responh", "id.orig_h", "id.resp_h", "src_ip", "dst_ip", "dest_ip", "srcip", "dstip", "src_ip_zeek", "dest_ip_zeek"} or "ip_addr" in lowered:
            distinct = set(map(str, values))
            entities[name] = {"distinct_sample_values": len(distinct), "sample_values": len(values),
                              "semantics": "name-based identifier candidate; asset identity and incident membership unknown"}
    joint = Counter(tuple(str(row[columns.index(name)]) for name in selected_labels)
                    for _ordinal, row in rows if len(row) == len(columns))
    return {"time_checks": times, "entity_checks": entities,
            "label_joint_sample_counts": [{"labels": dict(zip(selected_labels, key)), "rows": count}
                                          for key, count in sorted(joint.items())],
            "shortcut_columns": selected_labels + [name for name in columns if name.lower() in {"", "index", "unnamed: 0", "__index_level_0__"}],
            "shortcut_policy": "Exclude all annotation labels and export indexes from detector features; never infer causality from association."}


def selected_overlap(samples, exclude_labels=False):
    groups = {}
    split_sides = {}
    per_file = {}
    for sample in samples:
        names = sample["columns"]
        excluded = set(sample["labels"]) if exclude_labels else set()
        selected_names = sorted(name for name in names if name not in excluded)
        indices = [names.index(name) for name in selected_names]
        keys = Counter()
        for ordinal, row in sample["rows"]:
            if len(row) != len(names):
                continue
            values = tuple((type(row[index]).__name__, str(row[index])) for index in indices)
            key = (tuple(selected_names), values)
            keys[key] += 1
            split_sides.setdefault(key, set()).add("test" if ordinal % 5 == 0 else "train")
        per_file[sample["path"]] = {"selected_rows": sum(keys.values()), "distinct_rows": len(keys),
                                    "duplicate_excess_rows": sum(keys.values()) - len(keys)}
        for key, count in keys.items():
            groups.setdefault(key, {})[sample["path"]] = count
    pairs = {}
    cross_groups = 0
    for membership in groups.values():
        if len(membership) > 1:
            cross_groups += 1
        paths = sorted(membership)
        for left_index, left in enumerate(paths):
            for right in paths[left_index + 1:]:
                pair = pairs.setdefault((left, right), {"shared_distinct_rows": 0, "left_occurrences": 0, "right_occurrences": 0})
                pair["shared_distinct_rows"] += 1
                pair["left_occurrences"] += membership[left]
                pair["right_occurrences"] += membership[right]
    return {"scope": "Exact selected rows only: union of prefix and non-prefix membership, each ordinal once. No population overlap estimate.",
            "equality": "Sorted complete column names and typed parsed values; CSV strings stay lexical, Parquet native scalars; no cross-format coercion.",
            "includes_export_index": True, "includes_labels": not exclude_labels,
            "diagnostic_row_split": {"rule": "test iff 1-based source ordinal modulo 5 equals 0; train otherwise, across selected rows only",
                                     "distinct_groups_in_both": sum(len(sides) == 2 for sides in split_sides.values()),
                                     "status": "diagnostic only; no evaluation partition created or frozen"},
            "cross_file_distinct_groups": cross_groups, "per_file": per_file,
            "pairs": [{"left": left, "right": right, **value} for (left, right), value in sorted(pairs.items())]}


def evidence_path(path):
    root = MISSION / "results"
    absolute = path.absolute()
    if not absolute.is_relative_to(root):
        raise ValueError("Output must be beneath the project results directory")
    return contained(root, str(absolute.relative_to(root)))


def constitution_pin(expected):
    import yaml

    path = MISSION / "constitution/constitution.yaml"
    observed = fingerprint(path)["sha256"]
    document = yaml.safe_load(path.read_text())
    if not expected or observed != expected or document["status"] != "exploring" or document["revision"] != 7:
        raise ValueError("Expected exploring constitution revision 7 and matching --constitution-sha256")
    return {"revision": 7, "sha256": observed}


def observation_digest(observations):
    return hashlib.sha256(json.dumps(observations, sort_keys=True).encode()).hexdigest()


def read_evidence(path):
    result = json.loads(evidence_path(path).read_text())
    if result["status"] != "complete" or observation_digest(result["observations"]) != result["observations_sha256"]:
        raise ValueError("Evidence status or observation digest mismatch")
    return result


def evidence_summary(path):
    result = read_evidence(path)
    summaries = []
    for profile in result["observations"]["profiles"]:
        summaries.append({"path": profile["path"], "population": profile["population"],
                          "columns": profile["prefix"]["columns"],
                          "prefix_labels": profile["prefix"]["label_candidates"],
                          "nonprefix_labels": profile["nonprefix"]["label_candidates"],
                          "prefix_duplicate_excess": profile["prefix"]["exact_duplicate_sample_rows"],
                          "nonprefix_duplicate_excess": profile["nonprefix"]["exact_duplicate_sample_rows"],
                          "development_rows": len(profile["development_membership"]["row_ordinals"]),
                          "semantics": profile["semantics"]})
    return {"status": result["status"], "constitution": result["constitution"],
            "observations_sha256": result["observations_sha256"], "profiles": summaries,
            "selected_overlap": result["observations"]["selected_overlap"],
            "elapsed_seconds": result["elapsed_seconds"], "peak_rss_kib": result["peak_rss_kib"]}


def survey(args):
    output = evidence_path(args.output)
    if output.exists():
        raise ValueError("Refusing to overwrite an existing survey attempt")
    pin = constitution_pin(args.constitution_sha256)
    if not 1 <= args.rows <= 5000 or not 1 <= args.batch_size <= 16384 or not 1 <= args.seconds <= 1800:
        raise ValueError("Survey bounds: rows 1..5000, batch-size 1..16384, seconds 1..1800")
    result = {"schema_version": 2, "stage": "data-understanding", "evidence_class": "exploratory",
              "constitution": pin, "started_at": datetime.now(timezone.utc).isoformat(),
              "argv": sys.argv, "status": "running", "verdict": "inconclusive",
              "runtime": {"python": sys.version, "executable": sys.executable},
              "source_pins": {path.name: fingerprint(path)["sha256"] for path in
                              (Path(__file__), Path(__file__).with_name("datasets.py"), Path(__file__).with_name("datasets.sh"))},
              "file_elapsed_seconds": {}, "effective_host_effort": "unverified"}
    observations = {"source_lock_sha256": fingerprint(LOCK)["sha256"], "rows_per_sampling_mode": args.rows,
                    "seed": args.seed, "additional_label_columns": sorted(set(args.label_column)), "profiles": []}
    result["observations"] = observations
    started = time.monotonic()

    def timed_out(_signum, _frame):
        raise TimeoutError("Survey exceeded explicit runtime bound")

    previous = signal.signal(signal.SIGALRM, timed_out)
    signal.alarm(args.seconds)
    try:
        import pyarrow

        result["runtime"]["pyarrow"] = pyarrow.__version__
        document = json.loads(LOCK.read_text())
        entries = [document["derived"], *[entry for entry in document["files"] if Path(entry["path"]).suffix in {".csv", ".parquet"}]]
        if args.file:
            if set(args.file) - {entry["path"] for entry in entries}:
                raise ValueError("Requested file is outside the locked table allowlist")
            entries = [entry for entry in entries if entry["path"] in args.file]
        samples = []
        for entry in entries:
            file_started = time.monotonic()
            path = contained(DATA, entry["path"])
            before = path.stat()
            check_file(path, entry)
            if path.suffix == ".csv":
                columns, prefix, selected, population = csv_survey(path, args.rows, args.seed, args.label_column)
                method = "Python Random(seed) Algorithm R reservoir over all CSV records"
            else:
                columns, prefix, selected, population = parquet_survey(path, args.rows, args.seed, args.label_column, args.batch_size)
                method = "Python Random(seed).sample of metadata row ordinals; all Parquet batches traversed"
            after = path.stat()
            if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError("Source changed during survey")
            combined = sorted(dict(prefix + selected).items())
            profile = {"path": entry["path"], "source_sha256": entry["sha256"], "source_bytes": entry["bytes"],
                       "population": population, "sampling_method": method,
                       "prefix": summarize_rows(columns, prefix, args.rows, args.label_column),
                       "nonprefix": summarize_rows(columns, selected, args.rows, args.label_column),
                       "semantics": semantic_observations(columns, combined, args.label_column),
                       "development_membership": {"ordinal_base": 1, "header_counted": False,
                                                  "row_ordinals": [ordinal for ordinal, _row in combined],
                                                  "reason": "Selected labeled rows inspected by probe; development, never held-out"}}
            observations["profiles"].append(profile)
            samples.append({"path": entry["path"], "columns": columns, "rows": combined,
                            "labels": label_names(columns, args.label_column)})
            result["file_elapsed_seconds"][entry["path"]] = time.monotonic() - file_started
            print(json.dumps({"path": entry["path"], "population_rows": population["rows"], "development_rows": len(combined)}), flush=True)
        missing = set(args.label_column) - {name for sample in samples for name in sample["columns"]}
        if missing:
            raise ValueError(f"Requested label columns absent from all inputs: {sorted(missing)}")
        observations["selected_overlap"] = selected_overlap(samples)
        observations["selected_feature_overlap"] = selected_overlap(samples, exclude_labels=True)
        observations["disclosure_policy"] = "Population label aggregates inspected; no individual non-selected rows exposed. Previous inspected prefixes remain development. No held-out partition frozen."
        result["observations_sha256"] = observation_digest(observations)
        result["repeat_matches"] = None
        if args.compare:
            prior = read_evidence(args.compare)
            result["repeat_matches"] = prior["observations_sha256"] == result["observations_sha256"]
            result["comparison"] = {"path": str(args.compare), "sha256": fingerprint(args.compare)["sha256"]}
            if not result["repeat_matches"]:
                raise ValueError("Repeated observations differ")
        constitution_pin(args.constitution_sha256)
        if fingerprint(LOCK)["sha256"] != observations["source_lock_sha256"]:
            raise ValueError("Source lock changed during survey")
        result["status"] = "complete"
    except Exception as error:
        result["status"] = "failed"
        result["error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
    result["elapsed_seconds"] = time.monotonic() - started
    result["finished_at"] = datetime.now(timezone.utc).isoformat()
    result["peak_rss_kib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    save_new(output, result)
    if json.loads(output.read_text()) != json.loads(json.dumps(result)):
        raise ValueError("Saved survey read-back mismatch")
    print(json.dumps({"status": result["status"], "output": str(output), "sha256": fingerprint(output)["sha256"],
                      "elapsed_seconds": result["elapsed_seconds"], "observations_sha256": result.get("observations_sha256"),
                      "repeat_matches": result.get("repeat_matches"), "error": result.get("error")}, indent=2))
    return 0 if result["status"] == "complete" else 2


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=2000)
    parser.add_argument("--label-column", action="append", default=[])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--readback", type=Path)
    parser.add_argument("--compare", type=Path)
    parser.add_argument("--survey", action="store_true")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--constitution-sha256")
    parser.add_argument("--file", action="append", default=[])
    args = parser.parse_args()
    if args.readback:
        print(json.dumps(evidence_summary(args.readback), indent=2))
        return 0
    if not args.output:
        parser.error("--output is required unless --readback is used")
    if args.survey:
        return survey(args)
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
    sys.exit(main())