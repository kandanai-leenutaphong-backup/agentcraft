"""Assemble a conservative teardown proposal from immutable read-only evidence."""

from collections import Counter
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import shlex
from urllib.parse import urlsplit

from inventory_probe import ROOT, REPO, SUBSCRIPTION, TENANT, ENDPOINT, PROJECT_ID, REGISTRY_ID, retain


OWNED = {"agentcraft-hosted-tool-proof", "agentcraft-iris-optimization", "agentcraft-migration-tool-proof-v1", "agentcraft-migration-iris-v1"}
SOURCE_CACHE = {}
ITEMS = {}
GAPS = []


def read(path):
    path = Path(path)
    if not path.is_absolute():
        path = REPO / path
    return json.loads(path.read_text())


def latest(suffix):
    paths = sorted(ROOT.glob("*-" + suffix + ".json"))
    if not paths:
        raise ValueError("missing evidence: " + suffix)
    path = paths[-1]
    return path, read(path)


INDEX_PATH, INDEX = latest("receipt-identity-index")
REFERENCES = INDEX["identities"]


def reference(path, identity=None, pointer=None, fact=None):
    path = Path(path)
    if not path.is_absolute():
        path = REPO / path
    if path not in SOURCE_CACHE:
        payload = path.read_bytes()
        SOURCE_CACHE[path] = (payload.decode().splitlines(), hashlib.sha256(payload).hexdigest())
    lines, digest = SOURCE_CACHE[path]
    needle = json.dumps(identity, ensure_ascii=False) if identity is not None else None
    line = next((number for number, text in enumerate(lines, 1) if needle and needle in text), 1)
    return {"path": str(path.relative_to(REPO)), "line": line, "sha256": digest, "json_pointer": pointer, "fact": fact}


def source_proof(identity, actions=(), patterns=(), pointer=None):
    selected = []
    for candidate in REFERENCES.get(identity, []):
        name = Path(candidate["path"]).name
        if "intent" in name:
            continue
        action_match = candidate.get("action") in actions and candidate.get("status") == "complete"
        file_match = any(fnmatch.fnmatch(name, pattern) for pattern in patterns)
        if (action_match or file_match) and (pointer is None or candidate["pointer"].startswith(pointer)):
            selected.append(candidate)
    if not selected:
        return []
    selected.sort(key=lambda candidate: (len(candidate["path"]), candidate["path"], candidate["pointer"]))
    candidate = selected[0]
    return [reference(candidate["path"], identity, candidate["pointer"], "Original experiment operation retained this exact identity")]


def any_reference(identity):
    candidates = REFERENCES.get(identity, [])
    if not candidates:
        return []
    candidate = min(candidates, key=lambda candidate: (len(candidate["path"]), candidate["path"]))
    return [reference(candidate["path"], identity, candidate["pointer"], "Historical reference only; not independent creation proof")]


def add(kind, identity, state, live_path, proof=None, keep_reason=None, deletion=None, parent=None, detail=None,
        blocked=None, shared=False, force_keep=False):
    key = kind + "|" + identity
    if key in ITEMS:
        return ITEMS[key]
    proof = proof or []
    classification = "pre-existing/shared" if shared else "experiment-created" if proof else "unknown-provenance"
    disposition = "delete-candidate" if proof and not shared and not force_keep else "keep"
    item = {"key": key, "kind": kind, "id": identity, "current_state": state,
            "classification": classification, "disposition": disposition,
            "creator_provenance": {"status": "proved" if proof else "not proved", "evidence": proof},
            "current_evidence": reference(live_path, identity) if live_path else None,
            "keep_reason": keep_reason if disposition == "keep" else None,
            "delete": {"exact_call": deletion, "executed": False,
                       "irreversible": "Treat deletion as irreversible; no restore/soft-delete guarantee established",
                       "verification": "Read exact ID after deletion; require not found, not merely successful delete response"},
            "parent": parent, "details": detail or {}, "blockers": blocked or []}
    item["delete"]["execution_prohibited_in_this_assignment"] = True
    item["delete"]["api_verification"] = "Installed public SDK/CLI contract only; destructive request never exercised"
    if not deletion:
        item["delete"]["unresolved_reason"] = keep_reason or "No public supported deletion operation verified"
    if kind in {"agent", "agent_version", "hosted_session", "stored_response", "evaluation", "evaluation_run",
                "optimization_job", "optimization_candidate", "acr_manifest", "acr_repository"}:
        item["delete"]["irreversible"] = True
        item["delete"]["recovery"] = "No undelete contract established; recreating source/configuration is not restoring the same runtime/history"
    elif kind == "acr_tag":
        item["delete"]["irreversible"] = False
        item["delete"]["recovery"] = "Tag can be recreated only while its exact manifest/digest is retained"
    elif kind == "role_assignment":
        item["delete"]["irreversible"] = False
        item["delete"]["recovery"] = "Exact scoped assignment can be recreated with separate role-grant authority; access stops immediately on removal"
    elif kind == "model_deployment":
        item["delete"]["irreversible"] = "Conditional: deployment can be reprovisioned from recorded configuration, subject to model availability and quota; no atomic restore"
    else:
        item["delete"]["irreversible"] = "unknown: no retention/undelete contract verified; treat as irreversible before authorization"
    if not proof and not shared:
        item["keep_reason"] = keep_reason or "No local receipt proves this exact object was created by the named experiments"
        item["historical_references"] = any_reference(identity)
    if disposition == "delete-candidate" and not deletion:
        item["blockers"].append("No independently verified deletion operation for this object")
    ITEMS[key] = item
    return item


def values(suffix):
    path, envelope = latest(suffix)
    if envelope.get("status") == "error" or envelope.get("exit_code", 0) != 0:
        GAPS.append({"surface": suffix, "evidence": reference(path), "error": envelope.get("message", envelope.get("stderr"))})
        return path, []
    return path, envelope.get("result", [])


def assemble():
    agent_path, agents = values("agents")
    for agent in agents:
        name = agent["name"]
        proof = source_proof(name, actions=("deploy",), pointer="/result") if name in OWNED else []
        if name in OWNED and not proof:
            proof = source_proof(name, patterns=("deploy-*-created.json",), pointer="/name")
        add("agent", name, agent.get("state"), agent_path, proof,
            keep_reason="Outside the three testbeds; no experiment creation proof",
            deletion=f"project.agents.delete(agent_name={name!r}, force=False)", detail={"endpoint": ENDPOINT}, shared=name not in OWNED)
        version_path, versions = values("versions-" + name)
        for version in versions:
            identity = version["id"]
            version_proof = source_proof(identity, actions=("deploy", "demonstration-deploy"),
                patterns=("deploy-*-created.json", "*-validation-version.json", "*-created.json"))
            if version.get("draft"):
                version_proof = source_proof(version["version"], patterns=("*candidates*.json", "*candidate-metrics.json", "*optimizer-result.json", "*optimizer-final.json"))
                if not version_proof:
                    version_proof = source_proof(version["version"], actions=("collect-candidates", "optimizer-readback"), pointer="/result")
            if name not in OWNED:
                version_proof = []
            add("agent_version", identity, version.get("status"), version_path, version_proof,
                deletion=f"project.agents.delete_version(agent_name={name!r}, agent_version={version['version']!r}, force=False)",
                parent="agent|" + name, detail={"draft": version.get("draft"), "image": version.get("definition", {}).get("container_configuration", {}).get("image")},
                shared=name not in OWNED, keep_reason="Version belongs to a protected unrelated agent" if name not in OWNED else None)
            for field, kind, identity_field in (("blueprint", "agent_blueprint_principal", "principal_id"),
                    ("instance_identity", "agent_instance_principal", "principal_id"),
                    ("blueprint_reference", "agent_identity_blueprint", "blueprint_id")):
                child = version.get(field, {}).get(identity_field)
                if child:
                    child_proof = source_proof(child, patterns=("deploy-*-created.json",), actions=("deploy",), pointer=None) if name in OWNED else []
                    add(kind, child, "Referenced by current active agent version; directory object not independently read", version_path,
                        child_proof, parent="agent|" + name, force_keep=True, shared=name not in OWNED,
                        keep_reason="Provider-managed tenant identity; no independent tenant deletion authority or verified cascade contract",
                        detail=version[field], blocked=["Use agent owner lifecycle; verify identity cleanup separately. Do not delete an Entra principal merely by matching a name."])
        session_path, sessions = values("sessions-" + name)
        for session in sessions:
            identity = session["agent_session_id"]
            session_proof = source_proof(identity, actions=("invoke", "runtime-canary")) if name in OWNED else []
            parent = "agent_version|" + name + ":" + session.get("version_indicator", {}).get("agent_version", "unknown")
            item = add("hosted_session", identity, session.get("status"), session_path, session_proof,
                deletion=f"project.agents.stop_session(agent_name={name!r}, session_id={identity!r}); project.agents.delete_session(agent_name={name!r}, session_id={identity!r})",
                parent=parent, detail={"agent": name, "version": session.get("version_indicator", {}).get("agent_version"),
                                      "expires_at": session.get("expires_at"), "container_id": None,
                                      "container_observation": "Session is the public sandbox handle; separate container identity/running state not returned"},
                shared=name not in OWNED, keep_reason="No exact creation/invocation receipt; parent agent association alone is not creator proof" if name in OWNED else "Session belongs to protected unrelated agent")
            item["delete"]["stop_semantics"] = "stop_session terminates sandbox; delete_session is synchronous and returns 204 for absent sessions"

    job_path, jobs = values("optimization-jobs")
    job_proofs = {}
    job_evaluations = {}
    for job in jobs:
        identifier = job["id"]
        proof = source_proof(identifier, actions=("optimize",), patterns=("*optimizer-job-created.json",), pointer=None)
        job_proofs[identifier] = proof
        detail_path, envelope = latest("job-" + identifier)
        detail = envelope.get("result", {})
        candidates = detail.get("result", {}).get("candidates", [])
        add("optimization_job", identifier, detail.get("status", job.get("status")), detail_path, proof,
            deletion=f"project.beta.agents.delete_optimization_job(job_id={identifier!r})",
            detail={"cancel_if_nonterminal": f"project.beta.agents.cancel_optimization_job(job_id={identifier!r})",
                    "native_delete_cascade": "SDK documents cancellation of a non-terminal job and deletion of its candidate artifacts",
                    "candidate_count": len(candidates), "inputs": {key: value for key, value in detail.get("inputs", {}).items()
                        if key in ("agent_name", "agent_version", "train_dataset", "validation_dataset", "evaluators", "model")}})
        for candidate in candidates:
            candidate_id = candidate.get("candidate_id") or candidate.get("id")
            if not candidate_id:
                continue
            add("optimization_candidate", candidate_id, "Retained in succeeded native job result", detail_path, proof,
                deletion=f"project.beta.agents.delete_optimization_job(job_id={identifier!r})  # documented candidate cascade",
                parent="optimization_job|" + identifier,
                detail={key: candidate.get(key) for key in ("name", "agent_version", "eval_id", "eval_run_id")})
            if candidate.get("eval_id"):
                job_evaluations[candidate["eval_id"]] = identifier

    eval_path, evaluations = values("evals")
    for evaluation in evaluations:
        identifier = evaluation["id"]
        proof = source_proof(identifier, actions=("define", "evaluator-canary", "mapped-canary"),
                             patterns=("evaluation.json", "*canary-eval.json", "*canary-created.json"))
        if not proof and identifier in job_evaluations:
            proof = job_proofs[job_evaluations[identifier]] + any_reference(identifier)
        add("evaluation", identifier, "Definition exists", eval_path, proof,
            deletion=f"client.evals.delete(eval_id={identifier!r})", detail={"name": evaluation.get("name"),
                "optimizer_job": job_evaluations.get(identifier)})
        run_path, runs = values("eval-runs-" + identifier)
        for run in runs:
            run_id = run["id"]
            run_proof = source_proof(run_id, actions=("submit", "evaluator-canary", "mapped-canary"),
                patterns=("*run-id.json", "*canary-run.json", "*submitted.json", "*canary-created.json"))
            if not run_proof and proof and REFERENCES.get(run_id):
                run_proof = proof + any_reference(run_id)
            add("evaluation_run", run_id, run.get("status"), run_path, run_proof,
                deletion=f"client.evals.runs.delete(run_id={run_id!r}, eval_id={identifier!r})", parent="evaluation|" + identifier,
                detail={"eval_id": identifier, "cancel_if_nonterminal": f"client.evals.runs.cancel(run_id={run_id!r}, eval_id={identifier!r})"})
            artifact = run.get("properties", {}).get("job_logs")
            if artifact:
                add("evaluation_result_artifact", artifact, "Referenced by current evaluation run; artifact contents not read", run_path,
                    run_proof, force_keep=True, parent="evaluation_run|" + run_id,
                    keep_reason="Provider-managed artifact; independent deletion/cascade and retention not established")
            subruns = run.get("properties", {}).get("AOAISubRunIds")
            if subruns:
                for child in json.loads(subruns):
                    child_id = child.get("eval_run_id")
                    if child_id:
                        add("provider_evaluation_subrun", child_id, "Provider subrun reference; not independently enumerated", run_path,
                            force_keep=True, parent="evaluation_run|" + run_id, detail=child,
                            keep_reason="Internal provider subrun; direct supported delete route and creation ownership not established")

    dataset_path, datasets = values("datasets")
    storage_locations = {}
    for dataset in datasets:
        version_path, versions = values("dataset-versions-" + dataset["name"])
        for version in versions:
            identifier = version["id"]
            proof = source_proof(identifier, actions=("upload",), patterns=("dataset-registered.json",))
            if not proof and version["name"].startswith("opt-inline-"):
                matched = next((job_id for job_id in job_proofs if job_id in (version.get("description") or "")), None)
                if matched:
                    proof = job_proofs[matched] + source_proof(version["name"], actions=("optimize",), pointer="/result/job/inputs")
            add("dataset_version", identifier, "Registered", version_path, proof,
                deletion=f"project.datasets.delete(name={version['name']!r}, version={version['version']!r})",
                detail={"name": version["name"], "version": version["version"], "data_uri": version.get("dataUri"),
                        "created_by": version.get("systemData", {}).get("createdBy"),
                        "blob_cascade": "Dataset deletion does not establish underlying blob deletion; verify separately"})
            if version.get("dataUri"):
                storage_locations[version["dataUri"]] = (version_path, identifier)

    evaluator_path, evaluators = values("custom-evaluators")
    for evaluator in evaluators:
        version_path, versions = values("evaluator-versions-" + evaluator["name"])
        for version in versions:
            name, number = version["name"], version["version"]
            proof = source_proof(name, patterns=("*registered.json",), actions=("evaluator-register",), pointer="/name")
            if not proof:
                proof = source_proof(name, actions=("evaluator-register",), pointer="/result/registered")
            add("evaluator_version", version.get("id") or name + ":" + number, "Registered", version_path, proof,
                deletion=f"project.beta.evaluators.delete_version(name={name!r}, version={number!r})", detail={"name": name, "version": number})
    builtin_path, builtin = latest("builtin-coherence")
    add("builtin_evaluator", "builtin.coherence:12", builtin.get("status"), builtin_path, shared=True,
        keep_reason="Service-owned builtin evaluator, not created by experiments")

    response_path, responses = latest("stored-responses")
    for response in responses["observations"]:
        identifier = response["id"]
        proof = any_reference(identifier)
        for record in proof:
            record["fact"] = "Exact response ID retained by experiment execution and read back through its owning agent endpoint"
        add("stored_response", identifier, response.get("result", {}).get("status", "unknown"), response_path, proof,
            deletion=f"project.get_openai_client(agent_name={response.get('agent_name')!r}).responses.delete(response_id={identifier!r})",
            parent="agent|" + response.get("agent_name", "unknown"), detail={"agent": response.get("agent_name"), "read_status": response["status"]},
            blocked=[] if response["status"] == "complete" else ["Current response existence/state is unknown"])

    for suffix in ("resources-personal-llm", "resources-rg-agentcraft-dev"):
        path, resources = values(suffix)
        for resource in resources:
            if resource["id"].lower() == PROJECT_ID.lower():
                continue
            add("arm_resource", resource["id"], "Present in current resource-group inventory; runtime state not probed", path, shared=True,
                keep_reason="Existing shared infrastructure or separately owned investigation resource; no experiment creation receipt",
                deletion=f"az resource delete --subscription {SUBSCRIPTION} --ids {shlex.quote(resource['id'])}",
                detail={"name": resource["name"], "type": resource["type"], "tags": resource.get("tags")})
    for suffix, kind in (("group-personal-llm", "resource_group"), ("group-rg-agentcraft-dev", "resource_group"),
                         ("project", "foundry_project")):
        path, envelope = latest(suffix)
        resource = envelope["result"]
        add(kind, resource["id"], resource.get("properties", {}).get("provisioningState", "Present"), path,
            shared=True, keep_reason="Explicitly protected shared target; not created by these experiments",
            deletion=(f"az group delete --subscription {SUBSCRIPTION} --name {shlex.quote(resource['name'])} --yes" if kind == "resource_group"
                      else f"az resource delete --subscription {SUBSCRIPTION} --ids {shlex.quote(resource['id'])} --api-version 2025-06-01"))
    model_path, models = values("model-deployments")
    for model in models:
        name = model["name"]
        proof = []
        if name == "agentcraft-iris-optimizer-gpt54":
            proof = [reference("testbeds/foundry-agent optimization/deploy/evidence/20260922T092204948979Z-provision-optimizer-model.json",
                               model["id"], "/events/1/result/id", "Successful explicit model deployment create command, exit_code 0")]
        model_item = add("model_deployment", model["id"], model.get("properties", {}).get("provisioningState"), model_path, proof,
            shared=not proof, keep_reason="Present before optimizer model creation; shared model/judge/embedding deployment",
            deletion=f"az cognitiveservices account deployment delete --subscription {SUBSCRIPTION} --resource-group personal-llm --name han-primary-foundry-resource --deployment-name {shlex.quote(name)}",
            detail={"name": name, "model": model.get("properties", {}).get("model"), "sku": model.get("sku")})
        if not proof:
            model_item["preexisting_evidence"] = reference(
                "testbeds/foundry-agent optimization/deploy/evidence/20260922T092204948979Z-provision-optimizer-model.json",
                model["id"], "/events/0/result", "Model present in deployment inventory before the dedicated optimizer model was created")
    for suffix in ("registry-roles", "project-roles", "experiment-principal-roles"):
        path, assignments = values(suffix)
        for assignment in assignments:
            identifier = assignment["id"]
            proof = []
            if identifier.endswith("/db33a7a4-ab49-599d-a307-6eac9cb102ba"):
                proof = [reference("testbeds/foundry-hosted-agents/deploy/records/20260922T054913876849Z-grant-pull.json",
                                   identifier, "/result/readback", "Receipt result.created is true; exact registry-scoped AcrPull assignment read back")]
            add("role_assignment", identifier, "Present", path, proof, shared=not proof,
                keep_reason="Other existing/inherited grant; not an experiment-specific creation receipt",
                deletion=f"az role assignment delete --subscription {SUBSCRIPTION} --ids {shlex.quote(identifier)}",
                detail={key: assignment.get(key) for key in ("principalId", "roleDefinitionId", "roleDefinitionName", "scope", "condition")})

    repository_path, repositories = values("acr-repositories")
    for repository in repositories:
        tags_path, tags = values("acr-tags-" + repository.replace("/", "_"))
        manifest_path, manifests = values("acr-manifests-" + repository.replace("/", "_"))
        repository_proof = source_proof(repository, actions=("build", "build-overlap")) if repository in OWNED else []
        for image in manifests:
            identifier = "agentcraftdev67255.azurecr.io/" + repository + "@" + image["digest"]
            proof = source_proof(identifier, actions=("build", "build-overlap", "demonstration-build"))
            if not proof and repository in OWNED:
                proof = source_proof(image["digest"], actions=("build", "build-overlap", "demonstration-build"), patterns=("*build*.json",))
            if proof and not repository_proof:
                repository_proof = proof
            add("acr_manifest", identifier, "Present", manifest_path, proof if repository in OWNED else [], shared=repository not in OWNED,
                deletion=f"az acr repository delete --subscription {SUBSCRIPTION} --name agentcraftdev67255 --image {shlex.quote(repository + '@' + image['digest'])} --yes",
                parent="acr_repository|agentcraftdev67255.azurecr.io/" + repository,
                detail={"tags": image.get("tags"), "digest": image["digest"], "delete_effect": "Removes manifest and all tags pointing at it; do not also delete each tag"},
                keep_reason="Investigation application image; unrelated to these experiments")
        add("acr_repository", "agentcraftdev67255.azurecr.io/" + repository, "Present", repository_path, repository_proof,
            shared=repository not in OWNED, keep_reason="Investigation application repository; shared registry must remain",
            deletion=f"az acr repository delete --subscription {SUBSCRIPTION} --name agentcraftdev67255 --repository {shlex.quote(repository)} --yes",
            detail={"bulk_delete": "Only after every live tag and untagged digest is proved owned; prefer exact manifest deletion"})
        for tag in tags:
            identifier = "agentcraftdev67255.azurecr.io/" + repository + ":" + tag["name"]
            digest_id = "agentcraftdev67255.azurecr.io/" + repository + "@" + tag["digest"]
            manifest_item = ITEMS["acr_manifest|" + digest_id]
            add("acr_tag", identifier, "Present", tags_path, manifest_item["creator_provenance"]["evidence"], shared=repository not in OWNED,
                deletion=f"az acr repository untag --subscription {SUBSCRIPTION} --name agentcraftdev67255 --image {shlex.quote(repository + ':' + tag['name'])}",
                parent="acr_manifest|" + digest_id, detail={"digest": tag["digest"], "not_storage_cleanup": "Untag retains manifest/layers; delete digest once instead"},
                keep_reason="Investigation image tag")
    runs_path, build_runs = values("acr-runs")
    for run in build_runs:
        proof = source_proof(run["runId"], actions=("build", "build-overlap", "demonstration-build"), patterns=("*build*.json",))
        add("acr_build_run", run["id"], run.get("status"), runs_path, proof, force_keep=True,
            shared=bool(run.get("outputImages")) and all(image["repository"] not in OWNED for image in run.get("outputImages", [])),
            keep_reason="Terminal build history; installed CLI has no task delete-run action; no verified direct run-delete API",
            detail={"run_id": run["runId"], "output_images": run.get("outputImages"),
                    "cancel_if_running": f"az acr task cancel-run --subscription {SUBSCRIPTION} --registry agentcraftdev67255 --run-id {run['runId']}"})

    _, blob_scope = latest("blob-probe-scope")
    blob_observations = {uri: latest("blob-cli-properties-" + str(position))[0]
                         for position, uri in enumerate(sorted(blob_scope["blobs"]), 1)}
    for path in sorted((REPO / "testbeds/foundry-agent-evaluation/deploy/records").rglob("*blob-uploaded.json")):
        blob = read(path)
        uri = blob.get("data_uri")
        if not uri:
            continue
        parsed = urlsplit(uri)
        container, name = parsed.path.lstrip("/").split("/", 1)
        proof = [reference(path, uri, "/data_uri", "Successful original blob upload receipt")]
        add("blob", uri, "unknown: Entra metadata read denied InvalidAuthenticationInfo", blob_observations.get(uri), proof,
            deletion=f"az storage blob delete --subscription {SUBSCRIPTION} --account-name {parsed.hostname.split('.')[0]} --container-name {container} --name {shlex.quote(name)} --auth-mode login",
            blocked=["Storage account belongs to provider subscription d4b89623-911e-42b6-b8b3-067246110cb2; no direct access or separate deletion authority proved",
                     "Read exact blob properties/version/retention before deletion; do not retrieve SAS without separately authorized credential handling"],
            detail={"sha256": blob.get("sha256"), "delete_snapshots": "Do not silently include snapshots; inventory first"})
        storage_locations.setdefault(uri.rsplit("/", 1)[0], (path, None))
    for path in sorted((REPO / "testbeds/foundry-agent-evaluation/deploy/records").rglob("*storage-response.json")):
        reservation = read(path)
        storage_account = reservation.get("storage_account_arm_id")
        if storage_account:
            add("provider_storage_account", storage_account, "Referenced in provider reservation receipts; not read outside authorized subscription", path,
                shared=True, force_keep=True, keep_reason="Provider-managed account in another subscription; never experiment teardown scope")
        identifier = reservation.get("pending_upload_id")
        if identifier:
            add("upload_reservation", identifier, "unknown: historical accepted reservation; no public read/list API exposed", None,
                [reference(path, identifier, "/pending_upload_id", "Provider pending-upload response status 200 returned exact reservation ID")],
                force_keep=True, keep_reason="No public reservation cancel/delete method in installed Projects SDK; reconcile through service owner",
                detail={"blob_uri": reservation.get("blob_uri"), "dataset_version": reservation.get("version"),
                        "storage_account_arm_id": reservation.get("storage_account_arm_id")})
    for uri, (path, dataset_id) in storage_locations.items():
        if "blob|" + uri in ITEMS:
            continue
        add("managed_blob_location", uri, "Location referenced; contents, blobs, versions and reservations not enumerable with current access", path,
            force_keep=True, parent="dataset_version|" + dataset_id if dataset_id else None,
            keep_reason="Container/prefix reference is not ownership of every stored object; foreign provider-managed storage",
            detail={"exact_blob_delete": None, "required_read": "Authorized ContainerClient.list_blobs for exact dataset prefix, versions and snapshots; never delete storage account/container blindly"})

    for item in list(ITEMS.values()):
        if item["disposition"] != "delete-candidate":
            continue
        children = [child["key"] for child in ITEMS.values() if child["parent"] == item["key"] and child["disposition"] == "keep"]
        if children and item["kind"] in {"agent", "agent_version", "evaluation", "acr_repository", "acr_manifest"}:
            item["blockers"].append({"protected_children": children, "rule": "No forced/cascading delete until ownership and disposition of every child is resolved"})
        if item["kind"] == "role_assignment" and any(child["kind"] == "agent_version" and child["disposition"] == "keep"
                and child["parent"].removeprefix("agent|") in OWNED for child in ITEMS.values()):
            item["blockers"].append("Protected experiment-agent versions remain; retain shared project AcrPull until every registry consumer is settled")
    for suffix in ("openai-containers", "openai-files", "openai-vector-stores"):
        values(suffix)

    clock_path = ROOT / "inventory-worker-oplog.jsonl"
    local_path, local = latest("local-processes")
    classifications = Counter(item["classification"] for item in ITEMS.values())
    dispositions = Counter(item["disposition"] for item in ITEMS.values())
    by_kind = {}
    for item in ITEMS.values():
        by_kind.setdefault(item["kind"], Counter())[item["disposition"]] += 1
    manifest = {
        "schema_version": 1, "status": "complete-with-explicit-coverage-gaps", "inventory_only": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "target": {"cloud": "AzureCloud", "tenant": TENANT, "subscription": SUBSCRIPTION, "project": PROJECT_ID, "registry": REGISTRY_ID},
        "authorized_scope": {"cloud_mutations_performed": [], "agent_dispatches": 0,
            "only_write_root": str(ROOT), "overseer_oplog_written": False,
            "teardown_authorized_by_this_manifest": False, "candidate_definition": "Proposal only, not permission; blockers and current read-back must be resolved before any separate teardown"},
        "provenance_policy": "Unknown exact-object creator provenance means keep. Mere namespace/timestamp/parent association is not proof. Provider child links require original parent creation plus exact retained identity or explicit live provider creation attribution.",
        "counts": {"total_items": len(ITEMS), "count_unit": "Unique resource/artifact identities; parent/child candidates overlap and are not a count of required deletion calls",
            "by_classification": dict(classifications), "by_disposition": dict(dispositions),
            "by_kind": {key: dict(value) for key, value in sorted(by_kind.items())},
            "delete_candidates_with_blockers": sum(item["disposition"] == "delete-candidate" and bool(item["blockers"]) for item in ITEMS.values()),
            "optimization_jobs_running": sum(job.get("status") not in {"succeeded", "failed", "cancelled"} for job in jobs),
            "visible_matching_local_processes": len(local["processes"]), "inaccessible_process_directories": len(local["inaccessible"])},
        "items": sorted(ITEMS.values(), key=lambda item: (item["kind"], item["id"])),
        "owning_entrypoints": [
            {"path": "testbeds/foundry-hosted-agents/deploy/deploy.sh", "teardown_actions": [], "read_actions": ["inspect", "logs", "preflight"],
             "not_executed_reason": "configure_run/main hardcode testbed records output; no output override; violates evidence-only write allowance",
             "evidence": reference("testbeds/foundry-hosted-agents/deploy/experiment.py", pointer="main", fact="actions at lines 785 and 813; receipt write at line 831")},
            {"path": "testbeds/foundry-agent-evaluation/deploy/deploy.sh", "teardown_actions": [], "read_actions": ["inspect-upload", "reconcile", "verify"],
             "not_executed_reason": "configure_run/main persist testbed records and bindings; no output override",
             "evidence": reference("testbeds/foundry-agent-evaluation/deploy/experiment.py", pointer="main", fact="choices at line 752; retain at line 798")},
            {"path": "testbeds/foundry-agent optimization/deploy/deploy.sh", "teardown_actions": [],
             "read_actions": ["inspect-runtime", "model-inventory", "optimizer-readback", "optimizer-reconcile", "optimizer-diagnostics", "optimizer-wait"],
             "not_executed_reason": "configure_run persists inputs/prerequisites; main persists testbed evidence; no authorized output override",
             "evidence": reference("testbeds/foundry-agent optimization/deploy/live.py", pointer="main", fact="action dispatch and receipt persistence lines 343-435")}
        ],
        "recommended_teardown_order": [
            "Freeze exact manifest hash; obtain separate mutation authority. Re-read mutable inventory and resolve all protected-child blockers before parent cascades.",
            "Stop only proved experiment local pollers/servers. None visible here; inaccessible process directories remain a gap.",
            "If a future recheck finds nonterminal owned optimization jobs or evaluation runs, cancel and poll exact IDs to terminal. Current five jobs and all listed runs are terminal.",
            "For session IDs proved owned, stop then delete sessions. Unknown-provenance sessions stay; do not force-delete their parent versions/agents.",
            "Archive needed results; delete exact owned stored responses, then proved evaluation runs/definitions and optimization jobs/candidate artifacts. Read back absence and provider-managed artifact cleanup.",
            "Delete only proved versions, then agents only when every remaining child is explicitly allowed. Keep unrelated hc agents and their sessions.",
            "Delete proved custom evaluator versions and registered datasets after jobs/runs stop referencing them. Blob/reservation cleanup requires separate supported access and exact inventory.",
            "Remove the dedicated agentcraft-iris-optimizer-gpt54 model after all consumers settle; retain all four pre-existing model deployments.",
            "Delete owned ACR digests once no retained version/app uses them. Prefer digest-level deletion; repository deletion requires every child proved owned. Keep investigation repository/registry.",
            "Remove only exact db33a7a4-ab49-599d-a307-6eac9cb102ba AcrPull grant last, after proving no retained shared project consumer needs it. Keep shared project/account/RGs and all unrelated roles/resources.",
            "Re-enumerate all surfaces and settle unknowns; never claim all resources removed from a parent delete response alone."
        ],
        "coverage_gaps": GAPS + [
            {"surface": "blob storage", "fact": "Four exact historical uploads found; Entra metadata access denied. No SAS/key retrieval, cross-subscription ARM read, blob content read or mutation."},
            {"surface": "reservations", "fact": "Four historical reservation IDs; no public list/get/delete reservation API in installed SDK. Additional provider-internal reservations cannot be excluded."},
            {"surface": "generated data and drafts", "fact": "67 eval-data datasets and unlinked draft/session children kept unknown; timestamps/names alone cannot authorize deletion."},
            {"surface": "managed identities and provider artifacts", "fact": "Agent metadata and eval-run references enumerate IDs; independent directory/blob runtime and cascade cleanup not established."},
            {"surface": "local processes", "evidence": reference(local_path), "fact": "Zero visible matches; 54 inaccessible /proc directories. No process stopped."},
            {"surface": "stored responses", "fact": "152 locally referenced IDs read through agent-scoped clients; no public response-list API, so unrecorded responses cannot be excluded."},
            {"surface": "capture/timing", "fact": "Worker clock begins after initial instruction reads; early/tool-output-only failures retained in handoff, not a complete host tool transcript. No user deadline supplied."}
        ],
        "empty_observed_surfaces": {"project_connections": 0, "acr_tasks": 0, "evaluator_generation_jobs": 0,
                                    "locks_personal_llm": 0, "locks_rg_agentcraft_dev": 0},
        "failed_attempts": ["SDK evaluator owner corrected to project.beta.evaluators", "AzureCliCredential tenant+subscription combination rejected; explicit subscription used after tenant verification",
            "jq unavailable; standard-library JSON used without installation", "Blob SDK tenant challenge conflicted with subscription; CLI read confirmed InvalidAuthenticationInfo",
            "Project-global response reads failed; agent-scoped probe and all 152 corrected reads succeeded", "az acr task delete-run --help unavailable; no guessed deletion executed",
            "First manifest draft failed readback because generic secret scrubber redacted its authorization metadata key; renamed to authorized_scope, regenerated and validated; failed draft retained"],
        "primary_evidence_index": [{"path": str(path.relative_to(REPO)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for path in sorted(ROOT.glob("2026*.json")) if "summary" not in path.name and "teardown-manifest" not in path.name],
        "worker_clock": str(clock_path.relative_to(REPO)),
        "mission_pins": {"constitution": reference("agentcraft_projects/foundry-official-integration-20260922/constitution/constitution.yaml"),
                         "candidate_pins": "Not applicable: no pilot or agent invocation; source hashes are provenance only"},
        "settlement": "No cloud mutation, no local process stop, no environment/package/account change, no dispatch. Only new evidence files under assigned root; original experiment receipts unchanged."
    }
    validate(manifest)
    path = retain("teardown-manifest", manifest)
    validate(read(path))
    print(json.dumps({"manifest": str(path.relative_to(REPO)), "counts": manifest["counts"]}, indent=2))


def validate(manifest):
    keys = [item["key"] for item in manifest["items"]]
    assert len(keys) == len(set(keys)) == manifest["counts"]["total_items"]
    identities = [item["id"] for item in manifest["items"]]
    assert len(identities) == len(set(identities))
    for item in manifest["items"]:
        assert item["id"] and item["current_state"] is not None
        if item["classification"] == "unknown-provenance":
            assert item["disposition"] == "keep"
        if item["disposition"] == "delete-candidate":
            assert item["creator_provenance"]["evidence"]
            assert item["delete"]["exact_call"] or item["blockers"]
        for evidence in item["creator_provenance"]["evidence"]:
            path = REPO / evidence["path"]
            assert path.is_file() and evidence["line"] >= 1
            assert hashlib.sha256(path.read_bytes()).hexdigest() == evidence["sha256"]
    assert manifest["authorized_scope"]["cloud_mutations_performed"] == []


if __name__ == "__main__":
    assemble()