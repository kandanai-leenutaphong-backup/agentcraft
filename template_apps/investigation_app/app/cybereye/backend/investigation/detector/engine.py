"""Concurrent rule execution and pure situation synthesis."""

from __future__ import annotations

import asyncio
import hashlib
import time
from collections import defaultdict
from datetime import datetime
from typing import Any, AsyncIterator, Mapping

from situation_detector import (
    BATTERY_COMPLETED,
    RULE_COMPLETED,
    RULE_STARTED,
    normalize_config,
    run_battery_async,
    selected_rules,
    stream_battery,
)

from ...models import Pattern, RuleExecution, ScanRequest, ScanResponse, ScanSummary, Situation, SituationMetric
from .composition import default_configuration, rule_from_declaration
from .explain import (
    derive_execution_observation,
    derive_factor_derivation,
    derive_rule_explanation,
    derive_situation_metrics,
)
from .rules import Rule, registry


def _dt(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _ids(value: Any) -> list[str]:
    return [str(item) for item in value[:8]] if isinstance(value, list) else []


def validate_window(request: ScanRequest) -> None:
    if request.end <= request.start:
        raise ValueError("scan end must be after start")
    if (request.end - request.start).total_seconds() > 48 * 3600:
        raise ValueError("scan window is capped at 48 hours")


def _situation_id(host: str, principal: str, first_seen: datetime) -> str:
    anchor = first_seen.isoformat()
    return "cyb_" + hashlib.sha256(f"{host}|{principal}|{anchor}".encode()).hexdigest()[:12]


def _execution(rule: Rule, rows: list[dict[str, Any]], elapsed_ms: int) -> RuleExecution:
    observation = derive_execution_observation(rule, rows, elapsed_ms)
    return RuleExecution(
        rule_id=rule.rule_id, version=rule.version, name=rule.name, role=rule.role,
        hit_count=observation["groups_qualified"], elapsed_ms=elapsed_ms,
        explanation=derive_rule_explanation(rule), observation=observation,
    )


def _execution(rule: Rule, rows: list[dict[str, Any]], elapsed_ms: int) -> RuleExecution:
    observation = derive_execution_observation(rule, rows, elapsed_ms)
    return RuleExecution(
        rule_id=rule.rule_id, version=rule.version, name=rule.name, role=rule.role,
        hit_count=observation["groups_qualified"], elapsed_ms=elapsed_ms,
        explanation=derive_rule_explanation(rule), observation=observation,
    )


def _rule_payload(rule: Rule) -> dict[str, Any]:
    return {
        "rule_id": rule.rule_id, "version": rule.version, "name": rule.name,
        "description": rule.description, "role": rule.role,
        "evidence_semantics": rule.evidence_semantics,
    }


def _hit(rule: Rule, row: dict[str, Any]) -> Pattern | None:
    count = int(row.get("event_count") or 0)
    if count < rule.threshold:
        return None
    evidence_ids = _ids(row.get("evidence_ids"))
    return Pattern(
        detector=rule.rule_id,
        rule_id=rule.rule_id,
        rule_version=rule.version,
        label=rule.name,
        description=rule.description,
        observed_fact=f"{count} threshold-qualified record(s) for {row.get('principal') or 'unattributed'} on {row.get('host') or 'unattributed'}.",
        count=count,
        score=rule.score,
        confidence=rule.confidence,
        role=rule.role,
        behaviour_class=rule.behaviour_class,
        technique_ids=list(rule.technique_ids),
        first_seen=_dt(row["first_seen"]),
        last_seen=_dt(row["last_seen"]),
        summary=rule.description,
        evidence_columns=["resource_id"],
        evidence_ids=evidence_ids,
        evidence_semantics=rule.evidence_semantics,
        derivation=derive_factor_derivation(rule, row, count, evidence_ids),
    )


def synthesize(request: ScanRequest, results: dict[str, list[dict[str, Any]]],
               active: tuple[Rule, ...] | None = None) -> list[Situation]:
    active = registry() if active is None else active
    rules = {rule.rule_id: rule for rule in active}
    grouped: dict[tuple[str, str], list[Pattern]] = defaultdict(list)
    tool_times: dict[tuple[str, str], list[datetime]] = defaultdict(list)
    host_scoped: dict[str, list[Pattern]] = defaultdict(list)

    for rule in active:
        if rule.rule_id == "event_volume_excursion":
            continue
        for row in results.get(rule.rule_id, []):
            factor = _hit(rule, row)
            if factor is None:
                continue
            key = (str(row.get("host") or "unattributed").lower(), str(row.get("principal") or "unattributed"))
            if rule.rule_id == "directory_enumeration_alert" and key[1] == "unattributed":
                host_scoped[key[0]].append(factor)
                continue
            grouped[key].append(factor)
            if rule.rule_id == "tool_url_in_session_title":
                tool_times[key].append(factor.first_seen)

    # The volume rule is correlational, not standalone, and it may be disabled or absent
    # from a supplied configuration; synthesis then simply has no volume factor to attach.
    volume_rule = rules.get("event_volume_excursion")
    for row in results.get(volume_rule.rule_id, []) if volume_rule else []:
        key = (str(row.get("host") or "unattributed").lower(), str(row.get("principal") or "unattributed"))
        first = _dt(row["first_seen"])
        if not any(abs((first - tool).total_seconds()) <= 300 for tool in tool_times.get(key, [])):
            continue
        factor = _hit(volume_rule, row)
        if factor is not None:
            grouped[key].append(factor)

    for host, factors in host_scoped.items():
        matching_keys = [key for key in grouped if key[0] == host]
        if matching_keys:
            for key in matching_keys:
                grouped[key].extend(factors)
        else:
            grouped[(host, "unattributed")].extend(factors)

    situations: list[Situation] = []
    for (host, principal), factors in grouped.items():
        factors.sort(key=lambda item: (item.first_seen, item.rule_id))
        score = sum(item.score for item in factors)
        anchors = sum(item.role == "anchor" for item in factors)
        if score >= 80 and anchors >= 2:
            severity, confidence = "critical", "high"
        elif score >= 50 or len(factors) >= 2:
            severity, confidence = "high", "medium"
        else:
            severity = "medium" if score >= 25 else "low"
            confidence = "medium" if anchors else "low"
        first_seen = min(item.first_seen for item in factors)
        last_seen = max(item.last_seen for item in factors)
        thresholds = {rule_id: rule.threshold for rule_id, rule in rules.items()}
        situations.append(Situation(
            situation_id=_situation_id(host, principal, first_seen), host=host, principal=principal,
            severity=severity, confidence=confidence, first_seen=first_seen, last_seen=last_seen,
            detector_count=len({item.rule_id for item in factors}), patterns=factors,
            metrics=[SituationMetric.model_validate(metric) for metric in
                     derive_situation_metrics(factors, severity, confidence, thresholds)],
        ))
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    situations.sort(key=lambda item: (rank[item.severity], -item.detector_count, item.first_seen, item.host, item.principal))
    return situations


class DetectorEngine:
    """Domain scanner: it owns rules, evidence semantics and situation synthesis, and
    runs every rule through the shared `situation_detector` battery."""

    def __init__(self, adx: Any, configuration: dict[str, Any] | None = None) -> None:
        self.adx = adx
        self.configuration = normalize_config(configuration) if configuration is not None else default_configuration()
        self.rules: tuple[Rule, ...] = tuple(
            rule_from_declaration(entry) for entry in selected_rules(self.configuration)
        )
        self._by_id = {rule.rule_id: rule for rule in self.rules}

    async def _query(self, entry: Mapping[str, Any], window: Mapping[str, Any]) -> dict[str, Any]:
        started = time.monotonic()
        result = await self.adx.parameterized(
            entry["query"], {"start": window["start"], "end": window["end"], "rule_threshold": entry["parameters"].get("threshold", 1)},
            int(entry.get("processing", {}).get("max_rows", 100)),
        )
        return {
            "columns": list(result.columns), "rows": [list(row) for row in result.rows],
            "elapsed_ms": round((time.monotonic() - started) * 1000),
        }

    def _execute(self, entry: Mapping[str, Any], window: Mapping[str, Any]):
        return self._query(entry, window)

    def _process(self, entry: Mapping[str, Any], envelope: Mapping[str, Any],
                 window: Mapping[str, Any]) -> dict[str, Any]:
        rule = self._by_id[entry["id"]]
        records = [dict(zip(envelope["columns"], row)) for row in envelope["rows"]]
        elapsed_ms = int(envelope["elapsed_ms"])
        observation = derive_execution_observation(rule, records, elapsed_ms)
        return {
            "records": records, "observation": observation, "elapsed_ms": elapsed_ms,
            "hit_count": observation["groups_qualified"],
            "explanation": derive_rule_explanation(rule),
        }

    def _summarizer(self, request: ScanRequest, sink: list[Situation]):
        """Domain summary for the battery; the synthesized situations are kept for the
        response rather than synthesized a second time."""
        def summarize(entries: list[dict[str, Any]], window: Mapping[str, Any]) -> dict[str, Any]:
            situations = synthesize(
                request, {entry["rule_id"]: entry["processed"]["records"] for entry in entries}, self.rules,
            )
            sink.extend(situations)
            return {
                "tests_run": len(entries),
                "situations": len(situations),
                "critical": sum(item.severity == "critical" for item in situations),
                "high": sum(item.severity == "high" for item in situations),
                "evidence_rows": sum(factor.count for item in situations for factor in item.patterns),
            }
        return summarize

    def _execution_of(self, entry: Mapping[str, Any]) -> RuleExecution:
        rule = self._by_id[entry["rule_id"]]
        processed = entry["processed"]
        return RuleExecution(
            rule_id=rule.rule_id, version=rule.version, name=rule.name, role=rule.role,
            hit_count=processed["hit_count"], elapsed_ms=processed["elapsed_ms"],
            explanation=processed["explanation"], observation=processed["observation"],
        )

    async def scan(self, request: ScanRequest) -> ScanResponse:
        validate_window(request)
        started = time.monotonic()
        situations: list[Situation] = []
        result = await run_battery_async(
            self.configuration, {"start": request.start, "end": request.end},
            self._execute, self._process, summarize=self._summarizer(request, situations),
        )
        return self._response(request, situations, started, result["summary"],
                              [self._execution_of(entry) for entry in result["rules"]])

    async def stream_scan(self, request: ScanRequest) -> AsyncIterator[dict[str, Any]]:
        started = time.monotonic()
        try:
            validate_window(request)
            situations: list[Situation] = []
            executions: list[RuleExecution] = []
            battery = stream_battery(
                self.configuration, {"start": request.start, "end": request.end},
                self._execute, self._process, summarize=self._summarizer(request, situations),
            )
            summary: dict[str, Any] = {}
            async for event in battery:
                if event["event"] == RULE_STARTED:
                    rule = self._by_id[event["data"]["rule_id"]]
                    yield {"event": "rule_started",
                           "data": {**_rule_payload(rule), "explanation": derive_rule_explanation(rule)}}
                elif event["event"] == RULE_COMPLETED:
                    execution = self._execution_of(event["data"])
                    executions.append(execution)
                    rule = self._by_id[execution.rule_id]
                    yield {"event": "rule_completed",
                           "data": {**_rule_payload(rule), "hit_count": execution.hit_count,
                                    "elapsed_ms": execution.elapsed_ms, "explanation": execution.explanation,
                                    "observation": execution.observation}}
                elif event["event"] == BATTERY_COMPLETED:
                    summary = event["data"]["summary"]
            for situation in situations:
                yield {"event": "situation_partial", "data": situation.model_dump(mode="json")}
                for factor in situation.patterns:
                    yield {"event": "evidence_started", "data": {"situation_id": situation.situation_id, "rule_id": factor.rule_id}}
                    yield {"event": "evidence_completed", "data": {"situation_id": situation.situation_id, "rule_id": factor.rule_id, "evidence_count": len(factor.evidence_ids)}}
                yield {"event": "situation", "data": situation.model_dump(mode="json")}
            response = self._response(request, situations, started, summary, executions)
            yield {"event": "done", "data": response.model_dump(mode="json")}
        except Exception as exc:
            yield {"event": "error", "data": {"error_code": type(exc).__name__, "message": str(exc)}}

    @staticmethod
    def _response(request: ScanRequest, situations: list[Situation], started: float,
                  summary: Mapping[str, Any], executions: list[RuleExecution] | None = None) -> ScanResponse:
        return ScanResponse(
            window_start=request.start, window_end=request.end, situations=situations,
            rule_executions=executions or [],
            summary=ScanSummary(
                situations=int(summary.get("situations", len(situations))),
                critical=int(summary.get("critical", 0)), high=int(summary.get("high", 0)),
                evidence_rows=int(summary.get("evidence_rows", 0)),
                elapsed_ms=round((time.monotonic() - started) * 1000),
            ),
        )
