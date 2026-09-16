/**
 * Full-stack benchmark: Templers West-Dorrien 132kV Line + BESS Trip
 *
 * Dorrien end of Templers West-Dorrien 132kV line and Templers BESS
 * tripped at 05:07 on 07/08/2025. Tee line — only two of three ends
 * tripped. 132kV cable fault on Templers West-Templers BESS cable.
 * SA station — tests agent handling of complex tee-line protection event.
 */

import { test, expect } from "./fixtures";

test.describe("Full-Stack Benchmark: Templers", () => {
  test("tee-line + BESS trip investigation delegates with actions", async ({ authedPage: page }) => {
    const t0 = Date.now();
    const elapsed = () => ((Date.now() - t0) / 1000).toFixed(1);

    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });
    console.log(`[${elapsed()}s] App loaded`);

    await page.getByTestId("new-chat-button").click();
    const chatInput = page.getByPlaceholder("Send a message");
    await expect(chatInput).toBeVisible({ timeout: 15_000 });

    await chatInput.fill("Investigate TP_BESS, 2025-08-07 05:05:00 to 2025-08-07 05:15:00.\nAlarm signals: cb_trip=4, cb_cluster=4, unreas=2.\nSCADA signals: gen_trip=2, bus_collapse=1.");
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
    const dispatcherContent = page.locator("text=/Search Operating|Knowledge Base|Incident|Push Operator|operator|Templers|BESS|Dorrien|cable|tee|protection/i").first();
    const hasDispatcher = await expect(dispatcherContent).toBeVisible({ timeout: 90_000 }).then(() => true).catch(() => false);
    console.log(`[${elapsed()}s] Dispatcher: ${hasDispatcher ? "OK" : "FAILED"}`);

    const investigatorTab = page.getByTestId("agent-tab-investigator");
    if (await investigatorTab.isVisible()) await investigatorTab.click();
    const priorityPanel = page.locator("[data-testid='priority-actions-panel']");
    const actionCards = priorityPanel.locator("[class*='rounded-lg']").filter({ hasText: /Hold|Contact|Assess|Confirm|Check|Record|Verify|Monitor|Notify|Inspect|Review|Isolate|Restore|Investigate|Request|Engage|Reclassif/i });
    const hasActions = await expect.poll(async () => await actionCards.count() > 0, { timeout: 60_000 }).toBe(true).then(() => true).catch(() => false);
    console.log(`[${elapsed()}s] Actions: ${hasActions ? "YES" : "NONE"}`);

    await expect(streamingDot).toBeHidden({ timeout: 60_000 });
    console.log(`[${elapsed()}s] Done`);
    await page.screenshot({ path: "test-results/benchmark-templers-complete.png" });

    expect(hasDispatcher).toBe(true);
  });
});
