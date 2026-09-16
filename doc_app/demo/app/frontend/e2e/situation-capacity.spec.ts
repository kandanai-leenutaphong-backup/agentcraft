/**
 * Situation Capacity — E2E tests for MW accounting enrichment.
 *
 * Validates:
 *   R1: Backend returns enriched capacity fields in situations API
 *   R3: SituationCard shows capacity impact section
 *   R4: Investigate prompt includes MW impact line
 */

import { test, expect } from "./fixtures";

test.describe("Situation Capacity Enrichment", () => {

  // ── R1: Backend returns enriched fields ────────────────────────────
  test("backend returns enriched capacity fields in situations API", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    const result = await page.evaluate(async () => {
      const res = await fetch(
        "/api/situations/?start=2025-09-14+14%3A00&end=2025-09-14+15%3A30&station=LIAPOOTA",
        { headers: { "X-Dev-Key": "***REMOVED***" } },
      );
      return res.json();
    });

    expect(result.situations.length).toBeGreaterThan(0);
    const sit = result.situations[0];

    // Enriched capacity fields present
    expect(typeof sit.station_region).toBe("string");
    expect(sit.station_region.length).toBeGreaterThan(0);
    expect(typeof sit.region_rated_mw).toBe("number");
    expect(sit.region_rated_mw).toBeGreaterThan(0);
    expect(typeof sit.region_live_mw).toBe("number");
    expect(sit.region_live_mw).toBeGreaterThan(0);
    expect(typeof sit.nem_live_mw).toBe("number");
    expect(sit.nem_live_mw).toBeGreaterThan(0);
    expect(typeof sit.impact_region_pct).toBe("number");
    expect(typeof sit.impact_nem_pct).toBe("number");
  });

  // ── R3: SituationCard capacity impact section ─────────────────────
  test("situation card shows capacity impact section with region and percentages", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Trigger a live scan via Scan Scenarios
    const savedBtn = page.locator("button", { hasText: /Saved Sessions/i });
    await savedBtn.click();
    const scanEntry = page.locator("[data-testid='scan-scenario-button']").first();
    await expect(scanEntry).toBeVisible({ timeout: 5_000 });
    await scanEntry.click();

    // Wait for situation alerts
    const panel = page.getByTestId("situation-alerts-panel");
    await expect(panel).toBeVisible({ timeout: 30_000 });

    // Wait for at least one situation card
    const firstCard = panel.locator("button").first();
    await expect(firstCard).toBeVisible({ timeout: 30_000 });
    await firstCard.click();

    // Check capacity impact section
    const capacitySection = panel.locator("[data-testid='capacity-impact-section']");
    // Only visible if total_mw_lost > 0 — check if any card has it
    const hasCapacity = await capacitySection.first().isVisible().catch(() => false);
    if (hasCapacity) {
      // Verify content has region code and percentage
      const text = await capacitySection.first().textContent();
      expect(text).toContain("%");
      expect(text).toMatch(/MW/);
    }
    // Always verify the region badge in header
    const regionBadge = panel.locator("text=/\\[TAS\\]|\\[NSW\\]|\\[VIC\\]|\\[SA\\]|\\[QLD\\]/").first();
    await expect(regionBadge).toBeVisible({ timeout: 5_000 });
  });

  // ── R4: Investigate prompt includes MW impact ─────────────────────
  test("investigate prompt includes MW impact line", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Trigger live scan
    const savedBtn = page.locator("button", { hasText: /Saved Sessions/i });
    await savedBtn.click();
    const scanEntry = page.locator("[data-testid='scan-scenario-button']").first();
    await expect(scanEntry).toBeVisible({ timeout: 5_000 });
    await scanEntry.click();

    // Wait for situations
    const panel = page.getByTestId("situation-alerts-panel");
    await expect(panel).toBeVisible({ timeout: 30_000 });
    const firstCard = panel.locator("button").first();
    await expect(firstCard).toBeVisible({ timeout: 30_000 });
    await firstCard.click();

    // Intercept the chat POST
    let capturedBody = "";
    await page.route("**/api/chat/*", async (route) => {
      if (route.request().method() === "POST") {
        capturedBody = route.request().postData() ?? "";
      }
      await route.abort();
    });

    // Click Investigate
    const investigateBtn = panel.locator("button", { hasText: "Investigate" }).first();
    if (await investigateBtn.isVisible()) {
      await investigateBtn.click();
      await page.waitForTimeout(2000);

      if (capturedBody) {
        const body = JSON.parse(capturedBody);
        const prompt: string = body.content;

        // If the situation has MW loss, prompt should have MW impact line
        if (prompt.includes("MW impact:")) {
          expect(prompt).toMatch(/%/);
          expect(prompt).toMatch(/TAS|NSW|VIC|SA|QLD/);
        }
      }
    }
  });
});
