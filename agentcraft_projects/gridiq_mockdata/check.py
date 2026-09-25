#!/usr/bin/env python3
"""Validate GridIQ mock data: alignment, coverage extracted from the tools source, scenario predicates, PDFs.

Usage: python3 check.py --tools ../gridiq/tools [--out out]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEM = ("NSW", "VIC", "QLD", "SA", "TAS")
ABSTRACT = {"IdentifiedObject", "Equipment", "ConductingEquipment", "ScadaDeviceObject"}
CLASS_LABELS = {"GEN": {"SynchronousMachine", "GeneratingUnit"}, "UNIT": {"GeneratingUnit"},
                "LINE": {"ACLineSegment"}, "BUS": {"BusBarSection"}, "TRANS": {"PowerTransformer"},
                "CB": {"Switch"}, "SVC": {"StaticVarCompensator"}}
OWNER_KEYS = ("ScadaDeviceObject.ScadaAliasName", "SynchronousMachine.DTSMOMCompositeId",
              "PowerTransformer.NETMOMCompositeId")
PIPELINE_INTERNAL = {"adapter", "mode", "source_file", "page_count", "note"}
REPORT_WORDS = {"AEST", "NEM", "SYMPTOM", "SYMPTOMS", "CAUSE", "CONCLUSIONS", "WHAT", "HAPPENED", "WHY", "IT",
                "MATTERS", "IF", "YOU", "SEE", "THIS", "EQUIPMENT", "ACTION", "STATUS", "OPERATOR", "NOTE",
                "OUTCOME", "STATION", "REASONING", "GUIDE", "SCADA", "PAWS", "AGC", "BESS", "SVC"}
NOISE_LABELS = ("TAP_CHANGE", "UNDERVOLTAGE")
FMT = "%Y-%m-%dT%H:%M:%S"


class Results:
    def __init__(self) -> None:
        self.checks: list[tuple[str, str, bool, str, list[str]]] = []
        self.coverage: list[tuple[str, int, int, list[str]]] = []

    def add(self, section: str, name: str, failures: list[str], count: str = "") -> None:
        self.checks.append((section, name, not failures, count, failures))

    def cover(self, category: str, required: set[str], covered: set[str]) -> None:
        missing = sorted(required - covered)
        self.coverage.append((category, len(required), len(required) - len(missing), missing))
        self.add("B", f"coverage: {category}", [f"missing {m!r}" for m in missing], f"{len(required) - len(missing)}/{len(required)}")


# ── Loading ──────────────────────────────────────────────────────────────
def load_csv(path: Path) -> tuple[list[str], list[dict]]:
    with path.open(newline="") as fh:
        r = csv.DictReader(fh)
        return list(r.fieldnames or []), list(r)


def load_data(out: Path) -> dict:
    ah, alarms = load_csv(out / "kql/WatcherAlarmsAll.csv")
    sh, scada = load_csv(out / "kql/WatcherScadaAll.csv")
    for r in alarms:
        r["dt"] = datetime.strptime(r["timestamp_aest"], FMT)
        r["priority"] = int(r["priority"])
    for r in scada:
        r["dt"] = datetime.strptime(r["timestamp_aest"], FMT)
        r["Value"] = float(r["Value"])
    vertices = {v["id"]: v for v in map(json.loads, (out / "graph/vertices.jsonl").read_text().splitlines())}
    edges = [json.loads(x) for x in (out / "graph/edges.jsonl").read_text().splitlines()]
    schema = {}
    for m in re.finditer(r"\.create-merge table (\w+) \(([^)]*)\)", (out / "kql/schema.kql").read_text()):
        schema[m.group(1)] = [c.split(":")[0].strip() for c in m.group(2).split(",")]
    search = {}
    for d in sorted((out / "search").iterdir()):
        search[d.name] = {"index": json.loads((d / "index.json").read_text()),
                          "docs": [json.loads(x) for x in (d / "documents.jsonl").read_text().splitlines()],
                          "pdf": d / "report.pdf"}
    return dict(alarm_header=ah, alarms=alarms, scada_header=sh, scada=scada, vertices=vertices, edges=edges,
                schema=schema, search=search)


def load_config(tools: Path) -> dict:
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(tools.resolve().parent))
    from tools.situations.config import DEFAULT_DETECTOR_CONFIG  # noqa: E402
    return DEFAULT_DETECTOR_CONFIG


# ── Extraction from tools source ─────────────────────────────────────────
def py_sources(tools: Path) -> dict[Path, str]:
    return {p: p.read_text() for p in sorted(tools.rglob("*.py"))
            if "gridsfm" not in p.parts and "__pycache__" not in p.parts}


def quoted(text: str) -> list[str]:
    return [a or b for a, b in re.findall(r"'([^'{}]*)'|\"([^\"{}]*)\"", text)]


def extract(tools: Path, cfg: dict) -> dict:
    src = py_sources(tools)
    allsrc = "\n".join(src.values())
    ex: dict = {}
    # Graph: edge labels in traversal steps; other Class.Property literals are vertex properties.
    edge_ctx = re.compile(r"\.(?:in|out|inE|outE|both|bothE)\(\s*((?:'[^']*'\s*,?\s*)+)\)")
    edges, props, labels = set(), set(), set()
    for s in src.values():
        local = set()
        for m in edge_ctx.finditer(s):
            local |= set(re.findall(r"'([^']*)'", m.group(1)))
        edges |= local
        props |= {p for p in re.findall(r"'([A-Z][A-Za-z]+\.[A-Za-z_]+)'", s) if p not in local}
        labels |= set(re.findall(r"hasLabel\(\s*'([A-Za-z]+)'", s))
    ex["edges"], ex["props"], ex["labels"] = edges, props - edges, labels
    # Alarm labels.
    exact, contains = set(), set()
    for m in re.finditer(r"alarm_label\s*(==|!=|in|has|contains)\s*(\([^)]*\)|'[^']*')", allsrc):
        vals = [v for v in quoted(m.group(2)) if v]
        (contains if m.group(1) in ("has", "contains") else exact).update(vals)
    for sig in cfg["alarm_signals"]:
        if sig["col"] == "alarm_label":
            (exact if sig["op"] == "==" else contains).add(sig["val"])
        if sig.get("extra_col") == "alarm_label":
            (exact if sig["extra_op"] == "==" else contains).add(sig["extra_val"])
    pats = cfg["patterns"]
    exact |= set(pats["regional_cascade"]["alarm_labels"]) | set(pats["regional_cascade"]["emergency_labels"])
    exact |= {pats["system_reactive_event"]["svc_alarm_label"], pats["system_reactive_event"]["unit_alarm_label"]}
    ex["alarm_exact"], ex["alarm_contains"] = exact, contains
    # Measurements and TagId class segments.
    meas = set()
    for m in re.finditer(r"measurement\s*(?:==|in|has)\s*(\([^)]*\)|'[^']*')", allsrc):
        meas |= {v for v in quoted(m.group(1)) if v}
    meas |= {s["meas"] for s in cfg["scada_signals"]}
    ex["measurements"] = meas
    segs = set(re.findall(r"TagId\s+(?:contains|has)\s+'(\.[A-Z]+\.)'", allsrc))
    segs |= {t for s in cfg["scada_signals"] for t in s["tag_contains"]}
    ex["tag_segments"] = segs
    # Literal tag strings + templates expanded over NEM regions.
    tags = set(re.findall(r"[\"']([A-Z][A-Z0-9_]*(?:\.[A-Z0-9_]+){2,})[\"']", allsrc))
    for t in re.findall(r"[\"']((?:[A-Z0-9_]|\{[a-z_]+\})+(?:\.(?:[A-Z0-9_]|\{[a-z_]+\})+){2,})[\"']", allsrc):
        if "{" in t:
            tags |= {re.sub(r"\{[a-z_]+\}", r, t) for r in NEM}
    ex["tags"] = tags
    # Station lists.
    fe = pats["frequency_excursion"]
    ex["exclude_stations"], ex["tas_override"] = set(fe["exclude_stations"]), set(fe["tas_override"])
    ref = (tools / "grid_reference/_reference.py").read_text()
    regions = quoted(re.search(r"_NEM_REGIONS\s*=\s*\(([^)]*)\)", ref).group(1))
    extra = quoted(re.search(r"_PSEUDO_REGION_STATIONS\s*=.*?\|\s*\{([^}]*)\}", ref).group(1))
    ex["pseudo"] = {f"{r}1" for r in regions} | set(extra)
    # KQL source columns (where/project/by positions minus names computed in the same query).
    kw = {"and", "or", "not", "in", "between", "contains", "has", "by", "asc", "desc", "true", "false", "datetime",
          "bin", "iff", "isnull", "abs", "todouble", "tostring", "strcat", "round", "count", "dcount", "take", "top",
          "let", "where", "project", "order", "summarize", "extend", "serialize", "prev", "split", "substring",
          "indexof", "typeof", "pack_array", "kind", "inner", "leftouter", "on", "join", "union", "mv", "expand", "to"}
    tref = re.compile(r"WatcherAlarmsAll|WatcherScadaAll|\{table\}|\{scada_table\}|\{alarm_table\}")
    cols = set()
    for s in src.values():
        for q in s.split('"""'):
            if not tref.search(q) or "| " not in q:
                continue
            q = re.sub(r"\{[^{}]*\}", "", q)
            defined = {n for n, rhs in re.findall(r"\b([A-Za-z_]\w*)[ \t]*=(?!=)[ \t]*([^,\n]*)", q)
                       if not re.search(rf"\b{n}\b", rhs)} | set(re.findall(r"let\s+(\w+)", q))
            used = set()
            for w in re.finditer(r"\|\s*where\s+([^|]*)", q):
                used |= set(re.findall(r"\b([A-Za-z_]\w*)\s*(?:==|!in\b|in\s*\(|between|has\b|contains\b|!=|>=|<=|>|<)", w.group(1)))
            for w in re.finditer(r"\|\s*project\s+([^|]*)", q):
                used |= {i.strip() for i in w.group(1).split('"')[0].split(",") if re.fullmatch(r"[A-Za-z_]\w*", i.strip())}
            for w in re.finditer(r"\bby\s+([^|\n]*)", q):
                for i in w.group(1).split(","):
                    i = i.strip()
                    mb = re.match(r"bin\((\w+)", i)
                    if mb:
                        used.add(mb.group(1))
                    elif re.fullmatch(r"[A-Za-z_]\w*", i):
                        used.add(i)
            cols |= used - defined - kw
    ex["kql_columns"] = cols
    # Search: index names, semantic configs, vector fields per run_search_tool call.
    search_dir = tools / "search"
    names, semantic, vector = set(), {}, {}
    for p, s in src.items():
        if search_dir not in p.parents:
            continue
        found = set(re.findall(r"[\"']([a-z]+(?:-[a-z]+)*-index)[\"']", s))
        names |= found
        consts = dict(re.findall(r"^(_[A-Z_]+)\s*=\s*\"([^\"]+)\"", s, re.M))
        for call in re.findall(r"run_search_tool\((.*?)\n\s*\)", s, re.S):
            im = re.search(r"index_name=([\w()]+)", call)
            sm = re.search(r"semantic_config=([\w()]+)", call)
            vm = re.search(r"vector_field=\"(\w+)\"", call)
            idxs = [consts[im.group(1)]] if im and im.group(1) in consts else sorted(found)
            for idx in idxs:
                if sm and sm.group(1) in consts and "{" not in consts[sm.group(1)]:
                    semantic[idx] = consts[sm.group(1)]
                elif re.search(r"-semantic\"", s):
                    semantic[idx] = f"{idx}-semantic"
                if vm:
                    vector[idx] = vm.group(1)
    fcfg = (tools.parent / "foundation/config.py")
    if fcfg.exists():
        m = re.search(r"action_feedback_search_index:\s*str\s*=\s*\"([^\"]+)\"", fcfg.read_text())
        if m:
            names.add(m.group(1))
            vector.setdefault(m.group(1), "text_vector")
            semantic.setdefault(m.group(1), None)
    prov = (search_dir / "_aisearch/index_provisioning.py").read_text()
    std = set(re.findall(r"SearchField\(name=\"(\w+)\"", prov))
    vec_default = re.findall(r"name=\"(\w+)\",\s*type=SearchFieldDataType\.Collection", prov)
    std -= set(vec_default)
    std |= set(re.findall(r"^\s+\"(\w+)\":", prov.split("search_doc = {", 1)[1].split("}", 1)[0], re.M)) - set(vec_default)

    def adapter_fields(path: Path) -> set[str]:
        s = path.read_text()
        f = set(re.findall(r"(?:record|pdf_meta)\.get\(\s*[\"']([A-Za-z_]+)[\"']", s))
        f |= set(re.findall(r"fields\[\s*[\"']([A-Za-z_]+)[\"']\s*\]", s))
        for block in re.findall(r"metadata=\{(.*?)\}", s, re.S):
            f |= set(re.findall(r"[\"']([A-Za-z_]+)[\"']\s*:", block))
        return f - PIPELINE_INTERNAL

    ad = search_dir / "_aisearch/document_adapters"
    kinds = {"incident": adapter_fields(ad / "_incidents.py"), "lesson": adapter_fields(ad / "_lessons.py"),
             "feedback": adapter_fields(ad / "_action_feedback.py")}
    fb = (search_dir / "action_feedback.py").read_text()
    kinds["feedback"] |= set(re.findall(r"^\s+\"(\w+)\":", fb.split("return {", 1)[1].split("}", 1)[0], re.M))
    ex.update(index_names=names, semantic=semantic, vector=vector, std_fields=std, kind_fields=kinds)
    return ex


def index_kind(name: str) -> str:
    return "lesson" if name in ("paws-ds-index", "nearhit-ds-index") else "feedback" if name == "action-feedback" else "incident"


# ── Graph helpers ────────────────────────────────────────────────────────
class G:
    def __init__(self, vertices: dict, edges: list) -> None:
        self.v = vertices
        self.out = defaultdict(list)
        self.adj = defaultdict(set)
        for e in edges:
            self.out[e["out"]].append((e["label"], e["in"]))
            self.adj[e["out"]].add(e["in"])
            self.adj[e["in"]].add(e["out"])

    def p(self, vid: str, key: str, default=None):
        return self.v[vid]["properties"].get(key, default)

    def label(self, vid: str) -> str:
        return self.v[vid]["label"]

    def substation(self, vid: str) -> str | None:
        follow = {"Equipment.EquipmentContainer", "VoltageLevel.Substation", "Terminal.ConnectivityNode",
                  "ConnectivityNode.ConnectivityNodeContainer", "SynchronousMachine.GeneratingUnit"}
        seen, stack = set(), [vid]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            if self.label(x) == "Substation":
                return self.p(x, "Substation.EMSName")
            stack.extend(t for lbl, t in self.out[x] if lbl in follow)
        return None

    def terminal_device(self, tid: str) -> str | None:
        return next((t for lbl, t in self.out[tid] if lbl == "Terminal.ConductingEquipment"), None)

    def max_inertia(self, ems: str) -> float:
        subs = [x for x in self.v if self.label(x) == "Substation" and self.p(x, "Substation.EMSName") == ems]
        vals = [float(self.p(sm, "SynchronousMachine.Inertia"))
                for s in subs for gu in self.adj[s] if self.label(gu) == "GeneratingUnit"
                for sm in self.adj[gu] if self.label(sm) == "SynchronousMachine"
                and self.p(sm, "SynchronousMachine.Inertia") is not None]
        return max(vals) if vals else 0.0


# ── Section A ────────────────────────────────────────────────────────────
def section_a(R: Results, D: dict, ex: dict, g: G) -> dict:
    ems = {g.p(x, "Substation.EMSName") for x in g.v if g.label(x) == "Substation"}
    pseudo = ex["pseudo"]
    owners = defaultdict(set)
    for vid in g.v:
        for k in OWNER_KEYS:
            val = g.p(vid, k)
            if val:
                owners[val].add(vid)
    R.add("A", "graph: vertex ids/pk", [f"{v} pk={g.p(v, 'pk')}" for v in g.v if g.p(v, "pk") != "mock"], f"{len(g.v)} vertices")
    R.add("A", "graph: every vertex has Name/CIMMRID/AliasName/Description",
          [f"{v} missing {k}" for v in g.v for k in ("IdentifiedObject.Name", "IdentifiedObject.CIMMRID",
                                                      "IdentifiedObject.AliasName", "IdentifiedObject.Description")
           if not g.p(v, k)])
    mrids = [g.p(v, "IdentifiedObject.CIMMRID") for v in g.v]
    R.add("A", "graph: CIMMRID unique UUIDs", [m for m in mrids if mrids.count(m) > 1 or not re.fullmatch(r"[0-9a-f\-]{36}", m)])
    eids = [e["id"] for e in D["edges"]]
    R.add("A", "graph: edge endpoints exist, ids unique, pk",
          [f"{e['id']} {e['out']}->{e['in']}" for e in D["edges"] if e["out"] not in g.v or e["in"] not in g.v
           or e["properties"].get("pk") != "mock"] + [i for i in set(eids) if eids.count(i) > 1], f"{len(eids)} edges")

    def owner_ok(comp: str, station: str) -> tuple[str | None, list[str]]:
        errs = []
        own = owners.get(comp, set())
        if len(own) != 1:
            return None, [f"{comp}: {len(own)} owners"]
        vid = next(iter(own))
        dev = g.terminal_device(vid) if g.label(vid) == "Terminal" else vid
        parts = comp.split(".")
        if len(parts) != 3:
            errs.append(f"{comp}: not STATION.CLASS.EQUIP")
            return vid, errs
        if g.substation(vid) != station:
            errs.append(f"{comp}: owner substation {g.substation(vid)} != {station}")
        if parts[0] != station:
            errs.append(f"{comp}: first token != station {station}")
        if g.label(dev) not in CLASS_LABELS.get(parts[1], set()):
            errs.append(f"{comp}: class {parts[1]} vs label {g.label(dev)}")
        if g.p(dev, "IdentifiedObject.Name") != parts[2]:
            errs.append(f"{comp}: EQUIP {parts[2]} != Name {g.p(dev, 'IdentifiedObject.Name')}")
        return vid, errs

    errs, comps = [], set()
    for r in D["scada"]:
        stn = r["station"]
        if stn not in ems | pseudo:
            errs.append(f"scada station {stn}")
        if r["TagId"].split(".")[0] != stn:
            errs.append(f"{r['TagId']} station {stn}")
        if stn not in pseudo:
            comps.add((r["TagId"].rsplit(".", 1)[0], stn))
    for comp, stn in sorted(comps):
        errs += owner_ok(comp, stn)[1]
    R.add("A", "scada: station in EMSName/pseudo; composite owned by one vertex at station with matching class",
          sorted(set(errs)), f"{len(D['scada'])} rows, {len(comps)} composites")
    errs = []
    for r in D["alarms"]:
        if r["station"] not in ems:
            errs.append(f"alarm station {r['station']} not a Substation.EMSName")
        vid, e = owner_ok(r["client_composite_id"], r["station"])
        errs += e
        if vid:
            ok = {g.p(vid, "IdentifiedObject.CIMMRID")}
            if g.label(vid) == "Terminal":
                ok.add(g.p(g.terminal_device(vid), "IdentifiedObject.CIMMRID"))
            if r["mrid"] not in ok:
                errs.append(f"{r['client_composite_id']}: mrid {r['mrid']} not owner/device CIMMRID")
    R.add("A", "alarms: station=EMSName, composite owner, mrid=owner CIMMRID", sorted(set(errs)), f"{len(D['alarms'])} rows")
    errs = []
    for x in g.v:
        if g.label(x) != "VoltageLevel":
            continue
        tok = g.p(x, "VoltageLevel.PathName").split()
        if len(tok) < 4 or tok[2] != g.substation(x) or tok[3] != g.p(x, "IdentifiedObject.Name"):
            errs.append(f"{x}: {tok}")
    for x in g.v:
        if g.label(x) == "ACLineSegment":
            ends = {lbl: g.p(t, "VoltageLevel.PathName").split()[2] for lbl, t in g.out[x]
                    if lbl in ("ACLineSegment.NearVoltageLevel", "ACLineSegment.FarVoltageLevel")}
            if len(set(ends.values())) != 2:
                errs.append(f"{x}: near/far stations {ends}")
    R.add("A", "graph: VoltageLevel.PathName tokens [2]/[3] = station/kV; lines span two stations", errs)
    comp_region = {g.p(x, "Substation.EMSName"): g.p(x, "Substation.Company") for x in g.v if g.label(x) == "Substation"}
    R.add("A", "graph: Substation.Company in NEM regions; all five present",
          [f"{s}={c}" for s, c in comp_region.items() if c not in NEM] +
          [f"region {r} absent" for r in NEM if r not in comp_region.values()])
    sw = [x for x in g.v if g.label(x) == "Switch"]
    R.add("A", "graph: Switch NormalOpen/CurrentOpen are bool, >=1 abnormal",
          [x for x in sw if not isinstance(g.p(x, "Switch.NormalOpen"), bool) or not isinstance(g.p(x, "Switch.CurrentOpen"), bool)]
          + ([] if any(g.p(x, "Switch.NormalOpen") != g.p(x, "Switch.CurrentOpen") for x in sw) else ["no abnormal switch"]))
    cond = [x for x in g.v if g.p(x, "ConductingEquipment.BaseVoltage") is not None]
    has_term = {g.terminal_device(t) for t in g.v if g.label(t) == "Terminal"}
    R.add("A", "graph: every conducting device has a Terminal", [x for x in cond if x not in has_term], f"{len(cond)} devices")
    # Identifier vocabulary for search documents / PDFs.
    tags = {r["TagId"] for r in D["scada"]}
    labels = {r["alarm_label"] for r in D["alarms"]}
    vocab = set(ems) | pseudo | set(NEM) | REPORT_WORDS | {r["measurement"] for r in D["scada"]} | set(CLASS_LABELS)
    vocab |= {g.p(x, "IdentifiedObject.Name") for x in g.v} | {w for lb in labels for w in re.split(r"[ \-]", lb)}
    return dict(ems=ems, owners=owners, tags=tags, labels=labels, vocab=vocab, comp_region=comp_region)


def identifier_errors(text: str, ctx: dict) -> list[str]:
    errs = []
    known_dotted = ctx["tags"] | set(ctx["owners"])
    for tok in re.findall(r"\b[A-Z][A-Z0-9_]*(?:[.\-][A-Z0-9_]+)*\b", text):
        if len(tok) < 2:
            continue
        if "." in tok:
            if tok not in known_dotted:
                errs.append(tok)
        elif tok in ctx["labels"] or tok in ctx["vocab"]:
            continue
        elif "-" in tok and all(p in ctx["vocab"] or not re.match(r"[A-Z]", p) for p in tok.split("-")):
            continue
        else:
            errs.append(tok)
    return errs


# ── Section C: detector-equivalent predicates ────────────────────────────
def floor(dt: datetime, seconds: int) -> datetime:
    e = int(dt.timestamp())
    return datetime.fromtimestamp(e - e % seconds)


def binned(rows: list[dict], seconds: int, pred) -> dict[str, list[tuple[datetime, float, str]]]:
    acc = defaultdict(list)
    for r in rows:
        if pred(r):
            acc[(r["TagId"], r["station"], floor(r["dt"], seconds))].append(r["Value"])
    out = defaultdict(list)
    for (tag, stn, b), vals in sorted(acc.items()):
        out[tag].append((b, sum(vals) / len(vals), stn))
    return out


def scada_signal_hits(D: dict, sig: dict) -> list[tuple[str, datetime, str]]:
    series = binned(D["scada"], 15, lambda r: r["measurement"] == sig["meas"] and any(t in r["TagId"] for t in sig["tag_contains"]))
    hits = []
    for tag, pts in series.items():
        for (_, pv, _), (b, v, stn) in zip(pts, pts[1:]):
            if pv == 0 or v == pv:
                continue
            thr, base = sig.get("threshold", 0), sig.get("baseline")
            ct = sig["cond_type"]
            if ct == "drops_to_near_zero":
                ok = (base is None or abs(pv) >= base) and abs(v) <= thr
            elif ct == "drops_below":
                ok = (pv >= base if base is not None else v < pv) and v <= thr
            elif ct == "rises_above":
                ok = (pv <= base if base is not None else v > pv) and v >= thr
            elif ct == "change_percent":
                ok = abs(v - pv) / abs(pv) * 100 >= thr and (sig.get("direction") != "up" or v > pv) \
                    and (sig.get("direction") != "down" or v < pv)
            else:
                ok = abs(v - pv) >= thr
            if ok:
                hits.append((stn, b, tag))
    return hits


def alarm_signal_hits(D: dict, sig: dict) -> set[str]:
    def match(r, extra=False):
        pre = "extra_" if extra else ""
        col, op, val = sig[pre + "col"], sig.get(pre + "op", "contains"), sig[pre + "val"]
        return r[col] == val if op == "==" else val in r[col]
    counts = defaultdict(int)
    for r in D["alarms"]:
        if match(r) and (not sig.get("extra_col") or match(r, True)):
            wa = floor(r["dt"], 600)
            wb = floor(r["dt"] - timedelta(minutes=5), 600) + timedelta(minutes=5)
            for w in {wa, wb}:
                counts[(r["station"], w)] += 1
    return {s for (s, _), n in counts.items() if n >= sig.get("min_count", 1)}


def minute_diff(a: datetime, b: datetime) -> int:
    return int((floor(a, 60) - floor(b, 60)).total_seconds() // 60)


def section_c(R: Results, D: dict, cfg: dict, g: G, ctx: dict) -> None:
    P = cfg["patterns"]
    gen = lambda r: ".GEN." in r["TagId"] or ".UNIT." in r["TagId"]  # noqa: E731
    expect_scada = {"gen_trip": {"KESTREL", "MARLOW"}, "gen_major_loss": {"KESTREL", "MARLOW"},
                    "bus_collapse": {"MARLOW"}, "line_trip": {"KESTREL", "MARLOW"},
                    "line_kv_collapse": {"KESTREL", "MARLOW"}, "line_overload": {"KESTREL", "MARLOW"},
                    "transformer_trip": {"KESTREL", "MARLOW"}, "transformer_mva_trip": {"KESTREL", "MARLOW"}}
    for sig in cfg["scada_signals"]:
        hits = scada_signal_hits(D, sig)
        got = {s for s, _, _ in hits}
        want = expect_scada.get(sig["id"], set())
        R.add("C", f"scada signal {sig['id']} fires at {sorted(want)}", [f"missing {s}" for s in sorted(want - got)],
              "; ".join(sorted({f"{s}@{b:%H:%M:%S} {t}" for s, b, t in hits}))[:160])
    expect_alarm = {"cb_trip": {"KESTREL", "MARLOW"}, "cb_cluster": {"MARLOW"}, "kv_emer_bus": {"KESTREL", "MARLOW"},
                    "unreas": {"KESTREL"}, "br_warn": {"KESTREL"}, "br_ldsh": {"MARLOW"},
                    "br_emer": {"KESTREL", "MARLOW"}, "inter_ldsh": {"MARLOW"}, "cntr_emer": {"KESTREL"}}
    for sig in cfg["alarm_signals"]:
        got = alarm_signal_hits(D, sig)
        want = expect_alarm.get(sig["id"], set())
        R.add("C", f"alarm signal {sig['id']} fires at {sorted(want)}", [f"missing {s}" for s in sorted(want - got)], ",".join(sorted(got)))
    # generator_degradation
    c = P["generator_degradation"]
    stats = defaultdict(lambda: {"MW": [], "MVAR": []})
    for r in D["scada"]:
        if gen(r) and r["measurement"] in ("MW", "MVAR"):
            equip = ".".join(r["TagId"].split(".")[:3])
            stats[(r["station"], equip, floor(r["dt"], c["window_minutes"] * 60))][r["measurement"]].append(r["Value"])
    deg = []
    for (stn, equip, b), s in sorted(stats.items()):
        if len(s["MVAR"]) > 1 and s["MW"] and statistics.stdev(s["MVAR"]) > c["mvar_stdev_threshold"] and max(s["MW"]) > 5:
            der = round((1 - statistics.fmean(s["MW"]) / max(s["MW"])) * 100, 1)
            if der > c["mw_derating_pct"]:
                deg.append(f"{equip}@{b:%H:%M} stdev={statistics.stdev(s['MVAR']):.1f} derate={der}%")
    R.add("C", "pattern generator_degradation fires only for KESTREL.GEN.U2 @14:00",
          [] if deg and all(d.startswith("KESTREL.GEN.U2@14:00") for d in deg) else [f"got {deg}"], "; ".join(deg))
    # agc_removal_instability
    c = P["agc_removal_instability"]
    mv = defaultdict(list)
    for r in D["scada"]:
        if gen(r) and r["measurement"] == "MVAR":
            mv[(r["station"], floor(r["dt"], 600))].append(r["Value"])
    vol = [(s, b) for (s, b), v in mv.items() if len(v) > 1 and statistics.stdev(v) > c["mvar_stdev_threshold"]]
    agc = sorted({a["station"] for a in D["alarms"] if a["alarm_label"] == "GEN AGC" and any(
        s == a["station"] and abs(minute_diff(a["dt"], b)) <= c["time_proximity_minutes"] for s, b in vol)})
    R.add("C", "pattern agc_removal_instability fires at KESTREL", [] if agc == ["KESTREL"] else [f"got {agc}"], ",".join(agc))
    # generator_motoring
    c = P["generator_motoring"]
    mot = defaultdict(list)
    for r in D["scada"]:
        if gen(r) and r["measurement"] == "MW":
            mot[(r["station"], r["TagId"], floor(r["dt"], c["window_minutes"] * 60))].append(r["Value"])
    motor = []
    for (s, t, b), v in sorted(mot.items()):
        neg = sum(x < c["mw_threshold"] for x in v)
        if neg >= c["min_readings"] and neg / len(v) * 100 < 50:
            motor.append(f"{t}@{b:%H:%M} neg={neg} severe={sum(x < c['mw_severe_threshold'] for x in v)}")
    R.add("C", "pattern generator_motoring (severe) fires for KESTREL.GEN.U2.MW",
          [] if motor and all(m.startswith("KESTREL.GEN.U2.MW") and "severe=0" not in m for m in motor) else [f"got {motor}"],
          "; ".join(motor))
    # unit_unplanned_offline
    c = P["unit_unplanned_offline"]
    mw1 = binned(D["scada"], 60, lambda r: r["measurement"] == "MW" and gen(r))
    cands = []
    for tag, pts in mw1.items():
        for (_, pv, _), (b, v, stn) in zip(pts, pts[1:]):
            if pv > c["mw_drop_threshold"] and v < c["mw_offline_threshold"]:
                post = [x for bb, x, _ in pts if 1 <= (bb - b).total_seconds() / 60 <= c["persistence_minutes"]]
                if len(post) >= c["min_persistence_samples"] and max(post) < c["mw_offline_threshold"]:
                    al = [a for a in D["alarms"] if a["station"] == stn]
                    near = lambda labels, w: sum(a["alarm_label"] in labels and abs(minute_diff(b, a["dt"])) <= w for a in al)  # noqa: E731
                    cands.append(dict(tag=tag, stn=stn, t=b, cb=near(("CB", "CB-CRIT"), c["alarm_window_cb_min"]),
                                      mwcc=near(("MWCC",), c["alarm_window_mwcc_min"]),
                                      kv=near(("KV-EMER-D", "KV-EMER-I"), c["alarm_window_kv_emer_min"]),
                                      inertia=g.max_inertia(stn)))
    passed = [x for x in cands if x["inertia"] >= c["min_inertia_s"]]
    rejected = [x for x in cands if x["inertia"] < c["min_inertia_s"]]
    fmt = lambda x: f"{x['tag']}@{x['t']:%H:%M} cb={x['cb']} mwcc={x['mwcc']} kv={x['kv']} H={x['inertia']}"  # noqa: E731
    ok_pos = [x for x in passed if x["tag"] == "KESTREL.GEN.U1.MW" and x["cb"] and x["mwcc"] and x["kv"]]
    R.add("C", "pattern unit_unplanned_offline fires for KESTREL U1 with CB, MWCC, KV-EMER corroboration",
          [] if ok_pos and len(passed) == 1 else [f"passed {[fmt(x) for x in passed]}"], "; ".join(fmt(x) for x in passed))
    R.add("C", "negative: MARLOW BESS1 is a drop candidate but fails the inertia gate",
          [] if any(x["tag"] == "MARLOW.UNIT.BESS1.MW" for x in rejected) else [f"rejected {[fmt(x) for x in rejected]}"],
          "; ".join(fmt(x) for x in rejected))
    # synchronised_line_trip
    c = P["synchronised_line_trip"]
    ln = binned(D["scada"], 60, lambda r: r["measurement"] == "MW" and ".LINE." in r["TagId"])
    buckets = defaultdict(list)
    for tag, pts in ln.items():
        for (_, pv, _), (b, v, _) in zip(pts, pts[1:]):
            if abs(pv) > c["prev_value_threshold"] and abs(v) < c["current_value_threshold"]:
                buckets[floor(b, int(c["window_minutes"]) * 60)].append((tag, abs(pv) - abs(v)))
    sync = []
    for b, drops in sorted(buckets.items()):
        tags = {t for t, _ in drops}
        stns = {t.split(".")[0] for t in tags}
        total = sum(x for _, x in drops)
        if len(tags) >= c["min_tags_dropped"] and total >= c["min_combined_mw"]:
            sync.append((b, len(tags), len(stns), total))
    R.add("C", "pattern synchronised_line_trip fires cross-station @14:40",
          [] if any(b.strftime("%H:%M") == "14:40" and s >= c["cross_station_min_stations"] for b, _, s, _ in sync) else [f"got {sync}"],
          "; ".join(f"{b:%H:%M} tags={n} stations={s} mw={t:.0f}" for b, n, s, t in sync))
    # frequency: enrichment band classification, ROCOF, situation-level median
    fe = P["frequency_excursion"]
    vr = fe["valid_range"]
    fr = [r for r in D["scada"] if r["measurement"] in ("HZ", "FREQ") and vr["low"] <= r["Value"] <= vr["high"]]
    kept = [r for r in fr if r["station"] not in fe["exclude_stations"]]
    win = defaultdict(list)
    for r in kept:
        win[(r["station"], floor(r["dt"], fe["window_minutes"] * 60))].append(r["Value"])
    band = {}
    for (stn, b), v in win.items():
        if len(v) < fe["min_readings_severe"]:
            continue
        tas = ctx["comp_region"].get(stn) == "TAS" or stn in fe["tas_override"]
        bb = fe["tas_bands"] if tas else fe["mainland_bands"]
        order = ["protected", "generation", "normal"] if tas else ["protected", "network", "generation", "normal"]
        res = "none"
        for name in order:
            n = sum(x < bb[name]["low"] or x > bb[name]["high"] for x in v)
            need = fe["min_readings_normal"] if name == "normal" else fe["min_readings_severe"]
            if n >= fe["min_breach_count"] and len(v) >= need:
                res = name
                break
        band[(stn, b)] = res
    breached = {s for (s, _), r in band.items() if r != "none"}
    R.add("C", "frequency summary: mainland normal-band breach at KESTREL+MARLOW only; TAS clean; excluded dropped",
          ([] if breached == {"KESTREL", "MARLOW"} else [f"breached {sorted(breached)}"]) +
          [f"excluded {s} present" for s in fe["exclude_stations"] if any(k[0] == s for k in band)] +
          [f"tas_override {s} missing" for s in fe["tas_override"] if not any(k[0] == s for k in band)],
          ",".join(sorted(f"{s}@{b:%H:%M}={r}" for (s, b), r in band.items() if r != "none")))
    per_tag = defaultdict(list)
    for r in kept:
        per_tag[r["TagId"]].append((r["dt"], r["Value"]))
    rocof = {t: max((abs(v2 - v1) / (t2 - t1).total_seconds() for (t1, v1), (t2, v2) in zip(p, p[1:])), default=0)
             for t, p in per_tag.items()}
    mainland = {t: x for t, x in rocof.items() if ctx["comp_region"].get(t.split(".")[0]) != "TAS"}
    tasm = {t: x for t, x in rocof.items() if ctx["comp_region"].get(t.split(".")[0]) == "TAS"}
    R.add("C", f"ROCOF > {fe['rocof_threshold']} Hz/s on every mainland HZ/FREQ tag; TAS below",
          [f"{t} {x:.3f}" for t, x in mainland.items() if x <= fe["rocof_threshold"]] +
          [f"{t} {x:.3f}" for t, x in tasm.items() if x > fe["rocof_threshold"]],
          f"mainland min {min(mainland.values()):.3f}, TAS max {max(tasm.values()):.4f}")
    bins = defaultdict(list)
    for r in kept:
        bins[floor(r["dt"], fe["situation_bin_minutes"] * 60)].append(r)
    run = best = 0
    breadth = 0
    for b in sorted(bins):
        vals = [r["Value"] for r in bins[b]]
        med = statistics.median(vals)
        breadth = max(breadth, len({r["station"] for r in bins[b] if r["Value"] < fe["situation_nofb_lower"]}))
        run = run + 1 if not (fe["situation_nofb_lower"] <= med <= fe["situation_nofb_upper"]) else 0
        best = max(best, run)
    R.add("C", "frequency_excursion situation cannot fire (sustained median bins, breadth)",
          [f"median out of band for {best} bins"] if best >= fe["situation_min_sustained_bins"] else [],
          f"max out-of-band median run={best} (<{fe['situation_min_sustained_bins']}), breadth={breadth} (<{fe['situation_breadth_min_stations']})")
    # breadth patterns that cannot fire with two stations
    c = P["regional_cascade"]
    rc = defaultdict(lambda: [set(), set()])
    for a in D["alarms"]:
        if a["alarm_label"] in c["alarm_labels"]:
            w = floor(a["dt"], c["window_minutes"] * 60)
            rc[w][0].add(a["station"])
            if a["alarm_label"] in c["emergency_labels"]:
                rc[w][1].add(a["station"])
    mx = max((len(e) for _, e in rc.values()), default=0)
    R.add("C", "regional_cascade cannot fire", [] if mx < c["min_stations_with_emer"] and
          max((len(s) for s, _ in rc.values()), default=0) < c["min_stations_bypass"] else [f"{mx} emergency stations"],
          f"max emergency stations/5 min={mx} (<{c['min_stations_with_emer']})")
    c = P["system_reactive_event"]

    def arm(label: str, minutes: int) -> int:
        w = defaultdict(set)
        for a in D["alarms"]:
            if a["alarm_label"] == label:
                w[floor(a["dt"], minutes * 60)].add(a["station"])
        return max((len(s) for s in w.values()), default=0)
    svc, unit = arm(c["svc_alarm_label"], c["svc_window_minutes"]), arm(c["unit_alarm_label"], c["unit_window_minutes"])
    R.add("C", "system_reactive_event cannot fire", [] if svc < c["svc_min_stations"] and unit < c["unit_min_stations"]
          else [f"svc={svc} unit={unit}"], f"svc stations={svc} (<{c['svc_min_stations']}), unit stations={unit} (<{c['unit_min_stations']})")
    c = P["coordinated_oscillation"]
    inertial = sorted(s for s in ctx["ems"] if g.max_inertia(s) >= c["min_inertia_s"])
    R.add("C", "coordinated_oscillation cannot fire", [] if len(inertial) < c["min_stations"] else [f"{inertial}"],
          f"inertial stations={inertial} (<{c['min_stations']})")
    matched = set()
    for sig in cfg["alarm_signals"]:
        for a in D["alarms"]:
            if a["alarm_label"] in NOISE_LABELS and (a["alarm_label"] == sig["val"] if sig["op"] == "==" else sig["val"] in a["alarm_label"]):
                matched.add(a["alarm_label"])
    R.add("C", "noise labels present and match no alarm signal",
          [f"{n} absent" for n in NOISE_LABELS if n not in ctx["labels"]] + [f"{m} matches a signal" for m in matched])


# ── Section B + D ────────────────────────────────────────────────────────
def section_b(R: Results, D: dict, ex: dict, g: G, ctx: dict) -> None:
    labels = ctx["labels"]
    R.cover("alarm labels (exact)", ex["alarm_exact"], labels)
    R.cover("alarm labels (contains)", ex["alarm_contains"], {c for c in ex["alarm_contains"] if any(c in l for l in labels)})
    R.cover("measurements", ex["measurements"], {r["measurement"] for r in D["scada"]})
    R.cover("TagId class segments", ex["tag_segments"], {s for s in ex["tag_segments"] if any(s in t for t in ctx["tags"])})
    R.cover("literal tag strings", ex["tags"], ctx["tags"])
    hz_stations = {r["station"] for r in D["scada"] if r["measurement"] in ("HZ", "FREQ")}
    R.cover("detector station lists (EMSName + HZ tag)", ex["exclude_stations"] | ex["tas_override"], ctx["ems"] & hz_stations)
    R.add("B", "tas_override stations are Company TAS", [s for s in ex["tas_override"] if ctx["comp_region"].get(s) != "TAS"])
    R.cover("pseudo region stations (tags present)", ex["pseudo"], {r["station"] for r in D["scada"]})
    R.cover("vertex labels (hasLabel)", ex["labels"], {g.label(x) for x in g.v})
    R.cover("edge labels", ex["edges"], {e["label"] for e in D["edges"]})
    have = set()
    for x in g.v:
        for k, val in g.v[x]["properties"].items():
            cls = k.split(".")[0]
            if "." in k and val not in (None, "") and (cls in ABSTRACT or cls == g.label(x)):
                have.add(k)
    R.cover("vertex property keys (on matching label)", ex["props"], have)
    schema_cols = set(D["schema"].get("WatcherAlarmsAll", [])) | set(D["schema"].get("WatcherScadaAll", []))
    R.cover("KQL columns used by tools (in schema)", ex["kql_columns"], schema_cols)
    R.add("B", "CSV headers equal schema.kql columns",
          ([] if D["alarm_header"] == D["schema"].get("WatcherAlarmsAll") else ["WatcherAlarmsAll header"]) +
          ([] if D["scada_header"] == D["schema"].get("WatcherScadaAll") else ["WatcherScadaAll header"]))
    R.cover("search index names", ex["index_names"], set(D["search"]))
    sem_req = {f"{i}={s}" for i, s in ex["semantic"].items()}
    sem_have = set()
    for i, s in D["search"].items():
        cfgs = s["index"].get("semantic", {}).get("configurations", [])
        sem_have.add(f"{i}={cfgs[0]['name'] if cfgs else None}")
    R.cover("semantic configuration names", sem_req, sem_have)
    vec_req = {f"{i}={v}" for i, v in ex["vector"].items()}
    vec_have = {f"{i}={f['name']}" for i, s in D["search"].items() for f in s["index"]["fields"]
                if f["type"] == "Collection(Edm.Single)"}
    R.cover("vector fields", vec_req, vec_have)
    req, cov = set(), set()
    for i, s in D["search"].items():
        need = ex["std_fields"] | ex["kind_fields"][index_kind(i)]
        req |= {f"{i}:{f}" for f in need}
        idx_fields = {f["name"] for f in s["index"]["fields"]}
        cov |= {f"{i}:{f}" for f in need if f in idx_fields and s["docs"] and all(f in d for d in s["docs"])}
    R.cover("search document fields (index + every doc)", req, cov)


def section_d(R: Results, D: dict, ctx: dict, tools: Path) -> None:
    import pypdf
    skip = {"chunk_id", "parent_id", "filename", "creationDate"}
    for name, s in D["search"].items():
        errs = []
        try:
            reader = pypdf.PdfReader(str(s["pdf"]), strict=True)
            text = "\n".join(p.extract_text() for p in reader.pages)
            meta_title = (reader.metadata or {}).get("/Title", "")
        except Exception as exc:  # noqa: BLE001
            R.add("D", f"{name}: report.pdf parses", [f"{type(exc).__name__}: {exc}"])
            continue
        norm = " ".join(text.split())
        n = 0
        for d in s["docs"]:
            for k, v in d.items():
                if k in skip or not isinstance(v, str) or not v:
                    continue
                parts = [v]
                if k == "full_context":
                    try:
                        parts = [x for x in json.loads(v).values() if isinstance(x, str)]
                    except ValueError:
                        parts = [re.sub(r"^[A-Z][A-Za-z ]+: ", "", p) for p in v.split("\n\n")]
                for part in parts:
                    n += 1
                    if " ".join(part.split()) not in norm:
                        errs.append(f"{d['chunk_id'][:8]}.{k}: {part[:60]!r}")
        R.add("D", f"{name}: report.pdf parses ({len(reader.pages)} pages) and contains every document field",
              errs + ([] if meta_title else ["no /Title"]), f"{len(s['docs'])} docs, {n} text fields")
        idx = s["index"]
        fields = {f["name"]: f for f in idx["fields"]}
        vec = [f for f in idx["fields"] if f["type"] == "Collection(Edm.Single)"]
        vs = idx.get("vectorSearch", {})
        vz = (vs.get("vectorizers") or [{}])[0]
        e2 = []
        if len(vec) != 1 or vec[0].get("dimensions") != 3072 or vec[0].get("vectorSearchProfile") != "hnsw-profile":
            e2.append(f"vector field {vec}")
        if [p["name"] for p in vs.get("profiles", [])] != ["hnsw-profile"] or vs["profiles"][0]["algorithm"] != "hnsw-config" \
                or vs["profiles"][0]["vectorizer"] != "openai-vectorizer":
            e2.append("profile/algorithm/vectorizer names")
        if vz.get("azureOpenAIParameters", {}).get("modelName") != "text-embedding-3-large":
            e2.append("vectorizer model")
        keys = [f for f in idx["fields"] if f.get("key")]
        if [f["name"] for f in keys] != ["chunk_id"]:
            e2.append(f"key fields {keys}")
        ids = [d["chunk_id"] for d in s["docs"]]
        if len(set(ids)) != len(ids):
            e2.append("duplicate chunk_id")
        for d in s["docs"]:
            extra = set(d) - set(fields)
            if extra or vec and vec[0]["name"] in d:
                e2.append(f"{d['chunk_id'][:8]}: unknown/vector fields {sorted(extra)}")
        R.add("D", f"{name}: index.json (key, 3072-d hnsw/openai vectorizer) and docs conform", e2)
        R.add("A", f"{name}: identifiers in documents/PDF exist in graph/telemetry/alarms",
              sorted(set(identifier_errors(text, ctx) + [e for d in s["docs"] for v in d.values()
                                                          for x in (v if isinstance(v, list) else [v])
                                                          for e in identifier_errors(str(x), ctx)])))
    cases = tools.parent / "evaluations/cases"
    bench = sorted({p.stem.split("-")[0] for p in cases.glob("*.yaml")}) if cases.exists() else []
    clean = D["search"].get("investigation-clues-clean-index")
    dirty = D["search"].get("investigation-clues-index")
    if clean and dirty:
        blob = json.dumps(clean["docs"]).lower()
        overlap = {d["chunk"] for d in clean["docs"]} & {d["chunk"] for d in dirty["docs"]}
        R.add("D", "clean index: no benchmark scenario names, distinct from investigation-clues-index",
              [f"benchmark name {b!r}" for b in bench if b in blob] + [f"shared chunk {c[:40]!r}" for c in overlap],
              f"{len(bench)} benchmark names checked")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tools", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=HERE / "out")
    a = ap.parse_args()
    tools = a.tools.resolve()
    cfg = load_config(tools)
    ex = extract(tools, cfg)
    D = load_data(a.out)
    g = G(D["vertices"], D["edges"])
    R = Results()
    ctx = section_a(R, D, ex, g)
    section_b(R, D, ex, g, ctx)
    section_c(R, D, cfg, g, ctx)
    section_d(R, D, ctx, tools)
    print(f"{'category':<46} {'required':>8} {'covered':>8}")
    for cat, req, cov, _ in R.coverage:
        print(f"{cat:<46} {req:>8} {cov:>8}")
    print()
    fails = 0
    for sec in "ABCD":
        for s, name, ok, count, failures in R.checks:
            if s != sec:
                continue
            print(f"[{s}] {'PASS' if ok else 'FAIL'} {name}" + (f" ({count})" if count else ""))
            for f in failures[:25]:
                print(f"      - {f}")
            if len(failures) > 25:
                print(f"      ... {len(failures) - 25} more")
            fails += not ok
    print(f"\n{len(R.checks) - fails}/{len(R.checks)} checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
