"""Verify F01 settlement and create unpublished checkpoint input plus recovery."""

from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
from pathlib import Path
import re
import tarfile

from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

from run import ROOT, OUT, clock

F00 = ROOT / "deploy/remediation-evidence/20260922T151500Z-f00"
OWNERS = [ROOT / "testbeds" / name for name in ("foundry-hosted-agents", "foundry-agent-evaluation", "foundry-agent optimization")]
EXCLUDED = {"records", "evidence", "dataset", "agentcraft_projects", "__pycache__", "build", ".pytest_cache"}


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def pin(path):
    return {"path": str(path.relative_to(ROOT)), "sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}


def save(name, value):
    path = OUT / name
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x") as stream:
        stream.write(payload)
    assert path.read_text() == payload
    return pin(path)


def main():
    timing = clock()
    before = json.loads((F00 / "capture.json").read_text())
    for entry in before["historical_hash_only"]:
        if pin(ROOT / entry["path"])["sha256"] != entry["sha256"]:
            raise ValueError("historical drift: " + entry["path"])
    platforms = [f"manylinux_2_{minor}_x86_64" for minor in range(36, 4, -1)] + ["manylinux2014_x86_64", "manylinux2010_x86_64", "manylinux1_x86_64", "linux_x86_64"]
    tags = set(cpython_tags((3, 12), platforms=platforms)) | set(compatible_tags((3, 12), interpreter="cp312", platforms=platforms))
    advisories = []
    for path in OUT.glob("*-host-artifacts.json"):
        for artifact in json.loads(path.read_text())["artifacts"]:
            if not parse_wheel_filename(artifact["filename"])[3] & tags:
                raise ValueError("wheel incompatible with Bookworm: " + artifact["filename"])
            if artifact.get("vulnerabilities"):
                advisories.append({"package": artifact["name"], "version": artifact["version"],
                     "ids": sorted({item["id"] for item in artifact["vulnerabilities"]}),
                     "disposition": "existing runtime version preserved; retained risk, not repaired in F01; not a security-clearance claim"})
    active = []
    forbidden = []
    for owner in OWNERS:
        for path in owner.rglob("*"):
            relative = path.relative_to(owner)
            if not path.is_file() or any(part in EXCLUDED for part in relative.parts):
                continue
            if path.suffix not in {".py", ".sh", ".md", ".txt", ".lock", ".in", ".json", ".yaml", ".whl"} and path.name != "Dockerfile":
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(owner):
                raise ValueError("unsafe source")
            active.append(path)
            if "tests" not in relative.parts and (path.suffix in {".py", ".sh"} or path.name == "Dockerfile"):
                text = path.read_text()
                if re.search(r'"-m",\s*"pip"|^RUN pip |&& pip freeze|uv (?:run|sync|venv)', text, re.M):
                    forbidden.append(str(path.relative_to(ROOT)))
    if forbidden:
        raise ValueError("active forbidden package path: " + json.dumps(forbidden))
    original = {entry["path"]: entry for entry in before["source"]}
    for entry in before["source"]:
        if entry["path"].startswith("libraries/"):
            path = ROOT / entry["path"]
            if pin(path)["sha256"] != entry["sha256"]:
                raise ValueError("canonical library changed")
            active.append(path)
    active.extend(OUT / name for name in ("run.py", "packages.py", "images.py", "finish.py", "build-install-review.json", "installed-constraints.txt"))
    archive = OUT / "post-source.tar.gz"
    entries = []
    with archive.open("xb") as stream, tarfile.open(fileobj=stream, mode="w:gz") as bundle:
        for path in sorted(set(active)):
            identity = pin(path)
            payload = path.read_bytes()
            member = tarfile.TarInfo(identity["path"])
            member.size = len(payload)
            member.mode = path.stat().st_mode & 0o777
            bundle.addfile(member, io.BytesIO(payload))
            entries.append(identity)
    with tarfile.open(archive) as bundle:
        if set(bundle.getnames()) != {entry["path"] for entry in entries}:
            raise ValueError("archive membership mismatch")
        for entry in entries:
            if sha(bundle.extractfile(entry["path"]).read()) != entry["sha256"]:
                raise ValueError("archive byte mismatch")
    changes = [{"path": entry["path"], "action": "modified" if entry["path"] in original else "added",
                "before": original.get(entry["path"]), "after": entry} for entry in entries
               if entry["path"] not in original or original[entry["path"]]["sha256"] != entry["sha256"]]
    sources = save("post-source.json", {"archive": pin(archive), "files": entries, "changes": changes,
                   "archive_verified": True, "historical_files_unchanged": len(before["historical_hash_only"]),
                   "canonical_libraries_unchanged": True})
    installed = {}
    for distribution in importlib.metadata.distributions():
        installed.setdefault(canonicalize_name(distribution.metadata["Name"]), distribution)
    conflicts = []
    for name, distribution in installed.items():
        for text in distribution.requires or []:
            requirement = Requirement(text)
            if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
                continue
            dependency = installed.get(canonicalize_name(requirement.name))
            if dependency is None or not requirement.specifier.contains(dependency.version, prereleases=True):
                conflicts.append({"package": name, "requires": text, "installed": None if dependency is None else dependency.version})
    environment = save("environment-after.json", {"conflicts": conflicts,
        "setuptools": {"version": importlib.metadata.version("setuptools"), "location": str(importlib.metadata.distribution("setuptools").locate_file(""))},
        "runtime_mutation": "none", "new_build_package": "setuptools==80.9.0", "bookworm_wheel_tags": "passed",
        "advisories": advisories, "security": "existing pinned runtime advisories retained; no blanket upgrade; no claim of vulnerability-free images"})
    verification = json.loads((OUT / "profile-verification.json").read_text())
    tests = []
    for path in (OWNERS[0] / "deploy/records/20260922T162402541505Z-test.json",
                 OWNERS[1] / "deploy/records/20260922T162408954013Z-validate.json",
                 OWNERS[2] / "deploy/evidence/20260922T162405922255Z-test.json"):
        tests.append(pin(path))
    gaps = ["F08 image build and live acceptance deliberately not executed", "Shared environment retains pre-existing conflicts and runtime advisories",
            "Host actual installation refuses six system-package shadows pending exact recovery review; current imports already satisfy locks",
            "Initial reads/edit-tool calls remain host-owned; no private session log copied; intermediate draft bytes not all archived",
            "Parallel duplicate script edit caused syntax failure, repaired before package execution; failed receipts retained",
            "uv --path inventory failed; nonexistent target inventory attempted mkdir and was denied; existing-path guard added",
            "Original mission monotonic start unavailable; inherited UTC start/deadline retained; long edit intervals lack required 60-second clock checks",
            "Effective host effort, token cost and total cost unverified; no worker dispatch", "No Pylance-specific tools exposed; runtime and editor diagnostics used"]
    handoff = {"status": "complete", "completion_scope": "F01 local dependency checkpoint only", "stage": "build", "next_transition": "overseer checkpoint publication then assigned F02",
       "objective": "uv locked profiles replace five pip mutations and two freeze sites while retaining imports",
       "constitution": {"revision": 1, "sha256": "0a7e39fe0b4a62588b24b1f975fd61c1cb42b80ec35a6d1d263bd39c6575e1c8"},
       "prechange_decision": {"path": "records/v2/20260922T154739145740Z-execute-remediation-v1/record.json", "sha256": "fd93069ab91f1d6afcc98fd557e3f4d6eb7bf834d537d2faed3c4df83036177b"},
       "source": sources, "post_archive": pin(archive), "profiles": verification, "environment": environment,
       "tests": tests, "active_non_uv_mutations": 0, "active_non_uv_freeze": 0,
       "package_decisions": ["reuse canonical manifests through source-pinned local wheels", "H/E 98-package profile; O adds loader, 99 packages",
          "MAF core 1.18.0, foundry 1.13.0, openai provider 1.14.3, Projects 2.6.1, OpenAI 3.13.0, host 2.1.0, loader 1.0.0b1",
          "uv 0.9.30 and Python 3.12.12 official manifest digests pinned", "only actual package addition setuptools 80.9.0 after reviewed dry-run, hash and collision/recovery checks",
          "O consumed repair actions refuse; retirement deferred F06", "no modern hosting adapter needed for existing Responses owner; legacy adapter excluded"],
       "next_F02_hypothesis": "Explicit shape validation and agreement-based extraction fix nested output/sample=None grader errors; directory-backed skills require rejection. Start existing test_live.py synthetic cases; no frozen evaluator or historical-score edits.",
       "gaps": gaps, "timing": {"mission_start": "2026-09-22T15:06:18Z", "absolute_deadline": "2026-09-22T21:06:18Z", "worker": timing, "penalty_minutes": 0},
       "settlement": {"workers": "none", "processes": "synchronous returned; no server", "cloud": "no calls or writes", "environment_creation": "none", "publication": "none; checkpoint input only"}}
    handoff_ref = save("handoff.json", handoff)
    save("checkpoint-input.json", {"record_type": "checkpoint", "id": "f01-uv-dependency-checkpoint", "stage": "optimization",
        "series_id": None, "run_id": None, "parent_run_id": None, "iteration": None,
        "occurred_at": datetime.now(timezone.utc).isoformat(), "actor": "agentcraft-overseer", "status": "complete",
        "decision_ids": ["execute-remediation-v1"], "changes": changes,
        "metrics": [{"name": "active_non_uv_package_mutation_sites", "value": 0, "unit": "sites"},
                    {"name": "historical_files_unchanged", "value": len(before["historical_hash_only"]), "unit": "files"}],
        "coverage": {"status": "complete-for-declared-scope", "observed": ["F01 locked profiles, offline tests, exact import bytes, source archive readback"], "gaps": gaps},
        "reversion": {"status": "not_verified", "plan": "F00 source recovery retained; F01 post archive readback verified. Build package exact added paths retained; no active restore or live rollback performed."},
        "rationale": "F01 uv-only reproducibility established without cloud mutation or unrelated runtime repair; no comparative improvement claim",
        "supersedes": None, "evidence": [handoff_ref, sources, environment],
        "record_refs": [{"path": "records/v2/20260922T154739145740Z-execute-remediation-v1/record.json",
                         "sha256": "fd93069ab91f1d6afcc98fd557e3f4d6eb7bf834d537d2faed3c4df83036177b", "relation": "authorized-by"}]})
    print(json.dumps({"handoff": handoff_ref, "archive": pin(archive), "historical_unchanged": len(before["historical_hash_only"]),
                      "conflicts": len(conflicts), "advisory_entries": len(advisories), "changed_paths": len(changes)}))


if __name__ == "__main__":
    main()