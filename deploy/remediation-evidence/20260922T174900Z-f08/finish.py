"""Prepare F09 publication input and a derived report; never publish records."""

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import html
import importlib.util
import json
from pathlib import Path
import tarfile
from urllib.parse import quote

import evidence

ROOT, OUT = evidence.ROOT, evidence.OUT
PROJECT = ROOT / "agentcraft_projects/foundry-official-integration-20260922"
H = ROOT / "testbeds/foundry-hosted-agents/deploy/records/migration-h-v1"
E = ROOT / "testbeds/foundry-agent-evaluation/deploy/records/migration-e-v1"
O = ROOT / "testbeds/foundry-agent optimization/deploy/evidence"


def load(path):
    return json.loads(path.read_text())


def ref(path):
    payload = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)}


def archive(path):
    with tarfile.open(path) as bundle:
        return {member.name: bundle.extractfile(member).read() for member in bundle if member.isfile()}


def prepare():
    evidence.PREVIOUS.save("spec-before-f08-closeout.md", (ROOT / "specs/20260922_FOUNDRY_OFFICIAL_INTEGRATION_REMEDIATION.md").read_bytes())
    snapshot = evidence.PREVIOUS.snapshot("final")
    before = archive(OUT / "before-f08-source.tar.gz")
    after = archive(OUT / "final-source.tar.gz")
    changes, patch = [], []
    for name in sorted(before.keys() | after.keys()):
        if before.get(name) == after.get(name):
            continue
        changes.append({"path": name, "before_sha256": hashlib.sha256(before[name]).hexdigest() if name in before else None,
                        "after_sha256": hashlib.sha256(after[name]).hexdigest() if name in after else None,
                        "recovery": "exact named member in before-f08-source.tar.gz / final-source.tar.gz"})
        patch.extend(difflib.unified_diff(before.get(name, b"").decode().splitlines(True), after.get(name, b"").decode().splitlines(True),
                                         fromfile="before/" + name, tofile="after/" + name))
    evidence.PREVIOUS.save("source-changes.patch", "".join(patch).encode())
    specification = importlib.util.spec_from_file_location("previous_finish", ROOT / "deploy/remediation-evidence/20260922T163453Z-f02-f07/finish.py")
    previous = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(previous)
    original = archive(ROOT / "deploy/remediation-evidence/20260922T163453Z-f02-f07/before-f02-source.tar.gz")
    measurements = {"f08_before": previous.production(before), "final": previous.production(after), "f02_before": previous.production(original),
                    "claim": "No effort-savings or net code-reduction claim. Identical production scope; tests/docs/evidence excluded."}
    evidence.PREVIOUS.save("measurements.json", measurements)
    return evidence.PREVIOUS.save("source-changes.json", {"changes": changes, "before": ref(OUT / "before-f08-source.json"),
        "after": snapshot, "diff": ref(OUT / "source-changes.patch"), "recovery_verified": True})


def finish():
    settlement_path = sorted(OUT.glob("*-settlement-live.json"))[-1]
    settlement = load(settlement_path)
    assert settlement["settled"] and not settlement["pending_operations"]
    commands = []
    for path in sorted(OUT.glob("*.json")):
        value = load(path)
        if "command" in value and "exit_code" in value:
            commands.append({"receipt": ref(path), "command": value["command"], "exit_code": value["exit_code"],
                             "seconds": value["seconds"], "output": value["output"]})
    command_ref = evidence.PREVIOUS.save("command-inventory.json", commands)
    tests = {}
    for owner, path in {
        "H": ROOT / "testbeds/foundry-hosted-agents/deploy/records/20260922T190603834396Z-test.json",
        "E": ROOT / "testbeds/foundry-agent-evaluation/deploy/records/20260922T181652333042Z-validate.json",
        "O": O / "20260922T190705988425Z-test.json",
    }.items():
        value = load(path)
        assert value["status"] == "complete"
        tests[owner] = {"tests": value["result"]["tests"], "receipt": ref(path)}
    hosted = {}
    for tool, filename in {"nonce_digest": "20260922T183659245318Z-verify.json",
                           "nonce_statistics": "20260922T184257733774Z-verify.json",
                           "nonce_reverse": "20260922T184312034351Z-verify.json"}.items():
        path = H / filename
        result = load(path)["result"]
        assert result["readback"] and result["anonymous_status"] in (401, 403)
        hosted[tool] = {"receipt": ref(path), "response_id": result["response_id"], "version": result["version"],
                        "source_sha256": result["tool_evidence"]["source_sha256"],
                        "config_sha256": result["tool_evidence"]["config_sha256"], "anonymous_status": result["anonymous_status"]}
    evaluation_path = E / "20260922T181808468298Z-verify.json"
    evaluation = load(evaluation_path)["result"]
    assert evaluation["accepted"] and evaluation["complete"] and evaluation["proof_passed"] == 3
    grader = {}
    for name in ("canary", "mapped-canary"):
        path = O / "migration-o-v1" / ("evaluator-7f20a5cda0a9-" + name + "-passed.json")
        value = load(path)
        assert value["passed"] and sorted(row["results"][0]["score"] for row in value["rows"]) == [0, 0, 1]
        grader[name] = {"receipt": ref(path), "eval_id": value["run"]["eval_id"], "run_id": value["run"]["id"],
                        "counts": value["run"]["result_counts"], "scores": [row["results"][0]["score"] for row in value["rows"]]}
    independent_path = O / "migration-o-v3/candidate-validation-metrics.json"
    independent = load(independent_path)
    native_path = O / "migration-o-v3/migration-o-v3-recomputed-metrics.json"
    native = load(native_path)
    assert independent["complete_independent_validation"] and len(independent["candidates"]) == 3
    candidates = []
    for candidate in independent["candidates"]:
        assert len(candidate["rows"]) == 3 and all(row["stored_readback"] for row in candidate["rows"])
        candidates.append({"candidate_id": candidate["candidate_id"], "version": candidate["deployment"]["version"],
            "image": candidate["deployment"]["build"]["image"], "instructions_sha256": candidate["instructions_sha256"],
            "native_config_sha256": ref(O / "migration-o-v3" / (candidate["candidate_id"] + "-config.json"))["sha256"],
            "independent_metrics": candidate["metrics"], "native": candidate["native"],
            "stored_response_ids": [row["response"]["id"] for row in candidate["rows"]]})
    cancellation = {}
    for owner, path in {"H": H / "20260922T185121107291Z-invoke.json",
                         "O": O / "migration-o-v1/20260922T184643240858Z-runtime-canary.json"}.items():
        result = load(path)["result"]
        assert result["cancelled"] and result["readback"]["status"] == "cancelled" and not result["readback"]["output"]
        cancellation[owner] = {"receipt": ref(path), "response_id": result["response_id"], "status": "cancelled",
                               "completed_output_absent": True, "cleanup": "local handler tests; provider log marker not observed"}
    matrix = {"F00": {"status": "passed_prior_checkpoint", "evidence": ref(ROOT / "deploy/remediation-evidence/20260922T151500Z-f00/handoff.json")},
        "F01": {"status": "passed_prior_checkpoint_and_live_locked_builds", "evidence": ref(PROJECT / "records/v2/20260922T163403830370Z-f01-uv-dependency-checkpoint/record.json")},
        "F02": {"status": "passed", "evidence": grader},
        "F03": {"status": "passed", "evidence": [ref(evaluation_path), ref(native_path), ref(independent_path)]},
        "F04": {"status": "passed", "evidence": hosted},
        "F05": {"status": "passed", "job_id": native["job_id"], "candidate_count": 3, "independent_rows": 9},
        "F06": {"status": "passed", "note": "separate immutable manifests; old actions retired; dropped response guards and stored-response recovery"},
        "F07": {"status": "passed", "evidence": ref(OUT / "measurements.json")},
        "F08": {"status": "complete", "note": "H/E/O exact-artifact integration; no prediction-quality claim"},
        "F09": {"status": "prepared_not_published", "evidence": ref(settlement_path)}}
    conditional = load(ROOT / "deploy/remediation-evidence/20260922T163453Z-f02-f07/conditional-decisions.json")
    conditional["C04"].update(status="implemented_live_verified", decision="Direct CLI queued run identity, no inventory-difference submit association; source/tag/digest readback and dropped-response refusal.",
                              evidence=tests, limitation="No deliberately dropped production write or unrelated billable concurrent build; mocked refusal/concurrency association plus actual unknown-run recovery.")
    conditional["C09"].update(status="implemented_live_verified", evidence=cancellation,
                              limitation="Native canceled readback/no completed output is live. Task/client cleanup tested locally; provider cleanup marker unavailable. No hard-kill durability or rollback claim.")
    matrix.update(conditional)
    matrix_ref = evidence.PREVIOUS.save("acceptance-matrix.json", matrix)
    failures = ["Initial H build stdout was null; run crf reconciled by retained archive/tag/digest, never resubmitted.",
        "H persisted metadata null became {}; exact empty normalization repaired readback without inference replay.",
        "Evaluator registration retained exact code/schema but service omitted SDK threshold and added empty defaults; existing version reconciled.",
        "E catalogue list/get timestamps differ; exact executable fields retained. E/O service criterion IDs/null fields normalized narrowly.",
        "O synthetic dataset snake-case input was not SDK wire JSON; typed constructor repaired pre-inference failure.",
        "Native jobs v1/v2 settled baseline-only (perfect score/two stalls); retained as failed coverage, not victories.",
        "H v2 cancellation missed completion window; deferred public TextResponse fixed v3. All missed attempts are terminal completed, retained.",
        "Patch tool introduced nesting/indentation errors; immediate tests failed and local repairs passed. Duplicate-header/stale-context patches refused.",
        "New native membership fixture omitted name/metrics/evaluation fields; corrected. Read-only collection inadvertently ran in parallel with a failing test-exit check; no candidate deployment preceded final green gate.",
        "Dropped-build O test initially used wrong temporary repo root; corrected with production containment unchanged.",
        "Bounded provider cleanup logs hit event limit then read timeout; no cleanup-marker claim."]
    gaps = ["MAX requested; effective host effort unverified; tokens/provider cost unknown.",
        "Original mission monotonic ID unavailable; worker start 17:48:02Z does not reset mission start 15:06:18Z/deadline 21:06:18Z.",
        "Initial reads and manual read-only diagnostics are in host session log, not all in command inventory; no complete tool transcript capture claim.",
        "Blocking calls and some read/edit intervals prevented 60-second clock cadence; receipts retain boundary checks.",
        "No Pylance-specific tool available; runtime tests and editor diagnostics used.",
        "No live foreign-principal credential test; caller-side foreign-owner guard and anonymous refusal proven.",
        "No cloud rollback/hard-kill durability proof; no teardown; retained resources incur unknown ongoing cost.",
        "Short signal/SSE adapters and bounded loader-compatible resolver remain; resolver route is not verified public REST documentation.",
        "Intermediate failed edit bytes not separately archived at every attempt; before/after and intermediate recovery archives retained."]
    timing = evidence.clock()
    handoff = {"status": "complete", "objective": "F08 H/E/O exact-artifact integration and F09 settlement preparation",
        "scope": "assigned checkpoint only; authoritative mission closure belongs to overseer",
        "constitution": {"revision": 1, "sha256": "0a7e39fe0b4a62588b24b1f975fd61c1cb42b80ec35a6d1d263bd39c6575e1c8"},
        "decision": {"path": "records/v2/20260922T154739145740Z-execute-remediation-v1/record.json", "sha256": "fd93069ab91f1d6afcc98fd557e3f4d6eb7bf834d537d2faed3c4df83036177b"},
        "prior_checkpoint": {"path": "records/v2/20260922T174652824471Z-f02-f07-local-checkpoint/record.json", "sha256": "48ce14249704447f75ab31f8350079c8c36b0cd6b484ca95100271ed6ae36317"},
        "stage": "test/measure/settlement", "next_transition": "overseer F09 publication and strategic review; no further experiment",
        "hypothesis": "Official SDK lifecycle plus narrow strict adapters preserves protected live workflows and recoverability.",
        "matrix": matrix_ref, "tests": tests, "hosted": hosted, "grader": grader,
        "evaluation": {"receipt": ref(evaluation_path), "identity": evaluation["identity"], "counts": evaluation["aggregate"]["result_counts"],
                       "pins": evaluation["pins"], "proof_passed": 3, "accepted": True},
        "optimization": {"job_id": native["job_id"], "candidates": candidates, "native": ref(native_path), "independent": ref(independent_path),
            "exports": [ref(O / "migration-o-v3/migration-o-v3-native-rows.csv"), ref(O / "migration-o-v3/candidate-validation-metrics.csv")],
            "scope": "shared synthetic development fixtures only; no prediction improvement/generalization",
            "historical_regression": "unchanged: generated 28/30 versus native baseline 29/30; no heldout read/rerun/upload"},
        "cancellation": cancellation, "source_changes": ref(OUT / "source-changes.json"), "measurements": ref(OUT / "measurements.json"),
        "specification": {"before": ref(OUT / "spec-before-f08-closeout.md"), "after": ref(ROOT / "specs/20260922_FOUNDRY_OFFICIAL_INTEGRATION_REMEDIATION.md")},
        "dependency_manifests": {owner: ref(ROOT / path) for owner, path in {
            "H_E": "testbeds/foundry-hosted-agents/deploy/dependency-manifest.json",
            "O": "testbeds/foundry-agent optimization/deploy/dependency-manifest.json"}.items()},
        "recovery": {"before": ref(OUT / "before-f08-source.tar.gz"), "intermediate": ref(OUT / "live-repairs-source.tar.gz"),
                     "after": ref(OUT / "final-source.tar.gz"), "verified_member_bytes": True, "active_tree_restore": "not_performed"},
        "historical_integrity": ref(OUT / "historical-integrity.json"), "commands": command_ref, "settlement": ref(settlement_path),
        "pending_operations": settlement["pending_operations"], "workers": [], "local_background_processes": [],
        "failures": failures, "capture_gaps": gaps, "timing": timing, "mission_start_utc": "2026-09-22T15:06:18Z",
        "deadline_utc": "2026-09-22T21:06:18Z", "penalty_minutes": 0,
        "archival_request": "Overseer publish F08 outcome/F09 settlement using referenced exact bytes; archive large bundles externally if recorder size limits require. No records published by worker."}
    handoff_ref = evidence.PREVIOUS.save("handoff.json", handoff)
    publication = {"kind": "worker-publication-input", "authoritative": False, "status": "f08_complete_f09_prepared",
        "handoff": handoff_ref, "matrix": matrix_ref, "source_changes": ref(OUT / "source-changes.json"),
        "settlement": ref(settlement_path), "command_inventory": command_ref, "tests": tests,
        "historical_integrity": ref(OUT / "historical-integrity.json"), "failures": failures, "capture_gaps": gaps,
        "metrics": {"historical_files_unchanged": 896, "hosted_tools_verified": 3, "evaluation_rows": 3,
                    "native_candidates": 3, "independent_rows": 9, "native_jobs": 3, "baseline_only_jobs": 2,
                    "pending_operations": 0, "protected_and_final_versions_matched": 8},
        "timing": timing, "penalty_minutes": 0, "next": "Overseer publication; no new live experiment required."}
    assert len(json.dumps(publication).encode()) <= 65536
    publication_ref = evidence.PREVIOUS.save("publication-input.json", publication)
    report = PROJECT / "reports/latest.html"
    if report.exists():
        raise ValueError("report exists; concurrent-writer ownership unresolved, no overwrite")
    report.parent.mkdir(exist_ok=True)
    rows = "".join("<tr><th>" + html.escape(key) + "</th><td>" + html.escape(value["status"]) + "</td></tr>" for key, value in matrix.items())
    links = "".join('<li><a href="../../../' + quote(item["path"]) + '">' + html.escape(item["path"]) + '</a></li>'
                    for item in (handoff_ref, publication_ref, matrix_ref, ref(settlement_path), ref(native_path), ref(independent_path)))
    failures_html = "".join("<li>" + html.escape(value) + "</li>" for value in failures)
    rendered = "<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Foundry Migration F08</title>"
    rendered += "<style>body{font-family:Georgia,serif;max-width:76rem;margin:2rem auto;padding:0 1rem;color:#17251c;background:#f5f8f6;line-height:1.5}table{border-collapse:collapse;width:100%}th,td{border-bottom:1px solid #b4c6bc;padding:.5rem;text-align:left}a,td,li{overflow-wrap:anywhere}h1,h2{color:#165b42}main{padding-bottom:2rem}</style><main>"
    rendered += "<h1>Foundry Official Integration</h1><p>F08 live integration complete; F09 authoritative publication pending. Derived worker evidence, not an authoritative record.</p>"
    rendered += "<h2>Baseline, Local And Live</h2><p>Historical regression remains 28/30 versus 29/30. No historical holdout read, rerun or upload. Local gates: H39 / E26 / O46. Live H: three tools, distinct redeployment, stored identity, anonymous refusal. Live E: three complete finite rows and three independent proofs. Live O: two generated configs applied; native and independent exports complete.</p>"
    rendered += "<p>Native development scores: 1/3, 2/3, 3/3. Independent development scores: 0/3, 2/3, 3/3. Shared synthetic fixture; not prediction improvement or generalization. Two baseline-only jobs retained.</p>"
    rendered += "<p>Eight protected/final versions matched. All jobs/builds/cancellation attempts terminal; 896 historical hashes unchanged. Resources retained, costs unknown. Cancellation terminal state verified live; task/client cleanup tested locally, provider cleanup marker not recovered. No rollback or hard-kill durability claim.</p>"
    rendered += "<h2>Acceptance Matrix</h2><table><thead><tr><th>Gate</th><th>Status</th></tr></thead><tbody>" + rows + "</tbody></table>"
    rendered += "<h2>Failures Retained</h2><ul>" + failures_html + "</ul><h2>Primary Evidence</h2><ul>" + links + "</ul>"
    rendered += "<p>MAX effort requested; effective setting unverified. Original mission monotonic start unavailable; worker clock does not reset deadline 2026-09-22T21:06:18Z. Costs/tokens unknown. Only overseer may publish authoritative records.</p></main></html>"
    with report.open("x") as stream:
        stream.write(rendered)
    return {"handoff": handoff_ref, "publication": publication_ref, "report": ref(report)}


def verify():
    from html.parser import HTMLParser
    from urllib.parse import unquote

    references = {}
    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
                path = ROOT / value["path"]
                if not path.exists():
                    path = PROJECT / value["path"]
                if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != value["sha256"]:
                    raise ValueError("evidence digest mismatch: " + value["path"])
                references[str(path.relative_to(ROOT))] = value["sha256"]
            for field in value.values():
                walk(field)
        elif isinstance(value, list):
            for field in value:
                walk(field)
    for name in ("handoff.json", "publication-input.json", "acceptance-matrix.json", "command-inventory.json", "source-changes.json"):
        walk(load(OUT / name))
    restored = archive(OUT / "final-source.tar.gz")
    for name, payload in restored.items():
        if (ROOT / name).read_bytes() != payload:
            raise ValueError("final source drift: " + name)
    history = load(ROOT / "deploy/remediation-evidence/20260922T151500Z-f00/capture.json")["historical_hash_only"]
    for item in history:
        if hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("historical drift: " + item["path"])
    report = PROJECT / "reports/latest.html"
    class Links(HTMLParser):
        def __init__(self):
            super().__init__()
            self.paths = []
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                self.paths.extend(value for key, value in attrs if key == "href")
    parser = Links()
    parser.feed(report.read_text())
    for link in parser.paths:
        if not (report.parent / unquote(link)).resolve().is_file():
            raise ValueError("report evidence link missing: " + link)
    assert (OUT / "publication-input.json").stat().st_size <= 65536
    specification = ROOT / "specs/20260922_FOUNDRY_OFFICIAL_INTEGRATION_REMEDIATION.md"
    assert "- [ ] F09" in specification.read_text()
    spec_ref = evidence.PREVIOUS.save("spec-after-f08-closeout.md", specification.read_bytes())
    return evidence.PREVIOUS.save("final-verification.json", {
        "references_verified": len(references), "source_members_verified": len(restored),
        "historical_files_verified": len(history), "report_links_verified": len(parser.paths),
        "report": ref(report), "publication_input": ref(OUT / "publication-input.json"),
        "spec_recovery_after": spec_ref, "timing": evidence.clock(),
        "browser_rendering": "not exercised; static derived report structure and evidence links verified",
        "authoritative_publication": "not performed", "verified": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "finish", "verify"))
    args = parser.parse_args()
    print(json.dumps(prepare() if args.action == "prepare" else verify() if args.action == "verify" else finish()))