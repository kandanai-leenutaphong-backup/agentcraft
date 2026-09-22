"""Frozen scoring and native optimizer execution; no holdout access before selection."""

from contextlib import ExitStack
from datetime import datetime, timezone
import json
import csv
import io
import time
import uuid
import threading
import re
import asyncio
import ssl
import tarfile

import hosting
import prepare

SERIES = "native-mapping-v2"


def native_path(name):
    return prepare.EVIDENCE / (SERIES + "-" + name)


def observe_validation(live):
    deadline = time.monotonic() + 1800
    while True:
        selected = prepare.EVIDENCE / "candidate-validation-metrics.json"
        if selected.exists():
            result = json.loads(selected.read_text())
            return {"complete": result["complete_independent_validation"], "selected": result["selected"],
                    "candidates": [{"candidate_id": item["candidate_id"], "metrics": item["metrics"]} for item in result["candidates"]]}
        receipts = sorted(prepare.EVIDENCE.glob("*-candidate-validation.json"))
        if receipts:
            result = json.loads(receipts[-1].read_text())
            if result["status"] == "failed":
                return {"complete": False, "failure": result["result"], "receipt": prepare.pin(receipts[-1])}
        count = len(list(prepare.EVIDENCE.glob("cand_opt_21*-validation-row-[0-9][0-9][0-9].json")))
        print(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(), "completed_rows": count, "expected_rows": 90}), flush=True)
        if time.monotonic() >= deadline:
            return {"complete": False, "rows": count, "reason": "bounded observation ended; no inference repeated"}
        threading.Event().wait(20)


def observe_holdout(live):
    deadline = time.monotonic() + 1800
    while True:
        path = prepare.EVIDENCE / "final-holdout-result.json"
        if path.exists():
            result = json.loads(path.read_text())
            return {"complete": True, "accepted": result["accepted"],
                    "metrics": {role: item["metrics"] for role, item in result["results"].items()}}
        receipts = sorted(prepare.EVIDENCE.glob("*-final-holdout.json"))
        if receipts and json.loads(receipts[-1].read_text())["status"] == "failed":
            return {"complete": False, "failure": json.loads(receipts[-1].read_text())["result"]}
        count = len(list(prepare.EVIDENCE.glob("holdout-*-row-[0-9][0-9][0-9].json")))
        print(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(), "holdout_rows": count, "expected": 60}), flush=True)
        if time.monotonic() >= deadline:
            return {"complete": False, "rows": count, "reason": "observation ended; do not repeat unresolved holdout requests"}
        threading.Event().wait(20)


def baseline():
    frozen = prepare.EVIDENCE / "baseline-frozen.json"
    if frozen.exists():
        return json.loads(frozen.read_text())["deployment"]
    _, manifest = hosting.source_bytes()
    return json.loads((prepare.EVIDENCE / ("deploy-" + manifest["sha256"] + "-active.json")).read_text())


def invoke(client, deployed, query):
    clock = time.monotonic()
    response = client.responses.create(input=query, store=True, stream=False,
        extra_body={"agent_reference": {"type": "agent_reference", "name": deployed["agent"], "version": deployed["version"]}})
    return {"id": response.id, "status": response.status, "text": response.output_text,
            "metadata": response.metadata, "usage": response.usage.model_dump(mode="json") if response.usage else None,
            "seconds": time.monotonic() - clock}


def verify_identity(response, deployed, instructions_sha256=None):
    metadata = response["metadata"] or {}
    expected = {"agent_name": deployed["agent"], "agent_version": deployed["version"],
                "source_sha256": deployed["build"]["source"]["sha256"],
                "config_sha256": deployed["build"]["source"]["files"]["app/configuration.yaml"],
                "instructions_sha256": instructions_sha256 or prepare.sha((prepare.ROOT / "prompts/classifier.md").read_bytes())}
    if response["status"] != "completed" or any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("loaded runtime identity mismatch")


def runtime_canary(live):
    import httpx
    deployed = baseline()
    path = prepare.EVIDENCE / ("runtime-canary-v" + deployed["version"] + ".json")
    if path.exists():
        return json.loads(path.read_text())
    with ExitStack() as stack:
        project, client = live.connect(stack)
        client = stack.enter_context(project.get_openai_client(agent_name=deployed["agent"], max_retries=0, timeout=150))
        actual = project.agents.get_version(agent_name=deployed["agent"], agent_version=deployed["version"]).as_dict()
        if actual["definition"]["container_configuration"]["image"] != deployed["build"]["image"]:
            raise ValueError("baseline image drift")
        endpoint = live.TARGET["endpoint"] + "/agents/" + deployed["agent"] + "/endpoint/protocols/openai/responses?api-version=v1"
        anonymous = httpx.post(endpoint, json={"input": "unauthorized canary", "store": False}, timeout=30)
        if anonymous.status_code not in (401, 403):
            raise ValueError("anonymous invocation did not refuse")
        from azure.ai.projects.models import AgentOptimizationInlineDatasetInput
        dataset = AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/train.json").read_text()))
        query = dataset.dataset_items[0].query
        live.EVENTS.append({"operation": "runtime_canary", "agent": deployed["agent"], "version": deployed["version"],
                            "started_at": datetime.now(timezone.utc).isoformat(), "anonymous_status": anonymous.status_code})
        response = invoke(client, deployed, query)
        live.EVENTS.append({"operation": "runtime_response", "result": response})
        verify_identity(response, deployed)
        if response["text"].strip() not in prepare.LABELS:
            raise ValueError("runtime canary output not exact vocabulary")
        stored = client.responses.retrieve(response["id"])
        if stored.output_text != response["text"] or stored.metadata != response["metadata"]:
            raise ValueError("stored response readback mismatch")
        result = {"response": response, "anonymous_status": anonymous.status_code, "stored_readback": True,
                  "endpoint": endpoint, "scored": False, "input_partition": "train", "deployment": deployed}
        live.retain(path.name, result)
        return result


def baseline_route_canary(live):
    from azure.ai.projects.models import AgentOptimizationInlineDatasetInput
    deployed = baseline()
    dataset = AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/train.json").read_text()))
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        client = stack.enter_context(project.get_openai_client(agent_name=hosting.NAME, max_retries=0, timeout=150))
        response = invoke(client, deployed, dataset.dataset_items[0].query)
        live.EVENTS.append({"operation": "baseline_route_response", "response": response})
        verify_identity(response, deployed)
        return {"passed": True, "response": response, "input_partition": "train"}


def inspect_runtime(live):
    import httpx
    from azure.identity import AzureCliCredential
    with AzureCliCredential(tenant_id=live.TARGET["tenant"], process_timeout=30) as credential:
        response = httpx.get(live.TARGET["endpoint"] + "/agents/" + hosting.NAME + "/endpoint/sessions",
            params={"api-version": "v1"}, headers={"Authorization": "Bearer " + credential.get_token("https://ai.azure.com/.default").token},
            timeout=30)
    return {"status": response.status_code, "sessions": response.json()}


def runtime_logs(live):
    sessions = inspect_runtime(live)
    job = json.loads((prepare.EVIDENCE / "optimizer-job-created.json").read_text())
    candidates = [session for session in sessions["sessions"].get("data", []) if session.get("created_at", 0) >= job["created_at"]]
    if not candidates:
        return {"sessions_after_job": 0, "lines": []}
    session = max(candidates, key=lambda item: item["created_at"])
    lines = []
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        deadline = time.monotonic() + 20
        pending = ""
        try:
            for chunk in project.agents.get_session_log_stream(agent_name=hosting.NAME,
                agent_version=session["version_indicator"]["agent_version"], session_id=session["agent_session_id"],
                connection_timeout=10, read_timeout=5):
                pending += chunk.decode("utf-8", errors="replace")
                while "\n" in pending:
                    line, pending = pending.split("\n", 1)
                    if not line.startswith("data:"):
                        continue
                    try:
                        message = json.loads(line[5:]).get("message", "")
                    except (ValueError, AttributeError):
                        continue
                    if any(word in message for word in ("Error", "Exception", "denied", "failed", "optimization config", "429", "403", "401")):
                        message = re.sub(r"eyJ[A-Za-z0-9_.-]+", "[REDACTED]", message)
                        message = re.sub(r"(?i)(Bearer\s+|sig=|token=|secret=)[^\s&]+", r"\1[REDACTED]", message)
                        lines.append(message[:2000])
                if time.monotonic() >= deadline or len(lines) >= 50:
                    break
        except Exception as error:
            live.EVENTS.append({"operation": "bounded_log_stream_end", "error_type": type(error).__name__})
    return {"session": session, "sessions_after_job": len(candidates), "lines": lines,
            "coverage": "bounded exception/loader lines only; not full logs"}


def baseline_validation(live):
    from azure.ai.projects.models import AgentOptimizationInlineDatasetInput
    deployed = baseline()
    canary = json.loads((prepare.EVIDENCE / ("runtime-canary-v" + deployed["version"] + ".json")).read_text())
    if not canary["stored_readback"] or not json.loads(live.evaluator_path("canary-passed").read_text())["passed"]:
        raise ValueError("required live canaries missing")
    dataset = AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/validation.json").read_text()))
    frozen = {"constitution": prepare.pin(live.CONSTITUTION), "deployment": deployed,
              "model": "gpt-5.6-luna", "tools": [], "evaluator": prepare.pin(prepare.ROOT / "evaluator.py"),
              "dataset": prepare.pin(prepare.DATA / "manifest.json"), "comparison_lever": "instructions only",
              "selection": "macro-f1 descending, accuracy descending, invalid-rate ascending, candidate ID ascending",
              "holdout_scored": False}
    live.retain("baseline-frozen.json", frozen)
    rows = []
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        client = stack.enter_context(project.get_openai_client(agent_name=deployed["agent"], max_retries=0, timeout=150))
        for index, item in enumerate(dataset.dataset_items):
            path = prepare.EVIDENCE / ("baseline-validation-row-" + str(index).zfill(3) + ".json")
            if path.exists():
                rows.append(json.loads(path.read_text()))
                continue
            intent = path.with_suffix(".intent.json")
            if intent.exists():
                raise ValueError("unsettled validation row; reconcile stored response before repeating")
            live.retain(intent.name, {"index": index, "query_sha256": prepare.sha(item.query.encode()),
                                     "agent": deployed["agent"], "version": deployed["version"]})
            response = invoke(client, deployed, item.query)
            live.retain(path.with_suffix(".response.json").name, response)
            verify_identity(response, deployed)
            stored = client.responses.retrieve(response["id"])
            if stored.output_text != response["text"] or stored.metadata != response["metadata"]:
                raise ValueError("validation stored response drift")
            row = {"index": index, "query": item.query, "label": item.ground_truth, "prediction": response["text"],
                   "response": response, "stored_readback": True}
            live.retain(path.name, row)
            rows.append(row)
    metrics = prepare.EVALUATOR.score([row["label"] for row in rows], [row["prediction"] for row in rows])
    result = {"candidate_id": "frozen-hosted-baseline", "generation": None, "parent_id": None,
              "partition": "validation", "metrics": metrics, "rows": rows, "deployment": deployed}
    live.retain("baseline-validation.json", result)
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=("index", "label", "prediction", "seconds", "response_id"))
    writer.writeheader()
    for row in rows:
        writer.writerow({"index": row["index"], "label": row["label"], "prediction": row["prediction"],
                         "seconds": row["response"]["seconds"], "response_id": row["response"]["id"]})
    prepare.persist(prepare.EVIDENCE / "baseline-validation.csv", output.getvalue().encode())
    return {"metrics": metrics, "rows": len(rows), "holdout_scored": False}


def model_inventory(live):
    prepare.preflight()
    return hosting.command(live, ["cognitiveservices", "account", "list-models",
        "--subscription", hosting.TARGET["subscription_id"], "--resource-group", hosting.TARGET["model_resource_group"],
        "--name", hosting.TARGET["model_account"], "--query",
        "[?name=='gpt-5.4' || name=='gpt-5.1'].{name:name,version:version,skus:skus,capabilities:capabilities}"])


def provision_optimizer_model(live):
    prepare.preflight()
    name = "agentcraft-iris-optimizer-gpt54"
    base = ["--subscription", hosting.TARGET["subscription_id"], "--resource-group", hosting.TARGET["model_resource_group"],
            "--name", hosting.TARGET["model_account"]]
    existing = hosting.command(live, ["cognitiveservices", "account", "deployment", "list", *base])
    matches = [item for item in existing if item["name"] == name]
    expected = {"name": "gpt-5.4", "version": "2026-03-05", "format": "OpenAI"}
    if not matches:
        intent = prepare.EVIDENCE / "optimizer-model-intent.json"
        if intent.exists():
            raise ValueError("unresolved optimizer model intent; inspect provider operation")
        live.retain(intent.name, {"name": name, "model": expected, "sku": "GlobalStandard", "capacity": 100})
        hosting.command(live, ["cognitiveservices", "account", "deployment", "create", *base,
            "--deployment-name", name, "--model-name", expected["name"], "--model-version", expected["version"],
            "--model-format", "OpenAI", "--sku-name", "GlobalStandard", "--sku-capacity", "100"])
    actual = hosting.command(live, ["cognitiveservices", "account", "deployment", "show", *base, "--deployment-name", name])
    if any(actual["properties"]["model"].get(key) != value for key, value in expected.items()) or actual["properties"]["provisioningState"] != "Succeeded":
        raise ValueError("optimizer model identity/readiness mismatch")
    live.retain("optimizer-model-ready.json", actual)
    return actual


def optimizer_model_canary(live):
    from azure.identity import AzureCliCredential
    import httpx
    from llm_interface import Limits, connect
    prepare.preflight()
    deployment = json.loads((prepare.EVIDENCE / "optimizer-model-ready.json").read_text())

    async def run():
        with AzureCliCredential(tenant_id=live.TARGET["tenant"], process_timeout=30) as credential:
            async with httpx.AsyncHTTPTransport(verify=ssl.create_default_context(), trust_env=False, retries=0) as transport, connect(
                live.TARGET["endpoint"], deployment["name"], credential=credential, allow_model_calls=True,
                transport=transport, allowed_tools=(), limits=Limits(max_model_calls=1, max_tool_calls=1,
                    max_output_tokens=1024, timeout_seconds=120, max_concurrency=1),
            ) as model:
                response = await model.agent(name="optimizer-model-canary", instructions="Return exactly OK.", tools=()).run("Connection canary.")
                return {"text": response.text, "model": deployment["name"], "passed": response.text.strip() == "OK"}

    result = asyncio.run(run())
    live.retain("optimizer-model-canary.json", result)
    if not result["passed"]:
        raise ValueError("optimizer model canary output failed")
    return result


def optimization_request(live):
    from azure.ai.projects.models import (AgentOptimizationJob, AgentOptimizationJobInputs,
        AgentOptimizationInlineDatasetInput, AgentOptimizationEvaluatorRef, AgentOptimizationOptions, OptimizedAgentIdentifier)
    deployed = baseline()
    evaluator = json.loads(live.evaluator_path("registered").read_text())
    model = json.loads((prepare.EVIDENCE / "optimizer-model-ready.json").read_text())
    if not json.loads(live.evaluator_path("mapped-canary-passed").read_text())["passed"]:
        raise ValueError("native-shaped evaluator canary required")
    if not (prepare.EVIDENCE / "baseline-validation.json").exists():
        raise ValueError("complete baseline required before optimizer")
    return AgentOptimizationJob(inputs=AgentOptimizationJobInputs(
        agent=OptimizedAgentIdentifier(agent_name=deployed["agent"], agent_version=deployed["version"]),
        train_dataset=AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/train.json").read_text())),
        validation_dataset=AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/validation.json").read_text())),
        evaluators=[AgentOptimizationEvaluatorRef(name=evaluator["name"], version=evaluator["version"])],
        options=AgentOptimizationOptions(max_candidates=3, max_stalls=5, eval_model="gpt-5.6-luna",
            optimization_model=model["name"], optimization_config={
                "system_prompt": (prepare.ROOT / "prompts/classifier.md").read_text()})))


def optimize(live, retry_rejected=False):
    request = optimization_request(live)
    operation_id = str(uuid.uuid4())
    intent = native_path("optimizer-job-default-turn-intent.json")
    if intent.exists() and not retry_rejected:
        raise ValueError("existing optimizer intent; reconcile rather than resubmit")
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        if retry_rejected:
            prior = json.loads(intent.read_text())
            operation_id = prior["operation_id"]
            jobs = [job.as_dict() for job in project.beta.agents.list_optimization_jobs(agent_name=hosting.NAME, limit=100)]
            live.EVENTS.append({"operation": "reconcile_before_rejected_retry", "jobs": jobs})
            if jobs or prior["request"] != request.as_dict():
                raise ValueError("existing job or changed request; explicit reconciliation required")
        else:
            live.retain(intent.name, {"operation_id": operation_id, "request": request.as_dict(),
                        "constitution": prepare.pin(live.CONSTITUTION), "holdout_uploaded": False})
        poller = project.beta.agents.begin_create_optimization_job(job=request, operation_id=operation_id, polling=False)
        details = poller.details
        identity = {"operation_id": operation_id, "job_id": details.get("job_id") if isinstance(details, dict) else getattr(details, "job_id", None)}
        live.retain(native_path("optimizer-job-identity.json").name, identity)
        if not identity["job_id"]:
            raise ValueError("native job accepted but job identity missing; reconcile operation ID")
        actual = project.beta.agents.get_optimization_job(identity["job_id"]).as_dict()
        live.retain(native_path("optimizer-job-created.json").name, actual)
        return {"identity": identity, "job": actual}


def optimizer_readback(live):
    identity = json.loads(native_path("optimizer-job-identity.json").read_text())
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        return project.beta.agents.get_optimization_job(identity["job_id"]).as_dict()


def optimizer_operation(live):
    from azure.ai.projects.models import AgentOptimizationJob
    from azure.core.rest import HttpRequest
    from urllib.parse import urlsplit, urljoin
    intent = json.loads(native_path("optimizer-job-default-turn-intent.json").read_text())
    identity = json.loads(native_path("optimizer-job-identity.json").read_text())
    observed = {}

    def capture(response):
        actual = response.http_response
        observed.update({"status": actual.status_code, "operation_location": actual.headers.get("Operation-Location"),
                         "location": actual.headers.get("Location"), "request_id": actual.headers.get("x-ms-request-id")})

    with ExitStack() as stack:
        project, _ = live.connect(stack)
        poller = project.beta.agents.begin_create_optimization_job(job=AgentOptimizationJob(intent["request"]),
            operation_id=intent["operation_id"], polling=False, raw_response_hook=capture)
        details = poller.details
        returned = details.get("job_id") if isinstance(details, dict) else getattr(details, "job_id", None)
        if returned != identity["job_id"]:
            live.EVENTS.append({"operation": "idempotency_mismatch", "returned_job_id": returned, "expected": identity["job_id"]})
            raise ValueError("native idempotency returned a different job; reconcile both")
        location = observed.get("operation_location")
        live.EVENTS.append({"operation": "native_operation_headers", "observed": dict(observed)})
        if location:
            location = urljoin(live.TARGET["endpoint"] + "/", location)
            parsed = urlsplit(location)
            target = urlsplit(live.TARGET["endpoint"])
            internal_path = ("/agents-optimization/v1.0/subscriptions/" + hosting.TARGET["subscription_id"]
                + "/resourceGroups/" + hosting.TARGET["model_resource_group"]
                + "/providers/Microsoft.MachineLearningServices/workspaces/" + hosting.TARGET["model_account"]
                + "@" + target.path.rsplit("/", 1)[-1] + "@AML/agent_optimization_jobs/" + identity["job_id"])
            if parsed.scheme != "https" or parsed.netloc != target.netloc or not (
                parsed.path.startswith(target.path + "/") or parsed.path == internal_path):
                raise ValueError("foreign operation status endpoint refused")
            response = project.send_request(HttpRequest("GET", location))
            observed["operation_status"] = {"status": response.status_code, "body": response.json()}
        return {"identity": identity, "idempotent_reconciliation": True, "observed": observed}


def optimizer_diagnostics(live):
    from azure.core.rest import HttpRequest
    from urllib.parse import urlsplit, urlunsplit
    identity = json.loads(native_path("optimizer-job-identity.json").read_text())
    observed = {}

    def capture(response):
        observed["url"] = response.http_response.request.url

    with ExitStack() as stack:
        project, client = live.connect(stack)
        job = project.beta.agents.get_optimization_job(identity["job_id"], raw_response_hook=capture).as_dict()
        parts = urlsplit(observed["url"])
        candidate_url = urlunsplit((parts.scheme, parts.netloc, parts.path + "/candidates", parts.query, ""))
        response = project.send_request(HttpRequest("GET", candidate_url))
        candidates = {"status": response.status_code, "body": response.json()}
        evaluations = [{"id": item.id, "name": item.name, "created_at": item.created_at} for item in client.evals.list(limit=30).data]
        return {"job": job, "job_url": observed["url"], "candidates": candidates, "recent_evaluations": evaluations}


def optimizer_wait(live):
    identity = json.loads(native_path("optimizer-job-identity.json").read_text())
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        deadline = time.monotonic() + 3600
        previous = None
        while True:
            job = project.beta.agents.get_optimization_job(identity["job_id"]).as_dict()
            state = {"status": job.get("status"), "progress": job.get("progress"), "error": job.get("error")}
            if state != previous:
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                live.retain(stamp + "-native-progress.json", job)
                previous = state
            print(json.dumps({"observed_at": datetime.now(timezone.utc).isoformat(), "job_id": identity["job_id"], **state}), flush=True)
            if job.get("status") in ("succeeded", "failed", "canceled", "cancelled", "completed"):
                live.retain(native_path("optimizer-job-terminal.json").name, job)
                return job
            if time.monotonic() >= deadline:
                return {"settled": False, "job": job, "reason": "bounded observation ended; job retained, no resubmission"}
            threading.Event().wait(20)


def collect_candidates(live):
    from azure.core.rest import HttpRequest
    identity = json.loads(native_path("optimizer-job-identity.json").read_text())
    with ExitStack() as stack:
        project, client = live.connect(stack)
        job = project.beta.agents.get_optimization_job(identity["job_id"]).as_dict()
        if job.get("status") not in ("succeeded", "failed", "completed"):
            raise ValueError("candidate collection requires terminal native job")
        live.retain(native_path("optimizer-job-terminal.json").name, job)
        base = live.TARGET["endpoint"] + "/agent_optimization_jobs/" + identity["job_id"]
        response = project.send_request(HttpRequest("GET", base + "/candidates?api-version=v1"))
        if response.status_code != 200:
            raise ValueError("native candidate list unavailable")
        listing = response.json()
        live.retain(native_path("native-candidates.json").name, listing)
        if listing.get("has_more"):
            raise ValueError("candidate pagination requires continuation before completeness claim")
        rows = []
        for candidate in listing.get("data", []):
            candidate_id = candidate.get("candidate_id") or candidate.get("id")
            if not isinstance(candidate_id, str) or not candidate_id.replace("_", "").replace("-", "").isalnum():
                raise ValueError("invalid candidate identity")
            config_response = project.send_request(HttpRequest("GET", base + "/candidates/" + candidate_id + "/config?api-version=2025-11-15-preview"))
            if config_response.status_code != 200:
                raise ValueError("candidate config retrieval failed")
            config = config_response.json()
            live.retain(candidate_id + "-config.json", config)
            item = {"candidate_id": candidate_id, "generation": None, "parent_id": None,
                    "native": candidate, "config": config, "independent_metrics": None}
            eval_id, run_id = candidate.get("eval_id"), candidate.get("eval_run_id")
            if eval_id and run_id:
                run = client.evals.runs.retrieve(eval_id=eval_id, run_id=run_id)
                outputs = []
                for output in client.evals.runs.output_items.list(eval_id=eval_id, run_id=run_id, limit=100):
                    value = output.model_dump(mode="json")
                    retained = {key: value.get(key) for key in ("id", "status", "datasource_item", "results", "error")}
                    sample = value.get("sample") or {}
                    retained["sample"] = {"output_text": sample.get("output_text"),
                        "output": [message for message in sample.get("output", [])
                                   if message.get("role") == "assistant" and isinstance(message.get("content"), str)],
                        "usage": sample.get("usage")}
                    outputs.append(retained)
                item["evaluation"] = {"id": eval_id, "run_id": run_id, "status": run.status,
                                      "report_url": run.report_url, "result_counts": run.result_counts.model_dump(mode="json"), "rows": outputs}
            live.retain(candidate_id + "-evidence.json", item)
            rows.append(item)
        live.retain(native_path("candidate-metrics.json").name, {"job_id": identity["job_id"], "candidates": rows,
                    "complete_independent_validation": False, "holdout_scored": False})
        return {"job_id": identity["job_id"], "candidate_count": len(rows), "job_status": job["status"]}


def select_candidate(metrics):
    if not metrics or any(item["metrics"].get("n") != 30 for item in metrics):
        raise ValueError("every candidate requires complete thirty-row validation")
    identifiers = [item["candidate_id"] for item in metrics]
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("duplicate candidate identities")
    return sorted(metrics, key=lambda item: (-item["metrics"]["macro_f1"], -item["metrics"]["accuracy"],
                                            item["metrics"]["invalid_rate"], item["candidate_id"]))[0]


def native_row_metrics(live):
    from azure.ai.projects.models import AgentOptimizationInlineDatasetInput
    dataset = AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/validation.json").read_text()))
    expected = {item.query: item.ground_truth for item in dataset.dataset_items}
    collection = json.loads(native_path("candidate-metrics.json").read_text())
    summaries = []
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=("candidate_id", "row_index", "query", "label", "prediction", "correct", "native_score"))
    writer.writeheader()
    for candidate in collection["candidates"]:
        rows = candidate["evaluation"]["rows"]
        seen = set()
        labels, predictions = [], []
        for index, row in enumerate(rows):
            item = row["datasource_item"]
            query = item["query"]
            if query in seen or expected.get(query) != item.get("ground_truth"):
                raise ValueError("native validation row membership/label mismatch")
            seen.add(query)
            prediction = item.get("sample.output_text")
            labels.append(item["ground_truth"])
            predictions.append(prediction)
            writer.writerow({"candidate_id": candidate["candidate_id"], "row_index": index, "query": query,
                "label": item["ground_truth"], "prediction": prediction,
                "correct": isinstance(prediction, str) and prediction.strip() == item["ground_truth"],
                "native_score": row["results"][0].get("score") if row.get("results") else None})
        if seen != set(expected):
            raise ValueError("native validation coverage incomplete")
        summaries.append({"candidate_id": candidate["candidate_id"], "generation": None, "parent_id": None,
            "metrics": prepare.EVALUATOR.score(labels, predictions), "native_avg_score": candidate["native"].get("avg_score"),
            "report_url": candidate["evaluation"].get("report_url"), "origin": "recomputed from retained native evaluation rows; not fresh inference"})
    result = {"job_id": collection["job_id"], "candidates": summaries, "membership_verified": True}
    live.retain(native_path("recomputed-metrics.json").name, result)
    prepare.persist(native_path("native-rows.csv"), output.getvalue().encode())
    return result


def candidate_validation(live):
    from azure.ai.projects.models import AgentOptimizationInlineDatasetInput
    from azure.ai.agentserver.optimization import CandidateConfig, OptimizationConfig
    import sys
    sys.path.insert(0, str(prepare.ROOT))
    from composition import apply_optimization, load_spec
    collected = json.loads(native_path("candidate-metrics.json").read_text())
    if not collected["candidates"]:
        raise ValueError("native job returned no candidate configurations")
    dataset = AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/validation.json").read_text()))
    scored = []
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        for candidate in collected["candidates"]:
            candidate_id = candidate["candidate_id"]
            config = candidate["config"]
            parsed = CandidateConfig.from_dict(config)
            native = OptimizationConfig(instructions=parsed.instructions, model=parsed.model,
                temperature=parsed.temperature, skills=parsed.skills, tool_definitions=parsed.tool_definitions)
            spec = apply_optimization(load_spec(), native)
            prompt_hash = prepare.sha(spec.instructions.encode())
            version_path = prepare.EVIDENCE / (candidate_id + "-validation-version.json")
            if version_path.exists():
                deployed = json.loads(version_path.read_text())
            else:
                intent = prepare.EVIDENCE / (candidate_id + "-validation-version-intent.json")
                if intent.exists():
                    raise ValueError("unresolved candidate deployment; reconcile prior version")
                deployed = baseline()
                definition = dict(deployed["actual"]["definition"])
                definition.pop("container_protocol_versions", None)
                definition["environment_variables"] = {"OPTIMIZATION_CONFIG": json.dumps(config, sort_keys=True)}
                metadata = {"experiment": hosting.NAME, "source_sha256": deployed["build"]["source"]["sha256"],
                            "config_sha256": deployed["build"]["source"]["files"]["app/configuration.yaml"],
                            "native_candidate_id": candidate_id, "instructions_sha256": prompt_hash}
                live.retain(intent.name, {"definition": definition, "metadata": metadata})
                actual = project.agents.create_version(agent_name=hosting.NAME,
                    body={"definition": definition, "metadata": metadata}).as_dict()
                deployed = {**deployed, "version": str(actual["version"]), "actual": actual}
                live.retain(version_path.name, deployed)
            deadline = time.monotonic() + 300
            while True:
                actual = project.agents.get_version(agent_name=hosting.NAME, agent_version=deployed["version"]).as_dict()
                if actual.get("status") == "active":
                    break
                if actual.get("status") not in ("creating", "pending") or time.monotonic() >= deadline:
                    raise ValueError("candidate hosted version unavailable")
                threading.Event().wait(5)
            if actual["definition"]["environment_variables"]["OPTIMIZATION_CONFIG"] != json.dumps(config, sort_keys=True):
                raise ValueError("candidate configured bytes mismatch")
            rows = []
            client = stack.enter_context(project.get_openai_client(agent_name=hosting.NAME, max_retries=0, timeout=150))
            for index, item in enumerate(dataset.dataset_items):
                path = prepare.EVIDENCE / (candidate_id + "-validation-row-" + str(index).zfill(3) + ".json")
                if path.exists():
                    rows.append(json.loads(path.read_text()))
                    continue
                intent = path.with_suffix(".intent.json")
                if intent.exists():
                    raise ValueError("unresolved candidate row; reconcile stored response")
                live.retain(intent.name, {"candidate_id": candidate_id, "version": deployed["version"], "index": index})
                response = invoke(client, deployed, item.query)
                live.retain(path.with_suffix(".response.json").name, response)
                verify_identity(response, deployed, prompt_hash)
                stored = client.responses.retrieve(response["id"])
                if stored.output_text != response["text"] or stored.metadata != response["metadata"]:
                    raise ValueError("candidate stored response mismatch")
                row = {"index": index, "label": item.ground_truth, "query": item.query,
                       "prediction": response["text"], "response": response, "stored_readback": True}
                live.retain(path.name, row)
                rows.append(row)
            metrics = prepare.EVALUATOR.score([row["label"] for row in rows], [row["prediction"] for row in rows])
            result = {"candidate_id": candidate_id, "generation": None, "parent_id": None, "metrics": metrics,
                      "rows": rows, "deployment": deployed, "instructions_sha256": prompt_hash,
                      "native": candidate["native"], "config": config}
            live.retain(candidate_id + "-validation.json", result)
            scored.append(result)
    selected = select_candidate(scored)
    live.retain("selected-candidate.json", selected)
    live.retain("candidate-validation-metrics.json", {"candidates": scored, "selected": selected["candidate_id"],
                "holdout_scored": False, "complete_independent_validation": True})
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=("candidate_id", "generation", "parent_id", "n", "accuracy", "macro_f1", "invalid_rate", "native_avg_score", "eval_id", "eval_run_id"))
    writer.writeheader()
    for candidate in scored:
        writer.writerow({"candidate_id": candidate["candidate_id"], "generation": None, "parent_id": None,
            **{key: candidate["metrics"][key] for key in ("n", "accuracy", "macro_f1", "invalid_rate")},
            "native_avg_score": candidate["native"].get("avg_score"), "eval_id": candidate["native"].get("eval_id"),
            "eval_run_id": candidate["native"].get("eval_run_id")})
    prepare.persist(prepare.EVIDENCE / "candidate-validation-metrics.csv", output.getvalue().encode())
    return {"selected": selected["candidate_id"], "metrics": selected["metrics"], "candidates": len(scored), "holdout_scored": False}


def demonstration_candidate(comparison, baseline_id):
    if not comparison.get("complete_independent_validation"):
        raise ValueError("complete independent validation required")
    candidates = comparison["candidates"]
    select_candidate(candidates)
    return select_candidate([item for item in candidates if item["candidate_id"] != baseline_id])


def demonstration_decision(live):
    handoff_path = prepare.EVIDENCE / "20260922T123104615533Z-live-handoff.json"
    if prepare.sha(handoff_path.read_bytes()) != "e5b925e557cc0942f3da09e7dfc93517de9fd3f8bd0da369171a714e0411348e":
        raise ValueError("parent handoff pin mismatch")
    comparison = json.loads((prepare.EVIDENCE / "candidate-validation-metrics.json").read_text())
    terminal = json.loads(native_path("optimizer-job-terminal.json").read_text())
    baseline_id = terminal["result"]["baseline"]
    selected = demonstration_candidate(comparison, baseline_id)
    baseline_metrics = next(item["metrics"] for item in comparison["candidates"] if item["candidate_id"] == baseline_id)
    config_path = prepare.EVIDENCE / (selected["candidate_id"] + "-config.json")
    config = json.loads(config_path.read_text())
    if config != selected["config"] or prepare.sha(config["instructions"].encode()) != selected["instructions_sha256"]:
        raise ValueError("native candidate bytes drift")
    if selected["instructions_sha256"] == prepare.sha((prepare.ROOT / "prompts/classifier.md").read_bytes()):
        raise ValueError("demonstration requires changed native instructions")
    restore = json.loads((prepare.EVIDENCE / "final-holdout-result.json").read_text())["results"]["chosen"]["deployment"]
    if restore["version"] != "5" or restore["agent"] != hosting.NAME:
        raise ValueError("baseline v5 restore target mismatch")
    preserved = set(prepare.EVIDENCE.glob("*holdout*"))
    preserved.update(prepare.EVIDENCE / name for name in ("selected-candidate.json", "candidate-validation-metrics.json",
        "candidate-validation-metrics.csv", "final-verdict-correction.json", "final-version-canaries.json"))
    preserved.update((prepare.ROOT / ".agent_configs").rglob("*"))
    result = {"purpose": "DEMONSTRATION; not production promotion or best candidate", "parent_assignment":
        "2026-09-22 explicit bounded live decision under validated rev2: victory is running native-optimized changed config plus metrics, not guaranteed improvement. Select generated candidate by existing validation only; no optimizer run or holdout scoring. Thresholds unchanged.",
        "constitution": prepare.pin(live.CONSTITUTION), "parent_handoff": prepare.pin(handoff_path),
        "candidate_id": selected["candidate_id"], "native_config": prepare.pin(config_path),
        "instructions_sha256": selected["instructions_sha256"], "job_id": terminal["id"],
        "selection_rule": "generated candidates only; descending validation macro_f1, accuracy; ascending invalid_rate, candidate_id",
        "validation": selected["metrics"], "baseline_validation": baseline_metrics,
        "verdict": "regressed", "improvement_claim": False, "generalization_claim": False,
        "candidate_holdout": "not evaluated; historical baseline and same-config holdout 30/30 already disclosed",
        "generation": None, "parent_id": None, "restore": restore,
        "preserved": [prepare.pin(path) for path in sorted(preserved) if path.is_file()]}
    live.retain("demonstration-decision.json", result)
    return result


def demonstration_context():
    decision = json.loads((prepare.EVIDENCE / "demonstration-decision.json").read_text())
    for reference in [decision["native_config"], decision["constitution"], decision["parent_handoff"], *decision["preserved"]]:
        path = prepare.REPO / reference["path"]
        if prepare.sha(path.read_bytes()) != reference["sha256"]:
            raise ValueError("demonstration pinned evidence drift")
    comparison = json.loads((prepare.EVIDENCE / "candidate-validation-metrics.json").read_text())
    terminal = json.loads(native_path("optimizer-job-terminal.json").read_text())
    selected = demonstration_candidate(comparison, terminal["result"]["baseline"])
    with (prepare.EVIDENCE / "candidate-validation-metrics.csv").open(newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != len(comparison["candidates"]) or {row["candidate_id"] for row in rows} != {item["candidate_id"] for item in comparison["candidates"]}:
        raise ValueError("metrics CSV candidate coverage mismatch")
    for item in comparison["candidates"]:
        row = next(row for row in rows if row["candidate_id"] == item["candidate_id"])
        if any(row[key] != item["native"][key] for key in ("eval_id", "eval_run_id")) or any(float(row[key]) != item["metrics"][key] for key in ("n", "accuracy", "macro_f1", "invalid_rate")):
            raise ValueError("metrics CSV independent values or evaluation identity mismatch")
    if selected["candidate_id"] != decision["candidate_id"] or selected["instructions_sha256"] != decision["instructions_sha256"]:
        raise ValueError("demonstration validation selection drift")
    if prepare.sha(selected["config"]["instructions"].encode()) != decision["instructions_sha256"]:
        raise ValueError("demonstration native instructions drift")
    return decision, selected


def demonstration_verify(live):
    import httpx
    from azure.ai.projects.models import AgentOptimizationInlineDatasetInput
    decision, candidate = demonstration_context()
    _, manifest = hosting.source_bytes(demonstration=True)
    deployed = json.loads((prepare.EVIDENCE / ("deploy-" + manifest["sha256"] + "-active.json")).read_text())
    endpoint = live.TARGET["endpoint"] + "/agents/" + hosting.NAME + "/endpoint/protocols/openai/responses?api-version=v1"
    anonymous = httpx.post(endpoint, json={"input": "anonymous-demonstration", "store": False}, timeout=30)
    if anonymous.status_code not in (401, 403):
        raise ValueError("demonstration anonymous refusal failed")
    dataset = AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/train.json").read_text()))
    responses = []
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        actual = project.agents.get_version(agent_name=hosting.NAME, agent_version=deployed["version"]).as_dict()
        latest = project.agents.get(hosting.NAME).as_dict()["versions"]["latest"]
        restore = project.agents.get_version(agent_name=hosting.NAME, agent_version="5").as_dict()
        if actual.get("status") != "active" or str(latest["version"]) != deployed["version"] or actual["definition"]["container_configuration"]["image"] != deployed["build"]["image"]:
            raise ValueError("demonstration active latest image mismatch")
        if restore["definition"] != decision["restore"]["actual"]["definition"] or restore.get("status") != "active":
            raise ValueError("baseline restore target drift")
        client = stack.enter_context(project.get_openai_client(agent_name=hosting.NAME, max_retries=0, timeout=150))
        for index in (0, 1, 2):
            path = prepare.EVIDENCE / ("demonstration-v" + deployed["version"] + "-train-" + str(index) + ".json")
            if path.exists():
                response = json.loads(path.read_text())
            else:
                intent = path.with_suffix(".intent.json")
                if intent.exists():
                    raise ValueError("unresolved demonstration inference; reconcile stored response")
                live.retain(intent.name, {"version": deployed["version"], "train_index": index})
                response = invoke(client, deployed, dataset.dataset_items[index].query)
                live.retain(path.name, response)
            verify_identity(response, deployed, candidate["instructions_sha256"])
            if response["metadata"].get("applied_candidate_id") != candidate["candidate_id"] or response["metadata"].get("native_config_sha256") != decision["native_config"]["sha256"]:
                raise ValueError("loaded native candidate identity mismatch")
            if response["text"].strip() not in prepare.LABELS:
                raise ValueError("demonstration invalid label")
            stored = client.responses.retrieve(response["id"])
            if stored.output_text != response["text"] or stored.metadata != response["metadata"]:
                raise ValueError("demonstration stored response mismatch")
            responses.append(response)
        job = project.beta.agents.get_optimization_job(decision["job_id"]).as_dict()
        if job.get("status") not in ("succeeded", "failed", "completed"):
            raise ValueError("native optimization operation unsettled")
    protected = prepare.preflight()
    demonstration_context()
    result = {"status": "complete", "purpose": decision["purpose"], "endpoint": endpoint,
        "decision": prepare.pin(prepare.EVIDENCE / "demonstration-decision.json"), "deployment": deployed,
        "actual": actual, "restore_actual": restore, "candidate_id": candidate["candidate_id"],
        "native_config": decision["native_config"], "instructions_sha256": candidate["instructions_sha256"],
        "responses": responses, "stored_readback": True, "anonymous_status": anonymous.status_code,
        "input_partition": "train", "scored": False, "candidate_holdout": "not evaluated",
        "validation": decision["validation"], "baseline_validation": decision["baseline_validation"],
        "verdict": "regressed", "improvement_claim": False, "generalization_claim": False,
        "metrics": [prepare.pin(prepare.EVIDENCE / name) for name in ("candidate-validation-metrics.json", "candidate-validation-metrics.csv", SERIES + "-candidate-metrics.json", SERIES + "-recomputed-metrics.json", SERIES + "-native-rows.csv")],
        "metrics_source": "Foundry candidate eval_id/eval_run_id and report_url locate native evaluation rows; optimization job/candidate APIs locate configs and composite search scores. Independent hosted validation is local frozen-scorer CSV/JSON, not the native composite metric.",
        "generation_semantics": "Baseline plus two returned generated candidates; generation and parent IDs unknown/null. Candidate order is not lineage or every attempted generation.",
        "native_job": job, "protected_preflight": protected, "historical_records_unchanged": True,
        "resources": "retained; no teardown, no new optimizer run; baseline v5 restore retained",
        "cost": "unknown", "effective_effort": "unverified"}
    live.retain("demonstration-result.json", result)
    return result


def demonstration_handoff(live):
    decision, candidate = demonstration_context()
    result_path = prepare.EVIDENCE / "demonstration-result.json"
    result = json.loads(result_path.read_text())
    files, manifest = hosting.source_bytes(demonstration=True)
    if result["deployment"]["build"]["source"] != manifest:
        raise ValueError("verified demonstration image/source drift")
    checks = prepare.tests()
    receipts = sorted(prepare.EVIDENCE.glob("*-demonstration-*.json"))
    actions = [{"receipt": prepare.pin(path), **{key: value for key, value in json.loads(path.read_text()).items()
               if key in ("action", "status", "started_at", "finished_at", "seconds")}} for path in receipts]
    sources = [prepare.ROOT / name for name in ("README.md", "main.py", "composition.py", "configuration.yaml", "evaluator.py", "prompts/classifier.md")]
    sources.extend(path for path in (prepare.ROOT / "deploy").iterdir() if path.is_file())
    sources.extend((prepare.ROOT / "tests").glob("*.py"))
    sources.extend([live.CONSTITUTION, prepare.REPO / "README.md", prepare.REPO / "specs/20260922_FOUNDRY_AGENT_OPTIMIZATION.md"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = prepare.EVIDENCE / (stamp + "-demonstration-source.tar.gz")
    with tarfile.open(archive, "x:gz") as bundle:
        for path in sorted(set(sources)):
            if path.is_symlink():
                raise ValueError("source snapshot symlink refused")
            bundle.add(path, arcname=str(path.relative_to(prepare.REPO)), recursive=False)
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if bundle.extractfile(member).read() != (prepare.REPO / member.name).read_bytes():
                raise ValueError("source archive readback drift")
    outcome = {"status": "complete", "objective": "Running hosted native-generated changed configuration plus candidate metrics; no guaranteed improvement",
        "stage": "demonstration verified", "next_transition": "return assigned checkpoint; no follow-on experiment",
        "constitution": decision["constitution"], "candidate_id": candidate["candidate_id"],
        "native_config": decision["native_config"], "instructions_sha256": candidate["instructions_sha256"],
        "endpoint": result["endpoint"], "version": result["deployment"]["version"], "image": result["deployment"]["build"]["image"],
        "source_sha256": manifest["sha256"], "source_archive": prepare.pin(archive),
        "image_archive": result["deployment"]["build"]["archive"], "result": prepare.pin(result_path),
        "decision": prepare.pin(prepare.EVIDENCE / "demonstration-decision.json"), "parent_handoff": decision["parent_handoff"],
        "checks": checks, "actions": actions, "metrics": result["metrics"], "metrics_source": result["metrics_source"],
        "generation_semantics": result["generation_semantics"], "verdict": "development validation regression",
        "candidate_holdout": "not evaluated", "improvement_claim": False, "generalization_claim": False,
        "restore": {"agent": hosting.NAME, "version": "5", "image": decision["restore"]["build"]["image"]},
        "historical_records_unchanged": True, "provider_operations": "build succeeded, deployment active, optimizer terminal; none pending from this assignment",
        "workers": "none dispatched", "resources": "retained; protected hosted v3 unchanged; no teardown",
        "failures_deviations": ["jq unavailable; used repository file tools instead", "architecture overview absent; used existing owning implementation/runbook", "two mistaken skill-path reads failed; correct supplied skill subsequently read"],
        "capture_gaps": ["Action receipts measure commands, not total engineering effort or every editor tool duration", "Cost and effective runtime effort unknown", "No new generated-candidate holdout, production promotion, browser or human interactive sign-in claim", "Authoritative overseer publication outside worker scope"],
        "smallest_next_decision": "Accept bounded capability demonstration; quality improvement remains unproven"}
    live.retain(stamp + "-demonstration-handoff.json", outcome)
    return outcome


def apply_selected(live):
    selected = json.loads((prepare.EVIDENCE / "selected-candidate.json").read_text())
    comparison = json.loads((prepare.EVIDENCE / "candidate-validation-metrics.json").read_text())
    if not comparison["complete_independent_validation"] or comparison["selected"] != selected["candidate_id"]:
        raise ValueError("complete frozen selection required")
    instructions = selected["config"]["instructions"].encode()
    if prepare.sha(instructions) != selected["instructions_sha256"]:
        raise ValueError("selected native config digest mismatch")
    destination = prepare.ROOT / ".agent_configs"
    prepare.persist(destination / "baseline/instructions.md", instructions)
    prepare.persist(destination / "baseline/metadata.yaml", b"model: gpt-5.6-luna\ninstruction_file: instructions.md\n")
    provenance = {"candidate_id": selected["candidate_id"], "instructions_sha256": selected["instructions_sha256"],
                  "native_config": prepare.pin(prepare.EVIDENCE / (selected["candidate_id"] + "-config.json")),
                  "job": json.loads(native_path("optimizer-job-identity.json").read_text())}
    prepare.persist(destination / "selection.json", prepare.encoded(provenance))
    return {"applied": provenance, "next": "build then deploy exact selected source before final holdout"}


def final_holdout(live):
    selected = json.loads((prepare.EVIDENCE / "selected-candidate.json").read_text())
    selection = json.loads((prepare.ROOT / ".agent_configs/selection.json").read_text())
    if selection["candidate_id"] != selected["candidate_id"]:
        raise ValueError("selected config not applied")
    _, manifest = hosting.source_bytes()
    chosen = json.loads((prepare.EVIDENCE / ("deploy-" + manifest["sha256"] + "-active.json")).read_text())
    frozen = baseline()
    canaries = json.loads((prepare.EVIDENCE / "final-version-canaries.json").read_text())
    if canaries["baseline_version"] != frozen["version"] or canaries["chosen_version"] != chosen["version"] or not canaries["passed"]:
        raise ValueError("final version-routing canaries required before holdout")
    policy = {"selected": selected["candidate_id"], "baseline_version": frozen["version"],
              "chosen_version": chosen["version"], "holdout": prepare.pin(prepare.DATA / "private/holdout.json"),
              "no_reselection": True}
    live.retain("final-holdout-frozen.json", policy)
    holdout = json.loads((prepare.DATA / "private/holdout.json").read_text())
    results = {}
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        for role, deployed, prompt_hash in (("baseline", frozen, prepare.sha((prepare.ROOT / "prompts/classifier.md").read_bytes())),
                                           ("chosen", chosen, selected["instructions_sha256"])):
            client = stack.enter_context(project.get_openai_client(agent_name=hosting.NAME, max_retries=0, timeout=150))
            rows = []
            for index, item in enumerate(holdout):
                path = prepare.EVIDENCE / ("holdout-" + role + "-row-" + str(index).zfill(3) + ".json")
                if path.exists():
                    rows.append(json.loads(path.read_text()))
                    continue
                intent = path.with_suffix(".intent.json")
                if intent.exists():
                    raise ValueError("holdout request already attempted; reconcile without repeating")
                live.retain(intent.name, {"role": role, "index": index, "version": deployed["version"], "row_id": item["id"]})
                response = invoke(client, deployed, item["query"])
                live.retain(path.with_suffix(".response.json").name, response)
                verify_identity(response, deployed, prompt_hash)
                stored = client.responses.retrieve(response["id"])
                if stored.output_text != response["text"] or stored.metadata != response["metadata"]:
                    raise ValueError("holdout stored response mismatch")
                row = {"index": index, "id": item["id"], "label": item["label"], "prediction": response["text"],
                       "response": response, "stored_readback": True}
                live.retain(path.name, row)
                rows.append(row)
            results[role] = {"metrics": prepare.EVALUATOR.score([row["label"] for row in rows], [row["prediction"] for row in rows]),
                             "rows": rows, "deployment": deployed}
    before, after = results["baseline"]["metrics"], results["chosen"]["metrics"]
    accepted = after["accuracy"] >= 0.9 and after["macro_f1"] >= 0.9 and after["invalid_rate"] == 0 and all(
        after[key] >= before[key] for key in ("accuracy", "macro_f1"))
    validation = json.loads((prepare.EVIDENCE / "baseline-validation.json").read_text())["metrics"]
    gain = selected["metrics"]["macro_f1"] - validation["macro_f1"]
    native = json.loads(native_path("optimizer-job-terminal.json").read_text())
    generated_selected = selected["candidate_id"] != native["result"]["baseline"]
    result = {"selected": selected["candidate_id"], "results": results, "accepted": accepted,
              "validation_macro_f1_gain": gain, "improved": generated_selected and accepted and gain >= 0.01,
              "selected_is_native_baseline": not generated_selected,
              "holdout_once_per_agent": True, "reselection_permitted": False}
    live.retain("final-holdout-result.json", result)
    return result


def final_version_canaries(live):
    import httpx
    from azure.ai.projects.models import AgentOptimizationInlineDatasetInput
    selected = json.loads((prepare.EVIDENCE / "selected-candidate.json").read_text())
    _, manifest = hosting.source_bytes()
    chosen = json.loads((prepare.EVIDENCE / ("deploy-" + manifest["sha256"] + "-active.json")).read_text())
    frozen = baseline()
    dataset = AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/train.json").read_text()))
    endpoint = live.TARGET["endpoint"] + "/agents/" + hosting.NAME + "/endpoint/protocols/openai/responses?api-version=v1"
    anonymous = httpx.post(endpoint, json={"input": "anonymous-final-canary", "store": False}, timeout=30)
    if anonymous.status_code not in (401, 403):
        raise ValueError("final anonymous refusal failed")
    results = {}
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        for role, deployed, prompt_hash in (("baseline", frozen, prepare.sha((prepare.ROOT / "prompts/classifier.md").read_bytes())),
                                           ("chosen", chosen, selected["instructions_sha256"])):
            client = stack.enter_context(project.get_openai_client(agent_name=hosting.NAME, max_retries=0, timeout=150))
            response = invoke(client, deployed, dataset.dataset_items[0].query)
            live.EVENTS.append({"operation": "final_version_canary", "role": role, "response": response})
            verify_identity(response, deployed, prompt_hash)
            stored = client.responses.retrieve(response["id"])
            if stored.output_text != response["text"] or stored.metadata != response["metadata"]:
                raise ValueError("final canary stored readback failed")
            results[role] = response
    result = {"baseline_version": frozen["version"], "chosen_version": chosen["version"], "passed": True,
              "anonymous_status": anonymous.status_code, "responses": results, "input_partition": "train"}
    live.retain("final-version-canaries.json", result)
    return result


def handoff(live):
    checks = prepare.tests()
    integrity = prepare.verify()
    observed = prepare.preflight()
    selected_path = prepare.EVIDENCE / "selected-candidate.json"
    final_path = prepare.EVIDENCE / "final-holdout-result.json"
    selected = json.loads(selected_path.read_text()) if selected_path.exists() else None
    final = json.loads(final_path.read_text()) if final_path.exists() else None
    live_readback = {}
    if final:
        with ExitStack() as stack:
            project, _ = live.connect(stack)
            for role, item in final["results"].items():
                deployed = item["deployment"]
                actual = project.agents.get_version(agent_name=hosting.NAME, agent_version=deployed["version"]).as_dict()
                if actual.get("status") != "active" or actual["definition"]["container_configuration"]["image"] != deployed["build"]["image"]:
                    raise ValueError("final deployed identity drift")
                live_readback[role] = actual
    sources = [prepare.ROOT / name for name in ("README.md", "composition.py", "configuration.yaml", "main.py", "evaluator.py", "prompts/classifier.md")]
    sources.extend(path for path in (prepare.ROOT / "deploy").iterdir() if path.is_file() and path.suffix in (".py", ".sh", ".md", ".txt"))
    sources.append(prepare.ROOT / "deploy/Dockerfile")
    sources.extend((prepare.ROOT / "tests").glob("*.py"))
    sources.extend(path for path in (prepare.ROOT / ".agent_configs").rglob("*") if path.is_file())
    sources.extend([live.CONSTITUTION, prepare.DATA / "manifest.json", prepare.REPO / "specs/20260922_FOUNDRY_AGENT_OPTIMIZATION.md"])
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    archive = prepare.EVIDENCE / (stamp + "-live-source.tar.gz")
    with tarfile.open(archive, "x:gz") as bundle:
        for path in sorted(set(sources)):
            if path.is_symlink():
                raise ValueError("source snapshot symlink refused")
            bundle.add(path, arcname=str(path.relative_to(prepare.REPO)), recursive=False)
    with tarfile.open(archive) as bundle:
        for member in bundle.getmembers():
            if bundle.extractfile(member).read() != (prepare.REPO / member.name).read_bytes():
                raise ValueError("source archive readback drift")
    failures = []
    durations = []
    for path in sorted(prepare.EVIDENCE.glob("*.json")):
        value = json.loads(path.read_text())
        if value.get("action"):
            durations.append({"action": value["action"], "seconds": value.get("seconds"), "receipt": prepare.pin(path)})
            if value.get("status") == "failed":
                failures.append({"action": value["action"], "result": value.get("result"), "receipt": prepare.pin(path)})
    native = json.loads(native_path("optimizer-job-terminal.json").read_text())
    selected_is_baseline = selected is not None and selected["candidate_id"] == native["result"]["baseline"]
    if final:
        correction = {"supersedes_interpretation_of": prepare.pin(final_path), "accepted_quality": final["accepted"],
            "optimization_improved": False if selected_is_baseline else final["improved"],
            "verdict": "unchanged" if selected_is_baseline else ("improved" if final["improved"] else "unchanged"),
            "reason": "Selection retained native baseline; repeated-baseline validation variance is not optimization improvement.",
            "selected_is_native_baseline": selected_is_baseline, "raw_measurements_unchanged": True}
        live.retain("final-verdict-correction.json", correction)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=("role", "index", "row_id", "label", "prediction", "seconds", "response_id"))
        writer.writeheader()
        for role, item in final["results"].items():
            for row in item["rows"]:
                writer.writerow({"role": role, "index": row["index"], "row_id": row["id"], "label": row["label"],
                    "prediction": row["prediction"], "seconds": row["response"]["seconds"], "response_id": row["response"]["id"]})
        prepare.persist(prepare.EVIDENCE / "final-holdout-rows.csv", output.getvalue().encode())
    outcome = {"status": "needs-rescope" if final and selected_is_baseline else ("complete" if final else "blocked"), "objective": "Native automatic Iris optimization with selected hosted configuration and frozen scoring",
        "selected_is_native_baseline": selected_is_baseline,
        "optimization_improvement": False if selected_is_baseline else (final.get("improved") if final else None),
        "acceptance_limit": "Frozen selection retained native baseline, not a generated improved prompt; no optimization improvement claim" if selected_is_baseline else None,
        "smallest_next_decision": "Accept unchanged best configuration, or authorize a new comparison with fresh untouched holdout; do not reselect against observed holdout." if selected_is_baseline else "Review retained acceptance evidence.",
        "constitution": prepare.pin(live.CONSTITUTION), "series": SERIES, "stage": "final verification" if final else "native candidate verification",
        "next_transition": "parent evidence review and publication", "source_archive": prepare.pin(archive),
        "baseline_metrics": json.loads((prepare.EVIDENCE / "baseline-validation.json").read_text())["metrics"],
        "live_readback": live_readback,
        "native_job": native, "selected": {"candidate_id": selected["candidate_id"], "metrics": selected["metrics"]} if selected else None,
        "final": final, "tests": checks, "integrity": integrity, "protected_v3": observed["observed"]["protected_agent_active_and_unchanged"],
        "failures": failures, "action_durations": durations,
        "resources": {"classifier": hosting.NAME, "optimizer_model": "agentcraft-iris-optimizer-gpt54",
            "native_jobs_retained": ["opt_89d941bff7214fa0b670b77249c583ad", native["id"]],
            "teardown": "not authorized; images, versions, evaluator assets, datasets and responses retained"},
        "capture_gaps": ["Total session duration, tokens and monetary cost unknown; native service token counts retained separately.",
            "Early action receipts hash source at exit; later receipts capture module digests at entry. Exact deployed source archive is independently retained.",
            "First silent local observer was interrupted; state receipts survive but final local duration receipt is absent.",
            "Initial wrong legacy loader package remains installed with dependency conflicts; exact accepted runtime pins restored; deployed image uses only declared correct dependencies.",
            "Manual tool calls and edits are captured in host session logs, not a complete machine-readable action ledger here.",
            "No workers dispatched. Maximum effort requested; effective host setting unverified.",
            "Candidate IDs and observation order are not generation lineage; parent/generation remain null."],
        "primary_evidence": [prepare.pin(path) for path in sorted(prepare.EVIDENCE.glob("*.json"))],
        "authority": "primary worker handoff only; parent owns authoritative publication"}
    live.retain(stamp + "-live-handoff.json", outcome)
    return {"status": outcome["status"], "handoff": prepare.pin(prepare.EVIDENCE / (stamp + "-live-handoff.json")),
            "source_archive": prepare.pin(archive), "tests": checks["tests"], "protected_v3": outcome["protected_v3"]}