"""Frozen classification metrics; invalid outputs remain in every denominator."""

LABELS = ("Iris-setosa", "Iris-versicolor", "Iris-virginica")


def score(expected, outputs):
    if not expected or len(expected) != len(outputs) or any(label not in LABELS for label in expected):
        raise ValueError("nonempty aligned labels required")
    predictions = [output.strip() if isinstance(output, str) else None for output in outputs]
    matrix = {label: {prediction: 0 for prediction in (*LABELS, "invalid")} for label in LABELS}
    for actual, prediction in zip(expected, predictions, strict=True):
        matrix[actual][prediction if prediction in LABELS else "invalid"] += 1
    per_class = {}
    for label in LABELS:
        true_positive = matrix[label][label]
        false_positive = sum(matrix[actual][label] for actual in LABELS if actual != label)
        false_negative = sum(matrix[label].values()) - true_positive
        precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
        recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
        denominator = 2 * true_positive + false_positive + false_negative
        per_class[label] = {"precision": precision, "recall": recall,
                            "f1": 2 * true_positive / denominator if denominator else 0.0,
                            "support": sum(matrix[label].values())}
    return {"n": len(expected), "accuracy": sum(actual == predicted for actual, predicted in zip(expected, predictions)) / len(expected),
            "macro_f1": sum(item["f1"] for item in per_class.values()) / len(LABELS),
            "invalid_rate": sum(predicted not in LABELS for predicted in predictions) / len(expected),
            "per_class": per_class, "confusion_matrix": matrix}