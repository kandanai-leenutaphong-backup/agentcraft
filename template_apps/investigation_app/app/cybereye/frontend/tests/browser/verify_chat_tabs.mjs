/** Current investigation acceptance: local or signed, with output directed by ARTIFACT_DIR. */

import { chromium } from "playwright";
import { mkdirSync, writeFileSync } from "node:fs";
import { signContext, signingConfigured } from "../support/verify-auth.mjs";

const BASE = process.env.CYBEREYE_URL || "http://127.0.0.1:5173";
const SCENARIO = process.env.CYBEREYE_SCENARIO || "focal-privileged-session";
const INITIAL_SELECTION_ONLY = process.env.CYBEREYE_VERIFY_INITIAL_SELECTION_ONLY === "1";
const OUT = process.env.ARTIFACT_DIR || "/tmp/cybereye-tabs-proof";
const DESKTOP = { width: 1440, height: 900 };
const MOBILE = { width: 390, height: 844 };
const SCAN_MS = 180_000;
const RUN_MS = 300_000;
const QUIET_MS = 1_000;

const findings = [];
const record = (name, ok, detail) => {
  findings.push({ name, status: ok ? "ok" : "fail", detail });
  console.log(`   [${ok ? "ok" : "FAIL"}] ${name}: ${detail}`);
};
const notObserved = (name, detail) => {
  findings.push({ name, status: "not-observed", detail });
  console.log(`   [not-observed] ${name}: ${detail}`);
};

async function until(predicate, timeout) {
  const deadline = Date.now() + timeout;
  for (;;) {
    if (await predicate()) return true;
    if (Date.now() >= deadline) return false;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
}

async function box(page, selector) {
  const handle = page.locator(selector).first();
  if (!(await handle.count())) return null;
  return handle.boundingBox();
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: DESKTOP, serviceWorkers: "block" });
  const signed = await signContext(context, BASE, "");
  const page = await context.newPage();
  page.on("pageerror", (error) => record("page-error", false, String(error)));
  await page.addInitScript(() => {
    window.__streamRuns = { diagnosis: [], chat: [] };
    const originalFetch = window.fetch.bind(window);
    window.fetch = async (...args) => {
      const response = await originalFetch(...args);
      const path = new URL(response.url).pathname;
      const kind = path.endsWith("/situations/diagnose") ? "diagnosis"
        : path.startsWith("/api/chat/") ? "chat" : null;
      if (!kind || !response.body) return response;
      const trace = { events: [], done: false, closed: false, error: "" };
      window.__streamRuns[kind].push(trace);
      const originalReader = response.body.getReader.bind(response.body);
      response.body.getReader = (...readerArgs) => {
        const reader = originalReader(...readerArgs);
        const originalRead = reader.read.bind(reader);
        const decoder = new TextDecoder();
        let buffer = "";
        reader.read = async (...readArgs) => {
          try {
            const chunk = await originalRead(...readArgs);
            buffer += decoder.decode(chunk.value, { stream: !chunk.done });
            const frames = buffer.replace(/\r\n/g, "\n").split("\n\n");
            buffer = frames.pop();
            for (const frame of frames) {
              const event = /^event:\s*(\S+)/m.exec(frame)?.[1];
              if (event) trace.events.push(event);
              if (event === "done") trace.done = true;
            }
            trace.closed = chunk.done;
            return chunk;
          } catch (error) {
            trace.error = String(error);
            throw error;
          }
        };
        return reader;
      };
      return response;
    };
  });

  const isDiagnose = (request) => request.url().includes("/api/cyber/situations/diagnose");
  const sent = [];
  const failed = [];
  page.on("request", (request) => { if (isDiagnose(request)) sent.push(Date.now()); });
  page.on("requestfailed", (request) => {
    if (isDiagnose(request)) failed.push(request.failure()?.errorText || "failed");
  });

  await page.goto(BASE, { waitUntil: "domcontentloaded" });
  await page.locator(".scanner-scan-button").waitFor({ state: "visible", timeout: 60_000 });
  await page.waitForFunction(
    () => document.querySelectorAll(".scanner-scenario option").length > 1, null, { timeout: 60_000 });
  console.log(`   base ${BASE} · scenario ${SCENARIO} · signed=${signed} (module named: ${signingConfigured()})`);

  const labels = await page.locator(".chat-tabs button span:first-of-type").allInnerTexts();
  record("two-tabs-with-the-promised-labels", labels.length === 2
    && ["Cyber Defender", "Investigator"].includes(labels[0])
    && labels[1] === "Situation Summary", JSON.stringify(labels));
  const diagnosisTab = await page.getByTestId("chat-tab-diagnosis").count();
  record("no-diagnosis-tab-remains", diagnosisTab === 0,
    `chat-tab-diagnosis nodes: ${diagnosisTab}`);

  for (const [name, viewport] of [["desktop", DESKTOP], ["mobile", MOBILE]]) {
    await page.setViewportSize(viewport);
    await page.waitForFunction(
      (width) => document.documentElement.clientWidth === width, viewport.width, { timeout: 5_000 });
    const boxes = await page.locator(".chat-tabs button").evaluateAll((nodes) =>
      nodes.map((node) => node.getBoundingClientRect()).map((r) => ({ x: r.x, w: r.width, h: r.height })));
    const overlap = boxes.some((b, i) => i > 0 && b.x < boxes[i - 1].x + boxes[i - 1].w - 0.5);
    const sized = boxes.every((b) => b.w > 0 && b.h > 0);
    record(`tab-geometry-${name}`, sized && !overlap,
      `${boxes.length} tabs, heights ${boxes.map((b) => Math.round(b.h)).join("/")}, overlap=${overlap}`);
    await page.screenshot({ path: `${OUT}/tabs-${name}.png`, fullPage: false });
  }
  await page.setViewportSize(DESKTOP);

  record("no-diagnose-request-before-a-selection-exists", sent.length === 0,
    `${sent.length} requests`);

  await page.getByLabel("Test Scenarios").selectOption(SCENARIO);
  await page.locator(".scanner-scan-button").click();
  const scanned = await until(
    async () => (await page.locator(".situation-list article.situation").count()) > 0, SCAN_MS);
  record("scan-returns-situations", scanned,
    `${await page.locator(".situation-list article.situation").count()} situation card(s)`);

  const autoStarted = await until(async () => sent.length > 0, 60_000);
  record("investigation-auto-runs-on-selection", autoStarted,
    `${sent.length} diagnose request(s) sent with no investigate button clicked`);
  record("exactly-one-diagnose-request-for-one-selection", sent.length === 1,
    `${sent.length} request(s) on the wire for the initial selection`);

  await page.waitForFunction(() => document.querySelector(
    "[data-testid='investigation-stream'] .tool-card, [data-testid='investigation-stream'] .workload-state.failed"),
    null, { timeout: RUN_MS }).catch(() => {});
  const toolNames = await page.locator("[data-testid='investigation-stream'] .tool-card b").allInnerTexts();
  record("investigation-reports-real-tool-calls", toolNames.length > 0, JSON.stringify(toolNames));

  const onDefenderTab = await page.locator("#chat-panel-defender [data-testid='investigation-stream']").count();
  record("investigation-streams-into-the-cyber-defender-tab", onDefenderTab === 1,
    `investigation entries inside #chat-panel-defender: ${onDefenderTab}`);

  const steps = () => page.locator("[data-testid='sequence-steps'] > li").count().catch(() => 0);
  await page.waitForFunction(() => {
    const trace = window.__streamRuns.diagnosis[0];
    const failed = document.querySelector("[data-testid='investigation-stream'] .workload-state.failed");
    return failed || (trace && (trace.done || trace.closed || trace.error));
  }, null, { timeout: RUN_MS }).catch(() => {});
  const trace = await page.evaluate(() => window.__streamRuns.diagnosis[0]);
  record("diagnose-stream-reaches-a-terminal-state-on-the-wire", trace?.done === true,
    `done=${trace?.done}; reader error=${trace?.error}; events=${JSON.stringify(trace?.events)}; network=${JSON.stringify(failed)}`);
  record("investigation-did-not-double-fire", sent.length === 1, `${sent.length} diagnose request(s)`);
  await page.waitForFunction(() => {
    const node = document.querySelector("[data-testid='investigation-stream'] .workload-state");
    return !!node && (node.classList.contains("done") || node.classList.contains("failed"));
  }, null, { timeout: 60_000 }).catch(() => {});
  const flowState = await page.locator("[data-testid='investigation-stream'] .workload-state")
    .first().getAttribute("class").catch(() => null);
  const failureText = (flowState || "").includes("failed")
    ? await page.locator("[data-testid='investigation-stream']").innerText().catch(() => "") : "";
  record("investigation-flow-settles-done", (flowState || "").includes("done"),
    `workload-state class: ${flowState}${failureText ? `; displayed error: ${failureText}` : ""}`);

  const afterKnowledge = await page.locator("[data-testid='investigation-stream'] .tool-card b").allInnerTexts();
  record("mitre-knowledge-tool-runs-in-the-investigation",
    afterKnowledge.some((name) => /MITRE ATT&CK/i.test(name)), JSON.stringify(afterKnowledge));

  const diagnosisText = await page.locator("[data-testid='diagnosis-text']").innerText().catch(() => "");
  record("investigation-records-a-result", diagnosisText.trim().length > 20,
    `${diagnosisText.trim().length} characters`);
  await page.screenshot({ path: `${OUT}/defender-tab-investigation.png` });

  const stillRunning = await page.locator("[data-testid='investigation-stream'] .tool-state.running").count();
  const composing = await page.locator(".tool-composing").count();
  record("no-tool-is-still-running-at-completion", stillRunning === 0,
    `${stillRunning} tool card(s) still in the running state`);
  record("no-composing-input-remains", composing === 0, `${composing} composing indicator(s)`);
  const timersBefore = await page.locator("[data-testid='investigation-stream'] .tool-duration").allInnerTexts();
  await page.waitForTimeout(QUIET_MS);
  const timersAfter = await page.locator("[data-testid='investigation-stream'] .tool-duration").allInnerTexts();
  record("tool-timers-are-frozen-after-completion",
    timersBefore.length > 0 && JSON.stringify(timersBefore) === JSON.stringify(timersAfter),
    `${timersBefore.length} timer(s) unchanged over ${QUIET_MS}ms: ${JSON.stringify(timersAfter)}`);

  const reasoning = await page.locator("[data-testid='reasoning-block']").count();
  const labelled = await page.locator("[data-testid='reasoning-block'] .reasoning-tag").count();
  const stray = await page.locator("[data-testid='reasoning-block']").evaluateAll(
    (nodes) => nodes.filter((node) => !node.closest("#chat-panel-defender")).length);
  if (reasoning === 0) {
    notObserved("reasoning-blocks-are-labelled-model-summaries",
      "this run emitted no reasoning summaries, so labelling was not exercised");
  } else {
    record("reasoning-blocks-are-labelled-model-summaries", labelled === reasoning,
      `${labelled}/${reasoning} carry the summary-of-its-own-thinking label`);
  }
  record("reasoning-stays-out-of-the-evidence-board", stray === 0,
    `${stray} reasoning block(s) rendered outside the chat panel`);

  const finalSteps = await steps();
  record("sequence-records-at-least-one-step", finalSteps >= 1, `${finalSteps} step card(s)`);
  const stepFrames = trace?.events.filter((event) => event === "sequence_step").length || 0;
  record("sequence-cards-arrive-incrementally", stepFrames === finalSteps && stepFrames > 0,
    `${stepFrames} individual sequence_step frames, ${finalSteps} cards`);

  let evidenceIndex = -1;
  for (let index = 0; index < finalSteps && evidenceIndex < 0; index += 1) {
    await page.locator(".sequence-step-toggle").nth(index).click();
    await page.waitForSelector(`[data-testid='sequence-evidence-${index}']`, { timeout: 10_000 })
      .catch(() => {});
    const open = await page.locator("[data-testid^='sequence-evidence-']").count();
    record(`only-the-chosen-step-expands-${index}`, open === 1, `${open} evidence panel(s) open`);
    if (await page.locator(`[data-testid='sequence-evidence-${index}'] .sequence-record`).count()) {
      evidenceIndex = index;
      break;
    }
    await page.locator(".sequence-step-toggle").nth(index).click();
  }
  if (evidenceIndex < 0) {
    record("sequence-step-shows-its-record-and-provenance", false,
      `no attached telemetry record in ${finalSteps} step(s)`);
  } else {
    const panel = `[data-testid='sequence-evidence-${evidenceIndex}']`;
    const fields = await page.locator(`${panel} .sequence-record-fields dt`).count();
    const provenance = await page.locator(`${panel} .sequence-provenance`).first().innerText().catch(() => "");
    record("sequence-step-shows-its-record-and-provenance",
      fields >= 1 && /Retrieved by/.test(provenance) && /Returned/.test(provenance),
      `${fields} record field(s); provenance ${JSON.stringify(provenance.replace(/\n/g, " | ").slice(0, 160))}`);
    await page.screenshot({ path: `${OUT}/sequence-step-open.png` });
    await page.locator(".sequence-step-toggle").nth(evidenceIndex).focus();
    await page.keyboard.press("Enter");
    await page.waitForSelector(panel, { state: "detached", timeout: 10_000 }).catch(() => {});
    record("sequence-step-collapses-from-the-keyboard",
      (await page.locator(panel).count()) === 0,
      "Enter on the focused step toggle closed its evidence panel");
  }

  const typeText = await page.locator("[data-testid='diagnosis-type']").innerText().catch(() => "");
  record("typed-diagnosis-lands-in-the-board", typeText.trim().length > 3,
    JSON.stringify(typeText.trim().split("\n")[0]));

  await page.locator(".diagnosis-inset .classification-toggle").first().click().catch(() => {});
  const citations = page.locator(".diagnosis-inset .citation-open");
  await citations.first().waitFor({ timeout: 10_000 }).catch(() => {});
  const citationCount = await citations.count();
  record("diagnosis-carries-at-least-one-mitre-citation", citationCount >= 1,
    `${citationCount} citation button(s)`);

  if (citationCount >= 1) {
    await citations.first().click();
    await page.waitForFunction(
      () => {
        const node = document.querySelector(".diagnosis-inset .citation-doc");
        return !!node && !node.classList.contains("loading");
      }, null, { timeout: 60_000 },
    ).catch(() => {});
    const docText = await page.locator(".diagnosis-inset .citation-doc").innerText().catch(() => "");
    const errored = await page.locator(".diagnosis-inset .citation-doc.error").count();
    record("citation-drill-through-opens-a-source-document",
      errored === 0 && docText.trim().length > 50,
      `${docText.trim().length} characters rendered, ${errored} error state(s)`);
    await page.screenshot({ path: `${OUT}/citation-open.png` });
    await citations.first().click();
    await page.waitForSelector(".diagnosis-inset .citation-doc", { state: "detached", timeout: 10_000 })
      .catch(() => {});
    record("citation-drill-through-closes-again",
      (await page.locator(".diagnosis-inset .citation-doc").count()) === 0,
      "document removed after a second activation");
  }

  await page.getByTestId("chat-tab-summary").click();
  await page.waitForFunction(
    () => (document.querySelector("[data-testid='summary-text']")?.textContent || "").length > 40,
    null, { timeout: 120_000 },
  ).catch(() => {});
  const summaryText = await page.locator("[data-testid='summary-text']").innerText().catch(() => "");
  record("summary-streams-into-its-own-tab", summaryText.trim().length > 40,
    `${summaryText.trim().length} characters`);
  const defenderHidden = await page.locator("#chat-panel-defender").isHidden();
  record("summary-tab-does-not-mix-with-chat", defenderHidden,
    `defender panel hidden while summary tab is active: ${defenderHidden}`);
  await page.screenshot({ path: `${OUT}/summary-tab.png` });

  await page.getByTestId("chat-tab-defender").click();
  await page.locator(".chat-input textarea").fill(
    "Search MITRE ATT&CK for T1087 account discovery and cite the path and commit.");
  await page.keyboard.press("Enter");
  await page.waitForSelector("#chat-panel-defender .message.user", { timeout: 60_000 }).catch(() => {});
  await page.waitForSelector(
    "#chat-panel-defender .message.agent:not(.investigation-entry) .tool-card",
    { timeout: RUN_MS }).catch(() => {});
  const chatClosed = await until(() => page.evaluate(
    () => window.__streamRuns.chat.some((run) => run.done)), RUN_MS);
  record("interactive-chat-stream-completes", chatClosed, "chat SSE done delivered to the reader");
  const chatTools = await page.locator(
    "#chat-panel-defender .message.agent:not(.investigation-entry) .tool-card b").allInnerTexts();
  record("main-chat-takes-an-independent-turn", chatTools.length > 0, JSON.stringify(chatTools));
  const investigationIntact = await page.locator("[data-testid='diagnosis-text']").innerText().catch(() => "");
  record("chat-turn-does-not-mix-into-the-investigation-entry",
    investigationIntact.trim() === diagnosisText.trim(),
    "the investigation entry still holds its own output after a chat turn");
  await page.screenshot({ path: `${OUT}/defender-tab-chat.png` });

  const composer = await box(page, ".chat-input textarea");
  record("composer-is-visible-on-the-chat-tab", !!composer && composer.height > 20,
    composer ? `${Math.round(composer.width)}x${Math.round(composer.height)}` : "absent");

  await page.getByRole("tab", { name: "Data & Tools Catalogue", exact: true }).click();
  await page.locator(".agent-branch > summary").click();
  const catalogue = await page.evaluate(async () => {
    const response = await fetch("/api/cyber/agents");
    if (!response.ok) throw new Error(`Agent catalogue HTTP ${response.status}`);
    return response.json();
  });
  const loadedTools = catalogue.agents.flatMap((agent) => agent.tools);
  record("explorer-shows-the-loaded-tool-registry",
    (await page.locator(".agent-tool-list button").count()) === loadedTools.length && loadedTools.length > 0,
    `${loadedTools.length} declared tools`);
  const linkedTool = loadedTools.find((tool) => tool.datasource_ids?.length && tool.source.available);
  record("explorer-has-a-source-linked-tool", Boolean(linkedTool), linkedTool?.id || "none");
  if (linkedTool) {
    await page.locator(`.agent-tool-list button[title="${linkedTool.id}"]`).click();
    await page.waitForFunction((ids) => document.querySelectorAll("[data-tool-dependency=true]").length === ids.length,
      linkedTool.datasource_ids, { timeout: 30_000 });
    const highlighted = await page.locator("[data-tool-dependency=true]").evaluateAll(
      (nodes) => nodes.map((node) => node.getAttribute("data-source-id")).sort());
    record("explorer-highlights-exact-dependencies",
      JSON.stringify(highlighted) === JSON.stringify([...linkedTool.datasource_ids].sort()), highlighted.join(", "));
    await page.locator(".rex-pane:not([hidden]) .scv[data-highlighted=true]").waitFor({ timeout: 30_000 });
    const rendered = await page.locator(".rex-pane:not([hidden]) .scv-line-content").allTextContents();
    record("explorer-renders-the-registered-source", rendered.join("\n") === linkedTool.source.code.replace(/\r\n|\r/g, "\n"),
      `${rendered.length} highlighted lines from ${linkedTool.source.path}`);
    await page.screenshot({ path: `${OUT}/explorer.png` });
  }
  await page.getByRole("tab", { name: "Investigation", exact: true }).click();

  const cards = page.locator(".situation-list article.situation .situation-head");
  if (!INITIAL_SELECTION_ONLY && await cards.count() > 1) {
    const before = sent.length;
    await cards.nth(1).click();
    const cleared = await until(
      async () => sent.length > before
        && (await page.locator("[data-testid='diagnosis-text']").count()) === 0, 60_000);
    record("selection-change-supersedes-the-previous-run", cleared,
      `${sent.length - before} new diagnose request(s); previous result cleared: ${cleared}`);
  } else {
    notObserved("selection-change-supersedes-the-previous-run",
      INITIAL_SELECTION_ONLY ? "second model-assisted selection excluded by the approved live request budget"
        : "only one situation in this window; nothing to switch to");
  }
  await page.screenshot({ path: `${OUT}/second-selection.png` });

  writeFileSync(`${OUT}/report.json`, JSON.stringify(
    { base: BASE, scenario: SCENARIO, signed, initialSelectionOnly: INITIAL_SELECTION_ONLY,
      finishedAt: new Date().toISOString(), findings },
    null, 2));
  await browser.close();
  const fails = findings.filter((item) => item.status === "fail");
  const skipped = findings.filter((item) => item.status === "not-observed");
  console.log(`\n   ${findings.length - fails.length - skipped.length}/${findings.length} checks passed, `
    + `${fails.length} failed, ${skipped.length} not observed`);
  for (const item of skipped) console.log(`   not observed: ${item.name} — ${item.detail}`);
  process.exit(fails.length ? 1 : 0);
}

main().catch((error) => { console.error(error); process.exit(1); });
