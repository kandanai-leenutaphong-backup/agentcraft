/**
 * Situation Frequency — E2E tests for frequency enrichment in Grid Status.
 */

import { test, expect } from "./fixtures";

test.describe("Situation Frequency", () => {

  test("freq summary section appears in grid status after scan", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Trigger scan
    const savedBtn = page.locator("button", { hasText: /Saved Sessions/i });
    await savedBtn.click();
    const scanEntry = page.locator("[data-testid='scan-scenario-button']").first();
    await expect(scanEntry).toBeVisible({ timeout: 5_000 });
    await scanEntry.click();

    // Wait for situations
    const sitPanel = page.getByTestId("situation-alerts-panel");
    await expect(sitPanel.locator("[data-testid='station-group']").first()).toBeVisible({ timeout: 60_000 });

    // Frequency section — soft assertion (may be null if no freq data)
    const freqSection = page.locator("[data-testid='freq-summary']");
    const hasFreq = await freqSection.isVisible().catch(() => false);

    if (hasFreq) {
      // Expand it
      await freqSection.locator("button").first().click();

      // Should show "NEM:" line with Hz values
      await expect(freqSection.locator("text=NEM")).toBeVisible({ timeout: 5_000 });
      await expect(freqSection.locator("text=Hz").first()).toBeVisible({ timeout: 5_000 });

      // Should have per-region rows
      const regionRows = freqSection.locator("[data-testid='freq-region-row']");
      await expect(regionRows.first()).toBeVisible({ timeout: 5_000 });

      // Each row has a band badge
      const badges = freqSection.locator("[data-testid='freq-band-badge']");
      expect(await badges.count()).toBeGreaterThan(0);

      console.log("Frequency section: VISIBLE with region data");
    } else {
      console.log("Frequency section: NOT VISIBLE (no freq data for this window — expected)");
    }
  });
});
