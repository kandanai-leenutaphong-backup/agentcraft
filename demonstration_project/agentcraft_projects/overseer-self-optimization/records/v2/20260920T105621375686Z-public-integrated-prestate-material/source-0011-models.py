"""HTTP and internal contracts for the bounded CyberEye runtime."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


Severity = Literal["critical", "high", "medium", "low"]


class ScanRequest(BaseModel):
    start: datetime = datetime.fromisoformat("2026-08-13T02:30:00+00:00")
    end: datetime = datetime.fromisoformat("2026-08-13T03:40:59+00:00")


class Pattern(BaseModel):
    detector: str
    rule_id: str
    rule_version: str
    label: str
    description: str
    observed_fact: str
    count: int
    score: int
    confidence: Literal["high", "medium", "low"]
    role: Literal["anchor", "corroborator", "contextual"]
    behaviour_class: str = ""
    technique_ids: list[str] = Field(default_factory=list, max_length=12)
    first_seen: datetime
    last_seen: datetime
    summary: str
    evidence_columns: list[str] = Field(default_factory=list, max_length=16)
    evidence_ids: list[str] = Field(default_factory=list, max_length=8)
    evidence_semantics: str
    derivation: dict[str, Any] = Field(default_factory=dict)


class MetricContribution(BaseModel):
    source: str
    detail: str
    value: str


class SituationMetric(BaseModel):
    metric_id: str
    label: str
    value: str
    definition: str
    derivation: str
    contributions: list[MetricContribution] = Field(default_factory=list, max_length=16)


class RuleExecution(BaseModel):
    rule_id: str
    version: str
    name: str
    role: str
    hit_count: int
    elapsed_ms: int
    explanation: dict[str, Any] = Field(default_factory=dict)
    observation: dict[str, Any] = Field(default_factory=dict)


class Situation(BaseModel):
    situation_id: str
    host: str
    principal: str
    severity: Severity
    confidence: Literal["high", "medium", "low"]
    first_seen: datetime
    last_seen: datetime
    detector_count: int
    patterns: list[Pattern]
    metrics: list[SituationMetric] = Field(default_factory=list)
    status: Literal["open", "reviewed"] = "open"
    historical_replay: Literal[True] = True


class ScanSummary(BaseModel):
    situations: int
    critical: int
    high: int
    evidence_rows: int
    elapsed_ms: int


class ScanResponse(BaseModel):
    kind: Literal["cybereye_scan"] = "cybereye_scan"
    window_start: datetime
    window_end: datetime
    situations: list[Situation]
    summary: ScanSummary
    rule_executions: list[RuleExecution] = Field(default_factory=list)
    historical_replay: Literal[True] = True


class QueryRequest(BaseModel):
    query: str = Field(min_length=1, max_length=12_000)
    max_rows: int = Field(default=100, ge=1, le=1000)


class QueryResponse(BaseModel):
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    truncated: bool
    max_rows: int
    elapsed_ms: int
    client_request_id: str


class SessionResponse(BaseModel):
    session_id: str
    agent_id: Literal["cyber_defender"] = "cyber_defender"


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    situation: Situation | None = None
