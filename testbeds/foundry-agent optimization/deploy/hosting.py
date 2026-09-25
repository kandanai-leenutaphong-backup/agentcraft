"""Scoped Iris hosting over existing registry and Foundry project."""

from contextlib import ExitStack
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import threading

from foundry_ops.build import az_json, resolve_image, submit_build, wait_build
from foundry_ops.core import EvidenceLedger, encode_json, read_pinned, sha256_hex
from foundry_ops.hosting import deploy_version, hosted_definition

import prepare

NAME = "agentcraft-iris-optimization"
HOST = prepare.REPO / "testbeds/foundry-hosted-agents"
TARGET = json.loads((HOST / "deploy/env/target.json").read_text())


def command(live, arguments):
    return az_json(arguments, events=live.EVENTS, runner=subprocess.run)


def source_bytes(demonstration=False):
    built = json.loads((HOST / "deploy/records/20260922T060314845976Z-build.json").read_text())["result"]
    archive = HOST / built["archive"]
    if sha256_hex(archive.read_bytes()) != built["archive_sha256"]:
        raise ValueError("accepted library source archive drift")
    files = {}
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if not member.name.startswith("libraries/"):
                continue
            if not member.isfile() or ".." in Path(member.name).parts:
                raise ValueError("unsafe library archive member")
            content = bundle.extractfile(member).read()
            if sha256_hex(content) != built["source"]["files"][member.name]:
                raise ValueError("accepted library member drift")
            files[member.name] = content
    for name in ("main.py", "composition.py", "configuration.yaml", "prompts/classifier.md", "deploy/compatibility.py"):
        path = prepare.ROOT / name
        if path.is_symlink():
            raise ValueError("symlink application input refused")
        files["app/" + name] = path.read_bytes()
    for name in ("Dockerfile", "requirements.txt", "runtime-requirements.lock", "dependency-manifest.json"):
        files[name] = (prepare.ROOT / "deploy" / name).read_bytes()
    dependencies = json.loads(files["dependency-manifest.json"])
    for name, expected in dependencies["wheels"].items():
        path = prepare.ROOT / "deploy/wheelhouse" / name
        if path.is_symlink() or not path.resolve().is_relative_to(prepare.ROOT / "deploy/wheelhouse"):
            raise ValueError("unsafe dependency wheel")
        content = path.read_bytes()
        if sha256_hex(content) != expected:
            raise ValueError("locked wheel identity mismatch")
        files["wheelhouse/" + name] = content
    if sha256_hex(files["runtime-requirements.lock"]) != dependencies["runtime_lock_sha256"]:
        raise ValueError("runtime lock identity mismatch")
    files["app/.agent_configs/baseline/metadata.yaml"] = b"model: gpt-5.6-luna\ninstruction_file: instructions.md\n"
    files["app/.agent_configs/baseline/instructions.md"] = files["app/prompts/classifier.md"]
    selected = prepare.ROOT / ".agent_configs/selection.json"
    if selected.exists() and NAME == "agentcraft-iris-optimization":
        selection = json.loads(selected.read_text())
        candidate = json.loads((prepare.EVIDENCE / "selected-candidate.json").read_text())
        if selection["candidate_id"] != candidate["candidate_id"] or selection["instructions_sha256"] != candidate["instructions_sha256"]:
            raise ValueError("applied candidate provenance drift")
        instructions = (prepare.ROOT / ".agent_configs/baseline/instructions.md").read_bytes()
        if sha256_hex(instructions) != selection["instructions_sha256"]:
            raise ValueError("applied prompt drift")
        files["app/.agent_configs/baseline/instructions.md"] = instructions
        files["app/.agent_configs/selection.json"] = selected.read_bytes()
    if demonstration:
        import campaign
        decision, candidate = campaign.demonstration_context()
        files["app/.agent_configs/baseline/instructions.md"] = candidate["config"]["instructions"].encode()
        files["app/.agent_configs/selection.json"] = encode_json({
            "candidate_id": candidate["candidate_id"], "instructions_sha256": candidate["instructions_sha256"],
            "native_config_sha256": decision["native_config"]["sha256"], "purpose": "demonstration; validation regression"})
    hashes = {name: sha256_hex(content) for name, content in sorted(files.items())}
    manifest = {"files": hashes, "sha256": sha256_hex(encode_json(hashes)),
                "libraries_archive_sha256": built["archive_sha256"]}
    files["app/source-manifest.json"] = encode_json(manifest)
    return files, manifest


def build(live, demonstration=False):
    prepare.preflight()
    tests = prepare.tests()
    live.EVENTS.append({"operation": "local_tests", "result": tests})
    files, manifest = source_bytes(demonstration=demonstration)
    prefix = "build-" + manifest["sha256"]
    result_path = prepare.EVIDENCE / (prefix + "-result.json")
    if result_path.exists():
        return json.loads(result_path.read_text())
    archive = prepare.EVIDENCE / (prefix + ".tar.gz")
    if not archive.exists():
        with tarfile.open(archive, "x:gz") as bundle:
            for name, content in files.items():
                entry = tarfile.TarInfo(name)
                entry.size = len(content)
                bundle.addfile(entry, io.BytesIO(content))
    with tarfile.open(archive) as bundle:
        if set(bundle.getnames()) != set(files) or any(bundle.extractfile(name).read() != content for name, content in files.items()):
            raise ValueError("build archive mismatch")
    ledger = EvidenceLedger(prepare.EVIDENCE)
    target = {"subscription": TARGET["subscription_id"], "registry": TARGET["registry_name"]}

    def az(arguments):
        return command(live, arguments)

    with tempfile.TemporaryDirectory(prefix="iris-build-") as directory:
        if not ledger.exists(prefix + "-run.json"):
            for name, content in files.items():
                destination = Path(directory) / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
        run_id = submit_build(az, ledger, key=manifest["sha256"], image=NAME + ":" + manifest["sha256"],
                              context_dir=directory, **target)
    run = wait_build(az, run_id=run_id, sleep=threading.Event().wait, **target)
    image = resolve_image(az, run, registry_host=TARGET["registry_host"], repository=NAME, tag=manifest["sha256"], **target)
    result = {"image": image, "source": manifest, "archive": prepare.pin(archive), "run": run}
    live.retain(result_path.name, result)
    return result


def owned_previous(path, expected_sha256):
    previous = read_pinned(path, root=prepare.EVIDENCE, expected_sha256=expected_sha256)
    if previous.get("agent") != NAME or previous.get("actual", {}).get("metadata", {}).get("experiment") != NAME:
        raise ValueError("foreign previous deployment owner")
    return previous


def deployment(key):
    """Legacy `-active.json` records carry actual/build; foundry_ops active records pair with `-deployment.json`."""
    view = prepare.EVIDENCE / ("deploy-" + key + "-deployment.json")
    return json.loads((view if view.exists() else prepare.EVIDENCE / ("deploy-" + key + "-active.json")).read_text())


def deploy(live, demonstration=False, previous_path=None, previous_sha256=None):
    _, manifest = source_bytes(demonstration=demonstration)
    key = manifest["sha256"]
    built = json.loads((prepare.EVIDENCE / ("build-" + key + "-result.json")).read_text())
    ledger = EvidenceLedger(prepare.EVIDENCE)
    metadata = {"experiment": NAME, "source_sha256": key, "config_sha256": manifest["files"]["app/configuration.yaml"]}
    if demonstration:
        metadata.update({"purpose": "demonstration-not-production-promotion",
                         "native_candidate_id": selection["candidate_id"],
                         "instructions_sha256": selection["instructions_sha256"]})
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        previous = None
        if previous_path and not ledger.exists("deploy-" + key + "-created.json"):
            previous = owned_previous(previous_path, previous_sha256)
            actual_previous = project.agents.get_version(agent_name=NAME, agent_version=previous["version"]).as_dict()
            if (actual_previous.get("definition") != previous["actual"]["definition"]
                    or actual_previous.get("metadata") != previous["actual"].get("metadata")):
                raise ValueError("owned previous deployment drift")
            live.EVENTS.append({"operation": "owned_redeployment_prestate", "version": previous["version"], "actual": actual_previous})
        result = deploy_version(project, ledger, key=key, agent_name=NAME, definition=hosted_definition(built["image"]),
                                metadata=metadata, previous_version=previous and previous["version"],
                                previous_image=previous and previous["build"]["image"], sleep=threading.Event().wait)
        view = "deploy-" + key + "-deployment.json"
        if "actual" not in result and not ledger.exists(view):
            actual = project.agents.get_version(agent_name=NAME, agent_version=result["version"]).as_dict()
            live.retain(view, {"agent": NAME, "version": result["version"], "actual": actual, "build": built})
    return deployment(key)