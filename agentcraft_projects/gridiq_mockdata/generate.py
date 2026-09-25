#!/usr/bin/env python3
"""Deterministic GridIQ mock dataset: Eventhouse CSVs, Gremlin JSONL, AI Search indexes + PDF reports.

Usage: python3 generate.py [--out DIR] [--check]
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import random
import sys
import tempfile
import uuid
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20260310
PK = "mock"
NS = uuid.uuid5(uuid.NAMESPACE_OID, "gridiq-mockdata")
T0 = datetime(2026, 3, 10, 14, 0, 0)
WINDOW_S = 3600
STEP_S = 15
REPORT_CREATED = "D:20260311090000+10'00'"
EMBEDDING_MODEL = "text-embedding-3-large"
EMBEDDING_DIMS = 3072


def at(hms: str) -> int:
    h, m, s = (int(x) for x in hms.split(":"))
    return (h - 14) * 3600 + m * 60 + s


def ts(s: int) -> str:
    return (T0 + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%S")


EV = {
    "u2_derate": at("14:08:00"), "u2_derate_end": at("14:12:00"), "agc": at("14:10:00"),
    "u1_trip": at("14:30:00"), "freq_low": at("14:30:15"), "freq_hold": at("14:31:00"),
    "freq_back": at("14:33:00"), "km1_overload": at("14:38:00"),
    "km1_trip": at("14:40:00"), "km2_trip": at("14:40:15"), "motoring": at("14:52:00"),
}
FREQ_BURST = {at("14:30:01"): 49.96, at("14:30:02"): 49.83, at("14:30:03"): 49.72,
              at("14:30:04"): 49.66, at("14:30:05"): 49.63}
MOTORING_MW = {at("14:52:00"): -8.0, at("14:52:15"): -12.0, at("14:52:30"): -9.0}

# ── Stations ─────────────────────────────────────────────────────────────
SUBSTATIONS = {
    "KESTREL": dict(region="VIC", division="NORTH", alias="Kestrel Power Station",
                    desc="Kestrel thermal power station (fictional), Victoria", kvs=("330", "22")),
    "MARLOW": dict(region="NSW", division="SOUTH", alias="Marlow Terminal Station",
                   desc="Marlow BESS and SVC terminal station (fictional), New South Wales", kvs=("330", "33")),
}
# (station, region, division, kV, role) — lists fixed by DEFAULT_DETECTOR_CONFIG frequency_excursion.
AUX_STATIONS = [
    ("TTCLOCK", "QLD", "CENTRAL", "275", "excluded"), ("EAGLE_ST", "QLD", "SOUTH", "275", "excluded"),
    ("LYGS", "VIC", "EAST", "220", "excluded"), ("TIMESYNC", "NSW", "NORTH", "330", "excluded"),
    ("BLTS", "SA", "METRO", "275", "excluded"), ("MAGILL", "SA", "METRO", "275", "excluded"),
    ("BLGT", "TAS", "NORTH", "220", "tas"), ("GTCS", "TAS", "SOUTH", "220", "tas"),
    ("NOCS", "TAS", "NORTH", "220", "tas"), ("BLGC", "TAS", "WEST", "220", "tas"),
]
for _stn, _reg, _div, _kv, _role in AUX_STATIONS:
    _pretty = _stn.replace("_", " ").title()
    SUBSTATIONS[_stn] = dict(region=_reg, division=_div, alias=f"{_pretty} Frequency Monitor",
                             desc=f"{_pretty} frequency monitoring point (fictional), {_reg}", kvs=(_kv,))

PSEUDO_STATIONS = ("NSW1", "QLD1", "SA1", "TAS1", "VIC1", "MARKET")


def mrid(vid: str) -> str:
    return str(uuid.uuid5(NS, vid))


def vpath(stn: str, kv: str) -> str:
    s = SUBSTATIONS[stn]
    return f"{s['region']} {s['division']} {stn} {kv}"


# ── Graph ────────────────────────────────────────────────────────────────
CONTAINER_PROPS = ("Switch", "PowerTransformer", "SynchronousMachine", "ACLineSegment", "BusBarSection")


class Graph:
    def __init__(self) -> None:
        self.vertices: dict[str, dict] = {}
        self.edges: list[dict] = []

    def vertex(self, vid: str, label: str, name: str, alias: str, desc: str, props: dict) -> str:
        assert vid not in self.vertices, vid
        p = {"IdentifiedObject.Name": name, "IdentifiedObject.CIMMRID": mrid(vid),
             "IdentifiedObject.AliasName": alias, "IdentifiedObject.Description": desc}
        p.update(props)
        p["pk"] = PK
        self.vertices[vid] = {"id": vid, "label": label, "properties": p}
        return vid

    def edge(self, label: str, out: str, inn: str) -> None:
        assert out in self.vertices and inn in self.vertices, (label, out, inn)
        eid = str(uuid.uuid5(NS, f"{label}|{out}|{inn}"))
        self.edges.append({"id": eid, "label": label, "out": out, "in": inn, "properties": {"pk": PK}})


def build_graph() -> Graph:
    g = Graph()

    def substation(stn: str) -> str:
        s = SUBSTATIONS[stn]
        sid = g.vertex(f"mock-{stn}-Substation", "Substation", stn, s["alias"], s["desc"], {
            "Substation.EMSName": stn, "Substation.Company": s["region"],
            "Substation.PathName": f"{s['region']} {s['division']} {stn}",
            "Substation.NETMOMCompositeId": stn, "Substation.GENMOMCompositeId": stn})
        for kv in s["kvs"]:
            vl = g.vertex(f"mock-{stn}-{kv}-VoltageLevel", "VoltageLevel", kv, f"{s['alias']} {kv} kV",
                          f"{kv} kV voltage level at {s['alias']}", {"VoltageLevel.PathName": vpath(stn, kv)})
            g.edge("VoltageLevel.Substation", vl, sid)
        return sid

    def vl(stn: str, kv: str) -> str:
        return f"mock-{stn}-{kv}-VoltageLevel"

    def cn(stn: str, kv: str, name: str) -> str:
        alias = SUBSTATIONS[stn]["alias"]
        cid = g.vertex(f"mock-{stn}-{kv}-ConnectivityNode-{name}", "ConnectivityNode", name,
                       f"{alias} {kv} kV node {name}", f"Connectivity node {name} at {alias} {kv} kV",
                       {"ConnectivityNode.PathName": f"{vpath(stn, kv)} {name}", "ConnectivityNode.EMSName": name})
        g.edge("ConnectivityNode.ConnectivityNodeContainer", cid, vl(stn, kv))
        return cid

    def equip(stn: str, kv: str, label: str, name: str, alias: str, desc: str, *, container: str,
              scada: str | None = None, conducting: bool = True, extra: dict | None = None) -> str:
        path = f"{vpath(stn, kv)} {name}"
        p = {f"{label}.PathName": path, "PathName": path, "Equipment.SubstationContainer": stn}
        if label in CONTAINER_PROPS:
            p[f"{label}.SubstationContainer"] = stn
            p[f"{label}.VoltageLevelContainer"] = vpath(stn, kv)
        if conducting:
            p["ConductingEquipment.BaseVoltage"] = kv
        if scada:
            p["ScadaDeviceObject.ScadaAliasName"] = scada
        p.update(extra or {})
        did = g.vertex(f"mock-{stn}-{kv}-{label}-{name}", label, name, alias, desc, p)
        g.edge("Equipment.EquipmentContainer", did, container)
        return did

    def terminal(dev: str, seq: int, cnid: str, stn: str, kv: str, scada: str | None = None) -> str:
        dname = g.vertices[dev]["properties"]["IdentifiedObject.Name"]
        p = {"Terminal.SubstationContainer": stn, "Terminal.VoltageLevelContainer": vpath(stn, kv),
             "Terminal.SequenceNumber": seq}
        if scada:
            p["ScadaDeviceObject.ScadaAliasName"] = scada
        tid = g.vertex(f"{dev}-T{seq}", "Terminal", f"{dname}_T{seq}", f"{dname} terminal {seq}",
                       f"Terminal {seq} of {dname} at {stn} {kv} kV", p)
        g.edge("Terminal.ConductingEquipment", tid, dev)
        g.edge("Terminal.ConnectivityNode", tid, cnid)
        return tid

    def switch(stn: str, name: str, a: str, b: str, bay: str, normal_open: bool, current_open: bool,
               alias: str, desc: str, scada: bool = True) -> str:
        sw = equip(stn, "330", "Switch", name, alias, desc, container=vl(stn, "330"),
                   scada=f"{stn}.CB.{name}" if scada else None,
                   extra={"Switch.BayPathName": f"{vpath(stn, '330')} {bay}", "Switch.NormalOpen": normal_open,
                          "Switch.CurrentOpen": current_open, "Switch.EMSName": name})
        terminal(sw, 1, a, stn, "330")
        terminal(sw, 2, b, stn, "330")
        return sw

    def busbar(stn: str, kv: str, name: str, cnid: str, alias: str) -> str:
        bb = equip(stn, kv, "BusBarSection", name, alias, f"{alias} ({stn} {kv} kV)", container=vl(stn, kv),
                   scada=f"{stn}.BUS.{name}",
                   extra={"BusBarSection.EMSName": name, "BusBarSection.BayPathName": f"{vpath(stn, kv)} {name}"})
        terminal(bb, 1, cnid, stn, kv)
        return bb

    # KESTREL — thermal power station, VIC
    k = substation("KESTREL")
    kc = {n: cn("KESTREL", "330", n) for n in ("BUS1", "BUS2", "T1", "T2", "KM1", "KM1L", "KM2")}
    kc.update({n: cn("KESTREL", "22", n) for n in ("U1", "U2")})
    busbar("KESTREL", "330", "BUS1", kc["BUS1"], "Kestrel 330 kV Bus 1")
    busbar("KESTREL", "330", "BUS2", kc["BUS2"], "Kestrel 330 kV Bus 2")
    switch("KESTREL", "CB1", kc["T1"], kc["BUS1"], "T1", False, True, "Kestrel CB1 Unit 1 generator breaker",
           "Unit 1 generator circuit breaker at Kestrel")
    switch("KESTREL", "CB2", kc["T2"], kc["BUS2"], "T2", False, False, "Kestrel CB2 Unit 2 generator breaker",
           "Unit 2 generator circuit breaker at Kestrel")
    switch("KESTREL", "CB3", kc["BUS1"], kc["KM1"], "KM1", False, True, "Kestrel CB3 KM1 line breaker",
           "KM1 line circuit breaker at Kestrel")
    switch("KESTREL", "CB4", kc["BUS2"], kc["KM2"], "KM2", False, True, "Kestrel CB4 KM2 line breaker",
           "KM2 line circuit breaker at Kestrel")
    switch("KESTREL", "CB5", kc["BUS1"], kc["BUS2"], "CPL", True, True, "Kestrel CB5 bus coupler",
           "Bus coupler circuit breaker between Bus 1 and Bus 2 at Kestrel")
    switch("KESTREL", "DS1", kc["KM1"], kc["KM1L"], "KM1", False, False, "Kestrel DS1 KM1 line disconnector",
           "KM1 line disconnector at Kestrel", scada=False)
    for u, t, n in (("U1", "T1", "1"), ("U2", "T2", "2")):
        gu = equip("KESTREL", "22", "GeneratingUnit", u, f"Kestrel Unit {n}", f"Kestrel thermal generating unit {n}",
                   container=k, conducting=False,
                   extra={"GeneratingUnit.EMSName": u, "GeneratingUnit.MaxCapacityMW": 360.0})
        sm = equip("KESTREL", "22", "SynchronousMachine", u, f"Kestrel Unit {n} machine",
                   f"Kestrel unit {n} synchronous machine", container=vl("KESTREL", "22"),
                   scada=f"KESTREL.GEN.{u}",
                   extra={"SynchronousMachine.EMSName": u, "SynchronousMachine.Inertia": 4.5,
                          "SynchronousMachine.BaseMW": 0.0, "SynchronousMachine.BaseKVPU": 1.0,
                          "SynchronousMachine.DTSMOMCompositeId": f"KESTREL.GEN.{u}"})
        g.edge("SynchronousMachine.GeneratingUnit", sm, gu)
        terminal(sm, 1, kc[u], "KESTREL", "22")
        pt = equip("KESTREL", "330", "PowerTransformer", t, f"Kestrel Unit {n} transformer",
                   f"Kestrel 22/330 kV unit transformer {t}", container=k, scada=f"KESTREL.TRANS.{t}",
                   extra={"PowerTransformer.WindingCount": 2,
                          "PowerTransformer.NETMOMCompositeId": f"KESTREL.TRANS.{t}"})
        terminal(pt, 1, kc[u], "KESTREL", "22")
        terminal(pt, 2, kc[t], "KESTREL", "330")

    # MARLOW — BESS + SVC terminal station, NSW
    m = substation("MARLOW")
    mc = {n: cn("MARLOW", "330", n) for n in ("BUS1", "BUS2", "KM1", "KM2", "T1", "SVC1")}
    mc["BESS1"] = cn("MARLOW", "33", "BESS1")
    busbar("MARLOW", "330", "BUS1", mc["BUS1"], "Marlow 330 kV Bus 1")
    busbar("MARLOW", "330", "BUS2", mc["BUS2"], "Marlow 330 kV Bus 2")
    switch("MARLOW", "CB1", mc["BUS1"], mc["KM1"], "KM1", False, True, "Marlow CB1 KM1 line breaker",
           "KM1 line circuit breaker at Marlow")
    switch("MARLOW", "CB2", mc["BUS2"], mc["KM2"], "KM2", False, True, "Marlow CB2 KM2 line breaker",
           "KM2 line circuit breaker at Marlow")
    switch("MARLOW", "CB3", mc["BUS2"], mc["T1"], "T1", False, True, "Marlow CB3 BESS transformer breaker",
           "BESS transformer circuit breaker at Marlow")
    switch("MARLOW", "CB4", mc["BUS1"], mc["SVC1"], "SVC1", False, False, "Marlow CB4 SVC breaker",
           "SVC circuit breaker at Marlow")
    switch("MARLOW", "CB5", mc["BUS1"], mc["BUS2"], "CPL", True, True, "Marlow CB5 bus coupler",
           "Bus coupler circuit breaker between Bus 1 and Bus 2 at Marlow")
    pt = equip("MARLOW", "330", "PowerTransformer", "T1", "Marlow BESS transformer",
               "Marlow 33/330 kV BESS transformer T1", container=m, scada="MARLOW.TRANS.T1",
               extra={"PowerTransformer.WindingCount": 2, "PowerTransformer.NETMOMCompositeId": "MARLOW.TRANS.T1"})
    terminal(pt, 1, mc["BESS1"], "MARLOW", "33")
    terminal(pt, 2, mc["T1"], "MARLOW", "330")
    # Inverter-based unit: GeneratingUnit with a terminal and deliberately no SynchronousMachine.
    bess = equip("MARLOW", "33", "GeneratingUnit", "BESS1", "Marlow Battery 1", "Marlow battery energy storage unit 1",
                 container=m, scada="MARLOW.UNIT.BESS1",
                 extra={"GeneratingUnit.EMSName": "BESS1", "GeneratingUnit.MaxCapacityMW": 200.0})
    terminal(bess, 1, mc["BESS1"], "MARLOW", "33")
    svc = equip("MARLOW", "330", "StaticVarCompensator", "SVC1", "Marlow SVC 1", "Marlow static var compensator 1",
                container=m, scada="MARLOW.SVC.SVC1")
    terminal(svc, 1, mc["SVC1"], "MARLOW", "330")
    cap = equip("MARLOW", "33", "ShuntCompensator", "CAP1", "Marlow Capacitor 1", "Marlow 33 kV shunt capacitor bank 1",
                container=m)
    terminal(cap, 1, mc["BESS1"], "MARLOW", "33")

    # KM1 / KM2 — mutually coupled 330 kV double circuit KESTREL (near) to MARLOW (far)
    line_terms = {}
    for ln, kcn in (("KM1", kc["KM1L"]), ("KM2", kc["KM2"])):
        path = f"{vpath('KESTREL', '330')} {ln}"
        n = ln[-1]
        lid = g.vertex(f"mock-KESTREL-MARLOW-330-ACLineSegment-{ln}", "ACLineSegment", ln,
                       f"Kestrel to Marlow No.{n} 330 kV line", f"{ln} 330 kV line from Kestrel (VIC) to Marlow (NSW)", {
                           "ACLineSegment.PathName": path, "PathName": path,
                           "ACLineSegment.LinePathName": f"KESTREL MARLOW 330 {ln}",
                           "ACLineSegment.BayPathName": path, "ACLineSegment.SubstationContainer": "KESTREL",
                           "ACLineSegment.VoltageLevelContainer": vpath("KESTREL", "330"),
                           "Equipment.SubstationContainer": "KESTREL", "ConductingEquipment.BaseVoltage": "330"})
        g.edge("ACLineSegment.NearVoltageLevel", lid, vl("KESTREL", "330"))
        g.edge("ACLineSegment.FarVoltageLevel", lid, vl("MARLOW", "330"))
        line_terms[ln] = terminal(lid, 1, kcn, "KESTREL", "330", scada=f"KESTREL.LINE.{ln}")
        terminal(lid, 2, mc[ln], "MARLOW", "330", scada=f"MARLOW.LINE.{ln}")
    grp = g.vertex("mock-MutualCouplingGroup-KM1-KM2", "MutualCouplingGroup", "KM1_KM2",
                   "KM1 and KM2 double circuit", "Mutual coupling group of the KM1 and KM2 330 kV double circuit", {})
    mcv = g.vertex("mock-MutualCoupling-KM1-KM2", "MutualCoupling", "KM1_KM2_MC", "KM1 to KM2 coupling",
                   "Zero-sequence mutual coupling between KM1 and KM2", {})
    g.edge("MutualCoupling.First_Terminal", mcv, line_terms["KM1"])
    g.edge("MutualCoupling.Second_Terminal", mcv, line_terms["KM2"])
    g.edge("MutualCoupling.MutualCouplingGroup", mcv, grp)

    for stn, _reg, _div, kv, _role in AUX_STATIONS:
        substation(stn)
        c = cn(stn, kv, "HZMON")
        busbar(stn, kv, "HZMON", c, f"{SUBSTATIONS[stn]['alias']} bus")
    return g


# ── Telemetry ────────────────────────────────────────────────────────────
def _noise(rng: random.Random, sigma: float, clamp: float | None = None) -> float:
    if sigma <= 0:
        return 0.0
    lim = clamp if clamp is not None else 2.5 * sigma
    return max(-lim, min(lim, rng.gauss(0.0, sigma)))


def freq_base(s: int, kind: str) -> tuple[float, float]:
    if kind == "tas":
        return 50.00, 0.008
    if kind == "excluded":
        return 50.30, 0.004
    if s in FREQ_BURST:
        return FREQ_BURST[s], 0.0
    if EV["freq_low"] <= s <= EV["freq_hold"]:
        return 49.62, 0.004
    if EV["freq_hold"] < s <= EV["freq_back"]:
        return 49.62 + (s - EV["freq_hold"]) / (EV["freq_back"] - EV["freq_hold"]) * 0.18, 0.004
    return 50.00, 0.008


def device_sample(dev: str, s: int, rng: random.Random) -> dict[str, float]:
    """One sample per device; MVA derives from the same noisy MW/MVAR draw."""
    n = lambda sd: _noise(rng, sd)  # noqa: E731
    fz = lambda: freq_base(s, "mainland")  # noqa: E731
    if dev == "KESTREL.GEN.U1":
        if s >= EV["u1_trip"]:
            mw = mvar = 0.0
        else:
            mw, mvar = 330 + n(1.0), 80 + n(0.8)
        f, sd = fz()
        return {"MW": mw, "MVAR": mvar, "HZ": f + _noise(rng, sd, 0.025)}
    if dev == "KESTREL.GEN.U2":
        if s in MOTORING_MW:
            mw = MOTORING_MW[s]
        elif s < EV["u2_derate"]:
            mw = 300 + n(1.5)
        elif s < EV["u2_derate_end"]:
            mw = 300 - 110 * (s - EV["u2_derate"]) / (EV["u2_derate_end"] - EV["u2_derate"]) + n(1.5)
        else:
            mw = 190 + n(1.5)
        if s < EV["u2_derate"]:
            mvar = 60 + n(0.8)
        elif s < EV["u1_trip"]:
            mvar = 60 + 14 * math.sin(2 * math.pi * (s - EV["u2_derate"]) / 90) + n(2.0)
        else:
            mvar = 45 + n(0.8)
        return {"MW": mw, "MVAR": mvar}
    if ".LINE." in dev:
        stn, _, ln = dev.split(".")
        trip = EV["km1_trip"] if ln == "KM1" else EV["km2_trip"]
        if s >= trip:
            return {"MW": 0.0, "MVAR": 0.0, "MVA": 0.0, "KV": 0.0}
        sign = 1 if stn == "KESTREL" else -1
        base = {("KESTREL", "KM1"): (180, 40, 330.0), ("KESTREL", "KM2"): (175, 38, 330.0),
                ("MARLOW", "KM1"): (176, 35, 328.0), ("MARLOW", "KM2"): (171, 33, 328.0)}[(stn, ln)]
        mw0, mvar0, kv0 = base
        if ln == "KM1" and s >= EV["km1_overload"]:
            mw0, mvar0 = (190, 161) if stn == "KESTREL" else (186, 157)
        mw, mvar = sign * (mw0 + n(0.4)), sign * (mvar0 + n(0.3))
        return {"MW": mw, "MVAR": mvar, "MVA": math.hypot(mw, mvar), "KV": kv0 + n(0.4)}
    if dev == "KESTREL.BUS.BUS1":
        kv = 312.0 + n(0.5) if EV["u1_trip"] <= s < EV["u1_trip"] + 45 else 330.5 + n(0.3)
        f, sd = fz()
        return {"KV": kv, "HZ": f + _noise(rng, sd, 0.025)}
    if dev == "KESTREL.BUS.BUS2":
        return {"KV": 330.2 + n(0.3)}
    if dev == "MARLOW.BUS.BUS1":
        kv = 318.0 + n(0.5) if EV["km1_trip"] <= s < EV["km1_trip"] + 75 else 328.5 + n(0.3)
        f, sd = fz()
        return {"KV": kv, "FREQ": f + _noise(rng, sd, 0.025)}
    if dev == "MARLOW.BUS.BUS2":
        return {"KV": 0.0 if s >= EV["km2_trip"] else 328.3 + n(0.3)}
    if dev == "KESTREL.TRANS.T1":
        if s >= EV["u1_trip"]:
            return {"MW": 0.0, "MVA": 0.0}
        mw = 325 + n(1.0)
        return {"MW": mw, "MVA": math.hypot(mw, 72)}
    if dev == "KESTREL.TRANS.T2":
        if s in MOTORING_MW:
            mw = MOTORING_MW[s] - 1.0
        elif s < EV["u2_derate"]:
            mw = 295 + n(1.5)
        elif s < EV["u2_derate_end"]:
            mw = 295 - 108 * (s - EV["u2_derate"]) / (EV["u2_derate_end"] - EV["u2_derate"]) + n(1.5)
        else:
            mw = 187 + n(1.5)
        return {"MW": mw, "MVA": math.hypot(mw, 50)}
    if dev == "MARLOW.TRANS.T1":
        if s >= EV["km1_trip"]:
            return {"MW": 0.0, "MVA": 0.0}
        mw = 118 + n(0.5)
        return {"MW": mw, "MVA": math.hypot(mw, 20)}
    if dev == "MARLOW.UNIT.BESS1":
        if s >= EV["km1_trip"]:
            return {"MW": 0.0, "MVAR": 0.0}
        return {"MW": 120 + n(0.5), "MVAR": 2.0 + n(0.3)}
    raise KeyError(dev)


DEVICES = [
    ("KESTREL.GEN.U1", ("MW", "MVAR", "HZ")), ("KESTREL.GEN.U2", ("MW", "MVAR")),
    ("KESTREL.LINE.KM1", ("MW", "MVAR", "MVA", "KV")), ("KESTREL.LINE.KM2", ("MW", "MVAR", "MVA", "KV")),
    ("MARLOW.LINE.KM1", ("MW", "MVAR", "MVA", "KV")), ("MARLOW.LINE.KM2", ("MW", "MVAR", "MVA", "KV")),
    ("KESTREL.BUS.BUS1", ("KV", "HZ")), ("KESTREL.BUS.BUS2", ("KV",)),
    ("MARLOW.BUS.BUS1", ("KV", "FREQ")), ("MARLOW.BUS.BUS2", ("KV",)),
    ("KESTREL.TRANS.T1", ("MW", "MVA")), ("KESTREL.TRANS.T2", ("MW", "MVA")),
    ("MARLOW.TRANS.T1", ("MW", "MVA")), ("MARLOW.UNIT.BESS1", ("MW", "MVAR")),
]
FREQ_DEVICES = {"KESTREL.GEN.U1", "KESTREL.BUS.BUS1", "MARLOW.BUS.BUS1"}

# Region/system roll-up tags carried by pseudo stations (first TagId token): (tag, base, [(t, delta)]).
REGION_TAGS = [
    ("MARKET.REGION.QLD1.CMW", 6200, []), ("MARKET.REGION.SA1.CMW", 1400, []),
    ("MARKET.REGION.TAS1.CMW", 1100, []),
    ("MARKET.SUMM.MAINLAND.INER", 38000, [(EV["u1_trip"], -1800)]),
    ("MARKET.SUMM.NATIONAL.MW", 24500, [(EV["u1_trip"], -330), (EV["km1_trip"], -120)]),
    ("MARKET.SUMM.NATIONAL.RESV", 2600, [(EV["u1_trip"], -30)]),
    ("NSW1.LOAD.RLOADNSW1.MW", 8200, []), ("NSW1.SUMM.MARKET_ESS.MW", 350, [(EV["km1_trip"], -120)]),
    ("NSW1.SUMM.MARKET_SOLAR.MW", 2100, []), ("NSW1.SUMM.NSW_GENERATION.MW", 7600, [(EV["km1_trip"], -120)]),
    ("NSW1.SUMM.NSW_MARKET.MW", 7600, [(EV["km1_trip"], -120)]), ("NSW1.SUMM.NSW_MARKET.RESV", 900, []),
    ("NSW1.SUMM.WIND.MW", 1100, []),
    ("QLD1.LOAD.RLOADQLD1.MW", 6400, []), ("QLD1.SUMM.MARKET_ESS.MW", 180, []),
    ("QLD1.SUMM.MARKET_SOLAR.MW", 2500, []), ("QLD1.SUMM.MARKET_WIND.MW", 700, []),
    ("QLD1.SUMM.QLD_MARKET.MW", 6200, []), ("QLD1.SUMM.QLD_MARKET.RESV", 800, []),
    ("SA1.LOAD.RLOADSA1.MW", 1500, []), ("SA1.SUMM.MARKET_ESS.MW", 90, []),
    ("SA1.SUMM.MARKET_SOLAR.MW", 600, []), ("SA1.SUMM.SA_MARKET.MW", 1400, []),
    ("SA1.SUMM.SA_MARKET.RESV", 300, []), ("SA1.SUMM.WIND.MW", 800, []),
    ("TAS1.LOAD.RLOAD_DEMAND.MW", 1050, []), ("TAS1.SUMM.TAS_MARKET.MW", 1100, []),
    ("TAS1.SUMM.TAS_MARKET.RESV", 250, []), ("TAS1.SUMM.WIND.MW", 300, []),
    ("VIC1.LOAD.RLOADVIC1.MW", 5200, []), ("VIC1.SUMM.MARKET_ESS.MW", 150, []),
    ("VIC1.SUMM.TOTAL_SOLAR.MW", 1300, []), ("VIC1.SUMM.TOTAL_WIND.MW", 1500, []),
    ("VIC1.SUMM.VIC_GENERATION.MW", 5000, [(EV["u1_trip"], -330)]),
    ("VIC1.SUMM.VIC_MARKET.MW", 5000, [(EV["u1_trip"], -330)]), ("VIC1.SUMM.VIC_MARKET.RESV", 700, []),
]


def build_scada(rng: random.Random) -> list[list]:
    rows = []
    grid = list(range(0, WINDOW_S, STEP_S))
    for dev, meas in DEVICES:
        stn = dev.split(".")[0]
        times = sorted(set(grid) | (set(FREQ_BURST) if dev in FREQ_DEVICES else set()))
        for s in times:
            sample = device_sample(dev, s, rng)
            on_grid = s % STEP_S == 0
            for mm in meas:
                if not on_grid and mm not in ("HZ", "FREQ"):
                    continue
                rows.append([ts(s), f"{dev}.{mm}", mm, round(sample[mm], 3), stn])
    for stn, _reg, _div, _kv, role in AUX_STATIONS:
        for s in grid:
            f, sd = freq_base(s, role)
            rows.append([ts(s), f"{stn}.BUS.HZMON.HZ", "HZ", round(f + _noise(rng, sd, 0.025), 3), stn])
    for tag, base, steps in REGION_TAGS:
        stn, meas = tag.split(".")[0], tag.rsplit(".", 1)[1]
        for s in grid:
            v = base + sum(d for t, d in steps if s >= t) + _noise(rng, 0.001 * base)
            rows.append([ts(s), tag, meas, round(v, 3), stn])
    rows.sort(key=lambda r: (r[0], r[1]))
    return rows


# (time, label, composite, priority, text)
ALARMS = [
    ("14:05:00", "TAP_CHANGE", "KESTREL.TRANS.T1", 5, "KESTREL T1 tap position changed 9 to 10"),
    ("14:10:00", "GEN AGC", "KESTREL.GEN.U2", 3, "KESTREL U2 removed from AGC control"),
    ("14:30:02", "CB", "KESTREL.CB.CB1", 2, "KESTREL CB1 U1 generator circuit breaker opened"),
    ("14:30:03", "CB-CRIT", "KESTREL.CB.CB1", 1, "KESTREL CB1 critical breaker trip, U1 protection operated"),
    ("14:30:05", "KV-EMER-D", "KESTREL.BUS.BUS1", 1, "KESTREL BUS1 330 kV voltage emergency, decreasing"),
    ("14:30:10", "UNREAS", "KESTREL.GEN.U1", 3, "KESTREL U1 MW reading unreasonable against breaker state"),
    ("14:31:00", "MWCC", "KESTREL.GEN.U1", 2, "KESTREL U1 MW contingency change of 330 MW"),
    ("14:32:00", "TAP_CHANGE", "KESTREL.TRANS.T2", 5, "KESTREL T2 tap position changed 11 to 12"),
    ("14:40:00", "CB", "KESTREL.CB.CB3", 2, "KESTREL CB3 KM1 line circuit breaker opened"),
    ("14:40:00", "CB", "MARLOW.CB.CB1", 2, "MARLOW CB1 KM1 line circuit breaker opened"),
    ("14:40:01", "BR-WARN", "KESTREL.LINE.KM1", 3, "KESTREL KM1 branch loading warning"),
    ("14:40:15", "CB", "KESTREL.CB.CB4", 2, "KESTREL CB4 KM2 line circuit breaker opened"),
    ("14:40:15", "CB", "MARLOW.CB.CB2", 2, "MARLOW CB2 KM2 line circuit breaker opened"),
    ("14:40:16", "BR-EMER-D", "MARLOW.LINE.KM2", 1, "MARLOW KM2 branch emergency, decreasing"),
    ("14:40:16", "KV-EMER-I", "MARLOW.BUS.BUS2", 1, "MARLOW BUS2 330 kV voltage emergency"),
    ("14:40:17", "CB", "MARLOW.CB.CB3", 2, "MARLOW CB3 BESS transformer circuit breaker opened on undervoltage"),
    ("14:40:18", "BR-EMER-I", "KESTREL.LINE.KM2", 1, "KESTREL KM2 branch emergency, increasing"),
    ("14:40:20", "BR-LDSH-I", "MARLOW.TRANS.T1", 1, "MARLOW T1 branch load shedding required"),
    ("14:40:22", "INTER-LDSH", "MARLOW.LINE.KM1", 1, "MARLOW KM1 interconnector load shedding required"),
    ("14:40:25", "CNTR-EMER", "KESTREL.LINE.KM1", 1, "KESTREL KM1 contingency emergency"),
    ("14:40:30", "HZ-EMER", "MARLOW.BUS.BUS1", 1, "MARLOW BUS1 local frequency emergency"),
    ("14:40:40", "SC VR EMER", "MARLOW.SVC.SVC1", 1, "MARLOW SVC1 reactive limit reached, voltage regulation emergency"),
    ("14:41:00", "UN-VR-CDGN", "KESTREL.GEN.U2", 2, "KESTREL U2 mandatory reactive contingency"),
    ("14:41:10", "UNDERVOLTAGE", "MARLOW.BUS.BUS1", 4, "MARLOW BUS1 undervoltage 318 kV"),
    ("14:45:00", "TAP_CHANGE", "MARLOW.TRANS.T1", 5, "MARLOW T1 tap position changed 7 to 6"),
]


def composite_owners(g: Graph) -> dict[str, str]:
    owners: dict[str, str] = {}
    for vid, v in g.vertices.items():
        p = v["properties"]
        for key in ("ScadaDeviceObject.ScadaAliasName", "SynchronousMachine.DTSMOMCompositeId",
                    "PowerTransformer.NETMOMCompositeId"):
            if key in p:
                assert owners.get(p[key], vid) == vid, p[key]
                owners[p[key]] = vid
    return owners


def build_alarms(g: Graph) -> list[list]:
    owners = composite_owners(g)
    term_dev = {e["out"]: e["in"] for e in g.edges if e["label"] == "Terminal.ConductingEquipment"}
    rows = []
    for hms, label, comp, prio, text in ALARMS:
        owner = owners[comp]
        device = term_dev.get(owner, owner) if g.vertices[owner]["label"] == "Terminal" else owner
        rows.append([ts(at(hms)), label, text, prio, comp, g.vertices[device]["properties"]["IdentifiedObject.CIMMRID"],
                     comp.split(".")[0]])
    return rows


SCHEMA_KQL = """// GridIQ mock Eventhouse schema (AEST wall clock, no offset).
.create-merge table WatcherAlarmsAll (timestamp_aest: datetime, alarm_label: string, alarm_text: string, priority: int, client_composite_id: string, mrid: string, station: string)

.create-merge table WatcherScadaAll (timestamp_aest: datetime, TagId: string, measurement: string, Value: real, station: string)

// Load: .ingest into table WatcherAlarmsAll (h'<sas-url>/WatcherAlarmsAll.csv') with (format='csv', ignoreFirstRecord=true)
// Load: .ingest into table WatcherScadaAll (h'<sas-url>/WatcherScadaAll.csv') with (format='csv', ignoreFirstRecord=true)
"""
ALARM_COLS = ["timestamp_aest", "alarm_label", "alarm_text", "priority", "client_composite_id", "mrid", "station"]
SCADA_COLS = ["timestamp_aest", "TagId", "measurement", "Value", "station"]


def csv_bytes(header: list[str], rows: list[list]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow([f"{c:.3f}" if isinstance(c, float) else c for c in r])
    return buf.getvalue().encode("utf-8")


# ── Minimal PDF writer ───────────────────────────────────────────────────
# No PDF writer is installed and none may be added: emit text-only PDF 1.4 (standard-14 Helvetica, WinAnsi, fixed xref, no /ID or clock).
_HELV = [278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278, 278, 556, 556, 556, 556,
         556, 556, 556, 556, 556, 556, 278, 278, 584, 584, 584, 556, 1015, 667, 667, 722, 722, 667, 611, 778,
         722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278,
         278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556,
         556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500, 334, 260, 334, 584]
PAGE_W, PAGE_H, MARGIN = 612, 792, 54


def _width(text: str, size: float, bold: bool) -> float:
    w = sum(_HELV[ord(c) - 32] if 32 <= ord(c) < 127 else 1000 for c in text)
    return w * size / 1000 * (1.08 if bold else 1.0)


def _wrap(text: str, size: float, bold: bool) -> list[str]:
    out: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            out.append("")
            continue
        cur = words[0]
        for w in words[1:]:
            if _width(f"{cur} {w}", size, bold) <= PAGE_W - 2 * MARGIN:
                cur = f"{cur} {w}"
            else:
                out.append(cur)
                cur = w
        out.append(cur)
    return out


def _pdf_str(text: str) -> str:
    out = []
    for b in text.encode("cp1252"):
        if b in (0x28, 0x29, 0x5C):
            out.append("\\" + chr(b))
        elif 32 <= b < 127:
            out.append(chr(b))
        else:
            out.append(f"\\{b:03o}")
    return "(" + "".join(out) + ")"


def build_pdf(title: str, blocks: list[tuple[str, str]]) -> bytes:
    """blocks: (style, text) with style in {'title','h','p','gap'}."""
    style = {"title": ("F2", 14.0, True), "h": ("F2", 11.0, True), "p": ("F1", 9.5, False)}
    lines: list[tuple[str, float, str]] = []
    for kind, text in blocks:
        if kind == "gap":
            lines.append(("F1", 9.5, ""))
            continue
        font, size, bold = style[kind]
        lines.extend((font, size, ln) for ln in _wrap(text, size, bold))
    pages: list[list[tuple[str, float, str, float]]] = [[]]
    y = PAGE_H - MARGIN
    for font, size, ln in lines:
        lead = size * 1.4
        if y - lead < MARGIN + 20:
            pages.append([])
            y = PAGE_H - MARGIN
        y -= lead
        if ln:
            pages[-1].append((font, size, ln, y))
    objs: list[bytes] = [b"", b"", b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
                         b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
                         (f"<< /Title {_pdf_str(title)} /CreationDate ({REPORT_CREATED}) "
                          f"/Producer (gridiq_mockdata generate.py) >>").encode("latin-1")]
    kids = []
    for page in pages:
        ops = ["BT"]
        for font, size, ln, yy in page:
            ops.append(f"/{font} {size:g} Tf 1 0 0 1 {MARGIN} {yy:.2f} Tm {_pdf_str(ln)} Tj")
        ops.append("ET")
        data = "\n".join(ops).encode("latin-1")
        objs.append(b"<< /Length %d >>\nstream\n" % len(data) + data + b"\nendstream")
        content_num = len(objs)
        objs.append((f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
                     f"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents {content_num} 0 R >>").encode())
        kids.append(len(objs))
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = f"<< /Type /Pages /Kids [{' '.join(f'{k} 0 R' for k in kids)}] /Count {len(kids)} >>".encode()
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, 1):
        offsets.append(out.tell())
        out.write(f"{i} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode())
    for off in offsets:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R /Info 5 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


# ── AI Search ────────────────────────────────────────────────────────────
INCIDENT_INDEXES = ("investigation-clues-index", "investigation-clues-clean-index", "smirks-index")
LESSON_INDEXES = ("paws-ds-index", "nearhit-ds-index")
SEMANTIC = {"investigation-clues-index": "investigation-clues-index-semantic",
            "investigation-clues-clean-index": "investigation-clues-clean-index-semantic",
            "smirks-index": "smirks-index-semantic", "paws-ds-index": "paws-ds-semantic-configuration",
            "nearhit-ds-index": "nearhit-ds-semantic-configuration", "action-feedback": None}
# Vector field per index as passed by the tools (vector_field=...); action-feedback keeps the provisioning default.
VECTOR_FIELD = {"investigation-clues-index": "snippet_vector", "investigation-clues-clean-index": "snippet_vector",
                "smirks-index": "text_vector", "paws-ds-index": "snippet_vector",
                "nearhit-ds-index": "snippet_vector", "action-feedback": "text_vector"}
STANDARD_FIELDS = [
    ("chunk_id", dict(key=True, searchable=True, filterable=True, analyzer="keyword")),
    ("parent_id", dict(filterable=True)), ("chunk", dict(searchable=True)),
    ("title", dict(searchable=True, filterable=True)), ("filename", dict(filterable=True)),
    ("report_date", dict(filterable=True, sortable=True)),
    ("equipment_type", dict(searchable=True, filterable=True)), ("location", dict(searchable=True, filterable=True)),
    ("incident_date", dict(filterable=True)), ("full_context", dict()), ("cause", dict(searchable=True)),
    ("conclusions", dict(searchable=True)), ("recommendations", dict(searchable=True)),
    ("related_incidents", dict(searchable=True)),
]
EXTRA_FIELDS = {
    "incident": [("creationDate", dict(filterable=True, sortable=True)), ("rectification", dict(searchable=True))],
    "lesson": [("lesson_id", dict(filterable=True)), ("incident", dict(searchable=True, filterable=True)),
               ("symptom", dict(searchable=True)), ("what_happened", dict(searchable=True)),
               ("why_it_matters", dict(searchable=True)), ("if_you_see_this", dict(searchable=True)),
               ("equipment", dict(type="Collection(Edm.String)", searchable=True, filterable=True)),
               ("source_document", dict(filterable=True)), ("source_chapter", dict(searchable=True, filterable=True)),
               ("guide", dict(searchable=True)),
               ("tags", dict(type="Collection(Edm.String)", searchable=True, filterable=True, facetable=True))],
    "feedback": [("feedback_id", dict(filterable=True)), ("action_text", dict(searchable=True)),
                 ("status", dict(filterable=True, facetable=True)), ("operator_note", dict(searchable=True)),
                 ("outcome", dict(searchable=True)), ("station", dict(filterable=True, facetable=True)),
                 ("equipment_ids", dict(type="Collection(Edm.String)", searchable=True, filterable=True)),
                 ("reasoning", dict(searchable=True)), ("guide", dict(searchable=True)),
                 ("created_at", dict(filterable=True, sortable=True)),
                 ("tags", dict(type="Collection(Edm.String)", searchable=True, filterable=True, facetable=True))],
}


def index_kind(name: str) -> str:
    return "incident" if name in INCIDENT_INDEXES else "lesson" if name in LESSON_INDEXES else "feedback"


def index_definition(name: str) -> dict:
    fields = []
    for fname, attrs in STANDARD_FIELDS + EXTRA_FIELDS[index_kind(name)]:
        f = {"name": fname, "type": attrs.get("type", "Edm.String"), "key": attrs.get("key", False),
             "searchable": attrs.get("searchable", False), "filterable": attrs.get("filterable", False),
             "retrievable": True, "sortable": attrs.get("sortable", False), "facetable": attrs.get("facetable", False)}
        if "analyzer" in attrs:
            f["analyzer"] = attrs["analyzer"]
        fields.append(f)
    fields.append({"name": VECTOR_FIELD[name], "type": "Collection(Edm.Single)", "searchable": True,
                   "retrievable": False, "stored": True, "dimensions": EMBEDDING_DIMS,
                   "vectorSearchProfile": "hnsw-profile"})
    d = {
        "name": name, "fields": fields,
        "vectorSearch": {
            "algorithms": [{"name": "hnsw-config", "kind": "hnsw",
                            "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}],
            "profiles": [{"name": "hnsw-profile", "algorithm": "hnsw-config", "vectorizer": "openai-vectorizer"}],
            "vectorizers": [{"name": "openai-vectorizer", "kind": "azureOpenAI", "azureOpenAIParameters": {
                "resourceUri": "${FOUNDRY_ENDPOINT}", "deploymentId": EMBEDDING_MODEL, "modelName": EMBEDDING_MODEL}}],
        },
    }
    if SEMANTIC[name]:
        d["semantic"] = {"configurations": [{"name": SEMANTIC[name], "prioritizedFields": {
            "titleField": {"fieldName": "title"}, "prioritizedContentFields": [{"fieldName": "chunk"}],
            "prioritizedKeywordsFields": []}}]}
    return d


# Incident clue records: (short, equipment_type, location, details, key_events, cause, conclusions,
#                         recommendations, rectification, related)
CLUES_U1 = [
    ("unit MW collapse with generator breaker trip", "Generating unit", "KESTREL",
     "KESTREL U1 (KESTREL.GEN.U1) output fell from 330 MW to 0 MW between 14:29:45 and 14:30:00 AEST on "
     "2026-03-10. KESTREL.TRANS.T1.MW and KESTREL.TRANS.T1.MVA fell to 0 in the same sample.",
     "14:30:02 CB on KESTREL.CB.CB1; 14:30:03 CB-CRIT on KESTREL.CB.CB1; 14:30:10 UNREAS on KESTREL.GEN.U1; "
     "14:31:00 MWCC on KESTREL.GEN.U1.",
     "Generator protection opened CB1, the U1 generator circuit breaker, disconnecting U1 and T1 from BUS1.",
     "A genuine unit trip, not a telemetry fault: breaker alarms and the unit transformer confirm the loss. "
     "KESTREL.GEN.U1.MW stayed at 0 MW for the rest of the hour.",
     "Next action: confirm KESTREL.GEN.U1.MW remains at or below 5 MW for 5 minutes, then check the graph inertia "
     "of the U1 synchronous machine (4.5 s) before classifying the event as an unplanned unit outage.",
     "U1 held off line at KESTREL pending protection relay review.", "smirks-index report on 2026-03-10"),
    ("bus voltage emergency after the unit trip", "Busbar", "KESTREL",
     "KV-EMER-D was raised on KESTREL.BUS.BUS1 at 14:30:05. KESTREL.BUS.BUS1.KV dipped from 330 kV to about "
     "312 kV for 45 seconds while KESTREL.BUS.BUS2.KV stayed near 330 kV.",
     "14:30:05 KV-EMER-D on KESTREL.BUS.BUS1; bus coupler CB5 open as normal.",
     "Loss of U1 reactive output (KESTREL.GEN.U1.MVAR fell from 80 MVAR to 0) depressed BUS1 voltage; BUS2 was "
     "supported by U2.",
     "Voltage recovered without operator action; the KV-EMER-D alarm corroborates the U1 trip.",
     "Next action: review KESTREL.BUS.BUS1.KV and KESTREL.BUS.BUS2.KV together and confirm CB5 remained open.",
     "No rectification needed; the alarm was reset at KESTREL.", "none"),
    ("mainland frequency dip after generation loss", "System frequency", "VIC",
     "KESTREL.GEN.U1.HZ, KESTREL.BUS.BUS1.HZ and MARLOW.BUS.BUS1.FREQ fell from 50.00 Hz to 49.62 Hz by "
     "14:30:15 with a rate of change of frequency above 0.1 Hz/s. Tasmanian monitors BLGT.BUS.HZMON.HZ, "
     "GTCS.BUS.HZMON.HZ, NOCS.BUS.HZMON.HZ and BLGC.BUS.HZMON.HZ stayed at 50.00 Hz.",
     "14:30:15 to 14:33:00 mainland frequency below 49.85 Hz; recovery to 50.00 Hz by 14:33:15; "
     "MARKET.SUMM.NATIONAL.MW fell by 330 MW and MARKET.SUMM.MAINLAND.INER fell by 1800 MWs.",
     "Loss of 330 MW from KESTREL U1 in VIC.",
     "A normal operating band breach on the mainland only. The clock references TTCLOCK, EAGLE_ST, LYGS, "
     "TIMESYNC, BLTS and MAGILL read 50.30 Hz throughout and are excluded from frequency assessment.",
     "Next action: compare VIC1.SUMM.VIC_GENERATION.MW and VIC1.SUMM.VIC_MARKET.MW before and after 14:30:00 to "
     "size the loss.",
     "Frequency restored by frequency control reserves without directions.", "none"),
    ("reactive hunting after AGC removal", "Generating unit", "KESTREL",
     "KESTREL.GEN.U2.MVAR swung by more than 10 MVAR around 60 MVAR from 14:08 to 14:30 while "
     "KESTREL.GEN.U2.MW was derated from 300 MW to 190 MW.",
     "14:10:00 GEN AGC on KESTREL.GEN.U2; the MVAR swings stopped at 14:30:00.",
     "U2 excitation control hunting after the unit was removed from AGC.",
     "Consistent with generator degradation and AGC removal instability at KESTREL, independent of the U1 trip.",
     "Next action: compute the 10-minute standard deviation of KESTREL.GEN.U2.MVAR and compare the 30-minute "
     "average of KESTREL.GEN.U2.MW with its maximum.",
     "U2 excitation limiter settings to be checked by the KESTREL maintenance team.", "none"),
]
CLUES_LINE = [
    ("parallel line MW collapse at both ends", "Transmission line", "KESTREL",
     "KESTREL.LINE.KM1.MW fell from 190 MW to 0 MW at 14:40:00 and KESTREL.LINE.KM2.MW fell from 175 MW to 0 MW "
     "at 14:40:15 AEST on 2026-03-10; MARLOW.LINE.KM1.MW and MARLOW.LINE.KM2.MW fell to 0 MW in the same samples.",
     "14:40:00 CB on KESTREL.CB.CB3 and MARLOW.CB.CB1; 14:40:15 CB on KESTREL.CB.CB4 and MARLOW.CB.CB2.",
     "Both circuits of the KM1 and KM2 double circuit 330 kV corridor between KESTREL and MARLOW tripped within "
     "15 seconds.",
     "A synchronised line trip across two stations with more than 100 MW of combined flow lost.",
     "Next action: run a corridor query for KM1 to list the mutually coupled circuit KM2 and both endpoint stations.",
     "Circuits restored after a line patrol.", "none"),
    ("line voltage collapse after an overload step", "Transmission line", "KESTREL",
     "KESTREL.LINE.KM1.MVA rose by 35 percent at 14:38:00 before the trip; KESTREL.LINE.KM1.KV and "
     "MARLOW.LINE.KM1.KV fell from 330 kV to 0 kV at 14:40:00.",
     "14:38:00 KM1 MVA step up; 14:40:01 BR-WARN on KESTREL.LINE.KM1; 14:40:25 CNTR-EMER on KESTREL.LINE.KM1.",
     "KM1 loading increased shortly before the corridor fault.",
     "Line KV collapse at both ends confirms de-energisation rather than telemetry loss.",
     "Next action: check KESTREL.LINE.KM1.MVA against the line rating for the ten minutes before 14:40:00.",
     "Line rating review requested.", "none"),
    ("bus collapse and transformer trip at the receiving end", "Busbar", "MARLOW",
     "MARLOW.BUS.BUS2.KV fell from 328 kV to 0 kV at 14:40:15. MARLOW.TRANS.T1.MW, MARLOW.TRANS.T1.MVA and "
     "MARLOW.UNIT.BESS1.MW fell to 0 at 14:40:00.",
     "14:40:16 KV-EMER-I on MARLOW.BUS.BUS2; 14:40:17 CB on MARLOW.CB.CB3; 14:40:20 BR-LDSH-I on MARLOW.TRANS.T1.",
     "BUS2 was fed only through KM2 with the bus coupler CB5 open; BESS1 tripped on the KM1 fault.",
     "Loss of BUS2 and BESS1 is consequential to the line trip. BESS1 has no synchronous machine and is not an "
     "inertial unit.",
     "Next action: query switch states at MARLOW 330 kV and confirm CB1, CB2 and CB3 are open.",
     "BUS2 re-energised through CB5 after the corridor event.", "none"),
    ("emergency alarm burst at two stations", "Protection alarms", "MARLOW",
     "BR-EMER-D on MARLOW.LINE.KM2 at 14:40:16, BR-EMER-I on KESTREL.LINE.KM2 at 14:40:18, INTER-LDSH on "
     "MARLOW.LINE.KM1 at 14:40:22 and HZ-EMER on MARLOW.BUS.BUS1 at 14:40:30.",
     "Emergency alarms came from two stations only: KESTREL and MARLOW.",
     "Loss of the corridor between VIC and NSW.",
     "Two stations in emergency is below the eight station regional cascade threshold.",
     "Next action: count the stations raising emergency alarms within 5 minutes before escalating to a regional "
     "cascade.",
     "None required.", "none"),
]
SMIRKS = [
    ("event summary", "Transmission line", "KESTREL",
     "At 14:40:00 AEST on 2026-03-10 the KM1 330 kV line between KESTREL (VIC) and MARLOW (NSW) tripped, followed "
     "by the parallel KM2 line at 14:40:15. MARLOW BUS2 and BESS1 were lost. Earlier, at 14:30:00, KESTREL U1 "
     "tripped from 330 MW.",
     "14:30:00 U1 trip; 14:38:00 KM1 MVA rise of 35 percent; 14:40:00 KM1 trip; 14:40:15 KM2 trip; 14:40:40 "
     "SC VR EMER on MARLOW.SVC.SVC1.",
     "Simultaneous trip of a mutually coupled double circuit; root cause under investigation.",
     "The event was a non-credible contingency of the KM1 and KM2 double circuit.",
     "Reclassify the simultaneous trip of KM1 and KM2 as credible during high loading.",
     "Both lines returned to service at 16:05 AEST.", "investigation-clues report on the KESTREL U1 trip"),
    ("power system response", "Busbar", "MARLOW",
     "MARLOW.BUS.BUS2.KV collapsed to 0 kV; MARLOW.TRANS.T1 and MARLOW.UNIT.BESS1 were disconnected; "
     "NSW1.SUMM.MARKET_ESS.MW and NSW1.SUMM.NSW_GENERATION.MW fell by 120 MW.",
     "14:40:16 KV-EMER-I on MARLOW.BUS.BUS2; 14:41:00 UN-VR-CDGN on KESTREL.GEN.U2; 14:41:10 UNDERVOLTAGE on "
     "MARLOW.BUS.BUS1.",
     "Loss of the KM2 supply to BUS2 while the bus coupler CB5 was open.",
     "The reactive shortfall was local: SC VR EMER at one station and UN-VR-CDGN at one station are below the "
     "system reactive event thresholds.",
     "Review the SVC1 reactive reserve at MARLOW.",
     "CB5 closed at 15:10 AEST to restore BUS2.", "none"),
    ("earlier unit trip and motoring", "Generating unit", "KESTREL",
     "KESTREL U1 tripped at 14:30:00 with CB and CB-CRIT on KESTREL.CB.CB1, KV-EMER-D on KESTREL.BUS.BUS1 and "
     "MWCC on KESTREL.GEN.U1. Mainland frequency fell to 49.62 Hz.",
     "From 14:52:00 to 14:52:30 KESTREL.GEN.U2.MW read -8 MW, -12 MW and -9 MW (motoring).",
     "U1 generator protection operation.",
     "The U1 trip and the later U2 motoring are separate from the corridor event.",
     "Check the U2 reverse power protection settings.",
     "U2 motoring cleared at 14:52:45.", "none"),
]
# Lesson records: (lesson_id, incident, symptom, what_happened, why_it_matters, if_you_see_this, equipment,
#                  chapter, guide, tags, location)
PAWS = [
    ("paws-unit-trip-01", "Unit trip response", "Unit MW to zero with CB and CB-CRIT alarms",
     "A generating unit such as KESTREL U1 drops from full output to 0 MW in one sample and its generator breaker "
     "KESTREL.CB.CB1 raises CB and CB-CRIT.",
     "Unplanned loss of an inertial unit reduces system inertia and can start a frequency excursion.",
     "Confirm KESTREL.GEN.U1.MW stays at or below 5 MW for 5 minutes, check for MWCC within 15 minutes and notify "
     "the VIC region desk.",
     ["KESTREL.GEN.U1", "KESTREL.CB.CB1"], "Section 2 Unit trip", "Unit trip procedure steps 1 to 4",
     ["unit-trip", "CB-CRIT"], "KESTREL"),
    ("paws-kv-emer-02", "Bus voltage emergency response", "KV-EMER on a bus after a trip",
     "KV-EMER-D or KV-EMER-I is raised on a bus composite such as KESTREL.BUS.BUS1 or MARLOW.BUS.BUS2 after a unit "
     "or line trip.",
     "A bus voltage emergency can precede loss of load or a bus collapse.",
     "Read KESTREL.BUS.BUS1.KV or MARLOW.BUS.BUS2.KV; below 2 kV treat the bus as collapsed and check the bus "
     "coupler CB5.",
     ["KESTREL.BUS.BUS1", "MARLOW.BUS.BUS2"], "Section 3 Voltage emergency", "Voltage emergency procedure step 2",
     ["KV-EMER-D", "KV-EMER-I"], "MARLOW"),
    ("paws-frequency-03", "Frequency dip response", "Frequency below 49.85 Hz after generation loss",
     "Mainland HZ and FREQ tags such as KESTREL.BUS.BUS1.HZ and MARLOW.BUS.BUS1.FREQ fall below 49.85 Hz after a "
     "generation loss.",
     "Frequency outside the normal operating band for more than a few minutes needs reserve action.",
     "Exclude the clock stations TTCLOCK, EAGLE_ST, LYGS, TIMESYNC, BLTS and MAGILL and assess BLGT, GTCS, NOCS and "
     "BLGC against the Tasmanian bands.",
     ["KESTREL.BUS.BUS1", "MARLOW.BUS.BUS1"], "Section 4 Frequency", "Frequency procedure step 1",
     ["frequency", "HZ-EMER"], "VIC"),
]
NEARHIT = [
    ("nearhit-svc-01", "SVC reactive limit near miss", "SC VR EMER on MARLOW SVC1 after corridor trip",
     "At 14:40:40 SVC1 at MARLOW reached its reactive limit and raised SC VR EMER on MARLOW.SVC.SVC1 while "
     "MARLOW.BUS.BUS1.KV was near 318 kV.",
     "SVC1 was the only dynamic reactive source at MARLOW; one more contingency could have collapsed BUS1.",
     "Check CAP1 availability, confirm CB4 is closed and request reactive support from KESTREL U2.",
     ["MARLOW.SVC.SVC1", "MARLOW.BUS.BUS1"], "Chapter 1 Reactive reserve", "Reactive reserve checklist",
     ["SC VR EMER", "reactive"], "MARLOW"),
    ("nearhit-coupler-02", "Bus coupler configuration near miss", "Coupler CB5 open while BUS2 fed by one line",
     "MARLOW BUS2 was supplied only through KM2 and CB2 with the bus coupler CB5 open, so the KM2 trip at 14:40:15 "
     "collapsed BUS2.",
     "A single supply to a bus turns one line trip into a bus outage.",
     "Before switching, confirm the coupler state and the number of supplies to each bus.",
     ["MARLOW.CB.CB5", "MARLOW.BUS.BUS2"], "Chapter 2 Switching", "Switching configuration checklist",
     ["bus-collapse"], "MARLOW"),
    ("nearhit-bess-03", "Battery trip classification near miss", "BESS1 tripped with no inertia contribution",
     "MARLOW BESS1 (MARLOW.UNIT.BESS1) dropped from 120 MW to 0 MW at 14:40:00.",
     "BESS1 has no synchronous machine, so the unit trip check correctly does not treat it as an inertial unit.",
     "Use the MARLOW.UNIT.BESS1.MW trend and the CB alarm on MARLOW.CB.CB3 to confirm the disconnection.",
     ["MARLOW.UNIT.BESS1", "MARLOW.CB.CB3"], "Chapter 3 Inverter plant", "Inverter plant trip checklist",
     ["bess", "inertia"], "MARLOW"),
]
FEEDBACK = [
    dict(feedback_id="af-20260310-001", action_text="Confirm the KESTREL U1 trip and hold U1 off line",
         status="completed", operator_note="U1 confirmed tripped by CB1 and held off line.",
         outcome="Unit outage recorded; no further alarms from KESTREL.GEN.U1.", station="KESTREL",
         equipment_ids=["KESTREL.GEN.U1", "KESTREL.CB.CB1"],
         reasoning="KESTREL.GEN.U1.MW at 0 MW with CB and CB-CRIT on KESTREL.CB.CB1.",
         guide="PAWS unit trip procedure", created_at="2026-03-10T14:36:00", tags=["unit-trip", "KESTREL"]),
    dict(feedback_id="af-20260310-002", action_text="Close the MARLOW bus coupler CB5 to restore BUS2",
         status="completed", operator_note="CB5 closed at 15:10 after KM2 was confirmed isolated.",
         outcome="MARLOW.BUS.BUS2.KV restored.", station="MARLOW", equipment_ids=["MARLOW.CB.CB5", "MARLOW.BUS.BUS2"],
         reasoning="BUS2 collapsed to 0 kV at 14:40:15 with KV-EMER-I on MARLOW.BUS.BUS2.",
         guide="PAWS voltage emergency procedure", created_at="2026-03-10T15:10:00", tags=["bus-collapse", "MARLOW"]),
    dict(feedback_id="af-20260310-003", action_text="Direct KESTREL U2 to raise reactive output",
         status="declined", operator_note="U2 is at its reactive limit with UN-VR-CDGN; direction declined.",
         outcome="No change to KESTREL.GEN.U2.MVAR.", station="KESTREL", equipment_ids=["KESTREL.GEN.U2"],
         reasoning="UN-VR-CDGN on KESTREL.GEN.U2 at 14:41:00.", guide="Reactive reserve checklist",
         created_at="2026-03-10T14:42:00", tags=["reactive", "KESTREL"]),
    dict(feedback_id="af-20260310-004", action_text="Reclose KM1 at KESTREL CB3", status="declined",
         operator_note="A line patrol is required before reclosing KM1.",
         outcome="KM1 remained open until the patrol completed.", station="KESTREL",
         equipment_ids=["KESTREL.LINE.KM1", "KESTREL.CB.CB3"],
         reasoning="BR-WARN and CNTR-EMER on KESTREL.LINE.KM1.", guide="Line reclose procedure",
         created_at="2026-03-10T14:45:00", tags=["line-trip", "KESTREL"]),
]
REPORTS = {
    "investigation-clues-index": ("Investigation Clue Sheet: KESTREL U1 Unit Trip, 2026-03-10", CLUES_U1),
    "investigation-clues-clean-index": ("Investigation Clue Sheet: KM1 and KM2 Line Trip, 2026-03-10", CLUES_LINE),
    "smirks-index": ("Operational Event Report: Trip of KM1 and KM2 330 kV Lines, 2026-03-10", SMIRKS),
    "paws-ds-index": ("PAWS Procedure: Unit Trip and KV-EMER Response", PAWS),
    "nearhit-ds-index": ("Near-Miss Report: SC VR EMER on MARLOW SVC1, 2026-03-10", NEARHIT),
    "action-feedback": ("Operator Action Feedback Log, 2026-03-10", FEEDBACK),
}
INTRO = ("Fictional report generated for the GridIQ mock dataset. It names only mock stations, equipment, "
         "SCADA tags and alarm labels present in the mock Eventhouse and graph data. Times are AEST.")


def _chunk_id(title: str, chunk: str) -> str:
    return hashlib.md5(f"{title}:{chunk[:100]}".encode()).hexdigest()


def build_documents(index: str) -> tuple[str, list[dict]]:
    report_title, records = REPORTS[index]
    docs = []
    kind = index_kind(index)
    for i, rec in enumerate(records, 1):
        if kind == "incident":
            short, etype, loc, details, keyev, cause, concl, recs, rect, related = rec
            symptoms = f"{details}\n{keyev}"
            chunk = f"SYMPTOMS:\n{symptoms}\n\nCAUSE:\n{cause}\n\nCONCLUSIONS:\n{concl}"
            title = f"{report_title} \u2014 {i}. {short}"
            full = "\n\n".join(f"{k}: {v}" for k, v in (
                ("Incident Details", details), ("Incident Key Events", keyev), ("Incident Cause", cause),
                ("Rectification", rect), ("Conclusions", concl), ("Recommendations", recs),
                ("Related Incidents", related)))
            doc = dict(chunk=chunk, title=title, equipment_type=etype, location=loc, incident_date="2026-03-10",
                       report_date="2026-03-11", full_context=full, cause=cause, conclusions=concl,
                       recommendations=recs, related_incidents=related, creationDate=REPORT_CREATED,
                       rectification=rect)
        elif kind == "lesson":
            lid, incident, symptom, what, why, ifsee, equipment, chapter, guide, tags, loc = rec
            assert len(symptom) <= 60, symptom
            eq = ", ".join(equipment)
            chunk = "\n\n".join([f"SYMPTOM: {symptom}", f"WHAT HAPPENED: {what}", f"WHY IT MATTERS: {why}",
                                 f"IF YOU SEE THIS: {ifsee}", f"EQUIPMENT: {eq}"])
            doc = dict(chunk=chunk, title=f"{incident} \u2014 {symptom[:60]}", equipment_type=eq, location=loc,
                       incident_date="2026-03-10", report_date="2026-03-11", full_context=chunk, cause=what,
                       conclusions=why, recommendations=ifsee, related_incidents="smirks-index report on 2026-03-10",
                       lesson_id=lid, incident=incident, symptom=symptom, what_happened=what, why_it_matters=why,
                       if_you_see_this=ifsee, equipment=list(equipment), source_document="report.pdf",
                       source_chapter=chapter, guide=guide, tags=list(tags))
        else:
            r = rec
            assert len(r["action_text"]) <= 80
            eq = ", ".join(r["equipment_ids"])
            chunk = "\n\n".join([f"ACTION: {r['action_text']}", f"STATUS: {r['status']}",
                                 f"OPERATOR NOTE: {r['operator_note']}", f"OUTCOME: {r['outcome']}",
                                 f"STATION: {r['station']}", f"EQUIPMENT: {eq}", f"REASONING: {r['reasoning']}",
                                 f"GUIDE: {r['guide']}"])
            doc = dict(chunk=chunk, title=f"{r['status'].title()} action feedback - {r['action_text'][:80]}",
                       equipment_type=eq, location=r["station"], incident_date=r["created_at"],
                       report_date=r["created_at"], full_context=json.dumps(r, ensure_ascii=False, sort_keys=True),
                       cause=r["action_text"], conclusions=r["operator_note"] or r["outcome"],
                       recommendations=r["guide"], related_incidents=r["status"], **r)
        doc["chunk_id"] = _chunk_id(doc["title"], doc["chunk"])
        doc["parent_id"] = "report.pdf"
        doc["filename"] = "report.pdf"
        docs.append(doc)
    field_order = [f for f, _ in STANDARD_FIELDS + EXTRA_FIELDS[kind]]
    assert all(set(d) == set(field_order) for d in docs), index
    return report_title, [{f: d[f] for f in field_order} for d in docs]


RENDER_SKIP = {"chunk_id", "parent_id", "filename", "report_date", "incident_date", "creationDate",
               "full_context", "title", "chunk"}


def render_report(index: str, report_title: str, docs: list[dict]) -> bytes:
    blocks: list[tuple[str, str]] = [("title", report_title), ("p", INTRO), ("p", f"Report date: 2026-03-11"),
                                     ("gap", "")]
    for d in docs:
        blocks.append(("h", d["title"]))
        blocks.append(("p", d["chunk"]))
        shown = " ".join(d["chunk"].split())
        for k, v in d.items():
            if k in RENDER_SKIP or not isinstance(v, str) or not v:
                continue
            if " ".join(v.split()) not in shown:
                blocks.append(("p", f"{k.replace('_', ' ').capitalize()}: {v}"))
                shown += " " + " ".join(v.split())
        blocks.append(("gap", ""))
    return build_pdf(report_title, blocks)


# ── Assembly ─────────────────────────────────────────────────────────────
PATTERNS = {
    "fires": {
        "generator_degradation": "KESTREL.GEN.U2, 30-min bin 14:00: MVAR stdev > 5 and MW derate > 20%",
        "agc_removal_instability": "KESTREL: GEN AGC 14:10:00 + station MVAR stdev > 3 in 10-min bins",
        "unit_unplanned_offline": "KESTREL U1 drop 14:30 (330 -> 0 MW, 5 bins <= 5 MW) + CB/CB-CRIT, MWCC, KV-EMER-D",
        "synchronised_line_trip": "14:40 bucket: 4 .LINE. MW tags, 2 stations (cross-station), > 100 MW",
        "generator_motoring": "KESTREL.GEN.U2.MW 14:50 bin: -8, -12, -9 (severe)",
    },
    "negative": {
        "unit_unplanned_offline@MARLOW": "BESS1 passes the KQL drop/persistence stage at 14:40 but MARLOW has no "
                                         "SynchronousMachine -> inertia gate (>= 1.0 s) rejects it",
    },
    "cannot_fire_with_two_stations": {
        "regional_cascade": "emergency labels at 2 stations; needs >= 8 within 5 min (bypass 30)",
        "system_reactive_event": "SC VR EMER at 1 station (needs >= 3/30 min); UN-VR-CDGN at 1 (needs >= 5/60 min)",
        "coordinated_oscillation": "1 inertial station (KESTREL); needs >= 3 with 6 consecutive oscillating windows",
        "frequency_excursion": "situation needs the cross-station median outside 49.85-50.15 Hz for >= 2 five-min "
                               "bins: only 2 mainland stations vs 4 TAS, dip lasts < 1 bin; breadth 2 < 30. "
                               "freq_summary still shows a mainland normal-band breach (VIC, NSW).",
    },
}
TIMELINE = [
    ("14:05:00", "TAP_CHANGE noise at KESTREL.TRANS.T1"),
    ("14:08:00", "KESTREL U2 derate 300 -> 190 MW (to 14:12) and MVAR volatility (to 14:30)"),
    ("14:10:00", "GEN AGC on KESTREL.GEN.U2"),
    ("14:30:00", "KESTREL U1 trip 330 -> 0 MW; T1 MW/MVA -> 0; region tags VIC -330 MW, MAINLAND.INER -1800"),
    ("14:30:01", "1-s HZ/FREQ burst (ROCOF 0.13 Hz/s) at mainland tags"),
    ("14:30:02", "CB, CB-CRIT (+1 s) on KESTREL.CB.CB1; KV-EMER-D 14:30:05; UNREAS 14:30:10; MWCC 14:31:00"),
    ("14:30:15", "mainland HZ/FREQ at 49.62 Hz, recovering to 50.00 by 14:33:15; TAS unaffected"),
    ("14:38:00", "KM1 MVA +35% at both ends"),
    ("14:40:00", "KM1 trips (MW/MVAR/MVA/KV -> 0 both ends); MARLOW T1 and BESS1 -> 0 MW; CB KESTREL.CB.CB3, "
                 "MARLOW.CB.CB1"),
    ("14:40:15", "KM2 trips; MARLOW BUS2 KV -> 0; CB KESTREL.CB.CB4, MARLOW.CB.CB2; MARLOW.CB.CB3 14:40:17"),
    ("14:40:01", "BR-WARN, BR-EMER-D, KV-EMER-I, BR-EMER-I, BR-LDSH-I, INTER-LDSH, CNTR-EMER, HZ-EMER, "
                 "SC VR EMER, UN-VR-CDGN, UNDERVOLTAGE through 14:41:10"),
    ("14:52:00", "KESTREL U2 motoring: -8, -12, -9 MW"),
]
DEVIATIONS = [
    "Vector field follows tools (vector_field=...): snippet_vector for investigation-clues(+clean), paws, nearhit; "
    "text_vector for smirks and action-feedback.",
    "Line composites (KESTREL.LINE.KM*, MARLOW.LINE.KM*) are owned by the line's Terminal at each end; alarm mrid "
    "for a terminal-owned composite is the ACLineSegment CIMMRID.",
    "CLASS SVC added (MARLOW.SVC.SVC1 on StaticVarCompensator) for the SC VR EMER alarm.",
    "MARLOW.CB.CB3 also trips (14:40:17): cb_cluster counts CB alarms per station per 10-min window, so >= 3 CBs "
    "must be at one station; KESTREL/MARLOW line CBs alone give 2 per station.",
    "ROCOF > 0.1 Hz/s is not consumed by any tool query; realised with 1-s HZ/FREQ samples 14:30:01-05.",
    "Region/system tag measurement column = last TagId token (MW, CMW, RESV, INER).",
    "BESS1 GeneratingUnit carries a Terminal so equipment walks connect; no SynchronousMachine by design.",
    "ConnectivityNode containment uses edge ConnectivityNode.ConnectivityNodeContainer -> VoltageLevel; "
    "SynchronousMachine -> GeneratingUnit uses edge SynchronousMachine.GeneratingUnit.",
    "Bare PathName property added to equipment (breaker_neighbourhood reads values('PathName')).",
    "Incident PDFs carry /Info /Title and fixed /CreationDate (read by the incidents adapter).",
    "KESTREL.TRANS.T1 also trips with U1 (transformer_trip/transformer_mva_trip at KESTREL too); "
    "U2 motoring also fires gen_major_loss at 14:52.",
]


def generate(out: Path) -> dict:
    rng = random.Random(SEED)
    g = build_graph()
    files: dict[str, bytes] = {}
    scada = build_scada(rng)
    alarms = build_alarms(g)
    files["kql/schema.kql"] = SCHEMA_KQL.encode()
    files["kql/WatcherAlarmsAll.csv"] = csv_bytes(ALARM_COLS, alarms)
    files["kql/WatcherScadaAll.csv"] = csv_bytes(SCADA_COLS, scada)
    files["graph/vertices.jsonl"] = "".join(
        json.dumps(v, sort_keys=True) + "\n" for v in sorted(g.vertices.values(), key=lambda v: v["id"])).encode()
    files["graph/edges.jsonl"] = "".join(
        json.dumps(e, sort_keys=True) + "\n" for e in sorted(g.edges, key=lambda e: e["id"])).encode()
    doc_counts = {}
    for index in SEMANTIC:
        title, docs = build_documents(index)
        files[f"search/{index}/index.json"] = (json.dumps(index_definition(index), indent=2) + "\n").encode()
        files[f"search/{index}/documents.jsonl"] = "".join(json.dumps(d) + "\n" for d in docs).encode()
        files[f"search/{index}/report.pdf"] = render_report(index, title, docs)
        doc_counts[index] = len(docs)
    manifest = {
        "dataset": "gridiq-mockdata", "seed": SEED, "pk": PK,
        "window": {"start": ts(0), "end": ts(WINDOW_S), "cadence_s": STEP_S, "timezone": "AEST wall clock"},
        "files": {k: {"sha256": hashlib.sha256(v).hexdigest(), "bytes": len(v)} for k, v in sorted(files.items())},
        "counts": {"scada_rows": len(scada), "alarm_rows": len(alarms), "vertices": len(g.vertices),
                   "edges": len(g.edges), "search_documents": doc_counts,
                   "tags": len({r[1] for r in scada}), "stations": sorted({r[4] for r in scada})},
        "timeline": [{"time": f"2026-03-10T{t}", "event": e} for t, e in sorted(TIMELINE)],
        "patterns": PATTERNS, "design_deviations": DEVIATIONS,
    }
    files["manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    for rel, data in files.items():
        p = out / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    return manifest


def check(out: Path) -> int:
    with tempfile.TemporaryDirectory() as tmp:
        generate(Path(tmp))
        fresh = {p.relative_to(tmp).as_posix(): p.read_bytes() for p in Path(tmp).rglob("*") if p.is_file()}
    have = {p.relative_to(out).as_posix(): p.read_bytes() for p in out.rglob("*") if p.is_file()} if out.exists() else {}
    bad = sorted(k for k in set(fresh) | set(have) if fresh.get(k) != have.get(k))
    for k in bad:
        print(f"DIFF {k}")
    print(f"generate --check: {len(fresh)} files, {len(bad)} differ")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HERE / "out")
    ap.add_argument("--check", action="store_true", help="regenerate to a temp dir and compare with --out")
    a = ap.parse_args()
    if a.check:
        return check(a.out)
    m = generate(a.out)
    c = m["counts"]
    print(f"wrote {len(m['files']) + 1} files to {a.out}: scada={c['scada_rows']} alarms={c['alarm_rows']} "
          f"vertices={c['vertices']} edges={c['edges']} docs={sum(c['search_documents'].values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
