"""F00 source recovery only; no imports of application code or cloud operations."""

import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
ROOTS = (
    "testbeds/foundry-hosted-agents",
    "testbeds/foundry-agent-evaluation",
    "testbeds/foundry-agent optimization",
    "libraries/framework-core",
    "libraries/llm-interface",
    "libraries/modular-agents",
    "specs/20260922_FOUNDRY_HOSTED_AGENT_EVALUATION/deploy",
)
EXCLUDED = {"records", "evidence", "dataset", "agentcraft_projects", "__pycache__",
            ".git", "node_modules", ".venv", "dist", "build", ".pytest_cache"}
SUFFIXES = {".py", ".sh", ".toml", ".md", ".yaml", ".yml", ".json", ".txt", ".lock"}
NAMES = {"Dockerfile", "LICENSE", ".gitignore", ".dockerignore", "py.typed"}
SECRET = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|"
                    rb"(?:AccountKey|SharedAccessSignature)\s*=\s*[^\s;]{12,}|"
                    rb"[?&]sig=[A-Za-z0-9%+/=]{16,}|"
                    rb"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})")


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def safe(path, payload):
    if path.is_symlink() or not path.resolve().is_relative_to(REPO):
        raise ValueError("unsafe source path: " + str(path))
    if SECRET.search(payload):
        raise ValueError("secret-shaped source refused: " + str(path))
    payload.decode("utf-8")


def save(name, payload):
    with (OUT / name).open("xb") as stream:
        stream.write(payload)
    if (OUT / name).read_bytes() != payload:
        raise RuntimeError("capture readback mismatch")


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()


def sources():
    paths = set()
    for root in ROOTS:
        for path in (REPO / root).rglob("*"):
            relative = path.relative_to(REPO / root)
            if not path.is_file() or any(part in EXCLUDED or part.endswith(".egg-info") for part in relative.parts):
                continue
            if path.suffix in SUFFIXES or path.name in NAMES:
                paths.add(path)
    paths.update((REPO / "specs").glob("20260922_FOUNDRY_*.md"))
    paths.update(REPO / name for name in ("libraries/pyproject.toml", "libraries/capabilities.json", "docs/README.md"))
    return sorted(paths)


def history():
    result = []
    for root in ROOTS[:3]:
        for directory in ("deploy/records", "deploy/evidence", "agentcraft_projects"):
            for path in sorted((REPO / root / directory).rglob("*")):
                if path.is_file() and not path.is_symlink() and "__pycache__" not in path.parts:
                    result.append({"path": str(path.relative_to(REPO)), "bytes": path.stat().st_size,
                                   "sha256": sha(path.read_bytes()), "content_inspected": False})
    return result


def verify():
    manifest = json.loads((OUT / "source-manifest.json").read_text())
    with tarfile.open(OUT / "source-recovery.tar.gz") as archive:
        if sorted(archive.getnames()) != sorted(item["path"] for item in manifest):
            raise RuntimeError("archive membership mismatch")
        for item in manifest:
            member = archive.getmember(item["path"])
            if not member.isfile() or sha(archive.extractfile(member).read()) != item["sha256"]:
                raise RuntimeError("archive content mismatch")
            if sha((REPO / item["path"]).read_bytes()) != item["sha256"]:
                raise RuntimeError("source drift: " + item["path"])
    original = json.loads((OUT / "historical-hashes.json").read_text())
    for item in original:
        if sha((REPO / item["path"]).read_bytes()) != item["sha256"]:
            raise RuntimeError("historical evidence drift: " + item["path"])
    return {"source_files_verified": len(manifest), "historical_files_verified": len(original),
            "archive_sha256": sha((OUT / "source-recovery.tar.gz").read_bytes()),
            "verification": "all archive members read back and matched original files; no restore into active tree"}


def capture():
    selected = []
    payloads = {}
    for path in sources():
        payload = path.read_bytes()
        safe(path, payload)
        name = str(path.relative_to(REPO))
        payloads[name] = payload
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", "--", name], cwd=REPO,
                                 capture_output=True).returncode == 0
        selected.append({"path": name, "sha256": sha(payload), "bytes": len(payload),
                         "mode": path.stat().st_mode & 0o777, "tracked": tracked})
    names = list(payloads)
    for label, args in (("dirty.patch", []), ("staged.patch", ["--cached"])):
        diff = subprocess.run(["git", "diff", "--binary", *args, "--", *names], cwd=REPO,
                              capture_output=True, check=True).stdout
        safe(OUT / label, diff)
        save(label, diff)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for item in selected:
            member = tarfile.TarInfo(item["path"])
            member.size = item["bytes"]
            member.mode = item["mode"]
            archive.addfile(member, io.BytesIO(payloads[item["path"]]))
    save("source-recovery.tar.gz", buffer.getvalue())
    save("source-manifest.json", encoded(selected))
    save("historical-hashes.json", encoded(history()))
    receipt = {"observed_at": datetime.now(timezone.utc).isoformat(), **verify(),
               "scope": ROOTS, "excluded_directories": sorted(EXCLUDED),
               "secret_check": "allowlisted UTF-8 sources; private-key/token/SAS detectors; not a universal secret detector",
               "authority": "F00 primary worker evidence only; no authoritative publication"}
    save("capture-receipt.json", encoded(receipt))
    print(json.dumps(receipt))


def self_test():
    safe(OUT / "fixture.py", b"value = 1\n")
    try:
        safe(OUT / "fixture.py", b"-----BEGIN PRIVATE KEY-----")
    except ValueError:
        pass
    else:
        raise AssertionError("secret refusal failed")
    assert not any(any(part in EXCLUDED for part in path.relative_to(REPO).parts) for path in sources())
    print("capture self-test passed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("self-test", "capture", "verify"))
    action = parser.parse_args().action
    if action == "self-test":
        self_test()
    elif action == "capture":
        capture()
    else:
        print(json.dumps(verify()))