"""Scoped Iris hosting over existing registry and Foundry project."""

from contextlib import ExitStack
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import threading
import time

import prepare

NAME = "agentcraft-iris-optimization"
HOST = prepare.REPO / "testbeds/foundry-hosted-agents"
TARGET = json.loads((HOST / "deploy/env/target.json").read_text())


def command(live, arguments):
    started = time.monotonic()
    result = subprocess.run(["az", *arguments, "-o", "json"], capture_output=True, text=True, timeout=180)
    event = {"command": ["az", *arguments], "exit_code": result.returncode, "seconds": time.monotonic() - started}
    live.EVENTS.append(event)
    if result.returncode:
        event["diagnostic"] = result.stderr
        raise RuntimeError("scoped Azure command failed; inspect retained diagnostic")
    value = json.loads(result.stdout or "null")
    event["result"] = value
    return value


def source_bytes(demonstration=False):
    built = json.loads((HOST / "deploy/records/20260922T060314845976Z-build.json").read_text())["result"]
    archive = HOST / built["archive"]
    if prepare.sha(archive.read_bytes()) != built["archive_sha256"]:
        raise ValueError("accepted library source archive drift")
    files = {}
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if not member.name.startswith("libraries/"):
                continue
            if not member.isfile() or ".." in Path(member.name).parts:
                raise ValueError("unsafe library archive member")
            content = bundle.extractfile(member).read()
            if prepare.sha(content) != built["source"]["files"][member.name]:
                raise ValueError("accepted library member drift")
            files[member.name] = content
    for name in ("main.py", "composition.py", "configuration.yaml", "prompts/classifier.md", "deploy/compatibility.py"):
        path = prepare.ROOT / name
        if path.is_symlink():
            raise ValueError("symlink application input refused")
        files["app/" + name] = path.read_bytes()
    for name in ("Dockerfile", "requirements.txt"):
        files[name] = (prepare.ROOT / "deploy" / name).read_bytes()
    files["app/.agent_configs/baseline/metadata.yaml"] = b"model: gpt-5.6-luna\ninstruction_file: instructions.md\n"
    files["app/.agent_configs/baseline/instructions.md"] = files["app/prompts/classifier.md"]
    selected = prepare.ROOT / ".agent_configs/selection.json"
    if selected.exists():
        selection = json.loads(selected.read_text())
        candidate = json.loads((prepare.EVIDENCE / "selected-candidate.json").read_text())
        if selection["candidate_id"] != candidate["candidate_id"] or selection["instructions_sha256"] != candidate["instructions_sha256"]:
            raise ValueError("applied candidate provenance drift")
        instructions = (prepare.ROOT / ".agent_configs/baseline/instructions.md").read_bytes()
        if prepare.sha(instructions) != selection["instructions_sha256"]:
            raise ValueError("applied prompt drift")
        files["app/.agent_configs/baseline/instructions.md"] = instructions
        files["app/.agent_configs/selection.json"] = selected.read_bytes()
    if demonstration:
        import campaign
        decision, candidate = campaign.demonstration_context()
        files["app/.agent_configs/baseline/instructions.md"] = candidate["config"]["instructions"].encode()
        files["app/.agent_configs/selection.json"] = prepare.encoded({
            "candidate_id": candidate["candidate_id"], "instructions_sha256": candidate["instructions_sha256"],
            "native_config_sha256": decision["native_config"]["sha256"], "purpose": "demonstration; validation regression"})
    hashes = {name: prepare.sha(content) for name, content in sorted(files.items())}
    manifest = {"files": hashes, "sha256": prepare.sha(prepare.encoded(hashes)),
                "libraries_archive_sha256": built["archive_sha256"]}
    files["app/source-manifest.json"] = prepare.encoded(manifest)
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
    run_path = prepare.EVIDENCE / (prefix + "-run.json")
    base = ["--subscription", TARGET["subscription_id"], "--registry", TARGET["registry_name"]]
    tag = NAME + ":" + manifest["sha256"]
    if run_path.exists():
        run_id = json.loads(run_path.read_text())["run_id"]
    else:
        intent = prepare.EVIDENCE / (prefix + "-intent.json")
        if intent.exists():
            raise ValueError("unresolved build intent; inspect ACR before retry")
        before = command(live, ["acr", "task", "list-runs", *base, "--top", "30", "--query", "[].runId"])
        live.retain(intent.name, {"tag": tag, "archive": prepare.pin(archive), "prior_runs": before})
        with tempfile.TemporaryDirectory(prefix="iris-build-") as directory:
            context = Path(directory)
            for name, content in files.items():
                destination = context / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(content)
            command(live, ["acr", "build", *base, "--platform", "linux/amd64", "--image", tag,
                           "--file", str(context / "Dockerfile"), "--no-logs", "--no-wait", "--timeout", "900", str(context)])
        after = command(live, ["acr", "task", "list-runs", *base, "--top", "30", "--query", "[].runId"])
        new = set(after) - set(before)
        if len(new) != 1:
            raise ValueError("build run identity ambiguous; no automatic retry")
        run_id = new.pop()
        live.retain(run_path.name, {"run_id": run_id})
    deadline = time.monotonic() + 900
    while True:
        run = command(live, ["acr", "task", "show-run", *base, "--run-id", run_id,
                            "--query", "{runId:runId,status:status,outputImages:outputImages,startTime:startTime,finishTime:finishTime}"])
        if run["status"] == "Succeeded":
            break
        if run["status"] not in ("Queued", "Started", "Running") or time.monotonic() >= deadline:
            raise RuntimeError("build not successful; reconcile existing run")
        threading.Event().wait(10)
    matches = [image for image in run["outputImages"] if image["repository"] == NAME and image["tag"] == manifest["sha256"]]
    if len(matches) != 1:
        raise ValueError("build output identity mismatch")
    image = command(live, ["acr", "repository", "show", "--subscription", TARGET["subscription_id"],
                          "--name", TARGET["registry_name"], "--image", tag, "--query", "{digest:digest}"])
    if image["digest"] != matches[0]["digest"]:
        raise ValueError("image digest drift")
    result = {"image": TARGET["registry_host"] + "/" + NAME + "@" + image["digest"],
              "source": manifest, "archive": prepare.pin(archive), "run": run}
    live.retain(result_path.name, result)
    return result


def deploy(live, demonstration=False):
    _, manifest = source_bytes(demonstration=demonstration)
    built = json.loads((prepare.EVIDENCE / ("build-" + manifest["sha256"] + "-result.json")).read_text())
    prefix = "deploy-" + manifest["sha256"]
    created_path = prepare.EVIDENCE / (prefix + "-created.json")
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        if created_path.exists():
            created = json.loads(created_path.read_text())
        else:
            from azure.core.exceptions import ResourceNotFoundError
            try:
                existing = project.agents.get(NAME).as_dict()
            except ResourceNotFoundError:
                pass
            else:
                selection_path = prepare.ROOT / ".agent_configs/selection.json"
                if not selection_path.exists():
                    raise ValueError("existing agent requires selected-candidate redeployment")
                selection = json.loads(selection_path.read_text())
                if demonstration:
                    import campaign
                    decision, selection = campaign.demonstration_context()
                    if str(existing.get("versions", {}).get("latest", {}).get("version")) != decision["restore"]["version"]:
                        raise ValueError("demonstration prestate no longer baseline restore version")
                owned = json.loads((prepare.EVIDENCE / (selection["candidate_id"] + "-validation-version.json")).read_text())
                latest = existing.get("versions", {}).get("latest", {})
                actual_owned = project.agents.get_version(agent_name=NAME, agent_version=owned["version"]).as_dict()
                if actual_owned.get("metadata", {}).get("experiment") != NAME or not latest.get("version"):
                    raise ValueError("candidate deployment ownership missing")
                live.EVENTS.append({"operation": "selected_redeployment_prestate", "latest_version": latest["version"],
                                    "selected_validation_version": owned["version"]})
            definition = {"kind": "hosted", "cpu": "1", "memory": "2Gi",
                          "container_configuration": {"image": built["image"]},
                          "protocol_versions": [{"protocol": "responses", "version": "2.0.0"}]}
            metadata = {"experiment": NAME, "source_sha256": manifest["sha256"],
                        "config_sha256": manifest["files"]["app/configuration.yaml"]}
            if demonstration:
                metadata.update({"purpose": "demonstration-not-production-promotion",
                                 "native_candidate_id": selection["candidate_id"],
                                 "instructions_sha256": selection["instructions_sha256"]})
            intent = prepare.EVIDENCE / (prefix + "-intent.json")
            if intent.exists():
                raise ValueError("unresolved deployment intent; inspect before retry")
            live.retain(intent.name, {"name": NAME, "definition": definition, "metadata": metadata})
            created = project.agents.create_version(agent_name=NAME, body={"definition": definition, "metadata": metadata}).as_dict()
            live.retain(created_path.name, created)
        deadline = time.monotonic() + 300
        while True:
            actual = project.agents.get_version(agent_name=NAME, agent_version=str(created["version"])).as_dict()
            live.EVENTS.append({"operation": "hosted_state", "version": actual["version"], "status": actual.get("status")})
            if actual.get("status") == "active":
                break
            if actual.get("status") not in ("creating", "pending") or time.monotonic() >= deadline:
                raise RuntimeError("hosted version not active; inspect existing version")
            threading.Event().wait(5)
        if actual["definition"]["container_configuration"]["image"] != built["image"] or actual["metadata"]["source_sha256"] != manifest["sha256"]:
            raise ValueError("active hosted identity drift")
        result = {"agent": NAME, "version": str(actual["version"]), "actual": actual, "build": built}
        live.retain(prefix + "-active.json", result)
        return result