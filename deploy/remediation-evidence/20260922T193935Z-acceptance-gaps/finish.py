"""Measured correction and compact non-authoritative gap handoff."""

import argparse
import ast
from datetime import datetime, timezone
import difflib
import html
from html.parser import HTMLParser
import importlib.util
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
from urllib.parse import quote, unquote

import evidence

ROOT, OUT, PRIOR = evidence.ROOT, evidence.OUT, evidence.PRIOR
H = ROOT / "testbeds/foundry-hosted-agents"
E = ROOT / "testbeds/foundry-agent-evaluation"
O = ROOT / "testbeds/foundry-agent optimization"
BUILD = H / "deploy/records/migration-h-overlap-v1/20260922T194519593953Z-build-overlap.json"
E_VERIFY = E / "deploy/records/migration-e-final-h-v3/20260922T194842941922Z-verify.json"
H_TEST = H / "deploy/records/20260922T195054764532Z-test.json"
H_INSPECT = H / "deploy/records/migration-h-overlap-v1/20260922T195544429273Z-inspect.json"
REPORT = ROOT / "agentcraft_projects/foundry-official-integration-20260922/reports/latest.html"


def load(path):
    return json.loads(path.read_text())


def archive(path):
    with tarfile.open(path) as bundle:
        return {member.name: bundle.extractfile(member).read() for member in bundle if member.isfile()}


def production(files):
    selected = {name: data for name, data in files.items() if name.startswith("testbeds/")
                and "/tests/" not in name and (Path(name).suffix in (".py", ".sh") or Path(name).name == "Dockerfile")}
    functions, mutations, http, bearer = 0, [], [], []
    for name, data in sorted(selected.items()):
        text = data.decode()
        if name.endswith(".py"):
            tree = ast.parse(text)
            functions += sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) for node in ast.walk(tree))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    rendered = ast.unparse(node.func)
                    if (rendered == "project.send_request" or (name.endswith("campaign.py") and rendered == "httpx.get")
                            or (rendered == "client.request" and "def api(" in text)):
                        http.append({"path": name, "line": node.lineno, "call": rendered})
        for number, line in enumerate(text.splitlines(), 1):
            if '"Bearer " +' in line:
                bearer.append({"path": name, "line": number})
            if re.search(r"\bpip\s+install\b|['\"]pip['\"]\s*,\s*['\"]install['\"]", line):
                mutations.append({"path": name, "line": number, "command": line.strip(),
                                  "uv": bool(re.search(r"\buv\b", line))})
    return {"files": len(selected), "paths": sorted(selected), "lines": sum(len(data.splitlines()) for data in selected.values()),
            "functions": functions, "authenticated_custom_http": http, "manual_bearer": bearer,
            "dependency_mutation_sites": mutations, "non_uv_mutation_sites": sum(not item["uv"] for item in mutations)}


def measure():
    stages = {"F00": ROOT / "deploy/remediation-evidence/20260922T151500Z-f00/source.tar.gz",
              "F01": ROOT / "deploy/remediation-evidence/20260922T163453Z-f02-f07/before-f02-source.tar.gz",
              "review_final": PRIOR / "final-source.tar.gz"}
    measured = {name: production(archive(path)) for name, path in stages.items()}
    current = {name: (ROOT / name).read_bytes() for name in measured["review_final"]["paths"]}
    measured["current"] = production(current)
    assert [measured[name]["lines"] for name in stages] == [3501, 3523, 4291]
    assert all(value["paths"] == measured["F00"]["paths"] and value["files"] == 19 for value in measured.values())
    assert len(measured["current"]["dependency_mutation_sites"]) == 3 and measured["current"]["non_uv_mutation_sites"] == 0
    assert len(measured["F00"]["authenticated_custom_http"]) == 6
    assert len(measured["current"]["authenticated_custom_http"]) == 1
    return evidence.save("measurement-addendum.json", {"authoritative": False,
        "supersedes_claim_only": "F08 measurements undercounted two uv --no-config Docker installation sites; prior receipts remain immutable.",
        "scope": "Identical 19 H/E/O production Python/shell/Dockerfile paths; excludes tests/docs/locks/wheels/evidence/datasets; AST includes nested functions.",
        "stages": measured, "archives": {name: evidence.ref(path) for name, path in stages.items()},
        "current_source": {name: evidence.ref(ROOT / name) for name in sorted(current)},
        "claims": {"F01_bridge_lines": 22, "review_minus_F00_lines": 790, "review_minus_F01_lines": 768,
                   "current_minus_review_lines": measured["current"]["lines"] - 4291,
                   "authenticated_custom_http": "6 -> 1", "active_dependency_mutations": "3, all uv",
                   "net_code_reduction": False, "measured_effort_savings": "unknown"}})


def snapshot():
    before = archive(PRIOR / "final-source.tar.gz")
    names = set(before)
    names.update(str(path.relative_to(ROOT)) for path in OUT.glob("*.py"))
    names.add(str((OUT / "README.md").relative_to(ROOT)))
    names.update(("README.md", "agentcraft_projects/foundry-official-integration-20260922/reports/latest.html",
                  "testbeds/foundry-hosted-agents/deploy/env/migration-h-overlap-v1.json",
                  "testbeds/foundry-agent-evaluation/deploy/env/migration-e-final-h-v3.json"))
    files = {name: (ROOT / name).read_bytes() for name in sorted(names)}
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as bundle:
        for name, content in files.items():
            evidence.OWNER.PREVIOUS.CAPTURE.safe(ROOT / name, content)
            member = tarfile.TarInfo(name)
            member.size = len(content)
            bundle.addfile(member, io.BytesIO(content))
    saved = evidence.save("final-source.tar.gz", buffer.getvalue())
    assert archive(OUT / "final-source.tar.gz") == files
    changes, patch = [], []
    for name in sorted(set(before) & set(files)):
        if before[name] != files[name]:
            changes.append(name)
            patch.extend(difflib.unified_diff(before[name].decode().splitlines(True), files[name].decode().splitlines(True),
                                            fromfile="review/" + name, tofile="current/" + name))
    difference = evidence.save("source-changes.patch", "".join(patch).encode())
    return evidence.save("final-source.json", {"archive": saved, "member_bytes_verified": True,
        "files": [evidence.ref(ROOT / name) for name in files], "changed_prior_members": changes,
        "new_members": sorted(set(files) - set(before)), "diff": difference,
        "production": production({name: files[name] for name in before}),
        "restore": "Exact prior members in immutable F08 final-source.tar.gz; no active-tree restore performed."})


def verify_bindings():
    built = load(BUILD)
    assert built["status"] == "complete"
    result = built["result"]
    assert result["overlap_seconds"] > 0 and not result["failures"] and len(result["builds"]) == 2
    assert len({item["acr_run"]["runId"] for item in result["builds"]}) == 2
    commands = [item for item in built["observations"] if item.get("command", [])[:3] == ["az", "acr", "build"]]
    assert len(commands) == 2
    for build, command in zip(result["builds"], commands):
        request, run = build["request"], build["acr_run"]
        assert run["runId"] == command["result"]["runId"] == request["run_id"]
        assert run["status"] == "Succeeded"
        assert build["source"]["sha256"] == request["source_sha256"] == "5cb22af25af1b384fcafd11490f5bf95fa42b9eea2d781e2cb44f2025def0594"
        assert build["archive_sha256"] == request["archive_sha256"] == "5b4b55fb65684a90ce5c75fe9a4eb6c5aab2fde70bd49df89923eedca02fbb95"
        assert evidence.ref(H / build["archive"])["sha256"] == build["archive_sha256"]
        image = next(item for item in run["outputImages"] if item["tag"] == request["tag"])
        assert build["image"] == image["registry"] + "/" + image["repository"] + "@" + image["digest"]
        assert command["command"][command["command"].index("--image") + 1] == image["repository"] + ":" + image["tag"]
    selected = load(E / "deploy/records/migration-e-final-h-v3/selection.json")
    evaluation = load(E_VERIFY)
    assert evaluation["status"] == "complete"
    result_e = evaluation["result"]
    assert result_e["accepted"] and result_e["complete"] and result_e["settled"] and result_e["proof_passed"] == 3
    assert result_e["pins"] == selected["prerequisites"]["agent"]["pins"]
    assert result_e["pins"]["agent_version"] == "3"
    assert selected["evaluator"]["version"] == "12"
    assert result_e["dataset"]["remote_bytes_verified"] and result_e["aggregate"]["status"] == "completed"
    assert result_e["aggregate"]["data_source"]["target"]["version"] == "3"
    assert result_e["aggregate"]["data_source"]["target"]["name"] == result_e["pins"]["agent_name"]
    final_test = load(H_TEST)
    assert final_test["status"] == "complete" and final_test["result"]["tests"] == 41
    for name, expected in final_test["procedure_files"].items():
        assert evidence.ref(H / name)["sha256"] == expected
    assert built["procedure_files"]["deploy/experiment.py"] == final_test["procedure_files"]["deploy/experiment.py"]
    for name, expected in load(E / "deploy/records/20260922T181652333042Z-validate.json")["source"].items():
        assert evidence.ref(E / name)["sha256"] == expected
    for name, content in archive(PRIOR / "final-source.tar.gz").items():
        if name.startswith("testbeds/foundry-agent optimization/") and Path(name).suffix in (".py", ".sh"):
            assert (ROOT / name).read_bytes() == content
    inspected = load(H_INSPECT)
    assert inspected["status"] == "complete"
    versions = inspected["result"]["versions"]["result"]["data"]
    assert {item["version"] for item in versions} == {"1", "2", "3"}
    current = inspected["result"]["agent"]["result"]["versions"]["latest"]
    assert current["version"] == "3" and current["status"] == "active"
    assert current["definition"]["container_configuration"]["image"] == selected["prerequisites"]["agent"]["image"]
    assert all(current["metadata"][key] == result_e["pins"][key] for key in ("source_sha256", "config_sha256"))
    return {"builds": [{"request": item["request"], "run": item["acr_run"], "image": item["image"]}
                       for item in result["builds"]], "overlap_seconds": result["overlap_seconds"],
            "evaluation": {"identity": result_e["identity"], "pins": result_e["pins"], "dataset_id": result_e["dataset"]["id"],
                           "dataset_sha256": result_e["dataset"]["sha256"], "counts": result_e["aggregate"]["result_counts"],
                           "scores": [row["results"][0]["score"] for row in result_e["rows"]], "oracle_passed": 3},
            "tests": {"H": {"count": 41, "receipt": evidence.ref(H_TEST)},
                      "E": {"count": 26, "reused": True, "receipt": evidence.ref(E / "deploy/records/20260922T181652333042Z-validate.json")},
                      "O": {"count": 46, "reused": True, "receipt": evidence.ref(O / "deploy/evidence/20260922T190705988425Z-test.json")}}}


def report():
    verified = verify_bindings()
    prior = evidence.save("report-before.html", REPORT.read_bytes())
    measurements = load(OUT / "measurement-addendum.json")
    stages = measurements["stages"]
    rows = "\n".join("<tr><th>" + html.escape(name) + "</th><td>" + str(stage["lines"]) + "</td><td>"
                     + str(stage["functions"]) + "</td><td>" + str(len(stage["dependency_mutation_sites"]))
                     + "</td></tr>" for name, stage in stages.items())
    links = [("Current gap evidence", OUT / "README.md"), ("Worker handoff", OUT / "handoff.json"),
             ("Bounded publication input, not published", OUT / "result-input.json"),
             ("Measured correction", OUT / "measurement-addendum.json"), ("Actual build overlap", BUILD),
             ("Fresh final-host E verification", E_VERIFY), ("Original independent review", PRIOR / "acceptance-review.json"),
             ("Historical report, superseded current status", ROOT / prior["path"])]
    rendered_links = "\n".join('<li><a href="../../../' + quote(str(path.relative_to(ROOT))) + '">'
                                + html.escape(label) + "</a></li>" for label, path in links)
    content = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Foundry Migration Acceptance Correction</title>
<style>body{{font-family:Georgia,serif;max-width:76rem;margin:2rem auto;padding:0 1rem;color:#17251c;background:#f5f8f6;line-height:1.5}}table{{border-collapse:collapse;width:100%}}th,td{{border-bottom:1px solid #b4c6bc;padding:.5rem;text-align:left}}a,td,li{{overflow-wrap:anywhere}}h1,h2{{color:#165b42}}</style></head>
<body><main><h1>Foundry Official Integration</h1>
<p>Assigned acceptance gaps closed. F09 authoritative publication remains pending. Derived worker evidence, not an authoritative mission result.</p>
<h2>Independent Review Corrections</h2>
<p>C04: actual builds crm and crn overlapped {verified['overlap_seconds']} seconds. Both used the exact retained locked archive with distinct frozen tags. Direct returned run IDs match their own tag and output digest. No inventory association or deployment.</p>
<p>E: fresh migration-e-final-h-v3 dataset, one definition and one completed run target accepted agentcraft-migration-tool-proof-v1 version 3, with exact source/config/image pins. Three complete finite rows, coherence 4/4/4, oracle 3/3. Prior version-1 E evidence remains unchanged.</p>
<p>C09 passes with local lifecycle tests and live terminal cancelled readback. Live downstream no-further-dispatch/client closure remains not_verified. No extra cancellation or foreign-credential test was required.</p>
<h2>F07 Same 19-File Measurement</h2>
<table><thead><tr><th>Stage</th><th>Lines</th><th>Functions</th><th>Install sites</th></tr></thead><tbody>{rows}</tbody></table>
<p>F00 3501 -> F01 3523 -> review final 4291 -> current 4372 lines. F01 added 22; final at review added 790 versus F00, 768 versus F01. Current adds 81. Three active dependency mutations are all uv: H installer and H/O Dockerfiles. Prior matcher missed uv --no-config pip install. Custom authenticated HTTP sites 6 -> 1; manual bearer 2 -> 0. No net line/function reduction or measured effort-savings claim.</p>
<h2>Acceptance And Settlement</h2>
<p>H41 tests pass; E26/O46 unchanged-source evidence reused. Final H inventory remains versions 1/2/3 with accepted v3 active. Two new builds succeeded and fresh E run completed; no new pending operation. Prior H/O settlement is reused, not represented as a fresh O cloud read. Resources retained; costs unknown.</p>
<p>Original F00-F08 receipts and accepted H/O artifacts retained. No new optimizer, holdout, cancellation, foreign-credential, dependency, environment, grant, auth or teardown action. No workers dispatched. No project constitution/notebook/records written.</p>
<h2>Historical Results Preserved</h2>
<p>Historical prediction regression remains 28/30 versus 29/30; generated candidate holdout not evaluated. Prior native synthetic scores 1/3, 2/3, 3/3 and independent synthetic scores 0/3, 2/3, 3/3 remain unchanged. Two baseline-only jobs retained. Capability proof is not prediction improvement, generalization or statistical evidence.</p>
<p>Original H three-tool proof, protected invocation, stored readback and anonymous refusal remain accepted. No cloud rollback or hard-kill durability claim. MAX requested; effective runtime effort, tokens and cost unknown. Clock cadence gaps during blocking/read/edit intervals retained; deadline 2026-09-22T21:06:18Z unchanged.</p>
<h2>Primary Evidence</h2><ul>{rendered_links}</ul></main></body></html>
'''
    REPORT.write_text(content)
    return evidence.save("report-correction.json", {"before": prior, "after": evidence.ref(REPORT),
                         "authoritative": False, "F09": "pending_publication"})


def close():
    verified = verify_bindings()
    source = load(OUT / "final-source.json")
    measure_value = load(OUT / "measurement-addendum.json")
    assert source["production"] == measure_value["stages"]["current"]
    integrity = load(OUT / "historical-integrity.json")
    commands = [evidence.ref(path) for path in sorted(OUT.glob("*.json"))
                if "exit_code" in load(path) and "command" in load(path)]
    command_ref = evidence.save("command-inventory.json", {"commands": commands,
        "extra_observations": ["Two jq projections failed because jq is absent; no installation attempted; stdlib JSON projections succeeded.",
                               "Required docs/ARCHITECTURE_OVERVIEW.md absent; existing owner paths retained.",
                               "SDK serializers warned about Foundry extension types; actual wire target/criteria and stored outputs validated.",
                               "H invalid-input negative tests intentionally log HTTP 500/ValueError; suite passes."],
        "capture_gap": "Initial read-only tools/local test/manifest-check and manual projections live in host session transcript, not this subprocess inventory."})
    matrix = load(PRIOR / "acceptance-review.json")["acceptance_matrix"]
    matrix["C04"] = {"status": "pass", "basis": "actual overlapping builds, direct run/context/tag/digest binding; prior actual dropped-result recovery reused"}
    matrix["F07"] = {"status": "pass", "basis": "append-only corrected 19-file baseline bridge and all three uv mutation sites"}
    matrix["F08"] = {"status": "pass", "basis": "assigned missing concurrency and final-H-v3 E handoff now verified; unchanged H/O evidence reused"}
    matrix["F09"] = {"status": "not_verified", "basis": "overseer authoritative publication pending; worker input is not publication"}
    matrix_ref = evidence.save("acceptance-addendum.json", {"authoritative": False, "supersedes": evidence.ref(PRIOR / "acceptance-review.json"),
        "matrix": matrix, "C09": load(PRIOR / "acceptance-review.json")["c09_interpretation"],
        "new_evidence": [evidence.ref(BUILD), evidence.ref(E_VERIFY), evidence.ref(OUT / "measurement-addendum.json")]})
    timing = evidence.clock()
    assert timing["mission_remaining_seconds"] > 0
    gap_receipts = [evidence.ref(path) for directory in (H / "deploy/records/migration-h-overlap-v1", E / "deploy/records/migration-e-final-h-v3")
                    for path in sorted(directory.glob("*.json"))]
    handoff = {"status": "complete", "authoritative": False, "objective": "Close assigned AR01/AR02/AR03 acceptance gaps; preserve F09 publication boundary",
        "constitution": {"revision": 1, "sha256": "0a7e39fe0b4a62588b24b1f975fd61c1cb42b80ec35a6d1d263bd39c6575e1c8"},
        "request": evidence.ref(OUT / "request.json"), "prewrite_pins": evidence.ref(OUT / "prewrite-pins.json"),
        "review": evidence.ref(PRIOR / "acceptance-review.json"), "stage": "measure/settlement",
        "hypothesis": "Existing direct-ID build association holds during real overlap; unchanged E collector binds accepted final H v3.",
        "observed": verified, "acceptance": matrix_ref, "measurements": evidence.ref(OUT / "measurement-addendum.json"),
        "source": evidence.ref(OUT / "final-source.json"), "source_archive": evidence.ref(OUT / "final-source.tar.gz"),
        "commands": command_ref, "new_receipts": gap_receipts,
        "history": evidence.ref(OUT / "historical-integrity.json"), "history_counts": integrity,
        "report": evidence.ref(OUT / "report-correction.json"), "current_report": evidence.ref(REPORT),
        "settlement": {"new_builds_terminal": ["crm", "crn"], "new_E_terminal": verified["evaluation"]["identity"],
                       "pending_operations": [], "H_current_readback": evidence.ref(H_INSPECT),
                       "prior_H_O_operation_settlement_reused": evidence.ref(PRIOR / "20260922T191008048851Z-settlement-live.json"),
                       "O_fresh_cloud_read": False, "deployment_writes": 0, "workers": [], "local_background_processes": [],
                       "retention": "Build tags/images and fresh dataset/evaluation/run retained; no teardown; costs unknown."},
        "limits": ["F09 not published; no mission-complete claim.", "C09 live terminal/local lifecycle only; live downstream closure/no-dispatch unverified.",
                   "No optimization/generalization improvement; historical metrics/holdout unchanged.", "Actual provider tokens/cost/effective MAX effort unknown.",
                   "Original mission monotonic ID unavailable; inherited UTC deadline unchanged.",
                   "Clock checks exceeded 60 seconds during blocking commands and some read/edit intervals; no continuous-cadence claim.",
                   "Initial tools and manual diagnostics captured only by host transcript; no full independent tool-call archive.",
                   "No live rollback or hard-kill durability; source restore not executed."],
        "timing_at_handoff": timing, "mission_started_at": "2026-09-22T15:06:18Z", "deadline_utc": "2026-09-22T21:06:18Z",
        "penalty_minutes": 0, "archival_checkpoint": "Existing F00/F08 archives retained; new exact-source archive ready for overseer archival, no publication by worker.",
        "next_transition": "Overseer review and F09 authoritative publication; no automatic follow-on experiment."}
    handoff_ref = evidence.save("handoff.json", handoff)
    result_input = {"kind": "worker-result-input", "authoritative": False, "status": "assigned_gaps_complete_f09_pending",
        "handoff": handoff_ref, "acceptance": matrix_ref, "source": handoff["source"], "source_archive": handoff["source_archive"],
        "measurements": handoff["measurements"], "commands": command_ref, "history": handoff["history"],
        "observed": verified, "settlement": handoff["settlement"], "limits": handoff["limits"],
        "timing": timing, "penalty_minutes": 0, "next": handoff["next_transition"]}
    assert len(json.dumps(result_input, indent=2, sort_keys=True).encode()) + 1 <= 65536
    return evidence.save("result-input.json", result_input)


def verify_final():
    verified = verify_bindings()
    assert (OUT / "result-input.json").stat().st_size <= 65536
    references = {}
    def walk(value):
        if isinstance(value, dict):
            if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
                actual = evidence.ref(ROOT / value["path"])
                assert actual["sha256"] == value["sha256"], value["path"]
                if "bytes" in value:
                    assert actual["bytes"] == value["bytes"], value["path"]
                references[value["path"]] = actual
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    for name in ("handoff.json", "result-input.json", "measurement-addendum.json", "final-source.json", "command-inventory.json", "report-correction.json"):
        walk(load(OUT / name))
    members = archive(OUT / "final-source.tar.gz")
    for name, content in members.items():
        assert (ROOT / name).read_bytes() == content, name
    for item in load(OUT / "prewrite-pins.json")["protected_files"]:
        assert evidence.ref(ROOT / item["path"]) == item, item["path"]
    class Links(HTMLParser):
        def handle_starttag(self, tag, attrs):
            if tag == "a":
                target = dict(attrs).get("href", "")
                assert (REPORT.parent / unquote(target)).resolve().is_file(), target
    Links().feed(REPORT.read_text())
    for match in re.finditer(r"\]\(([^)]+)\)", (OUT / "README.md").read_text()):
        assert (OUT / unquote(match[1].split("#")[0])).resolve().exists(), match[1]
    return {"passed": True, "references_checked": len(references), "source_members": len(members),
            "result_input_bytes": (OUT / "result-input.json").stat().st_size, "new_operations_terminal": True,
            "overlap_seconds": verified["overlap_seconds"], "F09": "pending_publication"}


def seal():
    checks = verify_final()
    verification = evidence.save("final-verification.json", checks)
    outcome = subprocess.run(["python3", ".github/tools/oplog.py", "end", "--run", evidence.RUN,
                              "--log", str(evidence.CLOCK), "--achieved"], cwd=ROOT, capture_output=True, text=True, check=True)
    clock_ref = evidence.save("worker-clock.jsonl", evidence.CLOCK.read_bytes())
    return evidence.save("completion.json", {"verification": verification, "handoff": evidence.ref(OUT / "handoff.json"),
        "result_input": evidence.ref(OUT / "result-input.json"), "clock": clock_ref, "clock_end_output": outcome.stdout,
        "completed_at": datetime.now(timezone.utc).isoformat(), "authoritative_publication": False})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("measure", "snapshot", "verify-bindings", "report", "close", "verify-final", "seal"))
    args = parser.parse_args()
    print(json.dumps({"measure": measure, "snapshot": snapshot, "verify-bindings": verify_bindings,
                      "report": report, "close": close, "verify-final": verify_final, "seal": seal}[args.action](), indent=2))