"""Revision-2 live integration probes with immutable primary evidence."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import importlib.metadata
import inspect
import json
import subprocess
import sys
import time

import prepare

CONSTITUTION = prepare.PROJECT / "constitution/constitution.yaml"
CONSTITUTION_SHA256 = "854bfde0ee9421f141881d865834646f77972635a665737ba656c8fb79b7098d"
TARGET = json.loads((prepare.REPO / "testbeds/foundry-agent-evaluation/deploy/records/approved-decision.json").read_text())
EVENTS = []
EXACT_CODE = '''def grade(sample, item):
    response = item.get("response", item.get("sample.output_text", sample.get("output_text", "")))
    ground_truth = item["ground_truth"]
    labels = ("Iris-setosa", "Iris-versicolor", "Iris-virginica")
    valid = isinstance(response, str) and response.strip() in labels
    return float(valid and response.strip() == ground_truth)
'''
EVALUATOR_PREFIX = "evaluator-" + prepare.sha(EXACT_CODE.encode())[:12]


def evaluator_path(suffix):
    return prepare.EVIDENCE / (EVALUATOR_PREFIX + "-" + suffix + ".json")


def evaluator_retain(suffix, value, intent=False):
    path = evaluator_path(suffix)
    if intent and path.exists():
        raise ValueError("existing mutation intent requires readback; automatic resubmission refused")
    return prepare.persist(path, prepare.encoded(value))


def retain(name, value):
    path = prepare.EVIDENCE / name
    return prepare.persist(path, prepare.encoded(value))


def connect(stack):
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    facts = prepare.preflight()
    EVENTS.append({"operation": "protected_preflight", "result": facts})
    credential = stack.enter_context(AzureCliCredential(tenant_id=TARGET["tenant"], process_timeout=30))
    project = stack.enter_context(AIProjectClient(endpoint=TARGET["endpoint"], credential=credential, allow_preview=True,
                                  retry_total=0, connection_timeout=15, read_timeout=60))
    client = stack.enter_context(project.get_openai_client(max_retries=0, timeout=60))
    return project, client


def install_loader():
    command = [sys.executable, "-m", "pip", "install", "--user", "--break-system-packages",
               "--no-deps", "azure-ai-agentserver-optimization==1.0.0b1"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    EVENTS.append({"command": command, "exit_code": result.returncode,
                   "output": result.stdout, "error": result.stderr})
    if result.returncode:
        raise RuntimeError("loader installation failed; retained pip diagnostics")
    import azure.ai.agentserver.optimization as loader
    return {"version": importlib.metadata.version("azure-ai-agentserver-optimization"),
            "origin": loader.__file__, "exports": [name for name in dir(loader) if not name.startswith("_")]}


def restore_sdk():
    command = [sys.executable, "-m", "pip", "install", "--user", "--break-system-packages",
               "azure-ai-projects==2.6.1", "azure-ai-agentserver-core==2.1.0",
               "agent-framework-core==1.18.0", "agent-framework-foundry==1.13.0",
               "agent-framework-openai==1.14.3", "openai==3.13.0"]
    result = subprocess.run(command, capture_output=True, text=True, timeout=300)
    EVENTS.append({"command": command, "exit_code": result.returncode, "output": result.stdout, "error": result.stderr})
    if result.returncode:
        raise RuntimeError("SDK restoration failed")
    return {"sdk": importlib.metadata.version("azure-ai-projects"), "dependency_conflicts": "see retained pip output"}


def evaluator_definition():
    return {"evaluator_type": "custom", "categories": ["quality"],
            "display_name": "Iris exact stripped label", "description": "Native search guidance; frozen evaluator.py owns independent metrics",
            "definition": {"type": "code", "code_text": EXACT_CODE,
                "data_schema": {"type": "object", "properties": {"response": {"type": "string"},
                                 "ground_truth": {"type": "string"}}, "required": ["response", "ground_truth"]},
                "metrics": {"classification_correctness": {"type": "continuous", "desirable_direction": "increase",
                            "min_value": 0, "max_value": 1, "threshold": 1, "is_primary": True}}}}


def evaluator_register():
    namespace = {}
    exec(EXACT_CODE, namespace)
    outputs = [namespace["grade"]({}, {"response": response, "ground_truth": "Iris-setosa"})
               for response in (" Iris-setosa ", "Iris-versicolor", "not-a-label")]
    if outputs != [1, 0, 0]:
        raise ValueError("local exact evaluator canaries failed")
    name = "agentcraft-iris-exact-" + prepare.sha(EXACT_CODE.encode())[:12]
    request = evaluator_definition()
    with ExitStack() as stack:
        project, _ = connect(stack)
        evaluator_retain("register-intent", {"name": name, "request": request}, intent=True)
        result = project.beta.evaluators.create_version(name=name, evaluator_version=request).as_dict()
        evaluator_retain("registered", result)
        actual = project.beta.evaluators.get_version(name=name, version=result["version"]).as_dict()
        if actual["definition"]["code_text"] != EXACT_CODE:
            raise ValueError("registered code readback mismatch")
        return {"registered": actual, "local_canaries": outputs}


def evaluator_canary():
    evaluator = json.loads(evaluator_path("registered").read_text())
    request = {"name": "agentcraft-iris-exact-canary", "data_source_config": {"type": "custom",
               "item_schema": {"type": "object", "properties": {"response": {"type": "string"},
                   "ground_truth": {"type": "string"}}, "required": ["response", "ground_truth"]}},
               "testing_criteria": [{"type": "azure_ai_evaluator", "name": "classification_correctness",
                   "evaluator_name": evaluator["name"], "evaluator_version": evaluator["version"],
                   "data_mapping": {"response": "{{item.response}}", "ground_truth": "{{item.ground_truth}}"}}]}
    with ExitStack() as stack:
        _, client = connect(stack)
        evaluator_retain("canary-intent", request, intent=True)
        definition = client.evals.create(**request)
        evaluator_retain("canary-definition", definition.model_dump(mode="json"))
        run_request = {"eval_id": definition.id, "name": "positive-wrong-invalid",
                       "data_source": {"type": "jsonl", "source": {"type": "file_content", "content": [
                           {"item": {"response": response, "ground_truth": "Iris-setosa"}}
                           for response in (" Iris-setosa ", "Iris-versicolor", "not-a-label")]}}}
        evaluator_retain("canary-run-intent", run_request, intent=True)
        run = client.evals.runs.create(**run_request)
        result = run.model_dump(mode="json")
        evaluator_retain("canary-run", result)
        return result


def mapped_canary():
    evaluator = json.loads(evaluator_path("registered").read_text())
    request = {"name": "agentcraft-iris-native-field-canary", "data_source_config": {"type": "custom",
        "item_schema": {"type": "object", "properties": {"sample.output_text": {"type": "string"},
            "ground_truth": {"type": "string"}}, "required": ["sample.output_text", "ground_truth"]}},
        "testing_criteria": [{"type": "azure_ai_evaluator", "name": "classification_correctness",
            "evaluator_name": evaluator["name"], "evaluator_version": evaluator["version"]}]}
    with ExitStack() as stack:
        _, client = connect(stack)
        evaluator_retain("mapped-canary-intent", request, intent=True)
        definition = client.evals.create(**request)
        evaluator_retain("mapped-canary-definition", definition.model_dump(mode="json"))
        run_request = {"eval_id": definition.id, "name": "native-field-positive-wrong-invalid",
            "data_source": {"type": "jsonl", "source": {"type": "file_content", "content": [
                {"item": {"sample.output_text": response, "ground_truth": "Iris-setosa"}}
                for response in (" Iris-setosa ", "Iris-versicolor", "not-a-label")]}}}
        evaluator_retain("mapped-canary-run-intent", run_request, intent=True)
        run = client.evals.runs.create(**run_request)
        evaluator_retain("mapped-canary-run", run.model_dump(mode="json"))
        return run.model_dump(mode="json")


def canary_readback(mapped=False):
    prefix = "mapped-canary" if mapped else "canary"
    identity = json.loads(evaluator_path(prefix + "-run").read_text())
    with ExitStack() as stack:
        _, client = connect(stack)
        run = client.evals.runs.retrieve(run_id=identity["id"], eval_id=identity["eval_id"])
        rows = [item.model_dump(mode="json") for item in client.evals.runs.output_items.list(
            run_id=identity["id"], eval_id=identity["eval_id"], limit=10)]
        result = {"run": run.model_dump(mode="json"), "rows": rows, "passed": False}
        EVENTS.append({"operation": "native_canary_readback", "result": result})
        if run.status not in ("completed", "failed", "canceled", "cancelled"):
            return result
        expected = {" Iris-setosa ": 1, "Iris-versicolor": 0, "not-a-label": 0}
        if run.status != "completed" or len(rows) != 3:
            raise ValueError("native evaluator canary did not complete three rows")
        for row in rows:
            response = row["datasource_item"]["sample.output_text" if mapped else "response"]
            metrics = row.get("results", [])
            if len(metrics) != 1 or metrics[0].get("score") != expected.pop(response) or metrics[0].get("error"):
                raise ValueError("native evaluator canary score mismatch")
        if expected:
            raise ValueError("missing canary row")
        result["passed"] = True
        evaluator_retain(prefix + "-passed", result)
        return result


def gate():
    if prepare.sha(CONSTITUTION.read_bytes()) != CONSTITUTION_SHA256:
        raise ValueError("live constitution pin drift")
    if importlib.metadata.version("azure-ai-projects") != "2.6.1":
        raise ValueError("native SDK pin drift")
    return prepare.verify()


def capabilities():
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    facts = prepare.preflight()
    with ExitStack() as stack:
        credential = stack.enter_context(AzureCliCredential(process_timeout=30))
        project = stack.enter_context(AIProjectClient(
            endpoint=facts["target_endpoint"], credential=credential,
            retry_total=0, connection_timeout=15, read_timeout=60))
        operations = {}
        for group, owner in (("evaluators", project.beta.evaluators), ("agents", project.beta.agents)):
            operations[group] = {name: str(inspect.signature(getattr(owner, name)))
                                 for name in dir(owner) if not name.startswith("_") and callable(getattr(owner, name))}
        return {"preflight": facts, "operations": operations}


def main():
    import hosting
    import campaign
    parser = argparse.ArgumentParser(description=__doc__)
    actions = {"live-check": gate, "capabilities": capabilities, "install-loader": install_loader,
               "evaluator-register": evaluator_register, "evaluator-canary": evaluator_canary,
               "canary-readback": canary_readback, "restore-sdk": restore_sdk}
    actions.update({"mapped-canary": mapped_canary, "mapped-canary-readback": lambda: canary_readback(mapped=True)})
    actions.update({"build": lambda: hosting.build(sys.modules[__name__]),
                    "deploy": lambda: hosting.deploy(sys.modules[__name__]),
                    "runtime-canary": lambda: campaign.runtime_canary(sys.modules[__name__]),
                    "baseline-route-canary": lambda: campaign.baseline_route_canary(sys.modules[__name__]),
                    "inspect-runtime": lambda: campaign.inspect_runtime(sys.modules[__name__]),
                    "runtime-logs": lambda: campaign.runtime_logs(sys.modules[__name__]),
                    "baseline-validation": lambda: campaign.baseline_validation(sys.modules[__name__]),
                    "model-inventory": lambda: campaign.model_inventory(sys.modules[__name__]),
                    "provision-optimizer-model": lambda: campaign.provision_optimizer_model(sys.modules[__name__]),
                    "optimizer-model-canary": lambda: campaign.optimizer_model_canary(sys.modules[__name__]),
                    "optimize": lambda: campaign.optimize(sys.modules[__name__]),
                    "optimize-retry-rejected": lambda: campaign.optimize(sys.modules[__name__], retry_rejected=True),
                    "optimizer-readback": lambda: campaign.optimizer_readback(sys.modules[__name__]),
                    "optimizer-operation": lambda: campaign.optimizer_operation(sys.modules[__name__]),
                    "optimizer-diagnostics": lambda: campaign.optimizer_diagnostics(sys.modules[__name__]),
                    "optimizer-wait": lambda: campaign.optimizer_wait(sys.modules[__name__]),
                    "collect-candidates": lambda: campaign.collect_candidates(sys.modules[__name__]),
                    "native-row-metrics": lambda: campaign.native_row_metrics(sys.modules[__name__]),
                    "candidate-validation": lambda: campaign.candidate_validation(sys.modules[__name__]),
                    "observe-validation": lambda: campaign.observe_validation(sys.modules[__name__]),
                    "observe-holdout": lambda: campaign.observe_holdout(sys.modules[__name__]),
                    "apply-selected": lambda: campaign.apply_selected(sys.modules[__name__]),
                    "final-version-canaries": lambda: campaign.final_version_canaries(sys.modules[__name__]),
                    "final-holdout": lambda: campaign.final_holdout(sys.modules[__name__])})
    actions["handoff"] = lambda: campaign.handoff(sys.modules[__name__])
    actions.update({"demonstration-decision": lambda: campaign.demonstration_decision(sys.modules[__name__]),
                    "demonstration-build": lambda: hosting.build(sys.modules[__name__], demonstration=True),
                    "demonstration-deploy": lambda: hosting.deploy(sys.modules[__name__], demonstration=True),
                    "demonstration-handoff": lambda: campaign.demonstration_handoff(sys.modules[__name__]),
                    "demonstration-verify": lambda: campaign.demonstration_verify(sys.modules[__name__])})
    parser.add_argument("action", choices=tuple(actions))
    action = parser.parse_args().action
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    loaded_sources = {name: prepare.pin(prepare.ROOT / "deploy" / name)
                      for name in ("live.py", "campaign.py", "hosting.py", "prepare.py")}
    status = "complete"
    try:
        if action == "restore-sdk":
            if prepare.sha(CONSTITUTION.read_bytes()) != CONSTITUTION_SHA256:
                raise ValueError("constitution drift")
            verified = None
        else:
            verified = gate()
        result = verified if action == "live-check" else actions[action]()
    except Exception as error:
        status = "failed"
        result = {"error_type": type(error).__name__, "http_status": getattr(error, "status_code", None),
                  "reason": str(error) if not hasattr(error, "status_code") else "provider request failed"}
        if hasattr(error, "error") and error.error:
            result["provider_code"] = getattr(error.error, "code", None)
            result["provider_message"] = getattr(error.error, "message", None)
        if getattr(error, "response", None) is not None:
            try:
                body = error.response.json()
                detail = body.get("error", body)
                result["provider_detail"] = {key: detail.get(key) for key in ("code", "message", "type", "param", "title", "detail", "errors", "traceId")}
            except (ValueError, AttributeError, TypeError):
                result["provider_detail"] = "non-JSON response"
    receipt = {"action": action, "status": status, "started_at": started.isoformat(),
               "finished_at": datetime.now(timezone.utc).isoformat(), "seconds": time.monotonic() - clock,
               "constitution": prepare.pin(CONSTITUTION), "source": loaded_sources["live.py"], "loaded_sources": loaded_sources,
               "result": result, "events": EVENTS, "authority": "primary worker evidence; overseer publication pending"}
    path = prepare.EVIDENCE / (started.strftime("%Y%m%dT%H%M%S%fZ") + "-" + action + ".json")
    prepare.persist(path, prepare.encoded(receipt))
    print(json.dumps({"status": status, "receipt": prepare.pin(path)}))
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())