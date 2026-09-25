"""One-shot hosted evaluation integration; no optimization or hosting mutation."""

import argparse
from contextlib import ExitStack
import importlib.metadata
import importlib.util
import io
import json
from pathlib import Path
import re
import socket
import ipaddress
import subprocess
import sys
import time
import unittest
from urllib.parse import quote, unquote, urlsplit, urlunsplit


DEPLOY = Path(__file__).resolve().parent
ROOT = DEPLOY.parent
REPO = ROOT.parents[1]
FOUNDRY_OPS = REPO / "libraries/foundry-ops/src"
if str(FOUNDRY_OPS) not in sys.path:
    sys.path.insert(0, str(FOUNDRY_OPS))

from foundry_ops.core import (EvidenceLedger, error_summary, load_run_manifest, read_pinned, sanitize,  # noqa: E402
                              series_directory, sha256_hex, to_plain, utc_stamp)
from foundry_ops.core import sha256_file as digest  # noqa: E402
from foundry_ops.evaluation import (TERMINAL_RUN_STATUSES, PartialRowsError, check_counts,  # noqa: E402
                                    check_criteria, check_criterion, check_membership, check_row, collect_rows,
                                    target_text, validate_dataset_version, wait_for_run)
from foundry_ops.hosting import check_active_version  # noqa: E402

RECORDS = DEPLOY / "records"
PACKET = REPO / "specs/20260922_FOUNDRY_HOSTED_AGENT_EVALUATION"
HOST = REPO / "testbeds/foundry-hosted-agents"
CONSTITUTION = REPO / "agentcraft_projects/foundry-official-integration-20260922/constitution/constitution.yaml"
DECISION = json.loads((RECORDS / "approved-decision.json").read_text())
PINS = DECISION["pins"]
DATASET_NAME = "hosted-nonce-learning"
LEGACY_DATASET_VERSION = "sha256-" + DECISION["dataset_sha256"]
DATASET_VERSION = validate_dataset_version("sha256-" + DECISION["dataset_sha256"][:32])
NAME = "hosted-nonce-learning-" + DECISION["dataset_sha256"][:12]
EVENTS = []
RUN_MANIFEST = None
DATASET_PATH = PACKET / "dataset.jsonl"
oracle_spec = importlib.util.spec_from_file_location("packet_oracle", PACKET / "deploy/example.py")
ORACLE = importlib.util.module_from_spec(oracle_spec)
oracle_spec.loader.exec_module(ORACLE)


def ledger(directory=None):
    return EvidenceLedger(directory or RECORDS)


def retain(name, value, directory=None):
    return ledger(directory).retain(name, value)


def read_record(name):
    return ledger().read(name)


def reserve(name, request, directory=None):
    return ledger(directory).intent(name, request,
                                    context={"decision_sha256": digest(RECORDS / "approved-decision.json")})


def configure_run(path, expected_sha256, action, hosted_receipt=None, hosted_sha256=None):
    global RECORDS, DECISION, PINS, RUN_MANIFEST, DATASET_PATH, DATASET_NAME, DATASET_VERSION, NAME
    run = load_run_manifest(path, expected_sha256=expected_sha256, action=action, allowed_root=DEPLOY / "env",
                            pins={"constitution_sha256": CONSTITUTION,
                                  "target_sha256": DEPLOY / "records/approved-decision.json"})
    value = run.value
    binding = DEPLOY / "records" / run.series / "host-binding.json"
    if binding.exists():
        prior = json.loads(binding.read_text())
        if hosted_receipt and (str(Path(hosted_receipt).resolve()) != prior["path"] or hosted_sha256 != prior["sha256"]):
            raise ValueError("hosted binding changed")
        hosted_receipt, hosted_sha256 = prior["path"], prior["sha256"]
    require(bool(hosted_receipt) and bool(hosted_sha256), "first binding requires --hosted-receipt and --hosted-sha256")
    hosted = Path(hosted_receipt).resolve()
    receipt = read_pinned(hosted, root=HOST / "deploy/records/migration-h-v1", expected_sha256=hosted_sha256)
    require(receipt.get("action") == "deploy" and receipt.get("status") == "complete", "hosted deployment incomplete")
    deployed = receipt["result"]
    require(deployed["agent"] == run.agent, "accepted or foreign agent refused")
    require(receipt["target"]["project_endpoint"] == DECISION["endpoint"], "foreign hosted project")
    queries = value.get("queries", [])
    require(len(queries) == 3 and len(set(queries)) == 3 and all(re.fullmatch(r"[0-9a-f]{32}", query) for query in queries),
            "invalid fresh query membership")
    data = b"".join((json.dumps({"query": query}, sort_keys=True) + "\n").encode() for query in queries)
    directory = series_directory(DEPLOY / "records", run.series)
    store = EvidenceLedger(directory)
    run.bind(store)
    store.retain_bytes("dataset.jsonl", data, allow_identical=True)
    pins = {"agent_name": deployed["agent"], "agent_version": deployed["version"],
            "source_sha256": deployed["source"]["sha256"], "config_sha256": deployed["source"]["files"]["app/configuration.yaml"]}
    decision = dict(DECISION, pins=pins, image=deployed["image"], dataset_sha256=sha256_hex(data),
                    spec="specs/20260922_FOUNDRY_OFFICIAL_INTEGRATION_REMEDIATION.md", receipts={},
                    hypothesis="Fresh development SDK transport canary; no historical score comparison")
    for filename, payload in (("approved-decision.json", decision), ("host-binding.json", {"path": str(hosted), "sha256": hosted_sha256})):
        store.retain(filename, payload, allow_identical=True)
    RECORDS, DECISION, PINS, RUN_MANIFEST = directory, decision, pins, value
    DATASET_PATH = directory / "dataset.jsonl"
    ORACLE.ROOT = directory
    DATASET_NAME = run.series
    DATASET_VERSION = validate_dataset_version("sha256-" + decision["dataset_sha256"][:32])
    NAME = run.series
    return {"manifest_sha256": expected_sha256, "pins": pins, "dataset_sha256": decision["dataset_sha256"], "live": False}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def local_validate():
    dataset, dataset_hash = ORACLE.rows()
    require(dataset_hash == DECISION["dataset_sha256"], "dataset hash mismatch")
    if RUN_MANIFEST:
        return {"rows": len(dataset), "dataset_sha256": dataset_hash, "manifest_bound": True,
                "offline_suite": "run deploy.sh validate separately before live actions"}
    for name, expected in DECISION["receipts"].items():
        require(digest(HOST / "deploy/records" / name) == expected, "hosting receipt drift")
    for name in ("20260922T060615632239Z-verify.json", "20260922T060717524554Z-verify.json"):
        receipt = json.loads((HOST / "deploy/records" / name).read_text())
        result = receipt["result"]
        require(receipt["status"] == "complete" and result["readback"] is True
                and result["anonymous_status"] in (401, 403), "hosting acceptance incomplete")
        require(all(result["tool_evidence"][key] == value for key, value in PINS.items()), "hosting pins mismatch")
        require(result["version"]["definition"]["container_configuration"]["image"] == DECISION["image"], "image mismatch")
    build = json.loads((HOST / "deploy/records/20260922T060314845976Z-build.json").read_text())["result"]
    require(digest(HOST / build["archive"]) == build["archive_sha256"], "source archive mismatch")
    require(build["image"] == DECISION["image"], "build image mismatch")
    output = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(stream=output, verbosity=2).run(suite)
    require(result.wasSuccessful(), output.getvalue())
    return {"rows": len(dataset), "dataset_sha256": dataset_hash, "tests": result.testsRun,
            "test_output": output.getvalue(), "archive": build["archive"], "archive_sha256": build["archive_sha256"]}


def command(arguments):
    started = time.monotonic()
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=60)
    EVENTS.append({"command": arguments, "exit_code": result.returncode, "seconds": time.monotonic() - started})
    require(result.returncode == 0, "CLI request failed; no credential-bearing diagnostics retained")
    return json.loads(result.stdout)


def clients(stack):
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    credential = stack.enter_context(AzureCliCredential(tenant_id=DECISION["tenant"], process_timeout=30))
    project = stack.enter_context(AIProjectClient(endpoint=DECISION["endpoint"], credential=credential,
                                 retry_total=0, connection_timeout=15, read_timeout=60))
    client = stack.enter_context(project.get_openai_client(max_retries=0, timeout=60))
    return project, client


def version_check(project):
    version = project.agents.get_version(agent_name=PINS["agent_name"], agent_version=PINS["agent_version"]).as_dict()
    active = check_active_version(version, version=PINS["agent_version"], image=DECISION["image"],
                                  metadata={key: PINS[key] for key in ("source_sha256", "config_sha256")})
    return {"name": PINS["agent_name"], "version": active["version"], "status": active["status"],
            "image": DECISION["image"], "pins": PINS}


def preflight(project):
    account = command(["az", "account", "show", "--query", "{subscriptionId:id,tenantId:tenantId,cloud:environmentName}", "-o", "json"])
    require(account == {"subscriptionId": DECISION["subscription"], "tenantId": DECISION["tenant"], "cloud": "AzureCloud"}, "Azure context mismatch")
    versions = {name: importlib.metadata.version(name) for name in
                ("azure-ai-projects", "openai", "azure-identity", "azure-storage-blob")}
    require(versions["azure-ai-projects"] == "2.6.1" and versions["openai"] == "3.13.0", "SDK drift requires review")
    deployments = []
    for deployment in project.deployments.list():
        require(len(deployments) < 100, "deployment inventory exceeds bound")
        data = {key: getattr(deployment, key, None) for key in
            ("name", "type", "model_name", "model_version", "model_publisher", "capabilities", "connection_name")}
        data["sku"] = deployment.sku.as_dict() if getattr(deployment, "sku", None) else None
        deployments.append({key: data.get(key) for key in
                           ("name", "type", "model_name", "model_version", "model_publisher", "capabilities", "sku", "connection_name")})
    origins = {name: importlib.util.find_spec(name).origin for name in
               ("azure.ai.projects", "openai", "azure.identity", "azure.storage.blob")}
    return {"account": account, "python": sys.executable, "python_version": sys.version,
            "packages": versions, "origins": origins, "agent": version_check(project), "deployments": deployments}


def freeze(project):
    facts = preflight(project)
    judge = next(item for item in facts["deployments"] if item["name"] == "gpt-5.6-luna")
    require(judge["capabilities"].get("chat_completion") == "true", "judge lacks chat completion capability")
    require(judge["model_name"] and judge["model_version"], "judge model identity missing")
    versions = []
    for evaluator in project.beta.evaluators.list_versions(name="builtin.coherence", type="builtin", limit=20):
        require(len(versions) < 20, "evaluator version inventory exceeds bound")
        value = evaluator.as_dict()
        require(isinstance(value.get("version"), str) and value["version"].isdigit(), "unrecognized evaluator version")
        versions.append(value)
    require(bool(versions), "coherence evaluator catalogue empty")
    evaluator = max(versions, key=lambda item: int(item["version"]))
    selection = {"judge": judge, "prerequisites": facts,
                 "evaluator": {"name": "builtin.coherence", "version": evaluator["version"], "definition": evaluator},
                 "decision_sha256": digest(RECORDS / "approved-decision.json"),
                 "oracle_sha256": digest(PACKET / "deploy/example.py"),
                 "spec_sha256": digest(REPO / DECISION["spec"]),
                 "cost_exposure": "Existing GlobalStandard deployment; three target rows and one coherence criterion. No extra judge probe, model provisioning or hosting redeploy. Service retries/tokens/cost unknown."}
    retain("selection.json", selection)
    return selection


def evaluator_contract(value):
    return {key: field for key, field in value.items() if key not in {"created_at", "modified_at"}}


def selection_check(project):
    selected = read_record("selection.json")
    require(selected["decision_sha256"] == digest(RECORDS / "approved-decision.json"), "authority drift")
    require(selected["oracle_sha256"] == digest(PACKET / "deploy/example.py"), "oracle drift")
    judge = project.deployments.get(selected["judge"]["name"])
    require(judge.model_name == selected["judge"]["model_name"]
            and judge.model_version == selected["judge"]["model_version"]
            and judge.capabilities.get("chat_completion") == "true", "judge identity/capability drift")
    if RUN_MANIFEST:
        evaluator = selected["evaluator"]
        actual = project.beta.evaluators.get_version(name=evaluator["name"], version=evaluator["version"]).as_dict()
        EVENTS.append({"operation": "catalogue_evaluator_readback", "actual": actual})
        require(evaluator_contract(actual) == evaluator_contract(evaluator["definition"]), "frozen evaluator definition drift")
    version_check(project)
    return selected


def storage_url(url, arm_id, resolve=True, service_origin=None):
    parsed = urlsplit(url)
    match = re.fullmatch(r"/subscriptions/([^/]+)/resourceGroups/([^/]+)/providers/Microsoft.Storage/storageAccounts/([a-z0-9]+)", arm_id, re.IGNORECASE)
    require(match is not None and (match[1].lower() == DECISION["subscription"]
            or service_origin == DECISION["endpoint"]), "untrusted storage ARM identity")
    require(parsed.scheme == "https" and parsed.hostname == match[3].lower() + ".blob.core.windows.net"
            and parsed.port in (None, 443) and not parsed.username and not parsed.password
            and not parsed.fragment and parsed.path.startswith("/")
            and not re.search(r"[\x00-\x20\\]", url)
            and not re.search(r"%(?![0-9a-fA-F]{2})", parsed.path), "unsafe storage URL")
    path = unquote(parsed.path, errors="strict").rstrip("/")
    require(path and all(part not in ("", ".", "..") for part in path[1:].split("/"))
            and not re.search(r"[\x00-\x1f\x7f\\]", path), "unsafe storage path")
    if resolve:
        addresses = socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM)
        require(addresses and all(ipaddress.ip_address(item[4][0]).is_global for item in addresses), "nonpublic storage destination")
    return urlunsplit((parsed.scheme, parsed.hostname, quote(path, safe="/"), "", ""))


def storage_location(reference, resolve=True):
    from azure.storage.blob import ContainerClient
    arm = reference.storage_account_arm_id
    base = storage_url(reference.credential.sas_uri, arm, resolve, DECISION["endpoint"])
    target = storage_url(reference.blob_uri, arm, resolve, DECISION["endpoint"])
    base_parts = unquote(urlsplit(base).path)[1:].split("/")
    target_parts = unquote(urlsplit(target).path)[1:].split("/")
    require(len(base_parts) == 1 and re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{1,61}[a-z0-9])", base_parts[0])
            and "--" not in base_parts[0], "credential must identify one Azure container")
    require(urlsplit(base).hostname == urlsplit(target).hostname
            and target_parts[0] == base_parts[0], "blob outside credential container")
    with ContainerClient.from_container_url(reference.credential.sas_uri) as container:
        require(container.container_name == base_parts[0], "SDK container parsing mismatch")
    return {"container": base, "reference": target, "prefix": "/".join(target_parts[1:]),
            "storage_account_arm_id": arm}


def storage_metadata(value):
    reference = getattr(value, "blob_reference", None)
    credential = getattr(reference, "credential", None)
    return sanitize({"pending_upload_id": getattr(value, "pending_upload_id", None),
                      "version": getattr(value, "version", None),
                      "pending_upload_type": getattr(value, "pending_upload_type", None),
                      "storage_account_arm_id": getattr(reference, "storage_account_arm_id", None),
                      "blob_uri": getattr(reference, "blob_uri", None),
                      "credential_type": getattr(credential, "type", None),
                      "credential_container": getattr(credential, "sas_uri", None)})


def storage_response(pipeline_response):
    response = pipeline_response.http_response
    request_url = response.request.url
    from azure.ai.projects.models import PendingUploadResponse
    metadata = storage_metadata(PendingUploadResponse(response.json()))
    metadata.update({"request_url": sanitize(request_url), "status": response.status_code,
                     "request_id": response.headers.get("x-ms-request-id")})
    retain(utc_stamp() + "-storage-response.json", metadata)
    parsed = urlsplit(request_url)
    endpoint = urlsplit(DECISION["endpoint"])
    require(parsed.scheme == endpoint.scheme and parsed.hostname == endpoint.hostname
            and parsed.port in (None, 443) and not parsed.username and not parsed.password
            and parsed.path.startswith(endpoint.path + "/datasets/" + DATASET_NAME + "/versions/" + DATASET_VERSION),
            "foreign project response")
    require(response.status_code in (200, 201), "unsuccessful storage response")
    EVENTS.append({"operation": "authenticated-storage-response", "origin": DECISION["endpoint"],
                   "status": response.status_code, "request_id": response.headers.get("x-ms-request-id")})


def dataset_readback(project, dataset):
    from azure.storage.blob import ContainerClient
    credential = project.datasets.get_credentials(name=DATASET_NAME, version=DATASET_VERSION,
                                                 raw_response_hook=storage_response)
    reference = credential.blob_reference
    location = storage_location(reference)
    base = location["container"]
    uri = storage_url(dataset.data_uri, reference.storage_account_arm_id, service_origin=DECISION["endpoint"])
    require(urlsplit(uri).hostname == urlsplit(base).hostname
            and unquote(urlsplit(uri).path).startswith(unquote(urlsplit(base).path) + "/"), "dataset outside credential container")
    blob_name = unquote(urlsplit(uri).path)[len(unquote(urlsplit(base).path)) + 1:]
    with ContainerClient.from_container_url(reference.credential.sas_uri, retry_total=0,
                                           connection_timeout=15, read_timeout=60) as container:
        blob = container.get_blob_client(blob_name)
        properties = blob.get_blob_properties()
        expected = DATASET_PATH.read_bytes()
        require(properties.size == len(expected), "remote dataset length mismatch")
        content = blob.download_blob(offset=0, length=len(expected), max_concurrency=1).readall()
    require(content == expected, "remote dataset bytes mismatch")
    return {"id": dataset.id, "name": DATASET_NAME, "version": DATASET_VERSION,
            "sha256": sha256_hex(content), "remote_bytes_verified": True,
            "bytes": len(content), "storage_account_arm_id": reference.storage_account_arm_id,
            "data_uri": uri}


def upload(project):
    from azure.core.exceptions import ResourceNotFoundError
    from azure.ai.projects.models import PendingUploadRequest, FileDatasetVersion
    from azure.storage.blob import ContainerClient
    selection_check(project)
    try:
        existing = project.datasets.get(name=DATASET_NAME, version=DATASET_VERSION)
    except ResourceNotFoundError:
        existing = None
    if existing is not None:
        result = dataset_readback(project, existing)
        if (RECORDS / "dataset.json").exists():
            require(read_record("dataset.json")["id"] == result["id"], "dataset identity changed")
        else:
            retain("dataset.json", result)
        return dict(result, reused=True)
    require(RUN_MANIFEST is not None, "fresh pinned migration manifest required before upload")
    require(not any((RECORDS / name).exists() for name in ("valid-version-blob-intent.json", "valid-version-registration-intent.json")),
            "prior blob or registration outcome requires reconciliation")
    reserve("reservation", {"name": DATASET_NAME, "version": DATASET_VERSION, "sha256": DECISION["dataset_sha256"],
                            "manifest_sha256": digest(RECORDS / "run-manifest.json")})
    pending = project.datasets.pending_upload(name=DATASET_NAME, version=DATASET_VERSION,
                pending_upload_request=PendingUploadRequest(pending_upload_type="BlobReference"),
                raw_response_hook=storage_response)
    reference = pending.blob_reference
    location = storage_location(reference)
    base = location["container"]
    blob_name = (location["prefix"] + "/" if location["prefix"] else "") + "dataset.jsonl"
    location["blob_name"] = blob_name
    retain("valid-version-upload-location.json", location)
    with ContainerClient.from_container_url(reference.credential.sas_uri, retry_total=0,
                                           connection_timeout=15, read_timeout=60) as container:
        reserve("valid-version-blob", {"container": base, "blob_name": blob_name, "sha256": DECISION["dataset_sha256"]})
        with DATASET_PATH.open("rb") as source:
            with container.upload_blob(name=blob_name, data=source, overwrite=False, max_concurrency=1) as blob:
                data_uri = storage_url(blob.url, reference.storage_account_arm_id, service_origin=DECISION["endpoint"])
        retain("valid-version-blob-uploaded.json", {"data_uri": data_uri, "sha256": DECISION["dataset_sha256"]})
    reserve("valid-version-registration", {"name": DATASET_NAME, "version": DATASET_VERSION})
    dataset = project.datasets.create_or_update(name=DATASET_NAME, version=DATASET_VERSION,
                   dataset_version=FileDatasetVersion(data_uri=data_uri))
    retain("dataset-registered.json", {"id": dataset.id, "name": DATASET_NAME, "version": DATASET_VERSION})
    actual = project.datasets.get(name=DATASET_NAME, version=DATASET_VERSION)
    require(actual.id == dataset.id, "dataset registration readback mismatch")
    result = dataset_readback(project, actual)
    retain("dataset.json", result)
    return result


def inspect_upload(project):
    from azure.core.exceptions import HttpResponseError
    result = {"name": DATASET_NAME, "version": DATASET_VERSION, "write_retried": False,
              "blob_upload_attempted": (RECORDS / "blob-intent.json").exists(),
              "registration_attempted": (RECORDS / "registration-intent.json").exists()}
    try:
        dataset = project.datasets.get(name=DATASET_NAME, version=DATASET_VERSION)
        result["dataset"] = {"id": dataset.id, "type": dataset.type,
                             "data_uri": sanitize(dataset.data_uri)}
    except HttpResponseError as error:
        result["dataset_read"] = {"status": error.status_code, "code": getattr(error.error, "code", None)}
    try:
        credential = project.datasets.get_credentials(name=DATASET_NAME, version=DATASET_VERSION)
        reference = credential.blob_reference
        result["storage"] = {"arm_id": reference.storage_account_arm_id,
                             "blob_uri": sanitize(reference.blob_uri),
                             "credential_origin": urlsplit(reference.credential.sas_uri).hostname}
    except HttpResponseError as error:
        result["credential_read"] = {"status": error.status_code, "code": getattr(error.error, "code", None)}
    return result


def settled_closeout(project):
    selection_check(project)
    verified_path = RECORDS / "20260922T075653771799Z-verify.json"
    verified = read_record(verified_path.name)
    require(verified["status"] == "complete" and verified["result"]["accepted"], "missing live acceptance")
    result = verified["result"]
    rows_check(result["items"])
    require(all(ORACLE.oracle(item["datasource_item"]["query"], sample_text(item), PINS)
                for item in result["items"]), "retained proof no longer passes")
    dataset = dataset_readback(project, project.datasets.get(name=DATASET_NAME, version=DATASET_VERSION))
    require(dataset == read_record("dataset.json"), "final dataset readback drift")
    receipts = {path.name: json.loads(path.read_text()) for path in sorted(RECORDS.glob("*.json"))}
    failed = [{"path": name, "sha256": digest(RECORDS / name), "action": value.get("action"),
               "error": value.get("error"), "seconds": value.get("seconds")}
              for name, value in receipts.items() if value.get("status") == "failed"]
    validations = [value for value in receipts.values() if value.get("action") == "validate" and value.get("status") == "complete"]
    rows = [{"query": row["query"], "oracle_passed": row["oracle_passed"],
             "coherence": {key: row["results"][0].get(key) for key in
                ("score", "threshold", "label", "passed", "reason", "error", "status")}}
            for row in result["rows"]]
    return {"status": "complete", "stage": "measured-and-settled", "next_transition": "return-to-overseer",
            "objective": DECISION["objective"], "hypothesis": DECISION["hypothesis"],
            "outcome": "Completed one real three-row run; deterministic proof 3/3, coherence scores 4,4,2; capability proof only, no improvement claim.",
            "pins": PINS, "image": DECISION["image"], "judge": result["judge"],
            "dataset": dataset, **result["identity"], "report_url": result["aggregate"]["report_url"],
            "rows": rows, "aggregate": result["aggregate"], "tests": validations[-1]["result"]["tests"],
            "verified_receipt": {"path": verified_path.name, "sha256": digest(verified_path)},
            "attempts": {"pending_upload": 2 + len(list(RECORDS.glob("*-reservation-intent.json"))),
                         "blob_upload": 2, "registration_requests": 3, "registered_versions": 1,
                         "evaluation_definitions": 1, "evaluation_runs": 1, "target_rows": 3,
                         "judge_invocations_reported": 3, "automatic_retries": 0},
            "failed_receipts": failed,
            "local_failures": [
                "Two patch applications introduced indentation errors; immediate validation stopped locally; repaired and passed.",
                "SDK inspection attempted nonexistent SasCredential and private _model_base imports; corrected to public model APIs.",
                "Pre-submit adapter incorrectly assumed plain sample message content. First reconciliation locally marked proof false; actual service outputs retained, structured output-block decoder repaired and replayed. Original dotted generated field was valid; now cross-checked. No new run or inference.",
                "Generic OpenAI Pydantic serializer warns on Foundry extended data-source type; actual fields retained and read back.",
                "Architecture overview absent; no hosting or dependency ownership changes."],
            "retained": {"hosting": "unchanged accepted versions/images and existing judge",
                         "dataset": dataset["id"], "evaluation": result["identity"],
                         "orphan_uploaded_blob": read_record("blob-uploaded.json")["data_uri"],
                         "registered_blob": dataset["data_uri"],
                         "reservations": "Four pending-upload requests; first two IDs/expiry unknown; last two nonsecret IDs retained. No cleanup."},
            "settlement": "Run completed; no owned workers or local background processes; no further write/inference or teardown. Return checkpoint only.",
            "archival": "Primary receipts and original hosting archive retained; authoritative publication remains overseer-owned. No overseer dispatch.",
            "capture_gaps": ["First response metadata and second credential path were not retained; historical mismatch cause unknown.",
                             "First registration HTTP 400 body was discarded; same-version diagnostic replay captured version-length rejection.",
                             "Complete tool transcript remains host-owned; initial syntax failures have no runner receipts.",
                             "Total task duration, target token usage, cost and provider-internal retry count unknown; duplicate usage groups not summed.",
                             "Editor interpreter unknown; max effort requested, effective host setting unverified."],
            "measured_action_seconds": {name: value["seconds"] for name, value in receipts.items() if "seconds" in value},
            "evidence": {path.name: digest(path) for path in sorted(RECORDS.glob("*.json"))}}


def closeout(project):
    if (RECORDS / "run-id.json").exists():
        return settled_closeout(project)
    observed = inspect_upload(project)
    require(observed.get("dataset_read", {}).get("status") == 404
            and observed.get("credential_read", {}).get("status") == 404, "upload state changed; review before closeout")
    require((RECORDS / "upload-intent.json").exists(), "missing upload attempt evidence")
    require(not any((RECORDS / name).exists() for name in
                ("blob-intent.json", "registration-intent.json", "dataset-registered.json", "definition-intent.json", "run-intent.json", "run-id.json")), "later operation exists; reconcile it")
    recovery = (RECORDS / "upload-recovery-intent.json").exists()
    if recovery:
        import inspect
        from azure.ai.projects.operations import DatasetsOperations
        sdk = {"package": importlib.metadata.version("azure-ai-projects"),
               "source": inspect.getfile(DatasetsOperations),
               "source_sha256": digest(Path(inspect.getfile(DatasetsOperations))),
               "pending_upload": inspect.getdoc(DatasetsOperations.pending_upload),
               "get_credentials": inspect.getdoc(DatasetsOperations.get_credentials),
               "public_operations": [name for name in dir(DatasetsOperations) if not name.startswith("_")],
               "container_construction": inspect.getsource(DatasetsOperations._create_dataset_and_get_its_container_client)}
    else:
        sdk = None
    return {"status": "blocked", "stage": "dataset-upload", "objective": DECISION["objective"],
            "outcome": ("Second authorized pending-upload response captured provider-managed ARM and public Blob origin. Local credential/blob destination comparison failed before blob upload. Blob URI includes explicit :443; port canonicalization repaired and tested, but exact mismatch cause remains unverified because credential container path was not retained. SAS was memory-only and lost on process exit. Dataset and credential GET remain 404; no read-only pending-upload recovery operation exposed by installed SDK. No third request made."
                        if recovery else "Pending-upload response rejected by local storage ARM identity guard before blob upload. Named dataset and credentials both read back 404."),
            "pins": PINS, "image": DECISION["image"], "judge": read_record("selection.json")["judge"],
            "dataset": observed, "eval_id": None, "run_id": None, "report_url": None,
            "rows": [{"query": row["query"], "score": None, "oracle_verdict": "not-run"} for row in ORACLE.rows()[0]],
            "attempts": {"pending_upload": 2 if recovery else 1, "blob_upload": 0, "dataset_registration": 0,
                 "evaluation_definition": 0, "evaluation_run": 0, "target_inference": 0, "judge_inference": 0, "automatic_retries": 0},
            "hosting_readback": version_check(project),
            "retained": ["accepted hosted versions/images unchanged", "experiment-local write intent and receipts", "possible service-managed pending-upload reservations; second storage ARM/origin captured, reservation IDs/expiry/retention unknown"],
            "settlement": "No owned workers, local background processes, submitted evaluation runs or known asynchronous provider operations. Dataset absent; pending-upload reservation retention unknown; no cleanup attempted.",
            "managed_storage": read_record("pending-upload-metadata.json") if recovery else None,
            "sdk_recovery_contract": sdk,
            "recovery_decision_sha256": digest(RECORDS / "reservation-recovery-decision.json") if recovery else None,
            "local_failures": ["Initial recovery patch indentation error; validation refused before cloud activity; repaired and focused validation passed",
                               "Architecture overview absent; initial Python skill lookup used wrong repository path, corrected to installed skill path"] if recovery else [],
            "capture_gaps": ["First pending-upload ARM identity and origin not retained before guard failed; second response retained before destination validation",
                     "Second credential container path not retained; exact destination mismatch cause unverified; future nonsecret capture repaired",
                     "Pylance-specific tools unavailable; editor-selected interpreter unknown",
                     "Full tool transcript remains host-owned; total duration, tokens and cost unknown",
                     "Remaining definition/submission/result integration implemented but not live-verified"],
            "next_decision": ("Checkpoint required before any third pending_upload request. Installed SDK says pending_upload may retrieve or create; no read-only credential recovery for unregistered version. Scope would remain one actual upload/registration, definition and run, with unchanged pins/hash. Never erase either intent."
                              if recovery else "Authorize one additional pending_upload request with preserved prior intent and unchanged experiment bounds."),
            "cost": "unknown", "effort": "max requested, effective runtime setting unverified",
            "evidence": {path.name: digest(path) for path in sorted(RECORDS.glob("*.json"))}}


def define(project, client):
    from azure.ai.projects.models import TestingCriterionAzureAIEvaluator
    selected = selection_check(project)
    dataset = read_record("dataset.json")
    require(dataset["remote_bytes_verified"] is True and dataset["sha256"] == DECISION["dataset_sha256"], "dataset not verified")
    request = {"name": NAME, "data_source_config": {"type": "custom",
               "item_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
               "include_sample_schema": True}, "testing_criteria": [{"type": "azure_ai_evaluator", "name": "Coherence",
               "evaluator_name": "builtin.coherence", "initialization_parameters": {"deployment_name": selected["judge"]["name"]},
               "evaluator_version": selected["evaluator"]["version"],
               "data_mapping": {"query": "{{item.query}}", "response": "{{sample.output_text}}"}}]}
    request["testing_criteria"] = [TestingCriterionAzureAIEvaluator(item) for item in request["testing_criteria"]]
    reserve("definition", request)
    evaluation = client.evals.create(**request)
    result = {"id": evaluation.id, "request_id": getattr(evaluation, "_request_id", None)}
    retain("evaluation.json", result)
    actual = client.evals.retrieve(evaluation.id)
    require(actual.id == evaluation.id, "evaluation readback mismatch")
    return result


def submit(project, client):
    from azure.ai.projects.models import TargetCompletionEvalRunDataSource, AzureAIAgentTargetParam
    selection_check(project)
    dataset = read_record("dataset.json")
    actual = dataset_readback(project, project.datasets.get(name=DATASET_NAME, version=DATASET_VERSION))
    require(actual["id"] == dataset["id"], "dataset identity drift before run")
    request = {"eval_id": read_record("evaluation.json")["id"], "name": NAME,
               "data_source": {"type": "azure_ai_target_completions", "source": {"type": "file_id", "id": dataset["id"]},
               "input_messages": {"type": "template", "template": [{"type": "message", "role": "user",
               "content": {"type": "input_text", "text": "{{item.query}}"}}]},
               "target": {"type": "azure_ai_agent", "name": PINS["agent_name"], "version": PINS["agent_version"]}}}
    request["data_source"]["target"] = AzureAIAgentTargetParam(request["data_source"]["target"])
    request["data_source"] = TargetCompletionEvalRunDataSource(request["data_source"])
    reserve("run", request)
    run = client.evals.runs.create(**request)
    result = {"eval_id": request["eval_id"], "run_id": run.id, "request_id": getattr(run, "_request_id", None)}
    retain("run-id.json", result)
    return result


def rows_check(items):
    check_membership(items, expected={row["query"] for row in ORACLE.rows()[0]})


def sample_text(item):
    item = to_plain(item)
    require(isinstance(item, dict) and isinstance(item.get("sample"), dict), "target sample missing or malformed")
    return target_text(item)


def definition_check(definition, eval_id, criterion):
    require(definition.get("id") == eval_id, "registered evaluator definition/version drift")
    check_criteria(definition.get("testing_criteria"), [criterion])


def collect(client, identity, run):
    aggregate = sanitize({key: run.model_dump(mode="json").get(key) for key in
                          ("id", "eval_id", "status", "result_counts", "per_testing_criteria_results", "per_model_usage", "error", "report_url", "created_at", "name", "data_source")})
    failures = []
    partial = None
    try:
        collected = collect_rows(client, eval_id=identity["eval_id"], run_id=identity["run_id"], expected_count=3)
    except PartialRowsError as error:
        partial = error.partial
        collected = partial["rows"]
        failures.append(str(error))
    items = [sanitize({key: data.get(key) for key in
                       ("id", "eval_id", "run_id", "status", "datasource_item", "datasource_item_id", "results", "sample", "error")})
             for data in collected]
    complete = partial is None and len(items) == 3
    criterion = read_record("definition-intent.json")["request"]["testing_criteria"][0]
    try:
        require(aggregate["id"] == identity["run_id"] and aggregate["eval_id"] == identity["eval_id"], "foreign run identity")
        require(aggregate["status"] == "completed" and not aggregate.get("error"), "run incomplete or errored")
        definition = client.evals.retrieve(identity["eval_id"]).model_dump(mode="json")
        EVENTS.append({"operation": "evaluation_definition_readback", "definition": definition})
        definition_check(definition, identity["eval_id"], criterion)
        check_counts(aggregate.get("result_counts"), total=3)
        rows_check(items)
    except ValueError as error:
        complete = False
        failures.append(str(error))
    rows = []
    for item in items:
        data = item.get("datasource_item") or {}
        query = data.get("query")
        results = item.get("results") or []
        scored = passed = criterion_passed = False
        try:
            check_row(item, eval_id=identity["eval_id"], run_id=identity["run_id"])
            require(len(results) == 1, "exactly one criterion required")
            criterion_passed = check_criterion(results[0], name=criterion["name"], metric="coherence",
                                               evaluator_name=criterion.get("evaluator_name"),
                                               evaluator_version=criterion.get("evaluator_version"),
                                               strict_version=True)
            output = sample_text(item)
            passed = ORACLE.oracle(query, output, PINS)
            scored = True
        except ValueError as error:
            complete = False
            failures.append(str(error))
        rows.append({"id": item["id"], "query": query, "oracle_passed": passed, "scored": scored,
                     "criterion_passed": criterion_passed, "status": item["status"], "results": results})
    proof_passed = sum(row["oracle_passed"] for row in rows)
    accepted = run.status == "completed" and complete and proof_passed == 3 and all(row["scored"] for row in rows)
    return {"identity": identity, "aggregate": aggregate, "items": items, "rows": rows,
            "complete": complete, "has_next_page": partial is not None, "failures": failures,
            "next_cursor": partial["last_id"] if partial else None,
            "oracle_passed": proof_passed == 3, "criterion_passed": all(row["criterion_passed"] for row in rows) and len(rows) == 3,
            "proof_passed": proof_passed, "accepted": accepted, "settled": run.status in TERMINAL_RUN_STATUSES,
            "pins": PINS, "judge": read_record("selection.json")["judge"],
            "dataset": read_record("dataset.json"), "cost": "unknown"}


def reconcile(client):
    identity = read_record("run-id.json")
    polled = wait_for_run(client, eval_id=identity["eval_id"], run_id=identity["run_id"],
                          interval=10, attempts=30, seconds=600, on_event=EVENTS.append)
    if polled.settled:
        return collect(client, identity, polled.value)
    return {"identity": identity, "settled": False, "accepted": False, "status": polled.value.status,
            "next": "Read-only reconcile existing IDs; never resubmit."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["validate", "manifest-check", "preflight", "freeze", "upload", "inspect-upload", "closeout", "define", "submit", "reconcile", "verify"])
    parser.add_argument("--manifest")
    parser.add_argument("--manifest-sha256")
    parser.add_argument("--hosted-receipt")
    parser.add_argument("--hosted-sha256")
    arguments = parser.parse_args()
    if arguments.action != "validate" or arguments.manifest:
        if not arguments.manifest or not arguments.manifest_sha256:
            parser.error("live actions require pinned migration manifest; historical actions cannot replay")
        binding = configure_run(arguments.manifest, arguments.manifest_sha256, arguments.action,
                                arguments.hosted_receipt, arguments.hosted_sha256)
    started = time.monotonic()
    timestamp = utc_stamp()
    receipt = {"action": arguments.action, "utc": timestamp, "status": "failed",
               "decision_sha256": digest(RECORDS / "approved-decision.json")}
    exit_code = 1
    try:
        local = local_validate()
        if arguments.action in ("validate", "manifest-check"):
            receipt["result"] = local
        else:
            with ExitStack() as stack:
                project, client = clients(stack)
                if arguments.action == "preflight":
                    receipt["result"] = preflight(project)
                elif arguments.action == "freeze":
                    receipt["result"] = freeze(project)
                elif arguments.action == "upload":
                    receipt["result"] = upload(project)
                elif arguments.action == "inspect-upload":
                    receipt["result"] = inspect_upload(project)
                elif arguments.action == "closeout":
                    receipt["result"] = closeout(project)
                elif arguments.action == "define":
                    receipt["result"] = define(project, client)
                elif arguments.action == "submit":
                    receipt["result"] = submit(project, client)
                else:
                    receipt["result"] = reconcile(client)
                    if arguments.action == "verify":
                        require(receipt["result"]["accepted"], "live acceptance failed; inspect retained result")
        receipt["status"] = "complete"
        exit_code = 0
    except Exception as error:
        receipt["error"] = error_summary(error)
    receipt["seconds"] = time.monotonic() - started
    receipt["events"] = EVENTS
    receipt["source"] = {str(path.relative_to(ROOT)): digest(path) for path in
                         sorted(ROOT.rglob("*")) if path.is_file() and path.suffix in (".py", ".sh") and "__pycache__" not in path.parts}
    receipt["foundry_ops_source"] = {str(path.relative_to(REPO)): digest(path) for path in sorted(FOUNDRY_OPS.rglob("*.py"))}
    print(json.dumps(retain(timestamp + "-" + arguments.action + ".json", receipt)))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())