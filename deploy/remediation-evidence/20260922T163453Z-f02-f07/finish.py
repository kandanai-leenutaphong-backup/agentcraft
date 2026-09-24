"""Build a compact worker handoff from retained primary evidence, never publish it."""

import ast
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
import re
import tarfile

import evidence

ROOT, OUT = evidence.ROOT, evidence.OUT


def ref(path):
    data = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "sha256": evidence.digest(data), "bytes": len(data)}


def load_archive(name):
    with tarfile.open(OUT / name) as archive:
        return {member.name: archive.extractfile(member).read() for member in archive if member.isfile()}


def production(files):
    selected = {name: value for name, value in files.items() if "/tests/" not in name
                and (Path(name).suffix in (".py", ".sh") or Path(name).name == "Dockerfile")}
    functions, http, bearer, mutations = [], [], [], []
    for name, data in selected.items():
        text = data.decode()
        if name.endswith(".py"):
            tree = ast.parse(text)
            functions.extend(name + "::" + node.name for node in ast.walk(tree)
                             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)))
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                    rendered = ast.unparse(node.func)
                    if rendered == "project.send_request" or (name.endswith("campaign.py") and rendered == "httpx.get") or (rendered == "client.request" and "def api(" in text):
                        http.append({"path": name, "line": node.lineno, "call": rendered})
                    if rendered == "subprocess.run" and "\"pip\", \"install\"" in ast.get_source_segment(text, node):
                        mutations.append({"path": name, "line": node.lineno})
        for number, line in enumerate(text.splitlines(), 1):
            if '"Bearer " +' in line:
                bearer.append({"path": name, "line": number})
            if "uv pip install" in line or '["uv", "--no-config", "pip", "install"' in line:
                mutations.append({"path": name, "line": number})
    return {"files": len(selected), "lines": sum(len(value.splitlines()) for value in selected.values()),
            "functions": len(functions), "symbols": sorted(functions), "authenticated_custom_http": http,
            "manual_bearer": bearer, "dependency_mutation_sites": mutations,
            "scope": "same H/E/O active Python/shell/Dockerfile scope; excludes tests, docs, locks, wheelhouse, evidence and datasets"}


def main():
    before = load_archive("before-f02-source.tar.gz")
    after = load_archive("final-source.tar.gz")
    changes, patch = [], []
    for name in sorted(set(before) | set(after)):
        if before.get(name) == after.get(name):
            continue
        record = {"path": name, "action": "modified" if name in before and name in after else "added" if name in after else "removed"}
        for side, files in (("before", before), ("after", after)):
            record[side] = None
            if name in files:
                relative = "recovery-" + side + "/" + name
                (OUT / relative).parent.mkdir(parents=True, exist_ok=True)
                record[side] = evidence.save(relative, files[name])
        changes.append(record)
        patch.extend(difflib.unified_diff(before.get(name, b"").decode().splitlines(True),
            after.get(name, b"").decode().splitlines(True), fromfile="before/" + name, tofile="after/" + name))
    diff = evidence.save("source-changes.patch", "".join(patch).encode())
    inventory = evidence.save("source-changes.json", {"changes": changes, "diff": diff,
        "before": ref(OUT / "before-f02-source.json"), "after": ref(OUT / "final-source.json")})
    measured = {"before": production(before), "after": production(after)}
    measured["removed_symbols"] = sorted(set(measured["before"]["symbols"]) - set(measured["after"]["symbols"]))
    measured["added_symbols"] = sorted(set(measured["after"]["symbols"]) - set(measured["before"]["symbols"]))
    measured["net_production_lines"] = measured["after"]["lines"] - measured["before"]["lines"]
    measured["claim"] = "authenticated transport reduction only; net code may grow for strict validation/recovery; no effort savings estimate"
    measured["locks"] = {}
    for name, payload in after.items():
        if name.endswith("requirements.lock") and name in before:
            assert payload == before[name], "dependency lock changed unexpectedly"
            measured["locks"][name] = {"sha256": evidence.digest(payload), "unchanged": True,
                "packages": len(re.findall(r"^[A-Za-z0-9_.-]+==", payload.decode(), re.MULTILINE))}
    measurements = evidence.save("f07-measurements.json", measured)
    receipts = []
    for path in sorted(OUT.glob("*-*.json")):
        document = json.loads(path.read_text())
        if "command" in document and "exit_code" in document:
            receipts.append({**ref(path), "stage": document["stage"], "exit_code": document["exit_code"], "seconds": document["seconds"]})
    commands = evidence.save("command-inventory.json", receipts)
    probes = json.loads((OUT / "conditional-contract-probes.json").read_text())
    decisions = {}
    for key in ("C01", "C02", "C03", "C04", "C05", "C06", "C07", "C08", "C09", "C10"):
        decisions[key] = {"status": "implemented" if key in ("C04", "C09") else "retained",
                          "decision": probes[key]["gate"], "evidence": ref(OUT / "conditional-contract-probes.json")}
    decisions["C01"]["limitation"] = "bounded loader-compatible config GET is not a verified public REST reference; payload bound checked after SDK buffering"
    decisions["C03"]["limitation"] = "JSON-text tool proof remains; no native structured tool output or public AgentBinding adapter"
    decisions["C06"]["limitation"] = "native target identity/stored-readback parity not earned; direct SDK validation retained; no holdout upload"
    decisions["C09"]["limitation"] = "native asyncio.Event exercised on actual handlers with simulated blocked model/tool work; no deployed cancellation or hard-kill recovery claim"
    decisions["C10"]["limitation"] = "short cancellation/SSE adapters retained in independent host owners; no canonical library/dependency expansion"
    decision_ref = evidence.save("conditional-decisions.json", decisions)
    manifests = {owner: ref(ROOT / path) for owner, path in {
        "H": "testbeds/foundry-hosted-agents/deploy/env/migration-h-v1.json",
        "E": "testbeds/foundry-agent-evaluation/deploy/env/migration-e-v1.json",
        "O": "testbeds/foundry-agent optimization/deploy/env/migration-o-v1.json"}.items()}
    clocks = [json.loads(line) for line in (OUT / "task-clock.jsonl").read_text().splitlines()]
    clock = evidence.clock()
    timing = {"worker": clock, "mission_start_utc": "2026-09-22T15:06:18Z", "deadline_utc": "2026-09-22T21:06:18Z",
              "original_mission_monotonic": None, "penalty_minutes": 0,
              "cadence": "clock checks retained; some edit/read intervals exceeded 60 seconds; no uninterrupted cadence claim"}
    tests = {}
    for owner, directory, suffix in (("H", "testbeds/foundry-hosted-agents/deploy/records", "test"),
                                     ("E", "testbeds/foundry-agent-evaluation/deploy/records", "validate"),
                                     ("O", "testbeds/foundry-agent optimization/deploy/evidence", "test")):
        path = sorted((ROOT / directory).glob("20260922T17*-" + suffix + ".json"))[-1]
        value = json.loads(path.read_text())
        assert value["status"] == "complete"
        tests[owner] = {"tests": value["result"]["tests"], "receipt": ref(path)}
    stages = {
        "F02": {"status": "implemented_offline_pass_live_pending", "outcome": "explicit agreement extraction; data errors raise; skills/model/tool guards; code-hash-derived new evaluator identity; Evals mapping explicit"},
        "F03": {"status": "implemented_offline_pass_live_pending", "outcome": "bounded target adapters, exact run/row/criterion identity and finite scores, partial retrieval evidence, native request types; E builtin version resolved at freeze"},
        "F04": {"status": "implemented_offline_pass_live_pending", "outcome": "H api removed; Projects lifecycle/session and OpenAI Responses; exact version, no-repeat intents, stored output/metadata; anonymous HTTP retained"},
        "F05": {"status": "implemented_offline_and_readonly_parity_pass", "outcome": "native candidates matched 3 existing identities/metrics/eval links; create-based recovery removed; new submission/config canary pending"},
        "F06": {"status": "implemented_offline_pass", "outcome": "pinned fresh H/E/O manifests, separate targets/evidence, historical repair/holdout dispatch retired, observers single read, upload intents fresh"},
        "F07": {"status": "complete_local_checkpoint", "outcome": "owning runbooks updated, same-scope counts, recovery bytes and historical integrity retained; no net deletion/effort claim"},
        "F08": {"status": "not_executed_except_readonly_job_parity", "outcome": "live cloud mutation prohibited in assignment"},
        "F09": {"status": "pending_overseer", "outcome": "no authoritative publication by worker"}}
    risks = [
        "New registered evaluator schema/mapping, H SDK version creation/inference, E explicit builtin version, and O submit/config application require F08 live canaries.",
        "Native optimizer evaluator references have no public data_mapping field; Evals mapping is explicit, native envelope compatibility remains service-tested gate.",
        "C01 retained loader-compatible resolver route is not a verified public REST contract; SDK response buffering precedes payload-size refusal.",
        "Service may return fewer than requested max_candidates; collection fails closed and preserves terminal evidence instead of declaring completeness.",
        "E service initialization remains deployment_name; model variant untested and not adopted. Service-added criterion fields may cause strict readback refusal requiring explicit contract review.",
        "No cloud foreign-owner canary, deployed cancellation, new image build, live auth/readback or rollback test performed in this assignment.",
        "Host SDK warns store=true in-flight responses are not durable across hard kill; synchronous tool side effects cannot be undone by asyncio cancellation.",
        "Existing shared-package conflicts/shadow-install refusal remain F01 facts; no package/environment mutation performed."]
    failures = [
        "Initial F02 mapping patch missed closing brace; focused import failed, repaired before next slice.",
        "F02 test incorrectly passed skills_dir to CandidateConfig; inspected public OptimizationConfig signature, repaired fixture.",
        "Duplicate overlapping O F03 patch rejected; first patch passed focused tests; no partial second edit.",
        "F06 multi-file patch rejected for unordered test hunks; verified atomic refusal, reapplied ordered slices.",
        "Evidence selector inherited wrong repository root from unused historical capture helper; explicitly bound root and verified archives.",
        "H manifest-check first used O-style cwd path; refused before cloud access; corrected invocation passed.",
        "C04 build fixture omitted app directory; corrected representative fixture, passed.",
        "C09 credential mock injected after closure capture; fixed construction-time injection, both handler tests passed.",
        "E request TypedDicts were incorrectly treated as Azure models; focused serialization test caught it, constructors corrected.",
        "Historical inventory filename guessed incorrectly; switched to F00 capture.json historical_hash_only and verified 896 files.",
        "Injected Azure response fixture lacked json(); added method and actual SDK transport test passed.",
        "Initial cancellation filename guesses and one E receipt-name search were absent; source definitions resolved locally."]
    gaps = ["MAX requested; actual runtime effort unverified; tokens/cost unknown.",
            "First manual test failures and read/edit tool calls remain host-owned; no complete raw tool transcript copied. Command capture begins with evidence runner.",
            "Intermediate failed patch bytes not all separately archived; F01 before and per-stage/final after recovery bytes retained.",
            "Original mission monotonic clock unavailable; worker clock does not replace mission UTC deadline; some >60-second check gaps.",
            "No Pylance-specific tool available; runtime tests and editor diagnostics used.",
            "No notebook writing or authoritative records publication; this is worker evidence only."]
    parity = ROOT / "testbeds/foundry-agent optimization/deploy/evidence/migration-o-v1/20260922T172655783798Z-existing-job-parity.json"
    handoff = {"status": "complete", "completion_scope": "assigned local F02-F07 checkpoint, not full F00-F09 mission acceptance",
        "objective": "Official SDK remediation preserving workflows and frozen comparison evidence",
        "constitution": {"revision": 1, "sha256": "0a7e39fe0b4a62588b24b1f975fd61c1cb42b80ec35a6d1d263bd39c6575e1c8"},
        "decision": {"path": "records/v2/20260922T154739145740Z-execute-remediation-v1/record.json", "sha256": "fd93069ab91f1d6afcc98fd557e3f4d6eb7bf834d537d2faed3c4df83036177b"},
        "f01_checkpoint": {"path": "records/v2/20260922T163403830370Z-f01-uv-dependency-checkpoint/record.json", "sha256": "8221e1964931908f26ac0be4d874612ff8e75773f8dbfb9445e00848ce08a1bc"},
        "candidate_pins": "exact H/E/O source manifests and archives; no native agent worker pilot",
        "stage": "build/test/measure", "next_transition": "overseer publication and separately authorized F08 exact-artifact canaries",
        "hypothesis": "Strict agreement adapters and native SDK lifecycle preserve workflows while removing manual authenticated transports",
        "tasks": stages, "conditional_decisions": decision_ref, "tests": tests, "readonly_parity": ref(parity),
        "source_changes": inventory, "measurements": measurements, "command_inventory": commands,
        "before_archive": ref(OUT / "before-f02-source.tar.gz"), "after_archive": ref(OUT / "final-source.tar.gz"),
        "historical_integrity": ref(OUT / "historical-integrity.json"), "manifests": manifests,
        "F08": {"operator_runbooks": ["testbeds/foundry-hosted-agents/deploy/README.md", "testbeds/foundry-agent-evaluation/deploy/README.md", "testbeds/foundry-agent optimization/deploy/README.md"],
            "targets": {"H": "agentcraft-migration-tool-proof-v1", "E": "migration-e-v1", "O": "agentcraft-migration-iris-v1"},
            "new_job_eval_version_response_ids": None, "identity_reason": "not submitted; actual returned identities must be retained by F08",
            "existing_job": "opt_21aee306b2db4bebb7eb89a07d9c1f8d"},
        "risks": risks, "failures": failures, "capture_gaps": gaps, "timing": timing,
        "settlement": {"workers": "none dispatched", "cloud_writes": 0, "model_calls": 0,
            "local_processes": "all synchronous calls settled; no background servers or pollers", "packages": "unchanged",
            "accepted_agents": "no writes; H v3 protection rechecked in read-only preflight; O accepted versions not live reread",
            "restoration": "before/after changed-source bytes verified; no active-tree or live rollback attempted",
            "publication": "none; overseer owns authoritative records"}}
    handoff_ref = evidence.save("handoff.json", handoff)
    publication = {"schema_version": 1, "kind": "worker-publication-input", "authoritative": False,
        "project_id": "foundry-official-integration-20260922", "status": "local_checkpoint_complete_live_pending",
        "handoff": handoff_ref, "source_changes": inventory, "measurements": measurements,
        "tasks": stages, "evidence": [decision_ref, commands, ref(OUT / "historical-integrity.json"), ref(parity)],
        "archival_request": "Publish referenced changes and primary evidence through overseer; retain archive bytes externally when snapshot size limits apply",
        "capture_gaps": gaps, "metrics": {"tests": {owner: value["tests"] for owner, value in tests.items()},
            "readonly_candidate_matches": 3, "historical_files_verified": 896,
            "authenticated_http_before": len(measured["before"]["authenticated_custom_http"]),
            "authenticated_http_after": len(measured["after"]["authenticated_custom_http"])}}
    assert len(json.dumps(publication).encode()) <= 65536
    result = evidence.save("publication-input.json", publication)
    print(json.dumps({"handoff": handoff_ref, "publication_input": result, "tests": publication["metrics"]["tests"],
        "before": {key: measured["before"][key] for key in ("files", "lines", "functions")},
        "after": {key: measured["after"][key] for key in ("files", "lines", "functions")}}))


if __name__ == "__main__":
    main()