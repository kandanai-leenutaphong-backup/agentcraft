"""Offline dataset validation and independent structured proof scoring."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def rows():
    content = (ROOT / "dataset.jsonl").read_bytes()
    dataset = [json.loads(line) for line in content.splitlines()]
    assert len(dataset) == 3
    assert len({row["query"] for row in dataset}) == 3
    assert all(set(row) == {"query"} and re.fullmatch(r"[0-9a-f]{32}", row["query"])
               for row in dataset)
    return dataset, hashlib.sha256(content).hexdigest()


def oracle(query, output_text, pins):
    try:
        if (set(pins) != {"source_sha256", "config_sha256", "agent_name", "agent_version"}
                or not all(isinstance(value, str) and value for value in pins.values())):
            return False
        proof = json.loads(output_text)
        expected = {"marker": "foundry-custom-script-v1", "nonce": query,
                    "sha256": hashlib.sha256(
                        ("foundry-custom-script-v1:" + query).encode()).hexdigest()}
        if proof["nonce"] != query or any(proof[key] != value for key, value in pins.items()):
            return False
        events = proof["tool_events"]
        groups = [[event["data"] for event in events if event["kind"] == kind]
                  for kind in ("tool.call.ready", "tool.started", "tool.result")]
        if any(len(group) != 1 for group in groups):
            return False
        ready, started, result = [group[0] for group in groups]
        return bool(ready.get("call_id")) and (
            ready.get("name") == started.get("name") == "nonce_digest"
            and ready.get("arguments") == {"nonce": query}
            and ready["call_id"] == started.get("call_id") == result.get("call_id")
            and result.get("result") == expected)
    except (ValueError, KeyError, TypeError):
        return False


def validate():
    dataset, digest = rows()
    query = dataset[0]["query"]
    pins = {"source_sha256": "synthetic-source", "config_sha256": "synthetic-config",
            "agent_name": "synthetic-agent", "agent_version": "synthetic-version"}
    result = {"marker": "foundry-custom-script-v1", "nonce": query,
              "sha256": hashlib.sha256(("foundry-custom-script-v1:" + query).encode()).hexdigest()}
    proof = dict(pins, nonce=query, tool_events=[
        {"kind": "tool.call.ready", "data": {"call_id": "offline", "name": "nonce_digest",
                                             "arguments": {"nonce": query}}},
        {"kind": "tool.started", "data": {"call_id": "offline", "name": "nonce_digest"}},
        {"kind": "tool.result", "data": {"call_id": "offline", "result": result}},
    ])
    assert oracle(query, json.dumps(proof), pins)
    incorrect = copy.deepcopy(proof)
    incorrect["tool_events"][2]["data"]["result"]["sha256"] = "0" * 64
    assert not oracle(query, json.dumps(incorrect), pins)
    assert not oracle(query, json.dumps({"answer": "tool succeeded"}), pins)
    assert not oracle(query, json.dumps(proof), dict(pins, agent_version="wrong"))
    assert not oracle(query, json.dumps(proof), {})
    print(json.dumps({"status": "offline_pass", "rows": len(dataset), "sha256": digest,
                      "synthetic_positive": 1, "synthetic_negatives_rejected": 4}))


def score(items_path, pins_path):
    dataset, digest = rows()
    pins = json.loads(Path(pins_path).read_text())
    items = json.loads(Path(items_path).read_text())
    if not isinstance(items, list) or len(items) != 3:
        raise ValueError("exactly three output items required; missing rows are not passes")
    expected_queries = {row["query"] for row in dataset}
    observed_queries = [item.get("datasource_item", {}).get("query") for item in items]
    if set(observed_queries) != expected_queries or len(set(observed_queries)) != 3:
        raise ValueError("duplicate, missing or foreign query")
    results = []
    for item in items:
        data = item["datasource_item"]
        passed = oracle(data["query"], data.get("sample.output_text", ""), pins)
        results.append({"query": data["query"], "proof_passed": passed})
    print(json.dumps({"dataset_sha256": digest, "rows": results,
                      "proof_passed": sum(row["proof_passed"] for row in results),
                      "total": 3, "coherence": "review separately in service results"}))
    return all(row["proof_passed"] for row in results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["validate", "dry-run", "score"])
    parser.add_argument("--items")
    parser.add_argument("--pins")
    arguments = parser.parse_args()
    if arguments.action == "score":
        if not arguments.items or not arguments.pins:
            parser.error("score requires --items and --pins")
        raise SystemExit(0 if score(arguments.items, arguments.pins) else 2)
    validate()
    if arguments.action == "dry-run":
        print(json.dumps({"network": False, "max_dataset_uploads": 1,
                          "max_eval_definitions": 1, "max_run_submissions": 1,
                          "rows": 3, "live_implemented": False}))