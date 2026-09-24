"""Frozen scoring and native optimizer execution; no holdout access before selection."""

from contextlib import ExitStack
from datetime import datetime, timezone
import json
import math
import csv
import codecs
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

SERIES = None


def target_text(row):
    if hasattr(row, "model_dump"):
        row = row.model_dump(mode="json")
    item = row.get("datasource_item")
    sample = row.get("sample")
    if not isinstance(item, dict) or (sample is not None and not isinstance(sample, dict)):
        raise ValueError("malformed target containers")
    outputs = []
    for owner in (item, row):
        for key in ("response", "sample.output_text", "output_text"):
            if key in owner:
                outputs.append(owner[key])
    for owner in (item,):
        if "sample" in owner:
            if not isinstance(owner["sample"], dict) or "output_text" not in owner["sample"]:
                raise ValueError("malformed nested target")
            outputs.append(owner["sample"]["output_text"])
    if sample:
        if sample.get("output_text") is not None:
            outputs.append(sample["output_text"])
        messages = sample.get("output", [])
        if not isinstance(messages, list) or len(messages) > 128:
            raise ValueError("malformed target messages")
        texts = []
        for message in messages:
            if not isinstance(message, dict):
                raise ValueError("malformed target message")
            if message.get("role") != "assistant":
                continue
            content = message.get("content")
            if isinstance(content, str):
                if len(content.encode()) > 1000000:
                    raise ValueError("oversized target")
                try:
                    blocks = json.loads(content)
                except json.JSONDecodeError:
                    blocks = None
                if not isinstance(blocks, list):
                    texts.append(content)
                    continue
            else:
                blocks = content
            if not isinstance(blocks, list) or len(blocks) > 128:
                raise ValueError("malformed target blocks")
            for block in blocks:
                if not isinstance(block, dict) or block.get("type") != "output_text" or not isinstance(block.get("text"), str):
                    raise ValueError("malformed target text block")
                texts.append(block["text"])
        if texts:
            outputs.append("".join(texts))
    if not outputs or any(not isinstance(value, str) or len(value.encode()) > 1000000 for value in outputs):
        raise ValueError("target output missing or malformed")
    if any(value != outputs[0] for value in outputs):
        raise ValueError("conflicting target output")
    return outputs[0]


def evaluation_rows(client, eval_id, run_id, expected_count, events, retain=None):
    rows = []
    seen = set()
    deadline = time.monotonic() + 120
    cursor = None
    try:
        page = client.evals.runs.output_items.list(eval_id=eval_id, run_id=run_id, limit=min(100, expected_count + 1))
        for page_index, current in enumerate(page.iter_pages()):
            cursor = getattr(current, "last_id", None)
            events.append({"operation": "evaluation_page", "eval_id": eval_id, "run_id": run_id,
                           "page": page_index, "last_id": cursor, "rows_before": len(rows)})
            if page_index >= 20 or time.monotonic() >= deadline:
                raise ValueError("evaluation pagination bound exceeded; resume retained cursor")
            for model in current.data:
                row = model.model_dump(mode="json")
                identifier = row.get("id")
                if not isinstance(identifier, str) or not identifier or identifier in seen:
                    raise ValueError("duplicate or missing output identity")
                seen.add(identifier)
                rows.append(row)
                if len(rows) > expected_count:
                    raise ValueError("too many evaluation rows")
    except Exception:
        partial = {"eval_id": eval_id, "run_id": run_id, "rows": rows, "last_id": cursor, "complete": False}
        if retain:
            retain(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-partial-evaluation.json", partial)
        else:
            events.append({"operation": "partial_evaluation", **partial})
        raise
    return rows


def eval_metrics(evaluation, expected, evaluator):
    if evaluation.get("status") != "completed" or evaluation.get("error"):
        raise ValueError("native evaluation incomplete or errored")
    run = evaluation.get("run", {})
    if run.get("id") != evaluation["run_id"] or run.get("eval_id") != evaluation["id"] or run.get("status") != "completed" or run.get("error"):
        raise ValueError("native returned run identity/status mismatch")
    counts = evaluation.get("result_counts", {})
    if (counts.get("total") != len(expected) or counts.get("errored") != 0 or counts.get("skipped") != 0
            or any(type(counts.get(key)) is not int for key in ("total", "errored", "skipped"))):
        raise ValueError("native evaluation counts incomplete")
    definition = evaluation.get("definition", {})
    criteria = definition.get("testing_criteria", [])
    if definition.get("id") != evaluation["id"] or len(criteria) != 1:
        raise ValueError("native evaluation definition missing")
    criterion = criteria[0]
    if (criterion.get("evaluator_name") != evaluator["name"]
            or criterion.get("evaluator_version") != evaluator["version"]
            or criterion.get("type") != "azure_ai_evaluator"):
        raise ValueError("native evaluator identity/version drift")
    seen, identifiers, labels, predictions = set(), set(), [], []
    for row in evaluation["rows"]:
        item = row.get("datasource_item") or {}
        query = item.get("query")
        identifier = row.get("id")
        if (query not in expected or query in seen or item.get("ground_truth") != expected[query]
                or not isinstance(identifier, str) or not identifier or identifier in identifiers):
            raise ValueError("native row membership/identity mismatch")
        if (row.get("status") != "completed" or row.get("error")
                or row.get("eval_id") != evaluation["id"] or row.get("run_id") != evaluation["run_id"]):
            raise ValueError("native row incomplete or foreign")
        results = row.get("results")
        if not isinstance(results, list) or len(results) != 1:
            raise ValueError("native criterion missing")
        result = results[0]
        if (result.get("name") != criterion["name"] or result.get("metric") != evaluator["name"]
                or result.get("type") != "azure_ai_evaluator" or result.get("status") != "completed"
                or result.get("error") or type(result.get("score")) not in (int, float)
                or not math.isfinite(result["score"]) or type(result.get("passed")) is not bool):
            raise ValueError("native criterion identity/status/score invalid")
        for key, expected_value in (("evaluator_name", evaluator["name"]), ("evaluator_version", evaluator["version"])):
            if key in result and result[key] != expected_value:
                raise ValueError("native row evaluator drift")
        seen.add(query)
        identifiers.add(identifier)
        labels.append(expected[query])
        predictions.append(target_text(row))
    if seen != set(expected):
        raise ValueError("native evaluation membership incomplete")
    return prepare.EVALUATOR.score(labels, predictions)


def native_path(name):
    if not SERIES:
        raise ValueError("pinned run manifest required")
    return prepare.EVIDENCE / (SERIES + "-" + name)


def observe_validation(live):
    selected = prepare.EVIDENCE / "candidate-validation-metrics.json"
    if selected.exists():
        result = json.loads(selected.read_text())
        return {"complete": result["complete_independent_validation"], "selected": result["selected"],
                "candidates": [{"candidate_id": item["candidate_id"], "metrics": item["metrics"]} for item in result["candidates"]]}
    return {"complete": False, "next": "resume candidate-validation with the same manifest; unresolved intents refuse replay"}


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
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        sessions = []
        deadline = time.monotonic() + 60
        for session in project.agents.list_sessions(agent_name=hosting.NAME, limit=100):
            if len(sessions) >= 1000 or time.monotonic() >= deadline:
                raise ValueError("session inspection bound exceeded")
            sessions.append(session.as_dict())
    return {"status": 200, "sessions": {"data": sessions}}


def log_messages(chunks, max_bytes=262144, max_events=100):
    decoder = codecs.getincrementaldecoder("utf-8")("strict")
    pending, data, total, events = "", [], 0, 0
    for chunk in chunks:
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("log byte bound exceeded")
        pending += decoder.decode(chunk)
        while "\n" in pending:
            line, pending = pending.split("\n", 1)
            line = line.removesuffix("\r")
            if line.startswith("data:"):
                data.append(line[5:].lstrip(" "))
            elif not line and data:
                events += 1
                if events > max_events:
                    raise ValueError("log event bound exceeded")
                try:
                    value = json.loads("\n".join(data))
                except ValueError:
                    value = None
                data = []
                if isinstance(value, dict) and isinstance(value.get("message"), str):
                    yield value["message"]
    decoder.decode(b"", final=True)


def runtime_logs(live):
    sessions = inspect_runtime(live)
    job = json.loads(native_path("optimizer-job-created.json").read_text())
    candidates = [session for session in sessions["sessions"].get("data", []) if session.get("created_at", 0) >= job["created_at"]]
    if not candidates:
        return {"sessions_after_job": 0, "lines": []}
    session = max(candidates, key=lambda item: item["created_at"])
    lines = []
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        deadline = time.monotonic() + 20
        try:
            stream = project.agents.get_session_log_stream(agent_name=hosting.NAME,
                agent_version=session["version_indicator"]["agent_version"], session_id=session["agent_session_id"],
                connection_timeout=10, read_timeout=5)
            for message in log_messages(stream):
                if any(word in message for word in ("Error", "Exception", "denied", "failed", "429", "403", "401")):
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
    if live.RUN_MANIFEST:
        canary = json.loads((prepare.EVIDENCE / ("runtime-canary-v" + deployed["version"] + ".json")).read_text())
        if not canary.get("stored_readback") or not json.loads((prepare.EVIDENCE / "optimizer-model-canary.json").read_text()).get("passed"):
            raise ValueError("hosted/model canaries required before native optimization")
    if not live.RUN_MANIFEST and not (prepare.EVIDENCE / "baseline-validation.json").exists():
        raise ValueError("complete baseline required before optimizer")
    return AgentOptimizationJob(inputs=AgentOptimizationJobInputs(
        agent=OptimizedAgentIdentifier(agent_name=deployed["agent"], agent_version=deployed["version"]),
        train_dataset=AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/train.json").read_text())),
        validation_dataset=AgentOptimizationInlineDatasetInput(json.loads((prepare.DATA / "candidate/validation.json").read_text())),
        evaluators=[AgentOptimizationEvaluatorRef(name=evaluator["name"], version=evaluator["version"])],
        options=AgentOptimizationOptions(max_candidates=live.RUN_MANIFEST["max_candidates"], max_stalls=2, eval_model="gpt-5.6-luna",
            optimization_model=model["name"], optimization_config={
                "system_prompt": (prepare.ROOT / "prompts/classifier.md").read_text()})))


def optimize(live):
    request = optimization_request(live)
    operation_id = str(uuid.uuid4())
    intent = native_path("optimizer-job-default-turn-intent.json")
    if intent.exists():
        raise ValueError("existing optimizer intent; reconcile rather than resubmit")
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        live.retain(intent.name, {"operation_id": operation_id, "request": request.as_dict(),
                    "constitution": prepare.pin(live.CONSTITUTION), "holdout_uploaded": False})
        observed = {}
        def capture(response):
            from urllib.parse import urlsplit, urlunsplit
            actual = response.http_response
            observed["status"] = actual.status_code
            for key in ("x-ms-request-id", "apim-request-id", "Operation-Location", "Location"):
                value = actual.headers.get(key)
                if value and key in ("Operation-Location", "Location"):
                    parts = urlsplit(value)
                    value = urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
                if value:
                    observed[key] = value
            live.retain(native_path("optimizer-response-identity.json").name, observed)
        poller = project.beta.agents.begin_create_optimization_job(job=request, operation_id=operation_id,
            polling=False, raw_response_hook=capture)
        details = poller.details
        identity = {"operation_id": operation_id, "job_id": details.get("job_id") if isinstance(details, dict) else getattr(details, "job_id", None),
                "response": observed, "request_sha256": prepare.sha(prepare.encoded(request.as_dict())),
                "polling": False, "recovery": "get_optimization_job(job_id); operation_id retained for unknown submission; never repeat create"}
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
    identity = json.loads(native_path("optimizer-job-identity.json").read_text())
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        job = project.beta.agents.get_optimization_job(identity["job_id"]).as_dict()
        return {"identity": identity, "read_only_reconciliation": True, "job": job}


def optimizer_diagnostics(live):
    identity = json.loads(native_path("optimizer-job-identity.json").read_text())
    with ExitStack() as stack:
        project, _ = live.connect(stack)
        job = project.beta.agents.get_optimization_job(identity["job_id"]).as_dict()
        return {"job": job, "candidates": (job.get("result") or {}).get("candidates", [])}


def native_candidates(job, expected_count):
    if hasattr(job, "as_dict"):
        job = job.as_dict()
    candidates = (job.get("result") or {}).get("candidates")
    if job.get("status") not in ("completed", "succeeded") or job.get("error"):
        raise ValueError("native job not successfully complete; retain partial result")
    if not isinstance(candidates, list) or len(candidates) != expected_count or not candidates:
        raise ValueError("native candidate membership incomplete")
    seen = set()
    for candidate in candidates:
        identifier = candidate.get("id") or candidate.get("candidate_id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", identifier) or identifier in seen:
            raise ValueError("duplicate/missing candidate identity")
        seen.add(identifier)
        if any(not isinstance(candidate.get(key), str) or not candidate[key] for key in ("name", "eval_id", "eval_run_id")):
            raise ValueError("candidate evaluation identity missing")
        for key in ("avg_score", "avg_tokens"):
            if type(candidate.get(key)) not in (int, float) or not math.isfinite(candidate[key]):
                raise ValueError("candidate metric missing or nonfinite")
    return candidates


def resolve_candidate_config(project, endpoint, job_id, candidate_id):
    import importlib.metadata
    import sys
    from azure.core.rest import HttpRequest
    from azure.ai.agentserver.optimization import CandidateConfig
    if importlib.metadata.version("azure-ai-agentserver-optimization") != "1.0.0b1":
        raise ValueError("resolver exception version drift")
    if any(not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", value) for value in (job_id, candidate_id)):
        raise ValueError("unsafe native resolver identity")
    response = project.send_request(HttpRequest("GET", endpoint + "/agent_optimization_jobs/" + job_id
        + "/candidates/" + candidate_id + "/config?api-version=2025-11-15-preview"), connection_timeout=15, read_timeout=30)
    if response.status_code != 200:
        raise ValueError("candidate config retrieval failed")
    payload = response.read()
    if len(payload) > 1000000:
        raise ValueError("candidate config exceeds bound")
    config = json.loads(payload)
    if not isinstance(config, dict) or set(config) - {"name", "instructions", "model", "temperature", "skills", "tools"}:
        raise ValueError("unapproved candidate config fields")
    sys.path.insert(0, str(prepare.ROOT))
    from composition import apply_optimization, load_spec
    apply_optimization(load_spec(), CandidateConfig.from_dict(config))
    return config


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
    identity = json.loads(native_path("optimizer-job-identity.json").read_text())
    with ExitStack() as stack:
        project, client = live.connect(stack)
        job = project.beta.agents.get_optimization_job(identity["job_id"]).as_dict()
        live.retain(native_path("optimizer-job-terminal.json").name, job)
        expected_count = json.loads(native_path("optimizer-job-default-turn-intent.json").read_text())["request"]["inputs"]["options"]["max_candidates"]
        listing = {"data": native_candidates(job, expected_count), "source": "AgentOptimizationJob.result.candidates"}
        live.retain(native_path("native-candidates.json").name, listing)
        rows = []
        for candidate in listing.get("data", []):
            candidate_id = candidate.get("candidate_id") or candidate.get("id")
            if not isinstance(candidate_id, str) or not candidate_id.replace("_", "").replace("-", "").isalnum():
                raise ValueError("invalid candidate identity")
            config = resolve_candidate_config(project, live.TARGET["endpoint"], identity["job_id"], candidate_id)
            live.retain(candidate_id + "-config.json", config)
            item = {"candidate_id": candidate_id, "generation": None, "parent_id": None,
                    "native": candidate, "config": config, "independent_metrics": None}
            eval_id, run_id = candidate.get("eval_id"), candidate.get("eval_run_id")
            if eval_id and run_id:
                run = client.evals.runs.retrieve(eval_id=eval_id, run_id=run_id)
                expected = {row["query"]: row["ground_truth"] for row in json.loads(
                    (prepare.DATA / "candidate/validation.json").read_text())["dataset_items"]}
                outputs = evaluation_rows(client, eval_id, run_id, len(expected), live.EVENTS, live.retain)
                item["evaluation"] = {"id": eval_id, "run_id": run_id, "status": run.status,
                    "run": run.model_dump(mode="json"),
                    "error": run.model_dump(mode="json").get("error"),
                    "definition": client.evals.retrieve(eval_id).model_dump(mode="json"),
                    "report_url": run.report_url, "result_counts": run.result_counts.model_dump(mode="json"), "rows": outputs}
                live.retain(candidate_id + "-evaluation-raw.json", item["evaluation"])
                item["native_row_metrics"] = eval_metrics(item["evaluation"], expected,
                    json.loads(live.evaluator_path("registered").read_text()))
            live.retain(candidate_id + "-evidence.json", item)
            rows.append(item)
        live.retain(native_path("candidate-metrics.json").name, {"job_id": identity["job_id"], "candidates": rows,
                    "complete_independent_validation": False, "holdout_scored": False})
        return {"job_id": identity["job_id"], "candidate_count": len(rows), "job_status": job["status"]}


def select_candidate(metrics, expected_rows=30):
    if not metrics or any(item["metrics"].get("n") != expected_rows for item in metrics):
        raise ValueError("every candidate requires complete declared validation membership")
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
        verified_metrics = eval_metrics(candidate["evaluation"], expected,
            json.loads(live.evaluator_path("registered").read_text()))
        rows = candidate["evaluation"]["rows"]
        seen = set()
        labels, predictions = [], []
        for index, row in enumerate(rows):
            item = row["datasource_item"]
            query = item["query"]
            if query in seen or expected.get(query) != item.get("ground_truth"):
                raise ValueError("native validation row membership/label mismatch")
            seen.add(query)
            prediction = target_text(row)
            labels.append(item["ground_truth"])
            predictions.append(prediction)
            writer.writerow({"candidate_id": candidate["candidate_id"], "row_index": index, "query": query,
                "label": item["ground_truth"], "prediction": prediction,
                "correct": isinstance(prediction, str) and prediction.strip() == item["ground_truth"],
                "native_score": row["results"][0].get("score") if row.get("results") else None})
        if seen != set(expected):
            raise ValueError("native validation coverage incomplete")
        summaries.append({"candidate_id": candidate["candidate_id"], "generation": None, "parent_id": None,
            "metrics": verified_metrics, "native_avg_score": candidate["native"].get("avg_score"),
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
    selected = select_candidate(scored, len(dataset.dataset_items))
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