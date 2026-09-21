import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { accessSync, constants, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute, join, relative, resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

if (process.argv.length === 3 && process.argv[2] === "--help") {
  console.log("Native offline browser verification: ephemeral signed HTTP; synthetic native I/O; production lifespan not verified.\nPython: LIVE_PYTHON, then VIRTUAL_ENV/bin/python, then Investigation .venv/bin/python. Requires Python 3.12 virtualenv with Investigation dependencies including pytest and pytest-asyncio, frontend node_modules, and Playwright Chromium. No automatic install or sync.\nArtifacts: absolute ARTIFACT_DIR outside the checkout (default /tmp/agentcraft-investigation-browser). Source imports remain editable; frontend build output and synthetic state stay under the artifact directory. No cloud or user configuration.\nRun from Investigation: LIVE_PYTHON=/path/to/venv/bin/python ./deploy/deploy.sh browser-verify native-offline");
  process.exit(0);
}
assert.equal(process.argv.length, 2, "unknown native browser arguments");

const frontend = fileURLToPath(new URL("../../", import.meta.url));
const project = fileURLToPath(new URL("../../../", new URL("../../", import.meta.url)));
const checkout = resolve(project, "../..");
const within = (directory, path) => {
  const location = relative(directory, path);
  return location === "" || (!location.startsWith("..") && !isAbsolute(location));
};
const python = resolve(process.env.LIVE_PYTHON || join(process.env.VIRTUAL_ENV || join(project, ".venv"), "bin/python"));
assert.ok(!within(join(checkout, "template_apps"), python) || within(project, python),
  "native browser cannot use another template's interpreter");
assert.ok(existsSync(python), "Native browser Python missing; set LIVE_PYTHON to an existing Investigation virtualenv interpreter.");
accessSync(python, constants.X_OK);
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");
const outputRoot = process.env.ARTIFACT_DIR || "/tmp/agentcraft-investigation-browser";
assert.ok(isAbsolute(outputRoot) && !within(checkout, resolve(outputRoot)), "native browser artifacts must stay outside checkout");
let ancestor = resolve(outputRoot);
while (!existsSync(ancestor)) ancestor = dirname(ancestor);
assert.ok(!within(checkout, realpathSync(ancestor)), "native browser artifacts must resolve outside checkout");
mkdirSync(outputRoot, { recursive: true, mode: 0o700 });
assert.ok(!within(checkout, realpathSync(outputRoot)));
const output = mkdtempSync(join(outputRoot, "run-"));
const state = join(output, "state");
const dist = join(output, "frontend-dist");
mkdirSync(state, { mode: 0o700 });
const environment = { PATH: dirname(process.execPath) + ":/usr/bin:/bin", HOME: state,
  PYTHON_DOTENV_DISABLED: "1", PYTHONDONTWRITEBYTECODE: "1", NODE_DISABLE_COMPILE_CACHE: "1",
  CYBEREYE_NATIVE_BROWSER_PYTHON: python };
const report = { status: "running", synthetic: true, production_lifespan: "not verified",
  output, checks: [], phases: [], screenshots: [], browser_errors: [], blocked_browser_requests: [] };
const check = (name, detail) => { report.checks.push({ name, detail }); console.log(`PASS ${name}`); };

function frames(text) {
  return text.replace(/\r\n/g, "\n").split("\n\n").filter((frame) => frame.trim()).map((frame) => {
    const lines = frame.split("\n");
    const event = lines.find((line) => line.startsWith("event:"))?.slice(6).trim();
    const data = lines.filter((line) => line.startsWith("data:")).map((line) => line.slice(5).trim()).join("\n");
    return { event, data: JSON.parse(data) };
  });
}

function responseWait(page, predicate) {
  const pending = page.waitForResponse(predicate);
  pending.catch(() => {});
  return pending;
}

async function observedStream(page, path, occurrence = 0) {
  await page.waitForFunction(({ path, occurrence }) => {
    const stream = window.__nativeStreams?.filter((stream) => stream.path === path)[occurrence];
    return stream && (stream.closed || stream.error || /(?:^|\n)event:\s*(done|error)\n(?:[^\n]+\n)*\n/.test(stream.text));
  }, { path, occurrence });
  const stream = await page.evaluate(({ path, occurrence }) =>
    window.__nativeStreams.filter((stream) => stream.path === path)[occurrence], { path, occurrence });
  assert.equal(stream.error, "", JSON.stringify(stream));
  assert.equal(stream.truncated, false);
  return frames(stream.text);
}

async function phase(name, server, walk) {
  try {
    const value = await walk();
    report.phases.push({ name, status: "PASS" });
    return value;
  } catch (error) {
    const failure = { name, status: "FAIL", error: String(error.stack || error) };
    report.phases.push(failure);
    writeFileSync(join(output, `${name}-failure.json`), JSON.stringify({ ...failure,
      native: await server.command("snapshot").catch(() => null) }, null, 2) + "\n");
    console.error(`FAIL ${name}: ${error.message}`);
    return null;
  }
}

async function scanWalk(page, server, send) {
  const baseline = await server.command("snapshot");
  await server.command("prepare-scan");
  const declared = await (await send("GET", "/api/cyber/scenarios")).json();
  const scenario = declared.find((item) => item.id === "focal-privileged-session");
  await page.getByLabel("Test Scenarios").selectOption(scenario.id);
  assert.equal(await page.getByLabel("Scan start UTC").inputValue(), scenario.start.slice(0, 16));
  assert.equal(await page.getByLabel("Scan end UTC").inputValue(), scenario.end.slice(0, 16));
  check("scenario-window-readback", scenario);
  const streamed = (path) => responseWait(page, (response) => new URL(response.url()).pathname === path);
  const scanPending = streamed("/api/cyber/scan/stream");
  const summaryPending = streamed("/api/cyber/situations/summary/stream");
  const diagnosisPending = streamed("/api/cyber/situations/diagnose");
  const evidencePending = responseWait(page, (response) => new URL(response.url()).pathname.startsWith("/api/cyber/evidence/"));
  for (const pending of [scanPending, summaryPending, diagnosisPending, evidencePending]) pending.catch(() => {});
  await page.locator(".scanner-scan-button").click();
  const scanResponse = await scanPending;
  const scanEvents = await observedStream(page, "/api/cyber/scan/stream");
  report.scan_events = scanEvents;
  assert.equal(scanResponse.status(), 200);
  assert.equal(scanEvents.at(-1).event, "done", JSON.stringify(scanEvents));
  assert.equal(scanEvents.filter((frame) => frame.event === "rule_completed").length, 5);
  const scan = scanEvents.at(-1).data;
  assert.equal(scan.situations.length, 1);
  assert.equal(scan.rule_executions.length, 5);
  assert.equal(scan.situations[0].patterns.length, 3);
  check("real-five-rule-scan", scan);
  const summaryResponse = await summaryPending;
  const diagnosisResponse = await diagnosisPending;
  assert.equal(summaryResponse.status(), 200);
  assert.equal(diagnosisResponse.status(), 200);
  const summary = await observedStream(page, "/api/cyber/situations/summary/stream");
  const diagnosis = await observedStream(page, "/api/cyber/situations/diagnose");
  report.summary_events = summary;
  report.diagnosis_events = diagnosis;
  for (const [name, events] of [["summary", summary], ["diagnosis", diagnosis]]) {
    assert.equal(events.at(-1).event, "done", JSON.stringify(events));
    assert.equal(events.at(-1).data.status, "completed");
    assert.equal(events.filter((frame) => frame.event === "done").length, 1);
    assert.equal(events.filter((frame) => frame.event === "error").length, 0);
    check("automatic-native-" + name, events.map((frame) => frame.event));
  }
  assert.equal(diagnosis.at(-1).data.recorded, true);
  assert.equal(diagnosis.at(-1).data.sequenced, true);
  const recorded = diagnosis.find((frame) => frame.event === "diagnosis").data;
  assert.equal(recorded.situation_type_supported, true);
  assert.deepEqual(recorded.unsupported_citations, []);
  assert.equal(recorded.citations[0].path, "synthetic/enterprise-attack.json");
  const sequence = diagnosis.find((frame) => frame.event === "sequence_step").data;
  assert.deepEqual(sequence.evidence.map((item) => item.evidence_id), ["synthetic-event-1", "attack:synthetic-analytic"]);
  assert.equal(sequence.evidence[0].retrieval.retrieval_id, "call-telemetry");
  assert.equal(sequence.evidence[1].retrieval.retrieval_id, "call-knowledge");
  check("native-diagnosis-evidence-provenance", sequence);
  await page.locator("[data-testid='investigation-stream'] .workload-state.done").waitFor();
  assert.equal(await page.locator("[data-testid='investigation-stream'] .tool-card").count(), 5);
  assert.equal(await page.locator("[data-testid='investigation-stream'] .tool-state.running").count(), 0);
  const evidenceResponse = await evidencePending;
  const evidence = await evidenceResponse.json();
  assert.equal(evidenceResponse.status(), 200);
  assert.equal(evidence.row_count, 1);
  assert.equal(evidence.rows[0][evidence.columns.indexOf("resource_id")], "synthetic-event-1");
  report.evidence = evidence;
  await page.getByRole("navigation", { name: "Tool board views" }).getByRole("button", { name: "evidence", exact: true }).click();
  await page.locator(".evidence-view").getByText("synthetic-event-1", { exact: true }).waitFor();
  check("real-evidence-board-readback", evidence);
  const before = await server.command("snapshot");
  for (const [method, path, options, expected] of [
    ["POST", "/api/cyber/scan/stream", { unsigned: true, body: JSON.stringify({ start: scenario.start, end: scenario.end }) }, 401],
    ["GET", `/api/cyber/evidence/${scan.situations[0].situation_id}`, { slug: "foreign" }, 404],
    ["POST", "/api/cyber/situations/diagnose", { unsigned: true, body: JSON.stringify(scan.situations[0]) }, 401],
  ]) {
    const response = await send(method, path, options);
    assert.equal(response.status, expected);
    check("scan-refusal-" + method + "-" + path, expected);
  }
  const after = await server.command("snapshot");
  for (const path of ["/api/cyber/situations/diagnose", "/api/cyber/situations/summary/stream"]) {
    assert.equal(after.http.slice(baseline.http.length).filter((request) =>
      request.path === path && request.status === 200).length, 1, `duplicate automatic request: ${path}`);
  }
  assert.equal(after.attempts.length, before.attempts.length);
  assert.equal(after.last_scan.situations[0].situation_id, scan.situations[0].situation_id);
  assert.ok(Object.values(after.model_plans_remaining).every((count) => count === 0));
  assert.ok(Object.values(after.data_plans_remaining).every((count) => count === 0));
  assert.ok(Object.values(after.search_plans_remaining).every((count) => count === 0));
  assert.ok(Object.values(after.graph_plans_remaining).every((count) => count === 0));
  const delta = { model: after.model_requests.length - baseline.model_requests.length,
    adx: after.adx_attempts - baseline.adx_attempts,
    search: after.search_attempts - baseline.search_attempts,
    graph: after.graph_scripts.length - baseline.graph_scripts.length };
  assert.deepEqual(delta, { model: 7, adx: 7, search: 1, graph: 0 });
  assert.equal(after.attempts.filter((attempt) => attempt.service === "adx"
    && attempt.path === "/api/cyber/scan/stream").length, 5);
  assert.equal(after.attempts.filter((attempt) => attempt.service === "adx"
    && attempt.path === "/api/cyber/situations/diagnose").length, 1);
  assert.equal(after.attempts.filter((attempt) => attempt.service === "adx"
    && attempt.path.startsWith("/api/cyber/evidence/")).length, 1);
  check("scan-native-attempts-and-owned-cache", { baseline: { adx: baseline.adx_attempts,
    search: baseline.search_attempts, graph: baseline.graph_scripts.length }, delta });
  return scan;
}

async function queryWalk(page, server, send) {
  const baseline = await server.command("snapshot");
  await server.command("prepare-query");
  const board = page.getByRole("region", { name: "Central tool board", exact: true });
  await board.getByRole("navigation", { name: "Tool board views" })
    .getByRole("button", { name: "tools", exact: true }).click();
  const queryTool = async (name) => {
    const pending = responseWait(page, (response) => new URL(response.url()).pathname === "/api/cyber/query");
    await board.getByRole("button", { name: new RegExp(name) }).click();
    const response = await pending;
    assert.equal(response.status(), 200);
    assert.equal(response.headers()["cache-control"], "no-store, private");
    return await response.json();
  };
  const products = await queryTool("Product composition");
  assert.deepEqual(products.columns, ["product", "events"]);
  assert.equal(products.row_count, 2);
  assert.equal(products.max_rows, 100);
  assert.equal(products.truncated, false);
  await board.locator(".tools-view table").getByText("SYNTHETIC_WINDOWS", { exact: true }).waitFor();
  const rendered = await board.locator(".tools-view tbody tr").evaluateAll((rows) =>
    rows.map((row) => [...row.querySelectorAll("td")].map((cell) => cell.textContent)));
  assert.deepEqual(rendered, products.rows.map((row) => row.map(String)));
  check("query-board-native-envelope-readback", products);
  await board.getByRole("button", { name: "Expand the tools tab to full screen", exact: true }).click();
  await page.locator(".board.panel-fullscreen").waitFor();
  assert.equal(await board.getByRole("button", { name: "Restore the tools tab", exact: true }).getAttribute("aria-pressed"), "true");
  await page.keyboard.press("Escape");
  await page.locator(".board.panel-fullscreen").waitFor({ state: "detached" });
  check("query-board-toolbar-fullscreen-and-escape", "restored without a data request");
  const beforeRefusal = await server.command("snapshot");
  for (const [body, unsigned, expected] of [
    [{ query: "EventsUnified | evaluate python()", max_rows: 1 }, false, 400],
    [{ query: "EventsUnified | take 1", max_rows: 1 }, true, 401],
  ]) {
    const response = await send("POST", "/api/cyber/query", { body: JSON.stringify(body), unsigned });
    assert.equal(response.status, expected);
    if (!unsigned) assert.match((await response.json()).detail, /forbidden/);
  }
  assert.equal((await server.command("snapshot")).attempts.length, beforeRefusal.attempts.length);
  const empty = await queryTool("Authentication mix");
  assert.equal(empty.row_count, 0);
  assert.deepEqual(empty.rows, []);
  await board.locator(".tools-view .trender-empty").waitFor();
  assert.equal(await board.locator(".tools-view table").count(), 0);
  const recovered = await queryTool("Product composition");
  assert.deepEqual(recovered.rows, products.rows);
  await board.locator(".tools-view table").getByText("SYNTHETIC_WINDOWS", { exact: true }).waitFor();
  assert.equal(await board.locator(".tools-view .trender-empty").count(), 0);
  const after = await server.command("snapshot");
  assert.deepEqual({ model: after.model_requests.length - baseline.model_requests.length,
    adx: after.adx_attempts - baseline.adx_attempts, search: after.search_attempts - baseline.search_attempts,
    graph: after.graph_scripts.length - baseline.graph_scripts.length },
  { model: 0, adx: 3, search: 0, graph: 0 });
  assert.ok(after.attempts.slice(baseline.attempts.length).every((attempt) =>
    attempt.service === "adx" && attempt.path === "/api/cyber/query" && attempt.query.endsWith("| take 101")));
  check("query-refusal-empty-state-and-explicit-recovery", { adx: 3, model: 0, empty: empty.row_count });
}

async function chatWalk(page, server, send, session) {
  const baseline = await server.command("snapshot");
  let path;
  await page.route("**/api/chat/*", async (route) => {
    path = new URL(route.request().url()).pathname;
    session.session_id = path.split("/").at(-1);
    await server.command("prepare-chat", { session_id: session.session_id });
    await route.fallback();
  }, { times: 1 });
  await page.getByTestId("chat-tab-defender").click();
  const turn = async (message, occurrence) => {
    const pending = responseWait(page, (response) => new URL(response.url()).pathname === path);
    await page.locator(".chat-input textarea").fill(message);
    await page.locator('.chat-input button[title="Send"]').click();
    assert.equal((await pending).status(), 200);
    const events = await observedStream(page, path, occurrence);
    assert.equal(events.at(-1).event, "done", JSON.stringify(events));
    assert.equal(events.at(-1).data.status, "completed");
    assert.equal(events.filter((frame) => frame.event === "error").length, 0);
    return events;
  };
  const events = await turn("Read the SYNTHETIC category projection, then retrieve its SYNTHETIC advisory evidence.", 0);
  const resultPath = `/api/sessions/${session.session_id}/result`;
  report.chat_events = events;
  const tools = events.filter((frame) => frame.event === "tool_result");
  assert.deepEqual(tools.map((frame) => frame.data.name), ["query_events_kql", "search_mitre_attack"]);
  const telemetry = tools[0].data.result;
  const knowledge = tools[1].data.result;
  assert.equal(telemetry.rows[0].resource_id, "synthetic-chat-event-1");
  assert.equal(typeof telemetry.rows[0].source_time, "string");
  assert.equal(telemetry.scope.max_rows, 1);
  assert.equal(knowledge.category, "mitre_attack");
  assert.equal(knowledge.scope.row_count, 1);
  assert.equal(knowledge.scope.retrieval, "azure-ai-search");
  assert.equal(knowledge.rows[0].doc_id, "attack:synthetic-analytic");
  const message = page.locator("#chat-panel-defender .message.agent:not(.investigation-entry)").last();
  await message.locator(".message-body").getByText(/SYNTHETIC chat returned/).waitFor();
  assert.equal(await message.locator(".tool-card").count(), 2);
  for (const [index, envelope] of [telemetry, knowledge].entries()) {
    const card = message.locator(".tool-card").nth(index);
    await card.locator(".tool-card-head").click();
    await card.locator(".trender table").waitFor();
    assert.deepEqual(await card.locator(".trender th").allTextContents(), envelope.columns.slice(0, 8));
    const cells = await card.locator(".trender tbody td").allTextContents();
    assert.ok(cells.includes(index === 0 ? "synthetic-chat-event-1" : "attack:synthetic-analytic"));
    assert.equal(await card.locator(".tool-state.running").count(), 0);
  }
  const source = message.locator(".tool-card").first().locator(".scv[data-highlighted=true]");
  await source.waitFor();
  const queryCall = events.find((frame) => frame.event === "tool_call_end" && frame.data.name === "query_events_kql");
  const queryArguments = typeof queryCall.data.arguments === "string" ? JSON.parse(queryCall.data.arguments) : queryCall.data.arguments;
  assert.equal((await source.locator(".scv-line-content").allTextContents()).join("\n"), queryArguments.query);
  const wrap = source.getByRole("button", { name: "Wrap lines", exact: true });
  assert.equal(await wrap.getAttribute("aria-pressed"), "true");
  await wrap.click();
  assert.equal(await wrap.getAttribute("aria-pressed"), "false");
  assert.equal(await source.locator(".scv-code.scv-wrap").count(), 0);
  await wrap.click();
  assert.equal(await wrap.getAttribute("aria-pressed"), "true");
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], { origin: server.origin });
  await source.getByRole("button", { name: "Copy source code", exact: true }).click();
  await source.getByRole("button", { name: "Copied source code", exact: true }).waitFor();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), queryArguments.query);
  check("query-source-toolbar-wrap-copy-and-exact-readback", { query: queryArguments.query, wrapped: true });
  const result = await (await send("GET", resultPath)).json();
  assert.equal(result.result.status, "completed");
  assert.equal(result.result.run_id, events.at(-1).data.run_id);
  assert.match(result.result.text, /^SYNTHETIC chat returned/);
  const beforeRefusal = await server.command("snapshot");
  const authorized = beforeRefusal.authorized_tools.slice(baseline.authorized_tools.length);
  assert.deepEqual(authorized.map((call) => call.call_id), ["chat-telemetry", "chat-knowledge"]);
  assert.ok(authorized.every((call) => call.principal === server.principal && call.run_id === result.result.run_id));
  const request = beforeRefusal.model_requests[baseline.model_requests.length];
  const schema = request.tools.find((tool) => tool.function.name === "query_events_kql").function.parameters;
  assert.equal(schema.properties.max_rows.type, "integer");
  assert.equal(schema.properties.max_rows.minimum, 1);
  assert.equal(schema.additionalProperties, false);
  check("chat-native-typed-tools-search-envelope-and-owner-readback", { result, authorized, schema });
  for (const [method, url, options, expected] of [
    ["GET", resultPath, { slug: "foreign" }, 404],
    ["POST", path, { slug: "foreign", body: JSON.stringify({ message: "refuse" }) }, 404],
    ["POST", path, { unsigned: true, body: JSON.stringify({ message: "refuse" }) }, 401],
    ["POST", path, { body: JSON.stringify({ message: "" }) }, 422],
  ]) assert.equal((await send(method, url, options)).status, expected);
  assert.equal((await server.command("snapshot")).attempts.length, beforeRefusal.attempts.length);
  assert.deepEqual(await (await send("GET", resultPath)).json(), result);
  const followup = await turn("Summarize only the SYNTHETIC evidence already retrieved.", 1);
  report.chat_followup_events = followup;
  const latest = await (await send("GET", resultPath)).json();
  assert.equal(latest.result.status, "completed");
  assert.notEqual(latest.result.run_id, result.result.run_id);
  assert.equal(latest.result.run_id, followup.at(-1).data.run_id);
  assert.match(latest.result.text, /^SYNTHETIC follow-up/);
  await page.locator("#chat-panel-defender .message.agent:not(.investigation-entry)").last()
    .locator(".message-body").getByText(/SYNTHETIC follow-up/).waitFor();
  const after = await server.command("snapshot");
  assert.deepEqual({ model: after.model_requests.length - baseline.model_requests.length,
    adx: after.adx_attempts - baseline.adx_attempts, search: after.search_attempts - baseline.search_attempts,
    graph: after.graph_scripts.length - baseline.graph_scripts.length },
  { model: 4, adx: 1, search: 1, graph: 0 });
  assert.ok(after.model_requests.at(-1).messages.some((message) => message.role === "assistant"
    && message.content === result.result.text));
  assert.ok(after.model_requests.at(-1).messages.some((message) => message.role === "tool"
    && message.tool_call_id === "chat-knowledge"));
  check("chat-refusals-and-explicit-followup-without-data-replay", latest);
  return { session_id: session.session_id, result: latest };
}

async function profileTurn(page, server, send, revision, existingSession) {
  let path = existingSession ? `/api/chat/${existingSession}` : "";
  const occurrence = path ? await page.evaluate((path) =>
    window.__nativeStreams.filter((stream) => stream.path === path).length, path) : 0;
  if (existingSession) await server.command("prepare-profile", { session_id: existingSession, revision });
  else await page.route("**/api/chat/*", async (route) => {
    path = new URL(route.request().url()).pathname;
    await server.command("prepare-profile", { session_id: path.split("/").at(-1), revision });
    await route.fallback();
  }, { times: 1 });
  const readbackPending = responseWait(page, (response) =>
    new URL(response.url()).pathname === "/api/cyber/suspect-profiles");
  const streamPending = responseWait(page, (response) => new URL(response.url()).pathname.startsWith("/api/chat/"));
  await page.getByRole("region", { name: "Suspect profiles", exact: true })
    .getByRole("button", { name: revision === 1 ? "Create profile" : "Update profile", exact: true }).click();
  assert.equal((await streamPending).status(), 200);
  const events = await observedStream(page, path, occurrence);
  assert.equal(events.at(-1).event, "done", JSON.stringify(events));
  assert.equal(events.at(-1).data.status, "completed", JSON.stringify(events));
  const result = events.find((frame) => frame.event === "tool_result"
    && frame.data.name === "update_suspect_profile").data.result;
  assert.equal(result.profile.revision, revision, JSON.stringify(events));
  const readback = await readbackPending;
  assert.equal(readback.status(), 200);
  assert.deepEqual((await readback.json())[0], result.profile);
  const profile = await (await send("GET", "/api/cyber/suspect-profiles/synthetic-analyst")).json();
  assert.deepEqual(profile, result.profile);
  await page.locator(".profile-status").getByText(`Revision ${revision}`, { exact: true }).waitFor();
  assert.equal(await page.locator(".profile-identity h3").innerText(), profile.identity.display_name);
  assert.ok((await page.locator(".profile-activity").innerText()).includes(profile.activity[0].summary));
  assert.equal(profile.citations[0].evidence_id, "synthetic-profile-event");
  assert.equal(profile.citations[0].record.target_user_name, profile.identity.account);
  const snapshot = await server.command("snapshot");
  const authorized = snapshot.authorized_tools.filter((call) => call.run_id === events.at(-1).data.run_id);
  assert.deepEqual(authorized.map((call) => call.name), ["get_suspect_profile", "query_events_kql", "update_suspect_profile"]);
  assert.ok(authorized.every((call) => call.principal === server.principal));
  report.profile_events ??= [];
  report.profile_events.push(events);
  check(`profile-native-control-update-${revision}-and-api-readback`, { profile, authorized });
  return { profile, run_id: events.at(-1).data.run_id };
}

async function profileWalk(page, server, send, session) {
  await page.getByRole("navigation", { name: "Tool board views" })
    .getByRole("button", { name: "profiles", exact: true }).click();
  await page.getByText("No saved suspect profiles.", { exact: true }).waitFor();
  check("profile-empty-state", "No saved suspect profiles.");
  await profileTurn(page, server, send, 1, session.session_id);
  const { profile, run_id } = await profileTurn(page, server, send, 2, session.session_id);
  const path = "/api/cyber/suspect-profiles/synthetic-analyst";
  const payload = { profile_id: profile.profile_id, expected_revision: 2, identity: profile.identity,
    activity: profile.activity, evidence_run_id: run_id };
  for (const [name, method, options, expected] of [
    ["anonymous-read", "GET", { unsigned: true }, 401],
    ["anonymous-write", "PUT", { unsigned: true, body: JSON.stringify(payload) }, 401],
    ["foreign-read", "GET", { slug: "foreign" }, 404],
    ["foreign-write", "PUT", { slug: "foreign", body: JSON.stringify(payload) }, 422],
    ["stale", "PUT", { body: JSON.stringify({ ...payload, expected_revision: 1 }) }, 409],
    ["invalid", "PUT", { body: JSON.stringify({ ...payload, activity: [] }) }, 422],
    ["unsupported", "PUT", { body: JSON.stringify({ ...payload,
      activity: [{ ...profile.activity[0], evidence_ids: ["invented-profile-evidence"] }] }) }, 422],
    ["forged-owner", "PUT", { body: JSON.stringify({ ...payload, owner_id: "foreign" }) }, 422],
  ]) {
    const response = await send(method, path, options);
    assert.equal(response.status, expected, name);
    assert.equal(response.headers.get("cache-control"), "no-store, private");
    assert.deepEqual(await (await send("GET", path)).json(), profile);
    check("profile-refusal-" + name, expected);
  }
  assert.deepEqual(await (await send("GET", "/api/cyber/suspect-profiles", { slug: "foreign" })).json(), []);
  report.persisted_profile = profile;
}

async function profileReloadWalk(page, server, send) {
  await server.command("prepare-profile-reload");
  await page.reload({ waitUntil: "networkidle" });
  await page.getByRole("navigation", { name: "Tool board views" })
    .getByRole("button", { name: "profiles", exact: true }).click();
  await page.locator(".profile-status").getByText("Revision 2", { exact: true }).waitFor();
  assert.deepEqual(await (await send("GET", "/api/cyber/suspect-profiles/synthetic-analyst")).json(), report.persisted_profile);
  check("profile-full-page-refresh-persistence", report.persisted_profile.revision);
  for (const [name, viewport] of [["desktop", { width: 1440, height: 900 }], ["mobile", { width: 390, height: 844 }]]) {
    await page.setViewportSize(viewport);
    if (name === "mobile") {
      const { profile } = await profileTurn(page, server, send, 3);
      report.persisted_profile = profile;
    }
    const evidence = page.getByLabel("Evidence synthetic-profile-event", { exact: true });
    await evidence.scrollIntoViewIfNeeded();
    if (!await evidence.evaluate((node) => node.parentElement.open)) await evidence.click();
    await page.locator(".profile-citations dd").getByText("synthetic-analyst", { exact: true }).waitFor();
    const refresh = page.getByRole("button", { name: "Refresh profiles", exact: true });
    await refresh.focus();
    const pending = responseWait(page, (response) => new URL(response.url()).pathname === "/api/cyber/suspect-profiles");
    await page.keyboard.press("Enter");
    assert.equal((await pending).status(), 200);
    await page.locator(".suspect-profiles[aria-busy=false]").waitFor();
    await evidence.scrollIntoViewIfNeeded();
    const geometry = await page.locator(".suspect-profiles").evaluate((panel) => ({
      width: innerWidth, document_width: document.documentElement.scrollWidth,
      controls: [...panel.querySelectorAll("button, summary")].map((node) => {
        const rect = node.getBoundingClientRect();
        return { label: node.getAttribute("aria-label") || node.textContent,
          x: rect.x, right: rect.right, width: rect.width, height: rect.height };
      }),
      citations_visible: panel.querySelector("details").open,
      focus_visible: getComputedStyle(document.activeElement).outlineStyle,
    }));
    assert.ok(geometry.document_width <= viewport.width, JSON.stringify(geometry));
    assert.ok(geometry.controls.every((control) => control.height >= 44 && control.width >= 44
      && control.x >= 0 && control.right <= viewport.width + 1), JSON.stringify(geometry));
    assert.equal(geometry.citations_visible, true);
    assert.notEqual(geometry.focus_visible, "none", "keyboard refresh must retain visible focus");
    const screenshot = join(output, `profile-${name}.png`);
    await page.screenshot({ path: screenshot, fullPage: true });
    report.screenshots.push({ view: "suspect-profile", viewport, path: screenshot, sha256: digest(readFileSync(screenshot)) });
    check(`profile-${name}-real-controls-citations-and-geometry`, geometry);
  }
}

async function knowledgeWalk(page, server, send) {
  const baseline = await server.command("snapshot");
  await server.command("prepare-knowledge");
  const path = "/api/cyber/knowledge/type/" + encodeURIComponent("attack:synthetic-analytic");
  assert.equal((await send("GET", path, { unsigned: true })).status, 401);
  assert.equal((await server.command("snapshot")).attempts.length, baseline.attempts.length);
  const missing = await send("GET", "/api/cyber/knowledge/type/unreturned-document");
  assert.equal(missing.status, 404);
  assert.match((await missing.json()).detail, /unknown situation type/);
  const board = page.getByRole("region", { name: "Central tool board", exact: true });
  await board.getByRole("navigation", { name: "Tool board views" })
    .getByRole("button", { name: "situation", exact: true }).click();
  await board.locator(".diagnosis-inset .classification-toggle").click();
  const citation = board.locator(".diagnosis-inset .citation-open").first();
  const pending = responseWait(page, (response) => new URL(response.url()).pathname === path);
  await citation.click();
  const response = await pending;
  assert.equal(response.status(), 200);
  const document = await response.json();
  assert.equal(document.type_id, "attack:synthetic-analytic");
  assert.equal(document.path, "synthetic/enterprise-attack.json");
  assert.equal(document.commit, "a".repeat(40));
  const rendered = board.locator(".diagnosis-inset .citation-doc:not(.loading)");
  await rendered.getByText("synthetic/enterprise-attack.json", { exact: true }).waitFor();
  assert.ok((await rendered.innerText()).includes(document.definition));
  assert.ok((await rendered.innerText()).includes(document.license));
  assert.equal(await board.locator(".citation-doc.error").count(), 0);
  check("citation-native-keyed-readback-and-unknown-refusal", document);
  await citation.click();
  await board.locator(".diagnosis-inset .citation-doc").waitFor({ state: "detached" });
  const step = board.locator(".sequence-step-toggle").first();
  await step.click();
  const evidence = board.getByTestId("sequence-evidence-0");
  await evidence.waitFor();
  assert.equal(await evidence.locator(".sequence-record").count(), 2);
  const provenance = await evidence.locator(".sequence-provenance").allTextContents();
  assert.ok(provenance.some((text) => text.includes("Azure Data Explorer table fixture.EventsUnified")));
  assert.ok(provenance.some((text) => text.includes("Azure AI Search index fixture")));
  assert.ok((await evidence.innerText()).includes("synthetic-event-1"));
  await step.focus();
  await page.keyboard.press("Enter");
  await evidence.waitFor({ state: "detached" });
  const after = await server.command("snapshot");
  assert.deepEqual({ model: after.model_requests.length - baseline.model_requests.length,
    adx: after.adx_attempts - baseline.adx_attempts, search: after.search_attempts - baseline.search_attempts,
    graph: after.graph_scripts.length - baseline.graph_scripts.length },
  { model: 0, adx: 0, search: 4, graph: 0 });
  assert.ok(after.attempts.slice(baseline.attempts.length).every((attempt) =>
    attempt.service === "search" && attempt.method === "GET"));
  check("sequence-record-provenance-and-keyboard-close", { provenance, keyed_reads: 4 });
}

async function graphWalk(page, server, send) {
  const baseline = await server.command("snapshot");
  await server.command("prepare-graph");
  const prefix = "/api/cyber/graph/";
  const nodeId = "host|SYNTHETIC_HOST";
  const pending = (route, predicate = () => true) => responseWait(page, (response) => {
    const url = new URL(response.url());
    return url.pathname === prefix + route && predicate(url);
  });
  const overviewPending = pending("overview");
  const corePending = pending("core");
  await page.getByRole("navigation", { name: "Tool board views" })
    .getByRole("button", { name: "graph", exact: true }).click();
  const overviewResponse = await overviewPending;
  const coreResponse = await corePending;
  assert.equal(overviewResponse.status(), 200);
  assert.equal(coreResponse.status(), 200);
  const overview = await overviewResponse.json();
  const core = await coreResponse.json();
  assert.deepEqual(overview.nodes_by_label, { Host: 1, Identity: 1 });
  assert.equal(core.nodes.length, 2);
  assert.equal(core.edges.length, 1);
  const graph = page.locator(".graph-panel");
  await graph.locator(".graph-node").first().waitFor({ state: "visible" });
  assert.equal(await graph.locator(".graph-node").count(), 2);
  check("graph-native-overview-core-and-visible-nodes", { overview, core });
  const search = graph.getByRole("textbox", { name: "Search the ontology graph" });
  const missingPending = pending("search", (url) => url.searchParams.get("q") === "SYNTHETIC_MISSING");
  await search.fill("SYNTHETIC_MISSING");
  const missing = await missingPending;
  assert.equal(missing.status(), 200);
  assert.deepEqual(await missing.json(), []);
  assert.equal(await graph.locator(".graph-matches button").count(), 0);
  const searchPending = pending("search", (url) => url.searchParams.get("q") === "SYNTHETIC_HOST");
  await search.fill("SYNTHETIC_HOST");
  const found = await searchPending;
  assert.equal(found.status(), 200);
  assert.equal((await found.json())[0].id, nodeId);
  const nodePending = pending("node", (url) => url.searchParams.get("id") === nodeId);
  await graph.locator(".graph-matches button").filter({ hasText: "SYNTHETIC_HOST" }).click();
  const focusedResponse = await nodePending;
  assert.equal(focusedResponse.status(), 200);
  const focused = await focusedResponse.json();
  assert.equal(focused.focus, nodeId);
  assert.equal(focused.depth, 1);
  assert.equal(focused.edges[0].window_scoped, true);
  await graph.getByRole("region", { name: "SYNTHETIC_HOST detail", exact: true }).waitFor();
  const depthPending = pending("node", (url) => url.searchParams.get("depth") === "2");
  await graph.getByRole("group", { name: "Relationship reach from the focused entity" })
    .getByRole("button", { name: "2", exact: true }).click();
  const depthResponse = await depthPending;
  assert.equal(depthResponse.status(), 200);
  assert.equal((await depthResponse.json()).depth, 2);
  check("graph-search-missing-recovery-focus-and-depth", { focus: nodeId, depth: 2 });
  const beforeWindow = await server.command("snapshot");
  const window = graph.getByRole("region", { name: "Graph time window", exact: true });
  const structuralPending = pending("node", (url) => !url.searchParams.get("start"));
  await window.getByRole("button", { name: "Structural", exact: true }).click();
  const structural = await structuralPending;
  assert.equal(structural.status(), 200);
  assert.deepEqual((await structural.json()).edges, []);
  assert.equal(await window.getByRole("slider", { name: "Window start" }).isDisabled(), true);
  const windowedPending = pending("node", (url) => Boolean(url.searchParams.get("start")));
  await window.getByRole("button", { name: "Windowed", exact: true }).click();
  const windowed = await windowedPending;
  assert.equal(windowed.status(), 200);
  assert.equal((await windowed.json()).edges.length, 1);
  const start = window.getByRole("slider", { name: "Window start" });
  const movedPending = pending("node", (url) => url.searchParams.get("start")?.startsWith("2026-08-13T02:45"));
  await start.focus();
  await page.keyboard.press("ArrowRight");
  const moved = await movedPending;
  assert.equal(moved.status(), 200);
  assert.deepEqual((await moved.json()).edges, []);
  const restoredPending = pending("node", (url) => url.searchParams.get("start")?.startsWith("2026-08-13T02:30"));
  await page.keyboard.press("Home");
  const restored = await restoredPending;
  assert.equal(restored.status(), 200);
  assert.equal((await restored.json()).edges.length, 1);
  const transform = () => graph.locator(".graph-stage > svg g[transform]").first().getAttribute("transform");
  const beforeZoom = await transform();
  await graph.getByRole("button", { name: "Zoom in", exact: true }).click();
  assert.notEqual(await transform(), beforeZoom);
  await graph.getByRole("button", { name: "Reset the view", exact: true }).click();
  assert.equal(await transform(), beforeZoom);
  assert.equal((await server.command("snapshot")).attempts.length, beforeWindow.attempts.length);
  check("graph-window-slider-and-viewport-without-gremlin-replay", { structural: 0, windowed: 1, moved: 0, restored: 1 });
  const beforeRefusal = await server.command("snapshot");
  assert.equal((await send("GET", prefix + "node?id=" + encodeURIComponent(nodeId), { unsigned: true })).status, 401);
  assert.equal((await send("GET", prefix + "node?id=")).status, 422);
  assert.equal((await server.command("snapshot")).attempts.length, beforeRefusal.attempts.length);
  const unknown = await send("GET", prefix + "node?id=" + encodeURIComponent("host|SYNTHETIC_MISSING"));
  assert.equal(unknown.status, 404);
  assert.equal((await unknown.json()).detail, "unknown graph node");
  const after = await server.command("snapshot");
  assert.deepEqual({ model: after.model_requests.length - baseline.model_requests.length,
    adx: after.adx_attempts - baseline.adx_attempts, search: after.search_attempts - baseline.search_attempts,
    graph: after.graph_scripts.length - baseline.graph_scripts.length },
  { model: 0, adx: 0, search: 0, graph: 18 });
  assert.ok(Object.values(after.graph_plans_remaining).every((count) => count === 0));
  assert.equal(await graph.locator(".error-box").count(), 0);
  check("graph-native-call-budget-and-node-refusals", { graph: 18, model: 0 });
}

async function editorWalk(page, server, send, initialSession) {
  const baseline = await server.command("snapshot");
  const prefix = "/api/cyber/agent-editor";
  const get = async (path) => {
    const response = await send("GET", path);
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("cache-control"), "no-store, private");
    return await response.json();
  };
  const initial = await get(prefix);
  const names = ["SYNTHETIC Investigator", "SYNTHETIC Investigator Revised"];
  const versionNames = ["SYNTHETIC Baseline", "SYNTHETIC Focused"];
  await page.getByRole("tab", { name: "Agent Editor", exact: true }).click();
  const editor = page.getByTestId("agent-editor");
  await editor.getByRole("button", { name: "Create agent", exact: true }).click();
  const form = editor.getByRole("form", { name: "Agent configuration" });
  await form.getByRole("textbox", { name: "Name", exact: true }).fill(names[0]);
  await form.getByRole("textbox", { name: "Version name", exact: true }).fill(versionNames[0]);
  await form.getByRole("combobox", { name: "LLM", exact: true }).selectOption(initial.models[0].id);
  await form.getByRole("textbox", { name: "Prompt / system instruction", exact: true }).fill("SYNTHETIC-EDITOR-PROMPT-V1");
  await form.getByLabel("Upload Markdown instructions").setInputFiles({
    name: "synthetic.md", mimeType: "text/markdown", buffer: Buffer.from("SYNTHETIC-EDITOR-CONTEXT-V1\n"),
  });
  await form.locator(".ae-file").waitFor();
  for (const [index, tool] of initial.tools.entries()) {
    await form.getByRole("button", { name: "Add tool", exact: true }).click();
    await form.getByRole("combobox", { name: `Tool ${index + 1}`, exact: true }).selectOption(tool.id);
  }
  const createPending = responseWait(page, (response) => new URL(response.url()).pathname === prefix + "/agents"
    && response.request().method() === "POST");
  await form.getByRole("button", { name: "Save Agent", exact: true }).click();
  const createdResponse = await createPending;
  assert.equal(createdResponse.status(), 201);
  const createPayload = createdResponse.request().postDataJSON();
  const created = await createdResponse.json();
  const agentId = created.agent_id;
  const definitionPath = `${prefix}/agents/${agentId}`;
  await form.getByRole("status").filter({ hasText: "Agent saved." }).waitFor();
  const first = await get(definitionPath + "?version=1");
  assert.equal(first.name, names[0]);
  assert.equal(first.system_prompt, "SYNTHETIC-EDITOR-PROMPT-V1");
  assert.deepEqual(first.instruction_files, [{ name: "synthetic.md", content: "SYNTHETIC-EDITOR-CONTEXT-V1\n" }]);
  assert.deepEqual(first.tool_ids, initial.tools.map((tool) => tool.id));
  assert.deepEqual((await get(prefix)).investigator, initial.investigator);
  assert.equal(await form.getByRole("textbox", { name: "Name", exact: true }).isEditable(), false);
  check("editor-ui-create-persisted-version-and-no-implicit-assignment", first);
  let oldSession = initialSession.session_id;
  let second;
  const sessions = [];
  for (const version of [1, 2]) {
    if (version === 2) {
      await page.getByRole("tab", { name: "Agent Editor", exact: true }).click();
      await form.getByRole("button", { name: "Create New Version", exact: true }).click();
      assert.equal(await form.getByRole("button", { name: "Save New Version", exact: true }).isDisabled(), true);
      await form.getByRole("textbox", { name: "Version name", exact: true }).fill(versionNames[1]);
      await form.getByRole("textbox", { name: "Name", exact: true }).fill(names[1]);
      await form.getByRole("textbox", { name: "Prompt / system instruction", exact: true }).fill("SYNTHETIC-EDITOR-PROMPT-V2");
      await form.getByRole("textbox", { name: "synthetic.md instructions", exact: true }).fill("SYNTHETIC-EDITOR-CONTEXT-V2\n");
      const savedPending = responseWait(page, (response) => new URL(response.url()).pathname === definitionPath + "/versions"
        && response.request().method() === "POST");
      await form.getByRole("button", { name: "Save New Version", exact: true }).click();
      assert.equal((await savedPending).status(), 201);
      await form.getByRole("status").filter({ hasText: "New version saved." }).waitFor();
      second = await get(definitionPath + "?version=2");
      assert.equal(second.system_prompt, "SYNTHETIC-EDITOR-PROMPT-V2");
      const original = await get(definitionPath + "?version=1");
      for (const key of ["name", "version_name", "system_prompt", "instruction_files", "tool_ids"]) {
        assert.deepEqual(original[key], first[key], `immutable version field changed: ${key}`);
      }
      assert.deepEqual(second.versions, [1, 2]);
      check("editor-ui-new-version-preserves-original", second);
    }
    const previousResult = await get(`/api/sessions/${oldSession}/result`);
    await editor.getByRole("combobox", { name: "Investigator agent", exact: true }).selectOption(agentId);
    await editor.getByRole("combobox", { name: "Investigator version", exact: true }).selectOption(String(version));
    const assignmentPending = responseWait(page, (response) => new URL(response.url()).pathname === prefix + "/roles/investigator"
      && response.request().method() === "PUT");
    await editor.getByRole("button", { name: "Assign Investigator", exact: true }).click();
    const assignedResponse = await assignmentPending;
    const assigned = await assignedResponse.json();
    assert.equal(assignedResponse.status(), 200, JSON.stringify(assigned));
    assert.equal(assigned.agent_id, agentId);
    assert.equal(assigned.version, version);
    assert.deepEqual((await get(prefix)).investigator, assigned);
    await page.getByRole("tab", { name: "Investigation", exact: true }).click();
    await page.getByTestId("active-investigator").getByText(names[version - 1], { exact: true }).waitFor();
    await page.getByTestId("chat-tab-defender").click();
    const beforeRefusal = await server.command("snapshot");
    const oldPath = `/api/chat/${oldSession}`;
    const refusalReadback = await send("POST", oldPath, { body: JSON.stringify({ message: "SYNTHETIC verify old-session refusal" }) });
    assert.equal(refusalReadback.status, 409);
    assert.equal((await refusalReadback.json()).detail, "agent definition changed; create a new session");
    assert.deepEqual(await get(`/api/sessions/${oldSession}/result`), previousResult);
    assert.equal((await server.command("snapshot")).attempts.length, beforeRefusal.attempts.length);
    await server.command("prepare-editor-turn", { version });
    const freshPending = responseWait(page, (response) => new URL(response.url()).pathname === "/api/sessions"
      && response.request().method() === "POST");
    const chatPending = responseWait(page, (response) => new URL(response.url()).pathname.startsWith("/api/chat/")
      && response.status() === 200);
    await page.locator(".chat-input textarea").fill(`SYNTHETIC explicit fresh conversation for editor version ${version}.`);
    await page.locator('.chat-input button[title="Send"]').click();
    const freshResponse = await freshPending;
    assert.equal(freshResponse.status(), 200);
    const fresh = await freshResponse.json();
    assert.notEqual(fresh.session_id, oldSession);
    await chatPending;
    const events = await observedStream(page, `/api/chat/${fresh.session_id}`);
    assert.equal(events.at(-1).event, "done", JSON.stringify(events));
    assert.equal(events.at(-1).data.status, "completed");
    const metadata = events.find((frame) => frame.event === "metadata").data;
    assert.equal(metadata.agent_id, agentId);
    assert.equal(metadata.config_version, version);
    const result = await get(`/api/sessions/${fresh.session_id}/result`);
    assert.equal(result.result.text, `SYNTHETIC editor version ${version} used its saved instructions.`);
    assert.equal(result.result.run_id, metadata.run_id);
    const message = page.locator("#chat-panel-defender .message.agent:not(.investigation-entry)").last();
    await message.locator(".message-body").getByText(result.result.text, { exact: true }).waitFor();
    assert.equal(await message.locator(".message-role").getAttribute("data-agent-version"), String(version));
    assert.equal(await page.locator("#chat-panel-defender .error-box").filter({ hasText: "This turn was not replayed." }).count(), 0);
    const after = await server.command("snapshot");
    const modelRequest = after.model_requests.at(-1);
    assert.ok(JSON.stringify(modelRequest.messages).includes(`SYNTHETIC-EDITOR-PROMPT-V${version}`));
    assert.ok(JSON.stringify(modelRequest.messages).includes(`SYNTHETIC-EDITOR-CONTEXT-V${version}`));
    assert.ok(!JSON.stringify(modelRequest.messages).includes(previousResult.result?.text || "SYNTHETIC unused prior result"));
    assert.equal(after.model_requests.length, beforeRefusal.model_requests.length + 1);
    sessions.push({ version, old_session: oldSession, session_id: fresh.session_id, result, events });
    oldSession = fresh.session_id;
    check(`editor-v${version}-assignment-409-and-explicit-session-recovery`, sessions.at(-1));
  }
  const beforeRefusals = await server.command("snapshot");
  for (const [method, path, options, expected] of [
    ["GET", definitionPath, { slug: "foreign" }, 404],
    ["POST", definitionPath + "/versions", { slug: "foreign", body: JSON.stringify(createPayload) }, 404],
    ["POST", prefix + "/agents", { unsigned: true, body: JSON.stringify(createPayload) }, 401],
    ["POST", definitionPath + "/versions", { body: JSON.stringify({ ...createPayload, base_version: 1, expected_latest_version: 1 }) }, 409],
    ["PUT", prefix + "/roles/investigator", { body: JSON.stringify({ agent_id: agentId, version: 1, expected_revision: 0 }) }, 409],
  ]) assert.equal((await send(method, path, options)).status, expected);
  assert.deepEqual((await get(definitionPath)).versions, [1, 2]);
  assert.equal((await get(prefix)).investigator.version, 2);
  assert.equal((await server.command("snapshot")).attempts.length, beforeRefusals.attempts.length);
  await page.getByRole("tab", { name: "Agent Editor", exact: true }).click();
  await form.getByRole("button", { name: "Create New Version", exact: true }).click();
  await form.getByRole("textbox", { name: "Version name", exact: true }).fill("SYNTHETIC discarded draft");
  await form.getByRole("button", { name: "Reset", exact: true }).click();
  assert.equal(await form.getByRole("textbox", { name: "Version name", exact: true }).inputValue(), versionNames[1]);
  assert.equal(await form.getByRole("textbox", { name: "Name", exact: true }).isEditable(), false);
  assert.deepEqual(await form.locator(".ae-toolbar > button").allTextContents(), ["Create New Version", "Save New Version", "Reset"]);
  const after = await server.command("snapshot");
  assert.deepEqual({ model: after.model_requests.length - baseline.model_requests.length,
    adx: after.adx_attempts - baseline.adx_attempts, search: after.search_attempts - baseline.search_attempts,
    graph: after.graph_scripts.length - baseline.graph_scripts.length },
  { model: 2, adx: 0, search: 0, graph: 0 });
  check("editor-ownership-stale-write-refusal-and-toolbar-reset", { versions: [1, 2], model: 2 });
  report.editor = { agent_id: agentId, versions: [first, second], sessions };
}

async function viewportWalk(page, server) {
  const baseline = await server.command("snapshot");
  report.geometry = [];
  for (const [view, tab, groups] of [
    ["editor", "Agent Editor", [".header-tabs > button", "#workspace-agent-editor .ae-toolbar > *"]],
    ["investigation", "Investigation", [".header-tabs > button", ".chat-tabs > button", ".graph-nav > button"]],
  ]) {
    await page.getByRole("tab", { name: tab, exact: true }).click();
    for (const [name, viewport] of [["desktop", { width: 1440, height: 900 }], ["mobile", { width: 390, height: 844 }]]) {
      await page.setViewportSize(viewport);
      await page.waitForFunction((width) => document.documentElement.clientWidth === width, viewport.width);
      const geometry = await page.evaluate(({ view, name, groups }) => {
        const box = (node) => {
          const rect = node.getBoundingClientRect();
          return { label: node.getAttribute("aria-label") || node.textContent.trim(),
            x: rect.x, y: rect.y, width: rect.width, height: rect.height,
            right: rect.right, bottom: rect.bottom };
        };
        return { view, name, width: innerWidth, height: innerHeight,
          document_width: document.documentElement.scrollWidth,
          groups: groups.map((selector) => ({ selector,
            controls: [...document.querySelectorAll(selector)].map(box).filter((rect) => rect.width && rect.height) })),
          graph: view === "investigation" ? box(document.querySelector(".graph-stage > svg")) : null,
          nodes: view === "investigation" ? [...document.querySelectorAll(".graph-node")].map(box) : [],
        };
      }, { view, name, groups });
      report.geometry.push(geometry);
      assert.ok(geometry.document_width <= viewport.width, JSON.stringify(geometry));
      for (const group of geometry.groups) {
        assert.ok(group.controls.length > 0, group.selector);
        for (const [index, control] of group.controls.entries()) {
          assert.ok(control.x >= -1 && control.right <= viewport.width + 1, JSON.stringify(control));
          assert.ok(group.controls.slice(index + 1).every((next) => control.right <= next.x + 1
            || next.right <= control.x + 1 || control.bottom <= next.y + 1 || next.bottom <= control.y + 1),
          JSON.stringify(group));
        }
      }
      if (view === "investigation") {
        assert.ok(geometry.graph.width > 200 && geometry.graph.height > 200, JSON.stringify(geometry.graph));
        assert.equal(geometry.nodes.length, 2);
        assert.ok(geometry.nodes.every((node) => node.width > 0 && node.height > 0));
        await page.locator(".graph-stage").scrollIntoViewIfNeeded();
      } else {
        await page.locator("#workspace-agent-editor .ae-toolbar").scrollIntoViewIfNeeded();
      }
      const screenshot = join(output, `${view}-${name}.png`);
      await page.screenshot({ path: screenshot, fullPage: false });
      report.screenshots.push({ view, viewport, path: screenshot, sha256: digest(readFileSync(screenshot)) });
      check(`${view}-${name}-geometry-and-screenshot`, geometry);
    }
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  const after = await server.command("snapshot");
  assert.equal(after.attempts.length, baseline.attempts.length, "view changes must not invoke external services");
}

async function buildFrontend() {
  const child = spawn(process.execPath, [join(frontend, "node_modules/vite/bin/vite.js"),
    "build", "--configLoader", "runner", "--outDir", dist],
    { cwd: frontend, env: environment, stdio: ["ignore", "pipe", "pipe"] });
  let text = "";
  child.stdout.on("data", (chunk) => { text += chunk; });
  child.stderr.on("data", (chunk) => { text += chunk; });
  const code = await new Promise((resolve, reject) => {
    child.once("error", reject); child.once("exit", resolve);
  });
  writeFileSync(join(output, "build.log"), text);
  assert.equal(code, 0, text);
  report.frontend = { index_sha256: digest(readFileSync(join(dist, "index.html"))), source: frontend };
  check("production-frontend-build", report.frontend);
}

function requestSigner(privateKey) {
  let previous = 0n;
  return (method, path, body = Buffer.alloc(0), slug = "browser") => {
    const now = BigInt(Date.now()) * 1000n;
    previous = now > previous ? now : previous + 1n;
    const timestamp = new Date(Number(previous / 1000n)).toISOString().replace(/\.\d{3}Z$/,
      `.${String(previous % 1000000n).padStart(6, "0")}Z`);
    const canonical = [method.toUpperCase(), path, timestamp, slug, digest(body)].join("\n");
    return { "X-Request-Timestamp": timestamp, "X-Request-Context": slug,
      "X-Request-Signature": sign(null, Buffer.from(canonical, "ascii"), privateKey).toString("base64") };
  };
}

async function launchServer(publicKey) {
  const child = spawn(python, ["-B", "-m", "app.cybereye.tests.native_browser",
    "--state-dir", state, "--frontend-dist", dist],
    { cwd: project, env: environment, stdio: ["pipe", "pipe", "pipe"] });
  let stderr = "";
  child.stderr.on("data", (chunk) => { stderr += chunk; });
  const exited = new Promise((resolve) => child.once("exit", (code, signal) => resolve({ code, signal })));
  const pending = new Map();
  let readyResolve;
  let readyReject;
  const ready = new Promise((resolve, reject) => { readyResolve = resolve; readyReject = reject; });
  const lines = createInterface({ input: child.stdout });
  lines.on("line", (line) => {
    try {
      const message = JSON.parse(line);
      if (message.kind === "ready") readyResolve(message);
      else if (message.kind === "response") {
        pending.get(message.id)?.(message.value); pending.delete(message.id);
      } else if (message.kind === "closed") report.server_cleanup = message;
    } catch { stderr += line + "\n"; }
  });
  child.once("error", readyReject);
  child.once("exit", () => readyReject(new Error(stderr || "fixture exited before readiness")));
  child.stdin.write(JSON.stringify({ public_key: publicKey }) + "\n");
  let counter = 0;
  const control = {
    child,
    async command(command, payload = {}) {
      const id = ++counter;
      const response = new Promise((resolve) => pending.set(id, resolve));
      child.stdin.write(JSON.stringify({ ...payload, command, id }) + "\n");
      return await Promise.race([response, exited.then(() => { throw new Error(stderr || "fixture exited"); })]);
    },
    async close() {
      if (child.exitCode === null && child.signalCode === null) child.stdin.end('{"command":"stop"}\n');
      const deadline = setTimeout(() => child.kill("SIGKILL"), 10000);
      const result = await exited;
      clearTimeout(deadline);
      lines.close();
      writeFileSync(join(output, "server.log"), stderr);
      report.server_exit = result;
      assert.equal(result.code, 0, stderr);
      assert.equal(report.server_cleanup?.fixture_cleanup, true);
    },
  };
  try { return { ...control, ...await ready }; }
  catch (error) { await control.close().catch(() => {}); throw error; }
}

async function signedPage(context, base, headers) {
  const page = await context.newPage();
  page.on("pageerror", (error) => report.browser_errors.push(String(error)));
  await page.addInitScript(() => {
    window.__nativeStreams = [];
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await originalFetch(...args);
      const path = new URL(response.url).pathname;
      if (!response.body || !response.headers.get("content-type")?.includes("text/event-stream")) return response;
      const trace = { path, status: response.status, text: "", closed: false, truncated: false, error: "" };
      window.__nativeStreams.push(trace);
      const originalReader = response.body.getReader.bind(response.body);
      response.body.getReader = (...readerArgs) => {
        const reader = originalReader(...readerArgs);
        const originalRead = reader.read.bind(reader);
        const decoder = new TextDecoder();
        reader.read = async (...readArgs) => {
          try {
            const chunk = await originalRead(...readArgs);
            const text = decoder.decode(chunk.value, { stream: !chunk.done });
            if (trace.text.length + text.length <= 1048576) trace.text += text;
            else trace.truncated = true;
            trace.closed = chunk.done;
            return chunk;
          } catch (error) { trace.error = String(error); throw error; }
        };
        return reader;
      };
      return response;
    };
  });
  const session = await context.newCDPSession(page);
  session.on("Fetch.requestPaused", async ({ requestId, request }) => {
    try {
      const url = new URL(request.url);
      if (url.origin !== base) {
        report.blocked_browser_requests.push({ origin: url.origin, path: url.pathname });
        await session.send("Fetch.failRequest", { requestId, errorReason: "BlockedByClient" });
        return;
      }
      let body = Buffer.alloc(0);
      if (request.hasPostData) {
        assert.ok(request.postDataEntries?.every((entry) => typeof entry.bytes === "string"),
          "exact CDP body bytes required");
        body = Buffer.concat(request.postDataEntries.map((entry) => Buffer.from(entry.bytes, "base64")));
      }
      assert.ok(body.length <= 1048576);
      const fresh = headers(request.method, url.pathname + url.search, body);
      const retained = Object.entries(request.headers).filter(([name]) => !/^x-request-(timestamp|context|signature)$/i.test(name));
      await session.send("Fetch.continueRequest", { requestId,
        headers: [...retained, ...Object.entries(fresh)].map(([name, value]) => ({ name, value })) });
    } catch (error) {
      report.browser_errors.push(String(error));
      await session.send("Fetch.failRequest", { requestId, errorReason: "BlockedByClient" }).catch(() => {});
    }
  });
  await session.send("Fetch.enable", { patterns: [{ urlPattern: "*", requestStage: "Request" }] });
  return page;
}

async function main() {
  let server;
  let browser;
  try {
    await buildFrontend();
    const { privateKey, publicKey } = generateKeyPairSync("ed25519");
    const publicBytes = publicKey.export({ type: "spki", format: "der" }).subarray(-32);
    const headers = requestSigner(privateKey);
    server = await launchServer(publicBytes.toString("base64"));
    report.server = { pid: server.pid, origin: server.origin, principal: server.principal, lifecycle: server.lifecycle,
      interpreter: server.interpreter };
    const send = async (method, path, { body = "", slug = "browser", unsigned = false, signedHeaders } = {}) => {
      const bytes = Buffer.from(body);
      return await fetch(server.origin + path, { method,
        headers: { ...(unsigned ? {} : signedHeaders || headers(method, path, bytes, slug)),
          ...(body ? { "Content-Type": "application/json" } : {}) },
        ...(body ? { body: bytes } : {}), redirect: "error", signal: AbortSignal.timeout(30000) });
    };
    const created = await send("POST", "/api/sessions");
    assert.equal(created.status, 200);
    assert.equal(created.headers.get("cache-control"), "no-store, private");
    const session = await created.json();
    check("signed-session-create", session);
    for (const [method, path] of [["GET", "/"], ["POST", "/api/sessions"],
      ["GET", `/api/sessions/${session.session_id}/result`]]) {
      const response = await send(method, path, { unsigned: true });
      assert.equal(response.status, 401);
      assert.equal(await response.text(), "");
      assert.equal(response.headers.get("cache-control"), "no-store, private");
      check("anonymous-refused-" + method + "-" + path, 401);
    }
    const foreign = await send("GET", `/api/sessions/${session.session_id}/result`, { slug: "foreign" });
    assert.equal(foreign.status, 404);
    check("foreign-signed-owner-refused", 404);
    const replayHeaders = headers("GET", `/api/sessions/${session.session_id}/result`);
    assert.equal((await send("GET", `/api/sessions/${session.session_id}/result`, { signedHeaders: replayHeaders })).status, 200);
    assert.equal((await send("GET", `/api/sessions/${session.session_id}/result`, { signedHeaders: replayHeaders })).status, 401);
    check("signed-replay-refused", 401);
    const beforeTampering = await server.command("snapshot");
    const boundPath = `/api/sessions/${session.session_id}/result?probe=original`;
    assert.equal((await send("GET", boundPath)).status, 200);
    assert.equal((await send("GET", boundPath.replace("original", "tampered"), {
      signedHeaders: headers("GET", boundPath) })).status, 401);
    assert.equal((await send("POST", boundPath, { signedHeaders: headers("GET", boundPath) })).status, 401);
    const queryBody = JSON.stringify({ query: "EventsUnified | take 1", max_rows: 1 });
    assert.equal((await send("POST", "/api/cyber/query", { body: queryBody.replace("take 1", "take 2"),
      signedHeaders: headers("POST", "/api/cyber/query", Buffer.from(queryBody)) })).status, 401);
    assert.equal((await server.command("snapshot")).attempts.length, beforeTampering.attempts.length);
    check("signed-canonical-method-query-and-body-tampering-refused", { positive: 200, tampered: [401, 401, 401] });
    browser = await chromium.launch({ headless: true });
    report.chromium = browser.version();
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: "block" });
    context.setDefaultTimeout(15000);
    context.setDefaultNavigationTimeout(30000);
    await context.routeWebSocket("**/*", (websocket) => {
      report.blocked_browser_requests.push({ kind: "websocket", url: websocket.url() });
      websocket.close();
    });
    const page = await signedPage(context, server.origin, headers);
    const healthPending = responseWait(page, (response) => new URL(response.url()).pathname === "/api/health");
    const sessionRequests = [];
    page.on("request", (request) => {
      if (new URL(request.url()).pathname === "/api/sessions" && request.method() === "POST") sessionRequests.push(request);
    });
    await page.goto(server.origin, { waitUntil: "networkidle" });
    assert.equal(sessionRequests.length, 0);
    const uiSession = {};
    report.ui_session = uiSession;
    const healthResponse = await healthPending;
    assert.equal(healthResponse.status(), 200);
    report.health = await healthResponse.json();
    assert.equal(report.health.status, "ok");
    assert.equal(report.health.agent.knowledge_base.available, true);
    assert.equal(report.health.agent.classification_kb.available, true);
    assert.equal(report.health.graph.available, true);
    const startup = await server.command("snapshot");
    assert.deepEqual({ model: startup.model_requests.length, adx: startup.adx_attempts,
      search: startup.search_attempts, graph: startup.graph_scripts.length },
    { model: 0, adx: 1, search: 3, graph: 3 });
    assert.equal(startup.attempts.filter((attempt) => attempt.service === "graph"
      && attempt.path === "/api/health").length, 2);
    assert.equal(startup.attempts.filter((attempt) => attempt.service === "graph"
      && attempt.path === "/api/cyber/graph/entities").length, 1);
    assert.deepEqual(startup.external_attempts, []);
    check("native-startup-health", report.health);
    await page.locator(".scanner-scan-button").waitFor({ state: "visible" });
    const scenarios = await page.getByLabel("Test Scenarios").locator("option").allTextContents();
    assert.ok(scenarios.length > 1, JSON.stringify(scenarios));
    for (const selector of ["script[src]", 'link[rel="stylesheet"]']) {
      const asset = await page.locator(selector).first().getAttribute(selector.startsWith("script") ? "src" : "href");
      assert.equal((await send("GET", asset, { unsigned: true })).status, 401);
    }
    check("anonymous-script-and-stylesheet-refused", 401);
    check("real-production-frontend-startup", scenarios);
    await phase("scan", server, () => scanWalk(page, server, send));
    await phase("query", server, () => queryWalk(page, server, send));
    await phase("chat", server, () => chatWalk(page, server, send, uiSession));
    assert.equal(sessionRequests.length, 1);
    check("chat-session-created-on-first-send-and-reused", uiSession);
    await phase("profile", server, () => profileWalk(page, server, send, uiSession));
    await phase("knowledge", server, () => knowledgeWalk(page, server, send));
    await phase("graph", server, () => graphWalk(page, server, send));
    await phase("editor", server, () => editorWalk(page, server, send, uiSession));
    await phase("viewports", server, () => viewportWalk(page, server));
    await phase("profile-reload", server, () => profileReloadWalk(page, server, send));
    report.native = await server.command("snapshot");
    assert.equal(report.native.test_resolver_principal, null);
    assert.deepEqual(report.native.external_attempts, []);
    assert.deepEqual(report.native.native_rejections, []);
    assert.deepEqual(report.native.http.filter((request) => request.status === null || request.status >= 500), []);
    assert.deepEqual(report.browser_errors, []);
    assert.deepEqual(report.blocked_browser_requests, []);
    assert.ok(report.native.state_files.some((file) => file.path.startsWith("agents/")));
    for (const plans of ["model_plans_remaining", "data_plans_remaining", "search_plans_remaining", "graph_plans_remaining"]) {
      assert.ok(Object.values(report.native[plans]).every((count) => count === 0), plans);
    }
    assert.deepEqual(report.phases.filter((phase) => phase.status !== "PASS"), []);
    report.status = "PASS";
  } catch (error) {
    report.status = "FAIL";
    report.failure = String(error.stack || error);
    if (server) report.native = await server.command("snapshot").catch(() => null);
    const failedPage = browser?.contexts()[0]?.pages()[0];
    if (failedPage) {
      report.failed_ui = await failedPage.locator(".scanner .error-box").allTextContents();
      report.failure_geometry = [];
      for (const [name, viewport] of [["desktop", { width: 1440, height: 900 }], ["mobile", { width: 390, height: 844 }]]) {
        await failedPage.setViewportSize(viewport);
        report.failure_geometry.push(await failedPage.evaluate((name) => ({ name,
          width: innerWidth, height: innerHeight, document_width: document.documentElement.scrollWidth,
          tabs: [...document.querySelectorAll(".chat-tabs button")].map((node) => {
            const rect = node.getBoundingClientRect();
            return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
          }) }), name));
        const screenshot = join(output, `failure-${name}.png`);
        await failedPage.screenshot({ path: screenshot }).then(() => {
          report.screenshots.push({ path: screenshot, sha256: digest(readFileSync(screenshot)) });
        }).catch(() => {});
      }
    }
    writeFileSync(join(output, "report.json"), JSON.stringify(report, null, 2) + "\n");
    console.error(report.failure);
    throw error;
  } finally {
    if (browser) { await browser.close(); report.browser_closed = !browser.isConnected(); }
    if (server) await server.close().catch((error) => { report.status = "FAIL"; report.cleanup_error = String(error); });
    writeFileSync(join(output, "report.json"), JSON.stringify(report, null, 2) + "\n");
    console.log(JSON.stringify({ status: report.status, checks: report.checks.length, output }));
  }
  assert.equal(report.status, "PASS");
}

await main();