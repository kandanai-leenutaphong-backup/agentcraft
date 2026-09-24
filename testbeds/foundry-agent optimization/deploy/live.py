"""Revision-2 live integration probes with immutable primary evidence."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import importlib.metadata
import inspect
import json
import math
import subprocess
import sys
import time

import prepare

sys.path.insert(0, str(prepare.REPO / "libraries/foundry-ops/src"))

from foundry_ops.evals import check_counts, check_criteria as check_canary_criteria
from foundry_ops.manifest import load_run_manifest, series_directory
from foundry_ops.records import EvidenceLedger, encode_json, error_summary, sha256_hex, utc_stamp

CONSTITUTION = prepare.PROJECT / "constitution/constitution.yaml"
CONSTITUTION_SHA256 = "854bfde0ee9421f141881d865834646f77972635a665737ba656c8fb79b7098d"
TARGET = json.loads((prepare.REPO / "testbeds/foundry-agent-evaluation/deploy/records/approved-decision.json").read_text())
EVENTS = []
RUN_MANIFEST = None
EXACT_CODE = '''def grade(sample, item):
    if not isinstance(item, dict):
        raise ValueError("item must be an object")
    labels = ("Iris-setosa", "Iris-versicolor", "Iris-virginica")
    ground_truth = item.get("ground_truth")
    if not isinstance(ground_truth, str) or ground_truth not in labels:
        raise ValueError("invalid ground truth")
    outputs = []
    for key in ("response", "sample.output_text"):
        if key in item:
            outputs.append(item[key])
    if "sample" in item:
        if not isinstance(item["sample"], dict) or "output_text" not in item["sample"]:
            raise ValueError("malformed nested sample")
        outputs.append(item["sample"]["output_text"])
    if sample is not None:
        if not isinstance(sample, dict):
            raise ValueError("sample must be an object or null")
        if "output_text" in sample:
            outputs.append(sample["output_text"])
    if not outputs:
        raise ValueError("target output missing")
    response = outputs[0]
    if any(type(value) is not type(response) or value != response for value in outputs[1:]):
        raise ValueError("conflicting target outputs")
    valid = isinstance(response, str) and response.strip() in labels
    return float(valid and response.strip() == ground_truth)
'''
EVALUATOR_PREFIX = "evaluator-" + sha256_hex(EXACT_CODE.encode())[:12]
FORBIDDEN_AGENTS = frozenset({"agentcraft-iris-optimization", "agentcraft-hosted-tool-proof"})


def evaluator_path(suffix):
    return prepare.EVIDENCE / (EVALUATOR_PREFIX + "-" + suffix + ".json")


def evaluator_retain(suffix, value, intent=False):
    return EvidenceLedger(prepare.EVIDENCE).retain(evaluator_path(suffix).name, value, allow_identical=not intent)


def retain(name, value):
    return EvidenceLedger(prepare.EVIDENCE).retain(name, value, allow_identical=True)


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


def seed_prerequisites(value, evidence):
    names = {"baseline-frozen.json", "runtime-canary-v1.json", "optimizer-model-canary.json",
             EVALUATOR_PREFIX + "-registered.json", EVALUATOR_PREFIX + "-mapped-canary-passed.json"}
    references = value.get("prerequisites", {})
    if references and set(references) != names:
        raise ValueError("incomplete or foreign prerequisite set")
    for name, reference in references.items():
        source = prepare.REPO / reference["path"]
        if (source.is_symlink() or not source.resolve().is_relative_to(prepare.ROOT / "deploy/evidence/migration-o-v1")
                or sha256_hex(source.read_bytes()) != reference["sha256"]):
            raise ValueError("prerequisite path/digest mismatch")
        payload = json.loads(source.read_text())
        if name == "baseline-frozen.json":
            if payload.get("agent") != value["agent"] or payload.get("version") != "1":
                raise ValueError("foreign baseline prerequisite")
            payload = {"deployment": payload, "source_reference": reference}
        prepare.persist(evidence / name, encode_json(payload))


def configure_run(path, expected_sha256, action):
    global RUN_MANIFEST, CONSTITUTION, CONSTITUTION_SHA256
    import hosting
    import campaign
    run = load_run_manifest(path, expected_sha256=expected_sha256, action=action, allowed_root=prepare.ROOT / "deploy/env",
                            pins={"target_sha256": prepare.REPO / "testbeds/foundry-agent-evaluation/deploy/records/approved-decision.json"},
                            forbidden_agents=FORBIDDEN_AGENTS)
    value = run.value
    constitution = prepare.REPO / value["constitution"]["path"]
    if (constitution.resolve() != prepare.REPO / "agentcraft_projects/foundry-official-integration-20260922/constitution/constitution.yaml"
            or sha256_hex(constitution.read_bytes()) != value["constitution"]["sha256"]):
        raise ValueError("migration constitution mismatch")
    if type(value.get("max_candidates")) is not int or not 1 <= value["max_candidates"] <= 3:
        raise ValueError("invalid candidate bound")
    if type(value.get("max_stalls", 2)) is not int or not 1 <= value.get("max_stalls", 2) <= 10:
        raise ValueError("invalid stall bound")
    rows = value.get("development_rows")
    if not isinstance(rows, list) or not 2 <= len(rows) <= 6 or len({row["query"] for row in rows}) != len(rows):
        raise ValueError("invalid development membership")
    if any(set(row) != {"query", "ground_truth"} or row["ground_truth"] not in prepare.LABELS
           or not isinstance(row["query"], str) or not row["query"] for row in rows):
        raise ValueError("invalid synthetic development row")
    evidence = series_directory(prepare.ROOT / "deploy/evidence", value["series"])
    run.bind(EvidenceLedger(evidence))
    seed_prerequisites(value, evidence)
    prepare.EVIDENCE = evidence
    prepare.DATA = evidence / "development"
    RUN_MANIFEST = value
    CONSTITUTION, CONSTITUTION_SHA256 = constitution, value["constitution"]["sha256"]
    campaign.SERIES = value["series"]
    hosting.NAME = value["agent"]
    dataset = {"type": "inline", "dataset_items": [dict(row, desired_num_turns=1) for row in rows]}
    for partition in ("train", "validation"):
        prepare.persist(prepare.DATA / "candidate" / (partition + ".json"), encode_json(dataset))
    retain("optimizer-model-ready.json", {"name": value["optimizer_model"]})
    return {"manifest": prepare.pin(run.path), "series": value["series"], "live": False}


def existing_job_parity():
    import campaign
    reference = RUN_MANIFEST["existing_job"]
    path = prepare.REPO / reference["candidates_path"]
    if not path.resolve().is_relative_to(prepare.ROOT / "deploy/evidence") or sha256_hex(path.read_bytes()) != reference["candidates_sha256"]:
        raise ValueError("existing candidate receipt drift")
    retained = json.loads(path.read_text())["data"]
    with ExitStack() as stack:
        project, _ = connect(stack)
        job = project.beta.agents.get_optimization_job(reference["job_id"]).as_dict()
    actual = campaign.native_candidates(job, len(retained))
    def normalized(items):
        return {item.get("candidate_id") or item.get("id"): {key: item.get(key) for key in
            ("name", "avg_score", "avg_tokens", "eval_id", "eval_run_id")} for item in items}
    if normalized(actual) != normalized(retained):
        raise ValueError("native existing-job candidate parity mismatch")
    return {"job_id": reference["job_id"], "candidates": actual, "matched": len(actual), "read_only": True}


def evaluator_definition():
    return {"evaluator_type": "custom", "categories": ["quality"],
            "display_name": "Iris exact stripped label", "description": "Native search guidance; frozen evaluator.py owns independent metrics",
            "definition": {"type": "code", "code_text": EXACT_CODE,
                "data_schema": {"type": "object", "properties": {"response": {"type": "string"},
                                 "ground_truth": {"type": "string"}}, "required": ["response", "ground_truth"]},
                "metrics": {"classification_correctness": {"type": "continuous", "desirable_direction": "increase",
                            "min_value": 0, "max_value": 1, "is_primary": True}}}}


def check_registered_evaluator(actual, name, version):
    expected = evaluator_definition()["definition"]
    expected.update(init_parameters={"properties": {}, "required": [], "type": "object"}, prompt_text="")
    definition = dict(actual.get("definition", {}))
    definition.setdefault("init_parameters", {"properties": {}, "required": [], "type": "object"})
    definition.setdefault("prompt_text", "")
    if actual.get("name") != name or actual.get("version") != version or definition != expected:
        raise ValueError("registered evaluator identity/schema/code readback mismatch")


def evaluator_register():
    from azure.ai.projects.models import EvaluatorVersion
    namespace = {}
    exec(EXACT_CODE, namespace)
    outputs = [namespace["grade"]({}, {"response": response, "ground_truth": "Iris-setosa"})
               for response in (" Iris-setosa ", "Iris-versicolor", "not-a-label")]
    if outputs != [1, 0, 0]:
        raise ValueError("local exact evaluator canaries failed")
    name = "agentcraft-iris-exact-" + sha256_hex(EXACT_CODE.encode())[:12]
    request = evaluator_definition()
    with ExitStack() as stack:
        project, _ = connect(stack)
        if evaluator_path("registered").exists():
            result = json.loads(evaluator_path("registered").read_text())
        else:
            evaluator_retain("register-intent", {"name": name, "request": request}, intent=True)
            result = project.beta.evaluators.create_version(name=name, evaluator_version=EvaluatorVersion(request)).as_dict()
            evaluator_retain("registered", result)
        actual = project.beta.evaluators.get_version(name=name, version=result["version"]).as_dict()
        EVENTS.append({"operation": "registered_evaluator_readback", "actual": actual})
        check_registered_evaluator(actual, name, result["version"])
        return {"registered": actual, "local_canaries": outputs,
                "threshold_semantics": "Service omitted the SDK metric threshold; binary 1/0/0 scores are independently required, provider passed flags use 0.5."}


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
            "evaluator_name": evaluator["name"], "evaluator_version": evaluator["version"],
            "data_mapping": {"response": "{{item.sample.output_text}}", "ground_truth": "{{item.ground_truth}}"}}]}
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
    import campaign
    prefix = "mapped-canary" if mapped else "canary"
    identity = json.loads(evaluator_path(prefix + "-run").read_text())
    with ExitStack() as stack:
        _, client = connect(stack)
        run = client.evals.runs.retrieve(run_id=identity["id"], eval_id=identity["eval_id"])
        rows = campaign.evaluation_rows(client, identity["eval_id"], identity["id"], 3, EVENTS, retain)
        result = {"run": run.model_dump(mode="json"), "rows": rows, "passed": False}
        EVENTS.append({"operation": "native_canary_readback", "result": result})
        if run.status not in ("completed", "failed", "canceled", "cancelled"):
            return result
        definition = client.evals.retrieve(identity["eval_id"]).model_dump(mode="json")
        result["definition"] = definition
        expected_definition = json.loads(evaluator_path(prefix + "-intent").read_text())
        check_canary_criteria(definition.get("testing_criteria"), expected_definition["testing_criteria"])
        if (definition.get("id") != identity["eval_id"]
                or run.id != identity["id"] or run.eval_id != identity["eval_id"] or result["run"].get("error")):
            raise ValueError("canary run/evaluator identity drift")
        check_counts(result["run"].get("result_counts"), total=3, passed=1, failed=2)
        expected = {" Iris-setosa ": 1, "Iris-versicolor": 0, "not-a-label": 0}
        if run.status != "completed" or len(rows) != 3:
            raise ValueError("native evaluator canary did not complete three rows")
        for row in rows:
            response = row["datasource_item"]["sample.output_text" if mapped else "response"]
            metrics = row.get("results", [])
            if (row.get("status") != "completed" or row.get("error") or row.get("eval_id") != identity["eval_id"]
                    or row.get("run_id") != identity["id"] or response not in expected or len(metrics) != 1):
                raise ValueError("native evaluator canary row identity/status mismatch")
            criterion = metrics[0]
            if (criterion.get("name") != "classification_correctness" or criterion.get("metric") != "classification_correctness"
                    or criterion.get("status") != "completed" or criterion.get("type") != "azure_ai_evaluator"
                    or type(criterion.get("score")) not in (int, float) or not math.isfinite(criterion["score"])
                    or criterion["score"] != expected.pop(response) or criterion.get("error")):
                raise ValueError("native evaluator canary score mismatch")
        if expected:
            raise ValueError("missing canary row")
        result["passed"] = True
        evaluator_retain(prefix + "-passed", result)
        return result


def gate():
    if sha256_hex(CONSTITUTION.read_bytes()) != CONSTITUTION_SHA256:
        raise ValueError("live constitution pin drift")
    if importlib.metadata.version("azure-ai-projects") != "2.6.1":
        raise ValueError("native SDK pin drift")
    if RUN_MANIFEST:
        return {"series": RUN_MANIFEST["series"], "constitution": prepare.pin(CONSTITUTION), "historical_campaign": False}
    raise ValueError("pinned migration run manifest required")


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
    actions = {"live-check": gate, "capabilities": capabilities,
               "evaluator-register": evaluator_register, "evaluator-canary": evaluator_canary,
               "canary-readback": canary_readback, "manifest-check": gate, "existing-job-parity": existing_job_parity}
    actions.update({"mapped-canary": mapped_canary, "mapped-canary-readback": lambda: canary_readback(mapped=True)})
    actions.update({"build": lambda: hosting.build(sys.modules[__name__]),
                    "deploy": lambda: hosting.deploy(sys.modules[__name__], previous_path=args.previous, previous_sha256=args.previous_sha256),
                    "runtime-canary": lambda: campaign.cancellation_canary(sys.modules[__name__]) if args.probe == "cancellation" else campaign.runtime_canary(sys.modules[__name__]),
                    "baseline-route-canary": lambda: campaign.baseline_route_canary(sys.modules[__name__]),
                    "inspect-runtime": lambda: campaign.inspect_runtime(sys.modules[__name__]),
                    "runtime-logs": lambda: campaign.runtime_logs(sys.modules[__name__]),
                    "baseline-validation": lambda: campaign.baseline_validation(sys.modules[__name__]),
                    "model-inventory": lambda: campaign.model_inventory(sys.modules[__name__]),
                    "provision-optimizer-model": lambda: campaign.provision_optimizer_model(sys.modules[__name__]),
                    "optimizer-model-canary": lambda: campaign.optimizer_model_canary(sys.modules[__name__]),
                    "optimize": lambda: campaign.optimize(sys.modules[__name__]),
                    "optimizer-readback": lambda: campaign.optimizer_readback(sys.modules[__name__]),
                    "optimizer-reconcile": lambda: campaign.optimizer_operation(sys.modules[__name__]),
                    "optimizer-diagnostics": lambda: campaign.optimizer_diagnostics(sys.modules[__name__]),
                    "optimizer-wait": lambda: campaign.optimizer_wait(sys.modules[__name__]),
                    "collect-candidates": lambda: campaign.collect_candidates(sys.modules[__name__]),
                    "native-row-metrics": lambda: campaign.native_row_metrics(sys.modules[__name__]),
                    "candidate-validation": lambda: campaign.candidate_validation(sys.modules[__name__], args.previous, args.previous_sha256),
                    "observe-validation": lambda: campaign.observe_validation(sys.modules[__name__]),
                    "apply-selected": lambda: campaign.apply_selected(sys.modules[__name__]),
                    "final-version-canaries": lambda: campaign.final_version_canaries(sys.modules[__name__]),
                    "final-holdout": lambda: campaign.final_holdout(sys.modules[__name__])})
    actions["handoff"] = lambda: campaign.handoff(sys.modules[__name__])
    actions.update({"demonstration-decision": lambda: campaign.demonstration_decision(sys.modules[__name__]),
                    "demonstration-build": lambda: hosting.build(sys.modules[__name__], demonstration=True),
                    "demonstration-deploy": lambda: hosting.deploy(sys.modules[__name__], demonstration=True),
                    "demonstration-handoff": lambda: campaign.demonstration_handoff(sys.modules[__name__]),
                    "demonstration-verify": lambda: campaign.demonstration_verify(sys.modules[__name__])})
    for retired in ("final-holdout", "apply-selected", "final-version-canaries", "baseline-validation", "provision-optimizer-model",
                    "demonstration-decision", "demonstration-build", "demonstration-deploy", "demonstration-handoff", "demonstration-verify", "handoff"):
        actions.pop(retired, None)
    parser.add_argument("action", choices=tuple(actions))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--previous")
    parser.add_argument("--previous-sha256")
    parser.add_argument("--probe", choices=("cancellation",))
    args = parser.parse_args()
    action = args.action
    configure_run(args.manifest, args.manifest_sha256, action)
    started = datetime.now(timezone.utc)
    clock = time.monotonic()
    loaded_sources = {name: prepare.pin(prepare.ROOT / "deploy" / name)
                      for name in ("live.py", "campaign.py", "hosting.py", "prepare.py")}
    status = "complete"
    try:
        verified = gate()
        result = verified if action == "live-check" else actions[action]()
    except Exception as error:
        status = "failed"
        result = error_summary(error)
    receipt = {"action": action, "status": status, "started_at": started.isoformat(),
               "finished_at": datetime.now(timezone.utc).isoformat(), "seconds": time.monotonic() - clock,
               "constitution": prepare.pin(CONSTITUTION), "source": loaded_sources["live.py"], "loaded_sources": loaded_sources,
               "result": result, "events": EVENTS, "authority": "primary worker evidence; overseer publication pending"}
    name = utc_stamp(started) + "-" + action + ".json"
    retain(name, receipt)
    print(json.dumps({"status": status, "receipt": prepare.pin(prepare.EVIDENCE / name)}))
    return 0 if status == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())