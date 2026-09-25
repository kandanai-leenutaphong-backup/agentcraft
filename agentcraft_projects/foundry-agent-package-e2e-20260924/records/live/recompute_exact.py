"""Local exact recompute of a retained `evaluate` receipt: frozen `exact_answer.score` over decoded
`sample.output_text`, compared row by row with the native `exact` column. Offline; reads retained bytes only.

Usage (repository root): python3 -B agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/recompute_exact.py \
    <series>/<stamp>-evaluate.json <split> <out-name>
Writes records/live/<series>/<out-name>.json; exits 1 when local and native exact disagree on any row.
"""

import hashlib
import json
from pathlib import Path
import sys

LIVE = Path(__file__).resolve().parent
PROJECT = LIVE.parents[1]
sys.path.insert(0, str(PROJECT / "evaluator"))
import exact_answer  # noqa: E402
import graded_answer  # noqa: E402


def main(receipt: str, split: str, out_name: str) -> int:
    if not out_name.replace("-", "").isalnum() or split not in ("validation", "verification"):
        raise SystemExit("out-name must be [A-Za-z0-9-]+ and split validation|verification")
    path = LIVE / receipt
    if not path.resolve().is_relative_to(LIVE):
        raise SystemExit("receipt must lie under records/live")
    result = json.loads(path.read_text())["result"]
    split_path = PROJECT / f"dataset/{split}.jsonl"
    dataset = [json.loads(line) for line in split_path.read_text().splitlines() if line.strip()]
    by_query = {row["query"]: row for row in dataset}
    rows, native = [], {}
    for item in result["rows"]:
        source = item["datasource_item"]
        row = by_query[source["query"]]
        rows.append({"id": row["id"], "ground_truth": row["ground_truth"], "output_text": source.get("sample.output_text")})
        exact = [entry for entry in item["results"] if entry["name"] == "exact"]
        native[row["id"]] = exact[0]["score"] if exact else None
    if sorted(native) != sorted(row["id"] for row in dataset):
        raise SystemExit("eval rows do not cover the split exactly once")
    local = exact_answer.score(rows)
    disagree = [row["id"] for row in local["rows"] if float(row["correct"]) != native[row["id"]]]
    # Local only: the eval criteria carry no native graded column.
    graded = {row["id"]: graded_answer.grade({"output_text": row["output_text"]}, {"ground_truth": row["ground_truth"]})
              for row in rows}
    record = {"eval_id": result["eval_id"], "run_id": result["run_id"], "receipt": receipt,
              "receipt_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "split": split,
              "split_sha256": hashlib.sha256(split_path.read_bytes()).hexdigest(),
              "agent_version": result["rows"][0]["datasource_item"].get("agent_version"),
              "local_exact": local, "native_exact": native, "disagreements": disagree,
              "local_graded": graded, "local_graded_mean": round(sum(graded.values()) / len(graded), 6),
              "equal": not disagree}
    out = path.parent / f"{out_name}.json"
    out.write_text(json.dumps(record, indent=1, sort_keys=True) + "\n")
    print(json.dumps({"out": str(out.relative_to(LIVE)), "accuracy": local["accuracy"],
                      "invalid_format_rate": local["invalid_format_rate"],
                      "local_graded_mean": record["local_graded_mean"], "equal": record["equal"]}))
    return 0 if record["equal"] else 1


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:4]))
