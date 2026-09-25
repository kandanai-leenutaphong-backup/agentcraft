"""Derive the pinned caller files and the baseline env/run manifest from the frozen constitution artifacts.

Usage (from the repository root): python3 -B agentcraft_projects/foundry-agent-package-e2e-20260924/inputs/build_inputs.py [--check]
Writes inputs/*.json and deploy-env/baseline-v1.{env,run.json}, plus deploy-env/optimized-v1.{env,run.json} once the
baseline series holds exactly one select record; prints every sha256. Constitution rev 2 adds the graded search
evaluator, inputs/*-v2.json and deploy-env/optimize-v2.{env,run.json}, then deploy-env/optimized-v2.{env,run.json}
once the optimize-v2 series holds exactly one select record. `--check` rewrites nothing and
exits 1 when any file would change. Targets only; no secret enters any file.
"""

import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
REPO = PROJECT.parents[1]
INPUTS, ENV_DIR = PROJECT / "inputs", PROJECT / "deploy-env"
sys.path.insert(0, str(PROJECT / "evaluator"))
import exact_answer  # noqa: E402
import graded_answer  # noqa: E402

FROZEN = {"constitution/constitution.rev1.yaml": "616dfbefb665eb940177e631e5473dd0536c7ba0911f5bd3db04e9ad71d50a5f",
          "constitution/constitution.yaml": "22f468f38f49d0473c7315fa37c9c4b5a91c11fa08bb9adddff45d17787f4bc3",
          "dataset/manifest.json": "ee382d5f4d67589d6940ef54c2738d33ba22cf01bd216393a4298c4a5657c242",
          "evaluator/exact_answer.py": "bdf62ad45f978b63ea5090e5fdc314fb0831b234e34253d1182e3ef0a5baf85f",
          "evaluator/canaries.json": "a71c138809be6a4b95abe597899a07101854add535b7eb1545a2028380453c6d",
          "evaluator/graded_answer.py": "ed6b82bcb7f3a93d802dbf844b8bd6f92afe22c22df8af693c9d253ffdcfc66b",
          "evaluator/graded_canaries.json": "318a484d6b87001c6e719a2751e7dc92f97e38660e11f971613e8945b8a7013c",
          "agent/prompts/agent.md": "f8c33ae443446aaa586032812f2b69bf25ac348fd6e41e40429973db5270e8cf"}
GRADE_SHA256 = "b9ae1f41add1d92e89579a18a8f74215b5430c9e152f6251a97631224d67495a"
GRADED_SHA256 = "b256df132fb691769aacf26a55f699bc3a58754442ce6342b9828a5ec08c2cf8"
GRADED = "agentcraft-pkg-e2e-parcel-graded"
EVALUATOR, JUDGE, OPTIMIZER, RUNTIME = ("agentcraft-pkg-e2e-parcel-exact", "gpt-5.6-sol",
                                        "agentcraft-pkg-e2e-optimizer-gpt54", "gpt-5.6-luna")
# First version of a new evaluator name is "1" (O testbed readback); register-evaluator must confirm it.
EVALUATOR_VERSION = "1"
JOURNEYS = (("j1-nonstream-ok", "pq-verification-001", False),
            ("j2-stream-ok", "pq-verification-003", True),
            ("j3-zone-unknown", "pq-verification-007", False),
            ("j4-stream-weight-limit", "pq-verification-002", True))
SUBSCRIPTION = "67255afe-8670-4401-a1b8-df6ca63a3516"
ENV = {"AZURE_TENANT_ID": "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7",
       "AZURE_SUBSCRIPTION_ID": SUBSCRIPTION,
       "FOUNDRY_PROJECT_RESOURCE_ID": (f"/subscriptions/{SUBSCRIPTION}/resourceGroups/personal-llm/providers/"
                                       "Microsoft.CognitiveServices/accounts/han-primary-foundry-resource/"
                                       "projects/han-primary-foundry"),
       "FOUNDRY_PROJECT_ENDPOINT": "https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry",
       "ACR_NAME": "agentcraftdev67255",
       "ACR_LOGIN_SERVER": "agentcraftdev67255.azurecr.io",
       "IMAGE_REPOSITORY": "agentcraft-pkg-e2e-parcel",
       "MODEL_ACCOUNT": "han-primary-foundry-resource",
       "MODEL_RESOURCE_GROUP": "personal-llm",
       "MODEL_DEPLOYMENT": RUNTIME}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump(value) -> bytes:
    return (json.dumps(value, indent=1, sort_keys=True) + "\n").encode()


def rows(split):
    return [json.loads(line) for line in (PROJECT / f"dataset/{split}.jsonl").read_text().splitlines() if line.strip()]


def judge(name, evaluator, version, mapping):
    return {"type": "azure_ai_evaluator", "name": name, "evaluator_name": evaluator, "evaluator_version": version,
            "initialization_parameters": {"deployment_name": JUDGE}, "data_mapping": mapping}


def build() -> dict[str, bytes]:
    drifted = [path for path, digest in FROZEN.items() if sha((PROJECT / path).read_bytes()) != digest]
    grade = exact_answer.grade_source()
    if drifted or sha(grade.encode()) != GRADE_SHA256 or sha(graded_answer.grade_source().encode()) != GRADED_SHA256:
        raise SystemExit("frozen artifact drift: " + ", ".join(drifted or ["grade source"]))
    verification = {row["id"]: row for row in rows("verification")}
    expected = {"ok": [("lookup_zone", None), ("quote_parcel", None)],
                "error-zone-unknown": [("lookup_zone", "E_ZONE_UNKNOWN")],
                "error-weight-limit": [("lookup_zone", None), ("quote_parcel", "E_WEIGHT_LIMIT")]}
    journeys = []
    for journey_id, row_id, stream in JOURNEYS:
        row = verification[row_id]
        tools = [{"name": name, "status": "error", "error_code": code} if code else {"name": name, "status": "ok"}
                 for name, code in expected[row["case"]]]
        journeys.append({"id": journey_id, "input": row["query"], "stream": stream, "expected_tools": tools,
                         "expected_answer": row["ground_truth"], "notes": f"{row_id} ({row['case']})"})
    canaries = json.loads((PROJECT / "evaluator/canaries.json").read_text())["canaries"]
    evaluator = {
        "name": EVALUATOR, "metric": "exact", "display_name": "Parcel quote exact answer",
        "description": ("Frozen grade() from evaluator/exact_answer.py (registered source sha256 " + GRADE_SHA256
                        + "); 1 when stripped output equals ground_truth, else 0."),
        "code_text": grade, "code_sha256": GRADE_SHA256,
        "data_schema": {"type": "object", "properties": {"response": {"type": "string"},
                                                         "ground_truth": {"type": "string"}},
                        "required": ["response", "ground_truth"]},
        "canary": {"criterion_name": "exact", "match_field": "sample.output_text",
                   "item_schema": {"type": "object", "properties": {"sample.output_text": {"type": "string"},
                                                                    "ground_truth": {"type": "string"}},
                                   "required": ["sample.output_text", "ground_truth"]},
                   "data_mapping": {"response": "{{item.sample.output_text}}", "ground_truth": "{{item.ground_truth}}"},
                   "cases": [{"item": case["item"], "expected": case["expected"]} for case in canaries]}}
    criteria = {
        "name": "agentcraft-pkg-e2e-parcel-baseline-validation", "item_fields": ["query", "ground_truth"],
        "wait_seconds": 1800,
        "testing_criteria": [
            {"type": "azure_ai_evaluator", "name": "exact", "evaluator_name": EVALUATOR,
             "evaluator_version": EVALUATOR_VERSION,
             "data_mapping": {"response": "{{sample.output_text}}", "ground_truth": "{{item.ground_truth}}"}},
            judge("tool_call_success", "builtin.tool_call_success", "13",
                  {"response": "{{sample.output_items}}", "tool_definitions": "{{sample.tool_definitions}}"}),
            judge("tool_call_accuracy", "builtin.tool_call_accuracy", "15",
                  {"query": "{{item.query}}", "response": "{{sample.output_items}}",
                   "tool_calls": "{{sample.tool_calls}}", "tool_definitions": "{{sample.tool_definitions}}"})]}
    optimization = {"evaluators": [{"name": EVALUATOR, "version": EVALUATOR_VERSION}],
                    "optimization_model": OPTIMIZER, "max_candidates": 3, "eval_model": JUDGE,
                    "optimization_config": {"system_prompt": (PROJECT / "agent/prompts/agent.md").read_text(),
                                            "skills": [], "tools": []},
                    # Submission run returns unsettled after ~60 s; rerun optimize to resume polling, never resubmit.
                    "wait_seconds": 60}
    rule = {"status": "frozen", "score": "avg_score", "eligibility": "strictly_above_baseline",
            "tie_break": "earliest_observation", "fallback": "baseline",
            "demonstration": {"allowed": True, "label": "demonstration"}}
    files = {"inputs/journeys.json": dump({"journeys": journeys}), "inputs/criteria.json": dump(criteria),
             "inputs/evaluator.json": dump(evaluator), "inputs/optimization.json": dump(optimization),
             "inputs/selection-rule.json": dump(rule)}
    env = ("# Targets for series pkg-e2e-baseline-v1; identifiers only, Entra auth only.\n"
           + "".join(f"{key}={value}\n" for key, value in ENV.items())).encode()
    files["deploy-env/baseline-v1.env"] = env
    rel = PROJECT.relative_to(REPO).as_posix()
    manifest = {"schema_version": 1, "purpose": "foundry-hosted-agent", "series": "pkg-e2e-baseline-v1",
                "agent": "agentcraft-pkg-e2e-parcel",
                "actions": ["preflight", "build", "deploy", "invoke", "verify", "register-evaluator", "evaluate",
                            "optimize", "select", "inspect", "logs"],
                "env_sha256": sha(env), "previous_version": None, "previous_image": None,
                "package_dir": f"{rel}/agent",
                "inputs": {"journeys": sha(files["inputs/journeys.json"]), "criteria": sha(files["inputs/criteria.json"]),
                           "evaluator": sha(files["inputs/evaluator.json"]),
                           "optimization": sha(files["inputs/optimization.json"]),
                           "selection_rule": sha(files["inputs/selection-rule.json"]),
                           "items": sha((PROJECT / "dataset/validation.jsonl").read_bytes()),
                           "train": sha((PROJECT / "dataset/train.jsonl").read_bytes()),
                           "validation": sha((PROJECT / "dataset/validation.jsonl").read_bytes())}}
    files["deploy-env/baseline-v1.run.json"] = dump(manifest)
    files.update(optimized_series(criteria, files, rel))
    files.update(revision_two(criteria, evaluator, optimization, rule, files, rel))
    return files


def revision_two(criteria, evaluator, optimization, rule, files, rel) -> dict[str, bytes]:
    """Rev 2: graded search evaluator beside exact, max_stalls 10, one job on version 1 (series pkg-e2e-optimize-v2),
    selection by the native exact criterion; the promoted series appears once that job's select record exists."""
    canaries = json.loads((PROJECT / "evaluator/graded_canaries.json").read_text())["canaries"]
    graded = {
        **evaluator, "name": GRADED, "metric": "graded", "display_name": "Parcel quote graded answer similarity",
        "description": ("Search guidance only (acceptance stays agentcraft-pkg-e2e-parcel-exact). Registered grade() "
                        "from evaluator/graded_answer.py (source sha256 " + GRADED_SHA256 + "): 1.0 when the stripped "
                        "reply equals the reference answer line (TOTAL_CENTS=<integer cents> or ERROR=<error code>), "
                        "else 0.9 x LCS similarity to it."),
        "code_text": graded_answer.grade_source(), "code_sha256": GRADED_SHA256,
        "canary": {**evaluator["canary"], "criterion_name": "graded",
                   "cases": [{"item": case["item"], "expected": case["expected"]} for case in canaries]}}
    out = {"inputs/evaluator-graded-v2.json": dump(graded),
           "inputs/optimization-v2.json": dump({
               **optimization, "max_stalls": 10, "wait_seconds": 150,
               "evaluators": [{"name": GRADED, "version": EVALUATOR_VERSION},
                              {"name": EVALUATOR, "version": EVALUATOR_VERSION}]}),
           "inputs/selection-rule-v2.json": dump({**rule, "score": "criterion_mean", "criterion": EVALUATOR})}
    reports = {"optimized-v2-validation": "agentcraft-pkg-e2e-parcel-optimized-v2-validation",
               "optimized-v2-verification": "agentcraft-pkg-e2e-parcel-optimized-v2-verification"}
    out.update({f"inputs/criteria-{key}.json": dump({**criteria, "name": name}) for key, name in reports.items()})
    baseline = PROJECT / "records/live/pkg-e2e-baseline-v1"
    deployed = json.loads(next(baseline.glob("deploy-*-active.json")).read_text())
    env = ("# Targets for series pkg-e2e-optimize-v2; identifiers only, Entra auth only.\n"
           + "".join(f"{key}={value}\n" for key, value in ENV.items())).encode()
    out["deploy-env/optimize-v2.env"] = env
    out["deploy-env/optimize-v2.run.json"] = dump({
        "schema_version": 1, "purpose": "foundry-hosted-agent", "series": "pkg-e2e-optimize-v2",
        "agent": "agentcraft-pkg-e2e-parcel", "actions": ["preflight", "register-evaluator", "optimize", "select", "inspect"],
        "env_sha256": sha(env), "previous_version": deployed["version"],
        "previous_image": deployed["definition"]["container_configuration"]["image"], "package_dir": f"{rel}/agent",
        "inputs": {"evaluator": sha(out["inputs/evaluator-graded-v2.json"]),
                   "optimization": sha(out["inputs/optimization-v2.json"]),
                   "selection_rule": sha(out["inputs/selection-rule-v2.json"]),
                   "train": sha((PROJECT / "dataset/train.jsonl").read_bytes()),
                   "validation": sha((PROJECT / "dataset/validation.jsonl").read_bytes())}})
    # A baseline decision promotes nothing; only the one selected/demonstration record pins the promoted series.
    selects = sorted(path for path in (PROJECT / "records/live/pkg-e2e-optimize-v2").glob("select-*.json")
                     if not path.name.endswith("-baseline.json"))
    if len(selects) != 1:
        return out
    latest = json.loads(next((PROJECT / "records/live/pkg-e2e-optimized-v1").glob("deploy-*-active.json")).read_text())
    env = ("# Targets for series pkg-e2e-optimized-v2; identifiers only, Entra auth only.\n"
           + "".join(f"{key}={value}\n" for key, value in ENV.items())).encode()
    out["deploy-env/optimized-v2.env"] = env
    out["deploy-env/optimized-v2.run.json"] = dump({
        "schema_version": 1, "purpose": "foundry-hosted-agent", "series": "pkg-e2e-optimized-v2",
        "agent": "agentcraft-pkg-e2e-parcel",
        "actions": ["preflight", "deploy", "invoke", "verify", "evaluate", "inspect", "logs"],
        "env_sha256": sha(env), "previous_version": latest["version"],
        "previous_image": latest["definition"]["container_configuration"]["image"], "package_dir": f"{rel}/agent",
        "inputs": {"journeys": sha(files["inputs/journeys.json"]), "candidate_record": sha(selects[0].read_bytes()),
                   "criteria": sorted(sha(out[f"inputs/criteria-{key}.json"]) for key in reports),
                   "items": sorted(sha((PROJECT / f"dataset/{split}.jsonl").read_bytes())
                                   for split in ("validation", "verification"))}})
    return out


def optimized_series(criteria, files, rel) -> dict[str, bytes]:
    """S5/S6 series: same criteria renamed per report; emitted only once the baseline `select` record exists."""
    reports = {"optimized-validation": "agentcraft-pkg-e2e-parcel-optimized-validation",
               "optimized-verification": "agentcraft-pkg-e2e-parcel-optimized-verification",
               "baseline-verification": "agentcraft-pkg-e2e-parcel-baseline-verification"}
    out = {f"inputs/criteria-{key}.json": dump({**criteria, "name": name}) for key, name in reports.items()}
    criteria_pins = sorted(sha(data) for data in out.values())
    baseline = PROJECT / "records/live/pkg-e2e-baseline-v1"
    selects = sorted(baseline.glob("select-*.json"))
    if len(selects) != 1:
        return out
    deployed = json.loads(next(baseline.glob("deploy-*-active.json")).read_text())
    selected = json.loads(selects[0].read_text())
    retained = json.loads((baseline / selected["optimization_record"]).read_text())
    # Baseline-only job: the demonstration hosts the job's best (only) candidate, instructions only; never "optimized".
    best = retained["job"]["result"]["best"]
    config = retained["configs"][best]
    out["inputs/optimization-config-demonstration.json"] = dump({"instructions": config["config"]["instructions"]})
    out["inputs/optimization-config-demonstration.provenance.json"] = dump({
        "label": "demonstration", "not_optimized": True, "decision": selected["decision"],
        "select_record": selects[0].name, "job_id": retained["job_id"], "candidate_id": best,
        "candidate_is_baseline": best == retained["listing"]["baseline"], "candidate_config_sha256": config["sha256"],
        "candidate_fields": sorted(config["config"]), "deployed_fields": ["instructions"],
        "dropped_fields": {key: value for key, value in sorted(config["config"].items()) if key != "instructions"},
        "purpose": "prove S5 redeploy (OPTIMIZATION_CONFIG overlay, same image) and S6 re-verification"})
    env = ("# Targets for series pkg-e2e-optimized-v1; identifiers only, Entra auth only.\n"
           + "".join(f"{key}={value}\n" for key, value in ENV.items())).encode()
    out["deploy-env/optimized-v1.env"] = env
    manifest = {"schema_version": 1, "purpose": "foundry-hosted-agent", "series": "pkg-e2e-optimized-v1",
                "agent": "agentcraft-pkg-e2e-parcel",
                "actions": ["preflight", "deploy", "invoke", "verify", "evaluate", "inspect", "logs"],
                "env_sha256": sha(env), "previous_version": deployed["version"],
                "previous_image": deployed["definition"]["container_configuration"]["image"],
                "package_dir": f"{rel}/agent",
                "inputs": {"journeys": sha(files["inputs/journeys.json"]),
                           "candidate_record": sha(selects[0].read_bytes()),
                           "optimization_config": sha(out["inputs/optimization-config-demonstration.json"]),
                           "criteria": criteria_pins,
                           "items": sorted(sha((PROJECT / f"dataset/{split}.jsonl").read_bytes())
                                           for split in ("validation", "verification"))}}
    out["deploy-env/optimized-v1.run.json"] = dump(manifest)
    return out


def main() -> int:
    check = "--check" in sys.argv[1:]
    changed = []
    for name, data in build().items():
        path = PROJECT / name
        if not path.exists() or path.read_bytes() != data:
            changed.append(name)
            if not check:
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(data)
        print(sha(data), name)
    if check and changed:
        print("would change: " + ", ".join(changed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
