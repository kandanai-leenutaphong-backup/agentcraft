/**
 * Situation Detector E2E — verifies the scan → display → investigate pipeline.
 *
 * Tests:
 *   1. Control bar renders with defaults, Scan button visible
 *   2. Click Scan → situations load → LIAPOOTA card visible
 *   3. Expand LIAPOOTA → Investigate button + signal breakdowns visible
 *   4. Click Investigate → new chat session → Investigator starts streaming
 */

import { test, expect } from "./fixtures";

test.describe("Situation Detector", () => {
  test("scan loads situations and LIAPOOTA card appears", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Control bar should render with defaults
    const controlBar = page.getByTestId("situation-control-bar");
    await expect(controlBar).toBeVisible({ timeout: 10_000 });

    // Scan button should be visible
    const scanButton = page.getByTestId("situation-scan-button");
    await expect(scanButton).toBeVisible();

    // Click Scan
    await scanButton.click();

    // Wait for situations to load — LIAPOOTA MAJOR should appear
    const liapootaCard = page.locator("text=LIAPOOTA").first();
    await expect(liapootaCard).toBeVisible({ timeout: 30_000 });

    // Severity badge should show MAJOR
    const majorBadge = page.locator("text=MAJOR").first();
    await expect(majorBadge).toBeVisible({ timeout: 5_000 });

    await page.screenshot({ path: "test-results/situation-detector-scan.png" });
  });

  test("expand LIAPOOTA card shows signals and Investigate button", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Scan
    await page.getByTestId("situation-scan-button").click();
    const stationGroup = page.locator("text=LIAPOOTA").first();
    await expect(stationGroup).toBeVisible({ timeout: 30_000 });

    // Click station group header to reveal child situation cards
    await stationGroup.click();

    // Click the first individual situation card (MAJOR) to expand its details
    const situationCard = page.locator("[data-testid='station-group']").filter({ hasText: "LIAPOOTA" }).locator("button").filter({ hasText: /MAJOR|SERIOUS|CRITICAL/ }).first();
    await expect(situationCard).toBeVisible({ timeout: 5_000 });
    await situationCard.click();

    // Should see signal breakdowns inside the expanded card
    const alarmSignals = page.locator("text=Alarm Signals").first();
    await expect(alarmSignals).toBeVisible({ timeout: 5_000 });

    // Investigate button should be visible inside the expanded card
    const investigateBtn = page.getByTestId("investigate-LIAPOOTA");
    await expect(investigateBtn).toBeVisible({ timeout: 5_000 });

    await page.screenshot({ path: "test-results/situation-detector-expanded.png" });
  });

  test("Investigate button triggers full investigation pipeline", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Scan + expand station group + expand individual card + click Investigate
    await page.getByTestId("situation-scan-button").click();
    const stationGroup = page.locator("text=LIAPOOTA").first();
    await expect(stationGroup).toBeVisible({ timeout: 30_000 });
    await stationGroup.click();

    // Expand the first situation card inside the station group
    const situationCard = page.locator("[data-testid='station-group']").filter({ hasText: "LIAPOOTA" }).locator("button").filter({ hasText: /MAJOR|SERIOUS|CRITICAL/ }).first();
    await expect(situationCard).toBeVisible({ timeout: 5_000 });
    await situationCard.click();

    const investigateBtn = page.getByTestId("investigate-LIAPOOTA");
    await expect(investigateBtn).toBeVisible({ timeout: 5_000 });
    await investigateBtn.click();

    // Should see Investigator streaming
    // Open the Primary slot (Investigator no longer lives in the top tab row).
    const streamingDot = page.getByTestId("agent-tab-investigator-streaming");
    await expect(streamingDot).toBeVisible({ timeout: 30_000 });

    // Should see tool calls (confirms the investigate prompt triggered the Investigator)
    const toolCard = page.locator("button").filter({ hasText: /Station Summary|Event Timeline|Find Station Assets|Find Alarms|Search Investigati/i }).first();
    await expect(toolCard).toBeVisible({ timeout: 60_000 });

    // Delegation is tested in the canonical benchmark — just confirm the agent started
    await page.screenshot({ path: "test-results/situation-detector-investigate.png" });
  });
});
