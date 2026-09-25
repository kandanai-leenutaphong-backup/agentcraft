"""Frozen exact-answer evaluator. `grade` is registered verbatim as the native Foundry code evaluator
and is also the local independent scorer; `score` aggregates rows. No imports inside `grade`."""

import re


def grade(sample, item):
    if not isinstance(item, dict):
        raise ValueError("item must be an object")
    ground_truth = item.get("ground_truth")
    if not isinstance(ground_truth, str) or not (ground_truth.startswith("TOTAL_CENTS=") or ground_truth.startswith("ERROR=E_")):
        raise ValueError("invalid ground truth")
    outputs = []
    for key in ("response", "sample.output_text"):
        if key in item:
            outputs.append(item[key])
    if "sample" in item:
        if not isinstance(item["sample"], dict) or "output_text" not in item["sample"]:
            raise ValueError("malformed nested sample")
        outputs.append(item["sample"]["output_text"])
    if sample is not None:
        if not isinstance(sample, dict):
            raise ValueError("sample must be an object or null")
        if "output_text" in sample:
            outputs.append(sample["output_text"])
    if not outputs:
        raise ValueError("target output missing")
    response = outputs[0]
    if any(type(value) is not type(response) or value != response for value in outputs[1:]):
        raise ValueError("conflicting target outputs")
    return float(isinstance(response, str) and response.strip() == ground_truth)


ANSWER = re.compile(r"(?:TOTAL_CENTS=\d+|ERROR=E_[A-Z_]+)")


def score(rows):
    """rows: [{"id", "ground_truth", "output_text"}]. Missing/invalid outputs stay in every denominator."""
    if not rows:
        raise ValueError("nonempty rows required")
    outcomes = []
    for row in rows:
        text = row.get("output_text")
        stripped = text.strip() if isinstance(text, str) else None
        valid = stripped is not None and ANSWER.fullmatch(stripped) is not None
        correct = grade(None, {"ground_truth": row["ground_truth"], "response": text if isinstance(text, str) else ""}) == 1.0
        kind = "error" if row["ground_truth"].startswith("ERROR=") else "ok"
        outcomes.append({"id": row["id"], "kind": kind, "valid_format": valid, "correct": correct})
    n = len(outcomes)
    by_kind = {kind: [item for item in outcomes if item["kind"] == kind] for kind in ("ok", "error")}
    return {"n": n, "accuracy": sum(item["correct"] for item in outcomes) / n,
            "invalid_format_rate": sum(not item["valid_format"] for item in outcomes) / n,
            "accuracy_by_kind": {kind: (sum(item["correct"] for item in items) / len(items) if items else None)
                                 for kind, items in by_kind.items()},
            "support_by_kind": {kind: len(items) for kind, items in by_kind.items()},
            "rows": outcomes}


def grade_source():
    """Exact bytes registered with the native evaluator: the `grade` function only."""
    import inspect

    return inspect.getsource(grade)
