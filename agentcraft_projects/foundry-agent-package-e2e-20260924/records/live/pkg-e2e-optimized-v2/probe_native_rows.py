"""Read-only probe: native rows of the retained baseline-only job's candidate eval run (criterion names, row fields).

Usage (repository root): timeout 200 python3 -B agentcraft_projects/foundry-agent-package-e2e-20260924/records/live/pkg-e2e-optimized-v2/probe_native_rows.py
Writes probe-native-rows.json beside this file. No write to Azure; no inference.
"""

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[4]
sys.path.insert(0, str(REPO / "libraries/foundry-ops/src"))
from foundry_ops.core import sanitize, to_plain  # noqa: E402
from foundry_ops.evaluation import collect_rows  # noqa: E402

ENDPOINT = "https://han-primary-foundry-resource.services.ai.azure.com/api/projects/han-primary-foundry"
TENANT = "c79ab2bb-79cb-47f1-b4da-b6852fe45ff7"
EVAL_ID, RUN_ID = "eval_4756a02875e54d258dbf0447f651aa30", "evalrun_fbd15ed735664260ac4b4dbec8be8e21"


def main() -> int:
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    with AzureCliCredential(tenant_id=TENANT, process_timeout=30) as credential, \
            AIProjectClient(endpoint=ENDPOINT, credential=credential, retry_total=0) as project, \
            project.get_openai_client(max_retries=0, timeout=60) as client:
        evaluation = to_plain(client.evals.retrieve(EVAL_ID))
        run = to_plain(client.evals.runs.retrieve(run_id=RUN_ID, eval_id=EVAL_ID))
        rows = collect_rows(client, eval_id=EVAL_ID, run_id=RUN_ID, expected_count=200, partial_on_error=True)
    out = {"eval": evaluation, "run": run, "row_count": len(rows), "rows": rows}
    (HERE / "probe-native-rows.json").write_text(json.dumps(sanitize(out), indent=1, sort_keys=True, default=str) + "\n")
    print(json.dumps({"rows": len(rows), "criteria": [c.get("name") for c in evaluation.get("testing_criteria") or []],
                      "run_status": run.get("status"), "counts": run.get("result_counts")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
