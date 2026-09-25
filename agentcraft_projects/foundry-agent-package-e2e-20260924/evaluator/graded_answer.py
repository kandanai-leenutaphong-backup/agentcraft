"""Graded answer-similarity evaluator: optimization search signal only, never the acceptance metric.

`grade` is registered verbatim as a native Foundry code evaluator (no imports inside it). It returns 1.0 only for
the exact stripped answer and otherwise 0.9 x the mean of case-insensitive and case-sensitive LCS Dice similarity
to the ground-truth answer line, so partial progress toward the reference line scores strictly between 0 and 0.9.
`evaluator/exact_answer.py` stays the frozen acceptance metric.
"""


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
    if not isinstance(response, str):
        return 0.0
    answer = response.strip()[:4000]
    if answer == ground_truth:
        return 1.0
    if not answer:
        return 0.0

    def dice(left, right):
        previous = [0] * (len(right) + 1)
        for char in left:
            current = [0]
            for index, other in enumerate(right):
                current.append(previous[index] + 1 if char == other else max(previous[index + 1], current[index]))
            previous = current
        return 2.0 * previous[-1] / (len(left) + len(right))

    similarity = (dice(answer.lower(), ground_truth.lower()) + dice(answer, ground_truth)) / 2.0
    return round(0.9 * similarity, 6)


def grade_source():
    """Exact bytes registered with the native evaluator: the `grade` function only."""
    import inspect

    return inspect.getsource(grade)
