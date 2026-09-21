"""Versioned deterministic rule contracts for the bound telemetry table."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from ...config import settings


Role = Literal["anchor", "corroborator", "contextual"]

# Closed vocabulary shared with the local knowledge-base corpus
# (cyber_kb/normalize/vocabulary.py). Each value is anchored by exactly one rule below.
BehaviourClass = Literal[
    "beaconing", "credential_use", "directory_discovery", "privileged_session",
    "volume_anomaly",
]


@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str
    version: str
    name: str
    description: str
    query: str
    threshold: int
    score: int
    confidence: Literal["high", "medium", "low"]
    role: Role
    evidence_semantics: str
    behaviour_class: BehaviourClass
    technique_ids: tuple[str, ...] = ()


COMMON_PROJECT = "host, principal, event_count, first_seen, last_seen, evidence_ids"

_DECLARED: tuple[Rule, ...] = (
    Rule(
        "explicit_credential_burst", "1.0.0", "Explicit credential use",
        "A host and target principal produced at least five Windows event 4648 records.",
        """{TABLE}
| where source_time between (start .. end)
| where win_event_id == "4648" and isnotempty(target_host_name) and isnotempty(target_user_name)
| summarize event_count=count(), first_seen=min(source_time), last_seen=max(source_time), evidence_ids=make_list(resource_id, 8) by host=tolower(target_host_name), principal=tostring(target_user_name)
| where event_count >= rule_threshold
| project host, principal, event_count, first_seen, last_seen, evidence_ids
| order by host asc, principal asc, first_seen asc""",
        5, 35, "high", "anchor",
        "Up to eight resource IDs sampled from the same event-4648 host/principal group that crossed the threshold.",
        "credential_use",
        ("T1078", "T1550"),
    ),
    Rule(
        "tool_url_in_session_title", "1.0.0", "Tool URL in privileged session",
        "A CyberArk privileged-session record contains a WinPEAS or peass-ng reference and resolves a session host and user.",
        r'''{TABLE}
| where source_time between (start .. end)
| where product == "CYBERARK" and original_data has_any ("winPEAS", "peass-ng")
| extend host=tolower(coalesce(tostring(target_host_name), extract(@"dhost=([^\s]+)", 1, original_data))), principal=coalesce(tostring(target_user_name), extract(@"duser=([^\s]+)", 1, original_data))
| where isnotempty(host) and isnotempty(principal)
| summarize event_count=count(), first_seen=min(source_time), last_seen=max(source_time), evidence_ids=make_list(resource_id, 8) by host, principal
| where event_count >= rule_threshold
| project host, principal, event_count, first_seen, last_seen, evidence_ids
| order by host asc, principal asc, first_seen asc''',
        1, 30, "high", "anchor",
        "Up to eight resource IDs from CyberArk records whose payload contains the tool-title predicate for this session entity.",
        "privileged_session",
        ("T1082", "T1087"),
    ),
    Rule(
        "directory_enumeration_alert", "1.0.0", "Directory enumeration alert representation",
        "A Microsoft Defender for Identity Graph alert represents LDAP security-principal reconnaissance and exposes the actor host; principal attribution may remain unknown.",
        r'''{TABLE}
| where source_time between (start .. end)
| where product == "GRAPH_ALERTS" and original_data has "LdapSearchReconnaissanceSecurityAlert" and original_data has "Discovery"
| extend payload_host=extract(@'(?i)"description":"Actors on ([A-Za-z0-9._-]{1,64})', 1, original_data), payload_user=extract(@'(?i)"accountName":"([A-Za-z0-9._@\\-]{1,128})"', 1, original_data)
| extend host=tolower(coalesce(tostring(target_host_name), payload_host)), principal=coalesce(tostring(target_user_name), payload_user, "unattributed")
| where isnotempty(host) or principal != "unattributed"
| extend host=iff(isempty(host), "unattributed", host)
| summarize event_count=count(), first_seen=min(source_time), last_seen=max(source_time), evidence_ids=make_list(resource_id, 8) by host, principal
| where event_count >= rule_threshold
| project host, principal, event_count, first_seen, last_seen, evidence_ids
| order by host asc, principal asc, first_seen asc''',
        1, 25, "medium", "corroborator",
        "Up to eight resource IDs from Graph alert rows matching the discovery representation and the derived target entity.",
        "directory_discovery",
        ("T1087", "T1087.002", "T1069", "T1069.002", "T1482"),
    ),
    Rule(
        "event_volume_excursion", "1.0.0", "Entity event-volume excursion",
        "At least forty events occurred for one derived host/principal in a minute; synthesis only attaches bins within five minutes of a tool-title hit for the same entity.",
        # Qualification is deliberately not applied in KQL. The engine already tests the
        # threshold in Python, and filtering here would discard the busiest observed bin --
        # leaving an analyst unable to tell "no excursion" from "threshold unreachable".
        r'''{TABLE}
| where source_time between (start .. end)
| extend host=tolower(coalesce(tostring(target_host_name), extract(@"dhost=([^\s]+)", 1, original_data))), principal=coalesce(tostring(target_user_name), extract(@"duser=([^\s]+)", 1, original_data))
| where isnotempty(host) and isnotempty(principal)
| summarize event_count=count(), first_seen=min(source_time), last_seen=max(source_time), evidence_ids=make_list(resource_id, 8) by host, principal, minute=bin(source_time, 1m)
| top 50 by event_count desc
| project host, principal, event_count, first_seen, last_seen, evidence_ids
| order by event_count desc, host asc, principal asc, first_seen asc''',
        40, 15, "medium", "contextual",
        "Up to eight resource IDs from the same entity-minute bin; retained only when that bin is within five minutes of the same entity's tool-title hit.",
        "volume_anomaly",
    ),
    Rule(
        "fixed_interval_dns", "1.0.0", "Fixed-interval high-entropy DNS",
        "At least twenty DNS requests from one source use 15-character hexadecimal labels with approximately 120-second cadence.",
        r'''{TABLE}
| where source_time between (start .. end)
| where query_name matches regex "^[0-9A-Fa-f]{15}$" and isnotempty(source_address)
| sort by source_address asc, source_time asc
| serialize
| extend previous_time=prev(source_time), previous_source=prev(source_address)
| extend gap_seconds=iff(previous_source == source_address, datetime_diff("second", source_time, previous_time), long(null))
| summarize event_count=count(), names=dcount(query_name), cadence_matches=countif(gap_seconds between (115 .. 125)), first_seen=min(source_time), last_seen=max(source_time), evidence_ids=make_list(resource_id, 8) by host=tostring(source_address)
| extend principal="unattributed"
| where event_count >= rule_threshold and cadence_matches >= 10
| project host, principal, event_count, first_seen, last_seen, evidence_ids
| order by host asc, first_seen asc''',
        20, 25, "medium", "anchor",
        "Up to eight resource IDs from the same DNS source group; the group also has at least ten adjacent 115–125 second intervals.",
        "beaconing",
        ("T1071.004", "T1568.002"),
    ),
)


#: Queries are declared against `{TABLE}` and bound to the configured table once, here.
RULES: tuple[Rule, ...] = tuple(
    replace(rule, query=rule.query.replace("{TABLE}", settings.table)) for rule in _DECLARED
)


def registry() -> tuple[Rule, ...]:
    """Return the immutable, deterministically ordered rule registry."""
    return RULES
