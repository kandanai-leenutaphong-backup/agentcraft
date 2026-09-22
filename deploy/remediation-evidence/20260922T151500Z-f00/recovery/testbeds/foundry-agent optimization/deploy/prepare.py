"""Local preparation only. No cloud writes, optimizer submission or model calls."""

import argparse
from collections import Counter
import csv
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import time
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parents[1]
PROJECT = ROOT / "agentcraft_projects/foundry-agent-optimization"
EVIDENCE = ROOT / "deploy/evidence"
DATA = PROJECT / "dataset"
RAW = DATA / "private/source"
SEED = "uci-iris-v1-20260922"
DECISION = REPO / "specs/20260922_FOUNDRY_AGENT_OPTIMIZATION_DECISION.json"
SNAPSHOT_HASH = "9a873d53a750d3f17a14116199df8c7ddab02fb9a1127253529cecc1f4b572d2"
SOURCES = {"license.html": "https://archive.ics.uci.edu/dataset/53/iris",
           "iris.zip": "https://archive.ics.uci.edu/static/public/53/iris.zip"}
DATASET_SHA256 = "d11fe30213d36434a0879aab7cb00ce3c812eb7ba2495874438abff7b7b762e9"
spec = importlib.util.spec_from_file_location("frozen_classifier_evaluator", ROOT / "evaluator.py")
EVALUATOR = importlib.util.module_from_spec(spec)
spec.loader.exec_module(EVALUATOR)
LABELS = EVALUATOR.LABELS


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def pin(path):
    return {"path": str(path.relative_to(REPO)), "sha256": sha(path.read_bytes()), "bytes": path.stat().st_size}


def persist(path, payload):
    if path.is_symlink():
        raise ValueError("symlink output refused")
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f"immutable output differs: {path.name}")
    else:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    if path.read_bytes() != payload:
        raise ValueError("readback mismatch")
    return pin(path) if path.is_relative_to(REPO) else {"sha256": sha(payload)}


def snapshot():
    destination = EVIDENCE / "prechange.tar.gz"
    if not destination.exists():
        source = Path("/tmp/agentcraft-foundry-preparation-9198b9fd-prechange.tar.gz")
        if sha(source.read_bytes()) != SNAPSHOT_HASH:
            raise ValueError("prechange snapshot pin mismatch")
        persist(destination, source.read_bytes())
    if sha(destination.read_bytes()) != SNAPSHOT_HASH:
        raise ValueError("retained snapshot drift")
    entries = []
    records = 0
    with tarfile.open(destination, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile():
                continue
            archived = archive.extractfile(member).read()
            current = REPO / member.name.replace("testbeds/foundry-optimizer-agents/", "testbeds/foundry-agent-evaluation/", 1)
            unchanged = current.read_bytes() == archived
            if "/records/" in member.name:
                if not unchanged:
                    raise ValueError("immutable record changed")
                records += 1
            entries.append({"before": member.name, "after": str(current.relative_to(REPO)),
                            "sha256": sha(archived), "unchanged": unchanged})
    result = {"archive": pin(destination), "files": entries, "immutable_records_verified": records,
              "initial_capture": "tar compare against original disk passed before rename",
              "restore": "Archive retains old paths; restore only into a separate recovery directory, never over user edits.",
              "live_restore_tested": False}
    return result


def acquire():
    from webres import fetch
    RAW.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = RAW / name
        provenance = RAW / (name + ".provenance.json")
        if provenance.exists():
            metadata = json.loads(provenance.read_text())
            if metadata["source_url"] != url or sha(target.read_bytes()) != metadata["sha256"]:
                raise ValueError("acquisition provenance mismatch")
        else:
            if target.exists():
                raise ValueError("orphan acquisition requires reconciliation")
            payload, observed = fetch(url, timeout=30, obey_robots=True)
            persist(target, payload)
            persist(provenance, encoded(observed.to_dict()))
        if name == "license.html":
            page = target.read_text()
            if "creativecommons.org/licenses/by/4.0" not in page:
                raise ValueError("publisher CC BY 4.0 evidence absent; dataset download refused")
        elif sha(target.read_bytes()) != DATASET_SHA256:
            raise ValueError("upstream dataset revision changed; frozen hash refused")
    return {"sources": [pin(RAW / name) for name in SOURCES],
            "license": "CC-BY-4.0", "robots": "enforced by webres", "tls": "verified"}


def rows_from_text(text):
    unique = {}
    duplicates = 0
    total = 0
    for row in csv.reader(io.StringIO(text)):
        if not row:
            continue
        total += 1
        if len(row) != 5 or row[4] not in LABELS:
            raise ValueError("invalid row or class")
        features = tuple(float(value) for value in row[:4])
        if any(not math.isfinite(value) or value <= 0 for value in features):
            raise ValueError("invalid measurement")
        key = sha(encoded(features))
        if key in unique:
            if unique[key]["label"] != row[4]:
                raise ValueError("conflicting labels for identical features")
            duplicates += 1
        else:
            unique[key] = {"id": key, "features": features, "label": row[4]}
    if not unique:
        raise ValueError("empty dataset")
    return list(unique.values()), {"raw_rows": total, "duplicates_removed": duplicates, "unique_rows": len(unique)}


def splits(rows):
    result = {name: [] for name in ("train", "validation", "holdout")}
    for label in LABELS:
        group = sorted((row for row in rows if row["label"] == label), key=lambda row: sha((SEED + row["id"]).encode()))
        if len(group) < 5:
            raise ValueError("insufficient class support")
        size = max(1, round(len(group) * 0.2))
        result["holdout"].extend(group[:size])
        result["validation"].extend(group[size:2 * size])
        result["train"].extend(group[2 * size:])
    for name in result:
        result[name].sort(key=lambda row: sha((name + SEED + row["id"]).encode()))
    return result


def query(row):
    measurements = dict(zip(("sepal_length_cm", "sepal_width_cm", "petal_length_cm", "petal_width_cm"), row["features"], strict=True))
    return "Classify these iris measurements. Return exactly one of Iris-setosa, Iris-versicolor, Iris-virginica. Measurements: " + json.dumps(measurements, sort_keys=True)


def native_dataset(rows):
    from azure.ai.projects.models import AgentOptimizationDatasetCriterion, AgentOptimizationDatasetItem, AgentOptimizationInlineDatasetInput
    items = [AgentOptimizationDatasetItem(query=query(row), ground_truth=row["label"], desired_num_turns=1,
             criteria=[AgentOptimizationDatasetCriterion(name="classification_correctness",
                        instruction="Score 1 only if the entire stripped response exactly equals ground_truth; otherwise 0. No credit for explanations or synonyms.")]) for row in rows]
    return AgentOptimizationInlineDatasetInput(dataset_items=items).as_dict()


def prepare():
    acquire_result = acquire()
    with zipfile.ZipFile(RAW / "iris.zip") as archive:
        text = archive.read("iris.data").decode("ascii")
    rows, findings = rows_from_text(text)
    partitions = splits(rows)
    files = {}
    for name in ("train", "validation"):
        path = DATA / "candidate" / (name + ".json")
        files[name] = persist(path, encoded(native_dataset(partitions[name])))
    holdout = [{"id": row["id"], "query": query(row), "label": row["label"]} for row in partitions["holdout"]]
    secret_labels = DATA / "private/holdout.json"
    files["holdout"] = persist(secret_labels, encoded(holdout))
    secret_labels.chmod(0o600)
    centroids = {label: [sum(row["features"][column] for row in partitions["train"] if row["label"] == label) /
                        sum(row["label"] == label for row in partitions["train"]) for column in range(4)] for label in LABELS}
    predicted = [min(LABELS, key=lambda label: sum((value - center) ** 2 for value, center in zip(row["features"], centroids[label], strict=True)))
                 for row in partitions["validation"]]
    findings.update({"missing_measurements": 0, "classes": dict(Counter(row["label"] for row in rows)),
                     "feature_ranges_train_only": [[min(row["features"][column] for row in partitions["train"]),
                                                    max(row["features"][column] for row in partitions["train"])] for column in range(4)],
                     "development_probe": {"method": "nearest centroid fitted on train only; no model call",
                                           "validation": EVALUATOR.score([row["label"] for row in partitions["validation"]], predicted)},
                     "holdout_scored": False, "near_duplicate_policy": "Exact feature duplicates grouped; near-neighbors remain. Small canonical public benchmark may be memorized; no out-of-domain claim."})
    manifest = {"revision": "uci-iris-v1", "seed": SEED, "license": acquire_result["license"],
                "attribution": "Fisher, R. (1936). Iris. UCI Machine Learning Repository. https://doi.org/10.24432/C56C76",
                "sources": [{"url": SOURCES[name], **pin(RAW / name), "provenance": pin(RAW / (name + ".provenance.json"))} for name in SOURCES],
                "files": files, "membership": {name: [row["id"] for row in members] for name, members in partitions.items()},
                "class_counts": {name: dict(Counter(row["label"] for row in members)) for name, members in partitions.items()},
                "evaluator": pin(ROOT / "evaluator.py"), "preparation": pin(Path(__file__)), "findings": findings,
                "isolation": "Candidate upload allowlist is candidate/train.json and candidate/validation.json only. Raw source and holdout excluded from image, mounts, tools and optimizer; same-user local mode bits alone are not a sandbox."}
    persist(DATA / "manifest.json", encoded(manifest))
    return {"manifest": pin(DATA / "manifest.json"), "counts": {name: len(members) for name, members in partitions.items()}, "findings": findings}


def verify():
    manifest = json.loads((DATA / "manifest.json").read_text())
    for item in [*manifest["files"].values(), manifest["evaluator"], manifest["preparation"],
                 *manifest["sources"], *(source["provenance"] for source in manifest["sources"])]:
        if sha((REPO / item["path"]).read_bytes()) != item["sha256"]:
            raise ValueError("frozen artifact drift")
    membership = manifest["membership"]
    all_ids = [identifier for values in membership.values() for identifier in values]
    if len(all_ids) != len(set(all_ids)):
        raise ValueError("split leakage")
    for name in ("train", "validation"):
        document = json.loads((DATA / "candidate" / (name + ".json")).read_text())
        from azure.ai.projects.models import AgentOptimizationInlineDatasetInput
        if AgentOptimizationInlineDatasetInput(document).as_dict() != document:
            raise ValueError("native dataset serialization drift")
    return {"manifest": pin(DATA / "manifest.json"), "disjoint_rows": len(all_ids), "native_roundtrip": True,
            "snapshot": snapshot()["archive"], "immutable_records_verified": snapshot()["immutable_records_verified"]}


def preflight():
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    class OfflineCredential:
        def get_token(self, *args, **kwargs):
            raise RuntimeError("offline preflight refuses token acquisition")
    target = json.loads((REPO / "testbeds/foundry-agent-evaluation/deploy/records/approved-decision.json").read_text())
    with AIProjectClient(endpoint=target["endpoint"], credential=OfflineCredential()) as client:
        optimizer = callable(client.beta.agents.begin_create_optimization_job)
    packages = {}
    for name in ("azure-ai-projects", "harness-web-resource", "azure-ai-agentserver-core", "azure-ai-agentserver-agentframework", "azure-identity", "openai"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = None
    if packages["azure-ai-projects"] != "2.6.1" or not optimizer:
        raise ValueError("native optimizer prerequisite mismatch")
    modules = {}
    for name in ("agentconfig", "llm_interface", "azure.ai.agentserver.responses", "azure.ai.agentserver.agentframework"):
        try:
            module = importlib.util.find_spec(name)
            modules[name] = module.origin if module else None
        except ModuleNotFoundError:
            modules[name] = None
    account = subprocess.run(["az", "account", "show", "--query", "{subscription:id,tenant:tenantId}", "-o", "json"],
                             capture_output=True, text=True, timeout=30)
    if account.returncode != 0:
        raise ValueError("Azure CLI account unavailable; diagnostics omitted to protect credentials")
    account_value = json.loads(account.stdout)
    if account_value != {"subscription": target["subscription"], "tenant": target["tenant"]}:
        raise ValueError("Azure account does not match authorized target; no automatic context switch")
    observed = {}
    with AzureCliCredential(tenant_id=target["tenant"], process_timeout=30) as credential, AIProjectClient(
        endpoint=target["endpoint"], credential=credential, retry_total=0, connection_timeout=15, read_timeout=30
    ) as client:
        version = client.agents.get_version(agent_name=target["pins"]["agent_name"], agent_version=target["pins"]["agent_version"]).as_dict()
        if (version.get("status") != "active" or version["definition"]["container_configuration"]["image"] != target["image"]
                or any(version.get("metadata", {}).get(key) != target["pins"][key] for key in ("source_sha256", "config_sha256"))):
            raise ValueError("protected hosted agent drift")
        observed["protected_agent_active_and_unchanged"] = True
        observed["deployments"] = []
        for deployment in client.deployments.list():
            if len(observed["deployments"]) >= 100:
                raise ValueError("deployment inventory bound exceeded")
            observed["deployments"].append({key: getattr(deployment, key, None) for key in
                                           ("name", "model_name", "model_version", "capabilities")})
        observed["evaluators"] = []
        for evaluator in client.beta.evaluators.list(type="all", limit=100):
            if len(observed["evaluators"]) >= 200:
                raise ValueError("evaluator inventory bound exceeded")
            document = evaluator.as_dict()
            observed["evaluators"].append({key: document.get(key) for key in ("name", "version", "type", "id")})
        observed["exact_match_evaluator"] = client.beta.evaluators.get_version(name="builtin.string_check", version="2").as_dict()
        try:
            jobs = client.beta.agents.list_optimization_jobs(limit=1)
            next(iter(jobs), None)
            observed["optimizer_list_route"] = "accessible"
        except Exception as error:
            observed["optimizer_list_route"] = {"error_type": type(error).__name__, "http_status": getattr(error, "status_code", None)}
    return {"python": sys.executable, "packages": packages, "modules": modules, "account": account_value,
            "observed": observed, "operation": "AIProjectClient.beta.agents.begin_create_optimization_job",
            "operation_available": optimizer, "target_endpoint": target["endpoint"], "new_agent_name": "agentcraft-iris-optimization",
            "protected_agent": target["pins"], "cloud_reads": True, "cloud_writes": False, "model_calls": 0,
            "live_gaps": ["new agent/version not created or pinned", "native exact-match evaluator mapping needs a live canary before optimization",
                          "azure.ai.agentserver.agentframework absent locally; canonical agentconfig loader and Responses host are separate capabilities",
                          "optimizer support for hosted configuration mutation and promotion not live verified",
                          "candidate isolation and model availability must be verified at live assignment"],
            "effort": "maximum requested; effective host setting unverified"}


def tests():
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise ValueError(output.getvalue())
    return {"tests": result.testsRun, "output": output.getvalue()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("snapshot", "acquire", "prepare", "verify", "preflight", "test"))
    action = parser.parse_args().action
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    status = "complete"
    try:
        result = {"snapshot": snapshot, "acquire": acquire, "prepare": prepare, "verify": verify, "preflight": preflight, "test": tests}[action]()
    except Exception as error:
        status = "failed"
        result = {"error_type": type(error).__name__, "reason": str(error) if not hasattr(error, "status_code") else "service request failed; raw diagnostics omitted",
                  "http_status": getattr(error, "status_code", None)}
    receipt = {"action": action, "status": status, "started_at": started.isoformat(),
               "finished_at": datetime.now(timezone.utc).isoformat(), "seconds": time.monotonic() - clock,
               "decision": pin(DECISION), "result": result, "authority": "primary worker evidence; not authoritative publication"}
    path = EVIDENCE / (started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + action + ".json")
    persist(path, encoded(receipt))
    print(json.dumps({"status": status, "receipt": pin(path), "result": result if action not in {"snapshot", "test", "preflight"} else {"details": "see receipt"}}, sort_keys=True))
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())