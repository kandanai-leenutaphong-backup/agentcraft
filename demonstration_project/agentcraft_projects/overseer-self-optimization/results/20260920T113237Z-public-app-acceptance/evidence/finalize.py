"""Index this assigned acceptance evidence without publishing authoritative records."""

import argparse
from datetime import datetime, timezone
import difflib
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys


PINS = {
    "constitution/constitution.yaml": "070cadee2c44731d1b984dafc906a6bba2f2797de1bd2530474ef5777b8c0e37",
    "records/v2/20260920T113042019290Z-public-source-aware-ui-whoami-authorized/record.json": "a33d821cf7a510e4fc27b29ea9fb13028e9bea79bd61fc1867d819681da9831e",
    "records/v2/20260920T113042198692Z-public-source-aware-ui-before/record.json": "f1070ab67f508707f7616433b9cc6b70d54b58475e375948489b242b9cb52ff8",
    "records/v2/20260920T113041489720Z-public-integrated-app-partial-outcome/record.json": "0f009ac764c22a7497b50abadb8ad6d4d75e321634dd94a0f65630c5935fd959",
}
SOURCES = (
    "README.md",
    "template_apps/investigation_app/README.md",
    "template_apps/investigation_app/docs/ARCHITECTURE_OVERVIEW.md",
    "template_apps/investigation_app/deploy/README.md",
    "template_apps/investigation_app/app/cybereye/frontend/src/app/App.tsx",
    "template_apps/investigation_app/app/cybereye/frontend/src/features/scanner/ScannerPanel.tsx",
    "template_apps/investigation_app/app/cybereye/frontend/src/features/chat/ChatPanel.tsx",
    "template_apps/investigation_app/app/cybereye/frontend/tests/browser/verify-public-investigation.mjs",
    "template_apps/investigation_app/app/cybereye/backend/data/public_graph.py",
    "template_apps/investigation_app/app/cybereye/tests/public_runtime.py",
    "template_apps/investigation_app/app/cybereye/tests/public_browser.py",
    "template_apps/investigation_app/app/cybereye/tests/test_cosmos_telemetry.py",
)


def sha(payload):
    return hashlib.sha256(payload).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    evidence = Path(__file__).resolve().parent
    project = evidence.parents[2]
    for path, expected in PINS.items():
        assert sha((project / path).read_bytes()) == expected, path

    if args.verify:
        for name in ("source-manifest.json", "acceptance.json"):
            manifest = json.loads((evidence / name).read_text())
            for item in manifest["files"]:
                payload = (workspace / item["path"]).read_bytes()
                assert sha(payload) == item["sha256"] and len(payload) == item["bytes"], item["path"]
        print("Verified source/evidence hashes and unchanged constitution/receipt pins.")
        return

    baseline = {}
    for path in PINS:
        if "before/record.json" not in path and "partial-outcome/record.json" not in path:
            continue
        receipt = project / path
        record = json.loads(receipt.read_text())
        for change in record["changes"]:
            state = change["before" if "before/" in path else "after"]
            if state and state.get("snapshot"):
                snapshot = receipt.parent / state["snapshot"]
                assert sha(snapshot.read_bytes()) == state["sha256"], str(snapshot)
                baseline[change["path"]] = (state, snapshot)
    assert set(SOURCES).issubset(baseline)
    changed = {path for path, (state, _) in baseline.items()
               if sha((workspace / path).read_bytes()) != state["sha256"]}
    assert changed == set(SOURCES), sorted(changed.symmetric_difference(SOURCES))

    def entry(path):
        payload = path.read_bytes()
        return {"path": str(path.relative_to(workspace)), "bytes": len(payload), "sha256": sha(payload)}

    def retain(name, value):
        path = evidence / name
        with path.open("x") as handle:
            json.dump(value, handle, indent=2)
            handle.write("\n")
        assert json.loads(path.read_text()) == value
        return path

    deltas = []
    for path in SOURCES:
        state, snapshot = baseline[path]
        diff = "".join(difflib.unified_diff(snapshot.read_text().splitlines(keepends=True),
            (workspace / path).read_text().splitlines(keepends=True), fromfile=str(snapshot.relative_to(workspace)), tofile=path))
        deltas.append({"path": path, "before_sha256": state["sha256"],
            "before_snapshot": str(snapshot.relative_to(workspace)), "delta_sha256": sha(diff.encode()), "diff": diff})
    runtime = {}
    for package in ("azure-cosmos", "azdata", "llm-interface", "agent-framework-core", "openai", "httpx", "fastapi", "pytest"):
        try:
            runtime[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            runtime[package] = "unavailable metadata"
    import azure.cosmos
    sdk_path = Path(azure.cosmos.__file__)
    source_manifest = retain("source-manifest.json", {
        "kind": "primary-evidence-not-authoritative-record", "observed_at": datetime.now(timezone.utc).isoformat(),
        "constitution_revision": 9, "pins": PINS, "files": [entry(workspace / path) for path in SOURCES],
        "deltas": deltas, "unchanged_pinned_sources": len(baseline) - len(changed),
        "git_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=workspace, text=True).strip(),
        "scoped_git_dirty_patch_sha256": sha(subprocess.check_output(["git", "diff", "--binary", "--", *SOURCES], cwd=workspace)),
        "runtime": {"interpreter": sys.executable, "python": sys.version, "distributions": runtime,
                    "cosmos_source": str(sdk_path), "cosmos_source_sha256": sha(sdk_path.read_bytes())},
        "snapshot_restore": "not_verified", "source_changes": len(changed),
    })
    command_paths = sorted(evidence.glob("*-command.json"))
    commands = [{**entry(path), **{key: value for key, value in json.loads(path.read_text()).items() if key != "output"}}
                for path in command_paths]
    browser_paths = sorted(evidence.glob("*-browser/report.json"))
    report = json.loads(browser_paths[-1].read_text())
    assert report["status"] == "passed" and report["server"]["settled"] and report["server_exit"]["code"] == 0
    assert report["server"]["external_model_calls"] == 0 and not report["browser_errors"]
    paths = [*command_paths, source_manifest, Path(__file__).resolve(), evidence / "handoff.md"]
    for report_path in browser_paths:
        paths.extend(path for path in report_path.parent.iterdir() if path.is_file())
    retain("acceptance.json", {
        "kind": "primary-evidence-not-authoritative-record", "status": "complete", "local_slice": "PASS",
        "stage": "data-understanding", "next_transition": "overseer review and archival checkpoint",
        "observed_at": datetime.now(timezone.utc).isoformat(), "pins": PINS,
        "files": [entry(path) for path in sorted(set(paths))], "commands": commands,
        "failed_command_receipts": [item["path"] for item in commands if item["exit_code"] != 0],
        "primary_browser": entry(browser_paths[-1]), "browser_checks": len(report["checks"]),
        "screenshots": len(report["screenshots"]), "native_scripted_requests": report["server"]["scripted_model_requests"],
        "external_model_calls": 0, "cloud_mutations": "none", "workers": "none dispatched",
        "owned_server": "settled, exit 0; no retained URL", "effort": "max requested; effective runtime unverified",
        "archive": "overseer checkpoint requested; no records or notes written",
        "limits": ["two-event smoke, not full dataset", "synthetic browser stores and scripted native model HTTP",
            "native Cosmos mapping verified separately with mocked HTTP", "no live Entra/cloud/model acceptance",
            "legacy browser suite not rerun", "no comparative mission improvement"],
        "capture_gaps": ["read-only probes and edit tool failures remain in host session trace and handoff, not a complete exported tool ledger",
            "initial pin-check timestamp, total effort and costs unknown", "private deliberation intentionally excluded"],
    })
    print(json.dumps({"status": "complete", "source_manifest": entry(source_manifest),
        "acceptance": entry(evidence / "acceptance.json"), "changed_sources": len(changed),
        "command_receipts": len(commands), "failed_commands_retained": sum(item["exit_code"] != 0 for item in commands)}, indent=2))


if __name__ == "__main__":
    main()