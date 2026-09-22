"""F00-only immutable source recovery; no package, runtime or cloud mutation."""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
ROOTS = ["testbeds/foundry-hosted-agents", "testbeds/foundry-agent-evaluation",
         "testbeds/foundry-agent optimization", "libraries/framework-core",
         "libraries/llm-interface", "libraries/modular-agents"]
EXCLUDED = {"records", "evidence", "dataset", "agentcraft_projects", "__pycache__",
            ".git", "node_modules", "dist", "build", ".venv", ".pytest_cache"}
SUFFIXES = {".py", ".sh", ".md", ".json", ".yaml", ".yml", ".toml", ".txt", ".lock"}
SECRET = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
                    rb"(?:AccountKey|SharedAccessSignature)\s*=\s*[A-Za-z0-9+/]{20,}|"
                    rb"(?:ghp_|github_pat_|sk-proj-)[A-Za-z0-9_]{20,}|"
                    rb"[?&]sig=[A-Za-z0-9%+/]{20,}")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def pin(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.relative_to(ROOT)), "sha256": digest.hexdigest(),
            "bytes": path.stat().st_size}


def save(name, value):
    payload = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    if SECRET.search(payload):
        raise ValueError("credential-shaped evidence refused")
    path = OUT / name
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    if path.read_bytes() != payload:
        raise ValueError("evidence readback failed")
    return pin(path)


def selected():
    paths = []
    for root in ROOTS:
        for path in (ROOT / root).rglob("*"):
            relative = path.relative_to(ROOT / root)
            if any(part in EXCLUDED or part.endswith(".egg-info") for part in relative.parts):
                continue
            if path.is_file() and (path.suffix in SUFFIXES or path.name in {"Dockerfile", "LICENSE", "py.typed", ".dockerignore", ".gitignore"}):
                paths.append(path)
    paths.extend((ROOT / "specs").glob("20260922_FOUNDRY*.md"))
    paths.extend(path for path in (ROOT / "specs/20260922_FOUNDRY_HOSTED_AGENT_EVALUATION").rglob("*")
                 if path.is_file() and path.suffix in SUFFIXES and "__pycache__" not in path.parts)
    paths.extend([ROOT / "libraries/pyproject.toml", ROOT / "libraries/capabilities.json", ROOT / "docs/README.md"])
    lock = ROOT / "libraries/uv.lock"
    if lock.exists():
        paths.append(lock)
    for path in sorted(set(paths)):
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT):
            raise ValueError("unsafe source path: " + str(path))
        payload = path.read_bytes()
        payload.decode("utf-8")
        if SECRET.search(payload):
            raise ValueError("credential-shaped source refused: " + str(path.relative_to(ROOT)))
        yield path, payload


def verify(archive, entries, destination):
    expected = {entry["path"]: entry for entry in entries}
    with tarfile.open(archive, "r:gz") as bundle:
        members = bundle.getmembers()
        if len(members) != len(expected) or {member.name for member in members} != set(expected):
            raise ValueError("archive membership mismatch")
        for member in members:
            if not member.isfile() or member.name.startswith("/") or ".." in Path(member.name).parts:
                raise ValueError("unsafe archive member")
            payload = bundle.extractfile(member).read()
            if sha(payload) != expected[member.name]["sha256"]:
                raise ValueError("archive content mismatch")
            target = destination / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(payload)
            if sha(target.read_bytes()) != expected[member.name]["sha256"]:
                raise ValueError("recovery readback mismatch")
    return {"members": len(expected), "restored_bytes_verified": True}


def selftest():
    with tempfile.TemporaryDirectory(dir=OUT, prefix="selftest-") as directory:
        base = Path(directory)
        archive = base / "source.tar.gz"
        payload = b"dirty and untracked source\n"
        entry = {"path": "source.py", "sha256": sha(payload)}
        with tarfile.open(archive, "w:gz") as bundle:
            member = tarfile.TarInfo(entry["path"])
            member.size = len(payload)
            bundle.addfile(member, io.BytesIO(payload))
        verify(archive, [entry], base / "valid")
        try:
            verify(archive, [{**entry, "sha256": "0" * 64}], base / "invalid")
        except ValueError:
            pass
        else:
            raise AssertionError("tamper accepted")
        assert SECRET.search(b"AccountKey=" + b"A" * 30)
    print(json.dumps({"recovery": "passed", "tamper_refusal": "passed", "secret_refusal": "passed"}))


def capture():
    started = time.monotonic()
    entries = []
    archive = OUT / "source.tar.gz"
    with archive.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz") as bundle:
        for path, payload in selected():
            relative = str(path.relative_to(ROOT))
            member = tarfile.TarInfo(relative)
            member.size = len(payload)
            member.mode = path.stat().st_mode & 0o777
            bundle.addfile(member, io.BytesIO(payload))
            entries.append({"path": relative, "sha256": sha(payload), "bytes": len(payload), "mode": member.mode})
    recovery = verify(archive, entries, OUT / "recovery")
    historical = []
    for root in ROOTS[:3]:
        for path in (ROOT / root).rglob("*"):
            if path.is_file() and not path.is_symlink() and any(part in {"records", "evidence", "dataset", "agentcraft_projects"} for part in path.relative_to(ROOT / root).parts):
                historical.append(pin(path))
    git = {}
    for name, arguments in {
        "status": ["status", "--short", "--untracked-files=all", "--ignored", "--", *ROOTS],
        "diff": ["diff", "--binary", "--", *[entry["path"] for entry in entries]],
        "staged_diff": ["diff", "--cached", "--binary", "--", *[entry["path"] for entry in entries]],
        "head": ["rev-parse", "HEAD"],
    }.items():
        result = subprocess.run(["git", *arguments], cwd=ROOT, capture_output=True, text=True, timeout=60)
        git[name] = {"exit_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
    result = {"utc": datetime.now(timezone.utc).isoformat(), "archive": pin(archive), "source": entries,
              "historical_hash_only": historical, "recovery": recovery, "git": git,
              "seconds": time.monotonic() - started, "scope": ROOTS,
              "excluded": sorted(EXCLUDED), "secret_scan": "allowlisted UTF-8 source; pattern backstop passed; not a universal secret detector",
              "historical_payloads": "stream-hashed only; no holdout payload parsed, displayed or archived",
              "live_restore": "not_performed", "authority": "worker primary evidence; not authoritative publication"}
    print(json.dumps(save("capture.json", result)))


def settle():
    started = time.monotonic()
    captured = json.loads((OUT / "capture.json").read_text())
    by_path = {item["path"]: item for item in captured["source"]}
    current = {str(path.relative_to(ROOT)): sha(payload) for path, payload in selected()}
    if set(current) != set(by_path):
        raise ValueError("source membership changed")
    with tarfile.open(OUT / "source.tar.gz") as bundle:
        if set(bundle.getnames()) != set(by_path):
            raise ValueError("archive member drift")
        for name, entry in by_path.items():
            if current[name] != entry["sha256"]:
                raise ValueError("active source drift: " + name)
            if sha((OUT / "recovery" / name).read_bytes()) != entry["sha256"]:
                raise ValueError("isolated recovery drift: " + name)
            if sha(bundle.extractfile(name).read()) != entry["sha256"]:
                raise ValueError("archive content drift: " + name)
    for entry in captured["historical_hash_only"]:
        if pin(ROOT / entry["path"])["sha256"] != entry["sha256"]:
            raise ValueError("historical drift: " + entry["path"])
    inventory = subprocess.run(["git", "ls-files", "-z", "--", *by_path], cwd=ROOT,
                               capture_output=True, check=True, timeout=60)
    tracked = set(inventory.stdout.decode().split("\0")) - {""}
    unselected = []
    for root in ROOTS:
        for path in (ROOT / root).rglob("*"):
            relative = path.relative_to(ROOT / root)
            if path.is_file() and not any(part in EXCLUDED or part.endswith(".egg-info") for part in relative.parts) and str(path.relative_to(ROOT)) not in by_path:
                unselected.append(str(path.relative_to(ROOT)))
    artifacts = [pin(path) for path in sorted(OUT.iterdir()) if path.is_file() and path.name != "settlement.json"]
    value = {"utc": datetime.now(timezone.utc).isoformat(), "status": "complete",
             "source_files_verified": len(by_path), "historical_files_verified": len(captured["historical_hash_only"]),
             "tracked_source_files": len(tracked), "untracked_or_ignored_source_files": len(by_path) - len(tracked),
             "unselected_nonexcluded_paths": unselected,
             "source_archive": pin(OUT / "source.tar.gz"), "artifacts": artifacts,
             "seconds": time.monotonic() - started, "live_restore": "not_performed",
             "workers": 0, "new_cloud_mutations": 0, "new_model_requests": 0,
             "authoritative_publication": "not_performed; overseer checkpoint required",
             "tool_capture": "Per-command receipts plus current host tool history; private host logs not copied"}
    print(json.dumps(save("settlement.json", value)))


def build_manifests():
    entries = []
    archive = OUT / "build-manifests.tar.gz"
    names = ("libraries/llm-interface/MANIFEST.in", "libraries/modular-agents/MANIFEST.in")
    with archive.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz") as bundle:
        for name in names:
            path = ROOT / name
            payload = path.read_bytes()
            if path.is_symlink() or SECRET.search(payload):
                raise ValueError("unsafe build manifest")
            member = tarfile.TarInfo(name)
            member.size = len(payload)
            bundle.addfile(member, io.BytesIO(payload))
            entries.append(pin(path))
    recovery = verify(archive, entries, OUT / "recovery-build-manifests")
    receipt = {"utc": datetime.now(timezone.utc).isoformat(), "status": "complete", "source": entries,
               "archive": pin(archive), "recovery": recovery, "capture_code": pin(Path(__file__)),
               "prior_settlement": pin(OUT / "settlement.json"), "handoff": pin(OUT / "handoff.json"),
               "source_files_total": len(json.loads((OUT / "capture.json").read_text())["source"]) + len(entries),
               "scope_note": "Supplement preserves canonical Python build manifests. Existing H/O container allowlists use 51 library members already verified; broader modular-agents sdist graft/frontend/provenance is not this accepted container build context. No active H/E/O source omitted.",
               "publication": "Use original settlement plus this addendum; original archive and receipts remain unchanged"}
    print(json.dumps(save("build-manifests.json", receipt)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("selftest", "capture", "settle", "build-manifests"))
    args = parser.parse_args()
    {"selftest": selftest, "capture": capture, "settle": settle, "build-manifests": build_manifests}[args.action]()