"""Generates the per-incident HTML dashboard for supply-chain-guardian."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agent.reasoning import run_all  # noqa: E402

STATE_COLORS = {
    "Monitoring": "#6b7280",
    "Issue Detected": "#f59e0b",
    "Investigating": "#3b82f6",
    "Recommendation Ready": "#8b5cf6",
    "Requires Approval": "#ef4444",
    "Approved": "#10b981",
    "Executed": "#059669",
    "Rejected": "#6b7280",
}

CARD_TEMPLATE = """
<div class="card">
  <div class="card-header">
    <h2>{scenario_id}</h2>
    <span class="badge" style="background:{state_color}">{state}</span>
  </div>
  <p class="trigger">{trigger}</p>
  <div class="evidence-row">
    <div class="chip fabric">Fabric IQ<br><small>mocked</small></div>
    <div class="chip work">Work IQ<br><small>{work_label}</small></div>
    <div class="chip web">Web IQ<br><small>{web_label}</small></div>
    <div class="chip foundry">Foundry IQ<br><small>{foundry_label}</small></div>
  </div>
  <div class="section"><strong>Blast radius:</strong> {blast_summary}</div>
  <div class="section"><strong>Root-cause hypothesis:</strong> {hypothesis}</div>
  <div class="section"><strong>Business impact:</strong> {impact}</div>
  <div class="section"><strong>Recommended mitigation:</strong> {mitigation}</div>
  <div class="section"><strong>Confidence:</strong> {confidence} &nbsp; <strong>Evidence completeness:</strong> {completeness}</div>
  <div class="section"><strong>Consequential actions:</strong> {actions}</div>
  <div class="section"><strong>Execution result:</strong> {execution_result}</div>
</div>
"""

PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Supply Chain Guardian - Dashboard</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:24px; }}
  h1 {{ font-weight:600; }}
  .card {{ background:#1e293b; border-radius:12px; padding:20px; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,.3); }}
  .card-header {{ display:flex; justify-content:space-between; align-items:center; }}
  .badge {{ padding:4px 12px; border-radius:999px; font-size:12px; font-weight:600; color:white; }}
  .trigger {{ color:#94a3b8; font-style:italic; }}
  .evidence-row {{ display:flex; gap:12px; margin:12px 0; }}
  .chip {{ flex:1; text-align:center; padding:8px; border-radius:8px; font-size:13px; font-weight:600; }}
  .chip.fabric {{ background:#1d4ed8; }}
  .chip.work {{ background:#7c3aed; }}
  .chip.web {{ background:#16a34a; }}
  .chip.foundry {{ background:#ea580c; }}
  .chip small {{ font-weight:400; opacity:.85; }}
  .section {{ margin:8px 0; line-height:1.5; }}
</style>
</head>
<body>
<h1>Supply Chain Guardian</h1>
<p style="color:#94a3b8;">Autonomous supply-chain disruption agent. Mocked vs. live sources labelled per card.</p>
{cards}
</body>
</html>
"""


def build_dashboard() -> str:
    cards = [c.to_dict() for c in run_all()]
    rendered = []
    for d in cards:
        br = d["blast_radius"]
        rendered.append(CARD_TEMPLATE.format(
            scenario_id=d["scenario_id"],
            state=d["approval_state"],
            state_color=STATE_COLORS.get(d["approval_state"], "#6b7280"),
            trigger=d["disruption_trigger"],
            work_label="mocked" if d["work_iq_evidence"]["mocked"] else "live",
            web_label="mocked" if d["web_iq_evidence"]["mocked"] else "live",
            foundry_label="mocked" if d["foundry_iq_evidence"]["mocked"] else "live",
            blast_summary=(
                f"plants {', '.join(br['affected_plants']) or 'none'}; "
                f"SKUs {', '.join(br['affected_skus']) or 'none'}; "
                f"customers {', '.join(br['affected_customers']) or 'none'}"
            ),
            hypothesis=d["root_cause_hypothesis"],
            impact=d["estimated_business_impact"],
            mitigation=d["recommended_mitigation"],
            confidence=d["confidence"],
            completeness=d["evidence_completeness"],
            actions=", ".join(d["consequential_actions"]) or "none",
            execution_result=d["execution_result"] or "-",
        ))
    return PAGE_TEMPLATE.format(cards="\n".join(rendered))


INTERACTIVE_PAGE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Supply Chain Guardian - Live Portal</title>
<style>
  :root { color-scheme: dark; }
  body { font-family: -apple-system, Segoe UI, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; padding:24px; }
  h1 { font-weight:600; margin-bottom:4px; }
  .sub { color:#94a3b8; margin-top:0; }
  .status-bar { display:flex; gap:16px; align-items:center; margin:16px 0 24px; font-size:13px; color:#94a3b8; }
  .dot { width:8px; height:8px; border-radius:50%; background:#22c55e; display:inline-block; margin-right:6px; }
  .card { background:#1e293b; border-radius:12px; padding:20px; margin-bottom:20px; box-shadow:0 2px 8px rgba(0,0,0,.3); transition: box-shadow .2s; }
  .card-header { display:flex; justify-content:space-between; align-items:center; }
  .badge { padding:4px 12px; border-radius:999px; font-size:12px; font-weight:600; color:white; }
  .trigger { color:#94a3b8; font-style:italic; }
  .evidence-row { display:flex; gap:12px; margin:12px 0; flex-wrap:wrap; }
  .chip { flex:1; min-width:110px; text-align:center; padding:8px; border-radius:8px; font-size:13px; font-weight:600; }
  .chip.fabric { background:#1d4ed8; } .chip.work { background:#7c3aed; }
  .chip.web { background:#16a34a; } .chip.foundry { background:#ea580c; }
  .chip small { font-weight:400; opacity:.85; display:block; }
  .chip small.detail { font-size:10px; opacity:.75; white-space:normal; }
  .section { margin:8px 0; line-height:1.5; }
  .actions { display:flex; gap:10px; margin-top:14px; }
  button { border:none; border-radius:8px; padding:10px 18px; font-weight:600; cursor:pointer; font-size:14px; }
  .approve { background:#10b981; color:white; }
  .reject { background:#ef4444; color:white; }
  .reprobe { background:#334155; color:#e2e8f0; }
  button:disabled { opacity:.4; cursor:not-allowed; }
  .toast { position:fixed; bottom:24px; right:24px; background:#334155; padding:12px 18px; border-radius:8px; display:none; }
  .refresh-btn { background:#334155; color:#e2e8f0; padding:6px 14px; border-radius:6px; font-size:12px; }
  .activity-panel { background:#111827; border:1px solid #1f2937; border-radius:12px; padding:16px; margin-bottom:24px; }
  .activity-panel h3 { margin:0 0 10px; font-size:14px; color:#94a3b8; text-transform:uppercase; letter-spacing:.05em; }
  .activity-log { max-height:220px; overflow-y:auto; font-family: ui-monospace, Menlo, monospace; font-size:12px; line-height:1.6; }
  .activity-log .row { display:flex; gap:8px; padding:2px 0; border-bottom:1px solid #1f2937; }
  .activity-log .ts { color:#64748b; white-space:nowrap; }
  .activity-log .src { font-weight:700; white-space:nowrap; }
  .activity-log .scenario { color:#64748b; white-space:nowrap; }
  .activity-log .detail { color:#cbd5e1; }
  .src-fabric { color:#60a5fa; } .src-work { color:#c4b5fd; }
  .src-web { color:#86efac; } .src-foundry { color:#fdba74; }
  .src-agent { color:#f0abfc; } .src-human { color:#fde68a; }
  details.evidence-detail { margin-top:14px; background:#0f172a; border:1px solid #1f2937; border-radius:8px; padding:10px 14px; }
  details.evidence-detail summary { cursor:pointer; color:#93c5fd; font-weight:600; font-size:13px; }
  .evidence-block { margin-top:10px; }
  .evidence-block h4 { margin:12px 0 4px; font-size:12px; color:#94a3b8; text-transform:uppercase; }
  .evidence-block ul { margin:4px 0; padding-left:18px; font-size:12px; line-height:1.6; }
  .evidence-block a { color:#93c5fd; }
  .trace-row { font-family: ui-monospace, Menlo, monospace; font-size:11px; padding:2px 0; border-bottom:1px solid #1f2937; }
  .auth-panel { background:#111827; border:1px solid #1f2937; border-radius:12px; padding:16px; margin-bottom:24px; }
  .auth-panel h3 { margin:0 0 10px; font-size:14px; color:#94a3b8; text-transform:uppercase; letter-spacing:.05em; }
  .auth-row { display:flex; gap:12px; align-items:center; margin-bottom:8px; flex-wrap:wrap; }
  .auth-status { font-size:12px; color:#94a3b8; }
  .auth-code-box { background:#0f172a; border:1px solid #1f2937; border-radius:8px; padding:10px 14px; margin-top:8px; font-size:13px; display:none; }
  .auth-code-box .code { font-family: ui-monospace, Menlo, monospace; font-size:20px; font-weight:700; color:#fbbf24; letter-spacing:.08em; }
  .auth-code-box a { color:#93c5fd; }
  .citations { display:flex; flex-wrap:wrap; gap:6px; margin-top:6px; }
  .citation { font-size:11px; background:#0f172a; border:1px solid #1f2937; color:#93c5fd; padding:3px 8px; border-radius:999px; cursor:pointer; text-decoration:none; }
  .citation:hover { border-color:#3b82f6; }
  @keyframes flash-highlight { 0%{background:#1e3a5f;} 100%{background:transparent;} }
  .flash { animation: flash-highlight 1.5s ease-out; }
  .chat-panel { background:#111827; border:1px solid #1f2937; border-radius:12px; padding:16px; margin-bottom:24px; }
  .chat-panel h3 { margin:0 0 4px; font-size:14px; color:#94a3b8; text-transform:uppercase; letter-spacing:.05em; }
  .chat-hint { font-size:12px; color:#64748b; margin-bottom:10px; }
  .chat-log { max-height:220px; overflow-y:auto; margin-bottom:10px; font-size:13px; }
  .chat-row { padding:6px 0; border-bottom:1px solid #1f2937; white-space:pre-wrap; }
  .chat-row .who { font-weight:700; margin-right:6px; }
  .chat-row.you .who { color:#93c5fd; }
  .chat-row.agent .who { color:#86efac; }
  .chat-input-row { display:flex; gap:8px; }
  .chat-input-row input { flex:1; background:#0f172a; border:1px solid #1f2937; border-radius:8px; color:#e2e8f0; padding:8px 12px; font-size:13px; }
  .chat-input-row button { padding:8px 16px; }
</style>
</head>
<body>
<h1>Supply Chain Guardian</h1>
<p class="sub">Autonomous supply-chain disruption agent &mdash; live portal. Click Approve/Reject to move an incident past the approval gate.</p>
<div class="auth-panel">
  <h3>Live IQ source connections</h3>
  <div class="auth-row">
    <span class="auth-status">Foundry IQ (policy search):</span>
    <button class="refresh-btn" onclick="startAuth('search')">Connect Foundry IQ</button>
    <span class="auth-status">Fabric IQ (workspace):</span>
    <button class="refresh-btn" onclick="startAuth('fabric')">Connect Fabric IQ</button>
  </div>
  <div class="auth-code-box" id="auth-box"></div>
</div>
<div class="chat-panel">
  <h3>Agent console</h3>
  <p class="chat-hint">Type a command instead of clicking &mdash; e.g. "explain scenario-01-clear-disruption", "approve scenario-02-cascading-disruption", "reprobe scenario-03", "simulate", "list", "help". Rule-based command parser (not an LLM); every consequential action still requires you to name the incident explicitly.</p>
  <div class="chat-log" id="chat-log"></div>
  <div class="chat-input-row">
    <input id="chat-input" type="text" placeholder="Type a command, e.g. 'explain scenario-01'..." onkeydown="if(event.key==='Enter') sendChat();" />
    <button class="refresh-btn" onclick="sendChat()">Send</button>
  </div>
</div>
<div class="status-bar">
  <span><span class="dot"></span>Idle &middot; no live-IQ calls until you click Load below</span>
  <span id="last-updated">-</span>
  <button class="refresh-btn" onclick="load()" id="load-btn">Load live incidents</button>
  <button class="refresh-btn" onclick="simulate()">Simulate new disruption</button>
</div>
<div class="activity-panel">
  <h3>Agent Activity &mdash; live, cross-incident feed of every IQ call and decision</h3>
  <div class="activity-log" id="activity-log">Click "Load live incidents" above to fetch activity.</div>
</div>
<div id="cards">Click "Load live incidents" above &mdash; nothing is fetched automatically, to avoid spending live-IQ calls when nobody is viewing the page.</div>
<div class="toast" id="toast"></div>
<script>
const STATE_COLORS = {
  "Monitoring": "#6b7280", "Issue Detected": "#f59e0b", "Investigating": "#3b82f6",
  "Recommendation Ready": "#8b5cf6", "Requires Approval": "#ef4444",
  "Approved": "#10b981", "Executed": "#059669", "Rejected": "#6b7280"
};

function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.style.display = "block";
  setTimeout(() => t.style.display = "none", 3500);
}

async function decide(id, decision) {
  const res = await fetch(`/incidents/${id}/decision`, {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({decision})
  });
  const body = await res.json();
  if (!res.ok) { toast(`Rejected by server: ${body.detail}`); }
  else { toast(`${id} -> ${decision}`); }
  load();
}

async function reprobe(id) {
  toast(`Re-probing live IQ sources for ${id}...`);
  const res = await fetch(`/incidents/${id}/reprobe`, {method: "POST"});
  if (res.ok) { toast(`${id} evidence refreshed`); } else { toast(`Re-probe failed for ${id}`); }
  load();
}

async function simulate() {
  toast("Deriving a new disruption from the live ontology graph...");
  const res = await fetch("/incidents/simulate", {method: "POST"});
  const body = await res.json();
  if (res.ok) { toast(`New incident ${body.scenario_id} created`); } else { toast("Simulation failed"); }
  load();
}

let _authPollTimer = null;

async function startAuth(target) {
  if (_authPollTimer) { clearInterval(_authPollTimer); _authPollTimer = null; }
  const box = document.getElementById("auth-box");
  box.style.display = "block";
  box.innerHTML = "Starting sign-in...";
  const res = await fetch("/auth/device/start", {
    method: "POST", headers: {"content-type": "application/json"},
    body: JSON.stringify({target})
  });
  if (!res.ok) { box.innerHTML = "Could not start sign-in. Try again."; return; }
  const flow = await res.json();
  box.innerHTML = `Go to <a href="${flow.verification_uri}" target="_blank" rel="noopener">${flow.verification_uri}</a> `
    + `and enter code: <span class="code">${flow.user_code}</span><br>`
    + `<span class="auth-status">Waiting for sign-in to complete&hellip;</span>`;
  const deadline = Date.now() + flow.expires_in * 1000;
  const intervalMs = Math.max(flow.interval, 5) * 1000;
  _authPollTimer = setInterval(async () => {
    if (Date.now() > deadline) {
      clearInterval(_authPollTimer); _authPollTimer = null;
      box.innerHTML = "Sign-in code expired. Click Connect again to retry.";
      return;
    }
    const pollRes = await fetch("/auth/device/poll", {
      method: "POST", headers: {"content-type": "application/json"},
      body: JSON.stringify({device_code: flow.device_code})
    });
    const status = await pollRes.json();
    if (status.status === "success") {
      clearInterval(_authPollTimer); _authPollTimer = null;
      box.innerHTML = `Connected. Click "Load live incidents" (or Re-probe) to see it go live.`;
      toast(`${target === "search" ? "Foundry IQ" : "Fabric IQ"} connected`);
    } else if (status.status === "error") {
      clearInterval(_authPollTimer); _authPollTimer = null;
      box.innerHTML = "Sign-in failed: " + (status.detail || "unknown error");
    }
    // status === "pending": keep waiting silently
  }, intervalMs);
}

function srcClass(source) {
  return "src-" + source.toLowerCase().replace(/[^a-z]/g, "");
}

function renderEvidenceDetail(d) {
  const wk = d.work_iq_evidence, web = d.web_iq_evidence, fdy = d.foundry_iq_evidence, fab = d.fabric_iq_evidence;
  const msgs = (wk.live_probe && wk.live_probe.messages) || [];
  const webTitles = (!web.mocked && web.data.titles) || [];
  const webUrls = (!web.mocked && web.data.urls) || [];
  const fdyMatches = (fdy.live_probe && fdy.live_probe.live && fdy.live_probe.matches) || [];
  const fabItems = (fab.live_probe && fab.live_probe.live && fab.live_probe.items) || [];

  const workBlock = msgs.length
    ? `<ul>${msgs.map(m => `<li>"${m.subject}" &mdash; from ${m.from} at ${m.received}</li>`).join("")}</ul>`
    : `<p style="color:#64748b;font-size:12px;">No live messages retrieved this cycle.</p>`;
  const webBlock = webTitles.length
    ? `<ul>${webTitles.map((t, i) => `<li><a href="${webUrls[i] || '#'}" target="_blank" rel="noopener">${t}</a></li>`).join("")}</ul>`
    : `<p style="color:#64748b;font-size:12px;">Live search unavailable this cycle &mdash; showing fallback snapshot above.</p>`;
  const foundryBlock = fdyMatches.length
    ? `<ul>${fdyMatches.map(m => `<li>${m.title || m.id} (${m.category || "uncategorized"})</li>`).join("")}</ul>`
    : `<p style="color:#64748b;font-size:12px;">Live index call attempted; not yet consented (see Foundry IQ chip).</p>`;
  const fabricBlock = fabItems.length
    ? `<ul>${fabItems.map(i => `<li>${i.name} (${i.type})</li>`).join("")}</ul>`
    : `<p style="color:#64748b;font-size:12px;">Live workspace call attempted; not yet consented (see Fabric IQ chip).</p>`;

  const traceRows = (d.trace || []).slice().reverse().map(t =>
    `<div class="trace-row"><span class="ts">${t.ts}</span> <span class="${srcClass(t.source)}">[${t.source}]</span> ${t.action}: ${t.detail}</div>`
  ).join("");

  return `
  <details class="evidence-detail">
    <summary>Show retrieved evidence &amp; reasoning trace (what the agent actually fetched, from where)</summary>
    <div class="evidence-block">
      <div id="ev-work-${d.scenario_id}"><h4>Work IQ &mdash; live inbox messages</h4>${workBlock}</div>
      <div id="ev-web-${d.scenario_id}"><h4>Web IQ &mdash; live search results</h4>${webBlock}</div>
      <div id="ev-foundry-${d.scenario_id}"><h4>Foundry IQ &mdash; policy index matches</h4>${foundryBlock}</div>
      <div id="ev-fabric-${d.scenario_id}"><h4>Fabric IQ &mdash; workspace items</h4>${fabricBlock}</div>
      <h4>Full reasoning trace (most recent first)</h4>${traceRows || "<p style=\\"color:#64748b;font-size:12px;\\">No trace yet.</p>"}
    </div>
  </details>`;
}

function jumpTo(anchorId) {
  const el = document.getElementById(anchorId);
  if (!el) return;
  const details = el.closest("details.evidence-detail");
  if (details) details.open = true;
  el.scrollIntoView({behavior: "smooth", block: "center"});
  el.classList.add("flash");
  setTimeout(() => el.classList.remove("flash"), 1500);
}

function citationsFor(d) {
  // Mirrors the exact fields the backend correlated to produce the hypothesis, so each
  // citation names the real transaction/record (not just "trust me") and jumps straight
  // to that evidence block below.
  const br = d.blast_radius;
  const cites = [{
    label: `Fabric IQ: shipment ${br.shipment_id || "?"} / material ${br.material_id || "?"}`,
    anchor: `ev-fabric-${d.scenario_id}`
  }];
  const fdy = d.foundry_iq_evidence.data || [];
  if (fdy.length) {
    cites.push({label: `Foundry IQ: ${fdy.map(p => p.id).join(", ")}`, anchor: `ev-foundry-${d.scenario_id}`});
  }
  const query = `${br.material_id || ""} supplier shipment delay ${br.shipment_id || ""}`.trim();
  cites.push({label: `Web IQ: "${query}"`, anchor: `ev-web-${d.scenario_id}`});
  if (d.work_iq_evidence.data) {
    cites.push({label: "Work IQ: org context on file", anchor: `ev-work-${d.scenario_id}`});
  }
  return cites;
}

function card(d) {
  const br = d.blast_radius;
  const label = (ev) => ev.mocked ? "mocked" : "live";
  const pending = d.approval_state === "Requires Approval";
  const fab = d.fabric_iq_evidence, wk = d.work_iq_evidence, web = d.web_iq_evidence, fdy = d.foundry_iq_evidence;

  // Per-source detail line: shows exactly what the live probe did (real call attempted,
  // real result, or the honest reason it fell back), so nothing reads as flatly "mocked".
  const fabDetail = fab.live_probe && fab.live_probe.live
    ? `${fab.live_probe.items.length} item(s) in real workspace`
    : `live probe attempted: ${(fab.live_probe && fab.live_probe.error) || "not configured"}`;
  const wkDetail = wk.live_probe && wk.live_probe.mocked === false
    ? `${(wk.live_probe.messages || []).length} live inbox message(s) read`
    : `live probe attempted: ${(wk.live_probe && wk.live_probe.reason) || "not configured"}`;
  const webDetail = !web.mocked
    ? `live search: "${web.data.query}" (${web.data.result_count} result(s))`
    : `live call attempted this refresh: ${(web.data && web.data.live_attempt_failed_reason) || "not configured"} (showing fallback snapshot)`;
  const fdyDetail = fdy.live_probe && fdy.live_probe.live
    ? `${fdy.live_probe.matches.length} match(es) in real index`
    : `live probe attempted: ${(fdy.live_probe && fdy.live_probe.error) || "not configured"}`;

  return `
  <div class="card">
    <div class="card-header">
      <h2>${d.scenario_id}</h2>
      <span class="badge" style="background:${STATE_COLORS[d.approval_state] || '#6b7280'}">${d.approval_state}</span>
    </div>
    <p class="trigger">${d.disruption_trigger}</p>
    <div class="evidence-row">
      <div class="chip fabric" title="${fabDetail}">Fabric IQ<small>${label(fab)}</small><small class="detail">${fabDetail}</small></div>
      <div class="chip work" title="${wkDetail}">Work IQ<small>${label(wk)}</small><small class="detail">${wkDetail}</small></div>
      <div class="chip web" title="${webDetail}">Web IQ<small>${label(web)}</small><small class="detail">${webDetail}</small></div>
      <div class="chip foundry" title="${fdyDetail}">Foundry IQ<small>${label(fdy)}</small><small class="detail">${fdyDetail}</small></div>
    </div>
    <div class="section"><strong>Blast radius:</strong> plants ${br.affected_plants.join(", ") || "none"}; SKUs ${br.affected_skus.join(", ") || "none"}; customers ${br.affected_customers.join(", ") || "none"}</div>
    <div class="section"><strong>Root-cause hypothesis:</strong> ${d.root_cause_hypothesis}
      <div class="citations">${citationsFor(d).map(c => `<a href="#" class="citation" onclick="jumpTo('${c.anchor}');return false;">${c.label}</a>`).join("")}</div>
    </div>
    <div class="section"><strong>Business impact:</strong> ${d.estimated_business_impact}</div>
    <div class="section"><strong>Recommended mitigation:</strong> ${d.recommended_mitigation}</div>
    <div class="section"><strong>Confidence:</strong> ${d.confidence} &nbsp; <strong>Evidence completeness:</strong> ${d.evidence_completeness}</div>
    <div class="section" style="color:#94a3b8;font-size:12px;">Evidence last refreshed: ${d.evidence_refreshed_at || "-"} (auto-refreshes every 60s; monitor loop is always running)</div>
    <div class="section"><strong>Execution result:</strong> ${d.execution_result || "-"}</div>
    ${d.email_receipt ? `<div class="section"><strong>Notification sent:</strong> ${d.email_receipt.sent ? "✅ live email sent to " + d.email_receipt.to : "not sent (" + (d.email_receipt.reason || d.email_receipt.error || "unknown") + ")"}</div>` : ""}
    ${renderEvidenceDetail(d)}
    <div class="actions">
      <button class="approve" ${pending ? "" : "disabled"} onclick="decide('${d.scenario_id}','approved')">Approve</button>
      <button class="reject" ${pending ? "" : "disabled"} onclick="decide('${d.scenario_id}','rejected')">Reject</button>
      <button class="reprobe" onclick="reprobe('${d.scenario_id}')">Re-probe live IQ now</button>
    </div>
  </div>`;
}

function appendChat(who, text) {
  const log = document.getElementById("chat-log");
  const row = document.createElement("div");
  row.className = "chat-row " + who;
  const whoSpan = document.createElement("span");
  whoSpan.className = "who";
  whoSpan.textContent = (who === "you" ? "You" : "Agent") + ":";
  const txtSpan = document.createElement("span");
  txtSpan.textContent = text; // textContent, not innerHTML: never render chat text as markup
  row.appendChild(whoSpan);
  row.appendChild(txtSpan);
  log.appendChild(row);
  log.scrollTop = log.scrollHeight;
}

async function sendChat() {
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text) return;
  appendChat("you", text);
  input.value = "";
  try {
    const res = await fetch("/chat", {method: "POST", headers: {"content-type": "application/json"}, body: JSON.stringify({message: text})});
    const data = await res.json();
    appendChat("agent", data.reply);
    if (data.action_taken) { load(); } // a command changed state; refresh cards to reflect it
  } catch (e) {
    appendChat("agent", "Request failed: " + e);
  }
}

async function loadActivity() {
  const res = await fetch("/activity?limit=80");
  const events = await res.json();
  const log = document.getElementById("activity-log");
  if (!events.length) { log.innerHTML = "<p style='color:#64748b;'>No activity recorded yet.</p>"; return; }
  log.innerHTML = events.slice().reverse().map(e =>
    `<div class="row"><span class="ts">${e.ts}</span><span class="scenario">${e.scenario_id}</span><span class="src ${srcClass(e.source)}">[${e.source}]</span><span class="detail">${e.action}: ${e.detail}</span></div>`
  ).join("");
}

async function load() {
  const res = await fetch("/incidents");
  const data = await res.json();
  document.getElementById("cards").innerHTML = data.map(card).join("\\n");
  document.getElementById("last-updated").textContent = "Last updated " + new Date().toLocaleTimeString();
  loadActivity();
}

// Deliberately no auto-call to load() here: the page stays fully inert (no fetch, no
// live-IQ calls) until the human clicks "Load live incidents", even if the page itself
// gets reloaded/renavigated by something outside this app's control (browser, extension,
// proxy prefetch, etc.). This is the hard guarantee that cost only accrues on real usage.
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "reports" / "latest.html"))
    args = parser.parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(build_dashboard(), encoding="utf-8")
    print(f"wrote {out_path}")
