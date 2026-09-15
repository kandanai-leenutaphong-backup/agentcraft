import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { chromium } from "playwright";
import { signContext } from "../support/verify-auth.mjs";

const BASE = process.env.CYBEREYE_URL || "http://127.0.0.1:5173";
const OUTPUT = process.env.ARTIFACT_DIR || "/tmp/cybereye-agent-editor";
const LIVE = ["1", "chat"].includes(process.env.CYBEREYE_EDITOR_LIVE);
const INVESTIGATE = process.env.CYBEREYE_EDITOR_LIVE === "1";
const PREFIX = "/api/cyber/agent-editor";
const suffix = Date.now().toString(36);
const names = [`Editor test ${suffix}`, `Editor test ${suffix} revised`];
const versionNames = ["Baseline", "Focused triage"];
const findings = [];
const record = (name, detail = "") => { findings.push({ name, status: "pass", detail }); console.log(`PASS ${name}${detail ? `: ${detail}` : ""}`); };

async function api(page, path, method = "GET", body) {
  return page.evaluate(async ({ path, method, body }) => {
    const response = await fetch(path, { method, headers: { "Content-Type": "application/json" },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${await response.text()}`);
    return response.json();
  }, { path, method, body });
}

async function installTrace(page) {
  await page.addInitScript(() => {
    window.__editorRuns = [];
    const fetchOriginal = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await fetchOriginal(...args);
      const path = new URL(response.url).pathname;
      const kind = path.startsWith("/api/chat/") ? "chat" : path.endsWith("/situations/diagnose") ? "diagnosis" : null;
      if (!kind || !response.body) return response;
      const trace = { kind, done: false, errors: [], metadata: [], events: {} };
      window.__editorRuns.push(trace);
      const getReader = response.body.getReader.bind(response.body);
      response.body.getReader = (...options) => {
        const reader = getReader(...options);
        const read = reader.read.bind(reader);
        const decoder = new TextDecoder();
        let buffer = "";
        reader.read = async (...parameters) => {
          const chunk = await read(...parameters);
          buffer += decoder.decode(chunk.value, { stream: !chunk.done });
          const frames = buffer.replace(/\r\n/g, "\n").split("\n\n");
          buffer = frames.pop();
          for (const frame of frames) {
            const kind = /^event:\s*(\S+)/m.exec(frame)?.[1];
            if (!kind) continue;
            trace.events[kind] = (trace.events[kind] || 0) + 1;
            const lines = [...frame.matchAll(/^data:\s*(.*)$/gm)].map((line) => line[1]);
            const data = JSON.parse(lines.join("\n"));
            if (kind === "metadata") trace.metadata.push({ id: data.agent_id, name: data.agent_name,
              version: data.config_version, model: data.model });
            if (kind === "done") trace.done = true;
            if (kind === "error") trace.errors.push(data.detail || data.error);
          }
          return chunk;
        };
        return reader;
      };
      return response;
    };
  });
}

async function main() {
  mkdirSync(OUTPUT, { recursive: true });
  const browser = await chromium.launch();
  let originalRole;
  let page;
  let agentId;
  const consoleErrors = [];
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, serviceWorkers: "block" });
    await signContext(context, BASE, "");
    page = await context.newPage();
    await installTrace(page);
    page.on("pageerror", (error) => consoleErrors.push(String(error)));
    await page.goto(BASE, { waitUntil: "domcontentloaded" });
    assert.equal(await page.getByRole("tab", { name: "Explorer", exact: true }).count(), 0);
    await page.getByRole("tab", { name: "Data & Tools Catalogue", exact: true }).click();
    const catalogueView = page.getByTestId("resource-explorer");
    await catalogueView.locator(".rex-sources .inv-panel-tree").waitFor();
    assert.equal(await catalogueView.locator(":scope > .rex-navigation").count(), 2);
    await catalogueView.locator(".agent-branch > summary").first().click();
    await catalogueView.locator(".agent-tool-list button").first().click();
    await catalogueView.locator(".rex-pane:not([hidden]) .scv[data-highlighted=true]").waitFor();
    record("Data & Tools Catalogue replaces the Explorer tab and retains data navigation and tool inspection");
    await page.getByRole("tab", { name: "Agent Editor", exact: true }).click();
    const editor = page.getByTestId("agent-editor");
    await editor.getByRole("button", { name: "Create agent", exact: true }).waitFor();
    assert.equal(await editor.locator(".rex-sources, .inv-panel-tree, .inv-panel-detail").count(), 0);
    assert.equal(await editor.locator(":scope > .rex-navigation").count(), 1);
    assert.equal(await editor.locator(":scope > .rex-viewer").count(), 1);
    record("Agent Editor contains only agent navigation and its configuration viewer");
    const initial = await api(page, PREFIX);
    originalRole = initial.investigator;
    const builtin = initial.agents.find((agent) => agent.builtin);
    await editor.getByRole("button", { name: `Edit ${builtin.name}`, exact: true }).click();
    const form = editor.getByRole("form", { name: "Agent configuration" });
    await form.getByRole("textbox", { name: "Name", exact: true }).waitFor();
    const original = await api(page, `${PREFIX}/agents/${builtin.id}`);
    assert.equal(await form.getByRole("textbox", { name: "Name", exact: true }).inputValue(), original.name);
    assert.equal(await form.locator(".ae-file").count(), original.instruction_files.length);
    assert.equal(await form.locator(".ae-tool-rows select").count(), original.tool_ids.length);
    record("existing CyberDefender uses the same editor with its original instructions and tools");

    const versionName = form.getByRole("textbox", { name: "Version name", exact: true });
    const createVersion = form.getByRole("button", { name: "Create New Version", exact: true });
    const saveVersion = form.getByRole("button", { name: "Save New Version", exact: true });
    const reset = form.getByRole("button", { name: "Reset", exact: true });
    const addTool = form.getByRole("button", { name: "Add tool", exact: true });
    assert.deepEqual(await form.locator(".ae-toolbar > button").allTextContents(),
      ["Create New Version", "Save New Version", "Reset"]);
    assert.equal(await form.locator(".ae-toolbar > :first-child").getAttribute("aria-label"), "Agent version");
    assert.equal(await form.locator(".ae-draft-state, .ae-toolbar label").count(), 0);
    assert.equal(await form.getByRole("textbox", { name: "Name", exact: true }).isEditable(), false);
    assert.equal(await form.getByRole("combobox", { name: "LLM", exact: true }).isDisabled(), true);
    assert.equal(await saveVersion.isDisabled(), true);
    assert.equal(await addTool.isDisabled(), true);
    await form.getByRole("button", { name: "Inspect tool 1", exact: true }).click();
    await editor.locator(".rex-pane:not([hidden]) .scv[data-highlighted=true]").waitFor();
    await editor.getByRole("button", { name: "Agent configuration", exact: true }).click();
    record("saved versions open locked; toolbar order is selector, Create, Save, Reset; inspection stays available");

    await editor.getByRole("button", { name: "Unlock editing", exact: true }).click();
    assert.equal(await versionName.isEditable(), true);
    assert.equal(await form.getAttribute("data-drafting"), "true");
    assert.equal(await saveVersion.isDisabled(), true);
    assert.equal(await addTool.isDisabled(), true);
    assert.equal(await addTool.getAttribute("title"), "All available tools are assigned");
    await form.getByRole("button", { name: `Remove tool ${original.tool_ids.length}`, exact: true }).click();
    assert.equal(await addTool.isEnabled(), true);
    assert.equal(await saveVersion.isEnabled(), true);
    await addTool.click();
    await form.getByRole("combobox", { name: `Tool ${original.tool_ids.length}`, exact: true })
      .selectOption(original.tool_ids.at(-1));
    assert.equal(await saveVersion.isDisabled(), true);
    record("unlock creates only a draft; all-tools cap remains; reverting tool changes disables Save again");

    await versionName.fill("Unsaved variant");
    await form.getByRole("textbox", { name: "Prompt / system instruction", exact: true }).fill("Unsaved instructions");
    await form.getByLabel("Upload Markdown instructions").setInputFiles({
      name: "reset-me.md", mimeType: "text/markdown", buffer: Buffer.from("Unsaved attachment"),
    });
    await form.locator(".ae-file").nth(original.instruction_files.length).waitFor();
    await editor.getByRole("button", { name: "Lock editing", exact: true }).click();
    assert.equal(await versionName.isEditable(), false);
    assert.equal(await versionName.inputValue(), "Unsaved variant");
    assert.equal(await saveVersion.isDisabled(), true);
    await editor.getByRole("button", { name: "Unlock editing", exact: true }).click();
    assert.equal(await saveVersion.isEnabled(), true);
    await editor.getByRole("button", { name: "Lock editing", exact: true }).click();
    await reset.click();
    assert.equal(await versionName.inputValue(), original.version_name);
    assert.equal(await form.getByRole("textbox", { name: "Prompt / system instruction", exact: true }).inputValue(), original.system_prompt);
    assert.equal(await form.locator(".ae-file").count(), original.instruction_files.length);
    assert.equal(await versionName.isEditable(), false);
    assert.equal(await form.getAttribute("data-drafting"), "false");
    assert.deepEqual((await api(page, `${PREFIX}/agents/${builtin.id}`)).versions, original.versions);
    record("locking preserves draft changes; Reset removes unsaved fields and uploads without creating a version");

    await createVersion.click();
    assert.equal(await versionName.evaluate((node) => document.activeElement === node), true);
    assert.equal(await saveVersion.isDisabled(), true);
    await versionName.fill("Temporary name");
    assert.equal(await saveVersion.isEnabled(), true);
    await versionName.fill(original.version_name);
    assert.equal(await saveVersion.isDisabled(), true);
    await reset.click();
    record("Create New Version focuses its name and Save enables only for changes");

    await editor.getByRole("button", { name: "Create agent", exact: true }).click();
    assert.equal(await form.getByRole("textbox", { name: "Name", exact: true }).inputValue(), "");
    assert.equal(await form.locator(".ae-tool-rows select").count(), 0);
    await form.getByRole("textbox", { name: "Name", exact: true }).fill(names[0]);
    await versionName.fill(versionNames[0]);
    await form.getByRole("combobox", { name: "LLM", exact: true }).selectOption(initial.models[0].id);
    await form.getByRole("textbox", { name: "Prompt / system instruction", exact: true }).fill(
      "Use the attached instructions. For diagnosis, follow the requested evidence and sequence procedure.");
    await form.getByLabel("Upload Markdown instructions").setInputFiles({
      name: "not-markdown.txt", mimeType: "text/plain", buffer: Buffer.from("not an accepted file"),
    });
    await form.getByRole("alert").filter({ hasText: ".md" }).waitFor();
    assert.equal(await form.locator(".ae-file").count(), 0);
    record("non-Markdown upload is refused without adding an attachment");
    const uploaded = [
      { name: "voice.md", content: "For ordinary chat replies only, begin with EDITOR_FILE_V1. Never insert this marker into telemetry evidence.\n" },
      { name: "evidence.md", content: "State uncertainty explicitly. Never invent historical observations or citations.\n" },
    ];
    await form.getByLabel("Upload Markdown instructions").setInputFiles(uploaded.map((file) => ({
      name: file.name, mimeType: "text/markdown", buffer: Buffer.from(file.content),
    })));
    await form.locator(".ae-file").nth(1).waitFor();
    for (const [index, tool] of initial.tools.entries()) {
      await form.getByRole("button", { name: "Add tool", exact: true }).click();
      await form.getByRole("combobox", { name: `Tool ${index + 1}`, exact: true }).selectOption(tool.id);
    }
    await form.getByRole("button", { name: "Inspect tool 1", exact: true }).click();
    await editor.locator(".rex-pane:not([hidden]) .scv[data-highlighted=true]").waitFor();
    await editor.getByRole("button", { name: "Agent configuration", exact: true }).click();
    await form.getByRole("button", { name: "Save Agent", exact: true }).click();
    await form.getByRole("status").filter({ hasText: "Agent saved." }).waitFor();
    const afterCreate = await api(page, PREFIX);
    agentId = afterCreate.agents.find((agent) => agent.name === names[0]).id;
    const first = await api(page, `${PREFIX}/agents/${agentId}?version=1`);
    assert.deepEqual(first.instruction_files, uploaded);
    assert.deepEqual(first.tool_ids, initial.tools.map((tool) => tool.id));
    assert.equal(first.version_name, versionNames[0]);
    assert.equal(await versionName.isEditable(), false);
    assert.equal(afterCreate.investigator.agent_id, originalRole.agent_id);
    record("new agent, selected tools and multiple Markdown files persist and read back as version 1");
    record("saving an agent does not silently assign Investigator");

    await createVersion.click();
    assert.equal(await saveVersion.isDisabled(), true);
    await versionName.fill(versionNames[1]);
    await form.getByRole("textbox", { name: "Name", exact: true }).fill(names[1]);
    await form.getByRole("textbox", { name: "voice.md instructions", exact: true }).fill(uploaded[0].content.replace("V1", "V2"));
    await page.route(`**${PREFIX}/agents/${agentId}/versions`, (route) => route.fulfill({
      status: 503, json: { detail: "Verification fixture: storage unavailable" },
    }));
    await saveVersion.click();
    await form.getByRole("alert").filter({ hasText: "storage unavailable" }).waitFor();
    assert.equal(await form.getByRole("textbox", { name: "Name", exact: true }).inputValue(), names[1]);
    assert.equal((await api(page, `${PREFIX}/agents/${agentId}`)).version, 1);
    await page.unroute(`**${PREFIX}/agents/${agentId}/versions`);
    await saveVersion.click();
    await form.getByRole("status").filter({ hasText: "New version saved." }).waitFor();
    const second = await api(page, `${PREFIX}/agents/${agentId}?version=2`);
    assert.equal(second.name, names[1]);
    assert.equal(second.version_name, versionNames[1]);
    assert.deepEqual(second.version_names, { 1: versionNames[0], 2: versionNames[1] });
    assert.ok(second.instruction_files[0].content.includes("EDITOR_FILE_V2"));
    assert.equal((await api(page, `${PREFIX}/agents/${agentId}?version=1`)).name, names[0]);
    record("failed save preserves the draft; retry creates version 2 without overwriting version 1", "storage error was a browser fixture");
    await form.getByRole("combobox", { name: "Agent version", exact: true }).selectOption("1");
    await page.waitForFunction((name) => document.getElementById("ae-name")?.value === name, names[0]);
    assert.equal(await form.getByRole("textbox", { name: "voice.md instructions", exact: true }).inputValue(), uploaded[0].content);
    assert.equal(await versionName.inputValue(), versionNames[0]);
    assert.deepEqual(await form.getByRole("combobox", { name: "Agent version", exact: true }).locator("option").allTextContents(),
      ["v1 - Baseline", "v2 - Focused triage"]);
    record("named version dropdown reloads original label, name, prompts and tools");
    await createVersion.click();
    assert.equal(await form.locator(".ae-version-select option:checked").textContent(), "Draft from v1 - Baseline");
    await versionName.fill("Discard this variant");
    page.once("dialog", (dialog) => dialog.dismiss());
    await form.getByRole("combobox", { name: "Agent version", exact: true }).selectOption("2");
    assert.equal(await versionName.inputValue(), "Discard this variant");
    await reset.click();
    assert.equal(await versionName.inputValue(), "Baseline");
    assert.equal(await form.getByRole("combobox", { name: "Agent version", exact: true }).inputValue(), "1");
    record("an old version creates a draft from that version; cancel and Reset preserve immutable history");

    for (const viewport of [{ width: 1440, height: 900 }, { width: 900, height: 800 }, { width: 390, height: 844 }, { width: 320, height: 740 }]) {
      await page.setViewportSize(viewport);
      const geometry = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth,
        controls: [...document.querySelectorAll('#workspace-agent-editor .ae-form input:not([hidden]), #workspace-agent-editor .ae-form select, #workspace-agent-editor .ae-form textarea, #workspace-agent-editor .ae-toolbar button, #workspace-agent-editor .ae-edit-lock')]
          .filter((node) => node.getBoundingClientRect().width).map((node) => ({ right: node.getBoundingClientRect().right, left: node.getBoundingClientRect().left })) }));
      assert.ok(geometry.scroll <= viewport.width, JSON.stringify(geometry));
      assert.ok(geometry.controls.every((item) => item.left >= 0 && item.right <= viewport.width), JSON.stringify(geometry));
      if (viewport.width > 700) {
        const agents = await editor.locator(":scope > .rex-agents").boundingBox();
        const viewer = await editor.locator(":scope > .rex-viewer").boundingBox();
        assert.ok(agents && viewer && Math.abs(agents.y - viewer.y) <= 1
          && Math.abs(agents.x + agents.width - viewer.x) <= 1,
        `Agent navigation and viewer must remain adjacent: ${JSON.stringify({ agents, viewer })}`);
      }
      const toolbar = await form.locator(".ae-toolbar > *").evaluateAll((nodes) => nodes.map((node) => {
        const bounds = node.getBoundingClientRect();
        return { left: bounds.left, right: bounds.right, top: bounds.top, bottom: bounds.bottom };
      }));
      for (const [index, bounds] of toolbar.entries()) {
        assert.ok(toolbar.slice(index + 1).every((next) => bounds.right <= next.left + 1
          || next.right <= bounds.left + 1 || bounds.bottom <= next.top + 1 || next.bottom <= bounds.top + 1),
        `Toolbar controls overlap at ${viewport.width}px: ${JSON.stringify(toolbar)}`);
      }
      await page.screenshot({ path: `${OUTPUT}/editor-${viewport.width}.png`, fullPage: true });
      await editor.locator(".rex-viewer-head").scrollIntoViewIfNeeded();
      await page.screenshot({ path: `${OUTPUT}/editor-form-${viewport.width}.png`, fullPage: false });
      record(`editor and header fit ${viewport.width}px without horizontal overflow`);
    }
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.reload({ waitUntil: "domcontentloaded" });
    await page.getByRole("tab", { name: "Agent Editor", exact: true }).click();
    await editor.getByRole("button", { name: `Edit ${names[1]}`, exact: true }).click();
    await form.getByRole("combobox", { name: "Agent version", exact: true }).waitFor();
    assert.equal(await form.getByRole("combobox", { name: "Agent version", exact: true }).inputValue(), "2");
    assert.equal(await versionName.inputValue(), "Focused triage");
    assert.equal(await versionName.isEditable(), false);
    record("saved library reloads after a full page refresh");

    const assignVersion = async (version) => {
      await page.getByRole("tab", { name: "Agent Editor", exact: true }).click();
      await editor.getByRole("combobox", { name: "Investigator agent", exact: true }).selectOption(agentId);
      await editor.getByRole("combobox", { name: "Investigator version", exact: true }).selectOption(String(version));
      await editor.getByRole("button", { name: "Assign Investigator", exact: true }).click();
      await editor.locator(".ae-roles [role=status]").filter({
        hasText: `Assigned: ${names[version - 1]} / v${version} - ${versionNames[version - 1]}`,
      }).waitFor();
      assert.equal(await editor.getByRole("combobox", { name: "Investigator version", exact: true })
        .locator("option:checked").textContent(), `v${version} - ${versionNames[version - 1]}`);
      const assignment = (await api(page, PREFIX)).investigator;
      assert.equal(assignment.agent_id, agentId);
      assert.equal(assignment.version, version);
      await page.getByRole("tab", { name: "Investigation", exact: true }).click();
      await page.waitForFunction((name) => document.querySelector('[data-testid="active-investigator"]')?.textContent === name, names[version - 1]);
      record(`Investigator version ${version} is assigned and displayed in chat`);
    };

    await assignVersion(1);
    const runChat = async (version) => {
      const before = await page.evaluate(() => window.__editorRuns.filter((run) => run.kind === "chat").length);
      await page.locator(".chat-input textarea").fill("Reply in one short sentence that you are ready to inspect the historical replay. Do not call a tool.");
      await page.locator('.chat-input button[title="Send"]').click();
      await page.waitForFunction((index) => {
        const trace = window.__editorRuns.filter((run) => run.kind === "chat")[index];
        return trace && (trace.done || trace.errors.length);
      }, before, { timeout: 240_000 });
      const trace = await page.evaluate((index) => window.__editorRuns.filter((run) => run.kind === "chat")[index], before);
      assert.deepEqual(trace.errors, []);
      assert.equal(trace.done, true);
      assert.ok(trace.metadata.some((entry) => entry.id === agentId && entry.version === version));
      const message = page.locator("#chat-panel-defender .message.agent:not(.investigation-entry)").last();
      await page.waitForFunction((marker) => [...document.querySelectorAll('#chat-panel-defender .message.agent:not(.investigation-entry) .message-body')].at(-1)?.textContent.includes(marker), `EDITOR_FILE_V${version}`);
      assert.equal(await message.locator(".message-role").getAttribute("data-agent-version"), String(version));
      record(`live chat executes saved version ${version} and its uploaded instruction marker`);
    };

    if (LIVE) await runChat(1);
    await assignVersion(2);
    if (LIVE) await runChat(2);
    if (INVESTIGATE) {
      await page.getByLabel("Test Scenarios").selectOption("focal-privileged-session");
      await page.locator(".scanner-scan-button").click();
      await page.waitForFunction(() => window.__editorRuns.some((run) => run.kind === "diagnosis" && (run.done || run.errors.length)), null, { timeout: 360_000 });
      const trace = await page.evaluate(() => window.__editorRuns.find((run) => run.kind === "diagnosis"));
      assert.deepEqual(trace.errors, []);
      assert.equal(trace.done, true);
      assert.ok(trace.metadata.some((entry) => entry.id === agentId && entry.version === 2));
      assert.ok(trace.events.diagnosis >= 1 && trace.events.sequence_step >= 1 && trace.events.sequence >= 1);
      const investigation = page.getByTestId("investigation-stream");
      assert.equal(await investigation.locator(".message-agent-version").getAttribute("data-agent-id"), agentId);
      assert.ok((await investigation.getByTestId("diagnosis-text").innerText()).length > 20);
      await page.screenshot({ path: `${OUTPUT}/assigned-investigation.png` });
      record("automatic situation investigation uses the assigned agent/version and completes diagnosis plus evidence sequence");
    }
    assert.deepEqual(consoleErrors, []);
    record("no browser runtime errors");
    writeFileSync(`${OUTPUT}/report.json`, JSON.stringify({ base: BASE, agentId, liveChat: LIVE,
      liveInvestigation: INVESTIGATE,
      versions: [first, second], findings, finishedAt: new Date().toISOString() }, null, 2));
  } catch (error) {
    writeFileSync(`${OUTPUT}/failure.json`, JSON.stringify({ base: BASE, agentId, findings,
      error: String(error), consoleErrors }, null, 2));
    if (page && !page.isClosed()) await page.screenshot({ path: `${OUTPUT}/failure.png`, fullPage: true }).catch(() => {});
    throw error;
  } finally {
    if (page && originalRole && !page.isClosed()) {
      const latest = await api(page, PREFIX).catch(() => null);
      if (latest && (latest.investigator.agent_id !== originalRole.agent_id || latest.investigator.version !== originalRole.version)) {
        await api(page, `${PREFIX}/roles/investigator`, "PUT", { agent_id: originalRole.agent_id,
          version: originalRole.version, expected_revision: latest.investigator.revision });
      }
    }
    await browser.close();
  }
}

await main();