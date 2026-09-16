/**
 * E2E: Tool-call argument streaming — verifies real-time argument
 * rendering end-to-end.
 *
 * Strategy:
 *   The Foundry Agents service often completes tool calls in <200 ms,
 *   so polling from the test is too slow to catch the running window.
 *   Instead we install a MutationObserver in the page BEFORE submitting
 *   the prompt; the observer records distinct ``textContent`` snapshots
 *   of any node matching ``[data-testid='tool-args-raw']`` (real DELTA
 *   path) or ``[data-testid='tool-args-typewriter']`` (atomic-args
 *   fallback) as they appear and grow. After the stream finishes we
 *   read the recorded samples and require ≥ 2 distinct lengths.
 */

import { test, expect } from "./fixtures";

test.describe("Tool-call argument streaming", () => {
  test("renders progressive argument growth in the UI", async ({ authedPage: page }) => {
    test.setTimeout(180_000);

    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    await page.getByTestId("new-chat-button").click();
    const chatInput = page.getByPlaceholder("Send a message");
    await expect(chatInput).toBeVisible({ timeout: 15_000 });

    // Install the mutation-observing collector on the page side. It
    // accumulates into ``window.__argSamples`` until the test reads it.
    await page.evaluate(() => {
      // Module-scoped collector lives on window so subsequent evaluate
      // calls can read it back. Each entry is the textContent of one
      // matching node at one observation tick; later snapshots may
      // share a node but have a longer textContent.
      (window as unknown as { __argSamples: string[] }).__argSamples = [];
      const samples = (window as unknown as { __argSamples: string[] }).__argSamples;
      const harvest = () => {
        const nodes = document.querySelectorAll(
          '[data-testid="tool-args-raw"],[data-testid="tool-args-typewriter"]',
        );
        nodes.forEach((node) => {
          const value = (node.textContent ?? "").trim();
          if (value && samples[samples.length - 1] !== value) {
            samples.push(value);
          }
        });
      };
      // Initial sweep in case nodes already exist (defensive — should
      // not on a fresh chat).
      harvest();
      // Watch the entire body so dynamic mounts are caught wherever
      // they land in the chat tree.
      new MutationObserver(harvest).observe(document.body, {
        childList: true,
        subtree: true,
        characterData: true,
      });
    });

    await chatInput.fill(
      "Investigate LIAPOOTA, 2025-09-14 14:35:00 to 2025-09-14 14:45:00.\nAlarm signals: cb_trip=5.",
    );
    await chatInput.press("Enter");

    // Let the stream run long enough to produce at least one tool
    // card lifecycle. We do not block on a specific selector here —
    // the observer captures the brief running window for us.
    await page.waitForTimeout(60_000);

    const samples = await page.evaluate(
      () => (window as unknown as { __argSamples: string[] }).__argSamples,
    );

    expect(
      samples.length,
      `expected non-empty samples; got ${samples.length}`,
    ).toBeGreaterThan(0);

    const distinctLengths = new Set(samples.map((s) => s.length));
    expect(
      distinctLengths.size,
      `expected progressive growth, samples=${JSON.stringify(samples.map((s) => s.length))}`,
    ).toBeGreaterThan(1);
  });
});
