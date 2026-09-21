"""Observed public Windows patterns, never a per-event maliciousness label."""

from datetime import datetime
import time
from types import SimpleNamespace

from app.data.ontology import RULE_VERSION, rule_matches

from ..data.telemetry import CosmosTelemetry
from ..models import Pattern, RuleExecution, ScanRequest, ScanResponse, ScanSummary, Situation


class PublicDetector:
    def __init__(self, telemetry: CosmosTelemetry):
        self.telemetry = telemetry
        self.rules = (SimpleNamespace(rule_id=RULE_VERSION, name="Rundll32 DLL in Temp", version=RULE_VERSION,
            role="anchor", score=25, confidence="medium", behaviour_class="execution", threshold=1,
            technique_ids=("T1218.011",), description="Sysmon process creation: rundll32.exe with DLL in temp/tmp"),)
        self.configuration = {"profile": "public-cosmos", "rule_version": RULE_VERSION,
            "partition": telemetry.partition, "unsupported": ["authentication", "dns", "firewall", "privileged_session"],
            "acceptance": "development smoke only; no malicious ground truth"}

    async def scan(self, request: ScanRequest) -> ScanResponse:
        started = time.monotonic()
        observed = await self.telemetry.events(self.telemetry.partition, request.start, request.end)
        matches = {item["resource_id"]: item for item in observed if rule_matches(item)}
        situations = []
        covered = set()
        for case in await self.telemetry.cases(self.telemetry.partition):
            for alarm in await self.telemetry.alarms(self.telemetry.partition, case["id"]):
                if alarm["rule_version"] != RULE_VERSION or not alarm["derived"]:
                    raise ValueError("unsupported alarm derivation")
                evidence = await self.telemetry.evidence(self.telemetry.partition, alarm["event_refs"])
                if any(not rule_matches(item) for item in evidence):
                    raise ValueError("stale derived alarm evidence")
                selected = [item for item in evidence if item["resource_id"] in matches]
                if not selected:
                    continue
                if len(selected) > 8:
                    raise ValueError("narrow window to at most eight matching records")
                covered.update(item["resource_id"] for item in selected)
                first = min(datetime.fromisoformat(item["timestamp"]) for item in selected)
                last = max(datetime.fromisoformat(item["timestamp"]) for item in selected)
                pattern = Pattern(detector=RULE_VERSION, rule_id=RULE_VERSION, rule_version=RULE_VERSION,
                    label=self.rules[0].name, description=self.rules[0].description,
                    observed_fact=f"{len(selected)} Sysmon process-creation records match the deterministic pattern.",
                    count=len(selected), score=25, confidence="medium", role="anchor", behaviour_class="execution",
                    technique_ids=["T1218.011"], first_seen=first, last_seen=last,
                    summary="Derived suspicious pattern in public emulation; authorization and maliciousness unknown.",
                    evidence_columns=["resource_id"], evidence_ids=[item["resource_id"] for item in selected],
                    evidence_semantics="Exact normalized source records; emulation membership is not an attack label.",
                    derivation={"case_id": case["id"], "alarm_id": alarm["id"], "partition": self.telemetry.partition,
                                "source": self.telemetry.source, "derived": True})
                situations.append(Situation(situation_id=alarm["id"], host=selected[0]["host"],
                    principal=selected[0]["fields"].get("User", "unattributed"), severity="medium", confidence="medium",
                    first_seen=first, last_seen=last, detector_count=1, patterns=[pattern]))
        if covered != set(matches):
            raise ValueError("derived alarm membership does not cover observed pattern")
        elapsed = round((time.monotonic() - started) * 1000)
        return ScanResponse(window_start=request.start, window_end=request.end, situations=situations,
            summary=ScanSummary(situations=len(situations), critical=0, high=0, evidence_rows=len(matches), elapsed_ms=elapsed),
            rule_executions=[RuleExecution(rule_id=RULE_VERSION, version=RULE_VERSION, name=self.rules[0].name,
                role="anchor", hit_count=len(situations), elapsed_ms=elapsed,
                observation={"events_read": len(observed), "pattern_matches": len(matches), "derived": True,
                             "unsupported_rules": self.configuration["unsupported"]})])

    async def stream_scan(self, request: ScanRequest):
        yield {"event": "rule_started", "data": {"rule_id": RULE_VERSION, "name": self.rules[0].name}}
        try:
            result = await self.scan(request)
            yield {"event": "rule_completed", "data": result.rule_executions[0].model_dump(mode="json")}
            for situation in result.situations:
                yield {"event": "situation", "data": situation.model_dump(mode="json")}
            yield {"event": "done", "data": result.model_dump(mode="json")}
        except (ValueError, RuntimeError) as error:
            yield {"event": "error", "data": {"error_code": type(error).__name__, "message": str(error)}}