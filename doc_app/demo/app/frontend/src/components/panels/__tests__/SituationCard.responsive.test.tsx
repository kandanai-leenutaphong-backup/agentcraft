/**
 * Couturier R9 (2026-05-17) — responsive head-row regression.
 *
 * Pins the post-R9 shape:
 *   - Investigate button always exposes the accessible name "Investigate"
 *     regardless of whether the label is visually rendered (icon-only at
 *     narrow widths).
 *   - At narrow widths the head row renders the supplementary row-2
 *     element (MW · MW% · classification chip) under station; we assert
 *     by querying the row-2 test id rather than measuring the rendered
 *     layout because JSDOM does not evaluate container queries.
 *   - Severity pill precedes the classification chip in DOM order at
 *     every width (severity-first glance hierarchy from R1 must survive
 *     the R9 reflow).
 *
 * Vitest is currently skipped per the operator carve-out documented in
 * the prior audit run; this file is checked into source so that the
 * regression coverage exists the moment vitest is unblocked.
 */

import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import type { SituationRecord } from "@/api/situationApi";
import { useSituationStore } from "@/stores/situationStore";
import { SituationCard } from "../SituationCard";

const baseSituation: SituationRecord = {
  situation_id: "sit-r9-narrow",
  station: "ARARAT_BESS_T1",
  station_region: "VIC",
  severity: "CRITICAL",
  total_score: 18,
  alarm_score: 3,
  scada_score: 2,
  mw_boost: 1,
  total_mw_lost: 240,
  max_mw_drop: 240,
  alarm_count: 4,
  step_changes: 2,
  impact_station_pct: 87,
  impact_region_pct: 12,
  impact_nem_pct: 1,
  station_rated_mw: 275,
  station_unit_count: 1,
  region_rated_mw: 2500,
  region_live_mw: 2000,
  nem_live_mw: 24000,
  patterns: "compound_loss,bus_voltage_collapse",
  pattern_details: "{}",
  window_start: "2026-05-16T03:00:00",
  window_end: "2026-05-16T03:05:00",
  alarm_signals: "{}",
  scada_signals: "{}",
  alarm_mrids: "[]",
  affected_tags: "[]",
  affected_equipment: "[]",
  detected_at: "2026-05-16T03:05:00",
  detector_version: "test",
  config_hash: "test",
};

describe("SituationCard responsive head row (R9)", () => {
  beforeEach(() => {
    /* Seed a ready classification so both the wide-row and narrow-row
       chip instances render — otherwise ClassificationChip returns null
       and the row-2 fallback only carries MW/MW%. */
    useSituationStore.setState({
      classifications: {
        [baseSituation.situation_id]: {
          status: "ready",
          classification: "credible",
          rationale: "Within planning envelope.",
        },
      },
    } as never);
  });

  it("exposes 'Investigate' as accessible name regardless of label visibility", () => {
    render(<SituationCard situation={baseSituation} onInvestigate={() => {}} />);
    /* aria-label is always present; visible label may be hidden at
       narrow by a container query but the accessible name is stable. */
    expect(screen.getByRole("button", { name: "Investigate" })).toBeInTheDocument();
  });

  it("renders the narrow row-2 element under station", () => {
    render(<SituationCard situation={baseSituation} onInvestigate={() => {}} />);
    /* JSDOM does not evaluate container queries; the row-2 div is
       always in the DOM and the @[18rem]/card:hidden class controls
       its visibility at run-time. The contract we pin is structural:
       the supplementary row exists and carries the MW string. */
    const row2 = screen.getByTestId(`head-narrow-row-${baseSituation.situation_id}`);
    expect(row2).toBeInTheDocument();
    expect(row2.textContent ?? "").toMatch(/240\s*MW/);
    expect(row2.textContent ?? "").toMatch(/87%/);
  });

  it("severity pill precedes the classification chip in DOM order", () => {
    render(<SituationCard situation={baseSituation} onInvestigate={() => {}} />);
    const severity = screen.getByTestId(`severity-pill-${baseSituation.situation_id}`);
    /* getAllByTestId because the chip renders twice (wide row + narrow
       row-2). The first occurrence in source order is the wide-row
       chip; severity must precede it. */
    const chips = screen.getAllByTestId(`classify-badge-${baseSituation.situation_id}`);
    expect(chips.length).toBeGreaterThanOrEqual(1);
    const position = severity.compareDocumentPosition(chips[0]);
    /* DOCUMENT_POSITION_FOLLOWING = 4 — chip comes after severity. */
    expect(position & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});

/* ── Per-child Investigate preservation under arbitrary wrappers ─────
 *
 * Historically `<SituationCard />` was rendered as a child of
 * `SituationClusterCard`, which carried its own
 * `data-testid="investigate-cluster-…"` button. The cluster-card path
 * was retired (Undertaker 2026-05-24), but these guards stay: the
 * per-child `data-testid="investigate-{station}"` MUST keep working
 * inside any wrapper element so the single-situation flow (and every
 * test that selects by it) is unaffected by future re-parenting. */
describe("SituationCard — per-child Investigate preserved under cluster wrap (R4)", () => {
  it("renders the per-child investigate-{station} test-id when wrapped in a parent div", () => {
    render(
      <div data-testid="cluster-parent-wrapper">
        <SituationCard situation={baseSituation} onInvestigate={() => {}} />
      </div>,
    );
    expect(screen.getByTestId(`investigate-${baseSituation.station}`)).toBeInTheDocument();
  });

  it("exposes 'Investigate' as accessible name even when wrapped", () => {
    render(
      <section data-testid="cluster-parent-wrapper">
        <SituationCard situation={baseSituation} onInvestigate={() => {}} />
      </section>,
    );
    /* aria-label collapses to "Investigate {station}" regardless of
       parent — the cluster card must not have shadowed the per-child
       button. */
    expect(
      screen.getByRole("button", { name: `Investigate ${baseSituation.station}` }),
    ).toBeInTheDocument();
  });
});
