/**
 * Full-stack benchmark: Kempsey-Macksville/Raleigh 132kV Lines Trip (Data Gap)
 *
 * Kempsey-Macksville 9W5 and Kempsey-Raleigh 9W2 132kV lines tripped and
 * auto-reclosed at 16:47 on 02/09/2025. Lightning suspected.
 * Kempsey is an NSW station — NOT in Watcher tables (TAS region only).
 * Tests the agent's ability to handle missing data and still produce
 * actionable operator guidance from the incident description alone.
 */

import { test, expect } from "./fixtures";

test.describe("Full-Stack Benchmark: Kempsey (Data Gap)", () => {
  test("investigation with no operational data still delegates", async ({ authedPage: page }) => {
    const t0 = Date.now();
    const elapsed = () => ((Date.now() - t0) / 1000).toFixed(1);

    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });
    console.log(`[${elapsed()}s] App loaded`);

    // ── Phase 1: Send trigger ───────────────────────────────────────
    await page.getByTestId("new-chat-button").click();
    const chatInput = page.getByPlaceholder("Send a message");
    await expect(chatInput).toBeVisible({ timeout: 15_000 });

    await chatInput.fill("Investigate KEMPSEY, 2025-09-02 16:40:00 to 2025-09-02 17:00:00.\nKempsey - Macksville 9W5 132 kV line and Kempsey - Raleigh 9W2 132 kV line tripped and auto reclosed at 16:47 on 02/09/2025.\nLightning suspected but unconfirmed. No load shedding, no generation lost.\nNon-credible contingency — reclassified as credible until further notice.");
    await chatInput.press("Enter");
    console.log(`[${elapsed()}s] Trigger sent`);

    // ── Phase 2: Investigator streams ───────────────────────────────
    // Open the Primary slot (Investigator no longer lives in the top tab row).
    const investigatorStreamingDot = page.getByTestId("agent-tab-investigator-streaming");
    await expect(investigatorStreamingDot).toBeVisible({ timeout: 30_000 });
    console.log(`[${elapsed()}s] Investigator streaming`);

    // ── Phase 3: Tool calls render ──────────────────────────────────
    const toolCallCard = page.locator("button").filter({ hasText: /Station Summary|Event Timeline|Find Station Assets|Find Alarms/i }).first();
    await expect(toolCallCard).toBeVisible({ timeout: 60_000 });
    console.log(`[${elapsed()}s] First tool call visible`);

    // ── Phase 4: Delegation fires ───────────────────────────────────
    const delegationCard = page.locator("button").filter({ hasText: /Delegate to Specialist/i }).first();
    await expect(delegationCard).toBeVisible({ timeout: 120_000 });
    console.log(`[${elapsed()}s] Delegation fired`);

    // ── Phase 5: Dispatcher tab appears ─────────────────────────────
    const dispatcherTab = page.getByTestId("agent-tab-dispatcher");
    await expect(dispatcherTab).toBeVisible({ timeout: 30_000 });
    console.log(`[${elapsed()}s] Dispatcher tab visible`);

    // ── Phase 6: Dispatcher streams ─────────────────────────────────
    await dispatcherTab.click();
    await page.waitForTimeout(2000);
    const dispatcherContent = page.locator("text=/Search Operating|Knowledge Base|Incident|Push Operator|operator|investigation|findings|Kempsey|Macksville|Raleigh|lightning|line|data|unavailable/i").first();
    const hasDispatcher = await expect(dispatcherContent)
      .toBeVisible({ timeout: 90_000 })
      .then(() => true).catch(() => false);
    console.log(`[${elapsed()}s] Dispatcher content: ${hasDispatcher ? "VISIBLE" : "NOT VISIBLE"}`);

    // ── Phase 7: Priority actions (soft — may be advisory) ──────────
    const investigatorTab = page.getByTestId("agent-tab-investigator");
    if (await investigatorTab.isVisible()) await investigatorTab.click();

    const priorityPanel = page.locator("[data-testid='priority-actions-panel']");
    const actionCards = priorityPanel.locator("[class*='rounded-lg']").filter({ hasText: /Hold|Contact|Assess|Open|Confirm|Check|Record|Verify|Monitor|Notify|Inspect|Review|Isolate|Restore|Investigate|Request|Engage|Reclassif/i });
    const hasActions = await expect.poll(
      async () => await actionCards.count() > 0,
      { timeout: 60_000 },
    ).toBe(true).then(() => true).catch(() => false);
    console.log(`[${elapsed()}s] Priority actions: ${hasActions ? "YES" : "NONE (soft)"}`);

    // ── Phase 8: Complete ───────────────────────────────────────────
    await expect(investigatorStreamingDot).toBeHidden({ timeout: 60_000 });
    console.log(`[${elapsed()}s] Investigation done`);

    await page.screenshot({ path: "test-results/benchmark-kempsey-complete.png" });

    console.log("\n  FULL-STACK BENCHMARK: Kempsey (Data Gap)");
    console.log(`  Dispatcher: ${hasDispatcher ? "OK" : "FAILED"}`);
    console.log(`  Actions: ${hasActions ? "YES" : "NONE (advisory)"}\n`);

    // HARD requirements
    expect(hasDispatcher).toBe(true);
  });
});
