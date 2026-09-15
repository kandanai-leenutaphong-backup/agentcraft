"""GUIDE configuration for the shared query-battery detector."""

BASELINE_RULESETS = {
    "name": "Window evidence and category patterns",
    "parent_version": None,
    "change_rationale": ["Summarize observed window structure before investigator diagnosis and triage."],
    "configuration": {
        "version": "guide-joint-baseline-v1",
        "max_window_seconds": 31622400,
        "rule_sets": [
            {"id": "window_structure", "name": "Window structure", "enabled": True, "rules": [
                {"id": "window_shape", "name": "Evidence and entity diversity", "enabled": True,
                 "query": "SELECT COUNT(*) AS evidence_rows, COUNT(DISTINCT detector_id) AS detectors, COUNT(DISTINCT category) AS categories, COUNT(DISTINCT entity_type) AS entity_types, MIN(event_time) AS first_seen, MAX(event_time) AS last_seen FROM evidence",
                 "parameters": {"min_rows": 1},
                 "processing": {"max_rows": 1, "code": 'def process(rows, parameters):\n    observed = rows[0]\n    count = observed["evidence_rows"]\n    return {"matched": count >= parameters["min_rows"], "facts": [str(count) + " evidence rows; " + str(observed["detectors"]) + " distinct detectors in the supplied window"], "technique_ids": [], "summary": observed}\n'},
                 "metadata": {"description": "Window-scoped evidence counts and diversity; volume is not maliciousness."}}
            ]},
            {"id": "category_patterns", "name": "Category patterns", "enabled": True, "rules": [
                {"id": "category_mix", "name": "Observed category mix", "enabled": True,
                 "query": "SELECT category, COUNT(*) AS evidence_rows FROM evidence GROUP BY category ORDER BY evidence_rows DESC, category LIMIT 12",
                 "parameters": {},
                 "processing": {"max_rows": 12, "code": 'def process(rows, parameters):\n    categories = [str(row["category"]) for row in rows]\n    return {"matched": bool(rows), "facts": ["Observed categories: " + ", ".join(categories[:5]) if rows else "No category evidence in window"], "technique_ids": [], "summary": {"categories": rows, "category_count_returned": len(rows)}}\n'},
                 "metadata": {"description": "Observed categories, kept separate from investigator grade inference."}}
            ]}
        ],
    },
}