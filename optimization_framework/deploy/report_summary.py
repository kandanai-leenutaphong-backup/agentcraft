"""Offline, fixed-owner receipt summary; no experiment execution or network access."""

import hashlib
from html import escape
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STATUS = "partial: local process working; full acceptance blocked/incomplete"
RECEIPTS = {
    "native": "optimization_framework/reports/native-service-success-20260919.json",
    "overseer": "optimization_framework/reports/handoff-overseer-success.json",
    "handoff_blocked": "optimization_framework/reports/handoff-overseer-result.json",
    "dispatch_blocked": "optimization_framework/reports/handoff-20260919-portable-overseer-blocked-bewEYths.json",
    "dashboard": "optimization_framework/reports/dashboard-integration-20260919.json",
    "smoke": "optimization_framework/reports/dashboard-integration-smoke-20260919-rerun.json",
    "smoke_interrupted": "optimization_framework/reports/dashboard-integration-smoke-20260919.json",
    "dashboard_blocked": "optimization_framework/reports/dashboard-integration.json",
    "prompt": "optimization_framework/reports/investigation-prompt-live-final.json",
    "cloud": "optimization_framework/reports/cloud-investigation-20260919.json",
    "profile": "optimization_framework/reports/investigation-profile-local.json",
}
METRICS = (
    ("Native acceptance time", "native", "telemetry.time_to_verified_acceptance_seconds", "seconds"),
    ("Native observed model requests", "native", "telemetry.observed_model_call_starts", "requests"),
    ("Overseer acceptance time", "overseer", "timing_and_calls.time_to_verified_acceptance_seconds", "seconds"),
    ("Overseer observed model requests", "overseer", "timing_and_calls.observed_model_requests", "requests"),
    ("Overseer repair cycles", "overseer", "timing_and_calls.repair_cycles", "cycles"),
    ("Installed bundle files verified", "overseer", "installation.files_verified", "files"),
    ("Dashboard smoke passed", "smoke", "stats.expected", "tests"),
    ("Dashboard smoke failed", "smoke", "stats.unexpected", "tests"),
    ("Interrupted smoke skipped", "smoke_interrupted", "stats.skipped", "tests"),
    ("Prompt observed model requests", "prompt", "model_request_count", "requests"),
    ("Prompt trial elapsed time", "prompt", "duration_seconds", "seconds"),
    ("Profile browser checks", "profile", "browser.checks", "checks"),
    ("Profile persisted revision", "profile", "browser.persisted_revision", "revision"),
)
GATES = (
    ("G0", "pass", "Linked specification and requirement map delivered; not runtime acceptance."),
    ("G1", "partial", "Real config-only native execution and retained failures; independent OS evaluator missing."),
    ("G2", "pass (local supported scope)", "Local run, persisted metrics, export parity and real dashboard controls verified."),
    ("G3", "partial", "Actual app tool, prompt and profile checks exist; integrated all-four campaign and measured baseline effort missing."),
    ("G4", "pending", "No fair repeated architectural A/B comparison or measured construction cost."),
    ("G5", "blocked", "Cloud authorized, not deployed; durable profiles/agent filesystem and deployed auth proof unresolved."),
    ("G6", "partial", "Fresh exact overseer used installed skill successfully after credential fix; no measured improvement or independent SME review."),
    ("G7", "partial", "Registered config-only third-domain tests; not SME-confirmed brief-to-useful-workflow."),
)
FINDINGS = (
    ("Local process", "Supported deterministic and native configuration trials work. CLI, API and dashboard share the run service. This is not an arbitrary code executor.", "native"),
    ("Fresh overseer", "Exact overseer used the installed runtime after credential fallback repair. One accepted CSV configuration trial; explicit skill reading, not automatic discovery in a newly opened VS Code client. Supplied SME requirement was linked and read back; no new SME review was performed.", "overseer"),
    ("Dashboard", "Real local backend, four views, start/cancel, failed candidate, feedback, restore, reload and JSON/CSV/HTML parity. Recorded desktop/mobile widths: 1440/390. Native evidence was inspected, not rerun.", "dashboard"),
    ("Prompt behavior", "Two supplied synthetic scenarios, four baseline/candidate requests; candidate format checks passed, baseline format checks failed. Tools, foundations and original source unchanged. Narrow instruction adherence, not general behavior or fetched-data grounding.", "prompt"),
    ("Suspect profiles", "Owner-scoped SQLite revisions and cited historical activity work through native offline tools and real UI; refresh/API read-back and matching owner/citation/stale-write refusals observed. No production lifespan or cloud filesystem proof.", "profile"),
    ("Cloud", "Authorization already explicit. Offline plan/preflight tooling exists; no production image, deployment, live auth, exact-artifact rollback or resource reconciliation proven. Durable SQLite/profile and authored-agent filesystem semantics remain unresolved.", "cloud"),
)
FAILURES = (
    ("Initial overseer dispatch unavailable", "dispatch_blocked", "Later exact-overseer receipt supersedes this adoption blocker; original retained."),
    ("Native credential refusal", "handoff_blocked", "No submitted candidate; actual requests unknown. Credential fallback repaired before successful installed-skill trial."),
    ("Dashboard selected-run reload HTTP 400", "dashboard_blocked", "Initial smoke: one passed, one failed. Later reload and strict invalid-query refusals pass."),
    ("Interrupted dashboard smoke", "smoke_interrupted", "Two skipped, not a success; unchanged rerun records two passed."),
    ("Profile fixture attempts", "profile", "Retained attempts include unused fixture declarations and a constructor race; offline DNS guard blocked an external attempt. Later 58-check receipt has no external attempts."),
    ("Cloud incomplete", "cloud", "Receipt could not certify focused execution; parent later reports seven offline tests passed. Neither proves deployment."),
)
GAPS = (
    "Arbitrary repository code-edit executor is not implemented; authoring is bounded configuration only.",
    "Independent evaluator OS isolation and held-out protection are missing.",
    "Fair repeated A/B improvement, baseline coding effort, construction cost and billing reconciliation are unproven. Decisions remain inconclusive.",
    "All four Investigation variations are not integrated into one accepted campaign, including required deployed journeys.",
    "Domain intake registration tests do not establish an SME-confirmed brief-to-useful-workflow or general domain transfer.",
    "Production cloud deployment is not done. Durable profiles, authored-agent filesystem, tenant authentication and signed-agent replay persistence need implementation/proof, not new permission.",
    "Exact application rollback and resource reconciliation are unverified; synthetic restore is not production recovery.",
)


def field(document, dotted):
    value = document
    for key in dotted.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def safe_path(root, relative):
    path = root / relative
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise ValueError("symlink_refused")
    return path


def build_summary(root=ROOT):
    documents = {}
    evidence = []
    for owner, relative in RECEIPTS.items():
        path = safe_path(root, relative)
        digest = None
        state = "unknown: missing receipt"
        if path.is_file():
            raw = path.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            try:
                document = json.loads(raw)
                if not isinstance(document, dict):
                    raise ValueError("receipt must be an object")
                documents[owner] = document
                state = "available"
            except (ValueError, UnicodeError):
                state = "unknown: invalid receipt"
        evidence.append({"owner": owner, "path": relative, "sha256": digest, "state": state})
    metrics = []
    for label, owner, selector, unit in METRICS:
        value = field(documents.get(owner, {}), selector)
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            value = None
        metrics.append({"label": label, "value": value, "unit": unit,
                        "receipt": RECEIPTS[owner], "field": selector})
    observations = [{"title": title, "detail": detail if owner in documents else "unknown: receipt unavailable",
                     "receipt": RECEIPTS[owner]} for title, detail, owner in FINDINGS]
    history = [{"title": title, "detail": detail if owner in documents else "unknown: receipt unavailable",
                "receipt": RECEIPTS[owner]} for title, owner, detail in FAILURES]
    return {"schema_version": 1, "status": STATUS, "date_label": "2026-09-19",
            "clock_caveat": "Receipt filenames/session date differ from some runtime timestamps (2026-09-18); monotonic durations are not whole-project effort.",
            "outcome": "Supported local process demonstrated; comparative improvement not established.",
            "gates": [{"gate": gate, "status": status, "evidence": detail} for gate, status, detail in GATES],
            "metrics": metrics, "observations": observations, "failure_history": history,
            "recorded_checks": [
                {"scope": "Framework before report tests", "result": "152 passed", "provenance": "Parent-verified deploy/deploy.sh test; supplied assignment, not rerun here"},
                {"scope": "Investigation adapter", "result": "4 passed", "provenance": "Parent-verified adapter suite; supplied assignment, supersedes stale profile assertion blocker"},
                {"scope": "Cloud offline tooling", "result": "7 passed", "provenance": "Parent-verified deploy.tests.test_cloud; supplied assignment, not deployment proof"},
                {"scope": "Profile backend", "result": "84 passed" if any(check.get("result") == "84 passed; one existing Starlette deprecation warning" for check in documents.get("profile", {}).get("checks", [])) else "unknown", "provenance": RECEIPTS["profile"] + "#checks"},
                {"scope": "Profile frontend", "result": "29 passed" if any(check.get("result") == "29 passed" and check.get("command") == "npm test" for check in documents.get("profile", {}).get("checks", [])) else "unknown", "provenance": RECEIPTS["profile"] + "#checks"},
            ],
            "gaps": list(GAPS), "evidence": evidence,
            "links": {"dashboard": "http://localhost:9020", "dashboard_liveness": "unknown: not checked by offline report generation",
                      "desktop": "optimization_framework/frontend/artifacts/dashboard-integration/native-current/1440-comparison.png",
                      "mobile": "optimization_framework/frontend/artifacts/dashboard-integration/native-current/390-candidate-evidence.png"},
            "retention": "Original receipts and prior generated reports retained byte-for-byte under optimization_framework/reports/; original generated reports use -v1 filenames. Failed attempts and private external state retained. No server started/stopped, model/cloud calls or runtime tasks performed by this generator."}


def display(value):
    if value is None:
        return "unknown"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def render_html(summary):
    def text(value):
        return escape(str(value), quote=True)

    def link(path, label):
        return f'<a href="../../{text(path)}">{text(label)}</a>'

    metrics = "".join(f'<tr><th>{text(row["label"])}</th><td class="number">{display(row["value"])}</td><td>{text(row["unit"])}</td><td>{link(row["receipt"], row["field"])}</td></tr>' for row in summary["metrics"])
    gates = "".join(f'<tr><th>{row["gate"]}</th><td>{text(row["status"])}</td><td>{text(row["evidence"])}</td></tr>' for row in summary["gates"])
    observations = "".join(f'<article><h3>{text(row["title"])}</h3><p>{text(row["detail"])}</p>{link(row["receipt"], "Receipt")}</article>' for row in summary["observations"])
    failures = "".join(f'<li><strong>{text(row["title"])}</strong><p>{text(row["detail"])} {link(row["receipt"], "Receipt")}</p></li>' for row in summary["failure_history"])
    checks = "".join(f'<tr><th>{text(row["scope"])}</th><td>{text(row["result"])}</td><td>{text(row["provenance"])}</td></tr>' for row in summary["recorded_checks"])
    receipts = "".join(f'<tr><th>{link(row["path"], row["owner"])}</th><td>{text(row["state"])}</td><td><code>{text(row["sha256"] or "unknown")}</code></td></tr>' for row in summary["evidence"])
    gaps = "".join(f'<li>{text(gap)}</li>' for gap in summary["gaps"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Optimization Framework | Implementation Report</title><style>
:root{{--ink:#202523;--muted:#56635c;--line:#c9d3cb;--green:#135c45;--paper:#f8faf8;--warn:#8b3a28}}
*{{box-sizing:border-box}}body{{margin:0;color:var(--ink);background:var(--paper);font:16px/1.6 Georgia,serif;letter-spacing:0}}
header{{border-top:8px solid var(--green);background:linear-gradient(110deg,#e7f2eb,#f4f6f3);padding:44px max(24px,calc((100% - 1120px)/2)) 32px}}
h1{{font-size:38px;line-height:1.15;margin:12px 0;max-width:850px}}h2{{font-size:26px;margin:0 0 18px}}h3{{font-size:20px;margin:0 0 8px}}p{{margin:10px 0}}
main{{max-width:1168px;margin:auto;padding:0 24px}}section{{padding:32px 0;border-bottom:1px solid var(--line)}}a{{color:var(--green);text-underline-offset:3px}}a:focus-visible{{outline:3px solid var(--warn);outline-offset:4px}}
.eyebrow,nav,.status,th,td,.meta{{font-family:Verdana,sans-serif}}.eyebrow{{font-size:12px;text-transform:uppercase;letter-spacing:0}}.status{{color:var(--warn);font-weight:bold;font-size:16px;max-width:850px}}nav{{display:flex;gap:24px;flex-wrap:wrap;margin-top:22px;font-size:14px}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:30px}}article{{border-left:3px solid var(--line);padding-left:18px}}.table{{overflow:auto}}table{{width:100%;border-collapse:collapse;font-size:13px;text-align:left}}th,td{{padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top;overflow-wrap:anywhere}}th{{font-weight:600}}.number{{font-variant-numeric:tabular-nums;font-weight:bold}}code{{font-size:11px;overflow-wrap:anywhere}}li{{margin-bottom:14px}}.meta{{font-size:13px;color:var(--muted)}}figure{{margin:0}}img{{display:block;width:100%;height:auto;border:1px solid var(--line)}}figcaption{{font-size:14px;margin-top:8px}}footer{{padding:30px 0}}
@media(max-width:650px){{h1{{font-size:29px}}header{{padding:28px 20px}}main{{padding:0 20px}}.grid{{grid-template-columns:1fr}}th,td{{padding:10px 6px}}}}@media print{{header{{background:white}}section{{break-inside:avoid}}nav{{display:none}}}}
</style></head><body><header><div class="eyebrow">Agentcraft / evidence review / {text(summary['date_label'])}</div>
<h1>Optimization Framework</h1><p class="status">{text(summary['status'])}</p><p>{text(summary['outcome'])}</p>
<nav aria-label="Report links"><a href="http://localhost:9020">Local dashboard</a><a href="implementation-summary.json">Summary JSON</a><a href="IMPLEMENTATION_REPORT.md">Technical report</a><a href="#evidence">Receipt index</a></nav></header>
<main><section><h2>Outcome, Not Test Volume</h2><p>Native configuration acceptance and supported process adoption succeeded. No fair A/B improvement is established. Test counts measure engineering coverage, not optimization gains, production readiness or full portfolio completion.</p><p class="meta">Dashboard liveness unknown; linked for existing local session. No server operation performed. {text(summary['clock_caveat'])}</p></section>
<section><h2>What Works Locally</h2><div class="grid">{observations}</div></section>
<section><h2>Acceptance Gates</h2><div class="table"><table><thead><tr><th>Gate</th><th>Status</th><th>Boundary</th></tr></thead><tbody>{gates}</tbody></table></div></section>
<section><h2>Measured Execution</h2><p class="meta">Separate runs; no combined success rate. Missing telemetry is unknown, never zero. Durations rounded to milliseconds; exact values in JSON.</p><div class="table"><table><thead><tr><th>Measurement</th><th>Observed</th><th>Unit</th><th>Evidence field</th></tr></thead><tbody>{metrics}</tbody></table></div></section>
<section><h2>Engineering Checks</h2><p class="meta">Recorded counts are not added: suites overlap and describe different artifacts. New report-generator tests are verified separately.</p><div class="table"><table><thead><tr><th>Scope</th><th>Result</th><th>Provenance</th></tr></thead><tbody>{checks}</tbody></table></div></section>
<section><h2>Recorded Dashboard Views</h2><div class="grid"><figure><a href="../../{summary['links']['desktop']}"><img src="../../{summary['links']['desktop']}" alt="Recorded desktop comparison showing native run evidence" loading="lazy"></a><figcaption>Desktop: historical receipt evidence.</figcaption></figure><figure><a href="../../{summary['links']['mobile']}"><img src="../../{summary['links']['mobile']}" alt="Recorded mobile candidate evidence" loading="lazy" style="max-width:260px"></a><figcaption>Mobile: candidate evidence. Optional local images; report remains readable without them.</figcaption></figure></div></section>
<section><h2>Failures Retained</h2><ul>{failures}</ul></section><section><h2>Remaining Work</h2><ul>{gaps}</ul></section>
<section id="evidence"><h2>Receipt Index</h2><p class="meta">Fixed owner allowlist; SHA-256 of receipt bytes. Large source manifests stay in original receipts. No raw model output, private credentials or reasoning copied.</p><div class="table"><table><thead><tr><th>Receipt</th><th>Availability</th><th>SHA-256</th></tr></thead><tbody>{receipts}</tbody></table></div></section>
<footer class="meta">{text(summary['retention'])}</footer></main></body></html>
'''


def publish(root=ROOT):
    summary = build_summary(root)
    outputs = {
        "optimization_framework/reports/implementation-summary.json": (json.dumps(summary, indent=2, allow_nan=False) + "\n").encode(),
        "optimization_framework/reports/implementation-report.html": render_html(summary).encode(),
    }
    for relative, content in outputs.items():
        path = safe_path(root, relative)
        if path.exists() and (not path.is_file() or path.read_bytes() != content):
            raise FileExistsError(f"output_conflict: {relative}")
    for relative, content in outputs.items():
        path = safe_path(root, relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            with path.open("xb") as stream:
                stream.write(content)
        if path.read_bytes() != content:
            raise RuntimeError("output_readback_mismatch")
    return list(outputs)


if __name__ == "__main__":
    print(json.dumps({"status": STATUS, "outputs": publish()}))