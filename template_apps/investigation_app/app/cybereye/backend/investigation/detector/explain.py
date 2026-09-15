"""Derive explanations from rule query structure and observed execution output."""

from __future__ import annotations

import re
from typing import Any

from .rules import Rule

_TIME_PREDICATE = re.compile(r"source_time\s+between", re.IGNORECASE)


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    current = ""
    for character in text:
        if character in "([":
            depth += 1
        elif character in ")]":
            depth -= 1
        if character == "," and depth == 0:
            if current.strip():
                parts.append(current.strip())
            current = ""
            continue
        current += character
    if current.strip():
        parts.append(current.strip())
    return parts


def _steps(query: str) -> list[str]:
    steps: list[str] = []
    for raw in query.strip().splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("|"):
            steps.append(line[1:].strip())
        elif steps:
            steps[-1] = f"{steps[-1]} {line}"
        else:
            steps.append(line)
    return steps


def _summarize(body: str) -> tuple[list[str], list[str]]:
    index = body.lower().rfind(" by ")
    if index < 0:
        return _split_top_level(body), []
    return _split_top_level(body[:index]), _split_top_level(body[index + 4:])


def derive_rule_explanation(rule: Rule) -> dict[str, Any]:
    """Read the rule's own KQL to describe what it matches, groups, and qualifies."""
    steps = _steps(rule.query)
    explanation: dict[str, Any] = {
        "rule_id": rule.rule_id,
        "version": rule.version,
        "role": rule.role,
        "score": rule.score,
        "threshold": rule.threshold,
        "source_table": steps[0] if steps else "",
        "time_predicate": "",
        "filters": [],
        "derived_fields": [],
        "aggregations": [],
        "group_by": [],
        "qualification": [],
        "projection": [],
        "ordering": [],
        "pipeline_steps": max(len(steps) - 1, 0),
    }
    aggregated = False
    for step in steps[1:]:
        head, _, body = step.partition(" ")
        head = head.lower()
        body = body.strip()
        if head == "where":
            if _TIME_PREDICATE.search(body) and not explanation["time_predicate"]:
                explanation["time_predicate"] = body
            elif aggregated:
                explanation["qualification"].append(body)
            else:
                explanation["filters"].append(body)
        elif head == "extend":
            explanation["derived_fields"].extend(_split_top_level(body))
        elif head == "summarize":
            aggregated = True
            aggregations, group_by = _summarize(body)
            explanation["aggregations"].extend(aggregations)
            explanation["group_by"].extend(group_by)
        elif head == "project":
            explanation["projection"].extend(_split_top_level(body))
        elif head in {"order", "sort"}:
            explanation["ordering"].append(body.removeprefix("by ").strip())
    # A rule may leave qualification to the engine rather than to KQL, so that the groups it
    # did not qualify stay visible. The test still applies; state it from the declared threshold.
    if not explanation["qualification"]:
        explanation["qualification"].append(f"event_count >= {rule.threshold}")
    return explanation


def derive_execution_observation(
    rule: Rule, rows: list[dict[str, Any]], elapsed_ms: int,
) -> dict[str, Any]:
    """Describe what the executed rule actually returned in this window."""
    qualified = [row for row in rows if int(row.get("event_count") or 0) >= rule.threshold]
    counts = [int(row.get("event_count") or 0) for row in rows]
    return {
        "groups_returned": len(rows),
        "groups_qualified": len(qualified),
        "threshold_expression": f"event_count >= {rule.threshold}",
        "max_group_count": max(counts) if counts else 0,
        "elapsed_ms": elapsed_ms,
        "entities": [
            f"{row.get('host') or 'unattributed'} / {row.get('principal') or 'unattributed'}"
            for row in qualified[:6]
        ],
        "outcome": "hit" if qualified else "miss",
    }


def derive_factor_derivation(
    rule: Rule, row: dict[str, Any], count: int, evidence_ids: list[str],
) -> dict[str, Any]:
    """Bind the rule's derived structure to the one group that qualified."""
    explanation = derive_rule_explanation(rule)
    explanation["observed"] = {
        "entity": f"{row.get('host') or 'unattributed'} / {row.get('principal') or 'unattributed'}",
        "event_count": count,
        "qualification_test": f"{count} >= {rule.threshold}",
        "returned_columns": [key for key in row if key != "evidence_ids"],
        "evidence_ids_returned": len(evidence_ids),
    }
    return explanation


def derive_situation_metrics(
    factors: list[Any], severity: str, confidence: str, thresholds: dict[str, int],
) -> list[dict[str, Any]]:
    """Build metric explanations from the factors that actually qualified."""
    score = sum(factor.score for factor in factors)
    anchors = [factor for factor in factors if factor.role == "anchor"]
    representations = sum(factor.count for factor in factors)
    evidence_ids = sum(len(factor.evidence_ids) for factor in factors)
    return [
        {
            "metric_id": "correlated_patterns",
            "label": "correlated patterns",
            "value": str(len({factor.rule_id for factor in factors})),
            "definition": (
                "Distinct deterministic rules whose ADX query returned at least one "
                "threshold-qualified group for this entity in the scanned window."
            ),
            "derivation": " + ".join(factor.rule_id for factor in factors) or "no qualifying rule",
            "contributions": [
                {
                    "source": factor.rule_id,
                    "detail": f"{factor.count} events met {factor.count} >= {thresholds.get(factor.rule_id, factor.count)}",
                    "value": factor.role,
                }
                for factor in factors
            ],
        },
        {
            "metric_id": "confidence",
            "label": "confidence",
            "value": confidence,
            "definition": (
                "Categorical confidence assigned by the synthesis policy from the summed rule "
                "scores and the number of anchor rules that qualified."
            ),
            "derivation": (
                f"score {score} from {len(factors)} factor(s), {len(anchors)} anchor(s) "
                f"-> severity {severity}, confidence {confidence}"
            ),
            "contributions": [
                {"source": factor.rule_id, "detail": f"{factor.role} rule", "value": f"+{factor.score}"}
                for factor in factors
            ],
        },
        {
            "metric_id": "evidence_representations",
            "label": "evidence representations",
            "value": str(representations),
            "definition": (
                "Total records counted by the qualifying rule queries. A logical "
                "event can appear as more than one exported representation."
            ),
            "derivation": " + ".join(f"{factor.count}" for factor in factors) + f" = {representations}",
            "contributions": [
                {
                    "source": factor.rule_id,
                    "detail": f"{len(factor.evidence_ids)} sampled resource_id value(s)",
                    "value": str(factor.count),
                }
                for factor in factors
            ] + [
                {
                    "source": "sampled_evidence",
                    "detail": "resource_id values returned for row-level citation",
                    "value": str(evidence_ids),
                }
            ],
        },
    ]
