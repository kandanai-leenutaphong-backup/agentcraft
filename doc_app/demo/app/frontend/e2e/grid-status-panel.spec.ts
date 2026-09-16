/**
 * Grid Status Panel — E2E tests for the NEM dashboard.
 *
 * Validates R6: NEM summary, situation metrics, regional breakdown,
 * MW threatened indicator after a live situation scan.
 */

import { test, expect } from "./fixtures";

test.describe("Grid Status Panel", () => {

  test("grid status panel shows NEM dashboard after scan", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Trigger live scan via Scan Scenarios
    const savedBtn = page.locator("button", { hasText: /Saved Sessions/i });
    await savedBtn.click();
    const scanEntry = page.locator("[data-testid='scan-scenario-button']").first();
    await expect(scanEntry).toBeVisible({ timeout: 5_000 });
    await scanEntry.click();

    // Wait for situation alerts to populate (scan can take 10-20s)
    const sitPanel = page.getByTestId("situation-alerts-panel");
    await expect(sitPanel.locator("button").first()).toBeVisible({ timeout: 60_000 });

    // NEM Summary
    const nemSummary = page.locator("[data-testid='nem-summary']");
    await expect(nemSummary).toBeVisible({ timeout: 10_000 });
    const nemText = await nemSummary.textContent();
    expect(nemText).toContain("MW");
    expect(nemText).toContain("NEM");

    // Situation Summary
    const sitSummary = page.locator("[data-testid='situation-summary']");
    await expect(sitSummary).toBeVisible({ timeout: 5_000 });
    const sitText = await sitSummary.textContent();
    expect(sitText).toContain("Situations");
    expect(sitText).toContain("Stations");

    // Regional Breakdown
    const regionalBreakdown = page.locator("[data-testid='regional-breakdown']");
    await expect(regionalBreakdown).toBeVisible({ timeout: 5_000 });
    const regionText = await regionalBreakdown.textContent();
    expect(regionText).toMatch(/TAS|NSW|VIC|SA|QLD/);

    // MW Threatened (soft — may be 0 if no MW loss situations)
    const mwThreatened = page.locator("[data-testid='mw-threatened']");
    const hasThreatened = await mwThreatened.isVisible().catch(() => false);
    if (hasThreatened) {
      const threatText = await mwThreatened.textContent();
      expect(threatText).toContain("MW");
      expect(threatText).toContain("%");
    }

    // Severity distribution bar still renders
    await expect(page.locator("text=/MAJOR|SERIOUS|INVESTIGATE|CRITICAL/i").first()).toBeVisible({ timeout: 5_000 });
  });

  test("grid status shows empty state when no scan run", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Disable placeholders if on
    const phToggle = page.getByTestId("placeholder-toggle");
    const phText = await phToggle.textContent();
    if (phText?.includes("ON")) {
      await phToggle.click();
    }

    // Clear session to reset state
    const clearBtn = page.getByTestId("clear-session-button");
    if (await clearBtn.isVisible()) {
      await clearBtn.click();
    }

    // Grid status should show "Run a scan"
    await expect(page.locator("text=Run a scan to assess")).toBeVisible({ timeout: 5_000 });
  });

  test("threat breakdown shows station rows with MW and percentages", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Trigger live scan
    const savedBtn = page.locator("button", { hasText: /Saved Sessions/i });
    await savedBtn.click();
    const scanEntry = page.locator("[data-testid='scan-scenario-button']").first();
    await expect(scanEntry).toBeVisible({ timeout: 5_000 });
    await scanEntry.click();

    // Wait for situations
    const sitPanel = page.getByTestId("situation-alerts-panel");
    await expect(sitPanel.locator("button").first()).toBeVisible({ timeout: 30_000 });

    // Threat Breakdown section should exist
    const breakdown = page.locator("[data-testid='threat-breakdown']");
    await expect(breakdown).toBeVisible({ timeout: 10_000 });

    // Expand it
    await breakdown.locator("button").first().click();

    // Station rows should appear
    const stationRows = page.locator("[data-testid='threat-station-row']");
    await expect(stationRows.first()).toBeVisible({ timeout: 5_000 });
    const stationText = await stationRows.first().textContent();
    expect(stationText).toContain("MW");
    expect(stationText).toContain("%");

    // Expand a station to see equipment rows
    await stationRows.first().click();
    const equipRows = page.locator("[data-testid='threat-equipment-row']");
    const hasEquip = await equipRows.first().isVisible().catch(() => false);
    if (hasEquip) {
      const equipText = await equipRows.first().textContent();
      expect(equipText).toContain("MW");
      expect(equipText).toContain("%");
      // Equipment tag should have dots (e.g. LIAPOOTA.GEN.3.MW)
      expect(equipText).toContain(".");
    }
  });
});
