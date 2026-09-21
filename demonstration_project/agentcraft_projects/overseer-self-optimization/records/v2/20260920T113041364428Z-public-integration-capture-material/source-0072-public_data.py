"""Local public-source acquisition and packaging; no Azure or model operations."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import time
from urllib.parse import unquote, urlparse
import uuid
import zipfile


APP = Path(__file__).resolve().parents[1]
DATA = APP / "deploy/data/public-investigation"
LOCK = APP / "deploy/public_sources.lock.json"
REPOSITORIES = ("splunk/attack_data", "mitre-attack/attack-stix-data")


def sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, indent=2, sort_keys=True, ensure_ascii=True) + "\n").encode()


def safe_path(root: Path, name: str) -> Path:
    relative = PurePosixPath(name)
    if (not name or not relative.parts or relative.is_absolute() or ".." in relative.parts or "\\" in name
            or ":" in name or any(ord(char) < 32 for char in name)):
        raise ValueError("unsafe path")
    target = root / name
    if any(parent.is_symlink() for parent in (target, *target.parents)):
        raise ValueError("symlink refused")
    if not target.resolve().is_relative_to(root.resolve()):
        raise ValueError("path escape")
    return target


def retain(path: Path, payload: bytes) -> None:
    safe_path(path.parent, path.name)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable output differs: {path}")
        return
    with path.open("xb") as handle:
        handle.write(payload)
    if path.read_bytes() != payload:
        raise ValueError("read-back mismatch")


def source_url(url: str) -> None:
    parsed = urlparse(url)
    decoded = unquote(parsed.path)
    if ".." in PurePosixPath(decoded).parts or "\\" in decoded:
        raise ValueError("source path traversal refused")
    tree_query = parsed.netloc == "api.github.com" and "/git/trees/" in parsed.path and parsed.query == "recursive=1"
    if parsed.scheme != "https" or parsed.username or parsed.password or (parsed.query and not tree_query) or parsed.fragment:
        raise ValueError("source URL refused")
    prefix = {"api.github.com": "/repos/", "media.githubusercontent.com": "/media/"}.get(parsed.netloc, "/")
    if parsed.netloc not in {"api.github.com", "raw.githubusercontent.com", "media.githubusercontent.com"}:
        raise ValueError("source host refused")
    if not any(parsed.path.startswith(prefix + repo + "/") for repo in REPOSITORIES):
        raise ValueError("source repository refused")


def acquire(url: str, name: str, *, maximum: int, expected: str | None = None) -> dict:
    source_url(url)
    if not 1 <= maximum <= 100 * 1024 * 1024:
        raise ValueError("invalid byte limit")
    target = safe_path(DATA, name)
    receipt_path = safe_path(DATA, name + ".provenance.json")
    if target.exists():
        if target.stat().st_size > maximum:
            raise ValueError("cached source size limit exceeded")
        receipt = json.loads(receipt_path.read_text())
        payload = target.read_bytes()
        if (receipt["source_url"] != url or receipt["sha256"] != sha256(payload)
                or len(payload) > maximum or (expected and sha256(payload) != expected)):
            raise ValueError("cached source integrity mismatch")
        return {**receipt, "cache": "verified-skip"}
    from webres import Provenance, open_public

    with open_public(url, timeout=120, deadline=time.monotonic() + 180) as response:
        if response.status != 200:
            raise ValueError("source HTTP status refused")
        payload = response.read(maximum + 1)
        if len(payload) > maximum:
            raise ValueError("source size limit exceeded")
        if expected and sha256(payload) != expected:
            raise ValueError("source digest mismatch")
        receipt = Provenance(source_url=url, retrieved_at=datetime.now(timezone.utc).isoformat(),
                             status=response.status, content_type=response.headers.get("Content-Type", ""),
                             sha256=sha256(payload), bytes=len(payload), artefact=name,
                             publisher=urlparse(url).netloc, function="public-investigation-acquire").to_dict()
    retain(target, payload)
    retain(receipt_path, encoded(receipt))
    return {**receipt, "cache": "downloaded"}


def archive_members(payload: bytes, *, max_members: int = 32,
                    max_bytes: int = 64 * 1024 * 1024) -> dict[str, bytes]:
    if not 1 <= max_members <= 1000 or not 1 <= max_bytes <= 100 * 1024 * 1024:
        raise ValueError("invalid archive limits")
    output = {}
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        members = archive.infolist()
        if len(members) > max_members:
            raise ValueError("archive member limit")
        total = 0
        for member in members:
            safe_path(Path("/unused-public-archive"), member.filename)
            mode = member.external_attr >> 16
            if member.is_dir() or stat.S_ISLNK(mode) or member.flag_bits & 1:
                raise ValueError("archive special/encrypted member refused")
            if PurePosixPath(member.filename).suffix.lower() not in {".json", ".xml", ".log", ".txt", ".csv"}:
                raise ValueError("archive content type refused")
            total += member.file_size
            if total > max_bytes or member.file_size > max(1, member.compress_size) * 200:
                raise ValueError("archive expansion limit")
            if member.filename in output:
                raise ValueError("duplicate archive member")
            with archive.open(member) as handle:
                content = handle.read(max_bytes + 1)
            if len(content) != member.file_size:
                raise ValueError("archive member size mismatch")
            output[member.filename] = content
    return output


def rights(source: dict) -> None:
    if source.get("license") not in {"Apache-2.0", "MITRE-ATTACK-2025"} or source.get("rights_review") != "approved-path-review":
        raise ValueError("source rights unresolved")
    if not re.fullmatch(r"[0-9a-f]{64}", source.get("license_sha256", "")) or not re.fullmatch(r"[0-9a-f]{40}", source.get("commit", "")):
        raise ValueError("source rights/revision pin missing")


def load_lock() -> dict:
    lock = json.loads(LOCK.read_text())
    if lock.get("schema_version") != 1 or len(lock.get("sources", [])) != 2:
        raise ValueError("unsupported source lock")
    names = set()
    for source in lock["sources"]:
        rights(source)
        licenses = [item for item in source["files"] if item["purpose"] == "license"]
        if len(licenses) != 1 or licenses[0]["sha256"] != source["license_sha256"]:
            raise ValueError("license pin mismatch")
        for item in source["files"]:
            source_url(item["url"])
            safe_path(DATA, item["name"])
            if item["name"] in names or source["commit"] not in urlparse(item["url"]).path.split("/"):
                raise ValueError("duplicate file or unpinned source")
            if not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]) or not 1 <= item["bytes"] <= 100 * 1024 * 1024:
                raise ValueError("invalid file pin")
            names.add(item["name"])
    return lock


def verify_sources(lock: dict) -> dict:
    results = []
    for source in lock["sources"]:
        rights(source)
        for item in source["files"]:
            path = safe_path(DATA, item["name"])
            if path.stat().st_size != item["bytes"]:
                raise ValueError("locked size mismatch")
            payload = path.read_bytes()
            receipt = json.loads(safe_path(DATA, item["name"] + ".provenance.json").read_text())
            if sha256(payload) != item["sha256"] or receipt["sha256"] != item["sha256"] or receipt["source_url"] != item["url"]:
                raise ValueError("locked source/provenance mismatch")
            results.append({"name": item["name"], "sha256": item["sha256"], "bytes": len(payload)})
        if source.get("review_tree"):
            tree = json.loads(safe_path(DATA, source["review_tree"]).read_text())
            if tree.get("truncated") is not False:
                raise ValueError("incomplete rights tree")
            entries = {item["path"]: item for item in tree["tree"]}
            ancestors = PurePosixPath(source["source_path"]).parents
            overrides = [name for name in entries if PurePosixPath(name).parent in ancestors
                         and any(word in PurePosixPath(name).name.casefold() for word in ("license", "notice", "copying"))
                         and name != "LICENSE"]
            if overrides:
                raise ValueError("unreviewed nested rights: " + repr(overrides))
            for item in source["files"]:
                if item.get("path"):
                    payload = safe_path(DATA, item["name"]).read_bytes()
                    blob = hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()
                    if entries[item["path"]]["sha"] != blob:
                        raise ValueError("source tree membership mismatch")
            pointer = safe_path(DATA, "splunk/payload.lfs").read_text()
            telemetry = next(item for item in source["files"] if item["purpose"] == "telemetry")
            if f"oid sha256:{telemetry['sha256']}\nsize {telemetry['bytes']}" not in pointer:
                raise ValueError("LFS membership mismatch")
    return {"files": results, "network": "not used"}


def project_mitre(payload: bytes, source: dict, receipt: dict) -> tuple[list[dict], dict]:
    key_path = APP / "app/cybereye/backend/knowledge/keys.py"
    spec = importlib.util.spec_from_file_location("investigation_knowledge_keys", key_path)
    keys = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(keys)
    safe_key = keys.safe_key

    bundle = json.loads(payload)
    source_digest = sha256(payload)
    if bundle.get("type") != "bundle":
        raise ValueError("not a STIX bundle")
    objects = bundle["objects"]
    by_id = {item["id"]: item for item in objects}
    if len(by_id) != len(objects) or any(item.get("spec_version") != "2.1" for item in objects):
        raise ValueError("duplicate STIX identity or unsupported version")
    active = {identity: item for identity, item in by_id.items()
              if not item.get("revoked") and not item.get("x_mitre_deprecated")}

    def reference(item):
        references = [ref for ref in item.get("external_references", []) if ref.get("source_name") == "mitre-attack" and ref.get("external_id")]
        if len(references) != 1:
            raise ValueError("ambiguous official MITRE reference")
        return references[0]

    technique_map = defaultdict(set)
    skipped_relations = 0
    for relation in active.values():
        if relation["type"] != "relationship" or relation.get("relationship_type") != "detects":
            continue
        start = active.get(relation["source_ref"])
        target = active.get(relation["target_ref"])
        if not start or not target:
            skipped_relations += 1
            continue
        if start["type"] == "x-mitre-detection-strategy" and target["type"] == "attack-pattern":
            technique_map[start["id"]].add(reference(target)["external_id"])
    for item in active.values():
        if item["type"] == "x-mitre-detection-strategy":
            for analytic_id in item.get("x_mitre_analytic_refs", []):
                if analytic_id not in active:
                    skipped_relations += 1
                    continue
                if active[analytic_id]["type"] != "x-mitre-analytic":
                    raise ValueError("invalid analytic relationship")
                technique_map[analytic_id].update(technique_map[item["id"]])
    types = {"attack-pattern": ("situation_type", "technique"), "x-mitre-tactic": ("situation_type", "tactic"),
             "x-mitre-analytic": ("analytic", "analytic"), "x-mitre-detection-strategy": ("analytic", "detection_strategy")}
    documents = []
    for native_id, item in sorted(active.items()):
        if item["type"] not in types:
            continue
        ref = reference(item)
        kind, doc_type = types[item["type"]]
        doc_id = ref["external_id"]
        if not ref.get("url", "").startswith("https://attack.mitre.org/"):
            raise ValueError("nonofficial ATT&CK URL")
        techniques = [doc_id] if doc_type == "technique" else sorted(technique_map[native_id])
        description = item.get("description", "")
        document = {"id": safe_key(f"{kind}:{doc_id}"), "doc_kind": kind, "doc_id": doc_id,
                    "source": "mitre-attack", "doc_type": doc_type, "title": item["name"], "family": item["type"],
                    "definition": description, "summary": "", "body": description, "symptoms": [],
                    "keywords": [], "log_sources": [entry["name"] for entry in item.get("x_mitre_log_source_references", [])],
                    "platforms": item.get("x_mitre_platforms", []), "technique_ids": techniques,
                    "behaviour_class": [phase["phase_name"] for phase in item.get("kill_chain_phases", [])],
                    "maturity": "", "native_id": native_id, "attack_url": ref["url"],
                    "path": source["source_path"], "commit": source["commit"], "license": source["license"],
                    "retrieved_at": receipt["retrieved_at"], "release": source["release"],
                    "source_sha256": source_digest, "license_sha256": source["license_sha256"],
                    "modified": item["modified"], "advisory_only": True,
                    "content": item["name"] + "\n" + description}
        documents.append(document)
    if len({document["id"] for document in documents}) != len(documents):
        raise ValueError("Search key collision")
    return documents, {"bundle_id": bundle["id"], "objects": len(objects),
                       "objects_by_type": dict(Counter(item["type"] for item in objects)),
                       "documents": len(documents), "documents_by_type": dict(Counter(item["doc_type"] for item in documents)),
                       "excluded_revoked_or_deprecated": len(objects) - len(active),
                       "unresolved_inactive_detection_relations": skipped_relations,
                       "relationship_projection": "active detects links plus explicit strategy analytic refs; other STIX relationships not projected"}


def normalize(lock: dict) -> dict:
    from app.data.ontology import normalize_windows, validate_package

    verify_sources(lock)
    telemetry_source, knowledge_source = lock["sources"]
    telemetry_file = next(item for item in telemetry_source["files"] if item["purpose"] == "telemetry")
    knowledge_file = next(item for item in knowledge_source["files"] if item["purpose"] == "knowledge")
    payload = safe_path(DATA, telemetry_file["name"]).read_bytes()
    package = normalize_windows(payload, telemetry_source)
    knowledge, knowledge_report = project_mitre(safe_path(DATA, knowledge_file["name"]).read_bytes(), knowledge_source,
                                               json.loads(safe_path(DATA, knowledge_file["name"] + ".provenance.json").read_text()))
    knowledge_keys = {f"{item['doc_kind']}:{item['doc_id']}" for item in knowledge}
    for document in package["cosmos"]:
        if not set(document.get("knowledge_refs", [])).issubset(knowledge_keys):
            raise ValueError("missing advisory knowledge reference")
        if document["kind"] == "event":
            ref = document["source"]
            original = payload[ref["byte_offset"]:ref["byte_offset"] + ref["byte_length"]]
            if sha256(original) != ref["raw_sha256"]:
                raise ValueError("raw record read-back failed")
    validate_package(package)
    artifacts = {"cosmos.json": encoded(package["cosmos"]), "gremlin.json": encoded(package["gremlin"]),
                 "search.json": encoded(knowledge)}
    for source in lock["sources"]:
        for item in source["files"]:
            if item["purpose"] in {"license", "notice", "scenario"}:
                artifacts["notices/" + item["name"]] = safe_path(DATA, item["name"]).read_bytes()
    events = [item for item in package["cosmos"] if item["kind"] == "event"]
    transform_paths = [Path(__file__), APP / "app/data/ontology/public_windows.py", APP / "app/data/ontology/model.py",
                       APP / "app/cybereye/backend/knowledge/keys.py"]
    manifest = {"schema_version": 1, "series_id": lock["series_id"], "status": "local-package-not-deployed",
                "source_lock_sha256": sha256(LOCK.read_bytes()), "partition": package["partition"],
                "acquisition_receipts": {item["name"]: sha256(safe_path(DATA, item["name"] + ".provenance.json").read_bytes())
                                         for source in lock["sources"] for item in source["files"]},
                "source": package["source"], "knowledge": knowledge_report,
                "knowledge_source": {"commit": knowledge_source["commit"], "sha256": knowledge_file["sha256"]},
                "transforms": {str(path.relative_to(APP)): sha256(path.read_bytes()) for path in transform_paths},
                "artifacts": {name: {"sha256": sha256(content), "bytes": len(content)} for name, content in artifacts.items()},
                "counts": {"cosmos_documents": len(package["cosmos"]), "vertices": len(package["gremlin"]["vertices"]),
                           "edges": len(package["gremlin"]["edges"]), **package["observations"]},
                "example": {"incident_id": package["cosmos"][0]["id"],
                            "alarm_ids": package["cosmos"][0]["alarm_refs"], "events": events},
                "limitations": ["No cloud writes, UI integration, model calls or comparative acceptance.",
                                "Graph is a logical vertex/edge load package; Gremlin writer and property encoding remain future work.",
                                "Selected export has no original alarm or per-event malicious labels; all cases and alarms are explicit derivatives.",
                                "MITRE knowledge advisory only; no linked external reports fetched."]}
    manifest_bytes = encoded(manifest)
    package_digest = sha256(manifest_bytes)
    directory = safe_path(DATA, "packages/" + package_digest)
    for name, content in artifacts.items():
        retain(safe_path(directory, name), content)
    retain(directory / "manifest.json", manifest_bytes)
    example = {"incident_id": manifest["example"]["incident_id"], "alarm_ids": manifest["example"]["alarm_ids"],
               "events": [{"resource_id": event["resource_id"], "event_record_id": event["event_record_id"],
                           "timestamp": event["timestamp"], "source": event["source"], "entity_refs": event["entity_refs"],
                           "host": event["host"], "user": event["fields"].get("User"),
                           "process_guid": event["fields"].get("ProcessGuid"),
                           "parent_process_guid": event["fields"].get("ParentProcessGuid")} for event in events]}
    return {"package_path": str(directory), "package_sha256": package_digest,
            "counts": manifest["counts"], "knowledge": knowledge_report, "artifacts": manifest["artifacts"],
            "source_lock_sha256": manifest["source_lock_sha256"], "example": example}


def checks() -> list[dict]:
    workspace = APP.parents[1]
    commands = [([sys.executable, "-B", "-m", "unittest", "discover", "-s", "deploy/tests", "-p", "test_public_data.py", "-v"], workspace),
                ([sys.executable, "-B", "-m", "unittest", "app.cybereye.tests.test_public_attack_data", "-v"], APP),
                (["bash", "-n", str(workspace / "deploy/deploy.sh")], workspace),
                (["bash", "-n", str(APP / "deploy/deploy.sh")], workspace)]
    outcomes = []
    for command, directory in commands:
        started = datetime.now(timezone.utc).isoformat()
        clock = time.monotonic()
        completed = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=60)
        outcomes.append({"command": command, "cwd": str(directory), "started_at": started,
                         "duration_seconds": time.monotonic() - clock, "exit_code": completed.returncode,
                         "stdout": completed.stdout, "stderr": completed.stderr})
    return outcomes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    commands = parser.add_subparsers(dest="action", required=True)
    inspect = commands.add_parser("inspect", help="Acquire bounded source metadata or reviewed inputs")
    inspect.add_argument("--url", required=True)
    inspect.add_argument("--name", required=True)
    inspect.add_argument("--max-bytes", type=int, default=8 * 1024 * 1024)
    inspect.add_argument("--sha256")
    commands.add_parser("acquire", help="Acquire or verify-skip every exactly pinned input")
    commands.add_parser("verify", help="Offline source, rights and revision verification")
    commands.add_parser("normalize", help="Build and read back a deterministic local three-store package")
    commands.add_parser("checks", help="Run bounded offline tests and retain command-level timings")
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    result = {"argv": sys.argv, "started_at": started.isoformat(), "action": args.action}
    code = 0
    try:
        if args.action == "inspect":
            parsed = urlparse(args.url)
            metadata = parsed.netloc == "api.github.com" or PurePosixPath(parsed.path).name.lower() in {"license", "license.txt", "notice", "readme.md"} or parsed.path.endswith((".yml", ".yaml"))
            if not metadata and not (parsed.netloc == "raw.githubusercontent.com" and args.max_bytes <= 1024):
                raise ValueError("payload acquisition requires reviewed source lock; use acquire")
            result["output"] = acquire(args.url, args.name, maximum=args.max_bytes, expected=args.sha256)
        elif args.action == "checks":
            result["output"] = checks()
            code = int(any(item["exit_code"] for item in result["output"]))
        else:
            lock = load_lock()
            if args.action == "acquire":
                result["output"] = [acquire(item["url"], item["name"], maximum=item["bytes"], expected=item["sha256"])
                                    for source in lock["sources"] for item in source["files"]]
                verify_sources(lock)
            elif args.action == "verify":
                result["output"] = verify_sources(lock)
            else:
                result["output"] = normalize(lock)
        result["status"] = "failed" if code else "complete"
    except Exception as exc:
        result.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        code = 1
    result.update(finished_at=datetime.now(timezone.utc).isoformat(), duration_seconds=time.monotonic() - clock)
    name = started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:8] + ".json"
    retain(args.evidence / name, encoded(result))
    print(json.dumps(result, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())