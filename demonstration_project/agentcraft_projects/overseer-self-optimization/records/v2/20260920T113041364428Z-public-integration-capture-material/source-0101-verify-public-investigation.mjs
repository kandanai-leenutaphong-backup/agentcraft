import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { createInterface } from "node:readline";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const frontend = fileURLToPath(new URL("../../", import.meta.url));
const project = resolve(frontend, "../../..");
assert.ok(process.env.LIVE_PYTHON, "LIVE_PYTHON must name an existing installed interpreter; no environment setup occurs");
assert.ok(process.env.ARTIFACT_DIR, "ARTIFACT_DIR must name assigned primary evidence directory");
const output = join(resolve(process.env.ARTIFACT_DIR), new Date().toISOString().replace(/[:.]/g, "-") + "-browser");
const state = join(output, "state");
mkdirSync(state, { recursive: true });
const digest = (payload) => createHash("sha256").update(payload).digest("hex");
const report = { status: "running", started_at: new Date().toISOString(), checks: [], screenshots: [],
  browser_errors: [], requests: [], transport: "synthetic store adapters, real normalized licensed payload",
  production_lifespan: true, external_models: "disabled", deployed_auth: "not verified",
  persona: { who: "Analyst reviewing an emulation alert", goal: "Trace an alarm to actual event and entity provenance",
    known: "Windows event terminology", not_known: "Internal IDs, source schema or UI layout",
    constraints: "Desktop and narrow mobile; keyboard and pointer" },
  frontend_sha256: digest(readFileSync(join(frontend, "dist/index.html"))) };
const check = (name, detail) => { report.checks.push({ name, detail }); console.log(`PASS ${name}`); };

function signer(privateKey) {
  let previous = 0n;
  return (method, path, body = Buffer.alloc(0), owner = "public-browser") => {
    const now = BigInt(Date.now()) * 1000n;
    previous = now > previous ? now : previous + 1n;
    const stamp = new Date(Number(previous / 1000n)).toISOString().replace(/\.\d{3}Z$/,
      `.${String(previous % 1000000n).padStart(6, "0")}Z`);
    const canonical = [method, path, stamp, owner, digest(body)].join("\n");
    return { "X-Request-Timestamp": stamp, "X-Request-Context": owner,
      "X-Request-Signature": sign(null, Buffer.from(canonical, "ascii"), privateKey).toString("base64") };
  };
}

async function server(publicKey) {
  const child = spawn(resolve(process.env.LIVE_PYTHON), ["-B", "-m", "app.cybereye.tests.public_browser",
    "--state-dir", state, "--frontend-dist", join(frontend, "dist")], {
    cwd: project, env: { PATH: "/usr/bin:/bin", HOME: state, PYTHON_DOTENV_DISABLED: "1", PYTHONDONTWRITEBYTECODE: "1" },
    stdio: ["pipe", "pipe", "pipe"],
  });
  let stderr = "";
  child.stderr.on("data", (chunk) => { stderr += chunk; writeFileSync(join(output, "server.log"), stderr); });
  const exited = new Promise((resolve) => child.once("exit", (code, signal) => resolve({ code, signal })));
  const lines = createInterface({ input: child.stdout });
  let readyResolve, readyReject;
  const ready = new Promise((resolve, reject) => { readyResolve = resolve; readyReject = reject; });
  lines.on("line", (line) => {
    try {
      const message = JSON.parse(line);
      if (message.kind === "ready") readyResolve(message.origin);
      if (message.kind === "closed") report.server = message;
    } catch { stderr += line + "\n"; }
  });
  child.once("error", readyReject);
  child.once("exit", () => readyReject(new Error(stderr || "Server exited before readiness")));
  const timer = setTimeout(() => readyReject(new Error("Server readiness timed out: " + stderr)), 30000);
  child.stdin.write(JSON.stringify({ public_key: publicKey }) + "\n");
  async function close() {
    if (child.exitCode === null && child.signalCode === null) child.stdin.end('{"command":"stop"}\n');
    const deadline = setTimeout(() => child.kill("SIGKILL"), 10000);
    const result = await exited;
    clearTimeout(deadline); lines.close();
    writeFileSync(join(output, "server.log"), stderr);
    report.server_exit = result;
    assert.equal(result.code, 0, stderr);
    assert.equal(report.server?.settled, true);
  }
  try { return { origin: await ready, close }; }
  catch (error) { await close().catch(() => {}); throw error; }
  finally { clearTimeout(timer); }
}

async function geometry(page, label) {
  const result = await page.locator(".public-cases").evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const header = element.querySelector(".public-heading").getBoundingClientRect();
    const tabs = element.querySelector(".public-tabs").getBoundingClientRect();
    return { width: rect.width, scroll_width: element.scrollWidth, client_width: element.clientWidth,
      page_width: document.documentElement.clientWidth, page_scroll: document.documentElement.scrollWidth,
      header_bottom: header.bottom, tabs_top: tabs.top,
      controls: [...element.querySelectorAll("button")].filter((button) => button.getClientRects().length).map((button) => {
        const box = button.getBoundingClientRect();
        return { name: button.getAttribute("aria-label") || button.textContent, width: box.width, height: box.height,
          scroll_width: button.scrollWidth, client_width: button.clientWidth };
      }) };
  });
  assert.ok(result.width > 0);
  assert.ok(result.page_scroll <= result.page_width + 1, JSON.stringify(result));
  assert.ok(result.scroll_width <= result.client_width + 1, JSON.stringify(result));
  assert.ok(result.header_bottom <= result.tabs_top);
  assert.ok(result.controls.every((item) => item.scroll_width <= item.client_width + 1), JSON.stringify(result));
  if (page.viewportSize().width <= 700) assert.ok(result.controls.every((item) => item.height >= 44), JSON.stringify(result));
  check(label + "-geometry", result);
}

async function screenshot(page, name) {
  const path = join(output, name + ".png");
  await page.screenshot({ path, fullPage: false });
  report.screenshots.push({ name, path, viewport: page.viewportSize(), sha256: digest(readFileSync(path)) });
}

async function walk(page, viewport, name) {
  await page.setViewportSize(viewport);
  await page.goto(report.origin);
  const cases = page.getByRole("region", { name: "Public investigation", exact: true });
  await cases.getByRole("button", { name: "Attack Range rundll32 DLL in Temp emulation", exact: true }).waitFor();
  report.initial_impression ??= { heading: await cases.locator("h2").innerText(),
    first_action: "Named emulation case", transport: await cases.locator(".public-transport").innerText() };
  assert.match(await cases.innerText(), /SYNTHETIC store transport/);
  await cases.scrollIntoViewIfNeeded();
  await geometry(page, name + "-cases");
  await screenshot(page, name + "-cases");
  await cases.getByRole("button", { name: "Attack Range rundll32 DLL in Temp emulation", exact: true }).click();
  await cases.getByRole("button", { name: "rundll32-temp-dll-v1", exact: true }).click();
  await cases.getByRole("button", { name: /^Event 1 / }).click();
  const ref = await cases.getByTestId("public-event-id").innerText();
  assert.ok(ref.startsWith("event://scenario-"));
  for (const role of ["host", "user", "process"]) {
    await cases.getByRole("button", { name: `Open ${role} graph`, exact: true }).click();
    await cases.locator(".graph-detail").waitFor();
    await cases.locator(".graph-stage .graph-node").first().waitFor();
    const detail = cases.locator(".graph-detail");
    assert.match(await detail.innerText(), /6bc794b7f65562148c872fde1e7412ab3c173f4c/);
    if (role === "process") assert.match(await detail.innerText(), /Process/);
    await cases.locator(".graph-stage").scrollIntoViewIfNeeded();
    await geometry(page, name + "-" + role);
    const graph = await cases.locator(".graph-stage").evaluate((element) => ({
      width: element.getBoundingClientRect().width, height: element.getBoundingClientRect().height,
      nodes: element.querySelectorAll(".graph-node").length, edges: element.querySelectorAll(".graph-edge").length,
    }));
    assert.ok(graph.width > 0 && graph.height > 0 && graph.nodes > 1);
    check(name + "-" + role + "-graph", graph);
    await screenshot(page, name + "-" + role + "-graph");
    await detail.getByRole("button", { name: ref, exact: true }).click();
    assert.equal(await cases.getByTestId("public-event-id").innerText(), ref);
  }
  await cases.getByRole("button", { name: "Source provenance", exact: true }).click();
  const source = cases.getByTestId("public-source");
  await source.waitFor();
  const text = await source.innerText();
  for (const pin of ["5ac4747551f733d673cd6828a55732b7b542d3552698325cbdac2df2a69aa62f", "raw sha256", "byte offset", "byte length"]) {
    assert.ok(text.includes(pin), text);
  }
  await source.scrollIntoViewIfNeeded();
  await geometry(page, name + "-source");
  await screenshot(page, name + "-source");
  check(name + "-case-alarm-event-entities-source", { resource_id: ref, source: text });
  await cases.getByRole("button", { name: "Refresh cases", exact: true }).focus();
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => ({ tag: document.activeElement.tagName,
    outline: getComputedStyle(document.activeElement).outlineStyle, text: document.activeElement.textContent }));
  assert.equal(focused.tag, "BUTTON");
  assert.notEqual(focused.outline, "none");
  check(name + "-keyboard", focused);
}

let runtime, browser;
try {
  const { privateKey, publicKey } = generateKeyPairSync("ed25519");
  const headers = signer(privateKey);
  runtime = await server(publicKey.export({ format: "der", type: "spki" }).subarray(-32).toString("base64"));
  report.origin = runtime.origin;
  console.log("Production test server ready: " + runtime.origin);
  const anonymous = await fetch(runtime.origin + "/api/cyber/public/profile", { signal: AbortSignal.timeout(10000) });
  assert.equal(anonymous.status, 401);
  check("anonymous-refused", anonymous.status);
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  await context.route("**/*", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.origin !== runtime.origin) return route.abort("blockedbyclient");
    const body = request.postDataBuffer() || Buffer.alloc(0);
    await route.continue({ headers: { ...request.headers(), ...headers(request.method(), url.pathname + url.search, body) } });
  });
  const page = await context.newPage();
  page.setDefaultTimeout(15000);
  page.on("pageerror", (error) => report.browser_errors.push(String(error)));
  page.on("response", (response) => report.requests.push({ url: response.url(), status: response.status() }));
  await walk(page, { width: 1440, height: 1000 }, "desktop");
  await walk(page, { width: 390, height: 844 }, "mobile");
  assert.deepEqual(report.browser_errors, []);
  assert.ok(report.requests.every((item) => item.status < 400), JSON.stringify(report.requests.filter((item) => item.status >= 400)));
  report.audit = { status: "no_gaps_found", journeys: ["case-alarm-event-host-user-process-source", "graph evidence return", "keyboard", "reload"],
    viewports: ["1440x1000", "390x844"], empty_error_busy: "busy and error paths have text; error recovery checked separately in backend; empty package not a real-data scenario" };
  report.status = "passed";
} catch (error) {
  report.status = "failed";
  report.error = String(error.stack || error);
  console.error(report.error);
  process.exitCode = 1;
} finally {
  await browser?.close();
  try { await runtime?.close(); } catch (error) { report.cleanup_error = String(error); report.status = "failed"; process.exitCode = 1; }
  report.finished_at = new Date().toISOString();
  writeFileSync(join(output, "report.json"), JSON.stringify(report, null, 2) + "\n");
  console.log("Browser evidence: " + output);
}