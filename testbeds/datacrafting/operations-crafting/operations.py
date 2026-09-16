"""Operations-owned observations, simulated action plans and dataset semantics."""

from __future__ import annotations

from collections import Counter, defaultdict
import copy
import json

from core import AEST, Bundle, EvidenceReader, InvalidInput, QueryDenied, case_id, check_interval, json_bytes, jsonl_bytes, materialize_view, utc
from replay import NOTICE, compare, comparison_artifacts
import schemas


OBSERVABLE_CLASSES = {
    "generator_trip": "generation_disconnection",
    "busbar_trip": "busbar_deenergization",
    "restoration": "return_to_service",
}
GENERATOR_KINDS = {"generator", "generating_unit", "synchronous_machine", "synchronousmachine"}
BUSBAR_KINDS = {"busbar", "busbar_section", "busbarsection"}
SIGNAL_POINTS = {"active_power_mw", "breaker_closed", "voltage_kv"}
PLANNED_CODES = {"PLANNED_SHUTDOWN", "PLANNED_TRANSITION", "PLANNED_OUTAGE", "SCHEDULED_OUTAGE", "PLANNED_SWITCHING"}
TRIP_CODES = set(schemas.TRIP_ALARM_CODES)
TRIP_STATE_CODES = TRIP_CODES | set(schemas.LATCHED_TRIP_ALARM_CODES)
RESTORATION_CODES = set(schemas.RESTORATION_ALARM_CODES)


def _empty(status: str, message: str, gap: str | None = None) -> dict:
    return {"status": status, "event_type": None, "asset_ids": [], "event_time": None,
            "cause_status": "not_established", "classification": None, "hypotheses": [],
            "action_ids": [], "action_evidence": [], "evidence_ids": [], "gap": gap, "message": message}


def _insufficient(message: str, gap: str) -> dict:
    result = _empty("insufficient_evidence", message, gap)
    result["action_ids"] = ["request_tool_access" if gap == "tooling_gap" else "request_missing_data", "escalate_to_operator"]
    return result


def _kind(asset: dict) -> str:
    return asset["kind"].casefold().replace(" ", "_").replace("-", "_")


def _state(point: str, value: float, nominal: float) -> int | None:
    if point in ("breaker_closed", "available"):
        return int(value)
    if point == "active_power_mw":
        return 0 if abs(value) <= 5 else 1 if value >= 25 else None
    if point == "voltage_kv":
        return 0 if value <= max(1, nominal * 0.1) else 1 if value >= nominal * 0.8 else None
    return None


def _observe(view: dict, reader: EvidenceReader, *, power_only: bool) -> dict:
    try:
        scada = reader.query("scada")
    except QueryDenied:
        return _insufficient("SCADA access unavailable; request access and operator review.", "tooling_gap")
    if not scada["complete"]:
        return _insufficient("Evidence row bound truncated the window; narrow or restore coverage.", "data_gap")
    alarm_rows = []
    if not power_only and "alarms" in view["tools"]:
        alarm_rows = reader.query("alarms")["rows"]
    by_asset = defaultdict(lambda: defaultdict(list))
    for row in scada["rows"]:
        by_asset[row["asset_id"]][row["point"]].append(row)
    quality = {(row["asset_id"], row["point"]): row["quality"] for row in scada["quality"]}
    events = []
    uncertain_assets = []
    observed_ids = []
    monitored = [asset for asset in view["assets"] if _kind(asset) in GENERATOR_KINDS | BUSBAR_KINDS]
    if not monitored or not scada["rows"]:
        return _insufficient("No usable monitored-asset samples are available by this cutoff.", "data_gap")
    for asset in monitored:
        asset_id = asset["asset_id"]
        kind = _kind(asset)
        points = by_asset[asset_id]
        wanted = {"active_power_mw"} if power_only else SIGNAL_POINTS
        if kind in BUSBAR_KINDS and not power_only:
            wanted = wanted - {"active_power_mw"}
        transitions = []
        latest_states = []
        terminal_state = None
        valid_series = 0
        degraded = False
        for point in sorted(wanted):
            series = sorted(points.get(point, []), key=lambda row: (row["ts"], row["available_at"], row["row_id"]))
            last_quality = quality.get((asset_id, point))
            if kind in GENERATOR_KINDS and point == "voltage_kv":
                if (series and last_quality in (None, "good")
                        and (utc(view["decision_time"]) - utc(series[-1]["ts"])).total_seconds() <= view["limits"]["max_age_seconds"]
                        and len({row["value"] for row in series if row["ts"] == series[-1]["ts"]}) == 1):
                    nominal = float(asset["attributes"].get("nominal_kv", asset["attributes"].get("nominal_voltage_kv", 1)))
                    terminal_state = _state(point, series[-1]["value"], nominal)
                    observed_ids.append(series[-1]["row_id"])
                continue
            if last_quality is not None and last_quality != "good":
                degraded = True
                continue
            if not series:
                continue
            if (utc(view["decision_time"]) - utc(series[-1]["ts"])).total_seconds() > view["limits"]["max_age_seconds"]:
                degraded = True
                continue
            values_at_time = defaultdict(set)
            for row in series:
                values_at_time[row["ts"]].add(row["value"])
            if any(len(values) > 1 for values in values_at_time.values()):
                degraded = True
                continue
            nominal = float(asset["attributes"].get("nominal_kv", asset["attributes"].get("nominal_voltage_kv", max(row["value"] for row in series) or 1)))
            states = [_state(point, row["value"], nominal) for row in series]
            if states[-1] is None:
                degraded = True
                continue
            latest_states.append(states[-1])
            if len(values_at_time) >= 2:
                valid_series += 1
            observed_ids.append(series[-1]["row_id"])
            for previous, current, previous_state, current_state in zip(series, series[1:], states, states[1:]):
                if previous["ts"] != current["ts"] and previous_state is not None and current_state is not None and previous_state != current_state:
                    transitions.append({"time": current["ts"], "direction": current_state, "point": point,
                                        "evidence_ids": [previous["row_id"], current["row_id"]]})
        alarms = [row for row in alarm_rows if row["asset_id"] == asset_id]
        planned = [row for row in alarms if row["state"] == "active" and row["code"].upper() in PLANNED_CODES]
        if power_only and kind in BUSBAR_KINDS:
            continue
        if (not power_only and kind in GENERATOR_KINDS and set(latest_states) == {1}
                and (points.get("voltage_kv") or (asset_id, "voltage_kv") in quality) and terminal_state != 1):
            uncertain_assets.append(asset_id)
            continue
        if latest_states and len(set(latest_states)) > 1:
            uncertain_assets.append(asset_id)
            continue
        if transitions:
            transitions = list({transition["point"]: transition for transition in sorted(transitions, key=lambda transition: transition["time"])}.values())
            candidate = max(transitions, key=lambda transition: transition["time"])
            direction = candidate["direction"]
            if planned and any(row["ts"] <= candidate["time"] for row in planned):
                observed_ids.extend(row["row_id"] for row in planned)
                continue
            if latest_states and any(state != direction for state in latest_states):
                uncertain_assets.append(asset_id)
                continue
            matching = [transition for transition in transitions if transition["direction"] == direction]
            event_type = "restoration" if direction else "generator_trip" if kind in GENERATOR_KINDS else "busbar_trip"
            evidence_ids = [identifier for transition in matching for identifier in transition["evidence_ids"]]
            evidence_ids.extend(row["row_id"] for row in alarms if row["ts"] >= min(transition["time"] for transition in matching))
            events.append({"asset_id": asset_id, "event_type": event_type,
                           "time": min(transition["time"] for transition in matching), "evidence_ids": evidence_ids})
        else:
            trip_alarms = [row for row in alarms if row["state"] == "active" and row["code"].upper() in TRIP_CODES]
            if not power_only and latest_states and set(latest_states) == {0} and trip_alarms and not planned:
                events.append({"asset_id": asset_id, "event_type": "generator_trip" if kind in GENERATOR_KINDS else "busbar_trip",
                               "time": min(row["ts"] for row in trip_alarms),
                               "evidence_ids": [row["row_id"] for row in trip_alarms] + observed_ids[-len(latest_states):]})
            elif valid_series == 0 or degraded:
                uncertain_assets.append(asset_id)
    if events:
        if len({event["event_type"] for event in events}) != 1 or uncertain_assets:
            return _insufficient("Conflicting transitions or incomplete monitored-asset coverage require reconciliation.", "data_gap")
        event_type = events[0]["event_type"]
        result = _empty("event", "Observed as-of transitions support an event; ultimate cause is not established.")
        result.update({"event_type": event_type, "classification": OBSERVABLE_CLASSES[event_type],
                       "asset_ids": sorted(event["asset_id"] for event in events),
                       "event_time": min(event["time"] for event in events),
                       "evidence_ids": sorted({identifier for event in events for identifier in event["evidence_ids"]})})
        return result
    if uncertain_assets:
        return _insufficient("Missing, bad, stale or insufficient pre/post samples cannot establish absence of an event.", "data_gap")
    result = _empty("no_event", "No qualifying unplanned transition in usable as-of samples; steady outages are not new trips.")
    result["evidence_ids"] = sorted(set(observed_ids))
    return result


def _given_event(view: dict) -> dict:
    conditions = view["event_conditions"]
    types = {condition["event_type"] for condition in conditions}
    event_type = next(iter(types)) if len(types) == 1 else None
    result = _insufficient("Current state and recommendation prerequisites remain unverified.", "data_gap")
    result.update({"event_type": event_type, "classification": OBSERVABLE_CLASSES.get(event_type),
                   "asset_ids": sorted({asset_id for condition in conditions for asset_id in condition["asset_ids"]}),
                   "event_interval": {"start": min(condition["event_interval"]["start"] for condition in conditions),
                                      "end": max(condition["event_interval"]["end"] for condition in conditions)},
                   "evidence_ids": sorted(condition["notification_id"] for condition in conditions)})
    return result


def _communicate(view: dict, result: dict, state: str, observations: list[str]) -> dict:
    conditions = view["event_conditions"]
    given = "; ".join(f"{condition['event_type']} for {', '.join(condition['asset_ids'])} in "
                      f"[{condition['event_interval']['start']}, {condition['event_interval']['end']})"
                      for condition in conditions)
    result["message"] = (f"Given simulated notifications: {given}. As of {view['decision_time']}, current state is {state}: "
                         f"{'; '.join(observations) or 'no verified current measurements'}. {result['message']} "
                         f"Cause is not established; notifications do not prove recommendation prerequisites. "
                         f"Next steps: {', '.join(result['action_ids']) or 'none'}. "
                         "All steps are simulated recommendations or requests for an authorized operator; nothing is executed.")
    result["communication"] = {
        "notification_ids": sorted(condition["notification_id"] for condition in conditions),
        "event_type": result["event_type"], "asset_ids": result["asset_ids"].copy(),
        "event_interval": copy.deepcopy(result["event_interval"]), "decision_time": view["decision_time"],
        "state": state, "cause_status": result["cause_status"], "next_steps": result["action_ids"].copy(),
        "evidence_ids": result["evidence_ids"].copy(),
    }
    return result


def _refuse_actions(result: dict, gap: str, message: str) -> dict:
    result.update({"gap": gap, "action_ids": ["request_tool_access" if gap == "tooling_gap" else "request_missing_data", "escalate_to_operator"],
                   "action_evidence": [], "message": message})
    return result


def _conditioned_action(view: dict, reader: EvidenceReader) -> dict:
    result = _given_event(view)
    observations = []
    if result["event_type"] is None:
        result["message"] = "Conflicting notification types require separate operator reconciliation."
        return _communicate(view, result, "conflicting", observations)
    try:
        scada = reader.query("scada", asset_ids=result["asset_ids"])
    except QueryDenied:
        return _communicate(view, _refuse_actions(result, "tooling_gap", "SCADA access is unavailable."), "unverified", observations)
    if not scada["complete"]:
        result["message"] = "Current-state query is truncated; narrow or restore coverage."
        return _communicate(view, result, "unverified", observations)
    quality = {(row["asset_id"], row["point"]): row["quality"] for row in scada["quality"]}
    inventory = {asset["asset_id"]: asset for asset in view["assets"]}
    target_state = int(result["event_type"] == "restoration")
    for asset_id in result["asset_ids"]:
        asset = inventory[asset_id]
        kind = _kind(asset)
        if (kind not in GENERATOR_KINDS | BUSBAR_KINDS
                or result["event_type"] == "generator_trip" and kind not in GENERATOR_KINDS
                or result["event_type"] == "busbar_trip" and kind not in BUSBAR_KINDS):
            result["message"] = f"Notification type does not match the declared asset class for {asset_id}."
            return _communicate(view, result, "conflicting", observations)
        earliest = max(condition["event_interval"]["start"] for condition in view["event_conditions"] if asset_id in condition["asset_ids"])
        required = {"breaker_closed", "active_power_mw" if kind in GENERATOR_KINDS else "voltage_kv"}
        present = {row["point"] for row in scada["rows"] if row["asset_id"] == asset_id}
        for point in sorted(required | (present & SIGNAL_POINTS)):
            series = [row for row in scada["rows"] if row["asset_id"] == asset_id and row["point"] == point]
            latest = max(series, key=lambda row: (row["ts"], row["available_at"], row["row_id"])) if series else None
            if (latest is None or quality.get((asset_id, point), "good") != "good" or latest["ts"] < earliest
                    or (utc(view["decision_time"]) - utc(latest["ts"])).total_seconds() > view["limits"]["max_age_seconds"]):
                result["message"] = f"{asset_id} lacks a fresh usable post-notification {point} sample."
                return _communicate(view, result, "unverified", observations)
            result["evidence_ids"].append(latest["row_id"])
            observations.append(f"{asset_id} {point}={latest['value']} {latest['unit']} at {latest['ts']}")
            nominal = float(asset["attributes"].get("nominal_kv", asset["attributes"].get("nominal_voltage_kv", 1)))
            simultaneous = {row["value"] for row in series if row["ts"] == latest["ts"]}
            terminal_after_trip = kind in GENERATOR_KINDS and point == "voltage_kv" and not target_state
            state_matches = latest["value"] >= 0 if terminal_after_trip else _state(point, latest["value"], nominal) == target_state
            if len(simultaneous) != 1 or not state_matches:
                result["message"] = f"{asset_id} current {point} conflicts with the notified {result['event_type']} state."
                return _communicate(view, result, "conflicting", observations)
    if "alarms" in view["tools"]:
        alarms = reader.query("alarms", asset_ids=result["asset_ids"])
        if not alarms["complete"]:
            result["message"] = "Alarm query is truncated; protection state cannot be reconciled."
            return _communicate(view, result, "unverified", observations)
        for asset_id in result["asset_ids"]:
            by_code = defaultdict(list)
            for row in alarms["rows"]:
                if row["asset_id"] == asset_id and row["code"].upper() in TRIP_STATE_CODES | RESTORATION_CODES:
                    by_code[row["code"].upper()].append(row)
            current = []
            for series in by_code.values():
                latest_key = max((row["ts"], row["available_at"]) for row in series)
                latest = [row for row in series if (row["ts"], row["available_at"]) == latest_key]
                if len({row["state"] for row in latest}) != 1:
                    result["message"] = f"{asset_id} has contradictory simultaneous alarm states."
                    return _communicate(view, result, "conflicting", observations)
                current.extend(latest)
            relevant = [row for row in current if
                        (row["code"].upper() in TRIP_STATE_CODES and row["state"] == "active"
                         or row["code"].upper() in RESTORATION_CODES)]
            if not relevant:
                continue
            latest_time = max(row["ts"] for row in relevant)
            latest = [row for row in relevant if row["ts"] == latest_time]
            result["evidence_ids"].extend(row["row_id"] for row in latest)
            if any(int(row["code"].upper() in RESTORATION_CODES) != target_state for row in latest):
                result["message"] = f"{asset_id} latest protection/return indication conflicts with current notified state."
                return _communicate(view, result, "conflicting", observations)
    result.update({"status": "event", "gap": None, "action_ids": [],
                   "evidence_ids": sorted(set(result["evidence_ids"])),
                   "message": "Fresh current measurements agree with the given event; original transition detection was not required."})
    return _communicate(view, _plan_actions(view, reader, result), "verified", observations)


def _plan_actions(view: dict, reader: EvidenceReader, result: dict) -> dict:
    if view["task"] != "action" or result["status"] != "event":
        return result
    try:
        response = reader.query("knowledge", asset_ids=result["asset_ids"])
    except QueryDenied:
        return _refuse_actions(result, "tooling_gap", "Policy tool is unavailable; request access before recommendations.")
    if not response["complete"]:
        return _refuse_actions(result, "data_gap", "Policy query is truncated; no complete recommendation basis.")
    documents = response["rows"]
    matching = [(document, index, rule) for document in documents for index, rule in enumerate(document["action_rules"])
                if rule["event_type"] == result["event_type"] and rule["action_ids"] and set(result["asset_ids"]).intersection(document["asset_ids"])]
    covered = {asset_id for document, _, _ in matching for asset_id in document["asset_ids"]}
    if not set(result["asset_ids"]) <= covered:
        return _refuse_actions(result, "knowledge_gap", "No currently valid action policy covers every notified asset; request scoped policy evidence.")
    if any(tool not in view["tools"] for _, _, rule in matching for tool in rule["required_tools"]):
        return _refuse_actions(result, "tooling_gap", "A required policy capability is unavailable; request authorized tool access.")
    actions, plans = [], []
    for document, index, rule in matching:
        rule_evidence = [document["id"], *result["evidence_ids"]]
        scope = sorted(set(result["asset_ids"]).intersection(document["asset_ids"]))
        for tool in rule["required_tools"]:
            try:
                response = reader.query(tool, asset_ids=scope)
            except QueryDenied:
                return _refuse_actions(result, "tooling_gap", f"Required {tool} query was refused.")
            rows = response["rows"]
            if tool in ("scada", "alarms"):
                rows = [row for row in rows if row["row_id"] in result["evidence_ids"]]
            supported = {asset_id for row in rows for asset_id in row.get("asset_ids", [row.get("asset_id")])}
            if not response["complete"] or not set(scope) <= supported:
                return _refuse_actions(result, "data_gap", f"Required {tool} evidence is incomplete for {', '.join(scope)}; no operational recommendation.")
            rule_evidence.extend(row.get("row_id", row.get("id")) for row in rows)
        for action_id in rule["action_ids"]:
            if action_id not in actions:
                actions.append(action_id)
            plans.append({"action_id": action_id, "rule_id": f"{document['id']}:{index}",
                          "required_tools": rule["required_tools"], "rationale": rule["rationale"],
                          "evidence_ids": sorted(set(rule_evidence))})
        result["evidence_ids"] = sorted(set(result["evidence_ids"] + rule_evidence))
    result.update({"action_ids": actions, "action_evidence": plans})
    return result


def reference(view: dict, reader: EvidenceReader) -> dict:
    return _conditioned_action(view, reader) if view["task"] == "action" else _observe(view, reader, power_only=False)


def power_only(view: dict, reader: EvidenceReader) -> dict:
    if view["task"] == "action":
        result = _given_event(view)
        result["message"] = "Notification-only defer baseline: available state and policy tools were not inspected; request verification."
        return _communicate(view, result, "unverified", [])
    return _observe(view, reader, power_only=True)


def _label(bundle: Bundle, scenario: dict, view: dict) -> dict:
    expected = scenario["expected"]
    schemas.validate(schemas.EXPECTED, expected, f"scenario {scenario['scenario_id']}.expected")
    if not set(expected["asset_ids"]) <= set(scenario["asset_ids"]):
        raise InvalidInput("expected assets escape scenario scope")
    if expected["status"] == "event" and (not expected["asset_ids"] or expected["event_type"] is None or expected["event_interval"] is None):
        raise InvalidInput("expected event requires type, assets and event interval")
    if expected["event_interval"] is not None:
        check_interval(expected["event_interval"])
        if expected["status"] == "event" and expected["event_interval"]["start"] > scenario["decision_time"]:
            raise InvalidInput("expected observed event cannot begin after decision cutoff")
    if set(expected["action_ids"]).intersection(expected["forbidden_action_ids"]):
        raise InvalidInput("expected and forbidden actions overlap")
    incident = scenario["incident_id"].casefold()
    if (incident == "yallourn" and scenario["split"] != "development") or (incident == "murray" and scenario["split"] != "holdout"):
        raise InvalidInput("v1 incident grouping requires Yallourn development and Murray holdout")
    if any(clue in scenario["scenario_id"].casefold() for clue in ("generator_trip", "busbar_trip", "restoration", "yallourn", "murray", "no_event", "holdout", "development")):
        raise InvalidInput("scenario_id must be opaque, not an answer or incident label")
    sources = [event for event in bundle.sources["events"] if event["id"] in scenario["source_event_ids"]]
    parameters = copy.deepcopy(scenario["parameters"])
    label = {
        "schema_version": 1, "visibility": "evaluator_only", "mode": {"id": "operations", "version": 1},
        "case_id": case_id(bundle, scenario), **{key: copy.deepcopy(scenario[key]) for key in (
            "scenario_id", "incident_id", "split", "kind", "template_id", "variant", "source_event_ids", "expected", "assumptions")},
        "observable_classification": OBSERVABLE_CLASSES.get(expected["event_type"]) if expected["status"] == "event" else None,
        "event_time_tolerance_seconds": parameters.get("event_time_tolerance_seconds", 0),
        "max_detection_latency_seconds": parameters.get("maximum_detection_latency_seconds", parameters.get("max_detection_latency_seconds", 300)),
        "time_context": {"window_start": scenario["window_start"], "decision_time": scenario["decision_time"],
                         "timezone": "AEST", "utc_offset": "+10:00", "interval_end": "exclusive",
                         "source_events": [{key: copy.deepcopy(event[key]) for key in ("id", "reported_time", "precision", "event_interval")} for event in sources]},
        "forensic_truth": [{key: copy.deepcopy(event[key]) for key in ("id", "classification", "cause", "actual_actions")} for event in sources],
        "asset_bindings": [{"asset_id": asset_id, "name": bundle.assets[asset_id]["name"], "aliases": bundle.assets[asset_id]["aliases"],
                            "kind": bundle.assets[asset_id]["kind"], "cim_id": bundle.assets[asset_id]["cim_id"],
                            "scada_points": sorted({row["point"] for row in bundle.tables["scada"] if row["asset_id"] == asset_id and row["scenario_id"] == scenario["scenario_id"]}),
                            "capabilities": scenario["tools"], "binding_status": "synthetic_only"} for asset_id in sorted(scenario["asset_ids"])],
        "action_prerequisites": [{"knowledge_id": document["id"], "valid_from": document["valid_from"], "available_at": document["available_at"],
                                  "asset_ids": document["asset_ids"], **copy.deepcopy(rule)}
                                 for document in view["evidence"].get("knowledge", []) for rule in document["action_rules"]
                                 if rule["event_type"] == expected["event_type"] and set(expected["asset_ids"]).intersection(document["asset_ids"])],
        "parameters": parameters, "action_order": parameters.get("action_order", []),
        "acceptable_action_alternatives": parameters.get("acceptable_action_alternatives", []),
    }
    schemas.validate(schemas.LABEL, label, "label")
    return label


def _aest(timestamp: str) -> str:
    return utc(timestamp).astimezone(AEST).isoformat(timespec="seconds") + " AEST"


def _text(value) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _forensic_lines(events: list[dict]) -> list[str]:
    lines = []
    for event in events:
        cause = event["cause"]
        if isinstance(cause, dict):
            cause = {key: value for key, value in cause.items() if key != "source_refs"}
        lines.append(f"- {event['id']}: later classification {_text(event['classification'])}; later cause {_text(cause)}.")
        for action in event["actual_actions"]:
            if isinstance(action, dict):
                lines.append(f"- Historical action {action.get('id', '')}: {action.get('description', '')} Time: {action.get('reported_time', 'not specified')}; precision: {action.get('precision', 'not specified')}; uncertainty: {action.get('assumption', 'none additionally asserted')}.")
            else:
                lines.append(f"- Historical action: {action}")
    return lines


def _sample_lines(view: dict, produced: dict | None, expected: dict) -> list[str]:
    selected_assets = set((produced or {}).get("asset_ids", [])) or set(expected["asset_ids"])
    groups = defaultdict(list)
    for row in view["evidence"].get("scada", []):
        if row["asset_id"] in selected_assets and row["point"] in SIGNAL_POINTS:
            groups[(row["asset_id"], row["point"])].append(row)
    lines = ["", "Representative public samples (first/last per affected point; complete values in the public input file):", "",
             "| Asset / Point | Event UTC | Available UTC | Value | Unit | Evidence ID |",
             "| --- | --- | --- | ---: | --- | --- |"]
    for key, rows in sorted(groups.items()):
        for row in [rows[0], rows[-1]] if len(rows) > 1 else rows:
            lines.append(f"| {key[0]} / {key[1]} | {row['ts']} | {row['available_at']} | {row['value']} | {row['unit']} | {row['row_id']} |")
    if not groups:
        lines.append("| No affected-asset usable sample | - | - | - | - | - |")
    return lines


def replay_review(runs: dict) -> str:
    lines = ["## Replay Measurements", "", NOTICE, "",
             "Detection-only precision/recall require event type, exact assets and source-tolerant time. Given action notifications never enter event/localization/time denominators. Null means no denominator.", "",
             "| Run | Detection Cases | Passed | Status Accuracy | Event P/R | FP | Localization Recall | Time Accuracy |",
             "| --- | ---: | ---: | ---: | --- | ---: | ---: | ---: |"]
    for name, run in sorted(runs.items()):
        measured = run["metrics"]["detection"]
        lines.append(f"| {name} | {measured['cases']} | {measured['passed_cases']} | {measured['status_accuracy']} | {measured['event_precision']} / {measured['event_recall']} | {measured['false_positives']} | {measured['localization_recall']} | {measured['time_accuracy']} |")
    lines.extend(["", "Conditional action scores assess recommendations from GIVEN notifications, not independent event detection.", "",
                  "| Run | Action Cases | Passed | Recall / Exact | Prerequisites | Status / Gap | Input Consistency | Communication | Unsupported Causes |",
                  "| --- | ---: | ---: | --- | ---: | --- | ---: | ---: | ---: |"])
    for name, run in sorted(runs.items()):
        measured = run["metrics"]["action"]
        lines.append(f"| {name} | {measured['cases']} | {measured['passed_cases']} | {measured['action_recall']} / {measured['action_exact_match']} | {measured['action_prerequisites']} | {measured['action_status_accuracy']} / {measured['action_gap_accuracy']} | {measured['action_input_consistency']} | {measured['action_communication']} | {measured['unsupported_cause_claims']} |")
    lines.extend(["", "All denominators include missing and failed predictions. Complete requests, returned evidence IDs, errors and per-case diagnoses: `replay/cases.jsonl`.", "",
                  "Baseline: power-only transition detection; action always defers for verification and operator escalation without querying tools. No action detection credit is awarded.",
                  "Correct expected insufficiency is a pass; a resource gap is not automatically a predictor failure. Required classification, cause status and gap must match without private defaults or undocumented alternatives.",
                  "Communication measures declared event/asset/interval/state/uncertainty/next-step fields; narrative usefulness remains human-reviewed. Prerequisite completeness requires the expected or alternative action set with evidence (or the required safe refusal). Separate action_prerequisite_safety can pass on safe refusal without completeness credit.", ""])
    return "\n".join(lines)


def _review(bundle: Bundle, views: list[dict], labels: list[dict], runs: dict) -> bytes:
    source_events = {event["id"]: event for event in bundle.sources["events"]}
    documents = {document["id"]: document for document in bundle.sources["documents"]}
    cases = {case["case_id"]: case for case in runs["reference"]["cases"]}
    lines = ["# Operations Dataset Review", "", "Visibility: evaluator_only. Do not give this review, labels, provenance or raw pack paths to a predictor.", "",
             "Reports anchor authored events, not universal policy. Every KB action rule, waveform, cadence, alarm code, topology detail and availability assumption is simulated.",
             "Source PDF/extraction hashes and exact page-scoped quotes are retained only in private provenance. Byte/quote agreement is not proof that a report is universally correct.",
             "Yallourn support concerns synchronous-unit combinations/system strength, not replacement of exactly 597 MW. Protection/control classification and flooding/control-circuit explanations are later forensic truth.",
             "Murray trip/restoration source times have minute precision; synthetic seconds do not improve report precision. No generation or customer load loss is attributed to that busbar event; pre-existing outages are not new trips.",
             "AEST means fixed UTC+10, including October and January. Current policy without valid_to is assumed valid indefinitely; topology is static synthetic context.",
             "Mode defaults: 300-second latest-sample freshness; 300-second detection latency budget unless authored; zero extra event-time tolerance beyond the source interval. Thresholds (5/25 MW, 10%/80% nominal voltage) are synthetic decision assumptions.",
             "Action starts from explicit simulated operator notifications, preserving source intervals and assuming notification availability at cutoff, not report availability. Current affected-asset SCADA and scoped KB/topology/tool prerequisites still require verification. Alarm records are latched event indications, not periodically sampled freshness evidence; latest conflicting protection/return indications refuse.",
             "No physical operations, model calls, optimizer or training loop. Future campaign ownership remains the public OptimizationService.", "", replay_review(runs)]
    for view, label in zip(views, labels):
        case = cases[label["case_id"]]
        expected = label["expected"]
        lines.extend([f"## {label['case_id']} ({label['scenario_id']})", "",
                      f"Task/split/incident: {label['kind']} / {label['split']} / {label['incident_id']}. Template: {label['template_id']}; variant: {label['variant']}.",
                      "Assets: " + "; ".join(f"{asset['name']} [{asset['asset_id']}, {asset['kind']}]" for asset in view["assets"]),
                      f"Window starts {view['window_start']} ({_aest(view['window_start'])}); decision {view['decision_time']} ({_aest(view['decision_time'])}).",
                      f"Both record event time and availability time must be at/before decision; event time must also be at/after window start. Latest-sample freshness {view['limits']['max_age_seconds']} seconds; latency budget {label['max_detection_latency_seconds']} seconds; extra tolerance {label['event_time_tolerance_seconds']} seconds.",
                      f"Expected {label['kind']} outcome: {_text(expected)}",
                      f"Given event conditions (action inputs only): {_text(view.get('event_conditions', []))}",
                      f"Observable class: {_text(label['observable_classification'])}. Contemporaneous cause status: {expected['cause_status']}.",
                      "", "Source instance bindings:", "",
                      "| Canonical Asset | Source Aliases | Bound Points | Binding |",
                      "| --- | --- | --- | --- |"])
        for binding in label["asset_bindings"]:
            lines.append(f"| {binding['asset_id']} | {', '.join(binding['aliases'])} | {', '.join(binding['scada_points'])} | synthetic only; {binding['cim_id']} |")
        lines.extend(["", "Valid simulated action-policy prerequisites:"])
        for rule in label["action_prerequisites"]:
            lines.append(f"- {rule['knowledge_id']}, valid from {rule['valid_from']}, available {rule['available_at']}: {', '.join(rule['action_ids'])}. Required tools: {', '.join(rule['required_tools'])}. Rationale: {rule['rationale']}")
        if not label["action_prerequisites"]:
            lines.append("- No applicable as-of rule; required response is judged independently from the private label.")
        lines.append("")
        for event_id in label["source_event_ids"]:
            event = source_events[event_id]
            lines.append(f"Source event {event_id}: {event['reported_time']}; {event['precision']} precision; UTC interval {_text(event['event_interval'])} (exclusive end).")
            for document_id, page in sorted({(reference["document_id"], reference["page"]) for reference in event["source_refs"]}):
                document = documents[document_id]
                lines.append(f"Source reference {document['id']} page {page}; PDF SHA-256 {document['pdf_sha256']}; extraction SHA-256 {document['extraction_sha256']}. Exact quote: private provenance.")
        lines.extend(["", "Later/investigator truth, not early inference:", *_forensic_lines(label["forensic_truth"]), "",
                      f"Synthetic authoring assumptions: {_text(label['assumptions'])}; parameters: {_text(label['parameters'])}.",
                      "Public evidence row counts: " + _text({tool: len(rows) for tool, rows in view["evidence"].items()}),
                      "Reference produced: " + _text({key: value for key, value in (case["produced"] or {}).items() if key not in ("action_evidence", "evidence_ids")}),
                      f"Pass: {case['passed']}; observed gap: {case['observed_gap']}; failure gap: {case['failure_gap']}; failures: {_text(case['failures'])}.",
                      f"Next diagnosis: {case['remedy'] or 'No failed expectation in this synthetic case; no generalization claim.'}"])
        lines.extend(_sample_lines(view, case["produced"], expected))
        lines.extend(["", "Tool trace summary (full returned IDs/quality retained in replay/cases.jsonl):"])
        for call in case["trace"]:
            quality_counts = dict(sorted(Counter(row["quality"] for row in call.get("quality", [])).items()))
            lines.append(f"- Request {_text(call['request'])}; outcome {call['outcome']}; rows {call.get('count', 0)}; complete {call.get('complete')}; first six evidence IDs {_text(call.get('evidence_ids', [])[:6])}; quality counts {_text(quality_counts)}.")
        lines.extend(["", "Counterfactual replay diagnostics:"])
        for run_name, run in sorted(runs.items()):
            if run_name == "reference":
                continue
            alternate = next(result for result in run["cases"] if result["case_id"] == label["case_id"])
            produced = alternate["produced"] or {}
            lines.append(f"- {run_name}: {produced.get('status', 'missing')}, {produced.get('event_type')}, assets {_text(produced.get('asset_ids', []))}; pass {alternate['passed']}; gap {alternate['failure_gap']}. {alternate['remedy'] or 'No failed expectation.'}")
        lines.append("")
    return ("\n".join(lines) + "\n").encode("utf-8")


class OperationsMode:
    id = "operations"
    version = 1
    input_resources = frozenset(schemas.RESOURCES)

    def build(self, bundle: Bundle) -> dict[str, bytes]:
        views = []
        labels = []
        for scenario in sorted(bundle.scenarios, key=lambda scenario: scenario["scenario_id"]):
            view = materialize_view(bundle, scenario, self.id, self.version)
            schemas.validate(schemas.PUBLIC_VIEW, view, "public view")
            label = _label(bundle, scenario, view)
            views.append(view)
            labels.append(label)
        templates = []
        for template_id in sorted({label["template_id"] for label in labels}):
            templates.append({"template_id": template_id, "mode": {"id": self.id, "version": self.version},
                              "slots": {"asset_classes": "Canonical inventory kind(s), unique aliases and resource point bindings",
                                        "event_window": "UTC start/decision; fixed-AEST source interval and precision; separate availability cutoff",
                                        "event_conditions": "Action-only independently authored operator notifications; given event type/assets/source intervals, never detection answers or proof of prerequisites",
                                        "observable_signature": "Good/fresh MW, digital, voltage transitions and available corroborating alarms",
                                        "impact": "Observed values only; no inference of pre-existing outages as new loss",
                                        "action_preconditions": "Given notification plus fresh current affected-asset state, valid KB event_type, full policy scope and required tool evidence; no pre-transition requirement",
                                        "uncertainty": "no_event vs insufficient_evidence; hypothesis vs established cause"},
                              "instances": [{key: label[key] for key in ("case_id", "incident_id", "source_event_ids", "asset_bindings", "time_context", "parameters", "action_prerequisites")} for label in labels if label["template_id"] == template_id]})
        runs = compare(views, labels, baseline=power_only, reference=reference)
        artifacts = comparison_artifacts(runs)
        for kind in ("detection", "action"):
            artifacts[f"{kind}.inputs.jsonl"] = jsonl_bytes([view for view in views if view["task"] == kind])
            artifacts[f"{kind}.labels.jsonl"] = jsonl_bytes([label for label in labels if label["kind"] == kind])
        artifacts["templates.json"] = json_bytes({"schema_version": 1, "visibility": "evaluator_only", "synthetic": True, "templates": templates})
        artifacts["REVIEW.md"] = _review(bundle, views, labels, runs)
        return artifacts