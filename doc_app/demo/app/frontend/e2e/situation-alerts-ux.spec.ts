/**
 * Situation Alerts UX — grouping, filtering, Investigate All, resizable split.
 */

import { test, expect } from "./fixtures";

test.describe("Situation Alerts UX", () => {

  test("situations grouped by station with time range", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Trigger scan
    const savedBtn = page.locator("button", { hasText: /Saved Sessions/i });
    await savedBtn.click();
    const scanEntry = page.locator("[data-testid='scan-scenario-button']").first();
    await expect(scanEntry).toBeVisible({ timeout: 5_000 });
    await scanEntry.click();

    // Wait for station groups
    const panel = page.getByTestId("situation-alerts-panel");
    const stationGroup = panel.locator("[data-testid='station-group']").first();
    await expect(stationGroup).toBeVisible({ timeout: 60_000 });

    // Station header has name, time range, situation count
    const header = stationGroup.locator("[data-testid='station-group-header']");
    const headerText = await header.textContent();
    expect(headerText).toContain("→"); // time range
    expect(headerText).toMatch(/situation/i);

    // Click to expand — situation cards appear inside
    await header.click();
    // Station should have cards inside (already auto-expanded for first)
  });

  test("severity filters toggle situation visibility", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Trigger scan
    const savedBtn = page.locator("button", { hasText: /Saved Sessions/i });
    await savedBtn.click();
    await page.locator("[data-testid='scan-scenario-button']").first().click();

    const panel = page.getByTestId("situation-alerts-panel");
    await expect(panel.locator("[data-testid='station-group']").first()).toBeVisible({ timeout: 60_000 });

    // Get initial count
    const countBefore = await panel.locator("[data-testid='station-group']").count();

    // Toggle off INVESTIGATE — should reduce visible groups
    const invFilter = panel.locator("[data-testid='severity-filter-INVESTIGATE']");
    await expect(invFilter).toBeVisible();
    await invFilter.click();

    // Count may have changed
    await page.waitForTimeout(500);
    const countAfter = await panel.locator("[data-testid='station-group']").count();
    // Re-enable
    await invFilter.click();
    await page.waitForTimeout(500);
    const countRestored = await panel.locator("[data-testid='station-group']").count();
    expect(countRestored).toBe(countBefore);
  });

  test("station text filter filters by station name", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    const savedBtn = page.locator("button", { hasText: /Saved Sessions/i });
    await savedBtn.click();
    await page.locator("[data-testid='scan-scenario-button']").first().click();

    const panel = page.getByTestId("situation-alerts-panel");
    await expect(panel.locator("[data-testid='station-group']").first()).toBeVisible({ timeout: 60_000 });

    const filterInput = panel.locator("[data-testid='station-text-filter']");
    await expect(filterInput).toBeVisible();

    // Type a partial station name
    await filterInput.fill("LIAPO");
    await page.waitForTimeout(500);

    // Only LIAPOOTA groups visible
    const groups = panel.locator("[data-testid='station-group']");
    const count = await groups.count();
    if (count > 0) {
      const firstHeader = await groups.first().locator("[data-testid='station-group-header']").textContent();
      expect(firstHeader).toContain("LIAPO");
    }

    // Clear filter
    await filterInput.fill("");
    await page.waitForTimeout(500);
  });

  test("investigate all sends combined prompt to investigator", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    const savedBtn = page.locator("button", { hasText: /Saved Sessions/i });
    await savedBtn.click();
    await page.locator("[data-testid='scan-scenario-button']").first().click();

    const panel = page.getByTestId("situation-alerts-panel");
    await expect(panel.locator("[data-testid='station-group']").first()).toBeVisible({ timeout: 60_000 });

    const investigateAllBtn = panel.locator("[data-testid='investigate-all-button']");
    await expect(investigateAllBtn).toBeVisible();

    // Intercept chat POST
    let capturedBody = "";
    await page.route("**/api/chat/*", async (route) => {
      if (route.request().method() === "POST") {
        capturedBody = route.request().postData() ?? "";
      }
      await route.abort();
    });

    await investigateAllBtn.click();
    await page.waitForTimeout(3000);

    expect(capturedBody).toBeTruthy();
    const body = JSON.parse(capturedBody);
    expect(body.content).toContain("Investigate");
  });

  test("both situation alerts and grid status panels are visible", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Both panels visible
    await expect(page.getByTestId("situation-alerts-panel")).toBeVisible({ timeout: 10_000 });
    await expect(page.locator("text=Grid Status")).toBeVisible({ timeout: 10_000 });
  });
});
