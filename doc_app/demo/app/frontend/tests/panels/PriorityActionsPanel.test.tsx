import { beforeEach, describe, expect, test } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";

import { PriorityActionsPanel } from "@/components/panels/PriorityActionsPanel";
import { usePanelStore } from "@/stores/panelStore";

describe("PriorityActionsPanel", () => {
  beforeEach(() => {
    usePanelStore.setState({
      disturbanceSummary: null,
      operatingState: null,
      priorityActions: {
        actions: [
          {
            step: 1,
            action: "Open the C4 feeder breaker",
            reasoning: "## Evidence\n\n- Reverse power persisted for 11 minutes.\n- Protection X and Y remained unavailable.",
            guide: "1. Confirm switching authority.\n2. Open the C4 feeder breaker.\n3. Verify reverse power clears.",
          },
        ],
      },
    });
  });

  test("starts with a collapsed guide, expands to show citations, and shows markdown reasoning in the overlay", () => {
    render(<PriorityActionsPanel />);

    const guideToggle = screen.getByRole("button", { name: /guide/i });

    expect(screen.getByText("Guide")).toBeTruthy();
    expect(guideToggle.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByText("Confirm switching authority.")).toBeNull();
    expect(screen.queryByText("Supporting Signals")).toBeNull();

    fireEvent.click(guideToggle);

    expect(guideToggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Confirm switching authority.")).toBeTruthy();
    expect(screen.getByText("Sources")).toBeTruthy();
    expect(
      screen.getByRole("link", { name: /source 1: confirm switching authority\./i }).getAttribute("href"),
    ).toBe(
      "https://www.domain.com.au/energy-systems/electricity/national-electricity-market-nem/nem-events-and-reports/power-system-operating-incident-reports",
    );

    fireEvent.click(screen.getByRole("button", { name: /reasoning/i }));

    expect(screen.getByText("Evidence")).toBeTruthy();
    expect(screen.getByText("Reverse power persisted for 11 minutes.")).toBeTruthy();
    expect(screen.getByTitle("Font size: 14px")).toBeTruthy();
  });
});