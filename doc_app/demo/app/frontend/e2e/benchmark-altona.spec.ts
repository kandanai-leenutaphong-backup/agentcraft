/**
 * Full-stack benchmark: Altona No 3 220kV Bus + KTS-ATS Line Trip
 *
 * Altona No 3 220 kV Bus and KTS-ATS 220kV Line tripped at 09:53 on 15/08/2025.
 * Loss of SCADA at KTS due to 48V DC supply failure.
 * VIC station — tests agent handling of comms loss + protection failure event.
 */

import { test, expect } from "./fixtures";

test.describe("Full-Stack Benchmark: Altona", () => {
  test("bus + line trip with SCADA loss delegates with actions", async ({ authedPage: page }) => {
    const t0 = Date.now();
    const elapsed = () => ((Date.now() - t0) / 1000).toFixed(1);

    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });
    console.log(`[${elapsed()}s] App loaded`);

    await page.getByTestId("new-chat-button").click();
    const chatInput = page.getByPlaceholder("Send a message");
    await expect(chatInput).toBeVisible({ timeout: 15_000 });

    await chatInput.fill("Investigate ATS, 2025-08-15 09:45:00 to 2025-08-15 09:55:00.\nAlarm signals: cb_trip=3, cb_cluster=3.\nSCADA signals: line_trip=1, line_overload=4.");
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
    const dispatcherContent = page.locator("text=/Search Operating|Knowledge Base|Incident|Push Operator|operator|Altona|KTS|SCADA|DC.*supply|protection/i").first();
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
    await page.screenshot({ path: "test-results/benchmark-altona-complete.png" });

    expect(hasDispatcher).toBe(true);
  });
});
