import { chmodSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { dirname, isAbsolute, resolve } from "node:path";
import { pathToFileURL } from "node:url";

const approvedSources = new Set(["perth.adx.events_unified", "ait.adx.events", "cyberkb.search.mitre_attack"]);
const viewports = [{ width: 1440, height: 900 }, { width: 900, height: 800 }, { width: 390, height: 844 }];
const requireValue = (condition, code) => { if (!condition) throw new Error(code); };
const stable = value => Array.isArray(value) ? value.map(stable) : value && typeof value === "object"
  ? Object.fromEntries(Object.keys(value).sort().map(key => [key, stable(value[key])])) : value;
const digest = value => createHash("sha256").update(JSON.stringify(stable(value))).digest("hex");

function metrics(identity) {
  const surfaces = identity?.read_surfaces;
  const counters = [surfaces?.knowledge?.metrics, surfaces?.catalogue?.adx?.metrics, surfaces?.catalogue?.search?.metrics];
  const total = { known_attempts: 0, unknown_attempt_operations: 0 };
  for (const counter of counters) for (const key of Object.keys(total)) {
    requireValue(Number.isSafeInteger(counter?.[key]) && counter[key] >= 0, "read_guard_metrics_required");
    total[key] += counter[key];
  }
  return total;
}

export function loadAcceptance(env = process.env) {
  requireValue(env.CYBEREYE_READ_ONLY_ACCEPTANCE === "1", "read_guard_mode_required");
  for (const name of ["CYBEREYE_READ_BASELINE", "CYBEREYE_READ_LEDGER", "ARTIFACT_DIR", "LIVE_PYTHON", "CYBEREYE_READ_RUNNER"]) {
    requireValue(typeof env[name] === "string" && isAbsolute(env[name]), "read_guard_absolute_inputs_required");
  }
  for (const name of ["CYBEREYE_READ_BASELINE", "CYBEREYE_READ_LEDGER"]) {
    requireValue(statSync(env[name]).isFile() && (statSync(env[name]).mode & 0o777) === 0o600, "read_guard_private_inputs_required");
    requireValue((statSync(dirname(env[name])).mode & 0o077) === 0, "read_guard_private_directory_required");
  }
  const output = resolve(env.ARTIFACT_DIR);
  requireValue(!existsSync(output) && (statSync(dirname(output)).mode & 0o077) === 0, "read_guard_new_private_output_required");
  const baseline = JSON.parse(readFileSync(env.CYBEREYE_READ_BASELINE, "utf8"));
  requireValue(baseline.sources && Object.keys(baseline.sources).every(key => approvedSources.has(key)), "read_guard_sources_required");
  for (const source of Object.values(baseline.sources)) {
    requireValue(source.metadata && source.content && Number.isSafeInteger(source.limit)
      && source.limit >= 1 && source.limit <= 100, "read_guard_frozen_results_required");
  }
  const command = (action, args = []) => JSON.parse(execFileSync(env.LIVE_PYTHON,
    ["-B", env.CYBEREYE_READ_RUNNER, action, "--ledger", env.CYBEREYE_READ_LEDGER, ...args],
    { encoding: "utf8", env: { ...env }, maxBuffer: 1_048_576, stdio: ["ignore", "pipe", "pipe"] }));
  const ledger = { snapshot: () => command("ledger-status"),
    reserve: (owner, maximum, binding) => command("ledger-reserve", ["--owner", owner, "--maximum", String(maximum), "--binding", JSON.stringify(binding)]).reservation_id,
    settle: (reservation, attempts) => command("ledger-settle", ["--reservation", reservation, "--attempts", attempts === null ? "unknown" : String(attempts)]) };
  ledger.snapshot();
  return { base: env.CYBEREYE_URL, output, baseline, ledger };
}

export function createReadGuard({ base, baseline, ledger }) {
  const origin = new URL(base);
  requireValue(origin.protocol === "http:" && ["127.0.0.1", "localhost"].includes(origin.hostname)
    && !origin.username && !origin.password && ["", "/"].includes(origin.pathname), "read_guard_loopback_required");
  requireValue(baseline?.schema_version === 1 && /^[a-f0-9]{64}$/.test(baseline.candidate_sha256 || "")
    && baseline.binding?.candidate_sha256 === baseline.candidate_sha256
    && Date.parse(baseline.expires_at) > Date.now() && baseline.sources && ledger, "read_guard_baseline_required");
  requireValue(Object.keys(baseline.sources).every(key => approvedSources.has(key)), "read_guard_source_refused");
  const blocked = [], failures = [], admissions = [], pending = new Map();
  let queue = Promise.resolve();
  const rawFetch = (url, options = {}) => fetch(url, { ...options, redirect: "manual", signal: AbortSignal.timeout(30_000) });
  function classify(value, options = {}) {
    requireValue(Date.parse(baseline.expires_at) > Date.now(), "read_guard_baseline_expired");
    const url = new URL(value, base), method = (options.method || "GET").toUpperCase();
    requireValue(url.origin === origin.origin && !url.username && !url.password && method === "GET", "read_guard_request_refused");
    if (!url.pathname.startsWith("/api/")) return { url, maximum: 0 };
    const safe = /^\/api\/(?:whoami|cyber\/(?:rules|scenarios|agents|tools|library-identity|detector\/configuration|inventory\/(?:tree|selection)|agent-editor(?:\/[A-Za-z0-9_.-]+)*))$/;
    if (safe.test(url.pathname)) return { url, maximum: 0 };
    if (/^\/api\/cyber\/inventory\/(?:resource|content)$/.test(url.pathname)) {
      const found = Object.entries(baseline.sources).find(([, source]) => source.node === url.searchParams.get("node"));
      requireValue(found, "read_guard_source_refused");
      const [sourceId] = found;
      const limit = url.searchParams.get("limit");
      requireValue(limit === null || /^(?:[1-9][0-9]?|100)$/.test(limit), "read_guard_limit_refused");
      const selection = new Headers(options.headers).get("X-Inventory-Selection");
      const disabled = selection === "none" || selection === "" || selection !== null && selection !== "all" && !selection.split(",").includes(sourceId);
      return { url, maximum: disabled ? 0 : url.pathname.endsWith("resource") ? 2 : 3, sourceId };
    }
    if (/^\/api\/cyber\/knowledge\/type\/[A-Za-z0-9_:.-]+$/.test(url.pathname)) {
      requireValue((baseline.citation_paths || []).includes(url.pathname), "read_guard_citation_not_frozen");
      return { url, maximum: 2 };
    }
    throw new Error("read_guard_request_refused");
  }
  async function currentIdentity() {
    const response = await rawFetch(new URL("/api/cyber/library-identity", base));
    requireValue(response.status === 200, "read_guard_identity_unavailable");
    const identity = await response.json();
    requireValue(identity.editable === false && identity.wheel_install === true && identity.transport === "native"
      && Object.entries(baseline.identity || {}).every(([key, value]) => digest(identity[key]) === digest(value)), "read_guard_candidate_mismatch");
    return metrics(identity);
  }
  async function acquire() {
    let release;
    const gate = new Promise(resolveGate => { release = resolveGate; });
    const previous = queue;
    queue = previous.catch(() => {}).then(() => gate);
    await previous.catch(() => {});
    return release;
  }
  async function begin(admission) {
    const release = await acquire();
    try {
      requireValue(ledger.snapshot().remaining_slots >= admission.maximum, "budget_exhausted");
      const before = await currentIdentity();
      const reservation = ledger.reserve("browser", admission.maximum, baseline.binding);
      admissions.push({ source_id: admission.sourceId || "citation", maximum: admission.maximum, reservation });
      return { ...admission, release, before, reservation };
    } catch (error) { release(); throw error; }
  }
  async function finish(active, failed = false) {
    let attempts = null;
    try {
      if (!failed) {
        const after = await currentIdentity();
        const known = after.known_attempts - active.before.known_attempts;
        const unknown = after.unknown_attempt_operations - active.before.unknown_attempt_operations;
        requireValue(known >= 0 && known <= active.maximum && unknown >= 0, "read_guard_counter_mismatch");
        if (unknown === 0) attempts = known;
      }
    } catch { failures.push("read_guard_reconciliation_unknown"); }
    finally { ledger.settle(active.reservation, attempts); active.release(); }
  }
  async function guardedFetch(value, options = {}) {
    let admission;
    try { admission = classify(value, options); }
    catch (error) { blocked.push({ method: options.method || "GET", path: new URL(value, base).pathname }); throw error; }
    if (!admission.maximum) return rawFetch(admission.url, options);
    const active = await begin(admission);
    try {
      const response = await rawFetch(admission.url, options);
      await finish(active);
      return response;
    } catch (error) { await finish(active, true); throw error; }
  }
  async function install(context) {
    context.on("requestfinished", request => {
      const active = pending.get(request);
      if (active) { pending.delete(request); finish(active).catch(() => failures.push("read_guard_settlement_failed")); }
    });
    context.on("requestfailed", request => {
      const active = pending.get(request);
      if (active) { pending.delete(request); finish(active, true).catch(() => failures.push("read_guard_settlement_failed")); }
    });
    await context.route("**/*", async route => {
      const request = route.request();
      try {
        const admission = classify(request.url(), { method: request.method(), headers: request.headers() });
        if (admission.maximum) pending.set(request, await begin(admission));
        await route.continue();
      } catch {
        blocked.push({ method: request.method(), path: new URL(request.url()).pathname });
        await route.abort("blockedbyclient");
      }
    });
    if (context.routeWebSocket) await context.routeWebSocket("**/*", socket => socket.close());
  }
  return { fetch: guardedFetch, install, blocked, failures, admissions, identity: currentIdentity,
    async drain() { await queue; requireValue(failures.length === 0, "read_guard_unknown_delivery"); } };
}

function compare(observed, expected) {
  const value = { ...observed };
  delete value.observedAt;
  requireValue(digest(value) === digest(expected), "frozen_catalogue_mismatch");
}

export async function selectionJourney(page, guard, source, width) {
  const storageKey = "cybereye.inventory.selection";
  const explorer = page.getByTestId("resource-explorer");
  const state = () => page.evaluate(key => JSON.parse(sessionStorage.getItem(key)), storageKey);
  await explorer.getByRole("button", { name: "All on", exact: true }).click();
  requireValue((await state()).mode === "all", "selection_all_not_persisted");
  await explorer.getByRole("button", { name: "All off", exact: true }).click();
  requireValue((await state()).mode === "none", "selection_none_not_persisted");
  const expand = explorer.getByRole("button", { name: `Expand ${source.useCaseLabel}`, exact: true });
  if (await expand.count()) await expand.click();
  const checkbox = explorer.locator(`[data-source-id="${source.sourceId}"] input[type=checkbox]`);
  await checkbox.focus();
  requireValue(await checkbox.evaluate(node => document.activeElement === node), "selection_keyboard_focus_missing");
  await checkbox.press("Space");
  const selected = await state();
  requireValue(selected.mode === "explicit" && digest(selected.ids) === digest([source.sourceId]), "selection_checkbox_not_persisted");
  const label = await checkbox.locator("..").boundingBox();
  requireValue(label && label.width >= 24 && label.height >= 24, "selection_target_too_small");
  const direct = await guard.fetch(`/api/cyber/inventory/resource?node=${encodeURIComponent(source.id)}`, {
    headers: { "X-Inventory-Selection": "none" },
  });
  requireValue(direct.status === 409, "excluded_source_not_refused");
  const callerState = await guard.fetch("/api/cyber/inventory/selection", { headers: { "X-Inventory-Selection": source.sourceId } });
  const confirmed = await callerState.json();
  requireValue(confirmed.mode === "explicit" && digest(confirmed.enabled) === digest([source.sourceId]), "selection_readback_mismatch");
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("tab", { name: "Data & Tools Catalogue", exact: true }).click();
  requireValue(digest(await state()) === digest(selected), "selection_reload_widened");
  await page.evaluate(({ key, selection }) => sessionStorage.setItem(key, JSON.stringify(selection)), {
    key: storageKey, selection: { mode: "explicit", ids: [source.sourceId, "retired.source"] },
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.getByRole("tab", { name: "Data & Tools Catalogue", exact: true }).click();
  await page.waitForFunction(({ key, id }) => {
    const value = JSON.parse(sessionStorage.getItem(key) || "null");
    return value?.mode === "explicit" && value.ids.length === 1 && value.ids[0] === id;
  }, { key: storageKey, id: source.sourceId });
  return { case_id: `SCR-B3-selection-${width}`, passed: true, evidence_class: "browser", tab_only: true,
    stored_selection_sha256: digest(await state()), checkbox_target: { width: label.width, height: label.height } };
}

export async function run(env = process.env) {
  const inputs = loadAcceptance(env);
  const { base, output, baseline, ledger } = inputs;
  const guard = createReadGuard(inputs);
  const report = { candidate_sha256: baseline.candidate_sha256, checks: [], screenshots: [],
    blocked_before_delivery: guard.blocked, admissions: guard.admissions, passed: false, model_calls: false,
    fake_service_responses: false, authentication_changed: false, started_at: new Date().toISOString() };
  mkdirSync(output, { mode: 0o700 });
  let browser;
  try {
    await guard.identity();
    const read = async (path, params = {}) => {
      const response = await guard.fetch(`${path}?${new URLSearchParams(params)}`);
      requireValue(response.status === 200, "catalogue_http_failure");
      return response.json();
    };
    const root = await read("/api/cyber/inventory/tree");
    requireValue(digest(root.children.map(item => item.useCaseId).sort()) === digest(["ait", "open_source_cybersecurity", "perth_cybersec_poc_0"]), "catalogue_use_case_mismatch");
    const sources = [];
    for (const useCase of root.children) {
      const tree = await read("/api/cyber/inventory/tree", { node: useCase.id });
      sources.push(...tree.children.map(item => ({ ...item, useCaseLabel: useCase.label })));
    }
    requireValue(sources.length === 5, "catalogue_source_count_mismatch");
    const selected = sources.filter(item => approvedSources.has(item.sourceId) && baseline.sources[item.sourceId]);
    for (const source of selected) {
      const frozen = baseline.sources[source.sourceId];
      requireValue(frozen.node === source.id, "catalogue_node_mismatch");
      compare(await read("/api/cyber/inventory/resource", { node: source.id }), frozen.metadata);
      compare(await read("/api/cyber/inventory/content", { node: source.id, limit: frozen.limit }), frozen.content);
      report.checks.push({ case_id: `SCR-B1-api-${source.sourceId}`, passed: true, evidence_class: "live", observed_sha256: digest(frozen.content) });
    }
    const { chromium } = await import("playwright");
    browser = await chromium.launch({ headless: true });
    for (const viewport of viewports) {
      const context = await browser.newContext({ viewport, serviceWorkers: "block" });
      await guard.install(context);
      const page = await context.newPage();
      const responses = [];
      page.on("response", response => {
        const url = new URL(response.url());
        if (/^\/api\/cyber\/inventory\/(resource|content)$/.test(url.pathname) && response.status() === 200) {
          responses.push(response.json().then(body => ({ path: url.pathname, node: url.searchParams.get("node"), body })));
        }
      });
      await page.goto(base, { waitUntil: "domcontentloaded" });
      for (const name of ["Investigation", "Data & Tools Catalogue", "Agent Editor"]) {
        requireValue(await page.getByRole("tab", { name, exact: true }).isVisible(), "workspace_tab_unavailable");
      }
      await page.getByRole("tab", { name: "Data & Tools Catalogue", exact: true }).click();
      const explorer = page.getByTestId("resource-explorer");
      for (const useCase of root.children) {
        const expand = explorer.getByRole("button", { name: `Expand ${useCase.label}`, exact: true });
        if (await expand.count()) await expand.click();
      }
      for (const source of selected) {
        const frozen = baseline.sources[source.sourceId];
        requireValue(frozen.limit === 25, "browser_preview_limit_must_match_existing_control");
        const metadataResponse = page.waitForResponse(response => {
          const url = new URL(response.url());
          return url.pathname === "/api/cyber/inventory/resource" && url.searchParams.get("node") === source.id;
        });
        await explorer.locator(`[data-source-id="${source.sourceId}"] .inv-row-label`).click();
        const pane = page.getByRole("region", { name: `${source.label}, ${source.useCaseLabel}`, exact: true });
        await pane.getByRole("region", { name: "Measured now", exact: true }).waitFor({ timeout: 30_000 });
        compare(await (await metadataResponse).json(), frozen.metadata);
        const measured = await pane.getByRole("region", { name: "Measured now", exact: true }).innerText();
        for (const value of Object.values(frozen.metadata.metrics)) {
          requireValue(measured.includes(Number.isFinite(value) ? value.toLocaleString("en") : String(value)), "rendered_count_mismatch");
        }
        if (frozen.metadata.schemaFields?.length) {
          const renderedSchema = await pane.locator(".inv-schema > span").evaluateAll(nodes => nodes.map(node => ({
            name: node.querySelector("b").textContent, type: node.querySelector("i").textContent,
          })));
          requireValue(digest(renderedSchema) === digest(frozen.metadata.schemaFields), "rendered_schema_mismatch");
        }
        const button = pane.getByRole("button", { name: "Preview contents", exact: true });
        const contentResponse = page.waitForResponse(response => {
          const url = new URL(response.url());
          return url.pathname === "/api/cyber/inventory/content" && url.searchParams.get("node") === source.id;
        });
        await button.focus();
        await button.press("Enter");
        compare(await (await contentResponse).json(), frozen.content);
        if (frozen.content.rows?.length) {
          await pane.locator("tbody tr").first().waitFor({ timeout: 30_000 });
          const cells = await pane.locator("tbody tr").evaluateAll(nodes => nodes.map(node => [...node.querySelectorAll("td")].map(cell => cell.textContent)));
          requireValue(cells.length === frozen.content.rows.length, "rendered_row_count_mismatch");
          for (let position = 0; position < cells.length; position += 1) {
            for (const column of frozen.content.columns) {
              const value = frozen.content.rows[position][column];
              if (value !== null && value !== undefined && String(value).length <= 120) {
                requireValue(cells[position].some(cell => cell.includes(String(value))), "rendered_cell_mismatch");
              }
            }
          }
        } else requireValue((await pane.innerText()).toLowerCase().includes("empty"), "empty_state_not_visible");
        const geometry = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
        requireValue(geometry.document <= geometry.viewport + 1, "catalogue_horizontal_overflow");
        const shot = `${output}/${source.sourceId}-${viewport.width}.png`;
        await page.screenshot({ path: shot, fullPage: true });
        chmodSync(shot, 0o600);
        report.screenshots.push(shot);
        report.checks.push({ case_id: `SCR-B1-ui-${source.sourceId}-${viewport.width}`, passed: true, geometry });
      }
      const selection = await selectionJourney(page, guard, selected[0], viewport.width);
      report.checks.push(selection);
      const second = await context.newPage();
      await second.goto(base, { waitUntil: "domcontentloaded" });
      const secondSelection = await second.evaluate(() => sessionStorage.getItem("cybereye.inventory.selection"));
      requireValue(secondSelection === null || JSON.parse(secondSelection).mode === "all", "tab_selection_shared");
      await second.close();
      await page.getByRole("tab", { name: "Agent Editor", exact: true }).click();
      await page.getByRole("tab", { name: "Investigation", exact: true }).click();
      await Promise.all(responses);
      await guard.drain();
      await context.close();
    }
    report.passed = true;
  } catch (error) {
    report.error_code = /^[a-z_]{1,100}$/.test(error.message || "") ? error.message : "browser_verification_failed";
  } finally {
    if (browser) await browser.close();
    report.finished_at = new Date().toISOString();
    report.call_accounting = ledger.snapshot();
    writeFileSync(`${output}/report.json`, JSON.stringify(report, null, 2), { flag: "wx", mode: 0o600 });
  }
  return report;
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const report = await run();
    console.log(JSON.stringify({ passed: report.passed, checks: report.checks.length, output: process.env.ARTIFACT_DIR,
      error_code: report.error_code, call_accounting: report.call_accounting }));
    process.exitCode = report.passed ? 0 : 2;
  } catch { console.error(JSON.stringify({ status: "BLOCKED", error_code: "read_guard_preflight_refused" })); process.exitCode = 2; }
}