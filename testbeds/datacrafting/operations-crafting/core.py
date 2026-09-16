"""Mode-neutral integrity, bounded evidence and deterministic crafting primitives."""

from __future__ import annotations

import csv
import copy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping, Protocol
import xml.etree.ElementTree as ET

from rdflib import BNode, Graph, Literal, RDF, URIRef
from rdflib.compare import to_canonical_graph

import schemas
from schemas import InvalidInput


MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_ROWS = 100000
MAX_VIEW_ROWS = 10000
MAX_AGE_SECONDS = 300
AEST = timezone(timedelta(hours=10))
CSV_FIELDS = {
    "scada": "row_id,scenario_id,ts,available_at,asset_id,point,value,unit,quality,synthetic".split(","),
    "alarms": "row_id,scenario_id,ts,available_at,asset_id,code,state,severity,message,synthetic".split(","),
}
POINT_UNITS = {
    "active_power_mw": {"MW"}, "breaker_closed": {"1", "bool", "state"},
    "voltage_kv": {"kV"}, "flow_mva": {"MVA"}, "rating_mva": {"MVA"},
    "cooling_flow_pct": {"%"}, "vacuum_kpa": {"kPa"}, "available": {"1", "bool", "state"},
}


class Mode(Protocol):
    id: str
    version: int
    input_resources: frozenset[str]

    def build(self, bundle: Any) -> dict[str, bytes]: ...


def select_mode(mode_id: str, registry: Mapping[str, Mode]) -> Mode:
    if not isinstance(mode_id, str) or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", mode_id):
        raise InvalidInput("unknown mode")
    if mode_id not in registry:
        raise InvalidInput(f"unknown mode: {mode_id}")
    mode = registry[mode_id]
    if mode.id != mode_id or mode.version != 1:
        raise InvalidInput("invalid host mode registration")
    return mode


def confined_file(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or any(
        character in relative for character in ("\\", ":", "\x00")
    ):
        raise InvalidInput("expected a relative file path")
    path = PurePosixPath(relative)
    if path.is_absolute() or any(part in ("", ".", "..") for part in relative.split("/")):
        raise InvalidInput("path escapes declared root")
    root = Path(root)
    if root.is_symlink() or not root.is_dir():
        raise InvalidInput("root must be an existing non-symlink directory")
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise InvalidInput("symlink resource paths are forbidden")
    if not current.is_file():
        raise InvalidInput(f"missing resource: {relative}")
    return current


def utc(value: str) -> datetime:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
            raise ValueError("noncanonical timestamp")
        return parsed
    except (TypeError, ValueError) as error:
        raise InvalidInput(f"invalid canonical UTC timestamp: {value}") from error


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8")


def jsonl_bytes(values: list[dict]) -> bytes:
    return b"".join((json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False) + "\n").encode("utf-8") for value in values)


def _unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidInput(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _invalid_number(value: str) -> None:
    raise InvalidInput(f"nonfinite JSON number: {value}")


def decode_json(data: bytes) -> Any:
    try:
        return json.loads(data, object_pairs_hook=_unique_object, parse_constant=_invalid_number)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise InvalidInput(f"invalid JSON: {error}") from error


def read_bytes(root: Path, relative: str, expected_hash: str | None = None) -> bytes:
    path = confined_file(root, relative)
    with path.open("rb") as stream:
        data = stream.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise InvalidInput(f"resource exceeds byte bound: {relative}")
    if expected_hash is not None and digest(data) != expected_hash:
        raise InvalidInput(f"SHA-256 mismatch: {relative}")
    return data


def unique_index(rows: list[dict], key: str, name: str) -> dict[str, dict]:
    result = {}
    for row in rows:
        if row[key] in result:
            raise InvalidInput(f"duplicate {name}: {row[key]}")
        result[row[key]] = row
    return result


def alias_index(assets: list[dict]) -> dict[str, str]:
    result = {}
    for asset in assets:
        for alias in (asset["asset_id"], asset["name"], *asset["aliases"]):
            normalized = alias.strip().casefold()
            if not normalized or (normalized in result and result[normalized] != asset["asset_id"]):
                raise InvalidInput(f"ambiguous asset alias: {alias}")
            result[normalized] = asset["asset_id"]
    return result


def resolve_asset(aliases: Mapping[str, str], name: str) -> str:
    try:
        return aliases[name.strip().casefold()]
    except KeyError as error:
        raise InvalidInput(f"unresolved asset: {name}") from error


def check_interval(interval: dict) -> None:
    if utc(interval["end"]) <= utc(interval["start"]):
        raise InvalidInput("event interval must have an exclusive end after start")


def check_event_conditions(task: str, conditions: list[dict] | None, scope: set[str], start: str, end: str) -> None:
    if task == "detection":
        if conditions is not None:
            raise InvalidInput("detection forbids event_conditions")
        return
    if not conditions:
        raise InvalidInput("action event_conditions required; explicitly update legacy authoring and regenerate into NEW_PACK/NEW_RUN; preserve prior evidence")
    schemas.validate(schemas.EVENT_CONDITIONS, conditions, "event_conditions")
    unique_index(conditions, "notification_id", "notification")
    for condition in conditions:
        interval = condition["event_interval"]
        check_interval(interval)
        if not set(condition["asset_ids"]) <= scope:
            raise InvalidInput("event_conditions assets escape public scope")
        if not utc(start) <= utc(interval["start"]) <= utc(condition["available_at"]) <= utc(end):
            raise InvalidInput("event_conditions event/availability outside public window or before event start")


def check_source_time(event: dict) -> None:
    interval = event["event_interval"]
    check_interval(interval)
    start, end = utc(interval["start"]), utc(interval["end"])
    seconds = 1 if event["precision"] == "second" else 60
    if (end - start).total_seconds() != seconds or (seconds == 60 and start.second != 0):
        raise InvalidInput(f"source precision mismatch: {event['id']}")
    text = event["reported_time"]
    clock = re.search(r"\b(\d{2})(\d{2})(?:\.(\d{2}))?\s*hrs\b", text)
    if clock is None:
        clock = re.search(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", text)
    if clock is None:
        raise InvalidInput(f"reported_time needs a source AEST clock: {event['id']}")
    hour, minute, second = clock.groups()
    if (second is not None) != (seconds == 1):
        raise InvalidInput("reported clock contradicts declared source precision")
    local = start.astimezone(AEST)
    if (local.hour, local.minute, local.second) != (int(hour), int(minute), int(second or 0)):
        raise InvalidInput("reported AEST clock does not match UTC+10 interval")
    date_match = re.search(r"\b(\d{1,2}) ([A-Za-z]+) (\d{4})\b", text)
    iso_date = re.search(r"\b\d{4}-\d{2}-\d{2}\b", text)
    try:
        if date_match and datetime.strptime(date_match.group(), "%d %B %Y").date() != local.date():
            raise InvalidInput("reported date does not match AEST interval")
        if iso_date and datetime.strptime(iso_date.group(), "%Y-%m-%d").date() != local.date():
            raise InvalidInput("reported date does not match AEST interval")
    except ValueError as error:
        raise InvalidInput("invalid reported date") from error


def verify_sources(sources: dict, root: Path) -> None:
    pages_by_document = {}
    for document in sources["documents"]:
        pdf = read_bytes(root, document["pdf_path"], document["pdf_sha256"])
        if not pdf.startswith(b"%PDF-"):
            raise InvalidInput("source PDF signature missing")
        markdown = read_bytes(root, document["extraction_path"], document["extraction_sha256"]).decode("utf-8")
        if ("native_path" in document) != ("native_sha256" in document):
            raise InvalidInput("native source path/hash must be supplied together")
        if "native_path" in document:
            decode_json(read_bytes(root, document["native_path"], document["native_sha256"]))
        pages = {}
        for ordinal, page in enumerate(re.split(r"<!--\s*PageBreak\s*-->", markdown), 1):
            if not page.strip():
                continue
            number = re.search(r"<!--\s*PageNumber:\s*(\d+)\s*-->", page)
            page_id = int(number.group(1)) if number else ordinal
            if page_id in pages:
                raise InvalidInput("ambiguous CU page numbering")
            pages[page_id] = page
        if "pages" in document and len(pages) != document["pages"]:
            raise InvalidInput("declared native page count disagrees with Markdown")
        pages_by_document[document["id"]] = pages
    for event in sources["events"]:
        check_source_time(event)
    pending = [sources]
    while pending:
        value = pending.pop()
        if isinstance(value, dict):
            for reference in value.get("source_refs", []):
                schemas.validate(schemas.SOURCE_REF, reference, "source reference")
                pages = pages_by_document.get(reference["document_id"], {})
                if reference["quote"] not in pages.get(reference["page"], ""):
                    raise InvalidInput(f"source quote/page mismatch: {value.get('id', 'nested evidence')}")
            if value.get("precision") in ("second", "minute") and "event_interval" in value:
                check_source_time(value)
            pending.extend(value.values())
        elif isinstance(value, list):
            pending.extend(value)


def parse_csv(data: bytes, table: str) -> list[dict]:
    try:
        reader = csv.DictReader(io.StringIO(data.decode("utf-8"), newline=""), strict=True)
        if reader.fieldnames != CSV_FIELDS[table]:
            raise InvalidInput(f"unexpected {table} CSV header")
        rows = []
        for row in reader:
            if len(rows) >= MAX_ROWS or None in row or any(value is None for value in row.values()):
                raise InvalidInput(f"malformed or oversized {table} CSV")
            if row["synthetic"] != "true":
                raise InvalidInput("CSV records must declare synthetic=true")
            for key in ("row_id", "scenario_id", "asset_id"):
                schemas.validate(schemas.IDENTIFIER, row[key], f"{table}.{key}")
            utc(row["ts"])
            utc(row["available_at"])
            if table == "scada":
                point = row["point"]
                if point not in POINT_UNITS or row["unit"] not in POINT_UNITS[point]:
                    raise InvalidInput(f"unknown point or mismatched units: {point}/{row['unit']}")
                if row["quality"] not in ("good", "missing", "stale", "bad"):
                    raise InvalidInput("unknown SCADA quality")
                if row["value"] == "":
                    if row["quality"] != "missing":
                        raise InvalidInput("empty SCADA value requires missing quality")
                    row["value"] = None
                else:
                    row["value"] = float(row["value"])
                    if not math.isfinite(row["value"]):
                        raise InvalidInput("SCADA value must be finite")
                    if point in ("breaker_closed", "available") and row["value"] not in (0, 1):
                        raise InvalidInput("digital states must be zero or one")
            elif row["state"] not in ("active", "cleared"):
                raise InvalidInput("unknown alarm state")
            row["synthetic"] = True
            rows.append(row)
        unique_index(rows, "row_id", f"{table} row")
        return rows
    except (csv.Error, UnicodeError, ValueError) as error:
        raise InvalidInput(f"invalid {table}: {error}") from error


class _NoDocumentType(ET.TreeBuilder):
    def doctype(self, name, public_id, system_id):
        raise InvalidInput("RDF XML declarations/entities are forbidden")


def parse_topology(data: bytes, assets: list[dict]) -> tuple[Graph, dict[str, Any]]:
    if re.search(br"<!\s*(DOCTYPE|ENTITY)", data, re.IGNORECASE):
        raise InvalidInput("RDF XML declarations/entities are forbidden")
    try:
        ET.fromstring(data, parser=ET.XMLParser(target=_NoDocumentType()))
        namespaces = dict(declaration for _, declaration in ET.iterparse(io.BytesIO(data), events=("start-ns",)))
        if not any("CIM" in uri for uri in namespaces.values()) or "mock" not in namespaces:
            raise InvalidInput("topology must declare CIM and mock namespaces")
        graph = Graph().parse(data=data, format="xml", publicID="https://operations.invalid/topology")
    except Exception as error:
        raise InvalidInput(f"invalid RDF/XML topology: {error}") from error
    if not graph or len(graph) > MAX_ROWS:
        raise InvalidInput("topology must be nonempty and bounded")
    if any(isinstance(term, BNode) for triple in graph for term in triple):
        graph = to_canonical_graph(graph)
    subjects = set(graph.subjects())
    for _, predicate, target in graph:
        if not isinstance(target, Literal) and predicate != RDF.type and target not in subjects:
            raise InvalidInput(f"dangling topology reference: {target}")
    nodes = {}
    for asset in assets:
        cim_id = asset["cim_id"]
        matches = {subject for subject in subjects if str(subject) == cim_id or str(subject).rsplit("#", 1)[-1] == cim_id.lstrip("#")}
        matches.update(subject for subject, predicate, value in graph if str(predicate).endswith(".mRID") and str(value) == cim_id)
        if len(matches) != 1:
            raise InvalidInput(f"unresolved/ambiguous CIM asset: {asset['asset_id']}")
        nodes[asset["asset_id"]] = matches.pop()
    if len(set(nodes.values())) != len(nodes):
        raise InvalidInput("multiple assets claim one CIM node")
    for asset in assets:
        nominal = asset["attributes"].get("nominal_kv", asset["attributes"].get("nominal_voltage_kv"))
        if nominal is not None:
            node = nodes[asset["asset_id"]]
            bases = [target for predicate, target in graph.predicate_objects(node) if str(predicate).endswith(".BaseVoltage")]
            for base in bases:
                values = [float(value) for predicate, value in graph.predicate_objects(base) if str(predicate).endswith(".nominalVoltage")]
                if values and any(value != float(nominal) for value in values):
                    raise InvalidInput("asset and topology nominal voltages disagree")
    return graph, nodes


@dataclass
class Bundle:
    manifest: dict
    manifest_hash: str
    assets: dict[str, dict]
    aliases: dict[str, str]
    tables: dict[str, list[dict]]
    graph: Graph
    nodes: dict[str, Any]
    sources: dict
    scenarios: list[dict]


def load_bundle(pack: Path, source_root: Path) -> Bundle:
    manifest_data = read_bytes(pack, "manifest.json")
    manifest = decode_json(manifest_data)
    schemas.validate(schemas.MANIFEST, manifest, "manifest")
    resources = unique_index(manifest["resources"], "id", "resource capability")
    authoring = unique_index(manifest["authoring"], "id", "authoring capability")
    if set(resources) != set(schemas.RESOURCES) or set(authoring) != {"source_events", "scenarios"}:
        raise InvalidInput("manifest must supply exactly the v1 capabilities")
    entries = {**resources, **authoring}
    if len({entry["path"] for entry in entries.values()}) != len(entries):
        raise InvalidInput("multiple capabilities claim one path")
    payloads = {name: read_bytes(pack, entry["path"], entry["sha256"]) for name, entry in entries.items()}
    values = {name: decode_json(payloads[name]) for name in ("assets", "knowledge", "source_events", "scenarios")}
    for name, schema in (("assets", schemas.ASSETS), ("knowledge", schemas.KNOWLEDGE), ("source_events", schemas.SOURCES), ("scenarios", schemas.SCENARIOS)):
        schemas.validate(schema, values[name], name)
    assets = unique_index(values["assets"]["assets"], "asset_id", "asset")
    aliases = alias_index(list(assets.values()))
    sources = values["source_events"]
    unique_index(sources["documents"], "id", "source document")
    events = unique_index(sources["events"], "id", "source event")
    facts = unique_index(sources.get("facts", []), "id", "source fact")
    for event in sources["events"]:
        if set(event.get("fact_ids", [])) - facts.keys():
            raise InvalidInput("source event references unknown reviewed facts")
    scenarios = values["scenarios"]["scenarios"]
    scenario_index = unique_index(scenarios, "scenario_id", "scenario")
    incident_splits = {}
    for scenario in scenarios:
        if utc(scenario["window_start"]) > utc(scenario["decision_time"]):
            raise InvalidInput("evidence window begins after decision")
        if (utc(scenario["decision_time"]) - utc(scenario["window_start"])).total_seconds() > 7 * 86400:
            raise InvalidInput("evidence window exceeds seven-day host bound")
        check_event_conditions(scenario["kind"], scenario.get("event_conditions"), set(scenario["asset_ids"]),
                               scenario["window_start"], scenario["decision_time"])
        incident = scenario["incident_id"]
        if incident in incident_splits and incident_splits[incident] != scenario["split"]:
            raise InvalidInput("same-incident variants cannot cross splits")
        incident_splits[incident] = scenario["split"]
        for event_id in scenario["source_event_ids"]:
            if event_id not in events or events[event_id]["incident_id"] != incident:
                raise InvalidInput("scenario source event/incident mismatch")
        for condition in scenario.get("event_conditions", []):
            if not any(condition["event_type"] == events[event_id]["event_type"]
                       and set(condition["asset_ids"]) <= set(events[event_id]["asset_ids"])
                       and condition["event_interval"] == events[event_id]["event_interval"]
                       for event_id in scenario["source_event_ids"]):
                raise InvalidInput("event_conditions must retain a declared source event's type, assets and interval precision")
    knowledge = values["knowledge"]["documents"]
    unique_index(knowledge, "id", "knowledge document")
    for document in knowledge:
        utc(document["valid_from"])
        utc(document["available_at"])
        if "known_at" in document:
            utc(document["known_at"])
        if "valid_to" in document and utc(document["valid_to"]) <= utc(document["valid_from"]):
            raise InvalidInput("invalid knowledge validity interval")
        if document["kind"] == "forensic" and document["action_rules"]:
            raise InvalidInput("forensic truth cannot define action policy")
    for owner in [*sources["events"], *scenarios, *knowledge]:
        for asset_id in [*owner["asset_ids"], *owner.get("line_asset_ids", [])]:
            if asset_id not in assets:
                raise InvalidInput(f"unresolved canonical asset: {asset_id}")
    tables = {name: parse_csv(payloads[name], name) for name in CSV_FIELDS}
    for rows in tables.values():
        for row in rows:
            if row["scenario_id"] not in scenario_index or row["asset_id"] not in assets:
                raise InvalidInput("telemetry references an unknown scenario or asset")
            if "point" in row:
                declared = assets[row["asset_id"]]["attributes"].get("point_units", {})
                if declared and declared.get(row["point"]) != row["unit"]:
                    raise InvalidInput("SCADA point units disagree with asset binding")
                definition = values["assets"].get("point_definitions", {}).get(row["point"])
                if definition is not None and (definition["unit"] != row["unit"] or (row["value"] is not None and
                    (row["value"] < definition.get("minimum", -math.inf) or row["value"] > definition.get("maximum", math.inf)))):
                    raise InvalidInput("SCADA value/unit violates declared point definition")
    tables["knowledge"] = knowledge
    graph, nodes = parse_topology(payloads["topology"], list(assets.values()))
    verify_sources(sources, source_root)
    observed_counts = {"action_scenarios": sum(scenario["kind"] == "action" for scenario in scenarios),
                       "alarm_rows": len(tables["alarms"]), "assets": len(assets),
                       "detection_scenarios": sum(scenario["kind"] == "detection" for scenario in scenarios),
                       "deterministic_files": len(entries) + 1, "knowledge_documents": len(knowledge),
                       "rdf_triples": len(graph), "scada_rows": len(tables["scada"]), "scenarios": len(scenarios),
                       "source_documents": len(sources["documents"]), "source_events": len(events), "tables": len(CSV_FIELDS)}
    if "counts" in manifest and manifest["counts"] != observed_counts:
        raise InvalidInput("manifest counts disagree with validated resources")
    return Bundle(manifest, digest(manifest_data), assets, aliases, tables, graph, nodes, sources, scenarios)


PUBLIC_ATTRIBUTES = (
    "nominal_kv", "nominal_voltage_kv", "synchronous", "capacity_mw", "rated_mw",
    "system_strength_contributor", "normal_closed", "rating_mva",
)


def evidence_id(tool: str, original: str) -> str:
    return "e-" + digest(f"{tool}\0{original}".encode())[:24]


def case_id(bundle: Bundle, scenario: dict) -> str:
    return "c-" + digest(f"{bundle.manifest['resource_pack_id']}\0{scenario['scenario_id']}".encode())[:20]


def _topology_rows(bundle: Bundle, asset_ids: list[str]) -> list[dict]:
    rows = []
    asset_nodes = set(bundle.nodes.values())
    for asset_id in sorted(asset_ids):
        node = bundle.nodes[asset_id]
        allowed = {node}
        terminals = {subject for subject, predicate in bundle.graph.subject_predicates(node) if str(predicate).endswith(".ConductingEquipment")}
        allowed.update(terminals)
        for subject in list(allowed):
            allowed.update(target for predicate, target in bundle.graph.predicate_objects(subject)
                           if predicate != RDF.type and not isinstance(target, Literal) and target not in asset_nodes)
        for subject in sorted(allowed, key=str):
            for predicate, target in sorted(bundle.graph.predicate_objects(subject), key=lambda pair: (str(pair[0]), str(pair[1]))):
                if not isinstance(target, Literal) and predicate != RDF.type and target not in allowed:
                    continue
                triple = f"{asset_id}\0{subject}\0{predicate}\0{target}"
                rows.append({"row_id": evidence_id("topology", triple), "asset_id": asset_id,
                             "subject": str(subject), "predicate": str(predicate), "object": str(target),
                             "object_kind": "literal" if isinstance(target, Literal) else "resource", "synthetic": True})
    return rows


def materialize_view(bundle: Bundle, scenario: dict, mode_id: str, version: int) -> dict:
    scope = set(scenario["asset_ids"])
    start, end = scenario["window_start"], scenario["decision_time"]
    check_event_conditions(scenario["kind"], scenario.get("event_conditions"), scope, start, end)
    freshness = scenario["parameters"].get("stale_after_seconds", MAX_AGE_SECONDS)
    if type(freshness) is not int or not 1 <= freshness <= MAX_AGE_SECONDS:
        raise InvalidInput("authored freshness must narrow the 300-second host bound")
    assets = []
    for asset_id in sorted(scope):
        asset = bundle.assets[asset_id]
        assets.append({key: copy.deepcopy(asset[key]) for key in ("asset_id", "name", "kind", "station", "synthetic")})
        assets[-1]["attributes"] = {key: copy.deepcopy(asset["attributes"][key]) for key in PUBLIC_ATTRIBUTES
                                    if key in asset["attributes"] and isinstance(asset["attributes"][key], (str, int, float, bool))}
    view = {"schema_version": 1, "mode": {"id": mode_id, "version": version},
            "case_id": case_id(bundle, scenario), "task": scenario["kind"],
            "window_start": start, "decision_time": end, "assets": assets,
            "tools": sorted(scenario["tools"]), "limits": {"max_rows": MAX_VIEW_ROWS, "max_age_seconds": freshness},
            "evidence": {}, "quality": []}
    if scenario["kind"] == "action":
        view["event_conditions"] = [{**copy.deepcopy(condition),
                                     "notification_id": evidence_id("notification", condition["notification_id"])}
                                    for condition in scenario["event_conditions"]]
    for tool in ("scada", "alarms"):
        if tool not in view["tools"]:
            continue
        records = []
        for row in bundle.tables[tool]:
            if row["scenario_id"] != scenario["scenario_id"] or row["asset_id"] not in scope:
                continue
            if not (start <= row["ts"] <= end and row["available_at"] <= end):
                continue
            public = {key: value for key, value in row.items() if key != "scenario_id"}
            public["row_id"] = evidence_id(tool, row["row_id"])
            if tool == "scada":
                view["quality"].append({key: public[key] for key in ("row_id", "asset_id", "point", "ts", "available_at", "quality")})
                if row["quality"] != "good":
                    continue
            records.append(public)
        view["evidence"][tool] = sorted(records, key=lambda row: (row["ts"], row["row_id"]))
    if "knowledge" in view["tools"]:
        documents = []
        for document in bundle.tables["knowledge"]:
            shared_scope = sorted(scope.intersection(document["asset_ids"]))
            if not shared_scope or document["kind"] == "forensic":
                continue
            if document["valid_from"] > end or document["available_at"] > end or document.get("known_at", "0000") > end or document.get("valid_to", "9999") <= end:
                continue
            public = {key: copy.deepcopy(value) for key, value in document.items() if key in schemas.PUBLIC_KNOWLEDGE["properties"]}
            public["id"] = evidence_id("knowledge", document["id"])
            public["asset_ids"] = shared_scope
            documents.append(public)
        view["evidence"]["knowledge"] = sorted(documents, key=lambda row: row["id"])
    if "topology" in view["tools"]:
        view["evidence"]["topology"] = _topology_rows(bundle, sorted(scope))
    view["quality"].sort(key=lambda row: (row["ts"], row["row_id"]))
    if any(len(rows) > MAX_VIEW_ROWS for rows in [*view["evidence"].values(), view["quality"]]):
        raise InvalidInput("materialized case exceeds row bound; narrow its authored window")
    return view


class QueryDenied(ValueError):
    """A request exceeds the already-materialized public evidence boundary."""


class EvidenceReader:
    """Trusted local callback API, not a malicious-code or filesystem sandbox."""

    __slots__ = ("view", "trace")

    def __init__(self, view: dict):
        check_event_conditions(view["task"], view.get("event_conditions"), {asset["asset_id"] for asset in view["assets"]},
                               view["window_start"], view["decision_time"])
        self.view = copy.deepcopy(view)
        self.trace: list[dict] = []

    def query(self, tool: str, *, asset_ids: list[str] | None = None, case_id: str | None = None,
              start: str | None = None, end: str | None = None, limit: int = MAX_VIEW_ROWS) -> dict:
        request = {"tool": tool, "asset_ids": asset_ids, "case_id": case_id, "start": start, "end": end, "limit": limit}
        try:
            if tool not in schemas.TOOLS or tool not in self.view["tools"]:
                raise QueryDenied("unknown or unavailable tool")
            if case_id is not None and case_id != self.view["case_id"]:
                raise QueryDenied("case/scenario widening forbidden")
            scope = {asset["asset_id"] for asset in self.view["assets"]}
            selected = scope if asset_ids is None else set(asset_ids)
            if not selected <= scope:
                raise QueryDenied("asset widening forbidden")
            lower = self.view["window_start"] if start is None else start
            upper = self.view["decision_time"] if end is None else end
            utc(lower)
            utc(upper)
            if lower < self.view["window_start"] or upper > self.view["decision_time"] or lower > upper:
                raise QueryDenied("time widening forbidden")
            if type(limit) is not int or limit < 1 or limit > self.view["limits"]["max_rows"]:
                raise QueryDenied("row limit outside host bound")
            rows = []
            for row in self.view["evidence"].get(tool, []):
                if tool == "knowledge":
                    matches = selected.intersection(row["asset_ids"]) and row["valid_from"] <= upper and row["available_at"] <= upper and row.get("valid_to", "9999") > upper
                else:
                    matches = row["asset_id"] in selected
                    if tool != "topology":
                        matches = matches and lower <= row["ts"] <= upper and row["available_at"] <= upper
                if matches:
                    public = copy.deepcopy(row)
                    if tool == "knowledge":
                        public["asset_ids"] = sorted(selected.intersection(row["asset_ids"]))
                    rows.append(public)
            quality = {}
            if tool == "scada":
                for row in self.view["quality"]:
                    if row["asset_id"] in selected and lower <= row["ts"] <= upper and row["available_at"] <= upper:
                        key = (row["asset_id"], row["point"])
                        if key not in quality or (row["ts"], row["available_at"], row["quality"] != "good") >= (
                            quality[key]["ts"], quality[key]["available_at"], quality[key]["quality"] != "good"
                        ):
                            quality[key] = copy.deepcopy(row)
                for row in quality.values():
                    if (utc(upper) - utc(row["ts"])).total_seconds() > self.view["limits"]["max_age_seconds"]:
                        row["quality"] = "stale"
            response = {"tool": tool, "rows": rows[:limit], "complete": len(rows) <= limit,
                        "quality": [quality[key] for key in sorted(quality)]}
            self.trace.append({"request": request, "outcome": "ok", "count": len(response["rows"]),
                               "complete": response["complete"],
                               "evidence_ids": [row.get("row_id", row.get("id")) for row in response["rows"]],
                               "quality": response["quality"]})
            return response
        except (InvalidInput, QueryDenied, TypeError) as error:
            self.trace.append({"request": request, "outcome": "denied", "reason": str(error)})
            raise QueryDenied(str(error)) from error


def write_artifacts(output: Path, artifacts: dict[str, bytes], metadata: dict) -> dict:
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise InvalidInput("output already exists; select a NEW_RUN, never overwrite")
    for relative, data in artifacts.items():
        if relative == "manifest.json" or not isinstance(data, bytes):
            raise InvalidInput("artifact names/bytes violate output contract")
        if PurePosixPath(relative).is_absolute() or any(part in ("", ".", "..") for part in relative.split("/")) or any(character in relative for character in ("\\", ":", "\x00")):
            raise InvalidInput("artifact path escapes output")
    for parent in (output.parent, *output.parents):
        if parent.is_symlink():
            raise InvalidInput("symlink output parents forbidden")
    manifest = {"schema_version": 1, **metadata, "artifacts": [
        {"path": relative, "sha256": digest(data), "bytes": len(data),
         "visibility": "agent" if relative in ("detection.inputs.jsonl", "action.inputs.jsonl") else "evaluator_only"}
        for relative, data in sorted(artifacts.items())
    ]}
    schemas.validate(schemas.RUN_MANIFEST, manifest, "run manifest")
    try:
        output.mkdir(mode=0o700, parents=True, exist_ok=False)
    except FileExistsError as error:
        raise InvalidInput("output already exists; select a NEW_RUN") from error
    for relative, data in [*sorted(artifacts.items()), ("manifest.json", json_bytes(manifest))]:
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as stream:
            stream.write(data)
        if path.read_bytes() != data:
            raise OSError(f"artifact read-back mismatch: {relative}")
    return manifest


def read_artifacts(root: Path) -> tuple[dict, dict[str, bytes]]:
    manifest = decode_json(read_bytes(root, "manifest.json"))
    schemas.validate(schemas.RUN_MANIFEST, manifest, "run manifest")
    entries = unique_index(manifest["artifacts"], "path", "artifact path")
    if "manifest.json" in entries:
        raise InvalidInput("a manifest cannot contain its own content hash")
    artifacts = {}
    for relative, entry in entries.items():
        data = read_bytes(root, relative, entry["sha256"])
        if len(data) != entry["bytes"]:
            raise InvalidInput(f"artifact byte count mismatch: {relative}")
        artifacts[relative] = data
    return manifest, artifacts


def craft_dataset(*, mode_id: str, registry: Mapping[str, Mode], resources: Path, source_root: Path, output: Path) -> dict:
    mode = select_mode(mode_id, registry)
    if not mode.input_resources <= frozenset(schemas.RESOURCES):
        raise InvalidInput("host mode requests unknown capabilities")
    if Path(output).exists() or Path(output).is_symlink():
        raise InvalidInput("output already exists; select a NEW_RUN")
    bundle = load_bundle(Path(resources), Path(source_root))
    if not mode.input_resources <= {entry["id"] for entry in bundle.manifest["resources"]}:
        raise InvalidInput("mode input capabilities unavailable")
    artifacts = mode.build(bundle)
    if "provenance.json" in artifacts:
        raise InvalidInput("provenance belongs to core, not a mode")
    artifacts["provenance.json"] = json_bytes({
        "schema_version": 1, "visibility": "evaluator_only", "synthetic": True,
        "source_evidence": bundle.sources, "authoring_scenarios": bundle.scenarios,
        "resource_manifest": bundle.manifest, "resource_manifest_sha256": bundle.manifest_hash,
        "unverified_metadata": "Generator/review/source-manifest digests without an exchange path are retained declarations, not independently authenticated artifacts.",
        "time_policy": {"timezone": "AEST", "utc_offset": "+10:00", "interval_end": "exclusive",
                        "event_and_availability_cutoff": "inclusive decision_time", "max_age_seconds": MAX_AGE_SECONDS},
        "assumptions": ["Topology/inventory are static synthetic context, assumed known by each cutoff.",
                        "Knowledge without valid_to remains valid until superseded; this is a mock assumption.",
                        "Quote/page/hash verification proves retained evidence identity, not report correctness.",
                        "Trusted callbacks receive only materialized views; they are not sandboxed Python."],
    })
    return write_artifacts(Path(output), artifacts, {"mode": {"id": mode.id, "version": mode.version},
                                                    "synthetic": True, "resource_pack_id": bundle.manifest["resource_pack_id"],
                                                    "resource_manifest_sha256": bundle.manifest_hash})