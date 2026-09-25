"""Series pkg-e2e-datasets-v1: eval and optimization data as native Foundry Datasets (thin; foundry_ops only).

Usage (repository root; `az account set --subscription <SUB>` first):
  python3 -B <this> preflight | register | eval | compare | opt-submit | opt-poll | negative
Each subcommand is bounded and resumable from the ledger in this directory; no deletion, no RBAC, no deployment.
"""

from __future__ import annotations

from contextlib import ExitStack
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[2]
ROOT = PACKAGE.parents[1]
sys.path.insert(0, str(ROOT / "libraries" / "foundry-ops" / "src"))

from foundry_ops.core import EvidenceLedger, RefusedError, error_summary, sha256_file, sha256_hex, utc_stamp  # noqa: E402
from foundry_ops.data import (dataset_version_label, list_auto_datasets, project_jsonl, readback_dataset,  # noqa: E402
                              register_jsonl_dataset)
from foundry_ops.evaluation import run_agent_eval  # noqa: E402
from foundry_ops.optimization import list_candidates, optimization_job, submit_optimization, wait_optimization  # noqa: E402

TENANT = "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7"
SUBSCRIPTION = "67255afe-8670-4401-a1b8-df6ca63a3516"
ENDPOINT = "https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry"
AGENT = "agentcraft-pkg-e2e-parcel"
EVAL_VERSION = "3"
FIELDS = ["query", "ground_truth"]
SPLITS = ("train", "validation", "verification")
INLINE = PACKAGE / "records/live/pkg-e2e-optimized-v2"
INLINE_KEY = "src-d51b5dad684649d0f0202d79-pkg-95667431e925f468-v3-5e13452018b37846"
INLINE_RUN = "evalrun_4f07cf9e550e4d1099030223ec55882d"
OPT_INTENT = PACKAGE / ("records/live/pkg-e2e-optimize-v2/"
                        "optimize-src-d51b5dad684649d0f0202d79-pkg-95667431e925f468-v1-e44c64a49fc5f0bc-intent.json")
OPT_INPUT = PACKAGE / "inputs/optimization-v2.json"
EVAL_KEY = "datasets-v1-validation-v3"
OPT_KEY = "datasets-v1-reference-v1"
LEDGER = EvidenceLedger(HERE)


def retain(action: str, result: dict) -> None:
    LEDGER.retain(f"{utc_stamp()}-{action}.json", {"action": action, **result})
    print(json.dumps({"action": action, **{k: v for k, v in result.items() if k != "rows"}}, indent=1)[:4000])


def rows(split: str) -> list[dict]:
    return [json.loads(line) for line in (PACKAGE / "dataset" / f"{split}.jsonl").read_text().splitlines() if line]


def ref(split: str) -> dict:
    name = f"agentcraft-pkg-e2e-{split}"
    version = dataset_version_label(sha256_hex(project_jsonl(rows(split), fields=FIELDS)))
    return LEDGER.read(f"dataset-{name}-{version}-result.json")


def clients(stack: ExitStack):
    account = subprocess.run(["az", "account", "show", "--query", "id", "-o", "tsv"], capture_output=True, text=True,
                             timeout=60).stdout.strip()
    if account != SUBSCRIPTION:
        raise SystemExit(f"active subscription {account!r}; run az account set --subscription {SUBSCRIPTION}")
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential
    credential = stack.enter_context(AzureCliCredential(tenant_id=TENANT, process_timeout=30))
    return stack.enter_context(AIProjectClient(endpoint=ENDPOINT, credential=credential))


def preflight(project) -> None:
    versions = {v: (lambda d: {"status": d.get("status"), "id": d.get("id")})(
        project.agents.get_version(agent_name=AGENT, agent_version=v).as_dict()) for v in ("1", EVAL_VERSION)}
    retain("preflight", {"agent_versions": versions, "auto_datasets": len(list_auto_datasets(project))})


def register(project) -> None:
    results = {}
    for split in SPLITS:
        registered = register_jsonl_dataset(project, LEDGER, name=f"agentcraft-pkg-e2e-{split}", rows=rows(split),
                                            fields=FIELDS, description=f"agentcraft pkg-e2e {split} split; {FIELDS}")
        readback = readback_dataset(project, name=registered["name"], version=registered["version"],
                                    expected_sha256=registered["sha256"])
        results[split] = {"registered": registered, "readback": readback,
                          "source": {"path": f"dataset/{split}.jsonl",
                                     "sha256": sha256_file(PACKAGE / "dataset" / f"{split}.jsonl")}}
    retain("register", {"fields": FIELDS, "datasets": results})


def evaluate(project) -> None:
    intent = json.loads((INLINE / f"eval-{INLINE_KEY}-intent.json").read_text())["request"]
    dataset = ref("validation")
    started = time.monotonic()
    with project.get_openai_client(max_retries=0, timeout=150) as client:
        result = run_agent_eval(client, LEDGER, key=EVAL_KEY, name="agentcraft-pkg-e2e-parcel-datasets-v1-validation",
                                agent_name=AGENT, agent_version=EVAL_VERSION, testing_criteria=intent["testing_criteria"],
                                item_schema=intent["data_source_config"]["item_schema"], dataset=dataset,
                                attempts=40, interval=10, seconds=900,
                                on_event=lambda e: print(json.dumps(e), flush=True))
    retain("evaluate", {"dataset": dataset, "criteria_source_sha256": sha256_file(INLINE / f"eval-{INLINE_KEY}-intent.json"),
                        "seconds": round(time.monotonic() - started, 1),
                        **{k: v for k, v in result.items() if k != "rows"}})


def _per_row(summary: dict) -> dict:
    table = {}
    for row in summary["rows"]:
        results = {r["name"]: ("errored" if r.get("status") != "completed" or r.get("error") else r.get("passed"))
                   for r in row.get("results") or []}
        table[row["datasource_item"]["query"]] = results
    return table


def compare(_project) -> None:
    dataset_run = LEDGER.read(f"eval-{EVAL_KEY}-summary.json")
    inline_run = json.loads((INLINE / f"eval-{INLINE_KEY}-summary.json").read_text())
    if inline_run["run_id"] != INLINE_RUN:
        raise SystemExit("inline run identity drift")
    new, old = _per_row(dataset_run), _per_row(inline_run)
    queries = {row["query"] for row in rows("validation")}
    per_criterion = {}
    for name in dataset_run["summary"]:
        differ = sorted(q for q in queries if new.get(q, {}).get(name) != old.get(q, {}).get(name))
        per_criterion[name] = {"dataset": dataset_run["summary"][name], "inline": inline_run["summary"][name],
                               "differing_rows": len(differ), "differing_queries": differ}
    retain("compare", {"dataset_run": {"eval_id": dataset_run["eval_id"], "run_id": dataset_run["run_id"],
                                       "result_counts": dataset_run["result_counts"]},
                       "inline_run": {"eval_id": inline_run["eval_id"], "run_id": inline_run["run_id"],
                                      "result_counts": inline_run["result_counts"]},
                       "same_row_membership": set(new) == set(old) == queries, "rows": len(queries),
                       "criteria": per_criterion})


def opt_submit(project) -> None:
    config = json.loads(OPT_INPUT.read_text())
    prior = json.loads(OPT_INTENT.read_text())["request"]["inputs"]
    job = optimization_job(AGENT, prior["agent"]["agent_version"], train_dataset=ref("train"),
                           validation_dataset=ref("validation"), evaluators=config["evaluators"],
                           optimization_model=config["optimization_model"], max_candidates=3,
                           eval_model=config["eval_model"], max_stalls=config["max_stalls"],
                           optimization_config=config["optimization_config"])
    inline_options = {k: v for k, v in prior.items() if k not in ("train_dataset", "validation_dataset")}
    job_options = {k: v for k, v in job["inputs"].items() if k not in ("train_dataset", "validation_dataset")}
    if job_options != inline_options:
        raise SystemExit("request drift from optimize-v2 beyond dataset form")
    if not LEDGER.exists(f"optimize-{OPT_KEY}-identity.json"):
        LEDGER.retain(f"optimize-{OPT_KEY}-auto-datasets-before.json", {"auto": list_auto_datasets(project)})
    submitted = submit_optimization(project, LEDGER, key=OPT_KEY, job=job)
    retain("opt-submit", {"job_id": submitted["job_id"], "operation_id": submitted["operation_id"],
                          "status": submitted["job"].get("status"), "inputs": job["inputs"]})


def opt_poll(project) -> None:
    identity = LEDGER.read(f"optimize-{OPT_KEY}-identity.json")
    polled = wait_optimization(project, job_id=identity["job_id"], seconds=170, interval=20)
    job = polled.value
    result = {"job_id": identity["job_id"], "settled": polled.settled, "status": job.get("status"),
              "progress": job.get("progress"), "error": job.get("error")}
    if polled.settled:
        before = {d["name"] for d in LEDGER.read(f"optimize-{OPT_KEY}-auto-datasets-before.json")["auto"]}
        after = list_auto_datasets(project)
        hexid = identity["job_id"].removeprefix("opt_")
        new = [d for d in after if d["name"] not in before]
        listing = list_candidates(job, require_generated=False) if job.get("status") in ("succeeded", "completed") else None
        intent = LEDGER.read(f"optimize-{OPT_KEY}-intent.json")
        result.update({"submitted_at": intent["recorded_at"], "job_native": job,
                       "candidates": listing and [{k: c[k] for k in ("candidate_id", "is_baseline", "avg_score",
                                                                      "avg_tokens", "eval_run_id")}
                                                  for c in listing["candidates"]],
                       "best": listing and listing["best"], "generated": listing and listing["generated"],
                       "auto_datasets_new": new,
                       "opt_inline_for_job": [d for d in after if d["name"].startswith("opt-inline-" + hexid)]})
    retain("opt-poll", result)


def negative(project) -> None:
    valid = ref("validation")
    missing = "sha256-" + "0" * 32
    try:
        readback_dataset(project, name=valid["name"], version=missing, expected_sha256=valid["sha256"])
    except RefusedError as error:
        retain("negative", {"name": valid["name"], "version": missing, "refused": True, "error": error_summary(error),
                            "code": error.code})
        return
    raise SystemExit("nonexistent dataset version was not refused")


COMMANDS = {"preflight": preflight, "register": register, "eval": evaluate, "compare": compare,
            "opt-submit": opt_submit, "opt-poll": opt_poll, "negative": negative}

if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit("usage: datasets_v1.py " + " | ".join(COMMANDS))
    with ExitStack() as stack:
        COMMANDS[sys.argv[1]](None if sys.argv[1] == "compare" else clients(stack))
