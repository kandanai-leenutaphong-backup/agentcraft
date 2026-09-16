/**
 * Full-stack benchmark: Liapoota Bus Trip Investigation
 *
 * Verifies the complete pipeline — trigger to operator actions — with timing.
 * Tests both backend behavior (tools, delegation, persistence) and frontend
 * rendering (tabs, streaming, panels, action cards).
 *
 * This test is the CANONICAL reference for expected UI behavior during an
 * investigation. If UI behavior requirements change, update this test FIRST,
 * then implement the change.
 *
 * Expected flow:
 *   1. User types trigger → message bubble appears
 *   2. Investigator streams → streaming dot on tab, tokens in chat
 *   3. Tool calls render → collapsible cards (Find Station Assets, Find Alarms, etc.)
 *   4. Delegation fires → delegate_to_agent card appears
 *   5. Dispatcher tab appears → SubagentTab in tab bar (same row as Investigator)
 *   6. Dispatcher streams → background run banner visible, tokens + tool calls in Dispatcher tab
 *   7. Priority actions appear → cards fly into Operator Priorities panel with priority badges
 *   8. Complete → streaming indicators gone, all content static
 */

import { test, expect } from "./fixtures";

/** Timing record for benchmark reporting. */
interface BenchmarkTimings {
  triggerSent: number;
  firstToolCall?: number;
  delegationFired?: number;
  dispatcherTabVisible?: number;
  firstPriorityAction?: number;
  investigatorDone?: number;
  dispatcherDone?: number;
}

test.describe("Full-Stack Benchmark: Liapoota", () => {
  test("complete investigation pipeline with timing", async ({ authedPage: page }) => {
    const timings: BenchmarkTimings = { triggerSent: 0 };
    const t0 = Date.now();
    const elapsed = () => ((Date.now() - t0) / 1000).toFixed(1);

    // ── Phase 0: App loads ──────────────────────────────────────────
    await page.goto("/");
    await expect(page.locator("text=NEM GEM")).toBeVisible({ timeout: 30_000 });
    console.log(`[${elapsed()}s] App loaded`);

    // ── Phase 1: Create session + send trigger ──────────────────────
    await page.getByTestId("new-chat-button").click();
    const chatInput = page.getByPlaceholder("Send a message");
    await expect(chatInput).toBeVisible({ timeout: 15_000 });

    await chatInput.fill("Investigate LIAPOOTA, 2025-09-14 14:35:00 to 2025-09-14 14:45:00.\nAlarm signals: cb_trip=5, cb_cluster=5, kv_emer_bus=1, unreas=1.\nSCADA signals: bus_collapse=1, line_trip=1, line_overload=1.");
    await chatInput.press("Enter");
    timings.triggerSent = Date.now() - t0;
    console.log(`[${elapsed()}s] Trigger sent`);

    // ── Phase 2: Investigator starts streaming ──────────────────────
    // EXPECTED: Primary slot tab appears, then opening it reveals an
    // Investigator pill with a streaming pulse. The investigator agent
    // is no longer a top-level tab — it lives inside the Primary slot's
    // secondary row after the Grid Captain fan-out simplification.
    const investigatorStreamingDot = page.getByTestId("agent-tab-investigator-streaming");
    await expect(investigatorStreamingDot).toBeVisible({ timeout: 30_000 });
    console.log(`[${elapsed()}s] Investigator streaming`);

    // ── Phase 3: Tool calls render as cards ─────────────────────────
    // EXPECTED: At least one tool call card appears in the chat
    // Tool cards show display names from agent_config.yaml tool_display_names
    const toolCallCard = page.locator("button").filter({ hasText: /Station Summary|Event Timeline|Find Station Assets|Find Alarms|Find SCADA|SCADA Changes/i }).first();
    await expect(toolCallCard).toBeVisible({ timeout: 60_000 });
    timings.firstToolCall = Date.now() - t0;
    console.log(`[${elapsed()}s] First tool call card visible`);

    // ── Phase 4: Delegation fires ──────────────────────────────────
    // EXPECTED: delegate_to_agent tool call appears in chat
    const delegationCard = page.locator("button").filter({ hasText: /Delegate to Specialist/i }).first();
    await expect(delegationCard).toBeVisible({ timeout: 120_000 });
    timings.delegationFired = Date.now() - t0;
    console.log(`[${elapsed()}s] Delegation fired`);

    // ── Phase 5: Dispatcher tab appears ───────────────────────
    // EXPECTED: Inside the Primary slot's secondary row, a Dispatcher
    // pill appears with the instance id `dispatcher__primary`. We assert
    // the EXACT testid — the previous fallback chain (.or `subagent-tab*`)
    // silently masked regressions in the slot-aware tab routing.
    const dispatcherTab = page.getByTestId("agent-tab-dispatcher");
    await expect(dispatcherTab).toBeVisible({ timeout: 30_000 });
    timings.dispatcherTabVisible = Date.now() - t0;
    console.log(`[${elapsed()}s] Dispatcher tab visible`);

    await page.screenshot({ path: "test-results/benchmark-phase5-delegation.png" });

    // ── Phase 6: Dispatcher streams live ────────────────────────────
    // EXPECTED: Clicking Dispatcher tab shows:
    //   a) Streaming tokens in the Dispatcher conversation
    //   b) Tool call cards (Search Operating Procedures, Push Operator Action)
    //   c) Or delegation task message from the investigator
    //
    // The dispatcher runs search tools first (~30s), then generates text
    // with push_action calls. Allow generous timeout for content.

    await dispatcherTab.click();
    await page.waitForTimeout(2000);

    // Check for any dispatcher content: tool call cards, streaming text,
    // or the delegation task message. The ChatPanel renders messages in a
    // scrollable div — no data-testid on the container, so use broad
    // page-level locator scoped to visible text content.
    const dispatcherContent = page.locator("text=/Search Operating|Knowledge Base|Incident|Push Operator|operator-facing|investigation|findings|evidence|Liapoota/i").first();
    const hasDispatcherContent = await expect(dispatcherContent)
      .toBeVisible({ timeout: 90_000 })
      .then(() => true)
      .catch(() => false);
    console.log(`[${elapsed()}s] Dispatcher content: ${hasDispatcherContent ? "VISIBLE" : "NOT VISIBLE"}`);

    await page.screenshot({ path: "test-results/benchmark-phase6-dispatcher.png" });

    // ── Phase 7: Priority actions appear in panel ───────────────────
    // EXPECTED: Operator Priorities panel shows action cards with:
    //   - Priority badge (P5, P4, etc.)
    //   - Action text (equipment-specific instruction)
    //   - Expandable reasoning + guide
    //   - Fly-in animation on arrival
    //
    // Actions are pushed by the Dispatcher via push_action tool.
    // They appear in real-time via the background SSE subscription.

    // Switch back to the Investigator pill in the Primary slot to inspect
    // the full investigator transcript while the Dispatcher continues
    // streaming in the background.
    const investigatorTab = page.getByTestId("agent-tab-investigator");
    if (await investigatorTab.isVisible()) {
      await investigatorTab.click();
    }

    // Wait for priority actions — poll with generous timeout
    const priorityPanel = page.locator("[data-testid='priority-actions-panel']");
    const actionCards = priorityPanel.locator("[class*='rounded-lg']").filter({ hasText: /Hold|Contact|Assess|Open|Confirm|Check|Record|Verify|Monitor|Notify|Inspect|Review|Isolate|Restore/i });

    const hasActions = await expect.poll(
      async () => await actionCards.count() > 0,
      { timeout: 120_000, message: "Priority action cards should appear in the panel" },
    ).toBe(true).then(() => true).catch(() => false);

    if (hasActions) {
      timings.firstPriorityAction = Date.now() - t0;
      const count = await actionCards.count();
      console.log(`[${elapsed()}s] ${count} priority action card(s) visible`);
    } else {
      console.log(`[${elapsed()}s] NO priority actions visible (expected — SSE fix needed)`);
    }

    await page.screenshot({ path: "test-results/benchmark-phase7-actions.png" });

    // ── Phase 8: Investigation complete ─────────────────────────────
    // EXPECTED: Streaming indicators gone, content static
    await expect(investigatorStreamingDot).toBeHidden({ timeout: 60_000 });
    timings.investigatorDone = Date.now() - t0;
    console.log(`[${elapsed()}s] Investigator done`);

    await page.screenshot({ path: "test-results/benchmark-complete.png" });

    // ── Benchmark Report ────────────────────────────────────────────
    console.log("\n══════════════════════════════════════════════════");
    console.log("  FULL-STACK BENCHMARK: Liapoota Bus Trip");
    console.log("══════════════════════════════════════════════════");
    console.log(`  Trigger sent:         +${(timings.triggerSent / 1000).toFixed(1)}s`);
    console.log(`  First tool call:      +${timings.firstToolCall ? (timings.firstToolCall / 1000).toFixed(1) + "s" : "N/A"}`);
    console.log(`  Delegation fired:     +${timings.delegationFired ? (timings.delegationFired / 1000).toFixed(1) + "s" : "N/A"}`);
    console.log(`  Dispatcher tab:       +${timings.dispatcherTabVisible ? (timings.dispatcherTabVisible / 1000).toFixed(1) + "s" : "N/A"}`);
    console.log(`  First action card:    +${timings.firstPriorityAction ? (timings.firstPriorityAction / 1000).toFixed(1) + "s" : "MISSING"}`);
    console.log(`  Investigator done:    +${timings.investigatorDone ? (timings.investigatorDone / 1000).toFixed(1) + "s" : "N/A"}`);
    console.log(`  Dispatcher streaming: ${hasDispatcherContent ? "OK" : "FAILED"}`);
    console.log(`  Priority actions:     ${hasActions ? "OK" : "FAILED"}`);
    console.log("══════════════════════════════════════════════════\n");

    // ── Assertions ──────────────────────────────────────────────────
    // These are the HARD requirements. Test fails if any is false.

    // Tool calls MUST render in the investigator chat
    expect(timings.firstToolCall).toBeDefined();

    // Delegation MUST fire
    expect(timings.delegationFired).toBeDefined();

    // Dispatcher tab MUST appear
    expect(timings.dispatcherTabVisible).toBeDefined();

    // Dispatcher MUST stream content in the Dispatcher tab
    expect(hasDispatcherContent).toBe(true);

    // Priority actions MUST appear in the Operator Priorities panel
    expect(hasActions).toBe(true);
  });
});
