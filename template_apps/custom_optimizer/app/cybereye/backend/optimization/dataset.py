from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import threading
from pathlib import Path

from app.components.local_query import LocalQueryError, SQLiteReader
from template_foundations.situation_detector import normalize_window

GRADES = ("TruePositive", "BenignPositive", "FalsePositive")
FEATURES = ("event_time", "detector_id", "category", "mitre_techniques", "entity_type", "evidence_role")


class GuideDataset:
    def __init__(self, root: Path, contexts: Path, python_runner=None) -> None:
        self.root = root
        self.contexts = contexts
        self.python_runner = python_runner
        self.lock = threading.RLock()
        self.manifest = json.loads((root / "manifest.json").read_text())
        self.reader = SQLiteReader(root / "source.sqlite")
        with self.connect("source.sqlite") as connection:
            self.profile = connection.execute("SELECT * FROM training_profile").fetchall()
        self.profile_digest = hashlib.sha256(json.dumps(self.profile).encode()).hexdigest()

    def connect(self, name: str) -> sqlite3.Connection:
        return sqlite3.connect((self.root / name).resolve().as_uri() + "?mode=ro", uri=True)

    def describe(self) -> dict:
        with self.connect("source.sqlite") as connection:
            counts = dict(connection.execute("SELECT split,count(*) FROM cases GROUP BY split"))
            count = connection.execute("SELECT count(*) FROM evidence").fetchone()[0]
            lower, upper = connection.execute("SELECT min(start_time),max(end_time) FROM cases").fetchone()
        return {"dataset_id": self.manifest["dataset_id"],
                "counts": {"evidence": count, **counts}, "features": list(FEATURES),
                "labels": list(GRADES), "time_start": lower, "time_end": upper,
                "limitations": ["Anonymized alert-evidence incident grading, not raw-log detection or root-cause diagnosis.",
                    "First-appearance incident sampling is size-biased; results describe this frozen demonstration slice.",
                    "Training profiles use development labels only. Validation feedback is not an untouched final test.",
                    "Timestamp denotes source evidence time, not independently verified availability time.",
                    "Dataset license has not been independently verified; no redistribution is performed."]}

    def cases(self) -> list[dict]:
        with self.connect("source.sqlite") as connection:
            source = {row[0]: row[1:] for row in connection.execute(
                "SELECT case_id,start_time,end_time,evidence_count FROM cases")}
        result = []
        with self.connect("labels.sqlite") as connection:
            for split, limit in (("development", 3), ("validation", 5)):
                for grade in GRADES:
                    rows = connection.execute("SELECT case_id FROM labels WHERE split=? AND incident_grade=? ORDER BY case_id LIMIT ?",
                                              (split, grade, limit)).fetchall()
                    if len(rows) != limit:
                        raise ValueError("Not enough labeled incidents for the balanced demonstration battery")
                    for (case_id,) in rows:
                        lower, upper, count = source[case_id]
                        result.append({"case_id": case_id, "split": split, "expected": grade,
                                       "start_time": lower, "end_time": upper, "evidence_count": count})
        return result

    def context(self, case_id: str, window: dict | None = None) -> Path:
        if len(case_id) != 16 or any(character not in "0123456789abcdef" for character in case_id):
            raise ValueError("Invalid case id")
        directory = self.contexts / self.manifest["dataset_id"]
        target = directory / f"{case_id}.sqlite"
        bounds = normalize_window(window, 366 * 86400) if window else None
        if bounds:
            stamp = hashlib.sha256(json.dumps({key: value.isoformat() for key, value in bounds.items()}, sort_keys=True).encode()).hexdigest()[:16]
            target = directory / f"{case_id}-{stamp}.sqlite"
        with self.lock:
            if target.exists():
                return target
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self.connect("source.sqlite") as connection:
                predicate = " AND julianday(event_time) BETWEEN julianday(?) AND julianday(?)" if bounds else ""
                parameters = (case_id, bounds["start"].isoformat(), bounds["end"].isoformat()) if bounds else (case_id,)
                rows = connection.execute("SELECT event_time,detector_id,category,mitre_techniques,entity_type,evidence_role FROM evidence WHERE case_id=?" + predicate + " ORDER BY row_id",
                                          parameters).fetchall()
            if not rows and not bounds:
                raise ValueError("Case evidence not found")
            descriptor, name = tempfile.mkstemp(dir=directory, suffix=".sqlite")
            os.close(descriptor)
            temporary = Path(name)
            try:
                with sqlite3.connect(temporary) as connection:
                    connection.execute("CREATE TABLE evidence(event_time TEXT,detector_id TEXT,category TEXT,mitre_techniques TEXT,entity_type TEXT,evidence_role TEXT)")
                    connection.executemany("INSERT INTO evidence VALUES(?,?,?,?,?,?)", rows)
                    connection.execute("CREATE TABLE training_profile(feature TEXT,value TEXT,true_positive INTEGER,benign_positive INTEGER,false_positive INTEGER,support INTEGER)")
                    connection.executemany("INSERT INTO training_profile VALUES(?,?,?,?,?,?)", self.profile)
                    connection.execute("CREATE INDEX profile_lookup ON training_profile(feature,value)")
                os.replace(temporary, target)
                target.chmod(0o400)
            finally:
                temporary.unlink(missing_ok=True)
            return target

    def stress_cases(self, *, final: bool = False) -> list[dict]:
        with self.connect("source.sqlite") as connection:
            source = {row[0]: row[1:] for row in connection.execute(
                "SELECT case_id,start_time,end_time,evidence_count FROM cases")}
        result = []
        splits = (("final", 60),) if final else (("development", 30), ("validation", 90))
        with self.connect("labels.sqlite") as connection:
            for split, limit in splits:
                for grade in GRADES:
                    identifiers = [row[0] for row in connection.execute(
                        "SELECT case_id FROM labels WHERE split=? AND incident_grade=?", (split, grade))]
                    groups = {band: [] for band in ("sparse", "ordinary", "dense", "large")}
                    for case_id in identifiers:
                        count = source[case_id][2]
                        band = "sparse" if count <= 3 else "ordinary" if count <= 20 else "dense" if count <= 200 else "large"
                        groups[band].append(case_id)
                    for band, values in groups.items():
                        values.sort(key=lambda case_id: hashlib.sha256(f"guide-stress-v1:{case_id}".encode()).hexdigest())
                        if band == "large" and values:
                            largest = max(values, key=lambda case_id: source[case_id][2])
                            values.remove(largest)
                            values.insert(0, largest)
                    selected = []
                    while len(selected) < limit:
                        before = len(selected)
                        for band, values in groups.items():
                            if values and len(selected) < limit:
                                selected.append((values.pop(0), band))
                        if len(selected) == before:
                            raise ValueError("Not enough labeled incidents for the stress battery")
                    for case_id, band in selected:
                        lower, upper, count = source[case_id]
                        result.append({"case_id": case_id, "split": split, "expected": grade,
                                       "start_time": lower, "end_time": upper,
                                       "evidence_count": count, "evidence_band": band})
        return result

    def full_cases(self) -> list[dict]:
        with self.connect("source.sqlite") as connection:
            source = {row[0]: row[1:] for row in connection.execute(
                "SELECT case_id,start_time,end_time,evidence_count FROM cases")}
        with self.connect("labels.sqlite") as connection:
            labels = connection.execute(
                "SELECT case_id,split,incident_grade FROM labels ORDER BY split,case_id").fetchall()
        result = []
        for case_id, split, grade in labels:
            if split not in {"development", "validation", "final"} or grade not in GRADES:
                raise ValueError("Unexpected GUIDE split or incident grade")
            lower, upper, count = source[case_id]
            band = "sparse" if count <= 3 else "ordinary" if count <= 20 else "dense" if count <= 200 else "large"
            result.append({"case_id": case_id, "split": split, "expected": grade,
                           "stage": "training" if split == "development" else "evaluation",
                           "start_time": lower, "end_time": upper, "evidence_count": count, "evidence_band": band})
        if len({case["case_id"] for case in result}) != len(result):
            raise ValueError("GUIDE cases must be disjoint across splits")
        return result

    def query(self, case_id: str, sql: str) -> dict:
        if len(sql) > 12_000:
            raise ValueError("Tool SQL exceeds 12000 characters")
        result = SQLiteReader(self.context(case_id)).query(sql, max_rows=30, timeout_seconds=2,
                                                          tables={"evidence", "training_profile"})
        if len(json.dumps(result)) > 20_000:
            raise ValueError("Tool output exceeds the 20 KB case context budget")
        return result

    def preview(self) -> dict:
        return self.reader.query("SELECT event_time,detector_id,category,mitre_techniques,entity_type,evidence_role FROM evidence LIMIT 12",
                                 max_rows=12, tables={"evidence"})

    def run_tool(self, case_id: str, tool: dict, scope: dict | None = None) -> dict:
        if tool.get("language") == "python" or "code" in tool:
            if self.python_runner is None:
                raise ValueError("Python isolation unavailable; run ./deploy/deploy.sh optimization-setup")
            return self.python_runner.run(tool["code"], self.context(case_id, scope if scope and scope.get("windowed") else None), scope)
        return self.query(case_id, tool["sql"])

    def detector_query(self, case_id: str, rule: dict, window: dict) -> dict:
        bounds = normalize_window(window, 366 * 86400)
        try:
            result = SQLiteReader(self.context(case_id, window)).query(rule["query"],
                {**rule["parameters"], "window_start": bounds["start"].isoformat(), "window_end": bounds["end"].isoformat()},
                max_rows=rule["processing"].get("max_rows", 100), timeout_seconds=2, tables={"evidence", "training_profile"})
        except LocalQueryError as error:
            raise ValueError(str(error)) from error
        result["rows"] = [dict(zip(result["columns"], row)) for row in result["rows"]]
        if len(json.dumps(result)) > 20000:
            raise ValueError("Detector query output exceeds 20 KB")
        return result

    def detector_process(self, case_id: str, rule: dict, result: dict, window: dict) -> dict:
        if self.python_runner is None:
            raise ValueError("Python isolation unavailable")
        source = rule["processing"]["code"] + '\n\ndef run(ctx):\n    return process(ctx.scope["rows"], ctx.scope["parameters"])\n'
        scope = {"rows": result["rows"], "parameters": rule["parameters"], "truncated": result.get("truncated", False)}
        envelope = self.python_runner.run(source, self.context(case_id, window), scope)
        return envelope["data"]

    def profiles(self) -> dict:
        return self.reader.query("SELECT feature,value,true_positive,benign_positive,false_positive,support FROM training_profile ORDER BY support DESC LIMIT 30",
                                 max_rows=30, tables={"training_profile"})