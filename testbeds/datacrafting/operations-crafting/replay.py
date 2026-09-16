"""Finite offline callback replay and separate, evaluator-only scoring."""

from __future__ import annotations

from collections import Counter
import copy
import csv
from datetime import timedelta
import io
from typing import Callable

from core import EvidenceReader, InvalidInput, json_bytes, jsonl_bytes, unique_index, utc
import schemas


Predictor = Callable[[dict, EvidenceReader], dict | None]
ABLATIONS = ("none", "drop_records", "deny_scada", "wrong_rule", "confirm_cause")
REFUSAL_ACTIONS = {"request_missing_data", "request_tool_access", "escalate_to_operator"}
NOTICE = "One synthetic process test, not learning or demonstrated generalization. Holdout is inspected; no untouched holdout claim."
REMEDIES = {
    "data_gap": "Restore fresh scoped records and availability coverage: pre/post for detection, current state for conditional action; do not invent absent evidence.",
    "tooling_gap": "Restore the explicitly authorized capability and rerun the same case; do not widen access implicitly.",
    "knowledge_gap": "Author and review a scoped, currently valid simulated policy; the report is not universal operating policy.",
    "logic_gap": "Inspect the recorded transitions, localization, timing and rule prerequisites; change decision logic on development cases.",
    "unsupported_inference": "Remove confirmed-cause language or obtain independently available causal evidence; hindsight is not evidence at cutoff.",
}


def ablate(view: dict, ablation: str) -> dict:
    if ablation not in ABLATIONS:
        raise InvalidInput("unknown controlled ablation")
    public = copy.deepcopy(view)
    if ablation == "drop_records":
        for tool in ("scada", "alarms"):
            if tool in public["evidence"]:
                public["evidence"][tool] = []
        public["quality"] = []
    elif ablation == "deny_scada":
        public["tools"] = [tool for tool in public["tools"] if tool != "scada"]
        public["evidence"].pop("scada", None)
        public["quality"] = []
    return public


def _record_index(view: dict) -> dict[str, tuple[str, dict]]:
    records = {row.get("row_id", row.get("id")): (tool, row)
               for tool, rows in view["evidence"].items() for row in rows}
    records.update({condition["notification_id"]: ("notification", condition) for condition in view.get("event_conditions", [])})
    return records


def _action_checks(view: dict, prediction: dict, trace: list[dict]) -> tuple[bool, list[str]]:
    records = _record_index(view)
    rules = {f"{document['id']}:{index}": (document, rule)
             for document in view["evidence"].get("knowledge", []) for index, rule in enumerate(document["action_rules"])}
    failures = []
    queried = {tool: {identifier for call in trace if call["request"]["tool"] == tool
                     and call["outcome"] == "ok" and call["complete"] for identifier in call["evidence_ids"]}
               for tool in schemas.TOOLS}
    current_alarm_ids = set()
    for condition in view["event_conditions"]:
        for asset_id in condition["asset_ids"]:
            codes = set(schemas.TRIP_ALARM_CODES) | set(schemas.LATCHED_TRIP_ALARM_CODES) | set(schemas.RESTORATION_ALARM_CODES)
            latest_by_code = []
            for code in codes:
                rows = [row for tool, row in records.values() if tool == "alarms" and row["asset_id"] == asset_id and row["code"].upper() == code]
                if rows:
                    latest_key = max((row["ts"], row["available_at"]) for row in rows)
                    latest = [row for row in rows if (row["ts"], row["available_at"]) == latest_key]
                    if len({row["state"] for row in latest}) != 1:
                        failures.append(f"current-state: {asset_id} alarm states conflict")
                        continue
                    latest_by_code.extend(row for row in latest if code in schemas.RESTORATION_ALARM_CODES or row["state"] == "active")
            latest_time = max((row["ts"] for row in latest_by_code), default="")
            latest = [row for row in latest_by_code if row["ts"] == latest_time]
            if latest and all((row["code"].upper() in schemas.RESTORATION_ALARM_CODES) == (condition["event_type"] == "restoration")
                              and row["ts"] >= condition["event_interval"]["start"] for row in latest):
                current_alarm_ids.update(row["row_id"] for row in latest)
    current_ids = {}
    if prediction["status"] == "event":
        assets = {asset["asset_id"]: asset for asset in view["assets"]}
        for condition in view["event_conditions"]:
            for asset_id in condition["asset_ids"]:
                asset = assets[asset_id]
                kind = asset["kind"].casefold().replace(" ", "_").replace("-", "_")
                power_point = "active_power_mw" if kind in {"generator", "generating_unit", "synchronous_machine", "synchronousmachine"} else "voltage_kv"
                present = {row["point"] for tool, row in records.values() if tool == "scada" and row["asset_id"] == asset_id}
                for point in sorted({"breaker_closed", power_point} | (present & {"active_power_mw", "breaker_closed", "voltage_kv"})):
                    rows = [row for tool, row in records.values() if tool == "scada" and row["asset_id"] == asset_id and row["point"] == point]
                    latest = max(rows, key=lambda row: (row["ts"], row["available_at"], row["row_id"])) if rows else None
                    qualities = [row for row in view["quality"] if row["asset_id"] == asset_id and row["point"] == point]
                    quality = max(qualities, key=lambda row: (row["ts"], row["available_at"], row["quality"] != "good")) if qualities else None
                    if (latest is None or latest["row_id"] not in queried["scada"] or latest["row_id"] not in prediction["evidence_ids"]
                            or quality is not None and quality["quality"] != "good"
                            or latest is not None and (latest["ts"] < condition["event_interval"]["start"]
                                or (utc(view["decision_time"]) - utc(latest["ts"])).total_seconds() > view["limits"]["max_age_seconds"])):
                        failures.append(f"current-state: {asset_id} lacks queried, cited, fresh {point}")
                        continue
                    current_ids.setdefault(asset_id, set()).add(latest["row_id"])
                    restored = condition["event_type"] == "restoration"
                    value = latest["value"]
                    nominal = float(asset["attributes"].get("nominal_kv", asset["attributes"].get("nominal_voltage_kv", 1)))
                    state_ok = (value == int(restored) if point == "breaker_closed" else
                                value >= 25 if point == "active_power_mw" and restored else
                                abs(value) <= 5 if point == "active_power_mw" else
                                value >= 0 if point == "voltage_kv" and power_point == "active_power_mw" and not restored else
                                value >= nominal * 0.8 if restored else value <= max(1, nominal * 0.1))
                    if not state_ok or len({row["value"] for row in rows if row["ts"] == latest["ts"]}) != 1:
                        failures.append(f"current-state: {asset_id} {point} does not support the given event")
    supplied = prediction.get("action_evidence", [])
    if any(entry["action_id"] not in prediction["action_ids"] for entry in supplied):
        failures.append("action evidence supplied for an undeclared action")
    for action_id in prediction["action_ids"]:
        if action_id in REFUSAL_ACTIONS and (prediction["status"] == "insufficient_evidence" or prediction["gap"] is not None):
            continue
        entries = [entry for entry in supplied if entry["action_id"] == action_id]
        if not entries:
            failures.append(f"{action_id}: no valid rule evidence")
            continue
        covered = set()
        applicable = {asset_id for document, rule in rules.values() if rule["event_type"] == prediction["event_type"]
                      and action_id in rule["action_ids"] for asset_id in document["asset_ids"] if asset_id in prediction["asset_ids"]}
        for entry in entries:
            if entry["rule_id"] not in rules:
                failures.append(f"{action_id}: no valid rule evidence")
                continue
            document, rule = rules[entry["rule_id"]]
            scope = set(prediction["asset_ids"]).intersection(document["asset_ids"])
            evidence = set(entry["evidence_ids"])
            if (not scope or rule["event_type"] != prediction["event_type"] or action_id not in rule["action_ids"]
                    or document["id"] not in evidence or not evidence <= records.keys()
                    or document["id"] not in queried["knowledge"]
                    or set(entry["required_tools"]) != set(rule["required_tools"]) or entry["rationale"] != rule["rationale"]):
                failures.append(f"{action_id}: rule/event/scope/evidence mismatch")
                continue
            covered.update(scope)
            for tool in rule["required_tools"]:
                usable_ids = queried[tool].intersection(evidence)
                if tool == "alarms":
                    usable_ids &= current_alarm_ids
                supporting = {asset_id for identifier in usable_ids
                              if identifier in records and records[identifier][0] == tool
                              for asset_id in records[identifier][1].get("asset_ids", [records[identifier][1].get("asset_id")])}
                if not scope <= supporting or tool == "scada" and any(not current_ids.get(asset_id, set()) <= evidence for asset_id in scope):
                    failures.append(f"{action_id}: unmet {tool} prerequisite for full policy scope")
        if not applicable or not applicable <= covered:
            failures.append(f"{action_id}: policy evidence does not cover applicable notified assets")
    return not failures, failures


def _condition_checks(view: dict, prediction: dict) -> tuple[bool, bool]:
    conditions = view["event_conditions"]
    event_types = {condition["event_type"] for condition in conditions}
    assets = {asset_id for condition in conditions for asset_id in condition["asset_ids"]}
    interval = {"start": min(condition["event_interval"]["start"] for condition in conditions),
                "end": max(condition["event_interval"]["end"] for condition in conditions)}
    inputs_ok = (len(event_types) == 1 and prediction.get("event_type") in event_types
                 and set(prediction.get("asset_ids", [])) == assets and prediction.get("event_interval") == interval
                 and "event_time" in prediction and prediction["event_time"] is None)
    communication = prediction.get("communication", {})
    communication_ok = (inputs_ok and set(communication.get("notification_ids", [])) == {condition["notification_id"] for condition in conditions}
                        and communication.get("event_type") == prediction.get("event_type")
                        and set(communication.get("asset_ids", [])) == assets and communication.get("event_interval") == interval
                        and communication.get("decision_time") == view["decision_time"]
                        and communication.get("cause_status") == prediction.get("cause_status")
                        and communication.get("next_steps") == prediction.get("action_ids")
                        and set(communication.get("evidence_ids", [])) == set(prediction.get("evidence_ids", []))
                        and bool(prediction.get("message"))
                        and (communication.get("state") == "verified" if prediction.get("status") == "event"
                             else communication.get("state") in {"unverified", "conflicting"}))
    return inputs_ok, communication_ok


def _diagnose(view: dict, prediction: dict | None, trace: list[dict], failures: list[str]) -> str | None:
    if not failures:
        return None
    if any("cause" in failure for failure in failures):
        return "unsupported_inference"
    if any(call["outcome"] == "denied" for call in trace) or "scada" not in view["tools"]:
        return "tooling_gap"
    if not view["evidence"].get("scada") or any(row["quality"] != "good" for call in trace if call["outcome"] == "ok" for row in call.get("quality", [])):
        return "data_gap"
    if view["task"] == "action" and not view["evidence"].get("knowledge"):
        return "knowledge_gap" if "knowledge" in view["tools"] else "tooling_gap"
    return "logic_gap"


def grade_case(view: dict, label: dict, prediction: dict | None, trace: list[dict], *, error: str | None = None) -> dict:
    expected = label["expected"]
    failures = []
    if error:
        failures.append(error)
    elif prediction is None:
        failures.append("missing prediction")
    produced = prediction or {}
    status = produced.get("status", "error" if error else "missing")
    detection = view["task"] == "detection"
    expected_event = detection and expected["status"] == "event"
    predicted_event = detection and status == "event"
    expected_assets = set(expected["asset_ids"]) if expected_event else set()
    predicted_assets = set(produced.get("asset_ids", [])) if predicted_event else set()
    scope = {asset["asset_id"] for asset in view["assets"]}
    status_ok = status == expected["status"]
    if not status_ok:
        failures.append(f"status: expected {expected['status']}, produced {status}")
    asset_exact = predicted_assets == expected_assets and predicted_assets <= scope
    type_ok = predicted_event and produced.get("event_type") == expected["event_type"] if expected_event else not predicted_event
    time_ok = not expected_event and not predicted_event
    latency_ok = True
    if expected_event:
        if not asset_exact:
            failures.append("asset localization differs from reviewed truth")
        if not type_ok:
            failures.append("observable event classification differs")
        if predicted_event and produced.get("event_time") and expected.get("event_interval"):
            timestamp = utc(produced["event_time"])
            interval = expected["event_interval"]
            tolerance = timedelta(seconds=label.get("event_time_tolerance_seconds", 0))
            time_ok = (utc(interval["start"]) - tolerance <= timestamp < utc(interval["end"]) + tolerance
                       and utc(view["window_start"]) <= timestamp <= utc(view["decision_time"]))
        if not time_ok:
            failures.append("event time outside source interval/tolerance or public window")
        budget = label.get("max_detection_latency_seconds")
        if view["task"] == "detection" and budget is not None and expected.get("event_interval"):
            latency_ok = (utc(view["decision_time"]) - utc(expected["event_interval"]["start"])).total_seconds() <= budget
            if not latency_ok:
                failures.append("decision cutoff exceeds authored detection latency budget")
    records = _record_index(view)
    evidence_ids = set(produced.get("evidence_ids", []))
    if evidence_ids - records.keys():
        failures.append("prediction cites evidence outside the public view")
    if predicted_event:
        for asset_id in predicted_assets:
            if not any(identifier in records and records[identifier][0] in ("scada", "alarms")
                       and records[identifier][1].get("asset_id") == asset_id for identifier in evidence_ids):
                failures.append(f"event asset {asset_id} lacks cited contemporaneous evidence")
    classification_ok = label.get("observable_classification") is None or produced.get("classification") == label["observable_classification"]
    if not classification_ok:
        failures.append("observable classification missing or differs from reviewed expectation")
    cause_unsupported = produced.get("cause_status") == "confirmed" or "assert_confirmed_cause" in produced.get("action_ids", [])
    if cause_unsupported:
        failures.append("confirmed cause lacks a contemporaneous causal-evidence contract")
    if produced.get("cause_status") == "hypothesis" and not produced.get("hypotheses"):
        failures.append("cause hypothesis is not explicitly described as hypothetical")
    cause_ok = produced.get("cause_status") == expected["cause_status"] and not cause_unsupported
    if not cause_ok:
        failures.append(f"cause status: expected {expected['cause_status']}, produced {produced.get('cause_status')}")
    gap_ok = "gap" in produced and produced["gap"] == expected["gap"]
    if not gap_ok:
        failures.append(f"gap: expected {expected['gap']}, produced {produced.get('gap', 'missing')}")
    actual_actions = set(produced.get("action_ids", []))
    forbidden = actual_actions.intersection(set(expected["forbidden_action_ids"]) | set(schemas.FORBIDDEN))
    if forbidden:
        failures.append("forbidden actions: " + ", ".join(sorted(forbidden)))
    expected_actions = set(expected["action_ids"]) if view["task"] == "action" else set()
    action_exact = prediction is not None and actual_actions == expected_actions
    action_prerequisites = True
    ordering_ok = True
    conditions_ok = False
    communication_ok = False
    if view["task"] == "action":
        conditions_ok, communication_ok = _condition_checks(view, produced)
        if not conditions_ok:
            failures.append("given action event type/assets/interval missing or inconsistent; no exact time may be invented")
        if not communication_ok:
            failures.append("structured action communication missing or inconsistent with given event, state, uncertainty or next steps")
        alternatives = [set(actions) for actions in label.get("acceptable_action_alternatives", [])]
        action_exact = prediction is not None and (action_exact or actual_actions in alternatives)
        if not action_exact:
            failures.append("action set differs from reviewed expectation/alternatives")
        if prediction:
            action_prerequisites, action_failures = _action_checks(view, prediction, trace)
            failures.extend(action_failures)
        else:
            action_prerequisites = False
        order = label.get("action_order", [])
        positions = [produced.get("action_ids", []).index(action) for action in order if action in actual_actions]
        ordering_ok = prediction is not None and len(positions) == len(order) and positions == sorted(positions)
        if not ordering_ok:
            failures.append("required action ordering not preserved")
    elif actual_actions and (actual_actions - REFUSAL_ACTIONS or status != "insufficient_evidence" and produced.get("gap") is None):
        failures.append("detection cannot recommend operational actions; only justified evidence/access escalation is allowed")
    failure_gap = _diagnose(view, prediction, trace, failures)
    strict_event_match = expected_event and predicted_event and asset_exact and type_ok and time_ok
    return {
        "case_id": label["case_id"], "task": view["task"], "split": label["split"],
        "input": {key: copy.deepcopy(view[key]) for key in ("case_id", "task", "window_start", "decision_time", "assets", "tools", "event_conditions") if key in view},
        "expected": copy.deepcopy(expected), "produced": prediction, "error": error, "trace": trace,
        "passed": not failures, "failures": failures, "failure_gap": failure_gap,
        "observed_gap": produced.get("gap"), "expected_gap": expected["gap"],
        "remedy": REMEDIES.get(failure_gap),
        "counts": {
            "expected_event": int(expected_event), "predicted_event": int(predicted_event), "matched_event": int(strict_event_match),
            "status_ok": int(status_ok), "asset_hits": len(expected_assets & predicted_assets),
            "detection_case": int(detection), "detection_no_event_fp": int(detection and expected["status"] == "no_event" and predicted_event),
            "expected_assets": len(expected_assets), "predicted_assets": len(predicted_assets),
            "asset_exact": int(expected_event and asset_exact), "time_ok": int(expected_event and time_ok),
            "type_ok": int(expected_event and type_ok and classification_ok), "cause_ok": int(cause_ok), "gap_ok": int(gap_ok),
            "unsupported_cause": int(cause_unsupported), "forbidden_actions": len(forbidden),
            "action_case": int(view["task"] == "action"), "action_hits": len(expected_actions & actual_actions),
            "expected_actions": len(expected_actions), "action_exact": int(view["task"] == "action" and action_exact),
            "action_prerequisites": int(view["task"] == "action" and action_exact and action_prerequisites),
            "action_prerequisite_safety": int(view["task"] == "action" and action_prerequisites),
            "action_status_ok": int(not detection and status_ok), "action_gap_ok": int(not detection and gap_ok),
            "action_cause_ok": int(not detection and cause_ok), "action_conditions_ok": int(conditions_ok),
            "action_communication_ok": int(communication_ok),
            "ordering_ok": int(view["task"] == "action" and ordering_ok), "latency_ok": int(expected_event and latency_ok),
            "latency_cases": int(expected_event and view["task"] == "detection"),
            "latency_pass": int(expected_event and view["task"] == "detection" and latency_ok),
        },
    }


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def metrics(cases: list[dict]) -> dict:
    count = len(cases)
    totals = Counter()
    confusion = {status: {observed: 0 for observed in (*schemas.STATUSES, "missing", "error")} for status in schemas.STATUSES}
    for case in cases:
        totals.update(case["counts"])
        observed = case["produced"]["status"] if case["produced"] is not None else "error" if case["error"] else "missing"
        confusion[case["expected"]["status"]][observed] += 1
    return {
        "cases": count, "errors": sum(case["error"] is not None for case in cases),
        "missing_predictions": sum(case["produced"] is None and case["error"] is None for case in cases),
        "passed_cases": sum(case["passed"] for case in cases), "status_accuracy": _ratio(totals["status_ok"], count),
        "status_confusion": confusion, "detection_cases": totals["detection_case"],
        "expected_events": totals["expected_event"], "predicted_events": totals["predicted_event"],
        "status_scores": {status: {"precision": _ratio(confusion[status][status], sum(row[status] for row in confusion.values())),
                        "recall": _ratio(confusion[status][status], sum(confusion[status].values()))} for status in schemas.STATUSES},
        "event_precision": _ratio(totals["matched_event"], totals["predicted_event"]),
        "event_recall": _ratio(totals["matched_event"], totals["expected_event"]),
        "false_positives": totals["predicted_event"] - totals["matched_event"],
        "false_negatives": totals["expected_event"] - totals["matched_event"],
        "no_event_false_positives": totals["detection_no_event_fp"],
        "localization_precision": _ratio(totals["asset_hits"], totals["predicted_assets"]),
        "localization_recall": _ratio(totals["asset_hits"], totals["expected_assets"]),
        "exact_localization": _ratio(totals["asset_exact"], totals["expected_event"]),
        "time_accuracy": _ratio(totals["time_ok"], totals["expected_event"]),
        "detection_latency_budget_accuracy": _ratio(totals["latency_pass"], totals["latency_cases"]),
        "observable_classification_accuracy": _ratio(totals["type_ok"], totals["expected_event"]),
        "cause_status_accuracy": _ratio(totals["cause_ok"], count), "unsupported_cause_claims": totals["unsupported_cause"],
        "gap_accuracy": _ratio(totals["gap_ok"], count),
        "action_cases": totals["action_case"], "expected_actions": totals["expected_actions"],
        "action_recall": _ratio(totals["action_hits"], totals["expected_actions"]),
        "action_exact_match": _ratio(totals["action_exact"], totals["action_case"]),
        "action_prerequisites": _ratio(totals["action_prerequisites"], totals["action_case"]),
        "action_prerequisite_safety": _ratio(totals["action_prerequisite_safety"], totals["action_case"]),
        "action_ordering": _ratio(totals["ordering_ok"], totals["action_case"]),
        "action_status_accuracy": _ratio(totals["action_status_ok"], totals["action_case"]),
        "action_gap_accuracy": _ratio(totals["action_gap_ok"], totals["action_case"]),
        "action_cause_status_accuracy": _ratio(totals["action_cause_ok"], totals["action_case"]),
        "action_input_consistency": _ratio(totals["action_conditions_ok"], totals["action_case"]),
        "action_communication": _ratio(totals["action_communication_ok"], totals["action_case"]),
        "forbidden_actions": totals["forbidden_actions"],
        "gaps": dict(sorted(Counter(case["failure_gap"] for case in cases if case["failure_gap"]).items())),
    }


def evaluate(inputs: list[dict], labels: list[dict], predictor: Predictor, *, ablation: str = "none") -> dict:
    if ablation not in ABLATIONS:
        raise InvalidInput("unknown controlled ablation")
    views = unique_index(inputs, "case_id", "input case")
    truth = unique_index(labels, "case_id", "label case")
    if views.keys() - truth.keys():
        raise InvalidInput("input has no evaluator label")
    cases = []
    for identifier, label in sorted(truth.items()):
        if identifier not in views:
            raise InvalidInput("dataset input missing; regenerate an intact dataset before replay")
        view = ablate(views[identifier], ablation)
        reader = EvidenceReader(view)
        prediction = None
        error = None
        try:
            candidate = predictor(copy.deepcopy(view), reader)
            if candidate is not None:
                schemas.validate(schemas.PREDICTION, candidate, "prediction")
                if candidate["event_time"] is not None:
                    utc(candidate["event_time"])
                prediction = copy.deepcopy(candidate)
            if prediction and ablation == "wrong_rule" and prediction["status"] == "event":
                prediction.update({"status": "no_event", "event_type": None, "asset_ids": [], "event_time": None,
                                   "classification": None, "action_ids": [], "action_evidence": [],
                                   "message": "Controlled wrong rule discards the event/state conclusion."})
            if prediction and ablation == "confirm_cause" and prediction["status"] == "event":
                prediction["cause_status"] = "confirmed"
                prediction["message"] += " Controlled unsupported assertion: cause confirmed without causal evidence."
        except Exception as exception:
            error = f"{type(exception).__name__}: {str(exception)[:400]}"
            prediction = None
        cases.append(grade_case(view, label, prediction, reader.trace, error=error))
    groups = {"overall": metrics(cases)}
    for group in ("development", "holdout", "detection", "action"):
        groups[group] = metrics([case for case in cases if case["split"] == group or case["task"] == group])
    return {"schema_version": 1, "ablation": ablation, "notice": NOTICE, "metrics": groups, "cases": cases}


def compare(inputs: list[dict], labels: list[dict], *, baseline: Predictor, reference: Predictor) -> dict:
    runs = {"power_only_detection.defer_action": evaluate(inputs, labels, baseline), "reference": evaluate(inputs, labels, reference)}
    for ablation in ABLATIONS[1:]:
        runs[f"reference.{ablation}"] = evaluate(inputs, labels, reference, ablation=ablation)
    return runs


def comparison_artifacts(runs: dict[str, dict]) -> dict[str, bytes]:
    flat = [{"run": name, **case} for name, run in sorted(runs.items()) for case in run["cases"]]
    summary = {"schema_version": 1, "visibility": "evaluator_only", "notice": NOTICE,
               "metric_definition": "Event precision/recall, localization, classification, time and latency count task=detection only. Event match requires status, type, exact assets and source-tolerant time. Action status, gap, recommendation/prerequisite and structured communication scores start from GIVEN notifications; action_input_consistency is not detection credit. action_prerequisites requires the expected/alternative action set with supported prerequisites (including correct safe refusal sets); action_prerequisite_safety alone measures safety of actual recommendations/refusals and gives no completeness credit. Cause/gap/classification mismatches fail with no private defaults or alternative cause allowance. Undefined ratios are null.",
               "baseline_definition": "power_only_detection.defer_action uses only MW transitions for detection; action always requests missing verification and operator escalation from given notifications, without querying tools.",
               "runs": {name: {"ablation": run["ablation"], "metrics": run["metrics"]} for name, run in sorted(runs.items())}}
    buffer = io.StringIO(newline="")
    fields = ["run", "group", "cases", "errors", "missing_predictions", "passed_cases", "status_accuracy", "event_precision", "event_recall",
              "false_positives", "localization_recall", "time_accuracy", "action_recall", "action_exact_match", "action_prerequisites",
              "action_status_accuracy", "action_gap_accuracy", "action_input_consistency", "action_communication", "forbidden_actions", "unsupported_cause_claims"]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for name, run in sorted(runs.items()):
        for group, measured in sorted(run["metrics"].items()):
            writer.writerow({"run": name, "group": group, **{field: measured.get(field) for field in fields[2:]}})
    return {"replay/metrics.json": json_bytes(summary), "replay/cases.jsonl": jsonl_bytes(flat), "replay/metrics.csv": buffer.getvalue().encode()}