"""Evidence-preserving Windows emulation projection; payload commands are inert data."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import PureWindowsPath
import re
import uuid
from xml.etree import ElementTree

from .model import Graph


TRANSFORM_VERSION = "public-windows-v1"
RULE_VERSION = "rundll32-temp-dll-v1"
NAMESPACE = "{http://schemas.microsoft.com/win/2004/08/events/event}"


def digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def qualified_id(kind: str, *parts: str) -> str:
    if not all(isinstance(part, str) and part.strip() for part in parts):
        raise ValueError("empty identity component")
    return kind + "-" + digest(json.dumps(parts, ensure_ascii=True, separators=(",", ":")).encode())


def guid(value: str) -> str:
    if not value or value == "-":
        return ""
    parsed = uuid.UUID(value.strip("{}"))
    return str(parsed) if parsed.int else ""


def parse_records(payload: bytes) -> list[dict]:
    if len(payload) > 8 * 1024 * 1024 or b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
        raise ValueError("XML size/declaration refused")
    records = []
    offset = 0
    for ordinal, raw in enumerate(payload.splitlines(keepends=True), 1):
        start = offset
        offset += len(raw)
        if not raw.strip():
            continue
        if len(raw) > 1024 * 1024:
            raise ValueError("record size limit")
        root = ElementTree.fromstring(raw)
        if root.tag != NAMESPACE + "Event":
            raise ValueError("unsupported event namespace")
        system = root.find(NAMESPACE + "System")
        if system is None:
            raise ValueError("missing System")
        fields = {}
        for node in root.findall(f"{NAMESPACE}EventData/{NAMESPACE}Data"):
            name = node.attrib["Name"]
            if name in fields:
                raise ValueError("duplicate event field")
            fields[name] = node.text or ""
        created = system.find(NAMESPACE + "TimeCreated")
        provider = system.find(NAMESPACE + "Provider")
        source_time = created.attrib.get("SystemTime", "") if created is not None else ""
        if not source_time.endswith("Z"):
            raise ValueError("missing UTC event time")
        datetime.fromisoformat(source_time)
        records.append({"ordinal": ordinal, "byte_offset": start, "byte_length": len(raw),
                        "raw_sha256": digest(raw), "fields": fields, "timestamp": source_time,
                        "host": system.findtext(NAMESPACE + "Computer", "").strip().casefold(),
                        "event_id": system.findtext(NAMESPACE + "EventID", ""),
                        "event_record_id": system.findtext(NAMESPACE + "EventRecordID", ""),
                        "provider": provider.attrib.get("Name", "") if provider is not None else "",
                        "channel": system.findtext(NAMESPACE + "Channel", "")})
    if not records:
        raise ValueError("empty source")
    return records


def rule_matches(event: dict) -> bool:
    fields = event["fields"]
    command = fields.get("CommandLine", "").casefold()
    return (event["provider"] == "Microsoft-Windows-Sysmon" and event["event_id"] == "1"
            and PureWindowsPath(fields.get("Image", "")).name.casefold() == "rundll32.exe"
            and bool(re.search(r"\\(?:temp|tmp)\\[^\r\n]*\.dll(?:[,\s\"]|$)", command)))


def normalize_windows(payload: bytes, source: dict) -> dict:
    for key in ("source_id", "scenario_id", "commit", "source_path", "sha256", "source_url"):
        if not source.get(key):
            raise ValueError(f"missing source {key}")
    if digest(payload) != source["sha256"]:
        raise ValueError("source membership digest mismatch")
    partition = qualified_id("scenario", source["source_id"], source["scenario_id"], source["commit"], source["sha256"])
    graph = Graph()
    events = []
    omissions = Counter()
    source_pin = {key: source[key] for key in ("source_id", "scenario_id", "commit", "source_path", "sha256", "source_url")}

    def node(label: str, node_id: str, name: str, event: dict, **properties):
        item = graph.node(label, node_id, name, partition=partition, source=source_pin, **properties)
        item.observe("evidence_refs", event["resource_id"])
        item.touch(event["timestamp"])
        return item

    def edge(label: str, from_id: str, to_id: str, event: dict):
        item = graph.edge(label, from_id, to_id, partition=partition, source=source_pin)
        item.observe("evidence_refs", event["resource_id"])
        item.touch(event["timestamp"])

    for record in parse_records(payload):
        raw_ref = {**source_pin, **{key: record[key] for key in ("ordinal", "byte_offset", "byte_length", "raw_sha256")}}
        resource_id = f"event://{partition}/{record['ordinal']}"
        event = {**record, "id": qualified_id("event", partition, str(record["ordinal"])),
                 "resource_id": resource_id, "partition": partition, "kind": "event", "source": raw_ref,
                 "entity_refs": {}, "label_status": "unlabelled", "transform_version": TRANSFORM_VERSION}
        events.append(event)
        node("Event", event["id"], record["event_record_id"] or str(record["ordinal"]), event)
        if not record["host"]:
            omissions["missing_host"] += 1
            continue
        host_id = qualified_id("host", partition, record["host"])
        node("Host", host_id, record["host"], event)
        edge("EVIDENCES_ENTITY", event["id"], host_id, event)
        event["entity_refs"]["host"] = host_id
        fields = record["fields"]
        account = fields.get("User", "").strip()
        user_id = ""
        if "\\" in account and all(account.split("\\", 1)):
            domain, username = account.split("\\", 1)
            domain_id = qualified_id("domain", partition, "windows-account-domain", domain.casefold())
            user_id = qualified_id("user", partition, domain.casefold(), username.casefold())
            node("Domain", domain_id, domain, event, domain_kind="windows-account-domain")
            node("Identity", user_id, account, event)
            edge("MEMBER_OF_DOMAIN", user_id, domain_id, event)
            edge("EVIDENCES_ENTITY", event["id"], user_id, event)
            event["entity_refs"].update(user=user_id, domain=domain_id)
        else:
            omissions["missing_qualified_user"] += 1
        if record["provider"] != "Microsoft-Windows-Sysmon" or record["event_id"] != "1":
            omissions["unsupported_process_event"] += 1
            continue
        process_guid = guid(fields.get("ProcessGuid", ""))
        if not process_guid:
            omissions["missing_process_guid_no_pid_join"] += 1
            continue
        process_id = qualified_id("process", partition, host_id, process_guid)
        node("Process", process_id, fields.get("Image") or process_guid, event, process_guid=process_guid)
        graph.nodes[process_id].observe("observation_roles", "process_creation")
        edge("EVIDENCES_ENTITY", event["id"], process_id, event)
        edge("PROCESS_ON_HOST", process_id, host_id, event)
        if user_id:
            edge("EXECUTED_AS", process_id, user_id, event)
        event["entity_refs"]["process"] = process_id
        parent_guid = guid(fields.get("ParentProcessGuid", ""))
        if parent_guid:
            parent_id = qualified_id("process", partition, host_id, parent_guid)
            if parent_id == process_id:
                raise ValueError("self parent refused")
            node("Process", parent_id, fields.get("ParentImage") or parent_guid, event, process_guid=parent_guid)
            graph.nodes[parent_id].observe("observation_roles", "parent_field_reference")
            edge("PARENT_OF", parent_id, process_id, event)
            edge("PROCESS_ON_HOST", parent_id, host_id, event)
            event["entity_refs"]["parent_process"] = parent_id
        else:
            omissions["missing_parent_guid_no_pid_join"] += 1

    incident_id = qualified_id("incident", partition)
    matches = [event for event in events if rule_matches(event)]
    alarm_id = qualified_id("alarm", partition, RULE_VERSION)
    incident = {"id": incident_id, "resource_id": f"incident://{partition}", "partition": partition,
                "kind": "incident", "ground_truth_kind": "emulation_scenario", "derived": True,
                "title": source.get("title", source["scenario_id"]), "source": source_pin,
                "scenario_narrative": source.get("narrative", ""),
                "event_refs": [event["resource_id"] for event in events],
                "alarm_refs": [alarm_id] if matches else [], "knowledge_refs": ["situation_type:T1218.011"]}
    alarms = []
    if matches:
        alarms.append({"id": alarm_id, "resource_id": f"alarm://{partition}/{RULE_VERSION}",
                       "partition": partition, "kind": "alarm", "derived": True, "rule_version": RULE_VERSION,
                       "rule_description": "Sysmon EventID 1: rundll32.exe with a DLL path beneath temp/tmp in CommandLine",
                       "incident_id": incident_id, "source": source_pin,
                       "event_refs": [event["resource_id"] for event in matches],
                       "classification": "suspicious-pattern-not-malicious-ground-truth",
                       "knowledge_refs": ["situation_type:T1218.011"]})
    for event in events:
        node("Incident", incident_id, incident["title"], event, derived=True, ground_truth_kind="emulation_scenario")
        edge("CONTAINS_EVENT", incident_id, event["id"], event)
        if event in matches:
            node("SecurityAlert", alarm_id, RULE_VERSION, event, derived=True, rule_version=RULE_VERSION)
            edge("HAS_ALARM", incident_id, alarm_id, event)
            edge("SUPPORTED_BY", alarm_id, event["id"], event)
    creation_ids = {event["entity_refs"].get("process") for event in events}
    parent_ids = {event["entity_refs"]["parent_process"] for event in events if "parent_process" in event["entity_refs"]}
    omissions["parent_creation_not_in_export"] = len(parent_ids - creation_ids)

    def properties(item):
        return {**item.props, **{key: sorted(values) for key, values in item.observed.items()}}

    package = {"transform_version": TRANSFORM_VERSION, "partition": partition, "source": source_pin,
               "cosmos": [incident, *alarms, *events],
               "gremlin": {"vertices": [{"id": item.node_id, "label": item.label, "name": item.name,
                                            "properties": properties(item)} for item in graph.nodes.values()],
                           "edges": [{"id": qualified_id("edge", item.edge_id), "label": item.label,
                                       "from_id": item.from_id, "to_id": item.to_id,
                                       "properties": properties(item)} for item in graph.edges.values()]},
               "observations": {"events": len(events), "alarms": len(alarms), "omissions": dict(omissions),
                                "coverage": "complete selected export; scenario window completeness unknown",
                                "source_malicious_labels": "not supplied", "parent_user_relation": "not projected"}}
    validate_package(package)
    return package


def resolve_event(package: dict, resource_id: str, *, partition: str) -> dict:
    if partition != package["partition"]:
        raise ValueError("foreign scenario")
    matches = [event for event in package["cosmos"] if event["kind"] == "event" and event["resource_id"] == resource_id]
    if len(matches) != 1:
        raise ValueError("unknown or duplicate event ID")
    return matches[0]


def validate_package(package: dict) -> None:
    documents = package["cosmos"]
    partition = package["partition"]
    ids = [document["id"] for document in documents]
    if len(ids) != len(set(ids)) or any(re.search(r"[/\\?#]", value) for value in ids):
        raise ValueError("invalid Cosmos document IDs")
    event_refs = {document["resource_id"] for document in documents if document["kind"] == "event"}
    vertices = package["gremlin"]["vertices"]
    node_ids = {node["id"] for node in vertices}
    if len(node_ids) != len(vertices):
        raise ValueError("duplicate graph node")
    for document in documents:
        if document["partition"] != partition or any(document["source"][key] != value for key, value in package["source"].items()):
            raise ValueError("foreign source membership")
        if not set(document.get("event_refs", [])).issubset(event_refs):
            raise ValueError("unknown evidence reference")
        if not set(document.get("entity_refs", {}).values()).issubset(node_ids):
            raise ValueError("unknown entity reference")
        if not set(document.get("alarm_refs", [])).issubset(set(ids)):
            raise ValueError("unknown alarm reference")
    for item in [*vertices, *package["gremlin"]["edges"]]:
        props = item["properties"]
        if props["source"] != package["source"] or props["partition"] != partition:
            raise ValueError("foreign graph source")
        if not props.get("evidence_refs") or not set(props["evidence_refs"]).issubset(event_refs):
            raise ValueError("graph evidence membership mismatch")
    for edge in package["gremlin"]["edges"]:
        if edge["from_id"] not in node_ids or edge["to_id"] not in node_ids:
            raise ValueError("dangling graph edge")