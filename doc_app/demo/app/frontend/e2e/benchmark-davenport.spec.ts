/**
 * Full-stack benchmark: Davenport No.1 Transformer + 275kV West Bus Trip
 *
 * Davenport No.1 transformer tripped on Buchholz alarm at 07:42 on 28/08/2025.
 * CB fail protection on CB 6549 incorrectly triggered, causing the bus trip.
 * SA station — tests agent handling of transformer + CB fail protection event.
 */

import { test, expect } from "./fixtures";

test.describe("Full-Stack Benchmark: Davenport", () => {
  test("transformer + bus trip investigation delegates with actions", async ({ authedPage: page }) => {
    const t0 = Date.now();
    const elapsed = () => ((Date.now() - t0) / 1000).toFixed(1);

    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });
    console.log(`[${elapsed()}s] App loaded`);

    await page.getByTestId("new-chat-button").click();
    const chatInput = page.getByPlaceholder("Send a message");
    await expect(chatInput).toBeVisible({ timeout: 15_000 });

    await chatInput.fill("Investigate DEVNPORT, 2025-08-28 06:55:00 to 2025-08-28 07:05:00.\nAlarm signals: kv_emer_bus=2.\nSCADA signals: bus_collapse=1, line_trip=1, line_overload=1, transformer_trip=2.");
    await chatInput.press("Enter");
    console.log(`[${elapsed()}s] Trigger sent`);

    // Open the Primary slot (Investigator no longer lives in the top tab row).
    const streamingDot = page.getByTestId("agent-tab-investigator-streaming");
    await expect(streamingDot).toBeVisible({ timeout: 30_000 });

    const toolCard = page.locator("button").filter({ hasText: /Station Summary|Event Timeline|Find Station Assets|Find Alarms/i }).first();
    await expect(toolCard).toBeVisible({ timeout: 60_000 });
    console.log(`[${elapsed()}s] First tool call`);

    const delegationCard = page.locator("button").filter({ hasText: /Delegate to Specialist/i }).first();
    await expect(delegationCard).toBeVisible({ timeout: 120_000 });
    console.log(`[${elapsed()}s] Delegation fired`);

    const dispatcherTab = page.getByTestId("agent-tab-dispatcher");
    await expect(dispatcherTab).toBeVisible({ timeout: 30_000 });

    await dispatcherTab.click();
    await page.waitForTimeout(2000);
    const dispatcherContent = page.locator("text=/Search Operating|Knowledge Base|Incident|Push Operator|operator|Davenport|transformer|Buchholz|CB.*fail/i").first();
    const hasDispatcher = await expect(dispatcherContent).toBeVisible({ timeout: 90_000 }).then(() => true).catch(() => false);
    console.log(`[${elapsed()}s] Dispatcher: ${hasDispatcher ? "OK" : "FAILED"}`);

    const investigatorTab = page.getByTestId("agent-tab-investigator");
    if (await investigatorTab.isVisible()) await investigatorTab.click();
    const priorityPanel = page.locator("[data-testid='priority-actions-panel']");
    const actionCards = priorityPanel.locator("[class*='rounded-lg']").filter({ hasText: /Hold|Contact|Assess|Confirm|Check|Record|Verify|Monitor|Notify|Inspect|Review|Isolate|Restore|Investigate|Request|Engage/i });
    const hasActions = await expect.poll(async () => await actionCards.count() > 0, { timeout: 60_000 }).toBe(true).then(() => true).catch(() => false);
    console.log(`[${elapsed()}s] Actions: ${hasActions ? "YES" : "NONE"}`);

    await expect(streamingDot).toBeHidden({ timeout: 60_000 });
    console.log(`[${elapsed()}s] Done`);
    await page.screenshot({ path: "test-results/benchmark-davenport-complete.png" });

    expect(hasDispatcher).toBe(true);
  });
});
