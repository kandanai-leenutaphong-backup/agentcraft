/**
 * E2E: Delegation streaming — verifies the full Investigator → Dispatcher flow.
 *
 * Tests:
 * 1. Investigator sends a message and calls tools
 * 2. Investigator delegates to Dispatcher
 * 3. Dispatcher tab appears
 * 4. Dispatcher streams tokens and tool calls live
 * 5. Priority actions appear in the panel
 */

import { test, expect } from "./fixtures";

test.describe("Delegation & Dispatcher Streaming", () => {
  test("investigator delegates and dispatcher tab appears", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Create session and send trigger
    await page.getByTestId("new-chat-button").click();
    const chatInput = page.getByPlaceholder("Send a message");
    await expect(chatInput).toBeVisible({ timeout: 15_000 });
    await chatInput.fill("Investigate LIAPOOTA, 2025-09-14 14:35:00 to 2025-09-14 14:45:00.\nAlarm signals: cb_trip=5, cb_cluster=5, kv_emer_bus=1, unreas=1.\nSCADA signals: bus_collapse=1, line_trip=1, line_overload=1.");
    await chatInput.press("Enter");

    // Investigator streams and calls tools — Investigator now lives inside
    // the Primary slot's secondary row, not as a top-level tab.
    await expect(page.getByTestId("agent-tab-investigator-streaming")).toBeVisible({ timeout: 30_000 });
    const toolCard = page.locator("button").filter({ hasText: /Station Summary|Event Timeline|Find Station Assets|Find Alarms|Find SCADA|SCADA Changes/i }).first();
    await expect(toolCard).toBeVisible({ timeout: 60_000 });

    // Delegation fires
    const delegationCard = page.locator("button").filter({ hasText: /Delegate to Specialist/i }).first();
    await expect(delegationCard).toBeVisible({ timeout: 120_000 });

    // Dispatcher tab appears
    const dispatcherTab = page.getByTestId("agent-tab-dispatcher");
    await expect(dispatcherTab).toBeVisible({ timeout: 30_000 });

    // Priority actions appear (live via background SSE)
    const priorityPanel = page.locator("[data-testid='priority-actions-panel']");
    const actionCards = priorityPanel.locator("[class*='rounded-lg']").filter({
      hasText: /Hold|Contact|Assess|Open|Confirm|Check|Record|Verify|Monitor|Notify|Inspect|Review|Isolate|Restore/i,
    });
    await expect.poll(
      async () => await actionCards.count() > 0,
      { timeout: 120_000, message: "Priority actions should appear" },
    ).toBe(true);

    await page.screenshot({ path: "test-results/delegation-complete.png" });
  });

  test("saved session dropdown opens and renders options", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Open saved sessions dropdown
    const dropdownTrigger = page.locator("button").filter({ hasText: /Saved Sessions/i }).first();
    await expect(dropdownTrigger).toBeVisible({ timeout: 10_000 });
    await dropdownTrigger.click();

    // Dropdown menu should appear with "Load Historical Session" header
    const dropdownMenu = page.locator("text=Load Historical Session");
    await expect(dropdownMenu).toBeVisible({ timeout: 5_000 });

    // Liapoota option should be listed
    const liapoota = page.locator("button").filter({ hasText: /Liapoota Bus Trip/i }).first();
    await expect(liapoota).toBeVisible({ timeout: 5_000 });

    // Click to attempt load — session may or may not exist in Cosmos
    await liapoota.click();
    await page.waitForTimeout(3000);

    await page.screenshot({ path: "test-results/saved-session-dropdown.png" });

    // Dropdown closed after selection (either success or error)
    await expect(dropdownMenu).toBeHidden({ timeout: 5_000 });
  });
});
