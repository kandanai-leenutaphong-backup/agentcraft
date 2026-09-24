"""Reproducible F01 package preparation using existing Python and uv only."""

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import shutil
import site
import subprocess
import sys
import tarfile
import tomllib
import urllib.request
import zipfile

from packaging.requirements import Requirement
from packaging.tags import sys_tags
from packaging.utils import canonicalize_name, parse_wheel_filename

from run import ROOT, OUT, run

PYTHON = "/usr/bin/python3"
TARGET = Path("/home/hanchoong/.local/lib/python3.12/site-packages")
HOST = ROOT / "testbeds/foundry-hosted-agents/deploy"
OPT = ROOT / "testbeds/foundry-agent optimization/deploy"
LIBRARIES = ("framework-core", "llm-interface", "modular-agents")
LOCAL = {"agentcraft-core", "llm-interface", "modular-agents"}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x") as stream:
        stream.write(payload)
    assert path.read_text() == payload


def execute(command, cwd=ROOT):
    if run(command, cwd):
        raise RuntimeError("command failed; inspect append-only command receipt")


def uv(*arguments):
    return ["uv", "--no-config", *arguments]


def target_check():
    if sys.executable != PYTHON or not TARGET.is_dir() or TARGET.is_symlink():
        raise ValueError("existing interpreter/target mismatch")
    if Path(site.getusersitepackages()).resolve() != TARGET.resolve() or not os.access(TARGET, os.W_OK):
        raise ValueError("unapproved or nonwritable user-site")
    paths = [Path(path).resolve() for path in sys.path if path]
    if TARGET not in paths or any(paths.index(Path(path)) < paths.index(TARGET)
                                  for path in site.getsitepackages() if Path(path) in paths):
        raise ValueError("user-site does not precede system packages")
    return {"python": PYTHON, "target": str(TARGET), "sys_path": sys.path,
            "target_index": paths.index(TARGET), "system_writable": {
                path: os.access(path, os.W_OK) for path in site.getsitepackages()}}


def inventory():
    containment = target_check()
    inventories = {}
    for path in [TARGET, *map(Path, site.getsitepackages())]:
        if not path.is_dir():
            continue
        command = uv("pip", "list", "--python", PYTHON, "--target", str(path), "--format", "json")
        execute(command)
        latest = sorted(OUT.glob("*-command.json"))[-1]
        inventories[str(path)] = json.loads(json.loads(latest.read_text())["stdout"])
    versions = {}
    for packages in inventories.values():
        for package in packages:
            versions.setdefault(canonicalize_name(package["name"]), package["version"])
    save(OUT / "target-before.json", {"containment": containment, "inventories": inventories})
    constraints = "\n".join(f"{name}=={version}" for name, version in sorted(versions.items())
                              if name not in LOCAL | {"setuptools", "wheel"}) + "\n"
    (OUT / "installed-constraints.txt").write_text(constraints)
    execute(uv("pip", "compile", "--python", PYTHON, "--no-python-downloads", "--no-build-isolation",
               "--only-binary", ":all:", "--generate-hashes", str(HOST / "build-requirements.txt"),
               "-o", str(HOST / "build-requirements.lock")))


def build_install(dry_run):
    containment = target_check()
    if not dry_run:
        review = json.loads((OUT / "build-install-review.json").read_text())
        if review["lock_sha256"] != sha((HOST / "build-requirements.lock").read_bytes()):
            raise ValueError("reviewed build lock changed")
        if importlib.metadata.distribution("setuptools").locate_file("").resolve() == TARGET:
            raise ValueError("existing user-site setuptools needs exact backup before replacement")
        with zipfile.ZipFile(HOST / "wheelhouse/setuptools-80.9.0-py3-none-any.whl") as bundle:
            added = [name for name in bundle.namelist() if not name.endswith("/")]
            if any((TARGET / name).exists() or ".." in Path(name).parts for name in added):
                raise ValueError("build wheel would overwrite existing user-site file")
        save(OUT / "build-recovery.json", {"before": {"version": importlib.metadata.version("setuptools"),
             "origin": str(importlib.metadata.distribution("setuptools").locate_file(""))},
             "added_wheel_paths": added,
             "target": str(TARGET), "method": "system setuptools remains untouched; remove only added wheel RECORD paths after reviewing ownership",
             "wheel": str(HOST / "wheelhouse/setuptools-80.9.0-py3-none-any.whl"),
             "wheel_sha256": sha((HOST / "wheelhouse/setuptools-80.9.0-py3-none-any.whl").read_bytes())})
    command = uv("pip", "install", "--python", PYTHON, "--no-python-downloads", "--no-build-isolation",
                 "--only-binary", ":all:", "--require-hashes", "--target", str(TARGET),
                 "--no-index", "--find-links", str(HOST / "wheelhouse"),
                 "-r", str(HOST / "build-requirements.lock"))
    if dry_run:
        command.append("--dry-run")
    execute(command)
    print(json.dumps(containment))


def wheels():
    staged = OUT / "build-source"
    archive = ROOT / "deploy/remediation-evidence/20260922T151500Z-f00/source.tar.gz"
    if sha(archive.read_bytes()) != "ec3ba0a346a6589a101d7101d3be761e3112a4c843ebade80071df93335e2076":
        raise ValueError("F00 source archive changed")
    entries = []
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if not any(member.name.startswith("libraries/" + library + "/") for library in LIBRARIES):
                continue
            if not member.isfile() or ".." in Path(member.name).parts:
                raise ValueError("unsafe canonical source member")
            payload = bundle.extractfile(member).read()
            if (ROOT / member.name).read_bytes() != payload:
                raise ValueError("canonical source drift")
            destination = staged / member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() and destination.read_bytes() != payload:
                raise ValueError("staged source drift")
            destination.write_bytes(payload)
            entries.append({"path": member.name, "sha256": sha(payload)})
    save(OUT / "canonical-wheel-sources.json", entries)
    for library in LIBRARIES:
        execute(uv("build", "--wheel", "--python", PYTHON, "--no-python-downloads", "--no-build-isolation",
                   "--no-sources", "--no-create-gitignore", "--out-dir", str(HOST / "wheelhouse"),
                   str(staged / "libraries" / library)))


def compile_profiles():
    for owner in (HOST, OPT):
        if owner == OPT:
            (owner / "wheelhouse").mkdir(exist_ok=True)
            for wheel in (HOST / "wheelhouse").glob("*.whl"):
                name, _, _, _ = parse_wheel_filename(wheel.name)
                if canonicalize_name(name) in LOCAL:
                    shutil.copyfile(wheel, owner / "wheelhouse" / wheel.name)
        for profile in ("runtime", "host"):
            execute(uv("pip", "compile", "--python", PYTHON, "--no-python-downloads", "--no-build-isolation",
                       "--no-sources", "--only-binary", ":all:", "--prerelease", "allow", "--generate-hashes",
                       "--find-links", str(owner / "wheelhouse"),
                       "--constraints", str(OUT / "installed-constraints.txt"),
                       str(owner / (profile + "-requirements.in")), "-o", str(owner / (profile + "-requirements.lock"))))


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def artifacts(owner, profile):
    lock = owner / (profile + "-requirements.lock")
    text = lock.read_text()
    logical = text.replace("\\\n", " ").splitlines()
    wheelhouse = owner / "wheelhouse"
    wheelhouse.mkdir(exist_ok=True)
    provenance = []
    tags = list(sys_tags())
    for line in logical:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line.split(" --hash=", 1)[0].strip())
        version = next(iter(requirement.specifier)).version
        hashes = {part.split()[0] for part in line.split("--hash=sha256:")[1:]}
        local = [path for path in wheelhouse.glob("*.whl")
                 if canonicalize_name(parse_wheel_filename(path.name)[0]) == canonicalize_name(requirement.name)
                 and str(parse_wheel_filename(path.name)[1]) == version]
        if canonicalize_name(requirement.name) in LOCAL:
            if len(local) != 1 or sha(local[0].read_bytes()) not in hashes:
                raise ValueError("local wheel hash mismatch")
            provenance.append({"name": requirement.name, "version": version, "filename": local[0].name,
                               "sha256": sha(local[0].read_bytes()), "source": "canonical-wheel-sources.json"})
            continue
        metadata = fetch_json(f"https://pypi.org/pypi/{requirement.name}/{version}/json")
        candidates = []
        for artifact in metadata["urls"]:
            if artifact["packagetype"] != "bdist_wheel" or artifact["digests"]["sha256"] not in hashes:
                continue
            wheel_tags = parse_wheel_filename(artifact["filename"])[3]
            rank = min((tags.index(tag) for tag in wheel_tags if tag in tags), default=None)
            if rank is not None:
                candidates.append((rank, artifact))
        if not candidates:
            raise ValueError("no compatible hash-locked wheel: " + requirement.name)
        artifact = min(candidates, key=lambda value: value[0])[1]
        destination = wheelhouse / artifact["filename"]
        if not destination.exists():
            with urllib.request.urlopen(artifact["url"], timeout=60) as response:
                payload = response.read()
            if sha(payload) != artifact["digests"]["sha256"]:
                raise ValueError("artifact digest mismatch")
            with destination.open("xb") as stream:
                stream.write(payload)
        if sha(destination.read_bytes()) != artifact["digests"]["sha256"]:
            raise ValueError("retained artifact drift")
        provenance.append({"name": requirement.name, "version": version, "filename": destination.name,
                           "sha256": artifact["digests"]["sha256"], "url": artifact["url"],
                           "uploaded_at": artifact["upload_time_iso_8601"],
                           "license": metadata["info"].get("license_expression") or metadata["info"].get("license"),
                           "project_urls": metadata["info"].get("project_urls"),
                           "vulnerabilities": metadata.get("vulnerabilities", [])})
    name = owner.parent.name.replace(" ", "-") + "-" + profile + "-artifacts.json"
    save(OUT / name, {"profile": profile, "lock_sha256": sha(lock.read_bytes()),
                     "platform": "CPython 3.12 Linux x86_64", "artifacts": provenance,
                     "review_caveat": "PyPI release metadata and vulnerability feed; not a complete independent security audit"})


def finalize():
    for owner in (HOST, OPT):
        lock = owner / "runtime-requirements.lock"
        names = {canonicalize_name(Requirement(line.split(" --hash=", 1)[0].strip()).name)
                 for line in lock.read_text().replace("\\\n", " ").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")}
        wheels = {path.name: sha(path.read_bytes()) for path in (owner / "wheelhouse").glob("*.whl")
                  if canonicalize_name(parse_wheel_filename(path.name)[0]) in names}
        if len(wheels) != len(names):
            raise ValueError("incomplete runtime wheel closure")
        save(owner / "dependency-manifest.json", {"runtime_lock_sha256": sha(lock.read_bytes()),
             "host_lock_sha256": sha((owner / "host-requirements.lock").read_bytes()), "wheels": wheels,
             "platform": "CPython 3.12 Linux x86_64", "images": json.loads((OUT / "images.json").read_text()),
             "canonical_sources": json.loads((OUT / "canonical-wheel-sources.json").read_text()),
             "build_lock_sha256": sha((HOST / "build-requirements.lock").read_bytes())})


def verify():
    import importlib
    from email.parser import BytesParser
    from packaging.markers import default_environment

    reports = []
    for owner in (HOST, OPT):
        for profile in ("runtime", "host"):
            lock = owner / (profile + "-requirements.lock")
            output = OUT / (owner.parent.name.replace(" ", "-") + "-" + profile + "-reproduced.lock")
            execute(uv("pip", "compile", "--python", PYTHON, "--no-python-downloads", "--no-build-isolation",
                       "--only-binary", ":all:", "--no-index", "--find-links", str(owner / "wheelhouse"),
                       "--generate-hashes", "--prerelease", "allow", str(lock), "-o", str(output)))
            def requirements(path):
                return {canonicalize_name(requirement.name): requirement for line in path.read_text().replace("\\\n", " ").splitlines()
                        if line.strip() and not line.lstrip().startswith("#")
                        for requirement in [Requirement(line.split(" --hash=", 1)[0].strip())]}
            selected = requirements(lock)
            if {name: str(value.specifier) for name, value in selected.items()} != {
                    name: str(value.specifier) for name, value in requirements(output).items()}:
                raise ValueError("offline profile reproduction drift")
            missing = []
            for path in (owner / "wheelhouse").glob("*.whl"):
                name = canonicalize_name(parse_wheel_filename(path.name)[0])
                if name not in selected:
                    continue
                with zipfile.ZipFile(path) as bundle:
                    metadata = BytesParser().parsebytes(bundle.read(next(name for name in bundle.namelist() if name.endswith(".dist-info/METADATA"))))
                for text in metadata.get_all("Requires-Dist", []):
                    requirement = Requirement(text)
                    environments = [dict(default_environment(), extra=extra) for extra in ("", "foundry")
                                    if extra == "" or name == "llm-interface"]
                    if requirement.marker and not any(requirement.marker.evaluate(environment) for environment in environments):
                        continue
                    dependency = selected.get(canonicalize_name(requirement.name))
                    if dependency is None or not requirement.specifier.contains(next(iter(dependency.specifier)).version, prereleases=True):
                        missing.append({"owner": name, "requirement": text})
            if missing:
                raise ValueError("profile closure mismatch: " + json.dumps(missing))
            execute(uv("pip", "install", "--python", PYTHON, "--no-python-downloads", "--no-build-isolation",
                       "--only-binary", ":all:", "--require-hashes", "--no-index", "--find-links", str(owner / "wheelhouse"),
                       "--target", str(TARGET), "--dry-run", "-r", str(lock)))
            reports.append({"owner": owner.parent.name, "profile": profile, "packages": len(selected),
                            "complete_closure": True, "offline_reproduced": True, "lock_sha256": sha(lock.read_bytes())})
    imports = {}
    for name, distribution in {"agent_framework": "agent-framework-core", "azure.ai.projects": "azure-ai-projects",
         "azure.ai.agentserver.responses": "azure-ai-agentserver-responses", "azure.ai.agentserver.optimization": "azure-ai-agentserver-optimization",
         "llm_interface": "llm-interface", "agentconfig": "modular-agents", "agentcraft_core": "agentcraft-core"}.items():
        module = importlib.import_module(name)
        path = Path(module.__file__)
        candidates = [wheel for wheel in (OPT / "wheelhouse").glob("*.whl")
                      if canonicalize_name(parse_wheel_filename(wheel.name)[0]) == canonicalize_name(distribution)]
        with zipfile.ZipFile(candidates[0]) as bundle:
            expected = bundle.read(name.replace(".", "/") + "/__init__.py")
        imports[name] = {"path": str(path), "version": importlib.metadata.version(distribution),
                         "sha256": sha(path.read_bytes()), "matches_wheel": path.read_bytes() == expected}
    if not all(value["matches_wheel"] for value in imports.values()):
        raise ValueError("imported source differs from selected wheel: " + json.dumps(imports))
    save(OUT / "profile-verification.json", {"profiles": reports, "imports": imports,
          "shared_conflicts": "F00 conflicts intentionally not repaired; closure check is scoped to selected profiles"})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["inventory", "build-dry-run", "build-install", "wheels", "compile", "artifacts", "finalize", "verify"])
    parser.add_argument("--owner", choices=["H", "O"], default="H")
    parser.add_argument("--profile", choices=["build", "runtime", "host"], default="runtime")
    args = parser.parse_args()
    if args.action == "inventory":
        inventory()
    elif args.action in {"build-dry-run", "build-install"}:
        build_install(args.action == "build-dry-run")
    elif args.action == "wheels":
        wheels()
    elif args.action == "compile":
        compile_profiles()
    elif args.action == "finalize":
        finalize()
    elif args.action == "verify":
        verify()
    else:
        artifacts(HOST if args.owner == "H" else OPT, args.profile)