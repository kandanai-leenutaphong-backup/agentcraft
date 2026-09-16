/**
 * Situation Equipment Enrichment — E2E tests.
 *
 * Validates:
 *   R1: Backend returns affected_equipment with alarm and SCADA rows
 *   R3: Equipment boxes render with collapsible alarm/SCADA sub-lists
 *   R4: Investigate prompt includes per-equipment evidence
 */

import { test, expect } from "./fixtures";

test.describe("Situation Equipment Enrichment", () => {

  // ── R1: Backend returns affected_equipment ─────────────────────────
  test("backend returns affected_equipment with alarm and SCADA rows", async ({ authedPage: page }) => {
    // Navigate first so relative fetch URLs resolve correctly
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Call the situations API directly via fetch in the page context
    const result = await page.evaluate(async () => {
      const res = await fetch(
        "/api/situations/?start=2025-09-14+14%3A00&end=2025-09-14+15%3A30&station=LIAPOOTA",
        { headers: { "X-Dev-Key": "***REMOVED***" } },
      );
      return res.json();
    });

    expect(result.situations.length).toBeGreaterThan(0);
    const sit = result.situations[0];

    // affected_equipment is a JSON-encoded string
    const equipment = typeof sit.affected_equipment === "string"
      ? JSON.parse(sit.affected_equipment)
      : sit.affected_equipment;

    expect(Array.isArray(equipment)).toBe(true);
    expect(equipment.length).toBeGreaterThan(0);

    // At least one entry has alarms
    const withAlarms = equipment.filter((e: any) => e.alarms && e.alarms.length > 0);
    expect(withAlarms.length).toBeGreaterThan(0);

    // At least one entry has SCADA
    const withScada = equipment.filter((e: any) => e.scada && e.scada.length > 0);
    expect(withScada.length).toBeGreaterThan(0);

    // Verify alarm row fields
    const firstAlarm = withAlarms[0].alarms[0];
    expect(firstAlarm).toHaveProperty("timestamp_aest");
    expect(firstAlarm).toHaveProperty("alarm_label");
    expect(firstAlarm).toHaveProperty("alarm_text");
    expect(firstAlarm).toHaveProperty("priority");

    // Verify SCADA row fields
    const firstScada = withScada[0].scada[0];
    expect(firstScada).toHaveProperty("timestamp_aest");
    expect(firstScada).toHaveProperty("TagId");
    expect(firstScada).toHaveProperty("measurement");
    expect(firstScada).toHaveProperty("Value");
    expect(firstScada).toHaveProperty("prev_val");

    // Alarms sorted by priority ASC
    for (const eq of withAlarms) {
      for (let i = 1; i < eq.alarms.length; i++) {
        expect(eq.alarms[i].priority).toBeGreaterThanOrEqual(eq.alarms[i - 1].priority);
      }
    }

    // SCADA sorted by abs_drop DESC
    for (const eq of withScada) {
      for (let i = 1; i < eq.scada.length; i++) {
        expect(Math.abs(eq.scada[i].abs_drop)).toBeLessThanOrEqual(Math.abs(eq.scada[i - 1].abs_drop));
      }
    }
  });

  // ── R3: Equipment boxes render in placeholder mode ─────────────────
  test("equipment boxes render with collapsible alarm/SCADA sub-lists", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Ensure placeholder mode is ON
    const phToggle = page.getByTestId("placeholder-toggle");
    const phText = await phToggle.textContent();
    if (!phText?.includes("ON")) {
      await phToggle.click();
    }

    // Find the situation alerts panel
    const panel = page.getByTestId("situation-alerts-panel");
    await expect(panel).toBeVisible({ timeout: 10_000 });

    // Expand the first station group (it may already be expanded)
    const stationHeader = panel.locator("[data-testid='station-group-header']").first();
    if (await stationHeader.isVisible()) {
      await stationHeader.click();
    }

    // Now click the first situation card's expand button inside the station group
    const situationBtn = panel.locator("[data-testid='station-group']").first().locator("button").filter({ hasText: /MAJOR|CRITICAL|SERIOUS|INVESTIGATE|minor/i }).first();
    await expect(situationBtn).toBeVisible({ timeout: 5_000 });
    await situationBtn.click();

    // "Affected Equipment" section header should be visible
    await expect(panel.locator("text=Affected Equipment")).toBeVisible({ timeout: 5_000 });

    // At least 1 equipment box should render
    const equipBoxes = panel.locator("[data-testid='equipment-box']");
    await expect(equipBoxes.first()).toBeVisible({ timeout: 5_000 });

    // Click the first equipment box to expand it
    await equipBoxes.first().locator("button").first().click();

    // Alarm rows and/or SCADA rows should be visible
    const alarmRows = panel.locator("[data-testid='equipment-alarm-row']");
    const scadaRows = panel.locator("[data-testid='equipment-scada-row']");

    // At least one of alarm or SCADA rows should be present
    const alarmCount = await alarmRows.count();
    const scadaCount = await scadaRows.count();
    expect(alarmCount + scadaCount).toBeGreaterThan(0);
  });

  // ── R4: Investigate prompt includes station, time, and signals ───────
  test("investigate prompt includes station, time range, and signal counts", async ({ authedPage: page }) => {
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });

    // Ensure placeholder mode is ON
    const phToggle = page.getByTestId("placeholder-toggle");
    const phText = await phToggle.textContent();
    if (!phText?.includes("ON")) {
      await phToggle.click();
    }

    // Find the situation alerts panel and expand first card
    const panel = page.getByTestId("situation-alerts-panel");
    await expect(panel).toBeVisible({ timeout: 10_000 });
    const firstCard = panel.locator("button").first();
    await firstCard.click();

    // Intercept POST /api/chat/* to capture the prompt
    let capturedBody = "";
    await page.route("**/api/chat/*", async (route) => {
      const req = route.request();
      if (req.method() === "POST") {
        capturedBody = req.postData() ?? "";
      }
      // Abort the actual request — we only need to capture the body
      await route.abort();
    });

    // Click the Investigate button
    const investigateBtn = panel.locator("button", { hasText: "Investigate" }).first();
    await expect(investigateBtn).toBeVisible({ timeout: 5_000 });
    await investigateBtn.click();

    // Wait for the intercept to fire
    await page.waitForTimeout(2000);

    // Parse the captured body
    expect(capturedBody).toBeTruthy();
    const body = JSON.parse(capturedBody);
    const prompt: string = body.content;

    // Verify lean prompt: station name, time range, signal counts
    expect(prompt).toContain("Investigate");
    expect(prompt).toContain("LIAPOOTA");
    expect(prompt).toContain("2025-09-14");
    expect(prompt).toContain("Alarm signals:");
    expect(prompt).toContain("SCADA signals:");
    expect(prompt).toContain("cb_trip=");

    // Must NOT contain verbose equipment evidence (that caused timeouts)
    expect(prompt).not.toContain("AFFECTED EQUIPMENT");
    expect(prompt).not.toContain("P1 14:37");
  });
});
