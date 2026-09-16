import { beforeEach, describe, expect, test } from "vitest";
import { render, screen } from "@testing-library/react";

import { OperatingStatePanel } from "@/components/panels/OperatingStatePanel";
import { usePanelStore } from "@/stores/panelStore";

describe("OperatingStatePanel", () => {
  beforeEach(() => {
    usePanelStore.setState({
      disturbanceSummary: null,
      operatingState: {
        checks: [
          {
            name: "Frequency within band",
            category: "satisfactory",
            status: "pass",
            detail: "System frequency is inside the normal operating band.",
          },
          {
            name: "Loss of largest generator manageable",
            category: "secure",
            status: "pass",
            detail: "The seeded startup state assumes N-1 generator security is intact.",
          },
        ],
      },
      priorityActions: null,
    });
  });

  test("renders explicit NORMAL labels for operators instead of ticks", () => {
    render(<OperatingStatePanel />);

    expect(screen.getByText("Satisfactory Operating State")).toBeTruthy();
    expect(screen.getByText("Secure Operating State")).toBeTruthy();
    expect(screen.getAllByText("NORMAL").length).toBeGreaterThanOrEqual(4);
    expect(screen.queryByText("✓")).toBeNull();
    expect(screen.queryByText("✗")).toBeNull();
  });
});