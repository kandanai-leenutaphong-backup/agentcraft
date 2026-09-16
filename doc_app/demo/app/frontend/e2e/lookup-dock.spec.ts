/**
 * Data Search (center tab) E2E — verifies the Data Search dock content
 * hosted as a tab in the center column.
 *
 * Migrated 2026-04-17: the Data Search dock was moved from a bottom
 * resizable panel into the center column as a third tab alongside
 * Priorities and Topology. The header button (testid `lookup-dock-toggle`)
 * now toggles between the data tab and the priorities tab; the dock body
 * itself still carries testid `lookup-dock`.
 *
 * Tests:
 *   1. Header button activates the Data tab and reveals the dock body
 *   2. A data_search query renders a tabular tool-call result inside the tab
 *   3. Toggling again returns the user to the priorities tab
 *   4. Main chat still works while the data tab is active
 */

import { test, expect } from "./fixtures";

test.describe("Data Search (center tab)", () => {
  test("data search query returns tabular results", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // ── Activate the Data Search tab via the header button ───────────
    const dockToggle = page.getByTestId("lookup-dock-toggle");
    await expect(dockToggle).toBeVisible({ timeout: 10_000 });
    await dockToggle.click();

    // The Data tab body (containing the dock) should be visible
    const dataTabBody = page.getByTestId("center-tab-body-data");
    await expect(dataTabBody).toBeVisible({ timeout: 5_000 });

    // The dock content still carries the legacy testid for back-compat
    const dock = page.getByTestId("lookup-dock");
    await expect(dock).toBeVisible({ timeout: 5_000 });

    // ── Send a data search query ─────────────────────────────────────
    const dockInput = dock.getByPlaceholder("Search data...");
    await expect(dockInput).toBeVisible({ timeout: 5_000 });
    await dockInput.fill("LIAPOOTA");
    await dockInput.press("Enter");

    // Should see a tool call card (Find Station Assets / Find Alarms / Query Data)
    const toolCard = dock.locator("button").filter({ hasText: /Find Station Assets|Find Alarms|Query Data/i }).first();
    await expect(toolCard).toBeVisible({ timeout: 60_000 });

    // Expand the tool card to see the table
    await toolCard.click();
    await page.waitForTimeout(500);

    // Tabular results should render inside the expanded card
    const table = dock.locator("table").first();
    await expect(table).toBeVisible({ timeout: 10_000 });

    await page.screenshot({ path: "test-results/lookup-dock-data-search.png" });
  });

  test("toggle switches between data and priorities tabs", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    const dockToggle = page.getByTestId("lookup-dock-toggle");
    const dock = page.getByTestId("lookup-dock");
    const prioritiesBody = page.getByTestId("center-tab-body-priorities");

    // Starts on priorities by default
    await expect(prioritiesBody).toBeVisible({ timeout: 5_000 });

    // Click -> activate Data tab
    await dockToggle.click();
    await expect(dock).toBeVisible({ timeout: 5_000 });
    await expect(prioritiesBody).toBeHidden();

    // Click again -> back to priorities
    await dockToggle.click();
    await expect(prioritiesBody).toBeVisible({ timeout: 5_000 });
    await expect(dock).toBeHidden();

    // Click once more -> Data tab again
    await dockToggle.click();
    await expect(dock).toBeVisible({ timeout: 5_000 });
  });

  test("main chat works while data tab is active", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Activate Data tab
    const dockToggle = page.getByTestId("lookup-dock-toggle");
    await dockToggle.click();
    await expect(page.getByTestId("lookup-dock")).toBeVisible({ timeout: 5_000 });

    // Main chat still works — create session
    await page.getByTestId("new-chat-button").click();
    const chatInput = page.getByPlaceholder("Send a message");
    await expect(chatInput).toBeVisible({ timeout: 15_000 });

    // Grid Captain tab should be visible — it is the operator's entry
    // point and the only top-level chat tab guaranteed to exist before
    // any delegation has fired.
    const gridCaptainTab = page.getByTestId("agent-tab-investigator");
    await expect(gridCaptainTab).toBeVisible({ timeout: 10_000 });

    await page.screenshot({ path: "test-results/lookup-dock-with-chat.png" });
  });
});
